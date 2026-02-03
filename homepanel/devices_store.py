from __future__ import annotations

import json
import os
from typing import Any, Dict, List

DEVICES_PATH = os.path.join(os.path.dirname(__file__), "devices.json")


def load_devices() -> List[Dict[str, Any]]:
    with open(DEVICES_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    devices = cfg.get("devices", [])
    return devices if isinstance(devices, list) else []


def save_devices(devices: List[Dict[str, Any]]) -> None:
    payload = {"devices": devices}
    tmp_path = DEVICES_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, DEVICES_PATH)


def get_device(idx: int) -> Dict[str, Any]:
    devices = load_devices()
    return devices[idx]


def add_device(device: Dict[str, Any]) -> None:
    devices = load_devices()
    devices.append(device)
    save_devices(devices)


def update_device(idx: int, device: Dict[str, Any]) -> None:
    devices = load_devices()
    devices[idx] = device
    save_devices(devices)


def delete_device(idx: int) -> None:
    devices = load_devices()
    devices.pop(idx)
    save_devices(devices)
