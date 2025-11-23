# ZedinArkManager Docker Image Aktiválás Linuxon

## Fontos: ai_developer felhasználó alatt futtatás

Ez az útmutató az `ai_developer` felhasználó alatt történő futtatáshoz készült.

## Előfeltételek

1. **Docker telepítve**: Ellenőrizd, hogy a Docker telepítve van-e
   ```bash
   docker --version
   ```

2. **Docker jogosultságok**: Az `ai_developer` felhasználónak Docker parancsokat kell futtatnia
   ```bash
   # Ha "permission denied" hibát kapsz, add hozzá a felhasználót a docker csoporthoz:
   sudo usermod -aG docker ai_developer
   # Vagy futtasd sudo-val (nem ajánlott)
   ```

3. **Bejelentkezés**: Jelentkezz be `ai_developer` felhasználóként
   ```bash
   su - ai_developer
   # vagy
   sudo -u ai_developer -i
   ```

## Lépésről lépésre útmutató

### 1. Docker image build

Először build-eld a saját Docker image-t az `ai_developer` felhasználó alatt:

```bash
# Győződj meg róla, hogy az ai_developer felhasználó vagy
whoami  # kimenet: ai_developer

# Navigálj a projekt mappába
cd /home/ai_developer/ZedinSteamManager  # vagy ahol a projekt van

# Docker image build
cd docker
chmod +x build-image.sh entrypoint.sh
./build-image.sh latest
```

Ez létrehozza a `zedinarkmanager/ark-server:latest` image-t.

**Ellenőrzés:**
```bash
docker images | grep zedinarkmanager
```

**Ha Docker jogosultság hiba van:**
```bash
# Opció 1: Add hozzá a felhasználót a docker csoporthoz (ajánlott)
sudo usermod -aG docker ai_developer
# Újra be kell jelentkezned, hogy érvényesüljön

# Opció 2: Futtasd sudo-val (nem ajánlott, de működik)
sudo ./build-image.sh latest
```

### 2. Konfiguráció beállítása

A `config/app.py` fájlban állítsd be a saját Docker image használatát:

```python
config = {
    # ... egyéb beállítások ...
    
    # Docker image beállítások
    'ark_docker_image': 'zedinarkmanager/ark-server:latest',
    'ark_docker_use_custom': True,  # Saját image használata
}
```

**Vagy ha .env fájlt használsz:**
```bash
ARK_DOCKER_IMAGE=zedinarkmanager/ark-server:latest
ARK_DOCKER_USE_CUSTOM=True
```

### 3. Szerver újraindítása

A konfiguráció változás után indítsd újra a ZedinArkManager szervert az `ai_developer` felhasználó alatt:

```bash
# Győződj meg róla, hogy az ai_developer felhasználó vagy
whoami  # kimenet: ai_developer

# Ha systemd service-ként fut:
sudo systemctl restart zedinarkmanager

# Vagy ha manuálisan fut:
cd /home/ai_developer/ZedinSteamManager  # vagy ahol a projekt van
# Állítsd le (Ctrl+C), majd indítsd újra:
python run.py
# vagy
./start.sh
```

### 4. Új szerver létrehozása

Most már az új szerverek a saját Docker image-t fogják használni:

1. Menj a webes felületre
2. Hozz létre egy új ARK szervert
3. A szerver automatikusan a `zedinarkmanager/ark-server:latest` image-t fogja használni

### 5. Ellenőrzés

**Docker container ellenőrzése:**
```bash
docker ps | grep zedin_asa_
```

**Docker Compose fájl ellenőrzése:**
```bash
# Keress egy szerver mappát (ai_developer felhasználó mappájában)
cd /home/ai_developer/ZedinSteamManager/Server/ArkAscended  # vagy ahol a Servers mappa van
ls -la Servers/server_*/docker-compose.yaml

# Nézd meg a fájl tartalmát
cat Servers/server_*/docker-compose.yaml | grep image
```

Látnod kellene: `image: zedinarkmanager/ark-server:latest`

**Volume mount útvonalak ellenőrzése:**
```bash
# Ellenőrizd, hogy a volume mount útvonalak helyesek-e
cat Servers/server_*/docker-compose.yaml | grep volumes
```

Látnod kellene:
- `ServerFiles` -> `/home/zedin/arkserver` (saját image esetén)
- `Saved` -> `/home/zedin/arkserver/ShooterGame/Saved` (saját image esetén)

## Hibaelhárítás

### Docker image nem található

Ha a szerver indításakor "image not found" hibát kapsz:

```bash
# Ellenőrizd, hogy a image létezik-e
docker images | grep zedinarkmanager

# Ha nincs, build-eld újra
cd docker
./build-image.sh latest
```

### Konfiguráció nem érvényesül

Ha a régi image-t használja továbbra is:

1. Ellenőrizd a `config/app.py` fájlt
2. Indítsd újra a ZedinArkManager szervert
3. Ellenőrizd a logokat hibákért

### Port ütközések

Ha port ütközést kapsz:

- A rendszer automatikusan talál szabad portot
- Ha mégis probléma van, ellenőrizd: `netstat -tuln | grep 7777`

## Visszaállás POK image-re

Ha vissza szeretnél állni a POK image-re:

```python
config = {
    # ...
    'ark_docker_image': 'acekorneya/asa_server:2_1_latest',
    'ark_docker_use_custom': False,  # POK image használata
}
```

Majd indítsd újra a szervert.

## ai_developer felhasználó specifikus megjegyzések

### Jogosultságok

Az `ai_developer` felhasználónak jogosultsága kell:
- Docker parancsok futtatásához (docker csoport tagja)
- Szerverfájlok mappák írásához/olvasásához
- Volume mount mappák eléréséhez

### Útvonalak

A szerverfájlok alapértelmezett útvonala:
- **ServerFiles base**: `/home/ai_developer/ZedinSteamManager/Server/ArkAscended/ServerFiles`
- **Servers mappa**: `/home/ai_developer/ZedinSteamManager/Server/ArkAscended/Servers`

### Docker jogosultság beállítása

Ha Docker parancsok futtatásakor "permission denied" hibát kapsz:

```bash
# Add hozzá az ai_developer felhasználót a docker csoporthoz
sudo usermod -aG docker ai_developer

# Újra be kell jelentkezned, hogy érvényesüljön
# Vagy futtasd:
newgrp docker

# Ellenőrzés:
groups  # kimenetben kell lennie: docker
docker ps  # működnie kell permission denied nélkül
```

