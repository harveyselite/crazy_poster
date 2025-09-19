# debug_listings.py
import sqlite3, collections
DB = r"C:/Crazy_poster/shared-resources/database/crazy_poster.db"
CAMPAIGN_ID = 1

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

rows = cur.execute(
    "SELECT id, title, status, COALESCE(post_attempts,0) AS attempts "
    "FROM listings WHERE campaign_id=? ORDER BY id", (CAMPAIGN_ID,)
).fetchall()

print(f"Listings for campaign {CAMPAIGN_ID}: {len(rows)}")
counts = collections.Counter((r["status"] or "NULL") for r in rows)
print("Status breakdown:", dict(counts))
for r in rows[:10]:
    print(f"#{r['id']:>3} | {r['status'] or 'NULL':<8} | attempts={r['attempts']} | {r['title'][:60]}")
conn.close()
