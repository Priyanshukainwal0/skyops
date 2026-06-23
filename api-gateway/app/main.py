"""
SkyOps — API Gateway
Stores monitored services and receives health-check reports from the monitor-worker.
Supports SQLite (local dev) and PostgreSQL (production via DATABASE_URL).
"""
from __future__ import annotations

import os
import pathlib
import threading
import time
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel

DATABASE_URL = os.environ.get("DATABASE_URL", "")
DB_PATH = os.environ.get("DB_PATH", "skyops.db")
STATIC_DIR = pathlib.Path(__file__).parent / "static"
USE_POSTGRES = bool(DATABASE_URL)

app = FastAPI(title="SkyOps API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ── DB ────────────────────────────────────────────────────────────────────────

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras

    @contextmanager
    def get_db():
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _row(cursor, row):
        if row is None:
            return None
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row))

    def _rows(cursor, rows):
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, r)) for r in rows]

    def init_db():
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS services (
                    id         SERIAL PRIMARY KEY,
                    name       TEXT NOT NULL UNIQUE,
                    url        TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS checks (
                    id           SERIAL PRIMARY KEY,
                    service_id   INTEGER NOT NULL REFERENCES services(id),
                    status       TEXT NOT NULL,
                    latency_ms   REAL,
                    checked_at   TEXT NOT NULL
                )
            """)

    def db_fetchone(conn, sql, params=()):
        cur = conn.cursor()
        cur.execute(sql.replace("?", "%s"), params)
        row = cur.fetchone()
        return _row(cur, row) if row else None

    def db_fetchall(conn, sql, params=()):
        cur = conn.cursor()
        cur.execute(sql.replace("?", "%s"), params)
        return _rows(cur, cur.fetchall())

    def db_execute(conn, sql, params=()):
        cur = conn.cursor()
        cur.execute(sql.replace("?", "%s").replace(
            "INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"
        ), params)
        return cur

else:
    import sqlite3

    @contextmanager
    def get_db():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db():
        with get_db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS services (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    name       TEXT NOT NULL UNIQUE,
                    url        TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checks (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id   INTEGER NOT NULL REFERENCES services(id),
                    status       TEXT NOT NULL,
                    latency_ms   REAL,
                    checked_at   TEXT NOT NULL
                )
            """)

    def db_fetchone(conn, sql, params=()):
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def db_fetchall(conn, sql, params=()):
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def db_execute(conn, sql, params=()):
        return conn.execute(sql, params)


init_db()


def seed_default_services():
    default = os.environ.get("DEFAULT_SERVICES", "")
    if not default:
        return
    now = datetime.now(timezone.utc).isoformat()
    for entry in default.split(","):
        entry = entry.strip()
        if "|" not in entry:
            continue
        name, url = entry.split("|", 1)
        with get_db() as conn:
            existing = db_fetchone(conn, "SELECT id FROM services WHERE name=?", (name.strip(),))
            if not existing:
                db_execute(conn, "INSERT INTO services (name, url, created_at) VALUES (?, ?, ?)",
                           (name.strip(), url.strip(), now))


seed_default_services()


# ── Background checker ────────────────────────────────────────────────────────

def _background_checker():
    interval = int(os.environ.get("CHECK_INTERVAL", "60"))
    timeout = int(os.environ.get("REQUEST_TIMEOUT", "10"))
    time.sleep(10)
    while True:
        try:
            with get_db() as conn:
                services = db_fetchall(conn, "SELECT id, url FROM services")
            for svc in services:
                start = time.monotonic()
                try:
                    req = urllib.request.Request(svc["url"], method="GET")
                    req.add_header("User-Agent", "SkyOps-Monitor/1.0")
                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        status = "up" if resp.status < 500 else "down"
                except Exception:
                    status = "down"
                latency_ms = round((time.monotonic() - start) * 1000, 2)
                now = datetime.now(timezone.utc).isoformat()
                with get_db() as conn:
                    db_execute(conn,
                        "INSERT INTO checks (service_id, status, latency_ms, checked_at) VALUES (?, ?, ?, ?)",
                        (svc["id"], status, latency_ms, now))
        except Exception:
            pass
        time.sleep(interval)


threading.Thread(target=_background_checker, daemon=True).start()


# ── Schemas ───────────────────────────────────────────────────────────────────

class ServiceCreate(BaseModel):
    name: str
    url: str


class ServiceOut(BaseModel):
    id: int
    name: str
    url: str
    created_at: str
    last_status: Optional[str] = None
    last_latency_ms: Optional[float] = None


class CheckIn(BaseModel):
    service_id: int
    status: str
    latency_ms: Optional[float] = None


class CheckOut(BaseModel):
    id: int
    service_id: int
    status: str
    latency_ms: Optional[float]
    checked_at: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def dashboard():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"status": "ok", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/services", response_model=ServiceOut, status_code=201)
