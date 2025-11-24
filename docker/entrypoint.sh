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
PASSIVE_MODS="${PASSIVE_MODS:-}"
CLUSTER_ID="${CLUSTER_ID:-}"
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

# Modok letöltése (ha vannak beállítva)
if [ -n "${MOD_IDS}" ]; then
    echo "=========================================="
    echo "MODOK LETÖLTÉSE KEZDŐDIK"
    echo "=========================================="
    echo "Mod IDs: ${MOD_IDS}"
    echo "ARK_SERVER_DIR: ${ARK_SERVER_DIR}"
    echo "STEAMCMD_BIN: ${STEAMCMD_BIN}"
    
    # Ellenőrizzük, hogy a SteamCMD létezik-e
    if [ ! -f "${STEAMCMD_BIN}" ]; then
        echo "HIBA: SteamCMD nem található: ${STEAMCMD_BIN}"
        echo "Modok letöltése kihagyva"
    else
        echo "SteamCMD megtalálva, modok letöltése..."
        
        # ARK Survival Ascended modok a steamapps/workshop/content/2430930/ mappába kerülnek
        # A szerver több helyen is keresi a modokat:
        # 1. ShooterGame/Mods (relatív az ARK_SERVER_DIR-től)
        # 2. ShooterGame/Binaries/Win64/ShooterGame/Mods (ha a bináris mappájából fut)
        # A SteamCMD workshop_download_item automatikusan a workshop/content mappába tölti le,
        # de szimlinket kell létrehozni vagy másolni kell a modokat mindkét helyre
        
        # Először ellenőrizzük, hogy létezik-e a workshop mappa
        WORKSHOP_DIR="${ARK_SERVER_DIR}/steamapps/workshop/content/${ARK_APP_ID}"
        MODS_DIR="${ARK_SERVER_DIR}/ShooterGame/Mods"
        MODS_DIR_WIN64="${ARK_SERVER_DIR}/ShooterGame/Binaries/Win64/ShooterGame/Mods"
        
        echo "Workshop directory: ${WORKSHOP_DIR}"
        echo "Mods directory (standard): ${MODS_DIR}"
        echo "Mods directory (Win64): ${MODS_DIR_WIN64}"
        
        # Mindkét mappát létrehozzuk
        mkdir -p "${WORKSHOP_DIR}" || echo "FIGYELMEZTETÉS: Nem sikerült létrehozni a workshop mappát"
        mkdir -p "${MODS_DIR}" || echo "FIGYELMEZTETÉS: Nem sikerült létrehozni a Mods mappát"
        mkdir -p "${MODS_DIR_WIN64}" || echo "FIGYELMEZTETÉS: Nem sikerült létrehozni a Win64 Mods mappát"
        
        # Jogosultságok beállítása
        if [ -d "${WORKSHOP_DIR}" ]; then
            chmod -R u+w "${WORKSHOP_DIR}" 2>/dev/null || echo "FIGYELMEZTETÉS: Nem sikerült beállítani a workshop mappa jogosultságait"
        fi
        if [ -d "${MODS_DIR}" ]; then
            chmod -R u+w "${MODS_DIR}" 2>/dev/null || echo "FIGYELMEZTETÉS: Nem sikerült beállítani a Mods mappa jogosultságait"
        fi
        if [ -d "${MODS_DIR_WIN64}" ]; then
            chmod -R u+w "${MODS_DIR_WIN64}" 2>/dev/null || echo "FIGYELMEZTETÉS: Nem sikerült beállítani a Win64 Mods mappa jogosultságait"
        fi
        
        # Minden mod ID-t letöltünk
        # A MOD_IDS formátuma: "123456,789012" vagy "123456"
        IFS=',' read -ra MOD_ARRAY <<< "${MOD_IDS}"
        for mod_id in "${MOD_ARRAY[@]}"; do
            mod_id=$(echo "${mod_id}" | xargs)  # Trim whitespace
            if [ -n "${mod_id}" ]; then
                echo "----------------------------------------"
                echo "Mod letöltése: ${mod_id}..."
                echo "SteamCMD parancs: ${STEAMCMD_BIN} +force_install_dir ${ARK_SERVER_DIR} +login anonymous +workshop_download_item ${ARK_APP_ID} ${mod_id} +quit"
                
                # SteamCMD futtatása részletes outputtal
                "${STEAMCMD_BIN}" +force_install_dir "${ARK_SERVER_DIR}" \
                    +login anonymous \
                    +workshop_download_item ${ARK_APP_ID} ${mod_id} \
                    +quit 2>&1 | tee -a /tmp/steamcmd_mod_${mod_id}.log
                
                WORKSHOP_EXIT=$?
                echo "SteamCMD exit code: ${WORKSHOP_EXIT}"
                
                # Ellenőrizzük, hogy a mod letöltődött-e
                MOD_WORKSHOP_PATH="${WORKSHOP_DIR}/${mod_id}"
                if [ -d "${MOD_WORKSHOP_PATH}" ]; then
                    echo "✓ Mod ${mod_id} letöltve a workshop mappába: ${MOD_WORKSHOP_PATH}"
                    echo "Mod mappa tartalma:"
                    ls -la "${MOD_WORKSHOP_PATH}" | head -10 || echo "Nem sikerült listázni a mod mappát"
                    
                    # Szimlink létrehozása vagy másolás mindkét Mods mappába
                    # 1. Standard Mods mappa
                    MOD_TARGET="${MODS_DIR}/${mod_id}"
                    if [ ! -e "${MOD_TARGET}" ]; then
                        echo "Szimlink létrehozása (standard): ${MOD_TARGET} -> ${MOD_WORKSHOP_PATH}"
                        ln -sf "${MOD_WORKSHOP_PATH}" "${MOD_TARGET}" || {
                            echo "Szimlink létrehozása sikertelen, másolás próbálása..."
                            cp -r "${MOD_WORKSHOP_PATH}" "${MOD_TARGET}" || echo "Másolás is sikertelen"
                        }
                    else
                        echo "Mod már létezik a standard célhelyen: ${MOD_TARGET}"
                    fi
                    
                    # 2. Win64 Mods mappa (ha a bináris mappájából fut)
                    MOD_TARGET_WIN64="${MODS_DIR_WIN64}/${mod_id}"
                    if [ ! -e "${MOD_TARGET_WIN64}" ]; then
                        echo "Szimlink létrehozása (Win64): ${MOD_TARGET_WIN64} -> ${MOD_WORKSHOP_PATH}"
                        ln -sf "${MOD_WORKSHOP_PATH}" "${MOD_TARGET_WIN64}" || {
                            echo "Szimlink létrehozása sikertelen, másolás próbálása..."
                            cp -r "${MOD_WORKSHOP_PATH}" "${MOD_TARGET_WIN64}" || echo "Másolás is sikertelen"
                        }
                    else
                        echo "Mod már létezik a Win64 célhelyen: ${MOD_TARGET_WIN64}"
                    fi
                else
                    echo "FIGYELMEZTETÉS: Mod ${mod_id} mappa nem található: ${MOD_WORKSHOP_PATH}"
                    echo "Ellenőrizzük a workshop mappa tartalmát:"
                    ls -la "${WORKSHOP_DIR}" | head -20 || echo "Workshop mappa nem létezik vagy üres"
                fi
                
                if [ ${WORKSHOP_EXIT} -eq 0 ]; then
                    echo "✓ Mod ${mod_id} letöltési folyamat befejezve (exit code: 0)"
                else
                    echo "FIGYELMEZTETÉS: Mod ${mod_id} letöltése sikertelen (exit code: ${WORKSHOP_EXIT})"
                fi
            fi
        done
        
        # Jogosultságok újra beállítása a letöltött modokra
        if [ -d "${MODS_DIR}" ]; then
            chmod -R u+w "${MODS_DIR}" 2>/dev/null || echo "FIGYELMEZTETÉS: Nem sikerült beállítani a letöltött modok jogosultságait"
            echo "Standard Mods mappa végső tartalma:"
            ls -la "${MODS_DIR}" | head -20 || echo "Mods mappa nem létezik vagy üres"
        fi
        if [ -d "${MODS_DIR_WIN64}" ]; then
            chmod -R u+w "${MODS_DIR_WIN64}" 2>/dev/null || echo "FIGYELMEZTETÉS: Nem sikerült beállítani a Win64 letöltött modok jogosultságait"
            echo "Win64 Mods mappa végső tartalma:"
            ls -la "${MODS_DIR_WIN64}" | head -20 || echo "Win64 Mods mappa nem létezik vagy üres"
        fi
        
        echo "=========================================="
        echo "MODOK LETÖLTÉSE BEFEJEZVE"
        echo "=========================================="
    fi
