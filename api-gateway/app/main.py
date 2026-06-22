"""
SkyOps — API Gateway
Stores monitored services and receives health-check reports from the monitor-worker.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, HttpUrl

DB_PATH = os.environ.get("DB_PATH", "skyops.db")

app = FastAPI(title="SkyOps API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)


# ── DB ────────────────────────────────────────────────────────────────────────

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


init_db()


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
    status: str        # "up" | "down" | "timeout"
    latency_ms: Optional[float] = None


class CheckOut(BaseModel):
    id: int
    service_id: int
    status: str
    latency_ms: Optional[float]
    checked_at: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/services", response_model=ServiceOut, status_code=201)
def add_service(svc: ServiceCreate):
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO services (name, url, created_at) VALUES (?, ?, ?)",
                (svc.name, svc.url, now),
            )
            new_id = cur.lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(400, f"Service '{svc.name}' already exists.")
    return ServiceOut(id=new_id, name=svc.name, url=svc.url, created_at=now)


@app.get("/api/services", response_model=List[ServiceOut])
def list_services():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM services ORDER BY id").fetchall()
        result = []
        for r in rows:
            last = conn.execute(
                "SELECT status, latency_ms FROM checks WHERE service_id=? ORDER BY id DESC LIMIT 1",
                (r["id"],),
            ).fetchone()
            result.append(ServiceOut(
                id=r["id"], name=r["name"], url=r["url"], created_at=r["created_at"],
                last_status=last["status"] if last else None,
                last_latency_ms=last["latency_ms"] if last else None,
            ))
    return result


@app.get("/api/services/{service_id}", response_model=ServiceOut)
def get_service(service_id: int):
    with get_db() as conn:
        r = conn.execute("SELECT * FROM services WHERE id=?", (service_id,)).fetchone()
        if not r:
            raise HTTPException(404, f"Service {service_id} not found.")
        last = conn.execute(
            "SELECT status, latency_ms FROM checks WHERE service_id=? ORDER BY id DESC LIMIT 1",
            (service_id,),
        ).fetchone()
    return ServiceOut(
        id=r["id"], name=r["name"], url=r["url"], created_at=r["created_at"],
        last_status=last["status"] if last else None,
        last_latency_ms=last["latency_ms"] if last else None,
    )


@app.delete("/api/services/{service_id}", status_code=204)
def delete_service(service_id: int):
    with get_db() as conn:
        result = conn.execute("DELETE FROM services WHERE id=?", (service_id,))
        if result.rowcount == 0:
            raise HTTPException(404, f"Service {service_id} not found.")
        conn.execute("DELETE FROM checks WHERE service_id=?", (service_id,))


@app.post("/api/checks", response_model=CheckOut, status_code=201)
def record_check(check: CheckIn):
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        svc = conn.execute("SELECT id FROM services WHERE id=?", (check.service_id,)).fetchone()
        if not svc:
            raise HTTPException(404, f"Service {check.service_id} not found.")
        cur = conn.execute(
            "INSERT INTO checks (service_id, status, latency_ms, checked_at) VALUES (?, ?, ?, ?)",
            (check.service_id, check.status, check.latency_ms, now),
        )
        new_id = cur.lastrowid
    return CheckOut(id=new_id, service_id=check.service_id, status=check.status,
                    latency_ms=check.latency_ms, checked_at=now)


@app.get("/api/checks/{service_id}", response_model=List[CheckOut])
def get_checks(service_id: int, limit: int = 50):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM checks WHERE service_id=? ORDER BY id DESC LIMIT ?",
            (service_id, limit),
        ).fetchall()
    return [CheckOut(**dict(r)) for r in rows]
