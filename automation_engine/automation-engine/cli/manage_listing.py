# manage_listing.py
import argparse, asyncio, sqlite3, sys
from pathlib import Path

ROOT = Path(r"C:/Crazy_poster")
DB_PATH = ROOT / "shared-resources" / "database" / "crazy_poster.db"

FB_AUTOMATION = ROOT / "automation_engine" / "facebook_automation"
sys.path.append(str(FB_AUTOMATION))
from facebook_poster_simple import SimpleFacebookPoster

def get_url_from_db(listing_id: int) -> str | None:
    conn=sqlite3.connect(DB_PATH); c=conn.cursor()
    row=c.execute("SELECT fb_listing_url FROM listings WHERE id=?", (listing_id,)).fetchone()
    conn.close()
    return row[0] if row and row[0] else None

async def mark_sold(account: str, url: str):
    bot=SimpleFacebookPoster(account)
    try:
        if not await bot.start_browser(): return False
        if not await bot.goto_facebook(): return False
        await bot.page.goto(url)
        # common buttons
        for sel in [
            bot.page.get_by_role("button", name="Mark as sold"),
            bot.page.get_by_text("Mark as sold", exact=False).first,
            "button:has-text('Mark as sold')",
        ]:
            try:
                loc = sel if isinstance(sel,str) else sel
                await (loc if isinstance(loc,str) else loc).click(timeout=3000)
                await asyncio.sleep(1.0)
                return True
            except: pass
        return False
    finally:
        try: await bot.close_browser()
        except: pass

async def delete_listing(account: str, url: str):
    bot=SimpleFacebookPoster(account)
    try:
        if not await bot.start_browser(): return False
        if not await bot.goto_facebook(): return False
        await bot.page.goto(url)
        for sel in [
            bot.page.get_by_role("button", name="Delete listing"),
            bot.page.get_by_text("Delete listing", exact=False).first,
            "button:has-text('Delete listing')",
        ]:
            try:
                loc = sel if isinstance(sel,str) else sel
                await (loc if isinstance(loc,str) else loc).click(timeout=3000)
                await asyncio.sleep(0.8)
                # confirm dialog
                try:
                    await bot.page.get_by_role("button", name="Delete").click(timeout=3000)
                except:
                    await bot.page.get_by_text("Delete", exact=False).first.click(timeout=3000)
                await asyncio.sleep(1.0)
                return True
            except: pass
        return False
    finally:
        try: await bot.close_browser()
        except: pass

def main():
    ap=argparse.ArgumentParser(description="Manage Marketplace listing")
    ap.add_argument("account")
    sub=ap.add_subparsers(dest="cmd", required=True)

    ms=sub.add_parser("sold");  ms.add_argument("--url");  ms.add_argument("--id", type=int)
    dl=sub.add_parser("delete");dl.add_argument("--url");  dl.add_argument("--id", type=int)

    args=ap.parse_args()
    url = args.url or (get_url_from_db(args.id) if getattr(args,"id",None) else None)
    if not url:
        print("Provide --url or --id with fb_listing_url in DB"); return

    if args.cmd=="sold":
        asyncio.run(mark_sold(args.account, url))
    elif args.cmd=="delete":
        asyncio.run(delete_listing(args.account, url))

if __name__=="__main__":
    main()
