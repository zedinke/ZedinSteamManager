#!/bin/bash
# Jogosultságok javítása a szerverfájlokhoz

# Projekt mappa
PROJECT_DIR="$HOME/ZedinSteamManager"
SERVER_FILES_DIR="$PROJECT_DIR/Server/ArkAscended/ServerFiles"

echo "Jogosultságok javítása..."

# Ellenőrizzük, hogy a mappa létezik-e
if [ ! -d "$SERVER_FILES_DIR" ]; then
    echo "HIBA: A ServerFiles mappa nem található: $SERVER_FILES_DIR"
    exit 1
fi

# Jelenlegi felhasználó és csoport
CURRENT_USER=$(whoami)
CURRENT_GROUP=$(id -gn)

echo "Felhasználó: $CURRENT_USER"
echo "Csoport: $CURRENT_GROUP"
echo "Javítandó mappa: $SERVER_FILES_DIR"

# Jogosultságok javítása
echo "Jogosultságok beállítása..."
sudo chown -R "$CURRENT_USER:$CURRENT_GROUP" "$SERVER_FILES_DIR"
sudo chmod -R u+rwX "$SERVER_FILES_DIR"

echo "✓ Jogosultságok javítva!"
echo ""
echo "Most már törölheted a hiányos telepítést:"
echo "  rm -rf $SERVER_FILES_DIR/user_2/latest/ShooterGame"

