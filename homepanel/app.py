from flask import Flask, render_template_string, request, redirect, url_for

import weather_client
import network_read
import service_read
import devices_store
import rf_scan
import alerts_db
import threading
import time
import subprocess
import settings
from flask import Response



# --- Storm proximity scheduler (runs inside the web app) ---
import threading
import storm_proximity

from werkzeug.middleware.proxy_fix import ProxyFix

class PrefixMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        prefix = environ.get("HTTP_X_FORWARDED_PREFIX", "")
        if prefix:
            environ["SCRIPT_NAME"] = prefix
        return self.app(environ, start_response)



STORM_PROX_INTERVAL_SECONDS = 15 * 60  # 15 minutes
STORM_PROX_ENABLED = True

def storm_prox_loop():
    while True:
        if STORM_PROX_ENABLED:
            try:
                n = storm_proximity.sync_storm_proximity()
                print(f"[StormProx] Sync OK. New proximity alerts: {n}")
            except Exception as e:
                print("[StormProx] Sync error:", e)
        time.sleep(STORM_PROX_INTERVAL_SECONDS)

_storm_thread = threading.Thread(target=storm_prox_loop, daemon=True)
_storm_thread.start()
# --- end storm proximity scheduler ---


AUTO_SCAN_INTERVAL = 300  # seconds (5 minutes for now)
AUTO_SCAN_ENABLED = False

def rf_autoscan_loop():
    while True:
        if AUTO_SCAN_ENABLED:
            try:
                wifi, wifi_note = rf_scan.scan_wifi()

                wifi_rows = []
                for n in wifi:
                    wifi_rows.append({
                        "ssid": n.get("ssid", "—"),
                        "signal": n.get("signal", "—"),
                        "security": n.get("security", "—"),
                    })

                RF_CACHE["wifi"] = wifi_rows
                RF_CACHE["wifi_note"] = wifi_note
                RF_CACHE["last_scan"] = time.strftime("%Y-%m-%d %H:%M:%S")

                print(f"[RF] Auto-scan complete: {len(wifi_rows)} networks")

                # persist
                try:
                    _rf_save_state()
                except Exception:
                    pass

            except Exception as e:
                print("[RF] Auto-scan error:", e)

        time.sleep(AUTO_SCAN_INTERVAL)

autoscan_thread = threading.Thread(target=rf_autoscan_loop, daemon=True)
autoscan_thread.start()

app = Flask(__name__)
app.secret_key = "change-me-later"

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.wsgi_app = PrefixMiddleware(app.wsgi_app)

@app.context_processor
def inject_script_root():
    return {"script_root": request.script_root}



BASE_CSS = """
<style>
  :root{
    --bg:#0b0f14;
    --panel:#111826;
    --panel2:#0f1622;
    --text:#e5e7eb;
    --muted:#9ca3af;
    --border:#1f2937;
    --accent:#60a5fa;
    --good:#34d399;
    --bad:#f87171;
    --warn:#fbbf24;
  }
  *{box-sizing:border-box}
  body{ margin:0; background:var(--bg); color:var(--text);
        font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; }
  a{ color:inherit; }
  .wrap{ padding:16px; max-width:1200px; margin:0 auto; }
  .card{ background:linear-gradient(180deg, var(--panel), var(--panel2));
         border:1px solid var(--border); border-radius:16px; padding:16px; }
  .title{ font-size:18px; font-weight:800; margin:0 0 10px 0; letter-spacing:0.2px; }
  .sub{ color:var(--muted); font-size:16px; margin-top:10px; }
  .badge{ display:inline-block; padding:4px 10px; border-radius:999px;
          font-size:13px; font-weight:800; border:1px solid var(--border); color:var(--muted); }
  .grid{ display:grid; gap:16px; }
  .grid2{ grid-template-columns: 2fr 1fr; }
  .row2{ margin-top:16px; display:grid; gap:16px; grid-template-columns: repeat(3, 1fr); }
  a.tile{ text-decoration:none; display:block; }
  a.tile:hover .card{ border-color:#2b364a; }
  .kv{ display:flex; justify-content:space-between; gap:12px; padding:6px 0; border-top:1px solid rgba(31,41,55,.6); }
  .kv:first-of-type{ border-top:none; padding-top:0; }
  .k{ color:var(--muted); }
  .v{ font-weight:800; }
  .big{ font-size:56px; font-weight:900; line-height:1; margin:0; }
  .weatherLine{ display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; }
  .temp{ font-size:44px; font-weight:900; line-height:1; }
  .cond{ color:var(--muted); font-size:18px; font-weight:800; }

  .topbar{ display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:12px; }
  .btn{ display:inline-block; padding:10px 12px; border-radius:12px; border:1px solid var(--border);
        background:rgba(17,24,38,.35); text-decoration:none; font-weight:800; cursor:pointer; }
  .btnRow{ display:flex; gap:10px; flex-wrap:wrap; }
  .btnDanger{ border-color: rgba(248,113,113,.5); }
  .btnPrimary{ border-color: rgba(96,165,250,.6); }

  table{ width:100%; border-collapse:separate; border-spacing:0; overflow:hidden;
         border:1px solid var(--border); border-radius:14px; }
  th, td{ padding:10px 12px; border-bottom:1px solid rgba(31,41,55,.6); font-size:15px; }
  th{ text-align:left; color:var(--muted); font-weight:900; background:rgba(17,24,38,.35); }
  tr:last-child td{ border-bottom:none; }

  .cards{ display:grid; grid-template-columns: repeat(3, 1fr); gap:16px; }
  .statusDot{ width:10px;height:10px;border-radius:999px;display:inline-block;margin-right:8px; }
  .up{ background: var(--good); }
  .down{ background: var(--bad); }
  .unk{ background: var(--warn); }
  .pill{ display:inline-block; padding:6px 10px; border-radius:999px; border:1px solid var(--border);
         color:var(--muted); font-weight:800; font-size:13px; }
  .hrow{ display:flex; align-items:center; justify-content:space-between; gap:12px; }
  .hname{ font-weight:900; font-size:18px; }

  .svcRow{ margin-top:10px; display:flex; flex-wrap:wrap; gap:8px; }
  .svcPill{ display:inline-flex; align-items:center; gap:8px; padding:6px 10px; border-radius:999px;
            border:1px solid var(--border); font-weight:900; font-size:13px; color:var(--text);
            background:rgba(17,24,38,.35); }
  .svcDot{ width:8px; height:8px; border-radius:999px; display:inline-block; }

  .formGrid{ display:grid; gap:12px; grid-template-columns: 1fr 1fr; }
  .field{ display:flex; flex-direction:column; gap:6px; }
  label{ font-weight:900; color:var(--muted); font-size:13px; }
  input, textarea{ background: rgba(17,24,38,.35); border:1px solid var(--border);
                   border-radius:12px; padding:10px 12px; color:var(--text); font-size:15px; outline:none; }
  textarea{ min-height:120px; resize:vertical; }
  .full{ grid-column: 1 / -1; }
  .help{ color:var(--muted); font-size:13px; line-height:1.35; }
</style>
"""

