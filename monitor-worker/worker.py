"""
SkyOps — Monitor Worker
Polls all registered services every CHECK_INTERVAL seconds,
measures latency, and posts results back to the API Gateway.
"""
from __future__ import annotations

import os
import time
import logging

import httpx

API_URL = os.environ.get("API_URL", "http://api-gateway:8000")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "30"))
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "10"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [worker] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


def check_service(client: httpx.Client, svc: dict) -> None:
    service_id = svc["id"]
    url = svc["url"]
    try:
        resp = client.get(url, timeout=REQUEST_TIMEOUT)
        status = "up" if resp.status_code < 400 else "down"
        latency_ms = resp.elapsed.total_seconds() * 1000
    except httpx.TimeoutException:
        status, latency_ms = "timeout", None
    except Exception as exc:
        log.warning("Error checking %s: %s", url, exc)
        status, latency_ms = "down", None

    try:
        client.post(f"{API_URL}/api/checks", json={
            "service_id": service_id,
            "status": status,
            "latency_ms": latency_ms,
        })
        log.info("%-30s %-8s %s", svc["name"], status,
                 f"{latency_ms:.0f}ms" if latency_ms else "—")
    except Exception as exc:
        log.error("Failed to post check result: %s", exc)


def run():
    log.info("Monitor worker starting — API: %s, interval: %ss", API_URL, CHECK_INTERVAL)
    with httpx.Client() as client:
        while True:
            try:
                resp = client.get(f"{API_URL}/api/services", timeout=5)
                services = resp.json()
            except Exception as exc:
                log.warning("Could not fetch services: %s — retrying in %ss", exc, CHECK_INTERVAL)
                time.sleep(CHECK_INTERVAL)
                continue

            if not services:
                log.info("No services registered yet.")
            for svc in services:
                check_service(client, svc)

            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run()
