# ZedinArkManager Docker Image Aktiválás Linuxon

## Lépésről lépésre útmutató

### 1. Docker image build

Először build-eld a saját Docker image-t:

```bash
cd docker
chmod +x build-image.sh entrypoint.sh
./build-image.sh latest
```

Ez létrehozza a `zedinarkmanager/ark-server:latest` image-t.

**Ellenőrzés:**
```bash
docker images | grep zedinarkmanager
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

A konfiguráció változás után indítsd újra a ZedinArkManager szervert:

```bash
# Ha systemd service-ként fut:
sudo systemctl restart zedinarkmanager

# Vagy ha manuálisan fut:
# Állítsd le (Ctrl+C), majd indítsd újra:
python run.py
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
# Keress egy szerver mappát
ls -la Servers/server_*/docker-compose.yaml

# Nézd meg a fájl tartalmát
cat Servers/server_*/docker-compose.yaml | grep image
```

Látnod kellene: `image: zedinarkmanager/ark-server:latest`

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

