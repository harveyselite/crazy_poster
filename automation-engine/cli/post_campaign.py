# post_campaign.py
import argparse, asyncio, json, random, re, sqlite3, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:/Crazy_poster")
DB_PATH = ROOT / "shared-resources" / "database" / "crazy_poster.db"

FB_AUTOMATION = ROOT / "automation-engine" / "facebook_automation"
sys.path.append(str(FB_AUTOMATION))
from facebook_poster_simple import SimpleFacebookPoster

def now_utc(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def has_column(conn, table, col):
    return any(r[1]==col for r in conn.execute(f"PRAGMA table_info({table})").fetchall())

def ensure_columns():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    cols = [r[1] for r in c.execute("PRAGMA table_info(listings)").fetchall()]
    to_add = []
    if "status" not in cols:               to_add.append("ALTER TABLE listings ADD COLUMN status TEXT")
    if "post_attempts" not in cols:        to_add.append("ALTER TABLE listings ADD COLUMN post_attempts INTEGER")
    if "last_posted_at" not in cols:       to_add.append("ALTER TABLE listings ADD COLUMN last_posted_at TEXT")
    if "fb_listing_url" not in cols:       to_add.append("ALTER TABLE listings ADD COLUMN fb_listing_url TEXT")
    if "images_cached_dir" not in cols:    to_add.append("ALTER TABLE listings ADD COLUMN images_cached_dir TEXT")
    if "images_cached_json" not in cols:   to_add.append("ALTER TABLE listings ADD COLUMN images_cached_json TEXT")
    if "last_error_screenshot" not in cols:to_add.append("ALTER TABLE listings ADD COLUMN last_error_screenshot TEXT")
    for sql in to_add: c.execute(sql)
    conn.commit(); conn.close()

def fetch_listings(campaign_id, limit, only_status="pending"):
    conn = sqlite3.connect(DB_PATH); conn.row_factory=sqlite3.Row; c=conn.cursor()
    cols=[r[1] for r in c.execute("PRAGMA table_info(listings)").fetchall()]
    where = "campaign_id=?"; params=[campaign_id]
    if "status" in cols:
        if only_status=="pending":
            where += " AND (status IS NULL OR status='pending')"
        else:
            where += " AND status=?"; params.append(only_status)
    sql=f"SELECT * FROM listings WHERE {where} ORDER BY id ASC LIMIT ?"; params.append(limit)
    rows=c.execute(sql, params).fetchall(); conn.close(); return rows

def update_listing_status(listing_id, *, status=None, attempts_inc=0, fb_url=None, error_screenshot=None):
    conn = sqlite3.connect(DB_PATH); c=conn.cursor(); sets=[]; vals=[]
    if attempts_inc: sets.append("post_attempts=COALESCE(post_attempts,0)+?"); vals.append(attempts_inc)
    if status is not None and has_column(conn,"listings","status"): sets.append("status=?"); vals.append(status)
    if has_column(conn,"listings","last_posted_at"): sets.append("last_posted_at=?"); vals.append(now_utc())
    if fb_url and has_column(conn,"listings","fb_listing_url"): sets.append("fb_listing_url=?"); vals.append(fb_url)
    if error_screenshot and has_column(conn,"listings","last_error_screenshot"): sets.append("last_error_screenshot=?"); vals.append(error_screenshot)
    if sets:
        vals.append(listing_id)
        c.execute(f"UPDATE listings SET {', '.join(sets)} WHERE id=?", vals)
        conn.commit()
    conn.close()

def parse_images(row):
    # prefer cached dir/json
    images=[]
    if "images_cached_dir" in row.keys() and row["images_cached_dir"]:
        d = Path(row["images_cached_dir"])
        if d.exists():
            files = sorted([str(p) for p in d.iterdir() if p.is_file()])
            if files: return files[:10]
    if "images_cached_json" in row.keys() and row["images_cached_json"]:
        try:
            arr = json.loads(row["images_cached_json"])
            if isinstance(arr, list) and arr: return arr[:10]
        except: pass
    # JSON column
    if "images_json" in row.keys() and row["images_json"]:
        try:
            val = json.loads(row["images_json"]) if isinstance(row["images_json"], str) else row["images_json"]
            if isinstance(val, list): images = val
        except: pass
    # raw string column
    if (not images) and "images" in row.keys() and row["images"]:
        import re as _re
        parts = _re.split(r"[;\s,]+", row["images"].strip())
        images = [p for p in parts if p]
    return images[:10]

def row_to_listing_dict(row):
    def g(col, default=""): return row[col] if col in row.keys() and row[col] is not None else default
    clean_int = lambda v: int(re.sub(r"[^\d]","",str(v))) if str(v).strip() else ""
    return {
        "year": int(g("year", 0)) if str(g("year","")).isdigit() else g("year",""),
        "make": g("make",""),
        "model": g("model",""),
        "mileage": clean_int(g("mileage","")),
        "price": clean_int(g("price","")),
        "bodyStyle": g("body_style", g("bodystyle","")),
        "colorExt": g("color_ext",""),
        "colorInt": g("color_int",""),
        "condition": g("condition",""),
        "fuel": g("fuel",""),
        "transmission": g("transmission",""),
        "description": g("description",""),
        "vehicleType": g("vehicle_type", g("vehicleType","Car/Truck")),
        "titleStatus": g("title_status",""),
        "location": g("location",""),  # exact match from CSV
        "title": g("title",""),
        "hideFromFriends": g("hide_from_friends", g("hideFromFriends","0")),
    }

async def post_single_listing(account, row, *, do_publish: bool, listing_tag: str):
    listing = row_to_listing_dict(row)
    images = parse_images(row)

    bot = SimpleFacebookPoster(account)
    fb_url = None
    try:
        if not await bot.start_browser(): return False, None, None
        if not await bot.goto_facebook(): return False, None, None

        await bot.page.goto("https://www.facebook.com/marketplace/create/vehicle")
        await asyncio.sleep(1.5)

        if not await bot.ensure_vehicle_type_first(listing.get("vehicleType","Car/Truck")):
            return False, None, None

        if images:
            files = await bot.download_listing_images(images, listing_id=listing_tag)
            if files: await bot.upload_images(files)

        if not await bot.fill_vehicle_listing(listing):
            return False, None, None

        if do_publish:
            ok_pub, fb_url = await bot.finalize_and_publish(listing, prefer_no_groups=True)
            if not ok_pub:
                shot = await bot.save_screenshot(listing_tag, "publish-not-confirmed")
                return False, fb_url, shot
        return True, fb_url, None

    except Exception:
        try:
            shot = await bot.save_screenshot(listing_tag, "exception")
        except:
            shot = None
        return False, None, shot
    finally:
        try: await bot.close_browser()
        except: pass

async def run(account: str, campaign_id: int, *, limit=1, attempts=2, publish=False):
    ensure_columns()
    rows = fetch_listings(campaign_id, limit, only_status="pending")
    if not rows:
        print("No pending listings found for this campaign.")
        return

    print(f"Queued {len(rows)} listing(s) from campaign {campaign_id} for account '{account}'.")
    for row in rows:
        lid = row["id"]; title = row["title"] if "title" in row.keys() else "(no title)"
        tag = f"c{campaign_id}-l{lid}"
        print(f"\n--- Listing {lid}: {title} ---")

        success=False; url=None; shot=None
        for a in range(1, attempts+1):
            print(f"Attempt {a}/{attempts} …")
            ok, url, shot = await post_single_listing(account, row, do_publish=publish, listing_tag=tag)
            update_listing_status(lid, attempts_inc=1)
            if ok:
                success=True
                update_listing_status(lid, status=("posted" if publish else "prepared"), fb_url=url)
                print(f"✓ Success ({'published' if publish else 'prepared only'}){f' → {url}' if url else ''}")
                break
            else:
                print("× Failed this attempt.")

        if not success:
            update_listing_status(lid, status="failed", error_screenshot=shot)
            print(f"× Marked as failed. Screenshot: {shot or '(none)'}")

def main():
    ap = argparse.ArgumentParser(description="Run Crazy_poster campaign")
    ap.add_argument("account")
    ap.add_argument("campaign_id", type=int)
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--attempts", type=int, default=2)
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()
    asyncio.run(run(args.account, args.campaign_id, limit=args.limit, attempts=args.attempts, publish=args.publish))

if __name__ == "__main__":
    main()
