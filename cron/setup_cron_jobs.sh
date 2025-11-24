#!/bin/bash

# Cron job-ok automatikus beállítása
# Ez a script ellenőrzi és beállítja a szükséges cron job-okat

set -e

PROJECT_DIR="$1"
PYTHON_CMD="$2"

if [ -z "$PROJECT_DIR" ]; then
    echo "[CRON SETUP] HIBA: Projekt könyvtár nincs megadva!"
    exit 1
fi

if [ -z "$PYTHON_CMD" ]; then
    # Alapértelmezett Python parancs meghatározása
    if [ -f "$PROJECT_DIR/venv/bin/python3" ]; then
        PYTHON_CMD="$PROJECT_DIR/venv/bin/python3"
    else
        PYTHON_CMD="python3"
    fi
fi

echo "[CRON SETUP] Projekt könyvtár: $PROJECT_DIR"
echo "[CRON SETUP] Python parancs: $PYTHON_CMD"

# Cron job-ok definíciói
declare -A CRON_JOBS
CRON_JOBS["check_token_expiry"]="0 0 * * * $PYTHON_CMD $PROJECT_DIR/cron/check_token_expiry.py"
CRON_JOBS["stop_expired_token_servers"]="*/30 * * * * $PYTHON_CMD $PROJECT_DIR/cron/stop_expired_token_servers.py"

# Jelenlegi crontab lekérése
CURRENT_CRON=$(crontab -l 2>/dev/null || echo "")

# Cron job-ok hozzáadása (ha még nincsenek benne)
for job_name in "${!CRON_JOBS[@]}"; do
    cron_line="${CRON_JOBS[$job_name]}"
    
    # Ellenőrizzük, hogy már benne van-e a crontab-ban
    if echo "$CURRENT_CRON" | grep -q "$job_name"; then
        echo "[CRON SETUP] ✓ '$job_name' cron job már be van állítva"
    else
        # Hozzáadjuk a crontab-hoz
        (crontab -l 2>/dev/null || echo ""; echo "$cron_line") | crontab -
        echo "[CRON SETUP] ✓ '$job_name' cron job hozzáadva"
    fi
done

echo "[CRON SETUP] ✅ Cron job-ok beállítása befejezve"
echo "[CRON SETUP] Jelenlegi cron job-ok:"
crontab -l | grep -E "(check_token_expiry|stop_expired_token_servers)" || echo "  (nincs találat)"

