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

# Jelenlegi branch meghatározása
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ -z "$CURRENT_BRANCH" ]; then
    CURRENT_BRANCH="main"  # Alapértelmezett
fi

echo "[UPDATE] Jelenlegi branch: $CURRENT_BRANCH"

# Git pull
echo "[UPDATE] Git pull futtatása..."
git pull origin "$CURRENT_BRANCH" || {
    echo "[UPDATE] HIBA: Git pull sikertelen!"
    exit 1
}

# Függőségek frissítése
if [ -f "requirements.txt" ]; then
    echo "[UPDATE] Függőségek frissítése..."
    if [ -d "venv" ]; then
        source venv/bin/activate
        pip install -r requirements.txt --quiet
        PYTHON_CMD="venv/bin/python3"
    else
        pip3 install -r requirements.txt --quiet
        PYTHON_CMD="python3"
    fi
else
    # Ha nincs requirements.txt, próbáljuk meg megtalálni a Python-t
    if [ -d "venv" ]; then
        PYTHON_CMD="venv/bin/python3"
    else
        PYTHON_CMD="python3"
    fi
fi

# Adatbázis migráció (adatvesztés nélkül)
echo "[UPDATE] Adatbázis migráció futtatása..."
if [ -f "app/database_init.py" ]; then
    if [ -d "venv" ]; then
        source venv/bin/activate
    fi
    $PYTHON_CMD -m app.database_init || {
        echo "[UPDATE] ⚠️  Figyelmeztetés: Adatbázis migráció során hiba történt, de folytatjuk..."
    }
    echo "[UPDATE] ✓ Adatbázis migráció befejezve"
else
    echo "[UPDATE] ⚠️  Figyelmeztetés: database_init.py nem található, adatbázis migráció kihagyva"
fi

# Docker image build
echo "[UPDATE] Docker image build futtatása..."
if [ -f "docker/build-image.sh" ]; then
    chmod +x docker/build-image.sh
    docker/build-image.sh latest || {
        echo "[UPDATE] ⚠️  Figyelmeztetés: Docker build során hiba történt, de folytatjuk..."
    }
    echo "[UPDATE] ✓ Docker image build befejezve"
else
    echo "[UPDATE] ⚠️  Figyelmeztetés: build-image.sh nem található, Docker build kihagyva"
fi

# Cron job-ok automatikus beállítása
echo "[UPDATE] Cron job-ok ellenőrzése és beállítása..."
if [ -f "cron/setup_cron_jobs.sh" ]; then
    chmod +x cron/setup_cron_jobs.sh
    bash cron/setup_cron_jobs.sh "$PROJECT_DIR" "$PYTHON_CMD" || {
        echo "[UPDATE] ⚠️  Figyelmeztetés: Cron job beállítás során hiba történt, de folytatjuk..."
    }
    echo "[UPDATE] ✓ Cron job-ok ellenőrzése befejezve"
else
    echo "[UPDATE] ⚠️  Figyelmeztetés: setup_cron_jobs.sh nem található, cron job beállítás kihagyva"
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

