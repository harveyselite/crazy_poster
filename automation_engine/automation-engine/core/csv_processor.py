# csv_processor.py
# Crazy_poster â€” CSV intake, validation, import, and listing retrieval
import csv
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
from pathlib import Path  # (ensure imported at top)


import typer

app = typer.Typer(help="Crazy_poster CSV pipeline")
BASE = Path(r"C:/Crazy_poster")
DB_PATH = BASE / "shared-resources" / "database" / "crazy_poster.db"
def has_column(conn, table: str, col: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == col for row in cur.fetchall())

# ---- Canonical schema (supports aliases) ----
CANON_HEADERS = [
    "stock_type","campaign","platform","title","vehicleType","make","model","year",
    "mileage","price","week_price","bodyStyle","colorExt","colorInt","condition","fuel",
    "transmission","titleStatus","location","description","images","groups",
    "hideFromFriends","id"
]

ALIASES = {
    "stock type": "stock_type",
    "vehicletype": "vehicleType",
    "bodystyle": "bodyStyle",
    "colorext": "colorExt",
    "colorint": "colorInt",
    "titlestatus": "titleStatus",
    "week price": "week_price",
    "hidefromfriends": "hideFromFriends",
}

REQUIRED_FOR_POST = ["make","model","year","mileage","price","description","images"]
DEFAULTS = {
    "platform": "facebook",
    "vehicleType": "Car/Truck",
    "stock_type": "used",
    "hideFromFriends": "0",
}

# ---- DB bootstrap ----
def ensure_tables():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_name TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active'
    );
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER NOT NULL,
        row_id TEXT, -- CSV id column if present
        title TEXT,
        vehicle_type TEXT,
        make TEXT, model TEXT, year INTEGER,
        mileage INTEGER, price INTEGER, week_price INTEGER,
        body_style TEXT, color_ext TEXT, color_int TEXT,
        condition TEXT, fuel TEXT, transmission TEXT,
        title_status TEXT,
        location TEXT,
        description TEXT,
        images_json TEXT,    -- list[str]
        groups TEXT,
        hide_from_friends INTEGER DEFAULT 0,
        platform TEXT DEFAULT 'facebook',
        stock_type TEXT,
        status TEXT DEFAULT 'queued', -- queued|posted|failed|skipped|sold
        post_attempts INTEGER DEFAULT 0,
        last_posted_at TEXT,
        fb_listing_url TEXT,
        raw_json TEXT,       -- store entire CSV row normalized
        created_at TEXT NOT NULL,
        FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    conn.close()

# ---- CSV parsing utilities ----
def normalize_header(h: str) -> str:
    key = (h or "").strip()
    key = key.replace(" ", "_") if key.lower() == "stock type" else key
    k = key.replace(" ", "")
    k = ALIASES.get(k.lower(), key)
    return k

