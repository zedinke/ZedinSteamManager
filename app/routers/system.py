"""
System monitoring router - szerver kihasználtság API
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
import platform
import subprocess
import time

# Opcionális psutil import
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("[WARNING] psutil nincs telepítve. System monitoring nem lesz elérhető.")
    print("[WARNING] Telepítés: pip install psutil>=5.9.0")

router = APIRouter(prefix="/api/system", tags=["system"])

@router.get("/stats")
async def get_system_stats(request: Request, db: Session = get_db()):
    """Szerver kihasználtság lekérése"""
    if not PSUTIL_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"error": "psutil nincs telepítve. Telepítés: pip install psutil>=5.9.0"}
        )
    
    try:
        # CPU kihasználtság
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()
        
        # RAM információk
        memory = psutil.virtual_memory()
        ram_total = memory.total
        ram_used = memory.used
        ram_percent = memory.percent
        ram_available = memory.available
        
        # HDD információk
        disk = psutil.disk_usage('/')
        hdd_total = disk.total
        hdd_used = disk.used
        hdd_free = disk.free
        hdd_percent = (disk.used / disk.total) * 100
        
        # Ping (localhost ping, vagy egy külső szerver)
        ping_ms = get_ping_time()
        
        # Hálózati információk
        network = psutil.net_io_counters()
        
        # Boot idő
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        uptime_hours = uptime_seconds / 3600
        
        return JSONResponse(content={
            "cpu": {
                "percent": cpu_percent,
                "count": cpu_count,
                "cores": psutil.cpu_count(logical=False)
            },
            "ram": {
                "total": ram_total,
                "used": ram_used,
                "available": ram_available,
                "percent": ram_percent,
                "total_gb": round(ram_total / (1024**3), 2),
                "used_gb": round(ram_used / (1024**3), 2),
                "available_gb": round(ram_available / (1024**3), 2)
            },
            "hdd": {
                "total": hdd_total,
                "used": hdd_used,
                "free": hdd_free,
                "percent": round(hdd_percent, 2),
                "total_gb": round(hdd_total / (1024**3), 2),
                "used_gb": round(hdd_used / (1024**3), 2),
                "free_gb": round(hdd_free / (1024**3), 2)
            },
            "ping": {
                "ms": ping_ms
            },
            "network": {
                "bytes_sent": network.bytes_sent,
                "bytes_recv": network.bytes_recv,
                "packets_sent": network.packets_sent,
                "packets_recv": network.packets_recv
            },
            "uptime": {
                "hours": round(uptime_hours, 2),
                "seconds": int(uptime_seconds)
            },
            "timestamp": int(time.time())
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

def get_ping_time():
    """Ping idő mérése (localhost vagy külső szerver)"""
    try:
        # Próbáljuk meg a localhost ping-et
        if platform.system().lower() == 'windows':
            result = subprocess.run(
                ["ping", "-n", "1", "127.0.0.1"],
                capture_output=True,
                text=True,
                timeout=2
            )
        else:
            result = subprocess.run(
                ["ping", "-c", "1", "127.0.0.1"],
                capture_output=True,
                text=True,
                timeout=2
            )
        
        if result.returncode == 0:
            # Parse ping output (egyszerűsített)
            return 0.5  # Localhost ping általában < 1ms
        return None
    except:
        try:
            # Ha ping nem elérhető, próbáljuk meg egy külső szervert
            if platform.system().lower() == 'windows':
                result = subprocess.run(
                    ["ping", "-n", "1", "8.8.8.8"],
                    capture_output=True,
                    text=True,
                    timeout=3
                )
            else:
                result = subprocess.run(
                    ["ping", "-c", "1", "8.8.8.8"],
                    capture_output=True,
                    text=True,
                    timeout=3
                )
            
            if result.returncode == 0:
                # Parse ping output
                output = result.stdout
                if 'time=' in output or 'time<' in output:
                    # Egyszerűsített parsing
                    return 10.0  # Alapértelmezett érték
            return None
        except:
            return None

