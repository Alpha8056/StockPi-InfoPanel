# StockPi-InfoPanel — Project Documentation

---

## How It All Fits Together

nginx listens on port 80 and acts as the front door for everything. The launcher home screen is a static HTML file served directly by nginx. Kitchen Inventory and Info Panel are separate Python/Flask apps running under gunicorn, each on their own port. nginx proxies requests to them based on the URL prefix.

```
Browser → nginx :80
    /              → static launcher (index.html)
    /kitchen/      → gunicorn :5000  (kitchen_inventory/app.py)
    /panel/        → gunicorn :5100  (homepanel/app.py)
    /system/       → gunicorn :5100  (homepanel/app.py — system routes)
```

nginx also injects the "Apps" back-button into every page via `sub_filter` so you can always navigate back to the launcher.

---

## File Structure

```
StockPi-InfoPanel/
├── launcher/
│   └── index.html              Home screen (clock, app buttons, system controls)
├── homepanel/                  Info Panel Flask app (port 5100)
│   ├── app.py                  Main app — all routes, HTML templates, background threads
│   ├── settings.py             Load/save panel_settings.json
│   ├── weather_client.py       Fetches weather from NWS API, manages cache
│   ├── storm_proximity.py      Checks NWS alert polygons vs. home lat/lon, raises alerts
│   ├── net_monitor.py          Background ping/TCP/HTTP monitor for homelab devices
│   ├── network_db.py           SQLite schema + write functions for network data
│   ├── network_read.py         Read-only queries for network status
│   ├── service_read.py         Read-only queries for per-device service status
│   ├── devices_store.py        Load/save devices.json (CRUD helpers)
│   ├── alerts_db.py            SQLite schema + raise/clear/list for all alerts
│   ├── rf_scan.py              WiFi scan (nmcli) and BLE scan (bluetoothctl)
│   ├── config.json             ZIP code and home lat/lon (created by setup.sh)
│   ├── devices.json            List of homelab devices to monitor (created by setup.sh)
│   ├── panel_settings.json     Feature flags + weather section order (created by setup.sh)
│   ├── network.db              SQLite — device/service ping history and current status
│   ├── alerts.db               SQLite — active and cleared alerts (weather, network, etc.)
│   ├── data_cache/             JSON cache files for NWS API responses
│   └── venv/                   Python virtual environment
├── kitchen_inventory/          Kitchen Inventory Flask app (port 5000)
│   ├── app.py                  Main app — all routes and HTML templates
│   ├── inventory.py            All inventory logic (add, remove, grocery list, thresholds)
│   ├── db.py                   SQLite schema, migrations, and init
│   ├── inventory.db            SQLite — items, grocery list, locations, barcode cache, events
│   ├── templates/
│   │   └── resolve_barcode.html  Page shown when a barcode has no name yet
│   └── venv/                   Python virtual environment
├── nginx/
│   └── launcher.conf           nginx site config — routing, proxy, sub_filter injection
├── systemd/
│   ├── infopanel.service       systemd unit for the Info Panel (template, patched by setup.sh)
│   ├── kitchen.service         systemd unit for Kitchen Inventory (template, patched by setup.sh)
│   └── kitchen-kiosk.desktop   Autostart file for Chromium kiosk mode (optional)
├── setup.sh                    Full install script — packages, venvs, config, nginx, systemd
├── config.json.example         Example config showing the expected structure
├── TODO.md                     Feature tracker
└── DOCS.md                     This file
```

---

## Config Files

### `homepanel/config.json`
Created by `setup.sh`. Controls weather location.
```json
{
  "weather": {
    "zip": "12345"
  },
  "location": {
    "lat": null,
    "lon": null
  }
}
```
- `zip` — ZIP code used to pull weather from NWS. Editable from `/panel/settings`.
- `lat` / `lon` — Home coordinates used by storm proximity. If null, derived from ZIP via pgeocode.

### `homepanel/panel_settings.json`
Controls which cards show on the info panel and weather section order.
```json
{
  "weather_enabled": true,
  "rf_enabled": true,
  "network_enabled": true,
  "alerts_enabled": true,
  "weather_sections": {
    "current": 1,
    "hourly": 2,
    "alerts": 3,
    "forecast": 4,
    "radar": 5
  }
}
```

### `homepanel/devices.json`
List of homelab devices for the network monitor to ping. Editable from the UI.
```json
{
  "devices": [
    {
      "ip": "10.0.0.1",
      "name": "Router",
      "type": "router",
      "services": [
        { "name": "Web UI", "type": "http", "port": 80, "path": "/" }
      ]
    }
  ]
}
```

