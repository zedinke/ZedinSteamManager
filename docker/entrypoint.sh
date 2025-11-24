#!/bin/bash
# ZedinArkManager - ARK Server Entrypoint Script

# set -e kikapcsolva, hogy jobban kezeljük a hibákat
set +e

ARK_SERVER_DIR="${ARK_SERVER_DIR:-/home/ai_developer/arkserver}"
STEAMCMD_DIR="${STEAMCMD_DIR:-/home/ai_developer/steamcmd}"
STEAMCMD_BIN="${STEAMCMD_DIR}/steamcmd.sh"
ARK_APP_ID="2430930"  # ARK Survival Ascended App ID

# Environment változók beolvasása
INSTANCE_NAME="${INSTANCE_NAME:-1}"
MAP_NAME="${MAP_NAME:-TheIsland}"
ASA_PORT="${ASA_PORT:-7777}"
QUERY_PORT="${QUERY_PORT:-27015}"
RCON_PORT="${RCON_PORT:-27020}"
SESSION_NAME="${SESSION_NAME:-ZedinArkServer}"
MAX_PLAYERS="${MAX_PLAYERS:-70}"
RCON_ENABLED="${RCON_ENABLED:-True}"
BATTLEEYE="${BATTLEEYE:-False}"
API="${API:-False}"
SERVER_ADMIN_PASSWORD="${SERVER_ADMIN_PASSWORD:-}"
SERVER_PASSWORD="${SERVER_PASSWORD:-}"
MOD_IDS="${MOD_IDS:-}"
CUSTOM_SERVER_ARGS="${CUSTOM_SERVER_ARGS:-}"
UPDATE_SERVER="${UPDATE_SERVER:-True}"

# Ellenőrizzük, hogy a szerverfájlok léteznek-e
# ARK: Survival Ascended jelenleg csak Windows-on támogatott, ezért Wine-t használunk
# Először próbáljuk meg a linux64/ mappában lévő binárist, majd a ShooterGame/Binaries/Linux/ mappát, végül a Windows binárist Wine-nal
# A Linux bináris lehet a linux64/ mappában vagy a ShooterGame/Binaries/Linux/ mappában
if [ -f "${ARK_SERVER_DIR}/linux64/ShooterGameServer" ]; then
    SERVER_BINARY="${ARK_SERVER_DIR}/linux64/ShooterGameServer"
    USE_WINE=false
elif [ -f "${ARK_SERVER_DIR}/ShooterGame/Binaries/Linux/ShooterGameServer" ]; then
    SERVER_BINARY="${ARK_SERVER_DIR}/ShooterGame/Binaries/Linux/ShooterGameServer"
    USE_WINE=false
elif [ -f "${ARK_SERVER_DIR}/ShooterGame/Binaries/Win64/ShooterGameServer.exe" ]; then
    SERVER_BINARY="${ARK_SERVER_DIR}/ShooterGame/Binaries/Win64/ShooterGameServer.exe"
    USE_WINE=true
else
    # Alapértelmezett: próbáljuk meg a linux64/ mappát
    SERVER_BINARY="${ARK_SERVER_DIR}/linux64/ShooterGameServer"
    USE_WINE=false
fi

