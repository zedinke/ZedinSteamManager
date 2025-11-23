"""
Port kezelő szolgáltatás - automatikus port hozzárendelés
"""

import socket
import subprocess
import psutil
from typing import Optional, List
from sqlalchemy.orm import Session
from app.config import settings
from app.database import ServerInstance

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

def get_ark_server_ports(db: Session) -> List[int]:
    """
    Visszaadja az összes Ark szerver portját az adatbázisból
    Csak a 7777-es port környékén lévő portokat (Ark szerver portok)
    """
    ark_ports = []
    
    try:
        # Összes Ark szerver port lekérése
        servers = db.query(ServerInstance.port).filter(
            ServerInstance.port.isnot(None)
        ).all()
        
        for server in servers:
            if server.port and server.port >= settings.ark_default_port:
                # Csak az Ark alap port (7777) vagy annál nagyobb portokat vesszük figyelembe
                ark_ports.append(server.port)
    except Exception:
        # Ha hiba van, üres listát adunk vissza
        pass
    
    return sorted(ark_ports)

def find_available_port(start_port: int = None, max_attempts: int = 100, db: Session = None) -> Optional[int]:
    """
    Talál egy elérhető Ark szerver portot (7777-től kezdve)
    
    Args:
        start_port: Kezdő port (ha None, akkor a legmagasabb használt Ark port + 2)
        max_attempts: Maximum próbálkozások száma
        db: Adatbázis session (opcionális, ha nincs megadva, akkor csak a rendszer portokat nézi)
    
    Returns:
        Elérhető port szám vagy None
    """
    if start_port is None:
        # Alapértelmezett Ark porttól kezdünk (7777)
        start_port = settings.ark_default_port
    
    # Először ellenőrizzük az Ark szerverek portjait az adatbázisból
    if db:
        ark_ports = get_ark_server_ports(db)
        if ark_ports:
            # A legmagasabb Ark port + 2-től kezdünk
            highest_ark_port = max(ark_ports)
            start_port = max(start_port, highest_ark_port + 2)
        else:
            # Ha nincs Ark szerver, akkor az alap porttól kezdünk
            start_port = settings.ark_default_port
    else:
        # Ha nincs db session, akkor a rendszer portokat nézzük
        # De csak azokat, amelyek az Ark alap port környékén vannak
        used_ports = get_used_ports()
        ark_related_ports = [p for p in used_ports if p >= settings.ark_default_port]
        
        if ark_related_ports:
            highest_port = max(ark_related_ports)
            start_port = max(start_port, highest_port + 2)
    
    # Keressük az első elérhető portot
    for i in range(max_attempts):
        port = start_port + i
        if check_port_available(port):
            return port
    
    return None

def get_query_port(game_port: int, db: Session = None) -> int:
    """
    Query port számítása a game port alapján
    Ark Survival Ascended esetén általában game_port + 2
    """
    # Ark Survival Ascended: query port = game_port + 2
    query_port = game_port + 2
    
    # Ellenőrizzük, hogy elérhető-e
    if not check_port_available(query_port):
        # Ha nem elérhető, keressünk egy szabad portot az adatbázisból
        if db:
            # Lekérjük az összes használt query portot
            used_query_ports = []
            try:
                from app.database import ServerInstance
                servers = db.query(ServerInstance.query_port).filter(
                    ServerInstance.query_port.isnot(None)
                ).all()
                used_query_ports = [s.query_port for s in servers if s.query_port]
            except Exception:
                pass
            
            # Keressünk egy szabad portot (game_port + 2, +3, +4, stb.)
            for offset in range(2, 20):
                candidate_port = game_port + offset
                if candidate_port not in used_query_ports and check_port_available(candidate_port):
                    query_port = candidate_port
                    break
        else:
            # Ha nincs db session, próbáljuk meg a game_port + 3, +4, stb.
            for offset in range(3, 20):
                candidate_port = game_port + offset
                if check_port_available(candidate_port):
                    query_port = candidate_port
                    break
    
    return query_port

def get_rcon_port(game_port: int, db: Session = None) -> int:
    """
    RCON port számítása
    Ark Survival Ascended esetén alapértelmezett: 27015
    Ha foglalt, akkor 27015-től keresünk szabad portot
    """
    from app.config import settings
    
    # Ark Survival Ascended: RCON port alapértelmezett = 27015
    default_rcon_port = 27015
    rcon_port = default_rcon_port
    
    # Ellenőrizzük, hogy elérhető-e
    if not check_port_available(rcon_port):
        # Ha nem elérhető, keressünk egy szabad portot
        if db:
            # Lekérjük az összes használt RCON portot
            used_rcon_ports = []
            try:
                from app.database import ServerInstance
                servers = db.query(ServerInstance.rcon_port).filter(
                    ServerInstance.rcon_port.isnot(None)
                ).all()
                used_rcon_ports = [s.rcon_port for s in servers if s.rcon_port]
            except Exception:
                pass
            
            # Query port lekérése (game_port + 2)
            query_port = game_port + 2
            
            # Keressünk egy szabad portot 27015-től kezdve
            # Maximum 100 portot próbálunk meg
            for offset in range(0, 100):
                candidate_port = default_rcon_port + offset
                # Ne legyen query_port és ne legyen használt
                if candidate_port != query_port and candidate_port not in used_rcon_ports and check_port_available(candidate_port):
                    rcon_port = candidate_port
                    break
        else:
            # Ha nincs db session, próbáljuk meg 27015-től
            query_port = game_port + 2
            for offset in range(0, 100):
                candidate_port = default_rcon_port + offset
                if candidate_port != query_port and check_port_available(candidate_port):
                    rcon_port = candidate_port
                    break
    
    return rcon_port