---

## Databases

### `kitchen_inventory/inventory.db`
| Table | What it stores |
|---|---|
| `items` | Every scanned item — barcode, name, location, quantity, low threshold |
| `grocery_list` | Items that hit 0 qty or were manually added |
| `locations` | Storage zones (Pantry, Fridge, etc.) |
| `barcode_cache` | Barcode → product name lookups (offline cache) |
| `events` | Full history of every add/remove/move/delete action |

### `homepanel/network.db`
| Table | What it stores |
|---|---|
| `device_status` | Latest ping result per device (current state) |
| `device_history` | Every ping sample ever recorded |
| `service_status` | Latest TCP/HTTP check result per service |
| `service_history` | Every service check sample ever recorded |

### `homepanel/alerts.db`
| Table | What it stores |
|---|---|
| `alerts` | All alerts — weather proximity, device down, service down. Has `is_active` flag and `cleared_ts` |

Alert sources: `network`, `weather`
Alert levels: `info`, `warn`, `crit`

---

## Background Threads (homepanel)

Two threads run inside the gunicorn process:

| Thread | Interval | What it does |
|---|---|---|
| `storm_prox_loop` | 15 minutes | Calls NWS alerts API, checks if any alert polygon is within 50 miles of home, raises/clears proximity alerts in alerts.db |
| `rf_autoscan_loop` | 5 minutes | WiFi scan via nmcli (disabled by default — `AUTO_SCAN_ENABLED = False`) |

The network monitor (`net_monitor.py`) is **not** a thread inside the app — it runs as a separate process or is called on demand.

---

## Services

Both apps are managed by systemd and run under gunicorn.

| Service | Port | Working directory |
|---|---|---|
| `infopanel.service` | 5100 | `homepanel/` |
| `kitchen.service` | 5000 | `kitchen_inventory/` |

Both services are enabled to auto-start on boot (via `setup.sh`).

---

## Troubleshooting Commands

### Check service status
```bash
sudo systemctl status infopanel.service
sudo systemctl status kitchen.service
sudo systemctl status nginx
```

### View live logs
```bash
sudo journalctl -u infopanel.service -f
sudo journalctl -u kitchen.service -f
sudo journalctl -u nginx -f
```

### View last 30 log lines (no pager)
```bash
sudo journalctl -u infopanel.service -n 30 --no-pager
sudo journalctl -u kitchen.service -n 30 --no-pager
```

### Restart services
```bash
sudo systemctl restart infopanel.service
sudo systemctl restart kitchen.service
sudo systemctl restart nginx
```

### Check if ports are in use (stale gunicorn processes)
```bash
sudo ss -tlnp | grep 5000
sudo ss -tlnp | grep 5100
```

### Test apps directly (bypass nginx)
```bash
curl http://127.0.0.1:5000/
curl http://127.0.0.1:5100/
```

### Test through nginx
```bash
curl http://localhost/kitchen/
curl http://localhost/panel/
```

### Kill a stale gunicorn process holding a port
```bash
sudo kill <PID>
# Then restart the service
sudo systemctl restart kitchen.service
```

### Check nginx config is valid
```bash
sudo nginx -t
```

### Manually run storm proximity sync
```bash
cd ~/StockPi-InfoPanel/homepanel
source venv/bin/activate
python storm_proximity.py
```

### Inspect the inventory database
```bash
sqlite3 ~/StockPi-InfoPanel/kitchen_inventory/inventory.db
.tables
SELECT * FROM items;
SELECT * FROM grocery_list;
.quit
```

### Inspect the alerts database
```bash
sqlite3 ~/StockPi-InfoPanel/homepanel/alerts.db
SELECT * FROM alerts WHERE is_active=1;
.quit
```

### Clear the weather API cache (force fresh fetch)
```bash
rm ~/StockPi-InfoPanel/homepanel/data_cache/*.json
```

### Update from GitHub and restart
```bash
cd ~/StockPi-InfoPanel && git pull
sudo systemctl restart infopanel.service
sudo systemctl restart kitchen.service
```

---

## NWS API Notes

Weather data comes entirely from the free NWS API (`api.weather.gov`). No API key required.

Cache TTLs:
| Data | Cache TTL |
|---|---|
| ZIP → lat/lon | 7 days |
| /points (grid lookup) | 24 hours |
| Hourly forecast | 5 minutes |
| Multi-day forecast | 10 minutes |
| Active alerts | 60 seconds |

If weather stops loading, delete the cache files (see above) and check the logs for HTTP errors from the NWS API.
