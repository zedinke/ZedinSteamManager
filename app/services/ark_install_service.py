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
    
    # Log függvény definíciója (korábban kell, hogy használhassuk)
    log_lines = []
    
    async def log(message: str):
        log_lines.append(message)
        if progress_callback:
            if asyncio.iscoroutinefunction(progress_callback):
                await progress_callback(message)
            else:
                progress_callback(message)
    
    # Ha már van telepítés, de hiányos (pl. csak Saved mappa van), töröljük
    # hogy teljes újratelepítést csinálhassunk
    shooter_game = install_path / "ShooterGame"
    if shooter_game.exists():
        binaries = shooter_game / "Binaries"
        if not binaries.exists():
            # Hiányos telepítés - töröljük a ShooterGame mappát, hogy újratelepítsük
            import shutil
            import os
            await log("⚠️ Hiányos telepítés észlelve (nincs Binaries mappa). Régi telepítés törlése...")
            try:
                # Próbáljuk meg törölni, de ha nincs jogosultság, akkor csak figyelmeztetünk
                # A SteamCMD telepítés felülírja a fájlokat úgyis
                shutil.rmtree(shooter_game)
                await log("✓ Régi telepítés törölve")
            except PermissionError as e:
                await log(f"⚠️ Nincs jogosultság a régi telepítés törléséhez: {e}")
                await log("ℹ️ A SteamCMD telepítés felülírja a fájlokat, ezért a törlés nem szükséges.")
                # Próbáljuk meg a jogosultságok javítását (ha lehetséges)
                try:
                    import stat
                    # Jogosultságok javítása
                    for root, dirs, files in os.walk(shooter_game):
                        for d in dirs:
                            os.chmod(os.path.join(root, d), stat.S_IRWXU)
                        for f in files:
                            os.chmod(os.path.join(root, f), stat.S_IRUSR | stat.S_IWUSR)
                    # Most próbáljuk meg újra törölni
                    shutil.rmtree(shooter_game)
                    await log("✓ Régi telepítés törölve (jogosultságok javítása után)")
                except Exception as e2:
                    await log(f"⚠️ Jogosultságok javítása sem sikerült: {e2}")
                    await log("ℹ️ Folytatjuk a telepítést - a SteamCMD felülírja a fájlokat.")
            except Exception as e:
                await log(f"⚠️ Nem sikerült törölni a régi telepítést: {e}")
                await log("ℹ️ Folytatjuk a telepítést - a SteamCMD felülírja a fájlokat.")
    
    # SteamCMD parancs összeállítása
    # Ark Survival Ascended App ID: 2430930
    app_id = "2430930"
    
    # SteamCMD parancsok argumentumként
    # Ark Survival Ascended szerverfájlok telepítése
    # A parancsokat közvetlenül argumentumként adjuk át, nem script fájlként
    # Megjegyzés: Teljes telepítés (nem csak validate), hogy biztosan minden fájl letöltődjön
    # Ha már van telepítés, akkor is újratelepítjük, hogy biztosan teljes legyen
    steamcmd_args = [
        str(steamcmd_path),
        "+login", "anonymous",
        "+force_install_dir", str(install_path.absolute()),
        "+@sSteamCmdForcePlatformType", "windows",  # Kényszerítjük a Windows verzió letöltését
        "+app_update", app_id,  # Teljes telepítés (validate nélkül = minden fájlt letölt)
        "+quit"
    ]
    
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
        
        # Visszatérési kód ellenőrzése - várjuk meg, amíg a folyamat teljesen befejeződik
        return_code = await process.wait()
        
        # Folyamat befejeződése után várunk, hogy a fájlrendszer műveletek befejeződjenek
        await log("SteamCMD folyamat befejeződött, várakozás a fájlrendszer stabilizálódására...")
        await asyncio.sleep(2)  # Rövid várakozás a fájlrendszer műveletek befejezésére
        
        # SteamCMD néhány exit code esetén is sikeres lehet (pl. 8 = részben sikeres)
        # Ellenőrizzük, hogy a bináris létezik-e, mert az a fontos
        if return_code == 0:
            await log("✓ SteamCMD telepítés sikeresen befejeződött!")
            
            # Várunk egy kicsit, hogy a fájlrendszer frissüljön
            await asyncio.sleep(3)
            
            # Ha a SteamCMD azt mondta "already up to date", de nincs Binaries mappa,
            # akkor töröljük a ShooterGame mappát és újratelepítjük
            shooter_game = install_path / "ShooterGame"
            binaries = shooter_game / "Binaries" if shooter_game.exists() else None
            if shooter_game.exists() and (not binaries or not binaries.exists()):
                await log("⚠️ SteamCMD 'already up to date' üzenetet adott, de nincs Binaries mappa!")
                await log("⚠️ Töröljük a ShooterGame mappát és újratelepítjük...")
                try:
                    import subprocess
                    # Jogosultságok javítása
                    subprocess.run(
                        ["sudo", "chown", "-R", f"{os.getuid()}:{os.getgid()}", str(shooter_game)],
                        capture_output=True,
                        timeout=10
                    )
                    # Törlés
                    result = subprocess.run(
                        ["sudo", "rm", "-rf", str(shooter_game)],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode == 0:
                        await log("✓ ShooterGame mappa törölve, újratelepítés indítása...")
                        # Újratelepítés
                        await asyncio.sleep(2)
                        # Újratelepítés SteamCMD-vel
                        process2 = await asyncio.create_subprocess_exec(
                            str(steamcmd_path),
                            "+login", "anonymous",
                            "+force_install_dir", str(install_path.absolute()),
                            "+@sSteamCmdForcePlatformType", "windows",  # Kényszerítjük a Windows verzió letöltését
                            "+app_update", app_id,
                            "+quit",
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.STDOUT,
                            cwd=str(install_path.parent),
                            bufsize=0
                        )
                        while True:
                            line = await process2.stdout.readline()
                            if not line:
                                break
                            line_text = line.decode('utf-8', errors='ignore').strip()
                            if line_text:
                                await log(line_text)
                        return_code = await process2.wait()
                        await asyncio.sleep(3)  # Várunk, hogy a fájlrendszer frissüljön
                    else:
                        await log(f"⚠️ ShooterGame mappa törlése sikertelen: {result.stderr}")
                except Exception as e:
                    await log(f"⚠️ Újratelepítés sikertelen: {e}")
            
            # Ellenőrizzük, hogy a Windows bináris létezik-e (csak Windows bináris van)
            binary_path = install_path / "ShooterGame" / "Binaries" / "Win64" / "ShooterGameServer.exe"
            if not binary_path.exists():
                error_msg = f"HIBA: A telepítés sikeres volt, de a ShooterGameServer.exe bináris nem található: {binary_path}"
                await log(f"✗ {error_msg}")
                await log("Ellenőrzés:")
                await log(f"  - Install path létezik: {install_path.exists()}")
                if install_path.exists():
                    install_contents = list(install_path.iterdir())
                    await log(f"  - Install path tartalma ({len(install_contents)} elem): {[item.name for item in install_contents[:10]]}")
                    shooter_game = install_path / "ShooterGame"
                    if shooter_game.exists():
                        await log(f"  - ShooterGame mappa létezik: {shooter_game.exists()}")
                        shooter_contents = list(shooter_game.iterdir())
                        await log(f"  - ShooterGame tartalma ({len(shooter_contents)} elem): {[item.name for item in shooter_contents[:20]]}")
                        binaries = shooter_game / "Binaries"
                        if binaries.exists():
                            await log(f"  - Binaries mappa létezik: {binaries.exists()}")
                            binaries_contents = list(binaries.iterdir())
                            await log(f"  - Binaries tartalma ({len(binaries_contents)} elem): {[item.name for item in binaries_contents]}")
                            linux_bin = binaries / "Linux"
                            if linux_bin.exists():
                                await log(f"  - Linux mappa létezik: {linux_bin.exists()}")
                                linux_contents = list(linux_bin.iterdir())
                                await log(f"  - Linux mappa tartalma ({len(linux_contents)} elem): {[item.name for item in linux_contents[:20]]}")
                            else:
                                await log(f"  - Linux mappa NEM létezik!")
                                await log(f"  - Próbáljuk meg újratelepíteni a szerverfájlokat!")
                        else:
                            await log(f"  - Binaries mappa NEM létezik!")
                            await log(f"  - A telepítés hiányos! Próbáljuk meg újratelepíteni!")
                return False, '\n'.join(log_lines)
            
            await log(f"✓ ShooterGameServer bináris megtalálva: {binary_path}")
            await log("✓ Telepítés teljesen befejeződött!")
            return True, '\n'.join(log_lines)
        elif return_code == 8:
            # Exit code 8 gyakran előfordul, de a telepítés mégis sikeres lehet
            # Ellenőrizzük, hogy a bináris létezik-e
            await log(f"⚠️ SteamCMD exit code 8 (gyakori, nem feltétlenül hiba)")
            await log("Ellenőrizzük, hogy a telepítés sikeres volt-e...")
            
            # Ellenőrizzük, hogy a Windows bináris létezik-e (csak Windows bináris van)
            win64_binary = install_path / "ShooterGame" / "Binaries" / "Win64" / "ShooterGameServer.exe"
            
            # Várunk, amíg a bináris létrejön (max 60 másodperc, de csak akkor várunk, ha még nincs)
            max_wait_time = 60  # Maximum 60 másodperc
            check_interval = 2  # 2 másodpercenként ellenőrzünk
            waited_time = 0
            
            while waited_time < max_wait_time:
                # Részletes ellenőrzés
                shooter_game = install_path / "ShooterGame"
                if shooter_game.exists():
                    binaries = shooter_game / "Binaries"
                    if binaries.exists():
                        win64_path = binaries / "Win64"
                        if win64_path.exists():
                            if win64_binary.exists():
                                await log(f"✓ Windows bináris megtalálva: {win64_binary}")
                                await log("✓ Telepítés sikeres (exit code 8, de bináris létezik)!")
                                await log("ℹ️ Windows binárist használunk Wine-nal")
                                return True, '\n'.join(log_lines)
                
                # Ha még nincs, várunk és újra ellenőrizzük
                if waited_time == 0:
                    await log("Várakozás a bináris létrejöttére...")
                await asyncio.sleep(check_interval)
                waited_time += check_interval
                
                # Minden 10 másodpercben logoljuk az állapotot
                if waited_time % 10 == 0:
                    await log(f"Várakozás... ({waited_time}/{max_wait_time} másodperc)")
                    if shooter_game.exists():
                        binaries = shooter_game / "Binaries"
                        if binaries.exists():
                            binaries_contents = [item.name for item in binaries.iterdir()] if binaries.exists() else []
                            await log(f"  - Binaries tartalma: {binaries_contents}")
            
            # Ha a maximális várakozási idő után sincs bináris
            error_msg = f"Telepítés sikertelen (exit code 8, Windows bináris nem található {max_wait_time} másodperc után sem)"
            await log(f"✗ {error_msg}")
            await log("Próbáld meg újratelepíteni a szerverfájlokat!")
            return False, '\n'.join(log_lines)
        else:
            error_msg = f"Telepítés sikertelen (visszatérési kód: {return_code})"
            await log(f"✗ {error_msg}")
            
            # Mégis ellenőrizzük, hogy esetleg a Windows bináris létezik-e
            await asyncio.sleep(2)
            win64_binary = install_path / "ShooterGame" / "Binaries" / "Win64" / "ShooterGameServer.exe"
            
            if win64_binary.exists():
                await log("⚠️ Windows bináris mégis létezik, telepítés valószínűleg sikeres volt!")
                await log(f"✓ Windows bináris: {win64_binary}")
                await log("ℹ️ Windows binárist használunk Wine-nal")
                return True, '\n'.join(log_lines)
            
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

