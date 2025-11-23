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

A `config/app.py` fájlban állítsd be:

```python
config = {
    # ... egyéb beállítások ...
    'ark_docker_image': 'zedinarkmanager/ark-server:latest',
    'ark_docker_use_custom': True,  # Saját image használata
}
```

## Különbségek a POK image-hez képest

- **Mappa struktúra**: `/home/zedin/arkserver` helyett `/home/pok/arkserver`
- **Felhasználó**: `zedin` (UID 1000) helyett `pok`
- **Saját entrypoint script**: A szerver indítását kezeli

## Megjegyzés

Ez egy alap Dockerfile. Az ARK szerver teljes működéséhez szükség lehet további konfigurációkra és scriptekre, amelyeket a POK image tartalmaz.

