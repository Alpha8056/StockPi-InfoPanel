import os
import sqlite3
from typing import Any, Dict, List

DB_PATH = os.path.join(os.path.dirname(__file__), "network.db")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_services_for_ip(ip: str) -> List[Dict[str, Any]]:
    conn = _conn()
    rows = conn.execute("""
        SELECT svc_key, service_name, service_type, port, path, is_up, last_checked_ts
        FROM service_status
        WHERE ip = ?
        ORDER BY service_name ASC
    """, (ip,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
