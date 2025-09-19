from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime
from pathlib import Path
import asyncio, subprocess, json, os

BASE = Path(__file__).resolve().parents[2]  # C:\CRAZY_POSTER
UPLOADS = BASE / "shared-resources" / "uploads"
LOGS = BASE / "account-instances" / "Account_001" / "logs"  # adjust if you have multiple accounts
UPLOADS.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Crazy Poster API", version="0.1.0")
scheduler = AsyncIOScheduler()

# allow local Vite dev & your future domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def _start():
    if not scheduler.running:
        scheduler.start()

@app.on_event("shutdown")
async def _stop():
    if scheduler.running:
        scheduler.shutdown()

@app.get("/health")
async def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}

@app.post("/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    dest = UPLOADS / f"{ts}-{file.filename}"
    content = await file.read()
    dest.write_bytes(content)
    return {"path": str(dest), "size": len(content)}

async def run_campaign(csv_path: str, account_name: str):
    """
    Calls your existing poster CLI once (single-shot run).
    If you already have flags, wire them here.
    """
    log_file = LOGS / f"run-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.log"
    cmd = [
        "python",
        str(BASE / "automation_engine" / "cli" / "post_campaign.py"),
        "--account", account_name,
        "--csv", csv_path,
        "--headless", "0",
        "--exit-after", "1",  # post once then exit (adjust to your CLI)
    ]
    with open(log_file, "w", encoding="utf-8", errors="ignore") as lf:
        lf.write(f"CMD: {' '.join(cmd)}\n")
        lf.flush()
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=lf, stderr=lf, cwd=str(BASE)
        )
        await proc.communicate()
        lf.write(f"\nEXIT: {proc.returncode}\n")
    return {"exit_code": proc.returncode, "log": str(log_file)}

@app.post("/run-now")
async def run_now(payload: dict, bg: BackgroundTasks):
    """
    payload example:
    {
      "account": "Account_001",
      "csv_path": "C:/CRAZY_POSTER/shared-resources/uploads/20250919-cars.csv"
    }
    """
    account = payload.get("account", "Account_001")
    csv_path = payload["csv_path"]
    bg.add_task(run_campaign, csv_path, account)
    return {"queued": True}

@app.post("/schedule-once")
async def schedule_once(payload: dict):
    """
    payload example:
    {
      "account": "Account_001",
      "csv_path": "C:/CRAZY_POSTER/shared-resources/uploads/20250919-cars.csv",
      "when": "2025-09-20T20:15:00"   # ISO local time
    }
    """
    account = payload.get("account", "Account_001")
    csv_path = payload["csv_path"]
    when = datetime.fromisoformat(payload["when"])
    job = scheduler.add_job(
        run_campaign,
        trigger=DateTrigger(run_date=when),
        args=[csv_path, account],
        id=f"once-{when.timestamp()}",
        replace_existing=True,
    )
    return {"scheduled": True, "job_id": job.id, "run_at": when.isoformat()}
