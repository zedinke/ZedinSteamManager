# ZedinArkManager

Játék szerver kezelő manager rendszer - FastAPI alapú implementáció.

## Funkciók

- ✅ Moduláris telepítő rendszer
- ✅ Weboldali manager felület
- ✅ Jogosultság kezelés (Manager Admin, Server Admin, Admin, User)
- ✅ Token rendszer aktiválással
- ✅ Értesítési rendszer
- ✅ Email hitelesítés
- ✅ IP:port alapú elérés

## Telepítés

### 1. Függőségek telepítése

```bash
pip3 install -r requirements.txt
```

vagy

```bash
python3 -m pip install -r requirements.txt
```

### 2. Konfiguráció beállítása

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

### 3. Adatbázis létrehozása

```bash
python3 -m app.database_init
```

vagy

```bash
python3 install.py
```

### 4. Szerver indítása

```bash
python3 run.py
```

vagy

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Megjegyzés:** Ha a `python3` parancs nem található, próbáld meg `python`-nal, vagy telepítsd a Python 3-at.

## Elérés

A szerver indítása után:

```
http://YOUR_IP:8000
```

## Alapértelmezett bejelentkezés

- **Email:** `admin@example.com`
- **Jelszó:** `admin123`

⚠️ **FONTOS:** Változtasd meg az első bejelentkezés után!

## Projekt struktúra

```
zedinarkmanager/
├── app/
│   ├── main.py              # FastAPI fő alkalmazás
│   ├── config.py            # Konfiguráció
│   ├── database.py          # Adatbázis modell
│   ├── dependencies.py      # FastAPI dependencies
│   ├── routers/             # Route handlers
│   │   ├── auth.py
│   │   ├── dashboard.py
│   │   ├── tokens.py
│   │   ├── admin.py
│   │   └── notifications.py
│   └── services/            # Üzleti logika
│       ├── auth_service.py
│       ├── email_service.py
│       ├── token_service.py
│       └── notification_service.py
├── templates/               # Jinja2 template-ek
├── static/                  # Statikus fájlok (CSS, JS)
├── config/                  # Konfigurációs fájlok
└── requirements.txt         # Python függőségek
```

## Követelmények

- Python 3.8+
- MySQL/MariaDB
- FastAPI és függőségek (requirements.txt)

