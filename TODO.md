# StockPi-InfoPanel To-Do List

## ✅ Completed
- Tomorrow's forecast card on weather page
- Card-level feature flags (weather, RF, network, alerts) — toggle in info panel settings
- Settings page built into info panel side
- Fixed broken WEATHER_HTML structure (duplicate body tags)

---

## 🔧 In Progress / Next Up

### Launcher Page
- [ ] **Fix Restart Apps & Reboot Pi buttons** — currently link to `/system/restart` and `/system/reboot` but no backend exists to handle them. Need a small Flask `launcher_app.py` to process these.
- [ ] **Move Settings button to launcher page** — currently buried inside the info panel side (`/settings`). Should be accessible from the main home screen.
- [ ] **Launcher-level feature flags** — show/hide Kitchen Inventory and/or Info Panel buttons based on config so you can run one app without the other appearing.

### Info Panel
- [ ] **Auto-boot info panel on reboot** — `infopanel.service` exists but is not enabled. Run `sudo systemctl enable infopanel.service` to fix.
- [ ] **ZIP code setting in Settings page** — currently ZIP is hardcoded in `config.json`. Add a ZIP code input box in the settings UI so anyone who clones the repo can set their location without editing files manually.
- [ ] **Card layout customization** — ability to reorder or resize the cards on the info panel home screen (weather, RF, network, alerts).
- [ ] **Weather card layout customization** — choose which sections appear inside the weather page (radar, hourly table, tomorrow's forecast, alerts, storm proximity) and in what order.

---

## 💡 Future Ideas
- Next day weather forecast on home screen weather card summary (not just detail page)
- BLE scan results fully wired up on RF page
- Alerts/Events page: wire in active NWS alerts + storm proximity summary
- Alerts/Events page: wire in network/device down alerts

---

## 📁 Project Structure
- `homepanel/` — Info Panel Flask app (port 5100)
- `kitchen_inventory/` — StockPi Kitchen Inventory Flask app (port 5000)
- `launcher/` — Static home screen HTML served by nginx
- `nginx/launcher.conf` — nginx config routing `/kitchen/`, `/panel/`, `/system/`
- `systemd/` — Service files for both apps
