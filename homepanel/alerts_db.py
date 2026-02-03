from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "alerts.db")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,              -- unix epoch seconds
            source TEXT NOT NULL,             -- "network" | "service" | "weather" | "rf" | etc.
            level TEXT NOT NULL,              -- "info" | "warn" | "crit"
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            key TEXT NOT NULL,                -- de-dupe key (ex: "device:10.0.0.42" or "wx:alert:<id>")
            is_active INTEGER NOT NULL DEFAULT 1, -- 1=active, 0=cleared
            cleared_ts INTEGER                -- when cleared (unix epoch)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_active ON alerts(is_active)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_key_active ON alerts(key, is_active)")
    conn.commit()
    conn.close()


def raise_alert(
    *,
    ts: int,
    source: str,
    level: str,
    title: str,
    message: str,
    key: str,
) -> bool:
    """
    Creates an active alert if one with the same (key, is_active=1) doesn't already exist.
    Returns True if created, False if it already existed.
    """
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO alerts (ts, source, level, title, message, key, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (ts, source, level, title, message, key),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def clear_alert(*, key: str, cleared_ts: int) -> int:
    """
    Clears all active alerts matching key.
    Returns number of rows cleared.
    """
    conn = connect()
    cur = conn.execute(
        "UPDATE alerts SET is_active=0, cleared_ts=? WHERE key=? AND is_active=1",
        (cleared_ts, key),
    )
    conn.commit()
    n = cur.rowcount
    conn.close()
    return n


def list_alerts(active_only: bool = False, limit: int = 100) -> List[Dict[str, Any]]:
    conn = connect()
    if active_only:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE is_active=1 ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM alerts ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
