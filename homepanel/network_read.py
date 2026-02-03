import sqlite3
import os
from typing import Any, Dict, List

DB_PATH = os.path.join(os.path.dirname(__file__), "network.db")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_latest_status() -> List[Dict[str, Any]]:
    conn = _conn()
    rows = conn.execute("""
        SELECT ip, name, type, is_up, latency_ms, last_seen_ts
        FROM device_status
        ORDER BY is_up ASC, name ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]
