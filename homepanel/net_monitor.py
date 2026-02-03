from __future__ import annotations

import alerts_db
import time
import json
import os
import socket
import time
from typing import Any, Dict, List, Optional

from ping3 import ping  # type: ignore
import requests

import network_db

DEVICES_PATH = os.path.join(os.path.dirname(__file__), "devices.json")
INTERVAL_SECONDS = 60


def load_devices() -> List[Dict[str, Any]]:
    with open(DEVICES_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg.get("devices", [])


def ping_host(ip: str, timeout: float = 1.0) -> Optional[float]:
    r = ping(ip, timeout=timeout, unit="s")
    if r is None or r is False:
        return None
    return float(r) * 1000.0


def tcp_check(ip: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((ip, int(port)), timeout=timeout):
            return True
    except Exception:
        return False


def http_check(ip: str, port: int, path: str = "/", timeout: float = 2.5) -> bool:
    if not path.startswith("/"):
        path = "/" + path
    url = f"http://{ip}:{int(port)}{path}"
    try:
        r = requests.get(url, timeout=timeout)
        return 200 <= r.status_code < 400
    except Exception:
        return False


def svc_key_for(ip: str, svc: Dict[str, Any]) -> str:
    stype = str(svc.get("type", "tcp")).lower()
    sname = str(svc.get("name", "service"))
    port = svc.get("port", "")
    path = str(svc.get("path", "") or "")
    return f"{ip}|{stype}|{port}|{path}|{sname}"



def _service_alert_key(ip: str, svc: dict) -> str:
    typ = str(svc.get("type","tcp")).lower()
    port = int(svc.get("port", 0) or 0)
    path = str(svc.get("path","/")) if typ == "http" else ""
    return f"service:{ip}:{typ}:{port}:{path}"

def run_service_checks(ts: int, device: Dict[str, Any], device_is_up: bool) -> None:
    ip = str(device.get("ip", "")).strip()
    dname = str(device.get("name", "Unknown"))
    services = device.get("services", []) or []

    for svc in services:
        sname = str(svc.get("name", "Service"))
        stype = str(svc.get("type", "tcp")).lower()
        port = svc.get("port", None)
        path = str(svc.get("path", "/") or "/")
        key = svc_key_for(ip, svc)

        is_up = False
        if device_is_up and port is not None:
            if stype == "http":
                is_up = http_check(ip, int(port), path=path)
            else:
                is_up = tcp_check(ip, int(port))

        network_db.record_service_sample(
            ts=ts,
            svc_key=key,
            ip=ip,
            device_name=dname,
            service_name=sname,
            service_type=stype,
            port=int(port) if port is not None else None,
            path=path if stype == "http" else None,
            is_up=is_up,
        )


def run_once(devices: List[Dict[str, Any]]) -> None:
    ts = int(time.time())
    up_count = 0
    down_count = 0

    # --- Prune stale services (removed from devices.json) ---
    valid_keys: list[str] = []

    for d in devices:
        ip = d["ip"]
        name = d.get("name", ip)
        dev_type = d.get("type")

        ms = ping_host(ip)
        is_up = ms is not None

        if is_up:
            up_count += 1
        else:
            down_count += 1

        network_db.record_device_sample(
            ts=ts,
            ip=ip,
            name=name,
            dev_type=str(dev_type) if dev_type is not None else None,
            is_up=is_up,
            latency_ms=ms,
        )

        alert_key = f"device:{ip}"

        if not is_up:
            alerts_db.raise_alert(
                ts=ts,
                source="network",
                level="crit",
                title=f"Device DOWN: {name}",
                message=f"{name} ({ip}) is not responding to ping.",
                key=alert_key,
            )
        else:
            alerts_db.clear_alert(key=alert_key, cleared_ts=ts)

        run_service_checks(ts, d, is_up)

    now = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] Wrote samples. Devices UP={up_count} DOWN={down_count}")


def main() -> None:
    network_db.init_db()
    print(f"Network monitor started. Interval={INTERVAL_SECONDS}s. (devices reload each cycle)")
    while True:
        devices = load_devices()
        run_once(devices)
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
