# ZedinArkManager - FastAPI Telepítési útmutató

## Követelmények

- Python 3.8+
- MySQL/MariaDB adatbázis
- pip (Python package manager)

## Telepítési lépések

### 1. Projekt letöltése

```bash
git clone https://github.com/zedinke/ZedinSteamManager.git
cd ZedinSteamManager
```

### 2. Python függőségek telepítése

```bash
pip3 install -r requirements.txt
```

vagy

```bash
python3 -m pip install -r requirements.txt
```

**Megjegyzés:** Linux rendszereken általában `python3` és `pip3` a helyes parancsok.

### 3. Automatikus telepítés

```bash
python3 install.py
```

**Megjegyzés:** Ha a `python3` parancs nem található, ellenőrizd, hogy telepítve van-e a Python 3:

```bash
which python3
python3 --version
```

A script:
- Telepíti a függőségeket
- Létrehozza a konfigurációs fájlt
- Inicializálja az adatbázist

### 4. Manuális telepítés

Ha nem szeretnéd használni az automatikus telepítőt:

#### a) Konfiguráció létrehozása

Hozz létre egy `config/app.py` fájlt:

```python
config = {
    'db': {
        'host': 'localhost',
        'name': 'zedinarkmanager',
        'user': 'root',
        'pass': 'password',
    },
    'base_url': 'http://localhost:8000',
    'email': {
        'from': 'noreply@example.com',
        'from_name': 'ZedinArkManager',
    },
    'secret_key': 'your-secret-key-here',
    'token_expiry_days': 30,
    'notification_days_before_expiry': 5,
}
```

#### b) Adatbázis inicializálása

```bash
python3 -m app.database_init
```

### 5. Szerver indítása

```bash
python3 run.py
```

vagy

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Megjegyzés:** Ha a `python3` parancs nem található, próbáld meg `python`-nal.

## Elérés

A szerver indítása után:

```
http://YOUR_IP:8000
```

vagy

```
http://localhost:8000
```

## Alapértelmezett bejelentkezés

- **Email:** `admin@example.com`
- **Jelszó:** `admin123`

⚠️ **FONTOS:** Változtasd meg az első bejelentkezés után!

## Cron job beállítása

### Token lejárat ellenőrzés

```bash
crontab -e
```

Add hozzá:

```
0 0 * * * /usr/bin/python3 /path/to/zedinarkmanager/cron/check_token_expiry.py
```

### Automatikus repo frissítés

Az automatikus frissítés beállításához add hozzá a crontab-hoz:

```bash
crontab -e
```

**Napi frissítés (éjfélkor):**
```
0 0 * * * /usr/bin/python3 /path/to/zedinarkmanager/cron/auto_update.py
```

**Óránkénti frissítés:**
```
0 * * * * /usr/bin/python3 /path/to/zedinarkmanager/cron/auto_update.py
```

**30 percenkénti frissítés:**
```
*/30 * * * * /usr/bin/python3 /path/to/zedinarkmanager/cron/auto_update.py
```

**15 percenkénti frissítés:**
```
*/15 * * * * /usr/bin/python3 /path/to/zedinarkmanager/cron/auto_update.py
```

**Megjegyzés:** Cseréld ki a `/path/to/zedinarkmanager` részt a tényleges projekt útvonalára. Ha virtual environment-et használsz, használd a venv Python-ját:

```
*/30 * * * * /path/to/zedinarkmanager/venv/bin/python3 /path/to/zedinarkmanager/cron/auto_update.py
```

A frissítés log fájlja: `logs/auto_update.log`

## Fejlesztési mód

Auto-reload engedélyezése:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Produkciós futtatás

### Gunicorn használata

```bash
pip install gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Systemd service

Hozz létre egy `/etc/systemd/system/zedinarkmanager.service` fájlt:

```ini
[Unit]
Description=ZedinArkManager FastAPI Server
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/zedinarkmanager
ExecStart=/usr/bin/python3 /path/to/zedinarkmanager/run.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Indítás:

```bash
sudo systemctl enable zedinarkmanager
sudo systemctl start zedinarkmanager
```

## Hibaelhárítás

### "Module not found"

Telepítsd a függőségeket:
```bash
pip install -r requirements.txt
```

### Adatbázis kapcsolat hiba

Ellenőrizd a `config/app.py` fájlban az adatbázis beállításokat.

### Port már foglalt

Más portot használj:
```bash
python run.py --port 9000
```