def add_service(svc: ServiceCreate):
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        existing = db_fetchone(conn, "SELECT id FROM services WHERE name=?", (svc.name,))
        if existing:
            raise HTTPException(400, f"Service '{svc.name}' already exists.")
        if USE_POSTGRES:
            cur = conn.cursor()
            cur.execute("INSERT INTO services (name, url, created_at) VALUES (%s, %s, %s) RETURNING id",
                        (svc.name, svc.url, now))
            new_id = cur.fetchone()[0]
        else:
            cur = db_execute(conn, "INSERT INTO services (name, url, created_at) VALUES (?, ?, ?)",
                             (svc.name, svc.url, now))
            new_id = cur.lastrowid
    return ServiceOut(id=new_id, name=svc.name, url=svc.url, created_at=now)


@app.get("/api/services", response_model=List[ServiceOut])
def list_services():
    with get_db() as conn:
        rows = db_fetchall(conn, "SELECT * FROM services ORDER BY id")
        result = []
        for r in rows:
            last = db_fetchone(conn,
                "SELECT status, latency_ms FROM checks WHERE service_id=? ORDER BY id DESC LIMIT 1",
                (r["id"],))
            result.append(ServiceOut(
                id=r["id"], name=r["name"], url=r["url"], created_at=r["created_at"],
                last_status=last["status"] if last else None,
                last_latency_ms=last["latency_ms"] if last else None,
            ))
    return result


@app.get("/api/services/{service_id}", response_model=ServiceOut)
def get_service(service_id: int):
    with get_db() as conn:
        r = db_fetchone(conn, "SELECT * FROM services WHERE id=?", (service_id,))
        if not r:
            raise HTTPException(404, f"Service {service_id} not found.")
        last = db_fetchone(conn,
            "SELECT status, latency_ms FROM checks WHERE service_id=? ORDER BY id DESC LIMIT 1",
            (service_id,))
    return ServiceOut(
        id=r["id"], name=r["name"], url=r["url"], created_at=r["created_at"],
        last_status=last["status"] if last else None,
        last_latency_ms=last["latency_ms"] if last else None,
    )


@app.delete("/api/services/{service_id}", status_code=204)
def delete_service(service_id: int):
    with get_db() as conn:
        r = db_fetchone(conn, "SELECT id FROM services WHERE id=?", (service_id,))
        if not r:
            raise HTTPException(404, f"Service {service_id} not found.")
        db_execute(conn, "DELETE FROM checks WHERE service_id=?", (service_id,))
        db_execute(conn, "DELETE FROM services WHERE id=?", (service_id,))


@app.post("/api/checks", response_model=CheckOut, status_code=201)
def record_check(check: CheckIn):
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        svc = db_fetchone(conn, "SELECT id FROM services WHERE id=?", (check.service_id,))
        if not svc:
            raise HTTPException(404, f"Service {check.service_id} not found.")
        if USE_POSTGRES:
            cur = conn.cursor()
            cur.execute("INSERT INTO checks (service_id, status, latency_ms, checked_at) VALUES (%s, %s, %s, %s) RETURNING id",
                        (check.service_id, check.status, check.latency_ms, now))
            new_id = cur.fetchone()[0]
        else:
            cur = db_execute(conn,
                "INSERT INTO checks (service_id, status, latency_ms, checked_at) VALUES (?, ?, ?, ?)",
                (check.service_id, check.status, check.latency_ms, now))
            new_id = cur.lastrowid
    return CheckOut(id=new_id, service_id=check.service_id, status=check.status,
                    latency_ms=check.latency_ms, checked_at=now)


@app.get("/api/checks/{service_id}", response_model=List[CheckOut])
def get_checks(service_id: int, limit: int = 50):
    with get_db() as conn:
        rows = db_fetchall(conn,
            "SELECT * FROM checks WHERE service_id=? ORDER BY id DESC LIMIT ?",
            (service_id, limit))
    return [CheckOut(**r) for r in rows]


@app.post("/api/run-checks", tags=["ops"])
def run_checks():
    with get_db() as conn:
        services = db_fetchall(conn, "SELECT id, url FROM services")
    results = []
    timeout = int(os.environ.get("REQUEST_TIMEOUT", "10"))
    for svc in services:
        start = time.monotonic()
        try:
            req = urllib.request.Request(svc["url"], method="GET")
            req.add_header("User-Agent", "SkyOps-Monitor/1.0")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = "up" if resp.status < 500 else "down"
        except Exception:
            status = "down"
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        now = datetime.now(timezone.utc).isoformat()
        with get_db() as conn:
            db_execute(conn,
                "INSERT INTO checks (service_id, status, latency_ms, checked_at) VALUES (?, ?, ?, ?)",
                (svc["id"], status, latency_ms, now))
        results.append({"service_id": svc["id"], "status": status, "latency_ms": latency_ms})
    return {"checked": len(results), "results": results}
