#!/usr/bin/env python3
"""
ZedinArkManager - FastAPI telepítő script
"""

import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent

def print_header(text):
    print(f"\n{'='*60}")
    print(f"{text:^60}")
    print(f"{'='*60}\n")

def print_success(text):
    print(f"✓ {text}")

def print_error(text):
    print(f"✗ {text}")

def print_info(text):
    print(f"ℹ {text}")

def print_warning(text):
    print(f"⚠ {text}")

def check_command(cmd):
    try:
        subprocess.run([cmd, '--version'], capture_output=True, check=True, timeout=5)
        return True
    except:
        return False

def setup_venv():
    """Virtual environment létrehozása"""
    venv_dir = BASE_DIR / "venv"
    
    if venv_dir.exists():
        print_info("Virtual environment már létezik")
        return True
    
    print_info("Virtual environment létrehozása...")
    python_cmd = "python3" if check_command("python3") else sys.executable
    
    try:
        subprocess.run([python_cmd, "-m", "venv", str(venv_dir)], check=True)
        print_success("Virtual environment létrehozva")
        return True
    except Exception as e:
        print_error(f"Virtual environment létrehozása sikertelen: {e}")
        print_info("Próbáld meg telepíteni: sudo apt-get install python3-venv")
        return False

def get_python_cmd():
    """Python parancs lekérése (venv-ben vagy rendszerben)"""
    venv_python = BASE_DIR / "venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    
    # Ha nincs venv, próbáljuk meg python3-at
    if check_command("python3"):
        return "python3"
    
    return sys.executable

def install_dependencies():
    print_info("Python függőségek telepítése...")
    
    # Virtual environment beállítása
    if not setup_venv():
        print_warning("Virtual environment nélkül folytatás (nem ajánlott)")
    
    python_cmd = get_python_cmd()
    
    try:
        # pip install a venv-ben vagy rendszerben
        subprocess.run([python_cmd, "-m", "pip", "install", "--upgrade", "pip"], check=True)
        subprocess.run([python_cmd, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
        print_success("Függőségek telepítve")
        return True
    except Exception as e:
        print_error(f"Függőségek telepítése sikertelen: {e}")
        print_info("\nHa 'externally-managed-environment' hibát kapsz:")
        print_info("1. Telepítsd a python3-venv csomagot: sudo apt-get install python3-venv")
        print_info("2. Futtasd újra a telepítőt")
        return False

def create_config():
    print_info("Konfigurációs fájl beállítása...")
    
    config_dir = BASE_DIR / "config"
    config_dir.mkdir(exist_ok=True)
    
    config_file = config_dir / "app.py"
    
    if config_file.exists():
        response = input("config/app.py már létezik. Felül szeretnéd írni? (i/n): ").lower()
        if response != 'i':
            print_info("Konfigurációs fájl létrehozása kihagyva")
            return True
    
    print("\nAdatbázis beállítások:")
    db_host = input("Adatbázis hoszt [localhost]: ").strip() or "localhost"
    db_name = input("Adatbázis név: ").strip()
    db_user = input("Adatbázis felhasználó: ").strip()
    db_pass = input("Adatbázis jelszó: ").strip()
    
    print("\nWeboldal beállítások:")
    base_url = input("Base URL (pl. http://localhost:8000): ").strip()
    
    print("\nEmail beállítások:")
    email_from = input("Email küldő cím [noreply@example.com]: ").strip() or "noreply@example.com"
    email_from_name = input("Email küldő név [ZedinArkManager]: ").strip() or "ZedinArkManager"
    
    import secrets
    secret_key = secrets.token_urlsafe(32)
    
    config_content = f'''config = {{
    'db': {{
        'host': '{db_host}',
        'name': '{db_name}',
        'user': '{db_user}',
        'pass': '{db_pass}',
    }},
    'base_url': '{base_url}',
    'email': {{
        'from': '{email_from}',
        'from_name': '{email_from_name}',
    }},
    'secret_key': '{secret_key}',
    'token_expiry_days': 30,
    'notification_days_before_expiry': 5,
}}
'''
    
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(config_content)
        print_success(f"Konfigurációs fájl létrehozva: {config_file}")
        return True
    except Exception as e:
        print_error(f"Konfigurációs fájl létrehozása sikertelen: {e}")
        return False

def init_database():
    print_info("Adatbázis inicializálása...")
    try:
        python_cmd = get_python_cmd()
        subprocess.run([python_cmd, "-m", "app.database_init"], check=True)
        print_success("Adatbázis inicializálva")
        return True
    except Exception as e:
        print_error(f"Adatbázis inicializálás sikertelen: {e}")
        return False

def main():
    print_header("ZedinArkManager - FastAPI Telepítő")
    
    print_info(f"Projekt mappa: {BASE_DIR}")
    
    # Függőségek telepítése
    if not install_dependencies():
        sys.exit(1)
    
    # Konfiguráció
    if not create_config():
        sys.exit(1)
    
    # Adatbázis inicializálás
    if not init_database():
        sys.exit(1)
    
    print_header("Telepítés befejezve!")
    print_success("A ZedinArkManager sikeresen telepítve lett!")
    
    python_cmd = get_python_cmd()
    venv_python = BASE_DIR / "venv" / "bin" / "python"
    
    print("\nKövetkező lépések:")
    if venv_python.exists():
        print(f"1. Aktiváld a virtual environment-et:")
        print(f"   source venv/bin/activate")
        print(f"2. Indítsd el a szervert:")
        print(f"   {python_cmd} run.py")
        print(f"   vagy: uvicorn app.main:app --host 0.0.0.0 --port 8000")
    else:
        python_sys = "python3" if check_command("python3") else "python"
        print(f"1. Indítsd el a szervert:")
        print(f"   {python_sys} run.py")
        print(f"   vagy: uvicorn app.main:app --host 0.0.0.0 --port 8000")
    
    print("3. Nyisd meg a böngészőben a base_url-t")
    print("4. Jelentkezz be az alapértelmezett admin fiókkal:")
    print("   - Email: admin@example.com")
    print("   - Jelszó: admin123")
    print("5. ⚠️  FONTOS: Változtasd meg az admin jelszót az első bejelentkezés után!")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTelepítés megszakítva.")
        sys.exit(1)
    except Exception as e:
        print_error(f"\nVáratlan hiba: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

