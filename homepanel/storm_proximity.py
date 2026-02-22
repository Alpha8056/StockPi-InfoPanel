from __future__ import annotations

import math
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

import alerts_db
import weather_client

# Load home location from config.json
import json as _json, os as _os
_cfg_path = _os.path.join(_os.path.dirname(__file__), "config.json")
try:
    with open(_cfg_path) as _f:
        _cfg = _json.load(_f)
    HOME_LAT = float(_cfg.get("location", {}).get("lat", 38.8782))
    HOME_LON = float(_cfg.get("location", {}).get("lon", -99.3348))
except Exception:
    HOME_LAT = 38.8782
    HOME_LON = -99.3348

# How close before we create a "proximity" alert
DEFAULT_THRESHOLD_MILES = 50.0


def _miles_per_degree(lat: float) -> Tuple[float, float]:
    # Approx conversions at latitude
    miles_per_deg_lat = 69.0
    miles_per_deg_lon = 69.0 * math.cos(math.radians(lat))
    return miles_per_deg_lat, miles_per_deg_lon


def _point_segment_distance_miles(
    lat: float, lon: float, a_lat: float, a_lon: float, b_lat: float, b_lon: float
) -> float:
    """
    Approx distance from point to segment in miles using local equirectangular projection.
    Good enough for “storm within X miles” logic.
    """
    mpl, mplon = _miles_per_degree(lat)

    px, py = (lon * mplon), (lat * mpl)
    ax, ay = (a_lon * mplon), (a_lat * mpl)
    bx, by = (b_lon * mplon), (b_lat * mpl)

    vx, vy = (bx - ax), (by - ay)
    wx, wy = (px - ax), (py - ay)

    vv = vx * vx + vy * vy
    if vv <= 1e-12:
        # a==b
        dx, dy = (px - ax), (py - ay)
        return math.hypot(dx, dy)

    t = (wx * vx + wy * vy) / vv
    t = max(0.0, min(1.0, t))

    cx, cy = (ax + t * vx), (ay + t * vy)
    return math.hypot(px - cx, py - cy)


def _iter_rings_from_geometry(geom: Dict[str, Any]) -> Iterable[List[Tuple[float, float]]]:
    """
    Yield rings as lists of (lat, lon) from Polygon or MultiPolygon.
    GeoJSON coords are [lon, lat].
    """
    gtype = geom.get("type")
    coords = geom.get("coordinates")

    if not coords or not gtype:
        return

    if gtype == "Polygon":
        # coords: [ [ [lon,lat], ... ] , hole..., ]
        for ring in coords:
            ring_latlon = [(pt[1], pt[0]) for pt in ring if isinstance(pt, (list, tuple)) and len(pt) >= 2]
            if ring_latlon:
                yield ring_latlon

    elif gtype == "MultiPolygon":
        # coords: [ polygon1, polygon2, ... ] where polygon = rings
        for poly in coords:
            for ring in poly:
                ring_latlon = [(pt[1], pt[0]) for pt in ring if isinstance(pt, (list, tuple)) and len(pt) >= 2]
                if ring_latlon:
                    yield ring_latlon


def distance_to_geometry_miles(lat: float, lon: float, geom: Dict[str, Any]) -> Optional[float]:
    rings = list(_iter_rings_from_geometry(geom))
    if not rings:
        return None

    best = None
    for ring in rings:
        # distance to each segment in ring
        for i in range(len(ring) - 1):
            a_lat, a_lon = ring[i]
            b_lat, b_lon = ring[i + 1]
            d = _point_segment_distance_miles(lat, lon, a_lat, a_lon, b_lat, b_lon)
            if best is None or d < best:
                best = d

        # if ring isn't closed, also connect last->first
        if ring[0] != ring[-1] and len(ring) >= 2:
            a_lat, a_lon = ring[-1]
            b_lat, b_lon = ring[0]
            d = _point_segment_distance_miles(lat, lon, a_lat, a_lon, b_lat, b_lon)
            if best is None or d < best:
                best = d

    return best


def sync_storm_proximity(threshold_miles: float = DEFAULT_THRESHOLD_MILES) -> int:
    """
    Creates/updates proximity alerts for any active NWS alerts whose polygon comes within threshold_miles.
    Returns number of proximity alerts created this run.
    """
    alerts_db.init_db()

    data = weather_client.get_alerts()
    features = data.get("features", []) if isinstance(data, dict) else []
    now = int(time.time())

    created = 0
    active_keys = set()

    for f in features:
        if not isinstance(f, dict):
            continue
        fid = f.get("id") or ""
        props = f.get("properties") or {}
        geom = f.get("geometry") or {}

        if not fid or not isinstance(props, dict) or not isinstance(geom, dict):
            continue

        d = distance_to_geometry_miles(HOME_LAT, HOME_LON, geom)
        if d is None:
            continue

        # Only raise proximity alert when within threshold
        if d <= threshold_miles:
            event = props.get("event") or "Weather Alert"
            severity = str(props.get("severity", "Moderate")).lower()
            level = "crit" if severity in ("severe", "extreme") else "warn"

            key = f"wxprox:{fid}"
            active_keys.add(key)

            title = f"{event} within {d:.1f} miles"
            headline = (props.get("headline") or "").strip()
            msg = headline if headline else f"NWS alert is within {d:.1f} miles of ZIP 67601."

            if alerts_db.raise_alert(
                ts=now,
                source="weather",
                level=level,
                title=title,
                message=msg[:800],
                key=key,
            ):
                created += 1

    # Clear old proximity alerts that are no longer active/nearby
    rows = alerts_db.list_alerts(active_only=True, limit=500)
    for r in rows:
        if r.get("key", "").startswith("wxprox:") and r.get("key") not in active_keys:
            alerts_db.clear_alert(key=r["key"], cleared_ts=now)

    return created


if __name__ == "__main__":
    n = sync_storm_proximity()
    print(f"Storm proximity sync complete. New proximity alerts: {n}")
