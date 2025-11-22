#!/bin/bash

# ZedinArkManager Systemd Service Installer
# Ez a script létrehozza a systemd service fájlt

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICE_NAME="zedinarkmanager"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Felhasználó meghatározása (aki futtatja a scriptet)
CURRENT_USER=$(whoami)
CURRENT_GROUP=$(id -gn)

echo "[INSTALL] Systemd service telepítése..."

# Service fájl létrehozása
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=ZedinArkManager - Game Server Management System
After=network.target mysql.service

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_GROUP
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$PROJECT_DIR/venv/bin/python3 $PROJECT_DIR/run.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Service fájl jogosultságok beállítása
sudo chmod 644 "$SERVICE_FILE"

# Systemd újratöltése
sudo systemctl daemon-reload

# Service engedélyezése
sudo systemctl enable "$SERVICE_NAME"

echo "[INSTALL] ✅ Service telepítve: $SERVICE_NAME"
echo "[INSTALL] Service indítása: sudo systemctl start $SERVICE_NAME"
echo "[INSTALL] Service státusz: sudo systemctl status $SERVICE_NAME"
echo "[INSTALL] Service naplók: sudo journalctl -u $SERVICE_NAME -f"

