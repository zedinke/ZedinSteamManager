#!/bin/bash
# ZedinArkManager - ARK Server Entrypoint Script

set -e

ARK_SERVER_DIR="${ARK_SERVER_DIR:-/home/zedin/arkserver}"
STEAMCMD_DIR="${STEAMCMD_DIR:-/home/zedin/steamcmd}"

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

# Szerver indítási parancs összeállítása
cd "${ARK_SERVER_DIR}"

# Alap parancs
SERVER_ARGS=""

# Map
SERVER_ARGS="${SERVER_ARGS} ${MAP_NAME}"

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
echo "Starting ARK Server with args: ${SERVER_ARGS}"
exec ./ShooterGame/Binaries/Linux/ShooterGameServer ${SERVER_ARGS}

