# app.py
import csv
import io
import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from flask import Flask, request, redirect, url_for, render_template_string, flash
from apscheduler.schedulers.background import BackgroundScheduler

# ---- Paths & imports ---------------------------------------------------------
ROOT = Path(r"C:/Crazy_poster")
DB_PATH = ROOT / "shared-resources" / "database" / "crazy_poster.db"
FB_AUTOMATION = ROOT / "automation-engine" / "facebook_automation"
ASSETS = ROOT / "assets"
IMAGE_CACHE_ROOT = ASSETS / "image-cache"

import sys
sys.path.append(str(FB_AUTOMATION))
from facebook_poster_simple import SimpleFacebookPoster  # <-- your working class

app = Flask(__name__)
app.secret_key = "crazy_poster_secret"
scheduler = BackgroundScheduler()
scheduler.start()

# ---- Helpers -----------------------------------------------------------------
def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_schema():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = connect()
    c = conn.cursor()
    # campaigns
    c.execute("""
      CREATE TABLE IF NOT EXISTS campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_name TEXT UNIQUE,
        status TEXT,
        created_at TEXT,
        next_run_at TEXT,
        publish_by_default INTEGER DEFAULT 0
      )
    """)
    # listings (base)
    c.execute("""
      CREATE TABLE IF NOT EXISTS listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER,
        platform TEXT,
        title TEXT,
        vehicle_type TEXT,
        make TEXT,
        model TEXT,
        year TEXT,
        mileage TEXT,
        price TEXT,
        body_style TEXT,
        color_ext TEXT,
        color_int TEXT,
        condition TEXT,
        fuel TEXT,
        transmission TEXT,
        description TEXT,
        location TEXT,
        images TEXT,
        images_json TEXT,
        status TEXT,
        post_attempts INTEGER,
        last_posted_at TEXT,
        fb_listing_url TEXT,
        images_cached_dir TEXT,
        images_cached_json TEXT,
        last_error_screenshot TEXT
      )
    """)
    conn.commit()
    conn.close()

def has_column(table: str, col: str) -> bool:
    conn = connect()
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    conn.close()
    return col in cols

def list_accounts() -> List[str]:
    acc_root = ROOT / "account-instances"
    if not acc_root.exists(): return []
    return sorted([p.name for p in acc_root.iterdir() if p.is_dir()])

def parse_images_from_row(row: sqlite3.Row) -> List[str]:
    # Prefer cached first
    if row.get("images_cached_json"):
        try:
            j = json.loads(row["images_cached_json"])
            if isinstance(j, list) and j: return j[:10]
        except:
            pass
    if row.get("images_json"):
        try:
            j = json.loads(row["images_json"])
            if isinstance(j, list) and j: return j[:10]
        except:
            pass
    if row.get("images"):
        parts = re.split(r"[;\s,]+", row["images"].strip())
        parts = [p for p in parts if p]
        return parts[:10]
    return []

def row_to_listing_dict(row: sqlite3.Row) -> dict:
    def g(col, default=""):
        return row[col] if col in row.keys() and row[col] is not None else default
    clean_int = lambda v: int(re.sub(r"[^\d]", "", str(v))) if str(v).strip() else ""
    return {
        "vehicleType": g("vehicle_type", g("vehicleType", "Car/Truck")),
        "year": int(g("year", 0)) if str(g("year", "")).isdigit() else g("year", ""),
        "make": g("make", ""),
        "model": g("model", ""),
        "mileage": clean_int(g("mileage", "")),
        "price": clean_int(g("price", "")),
        "bodyStyle": g("body_style", g("bodystyle", "")),
        "colorExt": g("color_ext", ""),
        "colorInt": g("color_int", ""),
        "condition": g("condition", ""),
        "fuel": g("fuel", ""),
        "transmission": g("transmission", ""),
        "description": g("description", ""),
        "location": g("location", ""),
        "title": g("title", ""),
        "hideFromFriends": g("hide_from_friends", g("hideFromFriends", "0")),
    }

