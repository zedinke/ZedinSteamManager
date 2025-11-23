# Gyors Aktiválás - ai_developer felhasználó

## ✅ 1. Docker image build - KÉSZ!

A Docker image sikeresen build-elődött:
```
zedinarkmanager/ark-server:latest   6be11cf34901        107MB
```

## 📝 2. Konfiguráció beállítása

A `config/app.py` fájlban add hozzá vagy módosítsd:

```python
config = {
    # ... egyéb beállítások ...
    
    # Docker image beállítások
    'ark_docker_image': 'zedinarkmanager/ark-server:latest',
    'ark_docker_use_custom': True,  # ⚠️ FONTOS: True legyen!
}
```

**Ellenőrzés:**
```bash
cd ~/ZedinSteamManager
cat config/app.py | grep ark_docker
```

Látnod kellene:
- `'ark_docker_image': 'zedinarkmanager/ark-server:latest'`
- `'ark_docker_use_custom': True`

## 🔄 3. Szerver újraindítása

```bash
# Ha systemd service-ként fut:
sudo systemctl restart zedinarkmanager

# Vagy ha manuálisan fut:
cd ~/ZedinSteamManager
# Állítsd le (Ctrl+C), majd indítsd újra:
python run.py
```

## ✅ 4. Ellenőrzés

**Új szerver létrehozása után ellenőrizd:**

```bash
# Docker container
docker ps | grep zedin_asa_

# Docker Compose fájl
cat ~/ZedinSteamManager/Server/ArkAscended/Servers/server_*/docker-compose.yaml | grep image
```

Látnod kellene: `image: zedinarkmanager/ark-server:latest`

## 🎯 Kész!

Most már az új szerverek a saját Docker image-t fogják használni!

