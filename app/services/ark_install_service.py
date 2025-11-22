"""
Ark szerverfájlok telepítési szolgáltatás - SteamCMD használatával
"""

import subprocess
import asyncio
import os
from pathlib import Path
from typing import Optional, Callable, Awaitable, Union
from app.config import settings

def get_steamcmd_path() -> Optional[Path]:
    """SteamCMD útvonal keresése"""
    # Gyakori útvonalak
    common_paths = [
        Path("/usr/games/steamcmd"),
        Path("/usr/local/bin/steamcmd"),
        Path("/opt/steamcmd/steamcmd.sh"),
        Path.home() / "steamcmd" / "steamcmd.sh",
    ]
    
    for path in common_paths:
        if path.exists():
            return path
    
    # Ha nincs megtalálva, próbáljuk meg a PATH-ból
    import shutil
    steamcmd = shutil.which("steamcmd")
    if steamcmd:
        return Path(steamcmd)
    
    return None

async def install_ark_server_files(
    cluster_id: str,
    version: str,
    install_path: Path,
    progress_callback: Optional[Union[Callable[[str], None], Callable[[str], Awaitable[None]]]] = None
) -> tuple[bool, str]:
    """
    Ark szerverfájlok telepítése SteamCMD-vel
    
    Args:
        cluster_id: Cluster ID
        version: Verzió (opcionális, ha None, akkor legújabb)
        install_path: Telepítési útvonal
        progress_callback: Callback függvény a progress üzenetekhez
    
    Returns:
        (success: bool, log: str)
    """
    steamcmd_path = get_steamcmd_path()
    if not steamcmd_path:
        error_msg = "SteamCMD nem található! Telepítsd a SteamCMD-t."
        if progress_callback:
            progress_callback(error_msg)
        return False, error_msg
    
    # Telepítési útvonal létrehozása
    install_path.mkdir(parents=True, exist_ok=True)
    
    # SteamCMD parancs összeállítása
    # Ark Survival Ascended App ID: 2430930
    app_id = "2430930"
    
    # SteamCMD script
    # Ha version == "latest", akkor nincs beta paraméter
    if version.lower() == "latest":
        steamcmd_script = f"""
force_install_dir {install_path.absolute()}
login anonymous
app_update {app_id} validate
quit
"""
    else:
        # Ha konkrét verzió, akkor beta paraméterrel (ha szükséges)
        steamcmd_script = f"""
force_install_dir {install_path.absolute()}
login anonymous
app_update {app_id} validate
quit
"""
    
    log_lines = []
    
    async def log(message: str):
        log_lines.append(message)
        if progress_callback:
            if asyncio.iscoroutinefunction(progress_callback):
                await progress_callback(message)
            else:
                progress_callback(message)
    
    await log(f"SteamCMD telepítés indítása...")
    await log(f"Telepítési útvonal: {install_path.absolute()}")
    await log(f"App ID: {app_id}")
    
    try:
        # SteamCMD futtatása
        process = await asyncio.create_subprocess_exec(
            str(steamcmd_path),
            "+runscript", "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(install_path.parent),
            bufsize=0  # Unbuffered output
        )
        
        # Script küldése
        process.stdin.write(steamcmd_script.encode())
        await process.stdin.drain()
        process.stdin.close()
        
        # Kimenet feldolgozása (real-time)
        # Valós idejű kimenet olvasása
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            line_text = line.decode('utf-8', errors='ignore').strip()
            if line_text:
                await log(line_text)
        
        # Visszatérési kód ellenőrzése
        return_code = await process.wait()
        
        if return_code == 0:
            await log("✓ Telepítés sikeresen befejeződött!")
            return True, '\n'.join(log_lines)
        else:
            error_msg = f"Telepítés sikertelen (visszatérési kód: {return_code})"
            await log(f"✗ {error_msg}")
            return False, '\n'.join(log_lines)
            
    except Exception as e:
        error_msg = f"Telepítési hiba: {str(e)}"
        await log(f"✗ {error_msg}")
        return False, '\n'.join(log_lines)

def delete_ark_server_files(install_path: Path) -> bool:
    """
    Ark szerverfájlok törlése
    
    Args:
        install_path: Telepítési útvonal
    
    Returns:
        True ha sikeres, False egyébként
    """
    try:
        if install_path.exists():
            import shutil
            shutil.rmtree(install_path)
            return True
        return False
    except Exception:
        return False

