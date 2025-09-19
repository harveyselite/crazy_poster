# set_pending.py
import sqlite3
DB = r"C:/Crazy_poster/shared-resources/database/crazy_poster.db"
CAMPAIGN_ID = 1

conn = sqlite3.connect(DB)
cur = conn.cursor()
# Re-queue anything not definitively done; keep 'posted' and 'failed' intact.
cur.execute("""
    UPDATE listings
    SET status='pending'
    WHERE campaign_id=? AND (status IS NULL OR status NOT IN ('posted','failed'))
""", (CAMPAIGN_ID,))
print("Rows re-queued:", cur.rowcount)
conn.commit()
conn.close()