else
    echo "Nincs mod ID beállítva (MOD_IDS üres vagy nincs megadva)"
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
# FONTOS: ARK szerver parancssori formátum:
# MapName ?listen?SessionName="..."?RCONEnabled=True?RCONPort=...?ServerAdminPassword=... -Port=... -QueryPort=... -WinLiveMaxPlayers=... -clusterid=... -mods=... -passivemods=...

# Első rész: MapName_WP ?listen?SessionName=...?RCONEnabled=...?RCONPort=...?ServerAdminPassword=...
# FONTOS: A map név után kötelező a _WP utótag
MAP_NAME_WP="${MAP_NAME}"
if [[ ! "${MAP_NAME_WP}" =~ _WP$ ]]; then
    MAP_NAME_WP="${MAP_NAME}_WP"
fi

QUERY_PARAMS=()
QUERY_PARAMS+=("listen")
QUERY_PARAMS+=("SessionName=\"${SESSION_NAME}\"")

if [ "${RCON_ENABLED}" = "True" ]; then
    QUERY_PARAMS+=("RCONEnabled=True")
    QUERY_PARAMS+=("RCONPort=${RCON_PORT}")
    if [ -n "${SERVER_ADMIN_PASSWORD}" ]; then
        QUERY_PARAMS+=("ServerAdminPassword=${SERVER_ADMIN_PASSWORD}")
    fi
