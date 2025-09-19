import argparse, json, os, sqlite3, sys, time
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image
from io import BytesIO

ROOT = Path(r"C:/Crazy_poster")
DB_PATH = ROOT / "shared-resources" / "database" / "crazy_poster.db"
CACHE_ROOT = ROOT / "assets" / "image-cache"

def ensure_columns():
    conn = sqlite3.connect(DB_PATH); c=conn.cursor()
    cols=[r[1] for r in c.execute("PRAGMA table_info(listings)").fetchall()]
    adds=[]
    if "images_cached_dir" not in cols:  adds.append("ALTER TABLE listings ADD COLUMN images_cached_dir TEXT")
    if "images_cached_json" not in cols: adds.append("ALTER TABLE listings ADD COLUMN images_cached_json TEXT")
    for sql in adds: c.execute(sql)
    conn.commit(); conn.close()

def list_rows(campaign_id):
    conn=sqlite3.connect(DB_PATH); conn.row_factory=sqlite3.Row; c=conn.cursor()
    rows=c.execute("SELECT * FROM listings WHERE campaign_id=? ORDER BY id ASC", (campaign_id,)).fetchall()
    conn.close(); return rows

def parse_images(row):
    if "images_json" in row.keys() and row["images_json"]:
        try:
            v = json.loads(row["images_json"]) if isinstance(row["images_json"], str) else row["images_json"]
            if isinstance(v, list) and v: return v
        except: pass
    if "images" in row.keys() and row["images"]:
        import re
        parts = re.split(r"[;\s,]+", row["images"].strip())
        return [p for p in parts if p]
    return []

def ext_from_url(url, default=".jpg"):
    try:
        e=os.path.splitext(urlparse(url).path)[1].lower()
        if e in [".jpg",".jpeg",".png",".webp"]: return e
    except: pass
    return default

def save_verified(content: bytes, dest: Path):
    with Image.open(BytesIO(content)) as im:
        im.verify()
    dest.write_bytes(content)

def cache_for_campaign(campaign_id: int, limit: int | None):
    ensure_columns()
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    rows = list_rows(campaign_id)
    if limit: rows = rows[:limit]
    conn=sqlite3.connect(DB_PATH); c=conn.cursor()

    total=0; cached=0
    for row in rows:
        total+=1
        lid=row["id"]
        urls=parse_images(row)
        if not urls: continue
        out_dir = CACHE_ROOT / f"c{campaign_id}" / f"l{lid}"
        out_dir.mkdir(parents=True, exist_ok=True)
        files=[]
        for i,u in enumerate(urls[:10],1):
            if str(u).lower().startswith("http"):
                try:
                    r=requests.get(u, timeout=20)
                    if r.status_code!=200 or not r.content: continue
                    dest=out_dir / f"img_{i}{ext_from_url(u)}"
                    save_verified(r.content, dest)
                    files.append(str(dest))
                except: continue
            else:
                p=Path(u)
                if p.exists() and p.is_file():
                    files.append(str(p))
        if files:
            c.execute("UPDATE listings SET images_cached_dir=?, images_cached_json=? WHERE id=?",
                      (str(out_dir), json.dumps(files), lid))
            conn.commit()
            cached+=1
            print(f"✓ Cached {len(files)} images for listing {lid} → {out_dir}")
    conn.close()
    print(f"\nDone. Listings processed: {total}, cached: {cached}")

def main():
    ap = argparse.ArgumentParser(description="Pre-cache campaign images for fast posting")
    ap.add_argument("campaign_id", type=int)
    ap.add_argument("--limit", type=int, default=None)
    args=ap.parse_args()
    cache_for_campaign(args.campaign_id, args.limit)

if __name__=="__main__":
    main()