HOME_HTML = """
<!doctype html>
<html lang="en">
<head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>HomePanel</title>""" + BASE_CSS + """
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="title" style="margin:0">HomePanel</div>
  </div>
  <div class="grid grid2">
    {% if weather_enabled %}
      <a class="tile" href="/weather">
      <div class="card" style="min-height:140px">
        <div class="title">Weather ({{ wx_location }})</div>
        {% if wx_ok %}
          <div class="weatherLine">
            <div class="temp">{{ wx_temp }}</div>
            <div class="cond">{{ wx_condition }}</div>
          </div>
          <div class="sub">
            Feels like: <b>{{ wx_feels }}</b> • High/Low: <b>{{ wx_hi }}</b>/<b>{{ wx_lo }}</b> • Precip: <b>{{ wx_precip }}</b>
          </div>
          <div class="sub">Updated: {{ wx_updated }}</div>
        {% else %}
          <div class="sub">Weather unavailable right now.</div>
          <div style="margin-top:14px"><span class="badge">No data</span></div>
        {% endif %}
      </div>
    </a>
    {% endif %}

    <div class="card" style="min-height:140px">
      <div class="title">Time</div>
      <p class="big" id="clock">--:--</p>
      <div class="sub" id="dateLine">Loading…</div>
    </div>
  </div>

    <div class="row2">
      {% if rf_enabled %}
      <a class="tile" href="/rf">
        <div class="card">
          <div class="title">RF / Nearby Signals</div>
          <div class="kv"><div class="k">Wi-Fi</div><div class="v">{{ rf_wifi_count }}</div></div>
          <div class="kv"><div class="k">BLE</div><div class="v">{{ rf_ble_count }}</div></div>
          <div class="kv"><div class="k">Last Scan</div><div class="v">{{ rf_last_scan }}</div></div>
        </div>
      </a>
      {% endif %}

      {% if network_enabled %}
      <a class="tile" href="/network">
        <div class="card">
          <div class="title">Network / Homelab</div>
          <div class="kv"><div class="k">Devices</div><div class="v">{{ net_devices }}</div></div>
          <div class="kv"><div class="k">Offline</div><div class="v">{{ net_offline }}</div></div>
          <div class="kv"><div class="k">Status</div><div class="v">{{ net_status }}</div></div>
        </div>
      </a>
      {% endif %}

      {% if alerts_enabled %}
      <a class="tile" href="/events">
        <div class="card">
          <div class="title">Alerts / Events</div>
          <div class="kv"><div class="k">Alert Count</div><div class="v">—</div></div>
          <div class="kv"><div class="k">Severe Weather</div><div class="v">—</div></div>
          <div class="kv"><div class="k">Updated</div><div class="v">—</div></div>
        </div>
      </a>
      {% endif %}
    </div>


<script>
function tick(){
  const now = new Date();
  document.getElementById('clock').textContent =
    String(now.getHours()).padStart(2,'0') + ":" + String(now.getMinutes()).padStart(2,'0');
  document.getElementById('dateLine').textContent =
    now.toLocaleDateString(undefined, { weekday:'long', year:'numeric', month:'long', day:'numeric' });
}
tick(); setInterval(tick, 1000);
</script>
</body></html>
"""

WEATHER_HTML = """
<!doctype html>
<html lang="en">
<head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Weather</title>""" + BASE_CSS + """
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="title" style="margin:0">Weather Details ({{ wx_location }})</div>
    <a class="btn" href="/">Home</a>
  </div>

  <div class="card">
    {% if wx_ok %}
      <div class="weatherLine">
        <div class="temp">{{ wx_temp }}</div>
        <div class="cond">{{ wx_condition }}</div>
      </div>
      <div class="sub">
        Feels like: <b>{{ wx_feels }}</b> • High/Low: <b>{{ wx_hi }}</b>/<b>{{ wx_lo }}</b> • Precip: <b>{{ wx_precip }}</b>
      </div>
      <div class="sub">Updated: {{ wx_updated }}</div>
    {% else %}
      <div class="sub">Weather unavailable right now.</div>
    {% endif %}
  </div>
  <div style="height:16px"></div>

  <div class="card">
    <div class="title">Hourly Forecast (Next 12 Hours)</div>
    {% if hourly_rows %}
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Temp</th>
            <th>Condition</th>
            <th>Precip</th>
            <th>Wind</th>
          </tr>
        </thead>
        <tbody>
        {% for r in hourly_rows %}
          <tr>
            <td>{{ r.time }}</td>
            <td><b>{{ r.temp }}</b></td>
            <td>{{ r.cond }}</td>
            <td>{{ r.precip }}</td>
            <td>{{ r.wind }}</td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
    {% else %}
      <div class="sub">No hourly data available.</div>
    {% endif %}
  </div>

  <div style="height:16px"></div>

  <div class="card">
    <div class="title">Severe Weather & Alerts</div>
    {% if alerts %}
      {% for a in alerts %}
        <div style="padding:12px 0;border-top:1px solid rgba(31,41,55,.6)">
          <div style="font-weight:900">{{ a.headline }}</div>
          <div class="muted" style="margin-top:6px">{{ a.when }}</div>
          <div style="margin-top:8px">{{ a.desc }}</div>
        </div>
      {% endfor %}
    {% else %}
      <div class="sub">No active alerts.</div>
    {% endif %}
  </div>
</div>
</div>

  <div style="height:16px"></div>

  <div class="card">
    <div class="title">Tomorrow's Forecast</div>
    {% if tomorrow_periods %}
      {% for p in tomorrow_periods %}
        <div style="padding:12px 0; border-top:1px solid rgba(31,41,55,.6)">
          <div style="display:flex; justify-content:space-between; align-items:center; gap:12px;">
            <div style="font-weight:900; font-size:16px;">{{ p.name }}</div>
            <div style="font-size:22px; font-weight:900;">{{ p.temp }}</div>
          </div>
          <div class="sub" style="margin-top:4px;">{{ p.cond }}</div>
          <div class="sub">Precip: <b>{{ p.precip }}</b> • Wind: <b>{{ p.wind }}</b></div>
          <div style="margin-top:6px; color:var(--muted); font-size:13px;">{{ p.detail }}</div>
        </div>
      {% endfor %}
    {% else %}
      <div class="sub">No forecast data available.</div>
    {% endif %}
  </div>

  <div style="height:16px"></div>

  {% if storm_banner %}
  <div class="card" style="border:1px solid rgba(245,158,11,.35);">
    <div class="title">⚠ Storm Proximity</div>
    <div style="margin-top:6px; font-weight:900">{{ storm_banner }}</div>
    <div class="muted" style="margin-top:6px;">This appears when an active NWS warning polygon comes within your threshold.</div>
  </div>
  <div style="height:16px"></div>
  {% endif %}

  <div class="card">
    <div class="title">Radar (Dodge City – KDDC)</div>
    <div class="sub">Animated loop — refreshes every 2 minutes</div>
    <div style="border-radius:14px; overflow:hidden; border:1px solid rgba(31,41,55,.6); margin-top:10px;">
      <img id="radarImg" src="https://radar.weather.gov/ridge/standard/{{ radar_station }}_loop.gif"
           alt="Radar loop" style="width:100%; display:block;" />
    </div>
    <div class="muted" style="margin-top:10px" id="radarUpdated">Radar updated: —</div>
  </div>

  <div style="height:16px"></div>

  <div class="card">
    <div class="title">Severe Weather & Alerts</div>
    {% if alerts %}
      {% for a in alerts %}
        <div style="padding:12px 0;border-top:1px solid rgba(31,41,55,.6)">
          <div style="font-weight:900">{{ a.headline }}</div>
          <div class="muted" style="margin-top:6px">{{ a.when }}</div>
          <div style="margin-top:8px">{{ a.desc }}</div>
        </div>
      {% endfor %}
    {% else %}
      <div class="sub">No active alerts.</div>
    {% endif %}
  </div>

</div>

<script>
(function () {
  const img = document.getElementById("radarImg");
  const updated = document.getElementById("radarUpdated");
  function refreshRadar() {
    img.src = "https://radar.weather.gov/ridge/standard/{{ radar_station }}_loop.gif?t=" + Date.now();
    updated.textContent = "Radar refreshed: " + new Date().toLocaleString();
  }
  refreshRadar();
  setInterval(refreshRadar, 120000);
})();
</script>

</body></html>
"""

