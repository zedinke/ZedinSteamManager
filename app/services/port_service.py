"""
Port kezelő szolgáltatás - automatikus port hozzárendelés
"""

import socket
import subprocess
import psutil
from typing import Optional, List
from app.config import settings

def check_port_available(port: int) -> bool:
    """Ellenőrzi, hogy egy port elérhető-e"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('0.0.0.0', port))
            return True
        except OSError:
            return False

def get_used_ports() -> List[int]:
    """Visszaadja az összes használt portot"""
    used_ports = []
    
    # Psutil használata a futó folyamatokhoz
    try:
        for conn in psutil.net_connections(kind='inet'):
            if conn.status == psutil.CONN_LISTEN and conn.laddr:
                port = conn.laddr.port
                if port not in used_ports:
                    used_ports.append(port)
    except (psutil.AccessDenied, AttributeError):
        # Ha nincs jogosultság, akkor netstat-ot használunk
        try:
            result = subprocess.run(
                ['netstat', '-tuln'],
                capture_output=True,
                text=True,
                timeout=5
            )
            for line in result.stdout.split('\n'):
                if 'LISTEN' in line:
                    parts = line.split()
                    if len(parts) > 3:
                        addr = parts[3]
                        if ':' in addr:
                            port = int(addr.split(':')[-1])
                            if port not in used_ports:
                                used_ports.append(port)
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            pass
    
    return sorted(used_ports)

def find_available_port(start_port: int = None, max_attempts: int = 100) -> Optional[int]:
    """
    Talál egy elérhető portot
    
    Args:
        start_port: Kezdő port (ha None, akkor a legmagasabb használt port + 2)
        max_attempts: Maximum próbálkozások száma
    
    Returns:
        Elérhető port szám vagy None
    """
    if start_port is None:
        # Alapértelmezett porttól kezdünk
        start_port = settings.ark_default_port
    
    # Először ellenőrizzük a használt portokat
    used_ports = get_used_ports()
    
    # Ha van használt port, akkor a legmagasabb + 2-től kezdünk
    if used_ports:
        highest_port = max(used_ports)
        start_port = max(start_port, highest_port + 2)
    
    # Keressük az első elérhető portot
    for i in range(max_attempts):
        port = start_port + i
        if check_port_available(port):
            return port
    
    return None

def get_query_port(game_port: int) -> int:
    """
    Query port számítása a game port alapján
    Ark esetén általában game_port + 1, de ellenőrizzük, hogy elérhető-e
    """
    query_port = game_port + 1
    
    # Ha nem elérhető, keressünk egy másikat
    if not check_port_available(query_port):
        # Próbáljuk meg a game_port + 2-t
        query_port = game_port + 2
        if not check_port_available(query_port):
            # Ha ez sem elérhető, keressünk egy szabad portot
            available = find_available_port(game_port + 1)
            if available:
                query_port = available
            else:
                # Végül visszaadjuk az eredeti + 1-et, a rendszer majd kezeli
                query_port = game_port + 1
    
    return query_port

