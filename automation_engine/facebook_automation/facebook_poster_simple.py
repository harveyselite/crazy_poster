# facebook_poster_simple.py
import asyncio, json, os, random, time
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image
from playwright.async_api import async_playwright

class SimpleFacebookPoster:
    def __init__(self, account_name: str):
        self.account_name = account_name
        self.base_path = Path("C:/Crazy_poster")
        self.account_path = self.base_path / "account-instances" / account_name
        self.browser_profile_path = self.account_path / "browser-profile"
        self.context = None
        self.page = None

    # ---------- logging ----------
    def log(self, msg: str): print(f"[{self.account_name}] {msg}")

    # ---------- browser ----------
    async def start_browser(self):
        try:
            self.log("Starting browser...")
            pw = await async_playwright().start()
            self.context = await pw.chromium.launch_persistent_context(
                user_data_dir=str(self.browser_profile_path),
                headless=False,
                viewport={"width": 1366, "height": 768},
            )
            self.page = await self.context.new_page()
            self.log("Browser started successfully")
            return True
        except Exception as e:
            self.log(f"Browser start failed: {e}")
            return False

    async def goto_facebook(self):
        try:
            await self.page.goto("https://www.facebook.com", wait_until="domcontentloaded")
            self.log("Navigated to Facebook")
            return True
        except Exception as e:
            self.log(f"Navigation failed: {e}")
            return False

    async def close_browser(self):
        try:
            if self.context:
                await self.context.close()
            self.log("Browser closed")
        except Exception as e:
            self.log(f"Error closing browser: {e}")

    # ---------- generic helpers ----------
    async def _first_visible(self, locators, timeout_each=1500):
        for loc in locators:
            try:
                await loc.wait_for(timeout=timeout_each)
                return loc
            except:
                continue
        return None

    async def _try_click_any(self, selectors: list, scope=None, timeout_each=1500) -> bool:
        page = scope or self.page
        for sel in selectors:
            try:
                loc = page.locator(sel) if isinstance(sel, str) else (sel if scope is None else scope.locator(sel.selector))
                await loc.wait_for(timeout=timeout_each)
                await loc.click()
                await asyncio.sleep(0.4)
                return True
            except:
                continue
        return False

    async def save_screenshot(self, listing_id: str, tag: str = "error") -> str | None:
        try:
            out_dir = self.account_path / "screenshots"
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{listing_id}-{int(time.time())}-{tag}.png"
            await self.page.screenshot(path=str(path), full_page=True)
            self.log(f"Saved screenshot: {path}")
            return str(path)
        except Exception as e:
            self.log(f"Screenshot failed: {e}")
            return None

    # ---------- vehicle type first ----------
    VEHICLE_TYPE_SYNONYMS = ["Vehicle type", "Type", "Vehicle category", "Category"]

    async def _open_dropdown_by_label(self, names: list[str]):
        locs = []
        for n in names:
            locs += [
                self.page.get_by_label(n),
                self.page.get_by_role("combobox", name=n),
                self.page.locator(f"label:has-text('{n}')").locator(
                    "xpath=following::*[(self::div or self::button or self::input) and (@role='combobox' or @aria-haspopup or self::input)][1]"
                ),
                self.page.locator(f"[aria-label*='{n}' i]"),
            ]
        locs.append(self.page.get_by_role("combobox").first)
        for loc in locs:
            try:
                await loc.wait_for(timeout=1500)
                await loc.click()
                await asyncio.sleep(0.25)
                return loc
            except:
                continue
        return None

    async def _pick_option(self, value: str):
        try:
            await self.page.get_by_role("option", name=value, exact=False).click(timeout=1200)
            return True
        except:
            try:
                await self.page.keyboard.type(value, delay=int(random.uniform(35, 90)))
                await asyncio.sleep(0.25)
                await self.page.keyboard.press("Enter")
                return True
            except:
                return False

    async def ensure_vehicle_type_first(self, target="Car/Truck"):
        self.log("Setting Vehicle type first...")
        dd = await self._open_dropdown_by_label(self.VEHICLE_TYPE_SYNONYMS)
        if not dd:
            try:
                await self.page.get_by_role("button", name=target).click(timeout=1500)
                self.log(f"Vehicle type set via tile: {target}")
            except:
                self.log("Vehicle type control not found; continue but fields may not render.")
                return False
        else:
            if not await self._pick_option(target):
                self.log(f"Vehicle type selection failed for: {target}")
                return False
            self.log(f"Vehicle type set: {target}")

        try:
            await asyncio.wait_for(asyncio.shield(self.page.wait_for_load_state("networkidle")), timeout=5)
        except:
            pass
        for loc in [
            self.page.get_by_label("Year"),
            self.page.get_by_placeholder("Year"),
            self.page.get_by_role("combobox", name="Year"),
        ]:
            try:
                await loc.wait_for(timeout=2000)
                return True
            except:
                continue
        self.log("Vehicle type set, but Year/Make not visible yet.")
        return False

    # ---------- field typing/select ----------
    FIELD_SYNONYMS = {
        "Year": ["Year"],
        "Make": ["Make", "Manufacturer"],
        "Model": ["Model", "Variant"],
        "Mileage": ["Mileage", "Kilometers", "Odometer", "KM"],
        "Price": ["Price", "Selling price", "Amount"],
        "Description": ["Description", "Details"],
        "Location": ["Location", "Enter location", "City", "Postal code"],
    }

    def _candidates_for(self, name: str):
        names = self.FIELD_SYNONYMS.get(name, [name])
        locs = []
        for n in names:
            locs += [
                self.page.get_by_label(n),
                self.page.get_by_placeholder(n),
                self.page.get_by_role("combobox", name=n),
                self.page.locator(
                    f"xpath=//label[normalize-space()='{n}']/following::*[self::input or self::textarea or @contenteditable='true'][1]"
                ),
                self.page.locator(f"[aria-label='{n}']"),
            ]
        if name == "Description":
            locs += [
                self.page.locator('[role="textbox"][contenteditable="true"]'),
                self.page.locator("div[contenteditable='true']"),
            ]
        return locs

    async def _smart_field(self, name: str):
        return await self._first_visible(self._candidates_for(name), timeout_each=2000)

    async def _type_smart(self, locator, text, label=""):
        try:
            if locator is None:
                raise RuntimeError("locator is None")
            await locator.click()
            await asyncio.sleep(0.15)
            try:
                ce = await locator.get_attribute("contenteditable")
            except:
                ce = None
            if ce == "true":
                await self.page.keyboard.press("Ctrl+A")
                await asyncio.sleep(0.05)
                await self.page.keyboard.press("Backspace")
                for ch in str(text):
                    await self.page.keyboard.type(ch, delay=int(random.uniform(30, 80)))
            else:
                try:
                    await locator.fill("")
                except:
                    pass
                for ch in str(text):
                    await locator.type(ch, delay=int(random.uniform(30, 80)))
            self.log(f"Typed {label or 'field'}: {text}")
            return True
        except Exception as e:
            self.log(f"Could not type {label or 'field'}: {e}")
            return False

    async def _select_combo(self, name: str, value: str):
        try:
            cb = await self._smart_field(name)
            if not cb:
                self.log(f"{name}: combobox not found")
                return False
            await cb.click()
            await asyncio.sleep(0.15)
            for ch in str(value):
                await self.page.keyboard.type(ch, delay=int(random.uniform(25, 60)))
            await asyncio.sleep(0.2)
            try:
                await self.page.get_by_role("option", name=value, exact=False).click(timeout=1000)
            except:
                await self.page.keyboard.press("Enter")
            self.log(f"Selected {name}: {value}")
            return True
        except Exception as e:
            self.log(f"{name}: selection failed: {e}")
            return False

    # ---------- location ----------
    async def set_location(self, location_text: str) -> bool:
        if not location_text:
            return True
        try:
            loc = await self._smart_field("Location")
            if not loc:
                self.log("Location field not found; continuing without it.")
                return False
            await loc.click()
            await asyncio.sleep(0.15)
            try:
                await loc.fill("")
            except:
                pass
            await loc.type(location_text, delay=30)
            await asyncio.sleep(0.6)
            # pick first suggestion if present
            try:
                await self.page.get_by_role("option").first.click(timeout=1200)
            except:
                await self.page.keyboard.press("Enter")
            self.log(f"Location set: {location_text}")
            return True
        except Exception as e:
            self.log(f"Location set failed: {e}")
            return False

    # ---------- images ----------
    def _ext_from_url(self, url: str, default=".jpg"):
        try:
            path = urlparse(url).path
            ext = os.path.splitext(path)[1].lower()
            if ext in [".jpg", ".jpeg", ".png", ".webp"]:
                return ext
        except:
            pass
        return default

    def _sanitize_ext(self, ext: str):
        return ".jpg" if ext.lower() in [".jpeg", ".jpg"] else (ext if ext.lower() in [".png", ".webp"] else ".jpg")

    def _save_verified(self, content: bytes, dest_path: Path):
        with Image.open(BytesIO(content)) as im:
            im.verify()
        dest_path.write_bytes(content)

    async def download_listing_images(self, items: list[str], listing_id: str = "listing"):
        """
        Accepts URLs or local file paths. Local paths pass-through.
        URLs are downloaded under: account/temp-images/<listing_id>-<ts>/img_X.ext
        Returns list of local file paths.
        """
        if not items:
            return []
        all_local = []
        # If any item is already a local file, just use it
        for idx, it in enumerate(items, 1):
            p = Path(it)
            if p.exists() and p.is_file():
                all_local.append(str(p))
        if len(all_local) == len(items):
            self.log(f"Using cached local images: {len(all_local)}")
            return all_local

        out_dir = self.account_path / "temp-images" / f"{listing_id}-{int(time.time())}"
        out_dir.mkdir(parents=True, exist_ok=True)
        saved = []
        for idx, url in enumerate(items, 1):
            if str(url).lower().startswith("http"):
                try:
                    self.log(f"Downloading image {idx}: {url}")
                    r = requests.get(url, timeout=20)
                    if r.status_code != 200 or not r.content:
                        self.log(f"Skip (HTTP {r.status_code})")
                        continue
                    ext = self._sanitize_ext(self._ext_from_url(url))
                    dest = out_dir / f"img_{idx}{ext}"
                    self._save_verified(r.content, dest)
                    saved.append(str(dest))
                except Exception as e:
                    self.log(f"Skip image {idx}: {e}")
        self.log(f"Images downloaded: {len(saved)} â†’ {out_dir}")
        return saved

    async def upload_images(self, file_paths: list[str]):
        if not file_paths:
            self.log("No image files provided")
            return False
        try:
            before = await self.page.locator("img").count()
        except:
            before = 0

        # Strategy 1
        try:
            await self.page.set_input_files("input[type='file']", file_paths)
            self.log("Images queued via input[type=file]")
        except Exception as e1:
            self.log(f"Direct input upload not available: {e1}")
            # Strategy 2
            try:
                btns = [
                    self.page.get_by_role("button", name="Add photos"),
                    self.page.get_by_role("button", name="Add Photos"),
                    self.page.get_by_text("Add photos").first,
                    self.page.get_by_text("Add Photos").first,
                ]
                trigger = await self._first_visible(btns, 1200) or self.page.locator("input[type='file']").nth(0)
                async with self.page.expect_file_chooser(timeout=5000) as fc:
                    await trigger.click()
                chooser = await fc.value
                await chooser.set_files(file_paths)
                self.log("Images queued via file chooser")
            except Exception as e2:
                self.log(f"Fallback chooser failed: {e2}")
                return False

        try:
            for _ in range(50):
                await asyncio.sleep(0.4)
                after = await self.page.locator("img").count()
                if after > before:
                    self.log(f"Thumbnails detected: {after - before} new")
                    return True
        except:
            pass
        self.log("Could not confirm thumbnails; verify visually.")
        return True

    # ---------- form fill ----------
    async def fill_vehicle_listing(self, d: dict):
        try:
            await asyncio.sleep(1.0)
            try:
                btn = self.page.get_by_role("button", name="Car/Truck")
                await btn.click(timeout=1200)
                self.log("Vehicle type set: Car/Truck")
            except:
                pass

            # Location first (exact match requested)
            await self.set_location(d.get("location", ""))

            year_ok  = await self._select_combo("Year",  str(d.get("year", "")))  or await self._type_smart(await self._smart_field("Year"),  d.get("year", ""),  "Year")
            make_ok  = await self._select_combo("Make",  d.get("make", ""))       or await self._type_smart(await self._smart_field("Make"),  d.get("make", ""),  "Make")
            model_ok = await self._select_combo("Model", d.get("model", ""))      or await self._type_smart(await self._smart_field("Model"), d.get("model", ""), "Model")

            mileage_ok = await self._type_smart(await self._smart_field("Mileage"), str(d.get("mileage", "")).replace(",", ""), "Mileage/Kilometers")
            price_ok   = await self._type_smart(await self._smart_field("Price"),   str(d.get("price", "")).replace(",", ""),   "Price")

            await self._select_combo("Body style",          d.get("bodyStyle", "Sedan"))
            await self._select_combo("Exterior color",      d.get("colorExt", "Silver"))
            await self._select_combo("Interior color",      d.get("colorInt", "Black"))
            await self._select_combo("Vehicle condition",   d.get("condition", "Excellent"))
            await self._select_combo("Fuel type",           d.get("fuel", "Gasoline"))
            await self._select_combo("Transmission",        d.get("transmission", "Automatic"))

            desc_ok = await self._type_smart(await self._smart_field("Description"), d.get("description", ""), "Description")

            core_ok = all([year_ok, make_ok, model_ok, mileage_ok, price_ok, desc_ok])
            self.log("Core fields populated successfully." if core_ok else "Core fields missingâ€”verify visually.")
            return core_ok
        except Exception as e:
            self.log(f"Error filling vehicle listing: {e}")
            return False

    # ---------- publish flow ----------
    async def _clear_groups_if_any(self):
        try:
            checked = self.page.get_by_role("checkbox", checked=True)
            n = await checked.count()
            for i in range(n):
                await checked.nth(0).click()
                await asyncio.sleep(0.15)
            if n:
                self.log(f"Cleared {n} preselected group(s)")
        except Exception as e:
            self.log(f"Group clear skipped: {e}")

    async def _apply_hide_from_friends(self, flag: bool):
        try:
            label = self.page.get_by_text("Hide from friends", exact=False).first
            await label.wait_for(timeout=900)
            toggle = label.locator("xpath=following::*[@role='switch' or @role='checkbox' or input[@type='checkbox']][1]")
            try:
                current = await toggle.get_attribute("aria-checked")
                desired = "true" if flag else "false"
                if current != desired:
                    await toggle.click()
                    await asyncio.sleep(0.2)
                    self.log(f"Hide from friends set to {flag}")
            except:
                if flag:
                    await toggle.click()
                    await asyncio.sleep(0.2)
                    self.log("Hide from friends toggled on (fallback)")
        except:
            pass

    async def _wait_publish_success(self, timeout_ms=12000) -> tuple[bool, str | None]:
        try:
            await self.page.wait_for_url("**/marketplace/item/**", timeout=timeout_ms)
            return True, self.page.url
        except:
            pass
        try:
            await self.page.get_by_text("Your listing is live", exact=False).wait_for(timeout=4000)
            return True, self.page.url
        except:
            pass
        return False, None

    async def finalize_and_publish(self, listing: dict, prefer_no_groups: bool = True) -> tuple[bool, str | None]:
        self.log("Finalizing listing (Publish flow)â€¦")

        publish_buttons = [
            self.page.get_by_role("button", name="Publish"),
            self.page.get_by_role("button", name="Publish listing"),
            self.page.get_by_role("button", name="Post"),
            self.page.get_by_text("Publish listing", exact=False).first,
            self.page.get_by_text("Publish", exact=False).first,
            "button:has-text('Publish')",
            "button:has-text('Post')",
        ]
        next_buttons = [
            self.page.get_by_role("button", name="Next"),
            self.page.get_by_role("button", name="Continue"),
            self.page.get_by_text("Next", exact=False).first,
            self.page.get_by_text("Continue", exact=False).first,
            "button:has-text('Next')",
            "button:has-text('Continue')",
        ]

        hide_flag = str(listing.get("hideFromFriends", "0")).strip().lower() in ("1", "true", "yes", "y")
        await self._apply_hide_from_friends(hide_flag)

        async def click_any(scope=None):
            if await self._try_click_any(publish_buttons, scope=scope): return "publish"
            if await self._try_click_any(next_buttons,    scope=scope): return "next"
            try:
                dialog = self.page.locator('[role="dialog"]').first
                await dialog.wait_for(timeout=600)
                if await self._try_click_any(publish_buttons, scope=dialog): return "publish"
                if await self._try_click_any(next_buttons,    scope=dialog): return "next"
            except:
                pass
            return None

        # Attempt chain: publish immediately, else 3 rounds of next->publish
        action = await click_any()
        if action == "publish":
            ok, url = await self._wait_publish_success()
            if ok: return True, url

        for _ in range(3):
            if action != "next":
                action = await click_any()
                if action != "publish":
                    break
            await asyncio.sleep(0.8)
            if prefer_no_groups:
                await self._clear_groups_if_any()
            action = await click_any()
            if action == "publish":
                ok, url = await self._wait_publish_success()
                if ok: return True, url

        self.log("Publish not confirmed; leaving window open for manual review.")
        return False, None