NETWORK_HTML = """
<!doctype html>
<html lang="en">
<head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Network</title>""" + BASE_CSS + """
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="title" style="margin:0">Network / Homelab</div>
    <div class="btnRow">
      <a class="btn btnPrimary" href="/network/manage">Manage Devices</a>
      <a class="btn" href="/">Home</a>
    </div>
  </div>

  <div class="cards">
    {% for d in devices %}
      <div class="card">
        <div class="hrow">
          <div class="hname">
            {% if d.status == "UP" %}
              <span class="statusDot up"></span>
            {% elif d.status == "DOWN" %}
              <span class="statusDot down"></span>
            {% else %}
              <span class="statusDot unk"></span>
            {% endif %}
            {{ d.name }}
          </div>
          <span class="pill">{{ d.type or "device" }}</span>
        </div>

        <div class="sub">{{ d.ip }}</div>

        <div style="margin-top:10px">
          <div class="kv"><div class="k">Status</div><div class="v">{{ d.status }}</div></div>
          <div class="kv"><div class="k">Last Seen</div><div class="v">{{ d.last_seen }}</div></div>

          <div class="k" style="margin-top:10px">Services</div>
          <div class="svcRow">
            {% if d.services %}
              {% for s in d.services %}
                <span class="svcPill">
                  {% if s.is_up %}
                    <span class="svcDot up"></span>
                  {% else %}
                    <span class="svcDot down"></span>
                  {% endif %}
                  {{ s.name }}
                </span>
              {% endfor %}
            {% else %}
              <span class="badge">None</span>
            {% endif %}
          </div>
        </div>
      </div>
    {% endfor %}
  </div>
</div>
</body></html>
"""



EVENTS_HTML = """
<!doctype html>
<html lang="en">
<head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Alerts</title>""" + BASE_CSS + """
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="title" style="margin:0">Alerts / Events</div>
    <div class="btnRow">
      <a class="btn" href="/">Home</a>
    </div>
  </div>

  <div class="row2" style="grid-template-columns: repeat(3, 1fr); margin-top:0;">
    <div class="card">
      <div class="title">Active Alerts</div>
      <div class="kv"><div class="k">Count</div><div class="v">{{ active_count }}</div></div>
      <div class="kv"><div class="k">Last updated</div><div class="v">{{ updated }}</div></div>
    </div>

    <div class="card">
      <div class="title">Severe Weather</div>
      <div class="sub">Wiring next: show active NWS alerts + storm proximity.</div>
    </div>

    <div class="card">
      <div class="title">Network</div>
      <div class="sub">Wiring next: device/service down alerts from net monitor.</div>
    </div>
  </div>

  <div style="height:16px"></div>

  <div class="card">
    <div class="title">Active</div>
    {% if active %}
      {% for a in active %}
        <div style="padding:12px 0;border-top:1px solid rgba(31,41,55,.6)">
          <div style="display:flex; justify-content:space-between; gap:10px; align-items:flex-start;">
            <div style="font-weight:900">{{ a.title }}</div>
            <div class="pill">{{ a.level }}</div>
          </div>
          <div class="muted" style="margin-top:6px">
            {{ a.source }} • {{ a.ts_local }}
          </div>
          <div style="margin-top:8px">{{ a.message }}</div>
        </div>
      {% endfor %}
    {% else %}
      <div class="sub">No active alerts.</div>
    {% endif %}
  </div>

  <div style="height:16px"></div>

  <div class="card">
    <div class="title">Recent</div>
    {% if recent %}
      <table>
        <thead>
          <tr>
            <th>Time</th><th>Level</th><th>Source</th><th>Title</th><th>Status</th>
          </tr>
        </thead>
        <tbody>
          {% for r in recent %}
          <tr>
            <td>{{ r.ts_local }}</td>
            <td><span class="pill">{{ r.level }}</span></td>
            <td class="muted">{{ r.source }}</td>
            <td><b>{{ r.title }}</b></td>
            <td class="muted">{{ "ACTIVE" if r.is_active else "CLEARED" }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    {% else %}
      <div class="sub">No history yet.</div>
    {% endif %}
  </div>

</div>
</body></html>
"""

