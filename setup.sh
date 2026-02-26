#!/usr/bin/env bash
# =============================================================================
# StockPi-InfoPanel Setup Script
# Run from the root of the cloned repo:
#   chmod +x setup.sh && sudo ./setup.sh
# =============================================================================

set -e

# --- Colours -----------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# --- Must run as root --------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
  error "Please run with sudo: sudo ./setup.sh"
fi

# --- Detect the real user (person who called sudo) ---------------------------
REAL_USER="${SUDO_USER:-$(logname 2>/dev/null || echo pi)}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)

echo ""
echo -e "${BOLD}============================================${NC}"
echo -e "${BOLD}   StockPi-InfoPanel Setup${NC}"
echo -e "${BOLD}============================================${NC}"
echo ""

# --- Detect repo root (where this script lives) ------------------------------
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
info "Repo directory : $REPO_DIR"
info "Installing for user: $REAL_USER (home: $REAL_HOME)"
echo ""

# =============================================================================
# 1. COLLECT CONFIGURATION
# =============================================================================
echo -e "${BOLD}--- Configuration ---${NC}"

# ZIP code
while true; do
  read -rp "Enter your ZIP code (5 digits): " ZIP_CODE
  if [[ "$ZIP_CODE" =~ ^[0-9]{5}$ ]]; then
    break
  fi
  warn "Please enter a valid 5-digit ZIP code."
done

# Kiosk mode
read -rp "Set up Chromium kiosk mode (auto-launch browser on boot)? [y/N]: " KIOSK_ANSWER
SETUP_KIOSK=false
[[ "$KIOSK_ANSWER" =~ ^[Yy]$ ]] && SETUP_KIOSK=true

echo ""

# =============================================================================
# 2. INSTALL SYSTEM PACKAGES
# =============================================================================
echo -e "${BOLD}--- Installing system packages ---${NC}"
apt-get update -qq
apt-get install -y \
  python3 python3-pip python3-venv \
  nginx \
  bluetooth bluez \
  iputils-ping \
  openssl \
  > /dev/null 2>&1
success "System packages installed."

if $SETUP_KIOSK; then
  apt-get install -y chromium-browser > /dev/null 2>&1 || \
  apt-get install -y chromium > /dev/null 2>&1 || \
  warn "Could not install chromium — install it manually if needed."
fi

# =============================================================================
# 3. CREATE config.json (if it doesn't exist)
# =============================================================================
echo -e "${BOLD}--- Creating config.json ---${NC}"
CONFIG_PATH="$REPO_DIR/homepanel/config.json"

if [[ -f "$CONFIG_PATH" ]]; then
  warn "config.json already exists — skipping. Edit it manually if needed."
else
  cat > "$CONFIG_PATH" <<EOF
{
  "weather": {
    "zip": "$ZIP_CODE"
  },
  "location": {
    "lat": null,
    "lon": null
  }
}
EOF
  chown "$REAL_USER":"$REAL_USER" "$CONFIG_PATH"
  success "config.json created with ZIP $ZIP_CODE."
fi

# =============================================================================
# 4. CREATE devices.json (if it doesn't exist)
# =============================================================================
echo -e "${BOLD}--- Creating devices.json ---${NC}"
DEVICES_PATH="$REPO_DIR/homepanel/devices.json"

if [[ -f "$DEVICES_PATH" ]]; then
  warn "devices.json already exists — skipping."
else
  echo '{"devices": []}' > "$DEVICES_PATH"
  chown "$REAL_USER":"$REAL_USER" "$DEVICES_PATH"
  success "devices.json created (empty device list)."
fi

# =============================================================================
# 5. CREATE data_cache DIRECTORY
# =============================================================================
CACHE_DIR="$REPO_DIR/homepanel/data_cache"
mkdir -p "$CACHE_DIR"
chown -R "$REAL_USER":"$REAL_USER" "$CACHE_DIR"
success "data_cache directory ready."