def read_csv_rows(path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        raw_headers = [normalize_header(h) for h in reader.fieldnames or []]
        rows = []
        for r in reader:
            nr = {}
            for k, v in r.items():
                nr[normalize_header(k)] = (v or "").strip()
            rows.append(nr)
    return rows, raw_headers

def images_to_list(val: str) -> List[str]:
    """
    Extract all http(s) URLs. Handles commas/semicolons/whitespace and
    concatenated patterns like ...jpghttps://...
    """
    text = (val or "").replace("|", ",").replace(";", ",")
    return list(dict.fromkeys(re.findall(r"https?://[^\s,]+", text)))  # de-dupe, preserve order

def to_int(x: Any, default: int = 0) -> int:
    try:
        s = str(x).replace(",", "").strip()
        return int(float(s)) if s else default
    except:
        return default

def boolish(x: Any) -> int:
    s = str(x).strip().lower()
    return 1 if s in ("1","true","yes","y","on") else 0

# ---- Validation ----
@dataclass
class ValidationResult:
    valid: bool
    row_count: int
    errors: List[str]
    warnings: List[str]

def validate_rows(rows: List[Dict[str, str]], headers: List[str]) -> ValidationResult:
    errs, warns = [], []

    # Header coverage
    missing_headers = [h for h in REQUIRED_FOR_POST if h not in headers]
    if missing_headers:
        errs.append(f"Missing required columns: {', '.join(missing_headers)}")

    # Row checks
    for i, r in enumerate(rows, start=2):  # +2 for header 1-based UX
        # fill defaults
        for k, v in DEFAULTS.items():
            r.setdefault(k, v)

        # required non-empty
        for req in REQUIRED_FOR_POST:
            if not (r.get(req) or "").strip():
                errs.append(f"Row {i}: '{req}' is empty")

        # numeric sanity
        y = to_int(r.get("year", 0))
        if y < 1900 or y > 2035:
            warns.append(f"Row {i}: unusual year '{r.get('year')}'")

        mi = to_int(r.get("mileage", 0))
        if mi <= 0:
            warns.append(f"Row {i}: mileage '{r.get('mileage')}' not positive")

        pr = to_int(r.get("price", 0))
        if pr <= 0:
            warns.append(f"Row {i}: price '{r.get('price')}' not positive")

        # image URLs present
        if not images_to_list(r.get("images", "")):
            errs.append(f"Row {i}: no valid image URLs")

    return ValidationResult(valid=(len(errs) == 0), row_count=len(rows), errors=errs, warnings=warns)

# ---- Import ----
from datetime import datetime, timezone  # (ensure this import exists at top)

def get_or_create_campaign(campaign_name: str, csv_filename: Optional[str] = None) -> int:
    ensure_tables()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM campaigns WHERE campaign_name = ?", (campaign_name,))
    row = c.fetchone()
    if row:
        cid = row[0]
    else:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
        cols = ["campaign_name", "created_at", "status"]
        vals = [campaign_name, now, "active"]

        # Legacy schema support: if campaigns.csv_filename exists and is NOT NULL, we must populate it
        if has_column(conn, "campaigns", "csv_filename"):
            cols.append("csv_filename")
            vals.append(csv_filename or "")

        placeholders = ",".join(["?"] * len(vals))
        c.execute(f"INSERT INTO campaigns ({','.join(cols)}) VALUES ({placeholders})", tuple(vals))
        cid = c.lastrowid
        conn.commit()
    conn.close()
    return cid


def import_rows(campaign_id: int, rows: List[Dict[str, str]]) -> int:
    ensure_tables()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.utcnow().isoformat() + "Z"
    inserted = 0

    for r in rows:
        # fill defaults
        for k, v in DEFAULTS.items():
            r.setdefault(k, v)

        imgs = images_to_list(r.get("images", ""))

        c.execute("""
            INSERT INTO listings (
                campaign_id, row_id, title, vehicle_type,
                make, model, year, mileage, price, week_price,
                body_style, color_ext, color_int, condition, fuel, transmission,
                title_status, location, description,
                images_json, groups, hide_from_friends, platform, stock_type,
                status, post_attempts, last_posted_at, fb_listing_url, raw_json, created_at
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            campaign_id,
            r.get("id") or None,
            r.get("title") or "",
            r.get("vehicleType") or "Car/Truck",
            r.get("make") or "",
            r.get("model") or "",
            to_int(r.get("year"), 0),
            to_int(r.get("mileage"), 0),
            to_int(r.get("price"), 0),
            to_int(r.get("week_price"), 0),
            r.get("bodyStyle") or "",
            r.get("colorExt") or "",
            r.get("colorInt") or "",
            r.get("condition") or "",
            r.get("fuel") or "",
            r.get("transmission") or "",
            r.get("titleStatus") or "",
            r.get("location") or "",
            r.get("description") or "",
            json.dumps(imgs),
            r.get("groups") or "",
            boolish(r.get("hideFromFriends", 0)),
            r.get("platform") or "facebook",
            r.get("stock_type") or "used",
            "queued",
            0,
            None,
            None,
            json.dumps(r),
            now
        ))
        inserted += 1

    conn.commit()
    conn.close()
    return inserted

# ---- Query helpers for automation engine ----
def get_campaigns_summary() -> List[Dict[str, Any]]:
    ensure_tables()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT c.id, c.campaign_name, c.status,
               COUNT(l.id) as listing_count,
               SUM(CASE WHEN l.status='posted' THEN 1 ELSE 0 END) as posted_count
        FROM campaigns c
        LEFT JOIN listings l ON l.campaign_id = c.id
        GROUP BY c.id, c.campaign_name, c.status
        ORDER BY c.id DESC
    """)
    rows = c.fetchall()
    conn.close()
    out = []
    for r in rows:
        out.append({
            "id": r[0], "campaign_name": r[1], "status": r[2],
            "listing_count": r[3] or 0, "posted_count": r[4] or 0
        })
    return out

def get_campaign_listings(campaign_id: int) -> List[Dict[str, Any]]:
    ensure_tables()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, title, make, model, year, mileage, price, description, images_json,
               body_style, color_ext, color_int, condition, fuel, transmission
        FROM listings
        WHERE campaign_id = ?
        ORDER BY id ASC
    """, (campaign_id,))
    rows = c.fetchall()
    conn.close()
    out = []
    for r in rows:
        out.append({
            "id": r[0],
            "title": r[1],
            "make": r[2], "model": r[3], "year": r[4],
            "mileage": r[5], "price": r[6],
            "description": r[7],
            "images": json.loads(r[8] or "[]"),
            "bodyStyle": r[9], "colorExt": r[10], "colorInt": r[11],
            "condition": r[12], "fuel": r[13], "transmission": r[14],
        })
    return out

# ---- CLI commands ----
@app.command("validate")
def cli_validate(csv_file: str):
    """
    Validate a CSV against the Crazy_poster schema.
    """
    p = Path(csv_file)
    if not p.exists():
        typer.echo(f"âœ— File not found: {p}")
        raise typer.Exit(code=1)

    rows, headers = read_csv_rows(p)
    res = validate_rows(rows, headers)

    typer.echo(f"CSV Validation: {'âœ“ VALID' if res.valid else 'âœ— INVALID'}")
    typer.echo(f"Rows: {res.row_count}")
    if res.errors:
        typer.echo("\nErrors:")
        for e in res.errors[:50]:
            typer.echo(f"  - {e}")
        if len(res.errors) > 50:
            typer.echo(f"  ...and {len(res.errors)-50} more")
    if res.warnings:
        typer.echo("\nWarnings:")
        for w in res.warnings[:50]:
            typer.echo(f"  - {w}")

    raise typer.Exit(code=0 if res.valid else 2)

@app.command("import")
def cli_import(csv_file: str, campaign_name: str):
    """
    Import a CSV into a new or existing campaign.
    """
    p = Path(csv_file)
    if not p.exists():
        typer.echo(f"âœ— File not found: {p}")
        raise typer.Exit(code=1)

    rows, headers = read_csv_rows(p)
    res = validate_rows(rows, headers)
    if not res.valid:
        typer.echo("âœ— Import blocked: CSV failed validation. Run `validate` and fix issues.")
        raise typer.Exit(code=2)

    cid = get_or_create_campaign(campaign_name, Path(csv_file).name)
    count = import_rows(cid, rows)
    typer.echo(f"âœ“ Imported {count} listings into campaign '{campaign_name}' (ID {cid})")

@app.command("campaigns")
def cli_campaigns():
    """List campaigns + counts."""
    data = get_campaigns_summary()
    if not data:
        typer.echo("No campaigns found.")
        return
    typer.echo("\nCampaigns:")
    typer.echo("-"*80)
    for d in data:
        typer.echo(f"ID {d['id']:<4} | {d['campaign_name']:<24} | "
                   f"Listings: {d['listing_count']:<4} | Posted: {d['posted_count']:<4} | Status: {d['status']}")

@app.command("listings")
def cli_listings(campaign_id: int, limit: int = 10):
    """Show first N listings for a campaign (mapped for the poster)."""
    lst = get_campaign_listings(campaign_id)
    if not lst:
        typer.echo("No listings found.")
        return
    typer.echo(f"Showing up to {limit} listings for campaign {campaign_id}:\n" + "-"*80)
    for i, it in enumerate(lst[:limit], start=1):
        typer.echo(f"{i:>2}. {it['year']} {it['make']} {it['model']} â€” ${it['price']} | images: {len(it['images'])}")
        typer.echo(f"    Title: {it.get('title','')[:64]}")
        typer.echo(f"    Desc : {it['description'][:64]}...")
        if i == limit:
            break

if __name__ == "__main__":
    app()