RF_HTML = """
<!doctype html>
<html lang="en">
<head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>RF</title>""" + BASE_CSS + """
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="title" style="margin:0">RF / Nearby Signals</div>
    <div class="btnRow">
      <a class="btn btnPrimary" href="/rf/scan">Scan now</a>
      <a class="btn" href="/">Home</a>
    </div>
  </div>

  <div class="row2" style="grid-template-columns: repeat(3, 1fr); margin-top:0;">
    <div class="card">
      <div class="title">Wi-Fi</div>
      <div class="kv"><div class="k">Networks found</div><div class="v">{{ wifi_count }}</div></div>
      <div class="kv"><div class="k">Scan method</div><div class="v">{{ wifi_note }}</div></div>
    </div>

    <div class="card">
      <div class="title">Bluetooth (BLE)</div>
      <div class="kv"><div class="k">Devices found</div><div class="v">{{ ble_count }}</div></div>
      <div class="kv"><div class="k">Status</div><div class="v">{{ ble_note }}</div></div>
    </div>

    <div class="card">
      <div class="title">Scan</div>
      <div class="kv"><div class="k">Last scan</div><div class="v">{{ last_scan }}</div></div>
      <div class="kv"><div class="k">Refresh</div><div class="v">Tap “Scan now”</div></div>
    </div>
  </div>

  <div style="height:16px"></div>

  <div class="card">
    <div class="title">Wi-Fi Results</div>
    {% if wifi %}
      <table>
        <thead>
          <tr>
            <th>SSID</th>
            <th>Signal</th>
            <th>Security</th>
          </tr>
        </thead>
        <tbody>
          {% for n in wifi %}
          <tr>
            <td><b>{{ n.ssid }}</b></td>
            <td>{{ n.signal }}</td>
            <td class="muted">{{ n.security }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    {% else %}
      <div class="sub">No Wi-Fi results yet. Tap <b>Scan now</b>.</div>
    {% endif %}
  </div>

  <div style="height:16px"></div>

  <div class="card">
    <div class="title">BLE Results</div>
    <div class="sub">Coming next: real BLE scan results displayed here.</div>
  </div>
</div>
</body></html>
"""

MANAGE_HTML = """
<!doctype html>
<html lang="en">
<head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Manage Devices</title>""" + BASE_CSS + """
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="title" style="margin:0">Manage Devices</div>
    <div class="btnRow">
      <a class="btn btnPrimary" href="/network/device/new">Add Device</a>
      <a class="btn" href="/network">Back</a>
    </div>
  </div>

  <div class="card">
    {% if devices %}
      <table>
        <thead><tr>
          <th>#</th><th>Name</th><th>IP</th><th>Type</th><th>Services</th><th>Actions</th>
        </tr></thead>
        <tbody>
          {% for d in devices %}
          <tr>
            <td>{{ loop.index0 }}</td>
            <td><b>{{ d.name }}</b></td>
            <td>{{ d.ip }}</td>
            <td>{{ d.type }}</td>
            <td>{{ d.svc_count }}</td>
            <td>
              <a class="btn" href="/network/device/{{ loop.index0 }}/edit">Edit</a>
              <a class="btn btnDanger" href="/network/device/{{ loop.index0 }}/delete">Delete</a>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    {% else %}
      <div class="sub">No devices configured.</div>
    {% endif %}
  </div>
</div>
</body></html>
"""

DEVICE_FORM_HTML = """
<!doctype html>
<html lang="en">
<head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{{ title }}</title>""" + BASE_CSS + """
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="title" style="margin:0">{{ title }}</div>
    <a class="btn" href="/network/manage">Back</a>
  </div>

  {% if error %}
    <div class="card" style="border-color: rgba(248,113,113,.55); margin-bottom: 12px;">
      <div class="title" style="margin-bottom:6px;">Fix this first</div>
      <div class="sub">{{ error }}</div>
    </div>
  {% endif %}

  <form class="card" method="post" onsubmit="return buildServicesJson();">
    <div class="formGrid">
      <div class="field">
        <label>Device Name</label>
        <input name="name" value="{{ dev.name }}" required />
      </div>

      <div class="field">
        <label>IP Address</label>
        <input name="ip" value="{{ dev.ip }}" required />
      </div>

      <div class="field">
        <label>Device Type</label>
        <input name="type" value="{{ dev.type }}" placeholder="server / pi / router / etc." />
      </div>

      <div class="field full">
        <label>Services</label>

        <div class="help" style="margin-bottom:10px">
          Add checks like SSH (TCP 22) or Jellyfin (HTTP 8096 /).
        </div>

        <div id="servicesBox" style="display:grid; gap:10px;"></div>

        <div style="margin-top:10px" class="btnRow">
          <button class="btn btnPrimary" type="button" onclick="addServiceRow()">+ Add Service</button>
        </div>

        <!-- Hidden field that we submit to Flask -->
        <input type="hidden" name="services_json" id="services_json" value="[]">
      </div>
    </div>

    <div style="height:12px"></div>
    <div class="btnRow">
      <button class="btn btnPrimary" type="submit">Save</button>
      <a class="btn" href="/network/manage">Cancel</a>
    </div>
  </form>
</div>

<script>
  // Provided by Flask
  const initialServices = {{ services_list_json|safe }};

  function serviceRowTemplate(svc){
    const name = (svc && svc.name) ? svc.name : "";
    const type = (svc && svc.type) ? svc.type : "tcp";
    const port = (svc && svc.port !== undefined && svc.port !== null) ? String(svc.port) : "";
    const path = (svc && svc.path) ? svc.path : "/";

    const id = "svc_" + Math.random().toString(16).slice(2);

    return `
      <div class="card" style="padding:12px;border-radius:14px;">
        <div class="formGrid" style="grid-template-columns: 1.2fr .9fr .6fr;">
          <div class="field">
            <label>Service Name</label>
            <input data-k="name" value="${escapeHtml(name)}" placeholder="SSH / Jellyfin / HA" required>
          </div>

          <div class="field">
            <label>Type</label>
            <select data-k="type" onchange="togglePath(this)">
              <option value="tcp" ${type==="tcp" ? "selected":""}>TCP</option>
              <option value="http" ${type==="http" ? "selected":""}>HTTP</option>
            </select>
          </div>

          <div class="field">
            <label>Port</label>
            <input data-k="port" value="${escapeHtml(port)}" inputmode="numeric" placeholder="22 / 8096" required>
          </div>

          <div class="field full pathWrap" style="${type==="http" ? "" : "display:none;"}">
            <label>HTTP Path</label>
            <input data-k="path" value="${escapeHtml(path)}" placeholder="/" />
            <div class="help">Only used for HTTP. Leave as / for most dashboards.</div>
          </div>

          <div class="field full">
            <button class="btn btnDanger" type="button" onclick="removeServiceRow(this)">Remove</button>
          </div>
        </div>
      </div>
    `;
  }

  function escapeHtml(s){
    return String(s ?? "")
      .replaceAll("&","&amp;")
      .replaceAll("<","&lt;")
      .replaceAll(">","&gt;")
      .replaceAll('"',"&quot;")
      .replaceAll("'","&#039;");
  }

  function addServiceRow(svc){
    const box = document.getElementById("servicesBox");
    const html = serviceRowTemplate(svc || {});
    const wrapper = document.createElement("div");
    wrapper.innerHTML = html;
    box.appendChild(wrapper);
  }

  function removeServiceRow(btn){
    const card = btn.closest("div.card");
    if(card) card.parentElement.remove(); // wrapper div
  }

  function togglePath(sel){
    const card = sel.closest("div.card");
    const wrap = card.querySelector(".pathWrap");
    if(!wrap) return;
    wrap.style.display = (sel.value === "http") ? "" : "none";
  }

  function buildServicesJson(){
    const box = document.getElementById("servicesBox");
    const cards = box.querySelectorAll("div.card");
    const out = [];

    for(const card of cards){
      const name = card.querySelector('[data-k="name"]').value.trim();
      const type = card.querySelector('[data-k="type"]').value.trim();
      const portRaw = card.querySelector('[data-k="port"]').value.trim();

      if(!name){ alert("Service name is required."); return false; }
      if(!portRaw){ alert("Service port is required."); return false; }
      const port = Number(portRaw);
      if(!Number.isFinite(port) || port <= 0 || port > 65535){
        alert("Service port must be a number between 1 and 65535.");
        return false;
      }

      const svc = { name, type, port };
      if(type === "http"){
        let path = (card.querySelector('[data-k="path"]').value || "/").trim();
        if(!path.startsWith("/")) path = "/" + path;
        svc.path = path;
      }
      out.push(svc);
    }

    document.getElementById("services_json").value = JSON.stringify(out);
    return true;
  }

  // Init
  if(Array.isArray(initialServices) && initialServices.length){
    for(const s of initialServices) addServiceRow(s);
  } else {
    // Start with one blank row to guide the user
    addServiceRow({type:"tcp"});
  }
</script>
</body></html>
""" + BASE_CSS + """
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="title" style="margin:0">{{ title }}</div>
    <a class="btn" href="/network/manage">Back</a>
  </div>

  {% if error %}
    <div class="card" style="border-color: rgba(248,113,113,.55); margin-bottom: 12px;">
      <div class="title" style="margin-bottom:6px;">Fix this first</div>
      <div class="sub">{{ error }}</div>
    </div>
  {% endif %}

  <form class="card" method="post">
    <div class="formGrid">
      <div class="field">
        <label>Device Name</label>
        <input name="name" value="{{ dev.name }}" required />
      </div>

      <div class="field">
        <label>IP Address</label>
        <input name="ip" value="{{ dev.ip }}" required />
      </div>

      <div class="field">
        <label>Device Type</label>
        <input name="type" value="{{ dev.type }}" placeholder="server / pi / router / etc." />
      </div>

      <div class="field full">
        <label>Services (JSON list)</label>
        <textarea name="services_json" spellcheck="false">{{ services_json }}</textarea>
        <div class="help">We’ll replace this with a normal “Add Service” form next.</div>
      </div>
    </div>

    <div style="height:12px"></div>
    <div class="btnRow">
      <button class="btn btnPrimary" type="submit">Save</button>
      <a class="btn" href="/network/manage">Cancel</a>
    </div>
  </form>
</div>
</body></html>
"""