# =============================================================================
# 6. PYTHON VIRTUAL ENVIRONMENT + DEPENDENCIES
# =============================================================================
echo -e "${BOLD}--- Setting up Python virtual environment ---${NC}"
VENV_DIR="$REPO_DIR/homepanel/venv"

if [[ -d "$VENV_DIR" ]]; then
  warn "venv already exists — skipping creation."
else
  sudo -u "$REAL_USER" python3 -m venv "$VENV_DIR"
  success "venv created."
fi

info "Installing Python dependencies (this may take a minute)..."
sudo -u "$REAL_USER" "$VENV_DIR/bin/pip" install --upgrade pip --quiet
sudo -u "$REAL_USER" "$VENV_DIR/bin/pip" install -r "$REPO_DIR/homepanel/requirements.txt" --quiet
success "Python dependencies installed."

# =============================================================================
# 7. NGINX
# =============================================================================
echo -e "${BOLD}--- Configuring nginx ---${NC}"

mkdir -p /var/www/launcher
cp "$REPO_DIR/launcher/index.html" /var/www/launcher/index.html
success "Launcher HTML copied to /var/www/launcher."

cp "$REPO_DIR/nginx/launcher.conf" /etc/nginx/sites-available/stockpi.conf
ln -sf /etc/nginx/sites-available/stockpi.conf /etc/nginx/sites-enabled/stockpi.conf
rm -f /etc/nginx/sites-enabled/default

nginx -t > /dev/null 2>&1 && systemctl restart nginx
success "nginx configured and restarted."

# =============================================================================
# 8. SYSTEMD SERVICE — infopanel
# =============================================================================
echo -e "${BOLD}--- Installing systemd services ---${NC}"

# Generate a unique random secret key for Flask on this device
FLASK_SECRET=$(openssl rand -hex 32)
info "Generated unique Flask secret key."

SERVICE_SRC="$REPO_DIR/systemd/infopanel.service"
SERVICE_DEST="/etc/systemd/system/infopanel.service"

# Patch the service file on-the-fly:
#   - Replace hardcoded user with the real user
#   - Replace hardcoded paths with the actual repo path
#   - Replace the placeholder Flask secret with the generated one
sed \
  -e "s|User=kinv|User=$REAL_USER|g" \
  -e "s|/home/kinv/homepanel|$REPO_DIR/homepanel|g" \
  -e "s|FLASK_SECRET_KEY=change-me-to-a-random-secret|FLASK_SECRET_KEY=$FLASK_SECRET|g" \
  "$SERVICE_SRC" > "$SERVICE_DEST"

systemctl daemon-reload
systemctl enable infopanel.service
systemctl restart infopanel.service
success "infopanel.service installed and started (with unique secret key)."

# =============================================================================
# 9. KIOSK MODE (optional)
# =============================================================================
if $SETUP_KIOSK; then
  echo -e "${BOLD}--- Setting up kiosk autostart ---${NC}"
  AUTOSTART_DIR="$REAL_HOME/.config/autostart"
  mkdir -p "$AUTOSTART_DIR"
  cp "$REPO_DIR/systemd/kitchen-kiosk.desktop" "$AUTOSTART_DIR/stockpi-kiosk.desktop"
  chown -R "$REAL_USER":"$REAL_USER" "$AUTOSTART_DIR"
  success "Kiosk autostart configured. Will launch on next desktop login."
fi

# =============================================================================
# DONE
# =============================================================================
echo ""
echo -e "${BOLD}============================================${NC}"
echo -e "${GREEN}${BOLD}   Setup complete!${NC}"
echo -e "${BOLD}============================================${NC}"
echo ""

LOCAL_IP=$(hostname -I | awk '{print $1}')
echo -e "  Open in a browser: ${CYAN}http://${LOCAL_IP}${NC}"
echo -e "  Check service status: ${CYAN}sudo systemctl status infopanel.service${NC}"
echo -e "  View logs: ${CYAN}sudo journalctl -u infopanel.service -f${NC}"
echo ""
echo -e "  To change your ZIP code later, visit:"
echo -e "  ${CYAN}http://${LOCAL_IP}/panel/settings${NC}"
echo ""