# FONTOS: NE hozzuk létre a mappát itt! A manager már létrehozza megfelelő jogosultságokkal.
# Ha a szerver nincs telepítve és UPDATE_SERVER=True, akkor telepítjük
if [ ! -f "${SERVER_BINARY}" ] && [ "${UPDATE_SERVER}" = "True" ]; then
    echo "ARK szerver nincs telepítve. Telepítés indítása SteamCMD-vel..."
    
    # Ellenőrizzük, hogy a SteamCMD létezik-e és végrehajtható-e
    if [ ! -f "${STEAMCMD_BIN}" ]; then
        echo "HIBA: SteamCMD nem található: ${STEAMCMD_BIN}"
        echo "SteamCMD mappa tartalma:"
        ls -la "${STEAMCMD_DIR}" || echo "SteamCMD mappa nem létezik"
        exit 1
    fi
    
    if [ ! -x "${STEAMCMD_BIN}" ]; then
        echo "SteamCMD nem végrehajtható, jogosultságok beállítása..."
        chmod +x "${STEAMCMD_BIN}" || {
            echo "HIBA: Nem lehet végrehajthatóvá tenni a SteamCMD-t!"
            exit 1
        }
    fi
    
    # FONTOS: NE hozzuk létre és NE ellenőrizzük a mappát!
    # A manager már létrehozza megfelelő jogosultságokkal.
    # Csak használjuk, ha létezik.
    
    echo "SteamCMD futtatása..."
    echo "  - Install dir: ${ARK_SERVER_DIR}"
    echo "  - App ID: ${ARK_APP_ID}"
    
    # ARK szerver telepítése/frissítése
    # A SteamCMD hosszú ideig futhat, ezért timeout-ot nem állítunk
    "${STEAMCMD_BIN}" +force_install_dir "${ARK_SERVER_DIR}" \
        +login anonymous \
        +app_update ${ARK_APP_ID} validate \
        +quit
    
    STEAMCMD_EXIT=$?
    if [ ${STEAMCMD_EXIT} -ne 0 ]; then
        echo "HIBA: SteamCMD telepítés sikertelen (exit code: ${STEAMCMD_EXIT})"
        exit 1
    fi
    
    # Várakozás, hogy a fájlok leírásra kerüljenek
    sleep 2
    
    if [ ! -f "${SERVER_BINARY}" ]; then
        echo "HIBA: ARK szerver telepítése sikertelen! A bináris nem található: ${SERVER_BINARY}"
        echo "ARK_SERVER_DIR tartalma:"
        ls -la "${ARK_SERVER_DIR}" || echo "Mappa nem létezik"
        if [ -d "${ARK_SERVER_DIR}/ShooterGame" ]; then
            echo "ShooterGame mappa tartalma:"
            ls -la "${ARK_SERVER_DIR}/ShooterGame" || true
        fi
        exit 1
    fi
    
    echo "ARK szerver telepítve!"
fi

# Ha a szerverfájlok még mindig nem léteznek, hiba
if [ ! -f "${SERVER_BINARY}" ]; then
    echo "HIBA: ARK szerver bináris nem található: ${SERVER_BINARY}"
    echo "Ellenőrizd, hogy a szerverfájlok telepítve vannak-e a volume-on!"
    echo "ARK_SERVER_DIR: ${ARK_SERVER_DIR}"
    echo "Mappa tartalma:"
    ls -la "${ARK_SERVER_DIR}" || echo "Mappa nem létezik vagy nem elérhető"
    if [ -d "${ARK_SERVER_DIR}/ShooterGame" ]; then
        echo "ShooterGame mappa tartalma:"
        ls -la "${ARK_SERVER_DIR}/ShooterGame" || true
        if [ -d "${ARK_SERVER_DIR}/ShooterGame/Binaries" ]; then
            echo "Binaries mappa tartalma:"
            ls -la "${ARK_SERVER_DIR}/ShooterGame/Binaries" || true
            if [ -d "${ARK_SERVER_DIR}/ShooterGame/Binaries/Linux" ]; then
                echo "Linux mappa tartalma:"
                ls -la "${ARK_SERVER_DIR}/ShooterGame/Binaries/Linux" || true
            fi
            if [ -d "${ARK_SERVER_DIR}/ShooterGame/Binaries/Win64" ]; then
                echo "Win64 mappa tartalma:"
                ls -la "${ARK_SERVER_DIR}/ShooterGame/Binaries/Win64" || true
            fi
        fi
    fi
    exit 1
fi

# Szerver indítási parancs összeállítása
cd "${ARK_SERVER_DIR}" || {
    echo "HIBA: Nem lehet váltani a ${ARK_SERVER_DIR} mappába!"
    exit 1
}

echo "Jelenlegi mappa: $(pwd)"
echo "Szerver bináris létezik: $([ -f "${SERVER_BINARY}" ] && echo "IGEN" || echo "NEM")"

