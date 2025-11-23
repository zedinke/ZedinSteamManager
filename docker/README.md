# ZedinArkManager - ARK Server Docker Image

Saját Docker image a ZedinArkManager ARK szerverekhez, amely a saját mappa struktúrát használja (`/home/zedin/arkserver`).

## Build

```bash
cd docker
chmod +x build-image.sh
./build-image.sh [tag]
```

Példa:
```bash
./build-image.sh latest
./build-image.sh v1.0.0
```

## Használat

### 1. Docker image build

```bash
cd docker
chmod +x build-image.sh
./build-image.sh latest
```

### 2. Konfiguráció beállítása

A `config/app.py` fájlban állítsd be:

```python
config = {
    # ... egyéb beállítások ...
    'ark_docker_image': 'zedinarkmanager/ark-server:latest',
    'ark_docker_use_custom': True,  # Saját image használata
}
```

### 3. Szerverfájlok telepítése

**FONTOS**: A szerverfájlokat **ELŐSZÖR** telepíteni kell a host rendszeren a webes felületen keresztül!

**Telepítési lépések:**

1. **Menj a webes felületre** (pl. `http://YOUR_SERVER_IP:8000`)
2. **Jelentkezz be** Server Admin vagy Manager Admin felhasználóként
3. **Menj az "ARK Server Files" menüpontra**
4. **Telepítsd a szerverfájlokat** SteamCMD-vel
   - A telepítés automatikusan a `ServerFiles/user_{user_id}/latest/` mappába történik
   - A telepítés több GB-ot letölt, ez időbe telhet (30-60 perc)

**Miután a szerverfájlok telepítve vannak:**
- A szerverek automatikusan használják a telepített szerverfájlokat
- A Docker konténer a volume mount-on keresztül éri el a szerverfájlokat
- **A konténer NEM telepíti automatikusan a szerverfájlokat!** A host rendszeren kell telepíteni.

**Ellenőrzés:**
- Ellenőrizd, hogy a `ServerFiles/user_{user_id}/latest/ShooterGame/Binaries/Linux/ShooterGameServer` fájl létezik-e
- Ha nem létezik, a telepítés nem fejeződött be, telepítsd újra

## Különbségek a POK image-hez képest

- **Mappa struktúra**: `/home/zedin/arkserver` helyett `/home/pok/arkserver`
- **Felhasználó**: `zedin` (UID 1000) helyett `pok`
- **Saját entrypoint script**: A szerver indítását kezeli

## Működés

A Docker image automatikusan:
1. **Telepíti az ARK szervert** (ha még nincs telepítve) SteamCMD-vel az első indításkor
2. **Frissíti a szervert** (ha `UPDATE_SERVER=True` environment változó be van állítva)
3. **Indítja a szervert** a megadott beállításokkal

## Fontos megjegyzések

1. **Első indítás**: Az első indításkor a szerver automatikusan letöltődik SteamCMD-vel, ami időbe telhet (több GB).

2. **Volume mount**: A szerverfájlokat volume-on keresztül mountoljuk:
   - `ServerFiles` -> `/home/zedin/arkserver`
   - `Saved` -> `/home/zedin/arkserver/ShooterGame/Saved`

3. **Frissítés**: Ha `UPDATE_SERVER=True`, akkor minden indításkor ellenőrzi és frissíti a szervert.

4. **Szerverfájlok**: A szerverfájlokat a host rendszeren kell telepíteni (SteamCMD-vel), vagy a konténer automatikusan letölti az első indításkor.

## Különbségek a POK image-hez képest

- **Mappa struktúra**: `/home/zedin/arkserver` helyett `/home/pok/arkserver`
- **Felhasználó**: `zedin` (UID 1000) helyett `pok`
- **Egyszerűbb entrypoint**: Alapvető szerver indítási logika
- **Automatikus telepítés**: Ha a szerver nincs telepítve, automatikusan letölti

