import os
import sqlite3
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "network.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()

    # Device tables
    cur.execute("""
    CREATE TABLE IF NOT EXISTS device_status (
      ip TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      type TEXT,
      is_up INTEGER NOT NULL,
      latency_ms REAL,
      last_seen_ts INTEGER NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS device_history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts INTEGER NOT NULL,
      ip TEXT NOT NULL,
      name TEXT NOT NULL,
      type TEXT,
      is_up INTEGER NOT NULL,
      latency_ms REAL
    );
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_history_ts ON device_history(ts);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_history_ip_ts ON device_history(ip, ts);")

    # Service tables
    cur.execute("""
    CREATE TABLE IF NOT EXISTS service_status (
      svc_key TEXT PRIMARY KEY,
      ip TEXT NOT NULL,
      device_name TEXT NOT NULL,
      service_name TEXT NOT NULL,
      service_type TEXT NOT NULL,
      port INTEGER,
      path TEXT,
      is_up INTEGER NOT NULL,
      last_checked_ts INTEGER NOT NULL,
      last_ok_ts INTEGER
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS service_history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts INTEGER NOT NULL,
      svc_key TEXT NOT NULL,
      ip TEXT NOT NULL,
      device_name TEXT NOT NULL,
      service_name TEXT NOT NULL,
      service_type TEXT NOT NULL,
      port INTEGER,
      path TEXT,
      is_up INTEGER NOT NULL
    );
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_svc_hist_ts ON service_history(ts);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_svc_hist_key_ts ON service_history(svc_key, ts);")

    conn.commit()
    conn.close()


def record_device_sample(ts: int, ip: str, name: str, dev_type: Optional[str], is_up: bool, latency_ms: Optional[float]) -> None:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO device_history (ts, ip, name, type, is_up, latency_ms) VALUES (?, ?, ?, ?, ?, ?)",
        (ts, ip, name, dev_type, 1 if is_up else 0, latency_ms),
    )

    cur.execute("""
        INSERT INTO device_status (ip, name, type, is_up, latency_ms, last_seen_ts)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(ip) DO UPDATE SET
          name=excluded.name,
          type=excluded.type,
          is_up=excluded.is_up,
          latency_ms=excluded.latency_ms,
          last_seen_ts=excluded.last_seen_ts;
    """, (ip, name, dev_type, 1 if is_up else 0, latency_ms, ts))

    conn.commit()
    conn.close()


def record_service_sample(
    ts: int,
    svc_key: str,
    ip: str,
    device_name: str,
    service_name: str,
    service_type: str,
    port: Optional[int],
    path: Optional[str],
    is_up: bool,
) -> None:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO service_history (ts, svc_key, ip, device_name, service_name, service_type, port, path, is_up)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ts, svc_key, ip, device_name, service_name, service_type, port, path, 1 if is_up else 0),
    )

    # last_ok_ts only updates when the service is up
    last_ok_ts = ts if is_up else None

    cur.execute("""
        INSERT INTO service_status (svc_key, ip, device_name, service_name, service_type, port, path, is_up, last_checked_ts, last_ok_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(svc_key) DO UPDATE SET
          ip=excluded.ip,
          device_name=excluded.device_name,
          service_name=excluded.service_name,
          service_type=excluded.service_type,
          port=excluded.port,
          path=excluded.path,
          is_up=excluded.is_up,
          last_checked_ts=excluded.last_checked_ts,
          last_ok_ts=COALESCE(excluded.last_ok_ts, service_status.last_ok_ts);
    """, (svc_key, ip, device_name, service_name, service_type, port, path, 1 if is_up else 0, ts, last_ok_ts))

    conn.commit()
    conn.close()


def prune_services(valid_keys: list[str]) -> None:
    """
    Keep service_status clean by removing rows for services that no longer exist
    in devices.json (e.g. user deleted/renamed/re-added services).
    """
    conn = get_conn()

    if not valid_keys:
        conn.execute("DELETE FROM service_status")
        conn.commit()
        conn.close()
        return

    q = "DELETE FROM service_status WHERE svc_key NOT IN ({})".format(
        ",".join(["?"] * len(valid_keys))
    )
    conn.execute(q, valid_keys)
    conn.commit()
    conn.close()

