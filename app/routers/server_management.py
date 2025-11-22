"""
Server Management router - Manager Admin szerverkezelés
"""

from fastapi import APIRouter, Request, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db, User
from app.dependencies import require_manager_admin
from fastapi.templating import Jinja2Templates
from pathlib import Path
import subprocess
import os
import json
import threading
import queue
import time

router = APIRouter(prefix="/admin/server", tags=["server_management"])

# Template-ek inicializálása
BASE_DIR = Path(__file__).parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# SteamCMD mappa
STEAMCMD_DIR = BASE_DIR / "Server" / "SteamCMD"
STEAMCMD_BIN = STEAMCMD_DIR / "steamcmd.sh" if os.name != 'nt' else STEAMCMD_DIR / "steamcmd.exe"

# Folyamatok tárolása (process_id -> process)
active_processes = {}
process_outputs = {}  # process_id -> queue

@router.get("/steamcmd", response_class=HTMLResponse)
async def steamcmd_page(
    request: Request,
    db: Session = Depends(get_db)
):
    """SteamCMD kezelő oldal"""
    current_user = require_manager_admin(request, db)
    
    # Ellenőrizzük, hogy a SteamCMD telepítve van-e
    is_installed = STEAMCMD_BIN.exists() if STEAMCMD_BIN else False
    steamcmd_version = None
    
    if is_installed:
        try:
            # Próbáljuk meg lekérni a verziót
            result = subprocess.run(
                [str(STEAMCMD_BIN), "+quit"],
                capture_output=True,
                text=True,
                timeout=10
            )
            # A verzió általában a kimenetben van
            for line in result.stdout.split('\n'):
                if 'Steam' in line and 'version' in line.lower():
                    steamcmd_version = line.strip()
                    break
        except:
            pass
    
    return templates.TemplateResponse("admin/server/steamcmd.html", {
        "request": request,
        "current_user": current_user,
        "is_installed": is_installed,
        "steamcmd_version": steamcmd_version,
        "steamcmd_path": str(STEAMCMD_DIR)
    })

