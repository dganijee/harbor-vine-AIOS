#!/bin/bash
# Harbor & Vine Realty FluentOS — VPS Deployment Setup
# Run this on the VPS after cloning the repo.
#
# Usage: bash deploy/setup.sh dashboard.harbor-vine.com
#
# What this does:
# 1. Installs Caddy (reverse proxy + auto-SSL)
# 2. Configures the domain with basic auth for all 15 users
# 3. Creates a systemd service for the Flask server
# 4. Sets up daily auto-update cron job
# 5. Sets up daily Snowflake sync cron job

set -e

DOMAIN="${1:-YOUR_DOMAIN}"
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_USER="$(whoami)"

echo "============================================"
echo "  Harbor & Vine Realty FluentOS — VPS Setup"
echo "  Domain: $DOMAIN"
echo "  App dir: $APP_DIR"
echo "============================================"

# 1. Install Caddy
if ! command -v caddy &> /dev/null; then
    echo "[1/6] Installing Caddy..."
    sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
    sudo apt update && sudo apt install -y caddy
else
    echo "[1/6] Caddy already installed"
fi

# 2. Install Python deps
echo "[2/6] Installing Python dependencies..."
cd "$APP_DIR"
pip install -r requirements.txt 2>/dev/null || pip3 install flask flask-cors python-dotenv requests snowflake-connector-python

# 3. Initialize database
echo "[3/6] Initializing database..."
python3 engine/data_os.py || python engine/data_os.py

# 4. Set up passwords and Caddy config
echo "[4/6] Setting up Caddy..."
sed -i "s/YOUR_DOMAIN/$DOMAIN/g" "$APP_DIR/deploy/Caddyfile"
sudo cp "$APP_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile
sudo mkdir -p /var/log/caddy

echo ""
echo "  Generate passwords for each user:"
echo "    caddy hash-password"
echo "  Then edit /etc/caddy/Caddyfile — replace each REPLACE_WITH_HASH"
echo ""

# 5. Create systemd service for Flask
echo "[5/6] Creating systemd service..."
sudo tee /etc/systemd/system/harbor-vine-aios.service > /dev/null <<UNIT
[Unit]
Description=Harbor & Vine Realty FluentOS Dashboard
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$(which python3 || which python) scripts/server.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable harbor-vine-aios
sudo systemctl start harbor-vine-aios

# 6. Set up cron jobs
echo "[6/6] Setting up scheduled tasks..."

# Auto-update at 4:00 AM
(crontab -l 2>/dev/null; echo "0 4 * * * cd $APP_DIR && python3 scripts/auto_update.py >> data/update.log 2>&1") | sort -u | crontab -

# Morning brief at 7:25 AM CT (brokerage automations run, then brief sends at 7:30)
(crontab -l 2>/dev/null; echo "25 7 * * * cd $APP_DIR && python3 automations/stalled_deal_monitor.py >> data/automation.log 2>&1") | sort -u | crontab -
(crontab -l 2>/dev/null; echo "26 7 * * * cd $APP_DIR && python3 automations/showing_conflict_monitor.py >> data/automation.log 2>&1") | sort -u | crontab -
(crontab -l 2>/dev/null; echo "27 7 * * * cd $APP_DIR && python3 automations/commission_dispute_monitor.py >> data/automation.log 2>&1") | sort -u | crontab -
(crontab -l 2>/dev/null; echo "28 7 * * * cd $APP_DIR && python3 automations/lead_followup_monitor.py >> data/automation.log 2>&1") | sort -u | crontab -
(crontab -l 2>/dev/null; echo "29 7 * * * cd $APP_DIR && python3 automations/meeting_brief.py >> data/automation.log 2>&1") | sort -u | crontab -
(crontab -l 2>/dev/null; echo "30 7 * * * cd $APP_DIR && python3 automations/morning_brief.py >> data/automation.log 2>&1") | sort -u | crontab -

# Start Caddy
sudo systemctl restart caddy

echo ""
echo "============================================"
echo "  Setup complete!"
echo ""
echo "  Dashboard: https://$DOMAIN"
echo "  Service:   sudo systemctl status harbor-vine-aios"
echo "  Logs:      sudo journalctl -u harbor-vine-aios -f"
echo ""
echo "  Cron jobs installed:"
echo "    4:00 AM  — Auto-update from GitHub"
echo "    7:25 AM  — Automation monitors run"
echo "    7:30 AM  — Morning brief sent to Marisol Trent + Devin Okafor"
echo ""
echo "  Next steps:"
echo "  1. Point DNS A record for $DOMAIN to this server's IP"
echo "  2. Run 'caddy hash-password' for each user (Marisol Trent, Devin Okafor, etc.)"
echo "  3. Edit /etc/caddy/Caddyfile with password hashes"
echo "  4. sudo systemctl reload caddy"
echo "  5. Fill in .env with Snowflake, NetSuite, MS365, Telegram creds"
echo "============================================"
