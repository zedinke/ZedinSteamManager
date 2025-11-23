"""
Konfiguráció kezelés
"""

from pydantic_settings import BaseSettings
from pathlib import Path
import os
import secrets

BASE_DIR = Path(__file__).parent.parent

class Settings(BaseSettings):
    # Adatbázis
    db_host: str = "localhost"
    db_name: str = "zedinarkmanager"
    db_user: str = "root"
    db_pass: str = ""
    
    # Weboldal
    base_url: str = "http://localhost:8000"
    
    # Email
    email_from: str = "noreply@example.com"
    email_from_name: str = "ZedinArkManager"
    smtp_host: str = "localhost"
    smtp_port: int = 25
    smtp_user: str = ""
    smtp_pass: str = ""
    
    # Biztonság
    secret_key: str = ""
    token_expiry_days: int = 30
    notification_days_before_expiry: int = 5
    
    # JWT
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    
    # Session
    session_secret_key: str = ""
    
    # Ark Server
    ark_base_path: str = "/opt/ark_servers"  # Alap útvonal az Ark szerverekhez
    ark_install_path: str = "/opt/ark_server_files"  # Telepített szerverfájlok útvonala
    ark_serverfiles_base: str = "/home/ai_developer/ZedinSteamManager/Server/ArkAscended/ServerFiles"  # Felhasználó-alapú serverfiles mappák alap útvonala
    ark_default_port: int = 7777  # Alapértelmezett port
    ark_default_query_port: int = 27015  # Alapértelmezett query port
    
    class Config:
        env_file = BASE_DIR / ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

def load_settings() -> Settings:
    """Konfiguráció betöltése"""
    settings = Settings()
    
    # Ha nincs secret key, generálj egyet
    if not settings.secret_key:
        settings.secret_key = secrets.token_urlsafe(32)
    
    if not settings.jwt_secret_key:
        settings.jwt_secret_key = settings.secret_key
    
    if not settings.session_secret_key:
        settings.session_secret_key = secrets.token_urlsafe(32)
    
    # Konfigurációs fájl betöltése ha létezik
    config_file = BASE_DIR / "config" / "app.py"
    if config_file.exists():
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("config", config_file)
            config_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(config_module)
            
            if hasattr(config_module, 'config'):
                config_dict = config_module.config
                
                if 'db' in config_dict:
                    settings.db_host = config_dict['db'].get('host', settings.db_host)
                    settings.db_name = config_dict['db'].get('name', settings.db_name)
                    settings.db_user = config_dict['db'].get('user', settings.db_user)
                    settings.db_pass = config_dict['db'].get('pass', settings.db_pass)
                
                if 'base_url' in config_dict:
                    settings.base_url = config_dict['base_url']
                
                if 'email' in config_dict:
                    settings.email_from = config_dict['email'].get('from', settings.email_from)
                    settings.email_from_name = config_dict['email'].get('from_name', settings.email_from_name)
                    # SMTP beállítások is lehetnek a config-ban
                    if 'smtp' in config_dict['email']:
                        smtp_config = config_dict['email']['smtp']
                        settings.smtp_host = smtp_config.get('host', settings.smtp_host)
                        settings.smtp_port = smtp_config.get('port', settings.smtp_port)
                        settings.smtp_user = smtp_config.get('user', settings.smtp_user)
                        settings.smtp_pass = smtp_config.get('pass', settings.smtp_pass)
                        print(f"[CONFIG] SMTP beállítások betöltve: {settings.smtp_host}:{settings.smtp_port}, user: {settings.smtp_user}")
                    else:
                        print(f"[CONFIG] Figyelmeztetés: config/app.py-ban nincs 'smtp' beállítás az 'email' objektumban")
                else:
                    print(f"[CONFIG] Figyelmeztetés: config/app.py-ban nincs 'email' beállítás")
                
                if 'secret_key' in config_dict:
                    settings.secret_key = config_dict['secret_key']
                    settings.jwt_secret_key = config_dict['secret_key']
                
                if 'token_expiry_days' in config_dict:
                    settings.token_expiry_days = config_dict['token_expiry_days']
                
                if 'notification_days_before_expiry' in config_dict:
                    settings.notification_days_before_expiry = config_dict['notification_days_before_expiry']
        except Exception as e:
            import traceback
            print(f"[CONFIG] Config file load error: {e}")
            print(f"[CONFIG] Traceback: {traceback.format_exc()}")
    else:
        print(f"[CONFIG] Figyelmeztetés: config/app.py fájl nem található: {config_file}")
    
    return settings

settings = load_settings()
