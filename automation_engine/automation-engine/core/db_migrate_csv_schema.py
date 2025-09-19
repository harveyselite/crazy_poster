# db_migrate_csv_schema.py
# One-time SQLite migrations for Crazy_poster CSV pipeline.
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB = Path(r"C:/Crazy_poster/shared-resources/database/crazy_poster.db")

def colset(conn, table):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}

def add_col(conn, table, name, decl, default_sql=None):
    if name in colset(conn, table):
        return False
    ddl = f"ALTER TABLE {table} ADD COLUMN {name} {decl}"
    if default_sql:
        ddl += f" DEFAULT {default_sql}"
    conn.execute(ddl)
    return True

def ensure_campaigns(conn):
    # create table if missing
    conn.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_name TEXT NOT NULL UNIQUE
        )
    """)
    changed = False
    changed |= add_col(conn, "campaigns", "created_at", "TEXT", None)
    changed |= add_col(conn, "campaigns", "status", "TEXT", "'active'")
    if changed:
        # backfill created_at & status
        now = datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
        conn.execute("UPDATE campaigns SET created_at = COALESCE(created_at, ?)", (now,))
        conn.execute("UPDATE campaigns SET status = COALESCE(status, 'active')")
    return changed

def ensure_listings(conn):
    # create table if missing (minimal shape)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL
        )
    """)
    required = {
        "row_id": "TEXT",
        "title": "TEXT",
        "vehicle_type": "TEXT",
        "make": "TEXT",
        "model": "TEXT",
        "year": "INTEGER",
        "mileage": "INTEGER",
        "price": "INTEGER",
        "week_price": "INTEGER",
        "body_style": "TEXT",
        "color_ext": "TEXT",
        "color_int": "TEXT",
        "condition": "TEXT",
        "fuel": "TEXT",
        "transmission": "TEXT",
        "title_status": "TEXT",
        "location": "TEXT",
        "description": "TEXT",
        "images_json": "TEXT",
        "groups": "TEXT",
        "hide_from_friends": "INTEGER",
        "platform": "TEXT",
        "stock_type": "TEXT",
        "status": "TEXT",
        "post_attempts": "INTEGER",
        "last_posted_at": "TEXT",
        "fb_listing_url": "TEXT",
        "raw_json": "TEXT",
        "created_at": "TEXT",
    }
    changed = False
    for name, decl in required.items():
        changed |= add_col(conn, "listings", name, decl, None)
    return changed

def main():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB))
    try:
        ch1 = ensure_campaigns(conn)
        ch2 = ensure_listings(conn)
        conn.commit()
        print(f"Migration complete. campaigns_changed={ch1}, listings_changed={ch2}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
