"""
SMTP konfiguráció beolvasása Exim konfigurációból
"""

from pathlib import Path
import os

def read_exim_smtp_relay_config(domain: str = None) -> dict:
    """
    Exim SMTP relay konfiguráció beolvasása
    
    Args:
        domain: Domain név (opcionális, domain-specifikus konfigurációhoz)
    
    Returns:
        dict: SMTP beállítások (host, port, user, pass) vagy None
    """
    config = {}
    
    # Domain-specifikus konfiguráció először
    if domain:
        domain_config = Path(f"/etc/exim4/domains/{domain}/smtp_relay.conf")
        if domain_config.exists():
            return _parse_smtp_relay_file(domain_config)
    
    # Globális konfiguráció
    global_config = Path("/etc/exim4/smtp_relay.conf")
    if global_config.exists():
        return _parse_smtp_relay_file(global_config)
    
    return None

def _parse_smtp_relay_file(config_file: Path) -> dict:
    """SMTP relay konfigurációs fájl feldolgozása"""
    config = {}
    
    try:
        with open(config_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Formátum: kulcs: érték
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if key == 'host':
                        config['host'] = value
                    elif key == 'port':
                        try:
                            config['port'] = int(value)
                        except ValueError:
                            config['port'] = 25
                    elif key == 'user':
                        config['user'] = value
                    elif key == 'pass':
                        config['pass'] = value
    except Exception as e:
        print(f"Error reading SMTP relay config: {e}")
        return None
    
    return config if config else None

def get_smtp_settings(domain: str = None) -> dict:
    """
    SMTP beállítások lekérése (Exim konfigurációból vagy alapértelmezett)
    
    Returns:
        dict: SMTP beállítások
    """
    # Próbáljuk meg az Exim konfigurációt
    exim_config = read_exim_smtp_relay_config(domain)
    
    if exim_config:
        return {
            'host': exim_config.get('host', 'localhost'),
            'port': exim_config.get('port', 25),
            'user': exim_config.get('user', ''),
            'pass': exim_config.get('pass', ''),
            'use_tls': exim_config.get('port', 25) in [465, 587]  # TLS portok
        }
    
    # Alapértelmezett beállítások
    return {
        'host': 'localhost',
        'port': 25,
        'user': '',
        'pass': '',
        'use_tls': False
    }

