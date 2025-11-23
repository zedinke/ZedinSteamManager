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
    
    # SteamCMD parancsok argumentumként
    # Ark Survival Ascended szerverfájlok telepítése
    # A parancsokat közvetlenül argumentumként adjuk át, nem script fájlként
    # Megjegyzés: A validate opció ellenőrzi és letölti a hiányzó fájlokat
    steamcmd_args = [
        str(steamcmd_path),
        "+login", "anonymous",
        "+force_install_dir", str(install_path.absolute()),
        "+app_update", app_id, "validate",  # validate = ellenőrzi és letölti a hiányzó fájlokat
        "+quit"
    ]
    
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
        # SteamCMD futtatása parancsokkal argumentumként
        process = await asyncio.create_subprocess_exec(
            *steamcmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(install_path.parent),
            bufsize=0  # Unbuffered output
        )
        
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
            await log("✓ SteamCMD telepítés sikeresen befejeződött!")
            
            # Ellenőrizzük, hogy a bináris létezik-e
            binary_path = install_path / "ShooterGame" / "Binaries" / "Linux" / "ShooterGameServer"
            if not binary_path.exists():
                error_msg = f"HIBA: A telepítés sikeres volt, de a ShooterGameServer bináris nem található: {binary_path}"
                await log(f"✗ {error_msg}")
                await log("Ellenőrzés:")
                await log(f"  - Install path létezik: {install_path.exists()}")
                if install_path.exists():
                    await log(f"  - Install path tartalma: {list(install_path.iterdir())[:10]}")
                    shooter_game = install_path / "ShooterGame"
                    if shooter_game.exists():
                        await log(f"  - ShooterGame mappa létezik: {shooter_game.exists()}")
                        binaries = shooter_game / "Binaries"
                        if binaries.exists():
                            await log(f"  - Binaries mappa létezik: {binaries.exists()}")
                            linux_bin = binaries / "Linux"
                            if linux_bin.exists():
                                await log(f"  - Linux mappa létezik: {linux_bin.exists()}")
                                await log(f"  - Linux mappa tartalma: {list(linux_bin.iterdir())[:10]}")
                return False, '\n'.join(log_lines)
            
            await log(f"✓ ShooterGameServer bináris megtalálva: {binary_path}")
            await log("✓ Telepítés teljesen befejeződött!")
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

async def check_for_updates(
    install_path: Path,
    progress_callback: Optional[Union[Callable[[str], None], Callable[[str], Awaitable[None]]]] = None
) -> tuple[bool, str]:
    """
    Ellenőrzi, hogy van-e frissítés a szerverfájlokhoz
    A SteamCMD app_update parancs ellenőrzi, hogy szükséges-e frissítés
    
    Args:
        install_path: Telepítési útvonal
        progress_callback: Callback függvény a progress üzenetekhez (opcionális)
    
    Returns:
        (has_update: bool, current_version: str)
    """
    steamcmd_path = get_steamcmd_path()
    if not steamcmd_path:
        return False, ""
    
    # Ha a telepítési útvonal nem létezik, akkor nincs telepített verzió
    if not install_path.exists():
        return True, ""  # Van "frissítés" (nincs telepítve)
    
    app_id = "2430930"
    
    try:
        # SteamCMD futtatása app_update-dal, de csak ellenőrzés céljából
        # Ha van frissítés, akkor a SteamCMD jelezni fogja
        process = await asyncio.create_subprocess_exec(
            str(steamcmd_path),
            "+login", "anonymous",
            "+force_install_dir", str(install_path.absolute()),
            "+app_update", app_id, "validate",
            "+quit",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(install_path.parent),
            bufsize=0
        )
        
        # Kimenet feldolgozása
        output_lines = []
        has_update_indicator = False
        
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            line_text = line.decode('utf-8', errors='ignore').strip()
            if line_text:
                output_lines.append(line_text)
                # Ellenőrizzük, hogy van-e frissítés jelző
                # A SteamCMD jelez, ha frissítés szükséges
                if any(keyword in line_text.lower() for keyword in ['update available', 'update required', 'downloading', 'updating']):
                    has_update_indicator = True
        
        return_code = await process.wait()
        
        # Ha a process sikeres volt, akkor ellenőrizzük a kimenetet
        if return_code == 0:
            output_text = '\n'.join(output_lines).lower()
            # Ha nincs "success" vagy "already up to date", akkor lehet frissítés
            if has_update_indicator or ('success' not in output_text and 'already up to date' not in output_text):
                return True, "latest"
            return False, "latest"
        
        # Ha hiba történt, akkor feltételezzük, hogy lehet frissítés
        return True, ""
        
    except Exception as e:
        # Hiba esetén feltételezzük, hogy lehet frissítés (biztonságos oldal)
        return True, ""

