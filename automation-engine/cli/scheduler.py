# scheduler.py
import argparse, asyncio, sqlite3, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:/Crazy_poster")
DB_PATH = ROOT / "shared-resources" / "database" / "crazy_poster.db"

CLI = ROOT / "automation-engine" / "cli"
sys.path.append(str(CLI))
from post_campaign import run as run_campaign

def ensure_schedule_columns():
    conn=sqlite3.connect(DB_PATH); c=conn.cursor()
    cols=[r[1] for r in c.execute("PRAGMA table_info(listings)").fetchall()]
    if "scheduled_at" not in cols: c.execute("ALTER TABLE listings ADD COLUMN scheduled_at TEXT")
    conn.commit(); conn.close()

def pick_due(campaign_id, limit):
    conn=sqlite3.connect(DB_PATH); conn.row_factory=sqlite3.Row; c=conn.cursor()
    now=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    rows=c.execute("""
      SELECT * FROM listings
      WHERE campaign_id=? AND (status IS NULL OR status='pending')
        AND scheduled_at IS NOT NULL AND scheduled_at <= ?
      ORDER BY scheduled_at ASC, id ASC LIMIT ?
    """, (campaign_id, now, limit)).fetchall()
    conn.close(); return rows

async def main_async(account, campaign_id, limit, publish):
    ensure_schedule_columns()
    due = pick_due(campaign_id, limit)
    if not due:
        print("No due listings."); return
    # Reuse post_campaign runner but limit to N
    await run_campaign(account, campaign_id, limit=len(due), attempts=2, publish=publish)

def main():
    ap=argparse.ArgumentParser(description="Run scheduled listings")
    ap.add_argument("account"); ap.add_argument("campaign_id", type=int)
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--publish", action="store_true")
    args=ap.parse_args()
    asyncio.run(main_async(args.account, args.campaign_id, args.limit, args.publish))

if __name__=="__main__":
    main()
