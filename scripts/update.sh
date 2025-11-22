#!/bin/bash

# ZedinArkManager Update Script
# Ez a script frissíti a managert git-ről és újraindítja a service-t

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICE_NAME="zedinarkmanager"
UPDATE_FLAG="$PROJECT_DIR/.updating"

# Trap: ha a script megszakad, töröljük a flagot
trap 'rm -f "$UPDATE_FLAG"; exit 1' INT TERM EXIT

echo "[UPDATE] Frissítés kezdése..."

# Váltás a projekt könyvtárába
cd "$PROJECT_DIR"

# Git pull
echo "[UPDATE] Git pull futtatása..."
git pull origin main || {
    echo "[UPDATE] HIBA: Git pull sikertelen!"
    exit 1
}

# Függőségek frissítése
if [ -f "requirements.txt" ]; then
    echo "[UPDATE] Függőségek frissítése..."
    if [ -d "venv" ]; then
        source venv/bin/activate
        pip install -r requirements.txt --quiet
    else
        pip3 install -r requirements.txt --quiet
    fi
fi

# Service újraindítása
echo "[UPDATE] Service újraindítása..."
if systemctl is-active --quiet "$SERVICE_NAME"; then
    systemctl restart "$SERVICE_NAME"
    echo "[UPDATE] Service újraindítva."
else
    echo "[UPDATE] Service nem fut, indítás..."
    systemctl start "$SERVICE_NAME"
fi

# Várakozás, hogy a service elinduljon
sleep 2

# Ellenőrzés, hogy a service fut-e
if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "[UPDATE] ✅ Frissítés sikeres! Service fut."
    # Flag törlése
    rm -f "$UPDATE_FLAG"
    trap - INT TERM EXIT
    exit 0
else
    echo "[UPDATE] ❌ HIBA: Service nem indult el!"
    systemctl status "$SERVICE_NAME"
    # Flag törlése hiba esetén is
    rm -f "$UPDATE_FLAG"
    trap - INT TERM EXIT
    exit 1
fi

