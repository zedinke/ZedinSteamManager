# Docker Izoláció és Kompatibilitás

## Áttekintés

A ZedinArkManager Docker image és konténerek **NEM befolyásolják** más Linux felhasználók által futtatott Docker környezetét, mert:

## 1. Container Nevek

- **Prefix használata**: `zedin_asa_{server.id}`
- **Egyediség**: Minden container neve egyedi, mert a szerver ID alapján generálódik
- **Ütközés elkerülése**: A `zedin_` prefix biztosítja, hogy ne ütközzön más rendszerekkel (pl. POK Manager `asa_` prefix)

## 2. Docker Image-ek

- **Image név**: `zedinarkmanager/ark-server:latest`
- **Globális tárolás**: A Docker image-ek globálisan vannak tárolva (`/var/lib/docker/` vagy user namespace)
- **Megosztás**: Ha másik felhasználó is build-eli ugyanazt az image-t, az nem probléma, mert a Docker image-ek megoszthatók
- **Izoláció**: Ha rootless Docker-t használsz, akkor teljesen izoláltak a felhasználók között

## 3. Volume Mount-ok

- **Fájlrendszer szintű**: A volume mount-ok fájlrendszer szintűek
- **Jogosultságok**: A fájlok a saját felhasználó mappájában vannak (`Servers/server_{id}/`)
- **Hozzáférés**: Másik felhasználó nem fér hozzá a fájlokhoz (kivéve, ha explicit jogosultságot adsz)

## 4. Portok

- **Automatikus port hozzárendelés**: A rendszer automatikusan talál szabad portot
- **Ütközés ellenőrzés**: A `port_service.py` ellenőrzi, hogy a port elérhető-e
- **Adatbázis alapú**: A portok az adatbázisból kerülnek lekérésre, így minden felhasználó saját portokat használ

## 5. User ID (UID)

- **Konténer belső**: A Dockerfile-ban `zedin` user UID 1000, de ez **csak a konténeren belül** van
- **Host izoláció**: Ez **NEM ütközik** a host rendszer felhasználóival, mert a konténer izolált
- **Volume mount jogosultságok**: A volume mount-oknál a host fájlok jogosultságai számítanak, nem a konténer belső UID

## 6. Docker Daemon

- **Rootless Docker**: Ha rootless Docker-t használsz, akkor minden felhasználó saját Docker daemon-t futtat, teljesen izolálva
- **Root Docker**: Ha root Docker-t használsz, akkor a container nevek és portok ütközhetnek, de a `zedin_` prefix és az automatikus port hozzárendelés ezt megelőzi

## Összefoglalás

✅ **Biztonságos**: A container nevek egyediek (`zedin_asa_{server.id}`)
✅ **Izolált**: A volume mount-ok fájlrendszer szintűek, jogosultságok alapján
✅ **Port ütközések elkerülve**: Automatikus port hozzárendelés
✅ **Image megosztás**: A Docker image-ek megoszthatók, nem okoznak problémát
✅ **User ID**: A konténer belső UID nem ütközik a host felhasználókkal

## Ajánlások

1. **Rootless Docker használata**: Ha lehetséges, használj rootless Docker-t a teljes izolációért
2. **Jogosultságok**: Ügyelj a volume mount fájlok jogosultságaira
3. **Port ellenőrzés**: A rendszer automatikusan ellenőrzi a portokat, de manuálisan is ellenőrizheted
4. **Container nevek**: A `zedin_` prefix biztosítja, hogy ne ütközzön más rendszerekkel