@router.post("/steamcmd/install")
async def install_steamcmd(
    request: Request,
    db: Session = Depends(get_db)
):
    """SteamCMD telepítése"""
    current_user = require_manager_admin(request, db)
    
    # Ellenőrizzük, hogy már telepítve van-e
    if STEAMCMD_BIN.exists():
        return JSONResponse({
            "success": False,
            "message": "SteamCMD már telepítve van"
        })
    
    # Process ID generálása
    import uuid
    process_id = str(uuid.uuid4())
    
    # Output queue létrehozása
    output_queue = queue.Queue()
    process_outputs[process_id] = output_queue
    
    def install_process():
        """SteamCMD telepítő folyamat"""
        try:
            # Mappa létrehozása
            output_queue.put("[INFO] SteamCMD mappa létrehozása...\n")
            STEAMCMD_DIR.mkdir(parents=True, exist_ok=True)
            output_queue.put(f"[INFO] Mappa: {STEAMCMD_DIR}\n")
            
            # Linux/Unix rendszerek
            if os.name != 'nt':
                output_queue.put("[INFO] Linux/Unix rendszer észlelve\n")
                
                # SteamCMD letöltése
                output_queue.put("[INFO] SteamCMD letöltése...\n")
                download_cmd = "curl -sqL 'https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz' -o steamcmd.tar.gz"
                download_process = subprocess.Popen(
                    download_cmd,
                    shell=True,
                    cwd=str(STEAMCMD_DIR),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                # Live output olvasása
                for line in download_process.stdout:
                    output_queue.put(f"[DOWNLOAD] {line}")
                download_process.wait()
                
                if download_process.returncode != 0:
                    output_queue.put("[ERROR] Letöltés sikertelen!\n")
                    return
                
                output_queue.put("[INFO] Letöltés befejezve\n")
                output_queue.put("[INFO] Fájlok kicsomagolása...\n")
                
                # Kicsomagolás
                extract_process = subprocess.Popen(
                    "tar zxvf steamcmd.tar.gz",
                    shell=True,
                    cwd=str(STEAMCMD_DIR),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                for line in extract_process.stdout:
                    output_queue.put(f"[EXTRACT] {line}")
                extract_process.wait()
                
                if extract_process.returncode != 0:
                    output_queue.put("[ERROR] Kicsomagolás sikertelen!\n")
                    return
                
                output_queue.put("[INFO] Jogosultságok beállítása...\n")
                
                # Jogosultságok beállítása
                chmod_process = subprocess.run(
                    "chmod +x steamcmd.sh",
                    shell=True,
                    cwd=str(STEAMCMD_DIR),
                    capture_output=True,
                    text=True
                )
                
                if chmod_process.returncode != 0:
                    output_queue.put(f"[WARNING] Jogosultság beállítás: {chmod_process.stderr}\n")
                else:
                    output_queue.put("[INFO] Jogosultságok beállítva\n")
            else:
                # Windows rendszerek
                steamcmd_url = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
                output_queue.put(f"[INFO] SteamCMD letöltése Windows rendszerre...\n")
                output_queue.put("[ERROR] Windows telepítés még nincs implementálva\n")
                return
            
            # Ellenőrzés
            output_queue.put("[INFO] Telepítés ellenőrzése...\n")
            if STEAMCMD_BIN.exists():
                output_queue.put("[SUCCESS] ✓ SteamCMD telepítése sikeres!\n")
                output_queue.put(f"[INFO] Telepítési útvonal: {STEAMCMD_BIN}\n")
            else:
                output_queue.put("[ERROR] ✗ SteamCMD telepítése sikertelen! A fájl nem található.\n")
        except Exception as e:
            output_queue.put(f"[ERROR] Hiba: {str(e)}\n")
            import traceback
            output_queue.put(f"[ERROR] Traceback: {traceback.format_exc()}\n")
        finally:
            output_queue.put("[DONE]\n")
            # Várunk egy kicsit, hogy a WebSocket végig tudja olvasni az üzeneteket
            time.sleep(2)
            if process_id in active_processes:
                del active_processes[process_id]
            # Ne töröljük azonnal a process_outputs-ot, hogy a WebSocket végig tudja olvasni
            # A WebSocket törli, amikor befejeződik
    
    # Folyamat indítása háttérben
    thread = threading.Thread(target=install_process)
    thread.daemon = True
    thread.start()
    active_processes[process_id] = thread
    
    return JSONResponse({
        "success": True,
        "process_id": process_id,
        "message": "SteamCMD telepítése elindítva"
    })

@router.post("/steamcmd/update")
async def update_steamcmd(
    request: Request,
    db: Session = Depends(get_db)
):
    """SteamCMD frissítése"""
    current_user = require_manager_admin(request, db)
    
    # Ellenőrizzük, hogy telepítve van-e
    if not STEAMCMD_BIN.exists():
        return JSONResponse({
            "success": False,
            "message": "SteamCMD nincs telepítve"
        })
    
    # Process ID generálása
    import uuid
    process_id = str(uuid.uuid4())
    
    # Output queue létrehozása
    output_queue = queue.Queue()
    process_outputs[process_id] = output_queue
    
    def update_process():
        """SteamCMD frissítő folyamat"""
        try:
            output_queue.put("[INFO] SteamCMD frissítése elindítva...\n")
            output_queue.put(f"[INFO] Futtatás: {STEAMCMD_BIN} +quit\n")
            
            # SteamCMD frissítése
            process = subprocess.Popen(
                [str(STEAMCMD_BIN), "+quit"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                cwd=str(STEAMCMD_DIR)
            )
            
            # Live output olvasása soronként
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                output_queue.put(line)
                # Flush a buffer miatt
                import sys
                sys.stdout.flush()
            
            process.wait()
            
            if process.returncode == 0:
                output_queue.put("[SUCCESS] ✓ SteamCMD frissítése sikeres!\n")
            else:
                output_queue.put(f"[ERROR] ✗ SteamCMD frissítése sikertelen (exit code: {process.returncode})\n")
        except Exception as e:
            output_queue.put(f"[ERROR] Hiba: {str(e)}\n")
            import traceback
            output_queue.put(f"[ERROR] Traceback: {traceback.format_exc()}\n")
        finally:
            output_queue.put("[DONE]\n")
            # Várunk egy kicsit, hogy a WebSocket végig tudja olvasni az üzeneteket
            time.sleep(2)
            if process_id in active_processes:
                del active_processes[process_id]
            # Ne töröljük azonnal a process_outputs-ot, hogy a WebSocket végig tudja olvasni
            # A WebSocket törli, amikor befejeződik
    
    # Folyamat indítása háttérben
    thread = threading.Thread(target=update_process)
    thread.daemon = True
    thread.start()
    active_processes[process_id] = thread
    
    return JSONResponse({
        "success": True,
        "process_id": process_id,
        "message": "SteamCMD frissítése elindítva"
    })

@router.websocket("/steamcmd/output/{process_id}")
async def steamcmd_output(websocket: WebSocket, process_id: str):
    """WebSocket végpont a live terminál kimenethez"""
    await websocket.accept()
    
    try:
        while True:
            if process_id in process_outputs:
                output_queue = process_outputs[process_id]
                
                try:
                    # Várunk egy kicsit, hogy legyen output
                    line = output_queue.get(timeout=0.5)
                    await websocket.send_text(line)
                    
                    # Ha vége, kilépünk
                    if "[DONE]" in line:
                        break
                except queue.Empty:
                    # Nincs új output, küldünk egy üres üzenetet, hogy a kapcsolat éljen maradjon
                    await websocket.send_text("")
                    time.sleep(0.1)
            else:
                # Process nem található
                await websocket.send_text("[ERROR] Process nem található\n")
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(f"[ERROR] {str(e)}\n")
        except:
            pass