DELETE_HTML = """
<!doctype html>
<html lang="en">
<head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Delete Device</title>""" + BASE_CSS + """
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="title" style="margin:0">Delete Device</div>
    <a class="btn" href="/network/manage">Back</a>
  </div>

  <div class="card">
    <div class="title" style="margin-bottom:6px">Are you sure?</div>
    <div class="sub">This will remove <b>{{ dev.name }}</b> ({{ dev.ip }}) from <code>devices.json</code>.</div>
    <div style="height:12px"></div>

    <form method="post">
      <div class="btnRow">
        <button class="btn btnDanger" type="submit">Delete</button>
        <a class="btn" href="/network/manage">Cancel</a>
      </div>
    </form>
  </div>
</div>
</body></html>
"""

SETTINGS_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Panel Settings</title>
  <style>
    :root{
      --bg: #0f1115; --panel: #151922; --text: #e7e9ee; --muted: #a8b0c2;
      --border: #2a3142; --btn: #1b2231; --btnHover: #232c3f;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: var(--bg); color: var(--text); font-family: system-ui, sans-serif; padding: 20px; }
    .container { max-width: 600px; margin: 0 auto; }
    h1 { margin-bottom: 20px; }
    .card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin: 20px 0; }
    .setting-row { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid var(--border); }
    .setting-row:last-child { border-bottom: none; }
    .toggle { position: relative; width: 50px; height: 26px; }
    .toggle input { opacity: 0; width: 0; height: 0; }
    .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background: #555; border-radius: 26px; transition: .3s; }
    .slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 4px; bottom: 4px; background: white; border-radius: 50%; transition: .3s; }
    input:checked + .slider { background: #4CAF50; }
    input:checked + .slider:before { transform: translateX(24px); }
    .btn { padding: 12px 24px; background: var(--btn); color: var(--text); border: 1px solid var(--border); border-radius: 8px; cursor: pointer; text-decoration: none; display: inline-block; margin-top: 10px; }
    .btn:hover { background: var(--btnHover); }
  </style>
</head>
<body>
  <div class="container">
    <h1>Panel Settings</h1>
    
    <form method="post" action="settings/update">
      <div class="card">
        <h2 style="margin-bottom: 15px;">Weather Location</h2>
        <div class="setting-row">
          <span>ZIP Code</span>
          <input type="text" name="weather_zip" value="{{ weather_zip }}"
            style="background:#0f1115;border:1px solid #2a3142;border-radius:8px;padding:8px 12px;
                   color:#e7e9ee;font-size:15px;width:120px;text-align:center;"
            maxlength="5" placeholder="67601" />
        </div>
      </div>

      <div class="card">
        <h2 style="margin-bottom: 15px;">Toggle Cards</h2>
        
        <div class="setting-row">
          <span>Weather Card</span>
          <label class="toggle">
            <input type="checkbox" name="weather_enabled" {% if weather_enabled %}checked{% endif %}>
            <span class="slider"></span>
          </label>
        </div>
        
        <div class="setting-row">
          <span>RF / Nearby Signals Card</span>
          <label class="toggle">
            <input type="checkbox" name="rf_enabled" {% if rf_enabled %}checked{% endif %}>
            <span class="slider"></span>
          </label>
        </div>
        
        <div class="setting-row">
          <span>Network / Homelab Card</span>
          <label class="toggle">
            <input type="checkbox" name="network_enabled" {% if network_enabled %}checked{% endif %}>
            <span class="slider"></span>
          </label>
        </div>
        
        <div class="setting-row">
          <span>Alerts Card</span>
          <label class="toggle">
            <input type="checkbox" name="alerts_enabled" {% if alerts_enabled %}checked{% endif %}>
            <span class="slider"></span>
          </label>
        </div>
      </div>
      
      <button type="submit" class="btn">Save Settings</button>
    </form>
  </div>
</body>
</html>
"""


def _parse_services_json(text: str):
    text = (text or "").strip()
    if not text:
        return []
    import json
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Services JSON is invalid: {e.msg} (line {e.lineno}, column {e.colno})")
    if not isinstance(obj, list):
        raise ValueError("Services must be a JSON list (example: [])")
    return obj


def _fmt_ts(ts: int | None) -> str:
    if not ts:
        return "—"
    import datetime
    return datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")


def _safe_get_weather_summary():
    try:
        hourly = weather_client.get_forecast_hourly()
        props = hourly.get("properties", {})
        periods = props.get("periods", []) or []
        if not periods:
            raise ValueError("No hourly periods returned")

        now = periods[0]
        temp_f = now.get("temperature")
        temp_u = now.get("temperatureUnit", "F")
        condition = now.get("shortForecast", "Unknown")
        feels_like = now.get("temperature")

        precip = now.get("probabilityOfPrecipitation", {}) or {}
        precip_val = precip.get("value")
        precip_txt = f"{precip_val}%" if precip_val is not None else "—"

        temps = [float(p.get("temperature")) for p in periods[:24] if isinstance(p.get("temperature"), (int, float))]
        hi = f"{int(max(temps))}°{temp_u}" if temps else "—"
        lo = f"{int(min(temps))}°{temp_u}" if temps else "—"

        updated = props.get("updated", "")
        location = weather_client.get_weather_zip()

        return {
            "wx_ok": True,
            "wx_location": location,
            "wx_temp": f"{temp_f}°{temp_u}" if temp_f is not None else f"—°{temp_u}",
            "wx_condition": condition,
            "wx_feels": f"{feels_like}°{temp_u}" if feels_like is not None else "—",
            "wx_hi": hi,
            "wx_lo": lo,
            "wx_precip": precip_txt,
            "wx_updated": updated or "—",
        }
    except Exception:
        return {
            "wx_ok": False,
            "wx_location": weather_client.get_weather_zip(),
            "wx_temp": "—",
            "wx_condition": "—",
            "wx_feels": "—",
            "wx_hi": "—",
            "wx_lo": "—",
            "wx_precip": "—",
            "wx_updated": "—",
        }


def _network_summary():
    try:
        # based on configured devices (so it matches what you manage)
        cfg = devices_store.load_devices()
        status_rows = {d["ip"]: d for d in network_read.get_latest_status()}

        total = len(cfg)
        offline_names = []
        any_unknown = False

        for d in cfg:
            ip = d.get("ip", "")
            st = status_rows.get(ip)
            if not st:
                any_unknown = True
                continue
            if int(st.get("is_up", 0)) == 0:
                offline_names.append(d.get("name", ip))

        offline_txt = ", ".join(offline_names) if offline_names else "None"
        if offline_names:
            overall = "ISSUES"
        elif any_unknown:
            overall = "UNKNOWN"
        else:
            overall = "UP"

        return {"net_devices": str(total), "net_offline": offline_txt, "net_status": overall}
    except Exception:
        return {"net_devices": "—", "net_offline": "—", "net_status": "—"}



def _safe_hourly_rows(limit: int = 12):
    rows = []
    try:
        hourly = weather_client.get_forecast_hourly()
        periods = hourly.get("properties", {}).get("periods", []) or []
        for p in periods[:limit]:
            start = str(p.get("startTime", ""))
            time_short = start[11:16] if len(start) >= 16 else start

            t = p.get("temperature")
            u = p.get("temperatureUnit", "F")
            temp = f"{t}°{u}" if t is not None else "—"

            cond = p.get("shortForecast", "—")

            pop = p.get("probabilityOfPrecipitation", {}) or {}
            popv = pop.get("value")
            precip = f"{popv}%" if popv is not None else "—"

            ws = p.get("windSpeed", "—")
            wd = p.get("windDirection", "")
            wind = f"{ws} {wd}".strip()

            rows.append({"time": time_short, "temp": temp, "cond": cond, "precip": precip, "wind": wind})
    except Exception:
        pass
    return rows


def _safe_tomorrow_periods():
    rows = []
    try:
        forecast = weather_client.get_forecast()
        periods = forecast.get("properties", {}).get("periods", []) or []
        # Find tomorrow's periods (skip today/tonight)
        tomorrow_periods = [p for p in periods if not p.get("name", "").lower().startswith("to")]
        for p in tomorrow_periods[:2]:  # Day + Night
            t = p.get("temperature")
            u = p.get("temperatureUnit", "F")
            temp = f"{t}°{u}" if t is not None else "—"
            pop = p.get("probabilityOfPrecipitation", {}) or {}
            popv = pop.get("value")
            precip = f"{popv}%" if popv is not None else "—"
            ws = p.get("windSpeed", "—")
            wd = p.get("windDirection", "")
            wind = f"{ws} {wd}".strip()
            detail = p.get("detailedForecast", "")
            if len(detail) > 200:
                detail = detail[:200].rstrip() + "…"
            rows.append({
                "name": p.get("name", "—"),
                "temp": temp,
                "cond": p.get("shortForecast", "—"),
                "precip": precip,
                "wind": wind,
                "detail": detail,
            })
    except Exception:
        pass
    return rows


def _safe_alerts(limit: int = 5):
    items = []
    try:
        a = weather_client.get_alerts()
        feats = a.get("features", []) or []
        for f in feats[:limit]:
            prop = f.get("properties", {}) or {}
            headline = prop.get("headline") or prop.get("event") or "Alert"
            onset = prop.get("onset") or ""
            ends = prop.get("ends") or ""
            when = f"{onset} → {ends}".strip(" →")
            desc = prop.get("description") or ""
            if len(desc) > 350:
                desc = desc[:350].rstrip() + "…"
            items.append({"headline": headline, "when": when or "—", "desc": desc})
    except Exception:
        pass
    return items


import os
import json

RF_STATE_PATH = os.path.join(os.path.dirname(__file__), "rf_state.json")

def _rf_load_state() -> None:
    try:
        with open(RF_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            RF_CACHE["wifi"] = data.get("wifi", []) or []
            RF_CACHE["wifi_note"] = data.get("wifi_note", "—")
            RF_CACHE["ble"] = data.get("ble", []) or []
            RF_CACHE["ble_note"] = data.get("ble_note", "—")
            RF_CACHE["last_scan"] = data.get("last_scan", "—")
    except Exception:
        # No saved file yet (or corrupted) -> keep defaults
        pass

def _rf_save_state() -> None:
    try:
        data = {
            "wifi": RF_CACHE.get("wifi", []) or [],
            "wifi_note": RF_CACHE.get("wifi_note", "—"),
            "ble": RF_CACHE.get("ble", []) or [],
            "ble_note": RF_CACHE.get("ble_note", "—"),
            "last_scan": RF_CACHE.get("last_scan", "—"),
        }
        with open(RF_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


RF_CACHE = {
    "wifi": [],
    "wifi_note": "—",
    "ble": [],
    "ble_note": "—",
    "last_scan": "—",
}


@app.get("/")
def home():
    ctx = _safe_get_weather_summary()
    ctx.update(_network_summary())

    # RF summary (load saved scan if cache is empty)
    try:
        if RF_CACHE.get("last_scan","—") == "—" and (not RF_CACHE.get("wifi")) and (not RF_CACHE.get("ble")):
            _rf_load_state()
    except Exception:
        pass

    ctx["rf_wifi_count"] = str(len(RF_CACHE.get("wifi", []) or []))
    ctx["rf_ble_count"] = str(len(RF_CACHE.get("ble", []) or []))
    ctx["rf_last_scan"] = RF_CACHE.get("last_scan", "—") or "—"
# Load panel settings
    panel_settings = settings.load_settings()
    ctx.update(panel_settings)
    return render_template_string(HOME_HTML, **ctx)
@app.get("/weather")
def weather_page():
    ctx = _safe_get_weather_summary()
    hourly_rows = _safe_hourly_rows(12)
    alerts = _safe_alerts(5)
    
    # Storm proximity banner (from alerts.db)
    storm_banner = None
    try:
        import alerts_db
        alerts_db.init_db()
        active = alerts_db.list_alerts(active_only=True, limit=200)
        prox = [a for a in active if str(a.get("key","")).startswith("wxprox:")]
        if prox:
            # show the newest proximity alert title
            prox.sort(key=lambda x: int(x.get("ts", 0)), reverse=True)
            storm_banner = prox[0].get("title") or "Storm nearby"
    except Exception:
        storm_banner = None
    # Get dynamic radar station
    try:
        points = weather_client.get_points()
        radar_station = points.get("properties", {}).get("radarStation", "KDDC")
    except Exception:
        radar_station = "KDDC"

    return render_template_string(
        WEATHER_HTML,
        storm_banner=storm_banner,
        radar_station=radar_station,
         **ctx, hourly_rows=hourly_rows, alerts=alerts,
        tomorrow_periods=_safe_tomorrow_periods())

@app.get("/network")
def network_page():
    cfg_devices = devices_store.load_devices()
    status_rows = {d["ip"]: d for d in network_read.get_latest_status()}

    cards = []
    for d in cfg_devices:
        name = d.get("name", "Unknown")
        ip = d.get("ip", "")
        dtype = d.get("type", "")

        st = status_rows.get(ip)
        if st:
            is_up = bool(int(st.get("is_up", 0)))
            status = "UP" if is_up else "DOWN"
            last_seen = _fmt_ts(st.get("last_seen_ts"))
        else:
            status = "UNKNOWN"
            last_seen = "—"

        services_raw = service_read.get_services_for_ip(ip) if ip else []
        services = [{"name": s.get("service_name", "svc"), "is_up": bool(int(s.get("is_up", 0)))} for s in services_raw]

        cards.append({"name": name, "ip": ip, "type": dtype, "status": status, "last_seen": last_seen, "services": services})

    return render_template_string(NETWORK_HTML, devices=cards)


@app.get("/network/manage")
def manage_devices():
    devices = devices_store.load_devices()
    rows = []
    for d in devices:
        rows.append({
            "name": d.get("name", ""),
            "ip": d.get("ip", ""),
            "type": d.get("type", ""),
            "svc_count": len(d.get("services", []) or []),
        })
    return render_template_string(MANAGE_HTML, devices=rows)


@app.route("/network/device/new", methods=["GET", "POST"])
def device_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        ip = request.form.get("ip", "").strip()
        dtype = request.form.get("type", "").strip()
        services_json = request.form.get("services_json", "")

        try:
            services = _parse_services_json(services_json)
        except ValueError as e:
            dev = {"name": name, "ip": ip, "type": dtype}
            return render_template_string(DEVICE_FORM_HTML, title="Add Device", dev=dev, services_list_json=services_json, error=str(e))

        devices_store.add_device({"name": name, "ip": ip, "type": dtype, "services": services})
        return redirect(url_for("manage_devices"))

    dev = {"name": "", "ip": "", "type": ""}
    return render_template_string(DEVICE_FORM_HTML, title="Add Device", dev=dev, services_list_json="[]", error="")


@app.route("/network/device/<int:idx>/edit", methods=["GET", "POST"])
def device_edit(idx: int):
    dev0 = devices_store.get_device(idx)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        ip = request.form.get("ip", "").strip()
        dtype = request.form.get("type", "").strip()
        services_json = request.form.get("services_json", "")

        try:
            services = _parse_services_json(services_json)
        except ValueError as e:
            show = {"name": name, "ip": ip, "type": dtype}
            return render_template_string(DEVICE_FORM_HTML, title="Edit Device", dev=show, services_list_json=services_json, error=str(e))

        devices_store.update_device(idx, {"name": name, "ip": ip, "type": dtype, "services": services})
        return redirect(url_for("manage_devices"))

    import json
    services_json = json.dumps(dev0.get("services", []) or [], indent=2)
    show = {"name": dev0.get("name", ""), "ip": dev0.get("ip", ""), "type": dev0.get("type", "")}
    return render_template_string(DEVICE_FORM_HTML, title="Edit Device", dev=show, services_list_json=services_json, error="")


@app.route("/network/device/<int:idx>/delete", methods=["GET", "POST"])
def device_delete(idx: int):
    dev = devices_store.get_device(idx)
    if request.method == "POST":
        devices_store.delete_device(idx)
        return redirect(url_for("manage_devices"))
    show = {"name": dev.get("name", ""), "ip": dev.get("ip", ""), "type": dev.get("type", "")}
    return render_template_string(DELETE_HTML, dev=show)




@app.get("/rf")
def rf_page():
    # Load last scan from disk (survives restarts)
    if RF_CACHE.get("last_scan","—") == "—" and (not RF_CACHE.get("wifi")) and (not RF_CACHE.get("ble")):
        _rf_load_state()
    return render_template_string(
        RF_HTML,
        wifi=RF_CACHE["wifi"],
        wifi_count=len(RF_CACHE["wifi"]),
        wifi_note=RF_CACHE["wifi_note"],
        ble=RF_CACHE["ble"],
        ble_rows=RF_CACHE["ble"],
        ble_count=len(RF_CACHE["ble"]),
        ble_note=RF_CACHE["ble_note"],
        last_scan=RF_CACHE["last_scan"],
    )


@app.get("/rf/scan")
def rf_scan_now():
    wifi, wifi_note = rf_scan.scan_wifi()
    ble, ble_note = rf_scan.scan_ble()

    wifi_rows = []
    for n in wifi:
        wifi_rows.append({
            "ssid": n.get("ssid", "—"),
            "signal": n.get("signal", "—"),
            "security": n.get("security", "—"),
        })

    RF_CACHE["wifi"] = wifi_rows
    RF_CACHE["wifi_note"] = wifi_note
    ble_rows = []
    for b in (ble or []):
        if isinstance(b, dict):
            ble_rows.append({"mac": b.get("mac","—"), "name": b.get("name","—")})
    RF_CACHE["ble"] = ble_rows
    RF_CACHE["ble_note"] = ble_note

    import time
    RF_CACHE["last_scan"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _rf_save_state()


    script_root = request.environ.get("SCRIPT_NAME", "")
    return redirect(url_for("rf_page"))


@app.get("/events")
def events_page():
    try:
        alerts_db.init_db()
    except Exception:
        pass

    import time
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    active = alerts_db.list_alerts(active_only=True, limit=50)
    recent = alerts_db.list_alerts(active_only=False, limit=100)

    def local_ts(ts: int) -> str:
        try:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ts)))
        except Exception:
            return "—"

    for a in active:
        a["ts_local"] = local_ts(a.get("ts", 0))
    for r in recent:
        r["ts_local"] = local_ts(r.get("ts", 0))

    return render_template_string(
        EVENTS_HTML,
        active=active,
        recent=recent,
        active_count=str(len(active)),
        updated=now,
    )

# ============================
# System controls (behind nginx)
# ============================

@app.route("/system/")
def system_menu():
    return """
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>System</title>
      <style>
        body{font-family:system-ui,Segoe UI,Roboto,Arial; padding:18px; background:#0f1115; color:#e7e9ee;}
        a,button{display:block; width:100%; padding:18px; margin:12px 0; font-size:20px; border-radius:14px;
                 border:1px solid #2a3142; background:#1b2231; color:#e7e9ee; text-decoration:none; font-weight:800;}
        .danger{background:rgba(255,77,77,0.12); border-color:rgba(255,77,77,0.35);}
        .muted{color:#a8b0c2; font-size:14px;}
      </style>
    </head>
    <body>
      <a href="/" style="position:fixed;top:12px;left:12px;width:auto;padding:10px 14px;border-radius:12px;">🏠 Apps</a>
      <h1 style="margin-top:58px;">System</h1>
      <div class="muted">These buttons control services on this Pi.</div>

      <form method="post" action="/system/restart">
        <button type="submit">Restart Apps</button>
      </form>

      <form method="post" action="/system/reboot">
        <button class="danger" type="submit">Reboot Pi</button>
      </form>
    </body>
    </html>
    """

@app.route("/system/restart", methods=["POST"])
def system_restart():
    subprocess.run(["/usr/bin/sudo", "/bin/systemctl", "restart", "kitchen.service"], check=False)
    subprocess.run(["/usr/bin/sudo", "/bin/systemctl", "restart", "infopanel.service"], check=False)
    return "<html><body><h1>Apps restarting...</h1><p>Refresh in 5 seconds.</p><script>setTimeout(()=>location.href='/',5000)</script></body></html>"

@app.route("/system/reboot", methods=["POST"])
def system_reboot():
    subprocess.run(["/usr/bin/sudo", "/sbin/reboot"], check=False)
    return "<html><body><h1>Rebooting Pi...</h1><p>This will take about 30 seconds.</p></body></html>"

#@app.get("/settings")
#def settings_page():
#    current_settings = settings.load_settings()
#    return render_template_string(SETTINGS_HTML, **current_settings)

#@app.post("/settings/update")
#def settings_update():
#    current_settings = settings.load_settings()
    
    # Update settings from form checkboxes
#    # Update ZIP code if changed
    new_zip = request.form.get("weather_zip", "").strip()
    if new_zip and new_zip.isdigit() and len(new_zip) == 5:
        import json as _json
        cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
        try:
            with open(cfg_path, "r") as f:
                cfg = _json.load(f)
        except Exception:
            cfg = {}
        cfg.setdefault("weather", {})["zip"] = new_zip
        with open(cfg_path, "w") as f:
            _json.dump(cfg, f, indent=2)
        # Clear points cache so new ZIP takes effect immediately
        import glob
        for old_cache in glob.glob(os.path.join(os.path.dirname(__file__), "data_cache", "points_*.json")):
            try:
                os.remove(old_cache)
            except Exception:
                pass
        for old_cache in glob.glob(os.path.join(os.path.dirname(__file__), "data_cache", "zip_*.json")):
            try:
                os.remove(old_cache)
            except Exception:
                pass

    current_settings["weather_enabled"] = request.form.get("weather_enabled") == "on"
#    current_settings["rf_enabled"] = request.form.get("rf_enabled") == "on"
#    current_settings["network_enabled"] = request.form.get("network_enabled") == "on"
#    current_settings["alerts_enabled"] = request.form.get("alerts_enabled") == "on"
    
#    settings.save_settings(current_settings)
#    return redirect(url_for("settings_page"))

@app.get("/settings")
def settings_page():
    current_settings = settings.load_settings()
    current_settings["weather_zip"] = weather_client.get_weather_zip()
    return render_template_string(SETTINGS_HTML, **current_settings)

@app.post("/settings/update")
def settings_update():
    current_settings = settings.load_settings()

    # Save ZIP code if changed
    new_zip = request.form.get('weather_zip', '').strip()
    if new_zip and new_zip.isdigit() and len(new_zip) == 5:
        import json as _json, glob
        cfg_path = os.path.join(os.path.dirname(__file__), 'config.json')
        try:
            with open(cfg_path, 'r') as f:
                cfg = _json.load(f)
        except Exception:
            cfg = {}
        cfg.setdefault('weather', {})['zip'] = new_zip
        # Also update lat/lon for storm proximity
        try:
            lat, lon = weather_client.resolve_zip_to_latlon(new_zip)
            cfg.setdefault('location', {})['lat'] = lat
            cfg.setdefault('location', {})['lon'] = lon
        except Exception:
            pass
        with open(cfg_path, 'w') as f:
            _json.dump(cfg, f, indent=2)
        for old_cache in glob.glob(os.path.join(os.path.dirname(__file__), 'data_cache', 'points_*.json')):
            try: os.remove(old_cache)
            except Exception: pass
        for old_cache in glob.glob(os.path.join(os.path.dirname(__file__), 'data_cache', 'zip_*.json')):
            try: os.remove(old_cache)
            except Exception: pass
        for old_cache in glob.glob(os.path.join(os.path.dirname(__file__), 'data_cache', 'hourly_*.json')):
            try: os.remove(old_cache)
            except Exception: pass
        for old_cache in glob.glob(os.path.join(os.path.dirname(__file__), 'data_cache', 'forecast_*.json')):
            try: os.remove(old_cache)
            except Exception: pass
        for old_cache in glob.glob(os.path.join(os.path.dirname(__file__), 'data_cache', 'alerts_*.json')):
            try: os.remove(old_cache)
            except Exception: pass

    
    # Update settings from form checkboxes
    current_settings["weather_enabled"] = request.form.get("weather_enabled") == "on"
    current_settings["rf_enabled"] = request.form.get("rf_enabled") == "on"
    current_settings["network_enabled"] = request.form.get("network_enabled") == "on"
    current_settings["alerts_enabled"] = request.form.get("alerts_enabled") == "on"
    
    settings.save_settings(current_settings)
    return redirect("/")  # Changed from settings_page to home
