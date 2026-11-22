import asyncio
import ipaddress
import os
import socket
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl

load_dotenv()
HOST = os.getenv("SHIELD_HOST", "127.0.0.1")
PORT = int(os.getenv("SHIELD_PORT", "8787"))
DB = os.getenv("SHIELD_DB", "shield.db")
TOKEN = os.getenv("SHIELD_ADMIN_TOKEN", "")
INTERVAL = max(30, int(os.getenv("SHIELD_MONITOR_INTERVAL", "60")))
TIMEOUT = 12.0

def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            last_status TEXT DEFAULT 'PENDING',
            last_code INTEGER,
            last_latency REAL,
            last_checked TEXT,
            last_error TEXT
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER,
            url TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        db.execute("INSERT OR IGNORE INTO sites(url,created_at) VALUES(?,?)",
                   ("https://example.com", now()))

def now():
    return datetime.now(timezone.utc).isoformat()

def require_auth(authorization: str = Header(default="")):
    if not TOKEN or authorization != f"Bearer {TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized. Configure SHIELD_ADMIN_TOKEN.")

def validate_public_url(value: str):
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTPS website URLs are accepted.")
    host = parsed.hostname
    if host.lower() in {"localhost"} or host.endswith(".local"):
        raise ValueError("Local hostnames are not allowed.")
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError("The website hostname could not be resolved.")
    if not addresses:
        raise ValueError("The website hostname has no address.")
    for item in addresses:
        ip = ipaddress.ip_address(item[4][0])
        if not ip.is_global:
            raise ValueError("Private, local, and non-public IP addresses are blocked.")
    return value

async def check_site(site):
    url = site["url"]
    started = time.perf_counter()
    status, code, latency, error = "UP", None, None, None
    try:
        validate_public_url(url)
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False,
                                     headers={"User-Agent":"DDoS-Shield-Monitor/0.2"}) as client:
            response = await client.get(url)
        code = response.status_code
        latency = round((time.perf_counter() - started) * 1000, 2)
        if code >= 500:
            status, error = "DOWN", f"HTTP {code}"
        elif 300 <= code < 400:
            status, error = "WARNING", f"Redirect response HTTP {code}; redirect not followed"
    except Exception as exc:
        status, error = "DOWN", str(exc)[:300]
        latency = round((time.perf_counter() - started) * 1000, 2)
    checked = now()
    with connect() as db:
        previous = db.execute("SELECT last_status FROM sites WHERE id=?", (site["id"],)).fetchone()
        db.execute("""UPDATE sites SET last_status=?,last_code=?,last_latency=?,
                   last_checked=?,last_error=? WHERE id=?""",
                   (status, code, latency, checked, error, site["id"]))
        if previous and previous["last_status"] != status:
            db.execute("INSERT INTO events(site_id,url,status,message,created_at) VALUES(?,?,?,?,?)",
                       (site["id"], url, status, error or f"Status changed to {status}", checked))
    return status

async def monitor_loop():
    while True:
        with connect() as db:
            sites = db.execute("SELECT * FROM sites ORDER BY id").fetchall()
        for site in sites:
            await check_site(site)
        await asyncio.sleep(INTERVAL)

@asynccontextmanager
async def lifespan(app):
    init_db()
    task = asyncio.create_task(monitor_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="DDoS Shield", version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

class SiteInput(BaseModel):
    url: HttpUrl

@app.get("/")
def dashboard():
    return FileResponse("static/index.html")

@app.get("/api/health")
def health():
    return {"ok": True, "service": "DDoS Shield", "version": "0.2.0"}

@app.get("/api/summary", dependencies=[Depends(require_auth)])
def summary():
    with connect() as db:
        sites = [dict(x) for x in db.execute("SELECT * FROM sites ORDER BY id").fetchall()]
        events = [dict(x) for x in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 30").fetchall()]
    return {"sites": sites, "events": events, "monitor_interval_seconds": INTERVAL}

@app.post("/api/sites", dependencies=[Depends(require_auth)])
async def add_site(data: SiteInput):
    url = str(data.url).rstrip("/")
    try:
        validate_public_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    with connect() as db:
        try:
            cur = db.execute("INSERT INTO sites(url,created_at) VALUES(?,?)", (url, now()))
            site_id = cur.lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="This website is already being monitored.")
        site = db.execute("SELECT * FROM sites WHERE id=?", (site_id,)).fetchone()
    await check_site(site)
    return {"added": True, "message": "Website added; automatic monitoring has started.", "site_id": site_id}

@app.post("/api/sites/{site_id}/check", dependencies=[Depends(require_auth)])
async def manual_check(site_id: int):
    with connect() as db:
        site = db.execute("SELECT * FROM sites WHERE id=?", (site_id,)).fetchone()
    if not site:
        raise HTTPException(status_code=404, detail="Website not found.")
    await check_site(site)
    return {"checked": True}

@app.delete("/api/sites/{site_id}", dependencies=[Depends(require_auth)])
def delete_site(site_id: int):
    with connect() as db:
        cur = db.execute("DELETE FROM sites WHERE id=?", (site_id,))
        db.execute("DELETE FROM events WHERE site_id=?", (site_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Website not found.")
    return {"deleted": True}
