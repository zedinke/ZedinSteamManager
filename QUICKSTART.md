# Gyors kezdés - ZedinArkManager

## Linux/Mac telepítés

### 1. Python 3 ellenőrzése

```bash
python3 --version
```

Ha nincs telepítve, telepítsd:
- **Ubuntu/Debian:** `sudo apt-get install python3 python3-pip`
- **CentOS/RHEL:** `sudo yum install python3 python3-pip`
- **macOS:** `brew install python3`

### 2. Telepítés (automatikus virtual environment-tel)

```bash
python3 install.py
```

A script automatikusan:
- Létrehozza a virtual environment-et (`venv/`)
- Telepíti a függőségeket
- Létrehozza a konfigurációs fájlt
- Inicializálja az adatbázist

**Ha "externally-managed-environment" hibát kapsz:**

```bash
# Telepítsd a python3-venv csomagot
sudo apt-get install python3-venv

# Futtasd újra a telepítőt
python3 install.py
```

A script:
- Telepíti a függőségeket
- Létrehozza a konfigurációs fájlt (`config/app.py`)
- Inicializálja az adatbázist

### 4. Szerver indítása

**Virtual environment-tel (ajánlott):**

```bash
source venv/bin/activate
python run.py
```

vagy használd a start scriptet:

```bash
chmod +x start.sh
./start.sh
```

**Vagy közvetlenül:**

```bash
venv/bin/python run.py
```

**Vagy uvicorn-nal:**

```bash
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 5. Elérés

Nyisd meg a böngészőben:
```
http://YOUR_SERVER_IP:8000
```

### 6. Bejelentkezés

- **Email:** `admin@example.com`
- **Jelszó:** `admin123`

⚠️ **FONTOS:** Változtasd meg az admin jelszót az első bejelentkezés után!

## Windows telepítés

### 1. Python telepítése

Töltsd le és telepítsd a Python 3-at: https://www.python.org/downloads/

### 2. Függőségek telepítése

```cmd
pip install -r requirements.txt
```

### 3. Telepítés

```cmd
python install.py
```

### 4. Szerver indítása

```cmd
python run.py
```

## Hibaelhárítás

### "python: command not found"

**Linux/Mac:**
```bash
python3 install.py
```

**Windows:**
```cmd
python install.py
```

### "externally-managed-environment" hiba

Ez azt jelenti, hogy a rendszer nem engedélyezi a globális pip telepítést.

**Megoldás:**

```bash
# Telepítsd a python3-venv csomagot
sudo apt-get install python3-venv

# Futtasd újra a telepítőt (automatikusan létrehozza a venv-et)
python3 install.py
```

A telepítő automatikusan létrehozza a `venv/` mappát és abba telepíti a függőségeket.

### "Module not found"

Telepítsd a függőségeket:
```bash
pip3 install -r requirements.txt
```

### Adatbázis kapcsolat hiba

Ellenőrizd a `config/app.py` fájlban az adatbázis beállításokat.