# Alap parancs
SERVER_ARGS=""

# Map
SERVER_ARGS="${SERVER_ARGS} ${MAP_NAME}"

# Listen flag (dedicated server)
SERVER_ARGS="${SERVER_ARGS} -listen"

# Portok
SERVER_ARGS="${SERVER_ARGS} -Port=${ASA_PORT}"
SERVER_ARGS="${SERVER_ARGS} -QueryPort=${QUERY_PORT}"

# RCON
if [ "${RCON_ENABLED}" = "True" ]; then
    SERVER_ARGS="${SERVER_ARGS} -RCONEnabled=True -RCONPort=${RCON_PORT}"
    if [ -n "${SERVER_ADMIN_PASSWORD}" ]; then
        SERVER_ARGS="${SERVER_ARGS} -ServerAdminPassword=${SERVER_ADMIN_PASSWORD}"
    fi
fi

# Session Name
SERVER_ARGS="${SERVER_ARGS} -SessionName=\"${SESSION_NAME}\""

# Max Players
SERVER_ARGS="${SERVER_ARGS} -MaxPlayers=${MAX_PLAYERS}"

# Server Password
if [ -n "${SERVER_PASSWORD}" ]; then
    SERVER_ARGS="${SERVER_ARGS} -ServerPassword=${SERVER_PASSWORD}"
fi

# BattleEye
if [ "${BATTLEEYE}" = "True" ]; then
    SERVER_ARGS="${SERVER_ARGS} -UseBattlEye"
fi

# Mods
if [ -n "${MOD_IDS}" ]; then
    SERVER_ARGS="${SERVER_ARGS} -ActiveMods=${MOD_IDS}"
fi

# Custom Server Args
if [ -n "${CUSTOM_SERVER_ARGS}" ]; then
    SERVER_ARGS="${SERVER_ARGS} ${CUSTOM_SERVER_ARGS}"
fi

# Szerver indítása
echo "=========================================="
echo "ZedinArkManager - ARK Server Starting"
echo "=========================================="
echo "Instance: ${INSTANCE_NAME}"
echo "Map: ${MAP_NAME}"
echo "Port: ${ASA_PORT}"
echo "Query Port: ${QUERY_PORT}"
echo "RCON Port: ${RCON_PORT}"
echo "Session: ${SESSION_NAME}"
echo "Max Players: ${MAX_PLAYERS}"
echo "=========================================="
echo "Starting ARK Server..."
echo "Command: ${SERVER_BINARY} ${SERVER_ARGS}"
echo "=========================================="

# Ellenőrizzük, hogy a bináris végrehajtható-e
if [ ! -x "${SERVER_BINARY}" ]; then
    echo "HIBA: A szerver bináris nem végrehajtható: ${SERVER_BINARY}"
    echo "Jogosultságok beállítása..."
    chmod +x "${SERVER_BINARY}" || {
        echo "HIBA: Nem lehet végrehajthatóvá tenni a binárist!"
        exit 1
    }
fi

# Szerver indítása
echo "Szerver indítása..."
if [ "${USE_WINE}" = "true" ]; then
    echo "Wine használata Windows bináris futtatásához..."
    # Wine konfiguráció (ha szükséges)
    export WINEPREFIX="${ARK_SERVER_DIR}/.wine"
    export DISPLAY=:99
    # Xvfb indítása háttérben (ha szükséges)
    Xvfb :99 -screen 0 1024x768x24 > /dev/null 2>&1 &
    # Wine-nal futtatjuk a szervert
    exec wine "${SERVER_BINARY}" ${SERVER_ARGS}
else
    # Natív Linux bináris
    exec "${SERVER_BINARY}" ${SERVER_ARGS}
fi

# Ha ide jutunk, akkor a szerver leállt
EXIT_CODE=$?
echo "=========================================="
echo "ARK szerver leállt, kilépési kód: ${EXIT_CODE}"
echo "=========================================="
exit ${EXIT_CODE}

