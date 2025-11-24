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
# Először próbáljuk meg a linux64/ mappában lévő binárist, majd a Windows binárist Wine-nal
# A Linux bináris a linux64/ mappában van (vagy nincs, csak .so fájlok)
# A Windows bináris a ShooterGame/Binaries/Win64/ArkAscendedServer.exe (nem ShooterGameServer.exe!)
if [ -f "${ARK_SERVER_DIR}/linux64/ShooterGameServer" ]; then
    SERVER_BINARY="${ARK_SERVER_DIR}/linux64/ShooterGameServer"
    USE_WINE=false
elif [ -f "${ARK_SERVER_DIR}/ShooterGame/Binaries/Win64/ArkAscendedServer.exe" ]; then
    SERVER_BINARY="${ARK_SERVER_DIR}/ShooterGame/Binaries/Win64/ArkAscendedServer.exe"
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
    echo "Keresett bináris: ${SERVER_BINARY}"
    echo ""
    echo "Mappa tartalma:"
    ls -la "${ARK_SERVER_DIR}" || echo "Mappa nem létezik vagy nem elérhető"
    if [ -d "${ARK_SERVER_DIR}/linux64" ]; then
        echo ""
        echo "linux64 mappa tartalma:"
        ls -la "${ARK_SERVER_DIR}/linux64" || true
    fi
    if [ -d "${ARK_SERVER_DIR}/ShooterGame" ]; then
        echo ""
        echo "ShooterGame mappa tartalma:"
        ls -la "${ARK_SERVER_DIR}/ShooterGame" || true
        if [ -d "${ARK_SERVER_DIR}/ShooterGame/Binaries" ]; then
            echo ""
            echo "Binaries mappa tartalma:"
            ls -la "${ARK_SERVER_DIR}/ShooterGame/Binaries" || true
            if [ -d "${ARK_SERVER_DIR}/ShooterGame/Binaries/Win64" ]; then
                echo ""
                echo "Win64 mappa tartalma:"
                ls -la "${ARK_SERVER_DIR}/ShooterGame/Binaries/Win64" || true
                if [ -f "${ARK_SERVER_DIR}/ShooterGame/Binaries/Win64/ArkAscendedServer.exe" ]; then
                    echo ""
                    echo "✓ ArkAscendedServer.exe megtalálva! Használjuk ezt."
                    SERVER_BINARY="${ARK_SERVER_DIR}/ShooterGame/Binaries/Win64/ArkAscendedServer.exe"
                    USE_WINE=true
                else
                    echo ""
                    echo "✗ ArkAscendedServer.exe nem található a Win64 mappában"
                fi
            fi
        fi
    fi
    # Ha még mindig nincs bináris, kilépünk
    if [ ! -f "${SERVER_BINARY}" ]; then
        echo ""
        echo "✗ Bináris nem található sehol. Kilépés."
        exit 1
    fi
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
    # Wine konfiguráció
    # FONTOS: A Wine prefix-et a konténerben lévő home directory-ba tesszük,
    # nem a volume mount-ba, mert a volume mount nem a konténerben futó felhasználó tulajdona
    export WINEPREFIX="${HOME}/.wine"
    export DISPLAY=:99
    export WINEDEBUG=-all  # Wine debug üzenetek kikapcsolása (csak hibák)
    
    # Wine prefix inicializálása (ha még nem létezik)
    # FONTOS: A Wine automatikusan inicializálja a prefix-et, amikor először futtatunk egy alkalmazást
    # Ezért nem kell előre inicializálni, csak biztosítjuk, hogy a mappa létezzen
    if [ ! -d "${WINEPREFIX}" ]; then
        echo "Wine prefix mappa létrehozása: ${WINEPREFIX}"
        mkdir -p "${WINEPREFIX}" || {
            echo "HIBA: Nem sikerült létrehozni a Wine prefix mappát: ${WINEPREFIX}"
            exit 1
        }
        echo "✓ Wine prefix mappa létrehozva (a Wine automatikusan inicializálja az első futtatáskor)"
    else
        echo "Wine prefix már létezik: ${WINEPREFIX}"
    fi
    
    # Xvfb indítása háttérben (ha szükséges)
    echo "Xvfb indítása..."
    Xvfb :99 -screen 0 1024x768x24 > /dev/null 2>&1 &
    XVFB_PID=$!
    sleep 2  # Várunk, hogy az Xvfb elinduljon
    
    # Ellenőrizzük, hogy az Xvfb fut-e
    if ! kill -0 $XVFB_PID 2>/dev/null; then
        echo "FIGYELMEZTETÉS: Xvfb nem indult el, de folytatjuk..."
    else
        echo "✓ Xvfb elindult (PID: $XVFB_PID)"
    fi
    
    # Wine verzió ellenőrzése
    echo "Wine verzió:"
    wine --version || echo "FIGYELMEZTETÉS: Wine verzió ellenőrzés sikertelen"
    
    # Saved mappa és Logs mappa létrehozása (ha szükséges)
    SAVED_DIR="${ARK_SERVER_DIR}/ShooterGame/Saved"
    LOGS_DIR="${SAVED_DIR}/Logs"
    mkdir -p "${LOGS_DIR}" || echo "FIGYELMEZTETÉS: Nem sikerült létrehozni a Logs mappát"
    
    # Jogosultságok beállítása a Saved mappára (ha szükséges)
    # A Saved mappa volume mount, lehet, hogy a host-on más jogosultságokkal van
    # Próbáljuk meg javítani a jogosultságokat, ha nem tudunk írni
    if [ ! -w "${LOGS_DIR}" ]; then
        echo "FIGYELMEZTETÉS: Logs mappa nem írható, jogosultságok javítása..."
        chmod -R u+w "${SAVED_DIR}" 2>/dev/null || echo "FIGYELMEZTETÉS: Nem sikerült javítani a jogosultságokat"
    fi
    
    # Log fájl útvonal (ha nem tudunk írni a Saved mappába, használjuk a /tmp-t)
    if [ -w "${LOGS_DIR}" ]; then
        LOG_FILE="${LOGS_DIR}/server.log"
    else
        LOG_FILE="/tmp/ark_server.log"
        echo "FIGYELMEZTETÉS: Log fájl a /tmp/ark_server.log-ba íródik (Saved mappa nem írható)"
    fi
    
    # Wine prefix inicializálása (ha még nem teljes)
    # A Wine automatikusan inicializálja, de ellenőrizzük, hogy a kernel32.dll létezik-e
    if [ ! -f "${WINEPREFIX}/drive_c/windows/system32/kernel32.dll" ]; then
        echo "Wine prefix inicializálása (kernel32.dll hiányzik)..."
        # Próbáljuk meg inicializálni a Wine prefix-et
        WINEDLLOVERRIDES="mscoree,mshtml=" wineboot --init 2>&1 | head -10 || echo "FIGYELMEZTETÉS: Wine prefix inicializálás figyelmeztetéseket adott"
        sleep 2
    fi
    
    # Szerver indítása Wine-nal
    echo "Szerver indítása Wine-nal..."
    echo "Bináris: ${SERVER_BINARY}"
    echo "Parancs: wine ${SERVER_BINARY} ${SERVER_ARGS}"
    echo "Log fájl: ${LOG_FILE}"
    echo ""
    echo "=========================================="
    echo "Wine inicializálja a prefix-et az első futtatáskor..."
    echo "Ez 30-60 másodpercet vehet igénybe..."
    echo "=========================================="
    echo ""
    # A Wine inicializálása az első futtatáskor időbe telhet
    # A szerver kimenetét mind a stdout-ra, mind a log fájlba írjuk (ha lehet)
    if [ -w "${LOG_FILE}" ] || [ "${LOG_FILE}" = "/tmp/ark_server.log" ]; then
        exec wine "${SERVER_BINARY}" ${SERVER_ARGS} 2>&1 | tee -a "${LOG_FILE}"
    else
        # Ha nem tudunk írni a log fájlba, csak stdout-ra
        exec wine "${SERVER_BINARY}" ${SERVER_ARGS}
    fi
else
    # Natív Linux bináris
    # Saved mappa és Logs mappa létrehozása (ha szükséges)
    SAVED_DIR="${ARK_SERVER_DIR}/ShooterGame/Saved"
    LOGS_DIR="${SAVED_DIR}/Logs"
    mkdir -p "${LOGS_DIR}" || echo "FIGYELMEZTETÉS: Nem sikerült létrehozni a Logs mappát"
    
    echo "Szerver indítása natív Linux binárissal..."
    echo "Bináris: ${SERVER_BINARY}"
    echo "Parancs: ${SERVER_BINARY} ${SERVER_ARGS}"
    echo "Log fájl: ${LOGS_DIR}/server.log"
    exec "${SERVER_BINARY}" ${SERVER_ARGS} 2>&1 | tee -a "${LOGS_DIR}/server.log"
fi

# Ha ide jutunk, akkor a szerver leállt
EXIT_CODE=$?
echo "=========================================="
echo "ARK szerver leállt, kilépési kód: ${EXIT_CODE}"
echo "=========================================="
exit ${EXIT_CODE}

