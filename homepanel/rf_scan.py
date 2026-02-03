from __future__ import annotations

import subprocess
from typing import Any, Dict, List, Tuple


def _run(cmd: List[str], timeout: int = 10) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def scan_wifi() -> Tuple[List[Dict[str, Any]], str]:
    networks: List[Dict[str, Any]] = []

    # nmcli (preferred)
    rc, out, err = _run(
        ["bash", "-lc", "command -v nmcli >/dev/null 2>&1 && nmcli -t -f SSID,SIGNAL,SECURITY dev wifi list"],
        timeout=12,
    )
    if rc == 0 and out:
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) >= 3:
                ssid = parts[0].strip() or "<hidden>"
                signal = parts[1].strip() or "—"
                sec = ":".join(parts[2:]).strip() or "—"
                networks.append({"ssid": ssid, "signal": signal, "security": sec})
        return networks, "via nmcli"

    note = err or "Wi-Fi scan unavailable (missing tools or permissions)."
    return [], note


def scan_ble(duration_sec: int = 10) -> Tuple[List[Dict[str, Any]], str]:
    """
    BLE scan via bluetoothctl. We parse live output from the scan command
    (more reliable than relying on `bluetoothctl devices` cache).
    Returns list of {mac,name}.
    """
    rc, _, _ = _run(["bash", "-lc", "command -v bluetoothctl >/dev/null 2>&1 && echo ok"], timeout=5)
    if rc != 0:
        return [], "bluetoothctl not found."

    # Power on adapter (ignore failures)
    _run(["bash", "-lc", "bluetoothctl power on >/dev/null 2>&1 || true"], timeout=5)

    # Run scan and CAPTURE output; parse "Device XX:XX... Name"
    rc, out, err = _run(
        ["bash", "-lc", f"timeout {duration_sec} bluetoothctl scan on"],
        timeout=duration_sec + 3,
    )

    devices: List[Dict[str, Any]] = []
    for line in (out or "").splitlines():
        line = line.strip()
        # Lines often look like: "[NEW] Device AA:BB:CC:DD:EE:FF Some Name"
        if "Device " not in line:
            continue
        idx = line.find("Device ")
        rest = line[idx + len("Device "):].strip()
        parts = rest.split(" ", 1)
        mac = parts[0].strip() if parts else ""
        name = parts[1].strip() if len(parts) > 1 else "—"
        if mac and len(mac) >= 17:
            devices.append({"mac": mac, "name": name or "—"})

    # de-dup by mac
    seen = set()
    dedup = []
    for d in devices:
        if d["mac"] in seen:
            continue
        seen.add(d["mac"])
        dedup.append(d)

    note = f"scanned {duration_sec}s"
    if err and not dedup:
        note += f" (stderr: {err[:80]})"
    return dedup, note