# ---- CSV import & image caching ---------------------------------------------
def import_csv_bytes(campaign_name: str, data: bytes) -> int:
    """
    Imports a CSV (bytes) into the DB under campaign_name.
    Returns campaign_id.
    """
    ensure_schema()
    conn = connect()
    c = conn.cursor()

    # create or get campaign
    row = c.execute("SELECT id FROM campaigns WHERE campaign_name=?", (campaign_name,)).fetchone()
    if row:
        campaign_id = row["id"]
    else:
        c.execute("INSERT INTO campaigns (campaign_name, status, created_at) VALUES (?, ?, ?)",
                  (campaign_name, "active", now_utc()))
        campaign_id = c.lastrowid

    # parse CSV
    f = io.StringIO(data.decode("utf-8-sig"))
    rdr = csv.DictReader(f)
    required = ["platform","title","vehicleType","make","model","year","mileage","price","description","location"]
    missing = [h for h in required if h not in rdr.fieldnames]
    if missing:
        conn.close()
        raise ValueError(f"Missing columns: {', '.join(missing)}")

    count = 0
    for row in rdr:
        # images: prefer images_json; else images
        images_json = None
        if row.get("images_json"):
            try:
                images_json = json.dumps(json.loads(row["images_json"]))
            except:
                images_json = None
        images = row.get("images", "")

        c.execute("""
          INSERT INTO listings (
            campaign_id, platform, title, vehicle_type, make, model, year, mileage, price,
            body_style, color_ext, color_int, condition, fuel, transmission, description,
            location, images, images_json, status
          ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            campaign_id, row.get("platform","facebook"), row.get("title",""),
            row.get("vehicleType","Car/Truck"), row.get("make",""), row.get("model",""),
            row.get("year",""), row.get("mileage",""), row.get("price",""),
            row.get("bodyStyle",""), row.get("colorExt",""), row.get("colorInt",""),
            row.get("condition",""), row.get("fuel",""), row.get("transmission",""),
            row.get("description",""), row.get("location",""),
            images, images_json, "pending"
        ))
        count += 1

    conn.commit()
    conn.close()
    return campaign_id

def cache_images_for_campaign(campaign_id: int) -> int:
    """
    Downloads and caches images for all listings in campaign.
    Saves local paths in images_cached_* columns.
    """
    ensure_schema()
    IMAGE_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    conn = connect()
    c = conn.cursor()
    rows = c.execute("SELECT * FROM listings WHERE campaign_id=?", (campaign_id,)).fetchall()
    cached = 0
    for row in rows:
        lid = row["id"]
        urls = parse_images_from_row(row)
        if not urls: continue
        out_dir = IMAGE_CACHE_ROOT / f"c{campaign_id}" / f"l{lid}"
        out_dir.mkdir(parents=True, exist_ok=True)
        local_files = []

        # If url starts with http, let facebook_poster_simple download/verify later.
        # Here we only keep a pass-through cache: if it's a local path, copy; if http, store the URL list.
        # To keep it simple, we just store whatever we have as images_cached_json.
        for u in urls[:10]:
            local_files.append(u)

        c.execute("UPDATE listings SET images_cached_dir=?, images_cached_json=? WHERE id=?",
                  (str(out_dir), json.dumps(local_files), lid))
        cached += 1

    conn.commit()
    conn.close()
    return cached

# ---- Posting engine (uses your SimpleFacebookPoster) -------------------------
def update_listing_status(listing_id: int, *, status: Optional[str] = None,
                          fb_url: Optional[str] = None, error_screenshot: Optional[str] = None):
    conn = connect(); c = conn.cursor()
    sets, vals = [], []
    sets.append("post_attempts = COALESCE(post_attempts,0) + 1")
    if status is not None: sets.append("status=?"); vals.append(status)
    sets.append("last_posted_at=?"); vals.append(now_utc())
    if fb_url: sets.append("fb_listing_url=?"); vals.append(fb_url)
    if error_screenshot: sets.append("last_error_screenshot=?"); vals.append(error_screenshot)
    vals.append(listing_id)
    c.execute(f"UPDATE listings SET {', '.join(sets)} WHERE id=?", vals)
    conn.commit(); conn.close()

async def post_single_listing(account: str, row: sqlite3.Row, do_publish: bool):
    listing = row_to_listing_dict(row)
    images = parse_images_from_row(row)
    tag = f"c{row['campaign_id']}-l{row['id']}"
    bot = SimpleFacebookPoster(account)
    fb_url = None
    try:
        if not await bot.start_browser(): return False, None, None
        if not await bot.goto_facebook(): return False, None, None
        await bot.page.goto("https://www.facebook.com/marketplace/create/vehicle")
        await bot.ensure_vehicle_type_first(listing.get("vehicleType","Car/Truck"))

        if images:
            files = await bot.download_listing_images(images, listing_id=tag)
            if files: await bot.upload_images(files)

        filled = await bot.fill_vehicle_listing(listing)
        if not filled: return False, None, None

        if do_publish:
            ok_pub, fb_url = await bot.finalize_and_publish(listing, prefer_no_groups=True)
            if not ok_pub:
                shot = await bot.save_screenshot(tag, "publish-not-confirmed")
                return False, fb_url, shot
        return True, fb_url, None
    except Exception:
        try:
            shot = await bot.save_screenshot(tag, "exception")
        except:
            shot = None
        return False, None, shot
    finally:
        try: await bot.close_browser()
        except: pass

def run_campaign_background(account: str, campaign_id: int, limit: int, publish: bool):
    """
    Runs in a thread; uses asyncio per listing.
    """
    import asyncio
    conn = connect()
    rows = conn.execute("""
        SELECT * FROM listings
        WHERE campaign_id=? AND (status IS NULL OR status='pending')
        ORDER BY id ASC LIMIT ?
    """, (campaign_id, limit)).fetchall()
    conn.close()

    async def _run():
        for row in rows:
            ok, url, shot = await post_single_listing(account, row, publish)
            update_listing_status(row["id"],
                                  status=("posted" if publish and ok else "prepared" if ok else "failed"),
                                  fb_url=url,
                                  error_screenshot=(None if ok else shot))
    asyncio.run(_run())

# ---- APScheduler job helpers -------------------------------------------------
def schedule_campaign_once(campaign_id: int, dt_iso: str, account: str, publish: bool, limit: int):
    """
    Stores in DB and creates an APScheduler one-shot job.
    """
    conn = connect(); c = conn.cursor()
    c.execute("UPDATE campaigns SET next_run_at=? WHERE id=?", (dt_iso, campaign_id))
    conn.commit(); conn.close()

    # Remove existing job id if any
    job_id = f"campaign-{campaign_id}"
    try:
        scheduler.remove_job(job_id)
    except:
        pass

    # Schedule
    run_dt = datetime.fromisoformat(dt_iso.replace("Z","+00:00"))
    scheduler.add_job(
        func=lambda: run_campaign_background(account, campaign_id, limit, publish),
        trigger="date",
        run_date=run_dt,
        id=job_id,
        replace_existing=True,
    )

# ---- Routes / UI -------------------------------------------------------------
BASE_HTML = """
<!doctype html>
<title>Crazy Poster</title>
<link rel="stylesheet" href="https://unpkg.com/mvp.css">
<main>
  <header>
    <h1>Crazy Poster — Dashboard</h1>
    <nav>
      <a href="{{ url_for('dashboard') }}">Dashboard</a>
      <a href="{{ url_for('upload_csv') }}">Upload CSV</a>
    </nav>
  </header>
  {% with messages = get_flashed_messages() %}
    {% if messages %}
      <aside>
        {% for m in messages %}<p>{{ m }}</p>{% endfor %}
      </aside>
    {% endif %}
  {% endwith %}
  {% block body %}{% endblock %}
</main>
"""

@app.route("/")
def dashboard():
    ensure_schema()
    conn = connect()
    camps = conn.execute("""
      SELECT
        c.id, c.campaign_name, c.status, c.created_at, c.next_run_at,
        SUM(CASE WHEN l.status IS NULL OR l.status='pending' THEN 1 ELSE 0 END) AS pending,
        SUM(CASE WHEN l.status='prepared' THEN 1 ELSE 0 END) AS prepared,
        SUM(CASE WHEN l.status='posted' THEN 1 ELSE 0 END) AS posted,
        COUNT(l.id) as total
      FROM campaigns c
      LEFT JOIN listings l ON l.campaign_id=c.id
      GROUP BY c.id
      ORDER BY c.id DESC
    """).fetchall()
    conn.close()
    accounts = list_accounts()
    return render_template_string(BASE_HTML + """
{% block body %}
<section>
  <h2>Campaigns</h2>
  <table>
    <thead><tr>
      <th>ID</th><th>Name</th><th>Stats</th><th>Next run</th><th>Actions</th>
    </tr></thead>
    <tbody>
    {% for c in camps %}
      <tr>
        <td>{{ c['id'] }}</td>
        <td><a href="{{ url_for('campaign_detail', campaign_id=c['id']) }}">{{ c['campaign_name'] }}</a></td>
        <td>
          pending {{ c['pending'] or 0 }} |
          prepared {{ c['prepared'] or 0 }} |
          posted {{ c['posted'] or 0 }} |
          total {{ c['total'] or 0 }}
        </td>
        <td>{{ c['next_run_at'] or '-' }}</td>
        <td>
          <details>
            <summary>Run now</summary>
            <form method="post" action="{{ url_for('run_now') }}">
              <input type="hidden" name="campaign_id" value="{{ c['id'] }}">
              <label>Account
                <select name="account" required>
                  {% for a in accounts %}<option value="{{ a }}">{{ a }}</option>{% endfor %}
                </select>
              </label>
              <label>Limit <input type="number" name="limit" value="1" min="1"></label>
              <label><input type="checkbox" name="publish"> Publish</label>
              <button type="submit">Run</button>
            </form>
          </details>
          <details>
            <summary>Schedule</summary>
            <form method="post" action="{{ url_for('schedule_once') }}">
              <input type="hidden" name="campaign_id" value="{{ c['id'] }}">
              <label>Run at (UTC ISO)
                <input name="when" placeholder="2025-09-20T14:30:00Z" required>
              </label>
              <label>Account
                <select name="account" required>
                  {% for a in accounts %}<option value="{{ a }}">{{ a }}</option>{% endfor %}
                </select>
              </label>
              <label>Limit <input type="number" name="limit" value="1" min="1"></label>
              <label><input type="checkbox" name="publish"> Publish</label>
              <button type="submit">Save & Schedule</button>
            </form>
          </details>
        </td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
</section>
{% endblock %}
""", camps=camps, accounts=accounts)

@app.route("/upload", methods=["GET", "POST"])
def upload_csv():
    ensure_schema()
    if request.method == "POST":
        campaign = request.form.get("campaign") or "Campaign_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        file = request.files.get("csvfile")
        if not file or file.filename == "":
            flash("Please choose a CSV file")
            return redirect(request.url)
        try:
            cid = import_csv_bytes(campaign, file.read())
            flash(f"✓ Imported CSV into campaign '{campaign}' (ID {cid})")
            return redirect(url_for("campaign_detail", campaign_id=cid))
        except Exception as e:
            flash(f"Error importing CSV: {e}")
            return redirect(request.url)
    return render_template_string(BASE_HTML + """
{% block body %}
<section>
  <h2>Upload CSV</h2>
  <form method="post" enctype="multipart/form-data">
    <label>Campaign name <input name="campaign" placeholder="MyCampaign"></label>
    <label>CSV file <input type="file" name="csvfile" accept=".csv" required></label>
    <p>Required headers: platform,title,vehicleType,make,model,year,mileage,price,description,location
       (images or images_json optional)</p>
    <button type="submit">Import</button>
  </form>
</section>
{% endblock %}
""")

@app.route("/campaign/<int:campaign_id>")
def campaign_detail(campaign_id: int):
    ensure_schema()
    conn = connect()
    camp = conn.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
    listings = conn.execute("SELECT * FROM listings WHERE campaign_id=? ORDER BY id ASC", (campaign_id,)).fetchall()
    conn.close()
    accounts = list_accounts()
    return render_template_string(BASE_HTML + """
{% block body %}
<section>
  <h2>Campaign {{ camp['campaign_name'] }} (ID {{ camp['id'] }})</h2>
  <p>Next run: {{ camp['next_run_at'] or '-' }}</p>

  <details open>
    <summary>Run Campaign</summary>
    <form method="post" action="{{ url_for('run_now') }}">
      <input type="hidden" name="campaign_id" value="{{ camp['id'] }}">
      <label>Account
        <select name="account" required>
          {% for a in accounts %}<option value="{{ a }}">{{ a }}</option>{% endfor %}
        </select>
      </label>
      <label>Limit <input type="number" name="limit" value="1" min="1"></label>
      <label><input type="checkbox" name="publish"> Publish</label>
      <button type="submit">Run</button>
    </form>
    <form method="post" action="{{ url_for('cache_images') }}" style="margin-top: .5rem">
      <input type="hidden" name="campaign_id" value="{{ camp['id'] }}">
      <button>Pre-cache images</button>
    </form>
  </details>

  <details>
    <summary>Schedule once</summary>
    <form method="post" action="{{ url_for('schedule_once') }}">
      <input type="hidden" name="campaign_id" value="{{ camp['id'] }}">
      <label>Run at (UTC ISO) <input name="when" placeholder="2025-09-20T14:30:00Z" required></label>
      <label>Account
        <select name="account" required>
          {% for a in accounts %}<option value="{{ a }}">{{ a }}</option>{% endfor %}
        </select>
      </label>
      <label>Limit <input type="number" name="limit" value="1" min="1"></label>
      <label><input type="checkbox" name="publish"> Publish</label>
      <button type="submit">Save & Schedule</button>
    </form>
  </details>

  <h3>Listings</h3>
  <table>
    <thead><tr>
      <th>ID</th><th>Title</th><th>Yr/Make/Model</th><th>Price</th><th>Status</th><th>URL</th><th>Actions</th>
    </tr></thead>
    <tbody>
    {% for l in listings %}
      <tr>
        <td>{{ l['id'] }}</td>
        <td>{{ l['title'] }}</td>
        <td>{{ l['year'] }} {{ l['make'] }} {{ l['model'] }}</td>
        <td>{{ l['price'] }}</td>
        <td>{{ l['status'] or 'pending' }}</td>
        <td>{% if l['fb_listing_url'] %}<a href="{{ l['fb_listing_url'] }}" target="_blank">open</a>{% else %}-{% endif %}</td>
        <td>
          {% if l['fb_listing_url'] %}
            <form method="post" action="{{ url_for('mark_sold') }}" style="display:inline">
              <input type="hidden" name="listing_id" value="{{ l['id'] }}">
              <input type="hidden" name="campaign_id" value="{{ camp['id'] }}">
              <button>Mark sold</button>
            </form>
            <form method="post" action="{{ url_for('delete_live') }}" style="display:inline">
              <input type="hidden" name="listing_id" value="{{ l['id'] }}">
              <input type="hidden" name="campaign_id" value="{{ camp['id'] }}">
              <button>Delete live</button>
            </form>
          {% endif %}
          <form method="post" action="{{ url_for('delete_from_campaign') }}" style="display:inline" onsubmit="return confirm('Remove from campaign?');">
            <input type="hidden" name="listing_id" value="{{ l['id'] }}">
            <input type="hidden" name="campaign_id" value="{{ camp['id'] }}">
            <button>Remove</button>
          </form>
          {% if l['last_error_screenshot'] %}
            <a href="file:///{{ l['last_error_screenshot'] }}" target="_blank">screenshot</a>
          {% endif %}
        </td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
</section>
{% endblock %}
""", camp=camp, listings=listings, accounts=accounts)

@app.post("/run-now")
def run_now():
    campaign_id = int(request.form["campaign_id"])
    account = request.form["account"]
    limit = int(request.form.get("limit", 1))
    publish = bool(request.form.get("publish"))

    threading.Thread(
        target=run_campaign_background,
        args=(account, campaign_id, limit, publish),
        daemon=True,
    ).start()
    flash(f"Started background run for campaign {campaign_id} (account {account}, limit {limit}, {'publish' if publish else 'dry-run'})")
    return redirect(url_for("campaign_detail", campaign_id=campaign_id))

@app.post("/schedule-once")
def schedule_once():
    campaign_id = int(request.form["campaign_id"])
    when = request.form["when"].strip()
    account = request.form["account"]
    limit = int(request.form.get("limit", 1))
    publish = bool(request.form.get("publish"))
    # validates ISO a bit
    try:
        datetime.fromisoformat(when.replace("Z", "+00:00"))
    except:
        flash("Invalid ISO timestamp. Example: 2025-09-20T14:30:00Z")
        return redirect(url_for("campaign_detail", campaign_id=campaign_id))
    schedule_campaign_once(campaign_id, when, account, publish, limit)
    flash(f"Scheduled campaign {campaign_id} at {when} (UTC)")
    return redirect(url_for("campaign_detail", campaign_id=campaign_id))

@app.post("/cache-images")
def cache_images():
    campaign_id = int(request.form["campaign_id"])
    n = cache_images_for_campaign(campaign_id)
    flash(f"Cached image references for {n} listing(s).")
    return redirect(url_for("campaign_detail", campaign_id=campaign_id))

@app.post("/delete-from-campaign")
def delete_from_campaign():
    campaign_id = int(request.form["campaign_id"])
    listing_id = int(request.form["listing_id"])
    conn = connect(); conn.execute("DELETE FROM listings WHERE id=?", (listing_id,)); conn.commit(); conn.close()
    flash(f"Removed listing {listing_id} from campaign.")
    return redirect(url_for("campaign_detail", campaign_id=campaign_id))

@app.post("/mark-sold")
def mark_sold():
    campaign_id = int(request.form["campaign_id"])
    listing_id = int(request.form["listing_id"])

    # get url
    conn = connect()
    row = conn.execute("SELECT fb_listing_url FROM listings WHERE id=?", (listing_id,)).fetchone()
    conn.close()
    if not row or not row["fb_listing_url"]:
        flash("No fb_listing_url on this listing.")
        return redirect(url_for("campaign_detail", campaign_id=campaign_id))

    # choose first account for sold action (or make a select in UI if you want)
    accounts = list_accounts()
    if not accounts:
        flash("No accounts found.")
        return redirect(url_for("campaign_detail", campaign_id=campaign_id))
    account = accounts[0]

    # run in background
    def _bg():
        import asyncio
        async def _go():
            bot = SimpleFacebookPoster(account)
            try:
                if not await bot.start_browser(): return
                if not await bot.goto_facebook(): return
                await bot.page.goto(row["fb_listing_url"])
                for sel in [
                    bot.page.get_by_role("button", name="Mark as sold"),
                    bot.page.get_by_text("Mark as sold", exact=False).first,
                    "button:has-text('Mark as sold')",
                ]:
                    try:
                        loc = sel if isinstance(sel, str) else sel
                        await (bot.page.locator(loc) if isinstance(loc,str) else loc).click(timeout=3000)
                        await asyncio.sleep(1.0)
                        return
                    except: pass
            finally:
                try: await bot.close_browser()
                except: pass
        asyncio.run(_go())
    threading.Thread(target=_bg, daemon=True).start()
    flash(f"Mark-sold triggered for listing {listing_id}.")
    return redirect(url_for("campaign_detail", campaign_id=campaign_id))

@app.post("/delete-live")
def delete_live():
    campaign_id = int(request.form["campaign_id"])
    listing_id = int(request.form["listing_id"])

    conn = connect()
    row = conn.execute("SELECT fb_listing_url FROM listings WHERE id=?", (listing_id,)).fetchone()
    conn.close()
    if not row or not row["fb_listing_url"]:
        flash("No fb_listing_url on this listing.")
        return redirect(url_for("campaign_detail", campaign_id=campaign_id))

    account = (list_accounts() or [None])[0]
    if not account:
        flash("No accounts found.")
        return redirect(url_for("campaign_detail", campaign_id=campaign_id))

    def _bg():
        import asyncio
        async def _go():
            bot = SimpleFacebookPoster(account)
            try:
                if not await bot.start_browser(): return
                if not await bot.goto_facebook(): return
                await bot.page.goto(row["fb_listing_url"])
                for sel in [
                    bot.page.get_by_role("button", name="Delete listing"),
                    bot.page.get_by_text("Delete listing", exact=False).first,
                    "button:has-text('Delete listing')",
                ]:
                    try:
                        loc = sel if isinstance(sel, str) else sel
                        await (bot.page.locator(loc) if isinstance(loc,str) else loc).click(timeout=3000)
                        await asyncio.sleep(0.8)
                        try:
                            await bot.page.get_by_role("button", name="Delete").click(timeout=3000)
                        except:
                            await bot.page.get_by_text("Delete", exact=False).first.click(timeout=3000)
                        await asyncio.sleep(1.0)
                        return
                    except: pass
            finally:
                try: await bot.close_browser()
                except: pass
        asyncio.run(_go())
    threading.Thread(target=_bg, daemon=True).start()
    flash(f"Delete-live triggered for listing {listing_id}.")
    return redirect(url_for("campaign_detail", campaign_id=campaign_id))


if __name__ == "__main__":
    ensure_schema()
    # Suggest running with:  python app.py
    # then open http://127.0.0.1:5000
    app.run(host="127.0.0.1", port=5000, debug=True)