fi

if [ -n "${SERVER_PASSWORD}" ]; then
    QUERY_PARAMS+=("ServerPassword=${SERVER_PASSWORD}")
fi

# Query string összeállítása
QUERY_STRING=""
for param in "${QUERY_PARAMS[@]}"; do
    if [ -z "${QUERY_STRING}" ]; then
        QUERY_STRING="?${param}"
    else
        QUERY_STRING="${QUERY_STRING}?${param}"
    fi
done

# Első rész: MapName_WP + query string
FIRST_PART="${MAP_NAME_WP}${QUERY_STRING}"

# Második rész: -Port=... -QueryPort=... -WinLiveMaxPlayers=... -clusterid=...
SECOND_PART_ARGS=()
SECOND_PART_ARGS+=("-Port=${ASA_PORT}")
SECOND_PART_ARGS+=("-QueryPort=${QUERY_PORT}")
SECOND_PART_ARGS+=("-WinLiveMaxPlayers=${MAX_PLAYERS}")

# Cluster ID (ha van)
if [ -n "${CLUSTER_ID}" ]; then
    SECOND_PART_ARGS+=("-clusterid=${CLUSTER_ID}")
fi

SECOND_PART="${SECOND_PART_ARGS[*]}"

# Harmadik rész: -NoBattlEye -mods=... -passivemods=... custom args
THIRD_PART_ARGS=()

# BattleEye
if [ "${BATTLEEYE}" = "True" ]; then
    THIRD_PART_ARGS+=("-UseBattlEye")
else
    THIRD_PART_ARGS+=("-NoBattlEye")
fi

# Mods (aktív modok) - helyes formátum: -mods=123456,789012
if [ -n "${MOD_IDS}" ]; then
    THIRD_PART_ARGS+=("-mods=${MOD_IDS}")
fi

