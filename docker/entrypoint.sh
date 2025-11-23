#!/bin/bash
# ZedinArkManager - ARK Server Entrypoint Script

set -e

ARK_SERVER_DIR="${ARK_SERVER_DIR:-/home/zedin/arkserver}"
STEAMCMD_DIR="${STEAMCMD_DIR:-/home/zedin/steamcmd}"
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
SERVER_BINARY="${ARK_SERVER_DIR}/ShooterGame/Binaries/Linux/ShooterGameServer"

# Ha a szerver nincs telepítve és UPDATE_SERVER=True, akkor telepítjük
if [ ! -f "${SERVER_BINARY}" ] && [ "${UPDATE_SERVER}" = "True" ]; then
    echo "ARK szerver nincs telepítve. Telepítés indítása SteamCMD-vel..."
    
    if [ ! -f "${STEAMCMD_BIN}" ]; then
        echo "HIBA: SteamCMD nem található: ${STEAMCMD_BIN}"
        exit 1
    fi
    
    # ARK szerver telepítése/frissítése
    "${STEAMCMD_BIN}" +force_install_dir "${ARK_SERVER_DIR}" \
        +login anonymous \
        +app_update ${ARK_APP_ID} validate \
        +quit
    
    if [ ! -f "${SERVER_BINARY}" ]; then
        echo "HIBA: ARK szerver telepítése sikertelen!"
        exit 1
    fi
    
    echo "ARK szerver telepítve!"
fi

# Ha a szerverfájlok még mindig nem léteznek, hiba
if [ ! -f "${SERVER_BINARY}" ]; then
    echo "HIBA: ARK szerver bináris nem található: ${SERVER_BINARY}"
    echo "Ellenőrizd, hogy a szerverfájlok telepítve vannak-e a volume-on!"
    exit 1
fi

# Szerver indítási parancs összeállítása
cd "${ARK_SERVER_DIR}"

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

exec "${SERVER_BINARY}" ${SERVER_ARGS}

