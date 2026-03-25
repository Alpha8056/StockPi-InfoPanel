# StockPi-InfoPanel To-Do List

## ✅ Completed
- Tomorrow's forecast card on weather page
- Card-level feature flags (weather, RF, network, alerts) — toggle in info panel settings
- Settings page built into info panel side
- Fixed broken WEATHER_HTML structure (duplicate body tags)
- Launcher Restart Apps, Update, and Reboot Pi buttons — wired up with confirmation dialogs
- Settings button on launcher page (top-right, links to /panel/settings)
- Auto-boot infopanel on reboot — setup.sh runs `systemctl enable infopanel.service`
- ZIP code editable in Settings page (/panel/settings) — also set during install via setup.sh
- Weather card section ordering — priority 1–5 or hidden, configurable in Weather Section Settings
- Launcher-level feature flags** — show/hide Kitchen Inventory and/or Info Panel buttons based on config so you can run one app without the other appearing. Also added an option for the Weather Data to be on the launcher page
- Card layout customization** — ability to reorder or hide the cards on the info panel home screen (weather, RF, network, alerts).


---

## 🔧 In Progress / Next Up

### Launcher Page


### Info Panel



---

## 💡 Future Ideas
- BLE scan results on RF page (or remove RF/BLE/Network pages entirely — undecided)

---

## 📁 Project Structure
- `homepanel/` — Info Panel Flask app (port 5100)
- `kitchen_inventory/` — StockPi Kitchen Inventory Flask app (port 5000)
- `launcher/` — Static home screen HTML served by nginx
- `nginx/launcher.conf` — nginx config routing `/kitchen/`, `/panel/`, `/system/`
- `systemd/` — Service files for both apps
