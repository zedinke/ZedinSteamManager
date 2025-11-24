# Docker Image Újra Buildelése

Ha módosítottad a Docker fájlokat (Dockerfile.zedin-ark-server vagy entrypoint.sh), újra kell buildelni a Docker image-t, hogy a változtatások életbe lépjenek.

## Buildelési lépések

```bash
cd docker
chmod +x build-image.sh
./build-image.sh latest
```

Vagy közvetlenül:

```bash
cd docker
docker build -f Dockerfile.zedin-ark-server -t zedinarkmanager/ark-server:latest .
```

## Fontos megjegyzések

1. **A buildelés után** a futó Docker konténereket újra kell indítani, hogy az új image-t használják
2. **A régi konténereket** le kell állítani és újra kell indítani:
   ```bash
   docker-compose down
   docker-compose up -d
   ```
3. **Vagy** ha egyedi konténereket használsz:
   ```bash
   docker stop zedin_asa_<server_id>
   docker start zedin_asa_<server_id>
   ```

## Ellenőrzés

Ellenőrizd, hogy az új image buildelődött:

```bash
docker images | grep zedinarkmanager/ark-server
```

Látnod kellene: `zedinarkmanager/ark-server:latest`