# Passive Mods (ha van) - helyes formátum: -passivemods=123456,789012
if [ -n "${PASSIVE_MODS}" ]; then
    THIRD_PART_ARGS+=("-passivemods=${PASSIVE_MODS}")
fi

# Custom Server Args
if [ -n "${CUSTOM_SERVER_ARGS}" ]; then
    THIRD_PART_ARGS+=("${CUSTOM_SERVER_ARGS}")
fi

THIRD_PART="${THIRD_PART_ARGS[*]}"

# Teljes parancs összeállítása
# FONTOS: A FIRST_PART (map név + query string) külön argumentum, hogy ne legyen szóköz a map név és a ? között
# A második és harmadik részek külön argumentumok
SERVER_ARGS="${FIRST_PART}"
if [ -n "${SECOND_PART}" ]; then
    SERVER_ARGS="${SERVER_ARGS} ${SECOND_PART}"
fi
if [ -n "${THIRD_PART}" ]; then
    SERVER_ARGS="${SERVER_ARGS} ${THIRD_PART}"
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
    
    # Ellenőrizzük, hogy a Saved mappa létezik-e és írható-e
    if [ ! -d "${SAVED_DIR}" ]; then
        echo "FIGYELMEZTETÉS: Saved mappa nem létezik: ${SAVED_DIR}"
        echo "FIGYELMEZTETÉS: Próbáljuk létrehozni..."
        mkdir -p "${SAVED_DIR}" 2>/dev/null || echo "FIGYELMEZTETÉS: Nem sikerült létrehozni a Saved mappát"
    fi
    
    # Jogosultságok beállítása a Saved mappára (ha szükséges)
    # A Saved mappa volume mount, lehet, hogy a host-on más jogosultságokkal van
    # Próbáljuk meg javítani a jogosultságokat, ha nem tudunk írni
    if [ -d "${SAVED_DIR}" ] && [ ! -w "${SAVED_DIR}" ]; then
        echo "FIGYELMEZTETÉS: Saved mappa nem írható, jogosultságok javítása..."
        # Próbáljuk meg a Saved mappát írhatóvá tenni
        chmod -R u+w "${SAVED_DIR}" 2>/dev/null || {
            echo "FIGYELMEZTETÉS: Nem sikerült javítani a Saved mappa jogosultságait"
            echo "FIGYELMEZTETÉS: Ez normális lehet, ha a mappa a host-on más jogosultságokkal van"
        }
    fi
    
    # Logs mappa létrehozása
    if [ -w "${SAVED_DIR}" ]; then
        mkdir -p "${LOGS_DIR}" 2>/dev/null || echo "FIGYELMEZTETÉS: Nem sikerült létrehozni a Logs mappát"
        
        # Ellenőrizzük, hogy a Logs mappa írható-e
        if [ ! -w "${LOGS_DIR}" ]; then
            echo "FIGYELMEZTETÉS: Logs mappa nem írható, jogosultságok javítása..."
            chmod -R u+w "${LOGS_DIR}" 2>/dev/null || echo "FIGYELMEZTETÉS: Nem sikerült javítani a Logs mappa jogosultságait"
        fi
    else
        echo "FIGYELMEZTETÉS: Saved mappa nem írható, Logs mappa létrehozása kihagyva"
    fi
    
    # Log fájl útvonal (ha nem tudunk írni a Saved mappába, használjuk a /tmp-t)
    if [ -w "${LOGS_DIR}" ] 2>/dev/null; then
        LOG_FILE="${LOGS_DIR}/server.log"
        echo "✓ Log fájl a Saved mappába íródik: ${LOG_FILE}"
    else
        LOG_FILE="/tmp/ark_server.log"
        echo "FIGYELMEZTETÉS: Log fájl a /tmp/ark_server.log-ba íródik (Saved mappa nem írható)"
        echo "FIGYELMEZTETÉS: A Saved mappa jogosultságait a host-on kell javítani (sudo chown -R $(id -u):$(id -g) ${SAVED_DIR})"
    fi
    
    # Wine prefix inicializálása (ha még nem teljes)
    # A Wine automatikusan inicializálja, de ellenőrizzük, hogy a Wine prefix létezik-e és inicializálva van-e
    # A kernel32.dll ellenőrzése nem megbízható, mert a Wine prefix inicializálva lehet, de a DLL-ek más helyen lehetnek
    # Egyszerűen ellenőrizzük, hogy a Wine prefix létezik-e és van-e benne system.reg
    if [ ! -f "${WINEPREFIX}/system.reg" ]; then
        echo "Wine prefix inicializálása (system.reg hiányzik)..."
        echo "Ez 30-60 másodpercet vehet igénybe..."
        # Próbáljuk meg inicializálni a Wine prefix-et timeout-tal
        # A wineboot --init időbe telhet, ezért timeout-ot használunk
        # A stderr-t is redirecteljük, hogy ne zavarjon
        if timeout 90 sh -c 'WINEDLLOVERRIDES="mscoree,mshtml=" wineboot --init' > /tmp/wine_init.log 2>&1; then
            echo "✓ Wine prefix inicializálás sikeres"
        else
            EXIT_CODE=$?
            echo "FIGYELMEZTETÉS: Wine prefix inicializálás kilépési kód: $EXIT_CODE"
            if [ -f /tmp/wine_init.log ]; then
                echo "Wine inicializálás részletei (utolsó 20 sor):"
                tail -20 /tmp/wine_init.log || true
            fi
            # Mégis folytatjuk, mert a Wine prefix lehet, hogy létrejött
            if [ -f "${WINEPREFIX}/system.reg" ]; then
                echo "✓ Wine prefix inicializálva (system.reg létezik)"
            else
                echo "FIGYELMEZTETÉS: Wine prefix inicializálás nem fejeződött be, de folytatjuk..."
                echo "A Wine automatikusan inicializálja a prefix-et az első futtatáskor"
            fi
        fi
        sleep 1
    else
        echo "✓ Wine prefix már inicializálva (system.reg létezik)"
    fi
    
    # Szerver indítása Wine-nal
    echo "Szerver indítása Wine-nal..."
    echo "Bináris: ${SERVER_BINARY}"
    echo "Parancs: wine ${SERVER_BINARY} \"${FIRST_PART}\" ${SECOND_PART} ${THIRD_PART}"
    echo "Log fájl: ${LOG_FILE}"
    echo ""
    echo "=========================================="
    echo "Wine inicializálja a prefix-et az első futtatáskor..."
    echo "Ez 30-60 másodpercet vehet igénybe..."
    echo "=========================================="
    echo ""
    # A Wine inicializálása az első futtatáskor időbe telhet
    # A szerver kimenetét mind a stdout-ra, mind a log fájlba írjuk (ha lehet)
    # FONTOS: A FIRST_PART-ot külön argumentumként adjuk át, hogy a map név és a ? között ne legyen szóköz
    if [ -w "${LOG_FILE}" ] || [ "${LOG_FILE}" = "/tmp/ark_server.log" ]; then
        exec wine "${SERVER_BINARY}" "${FIRST_PART}" ${SECOND_PART} ${THIRD_PART} 2>&1 | tee -a "${LOG_FILE}"
    else
        # Ha nem tudunk írni a log fájlba, csak stdout-ra
        exec wine "${SERVER_BINARY}" "${FIRST_PART}" ${SECOND_PART} ${THIRD_PART}
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
    # FONTOS: A FIRST_PART-ot külön argumentumként adjuk át, hogy a map név és a ? között ne legyen szóköz
    exec "${SERVER_BINARY}" "${FIRST_PART}" ${SECOND_PART} ${THIRD_PART} 2>&1 | tee -a "${LOGS_DIR}/server.log"
fi

# Ha ide jutunk, akkor a szerver leállt
EXIT_CODE=$?
echo "=========================================="
echo "ARK szerver leállt, kilépési kód: ${EXIT_CODE}"
echo "=========================================="
exit ${EXIT_CODE}


