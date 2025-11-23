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
    
    # Log függvény definíciója (korábban kell, hogy használhassuk)
    log_lines = []
    
    async def log(message: str):
        log_lines.append(message)
        if progress_callback:
            if asyncio.iscoroutinefunction(progress_callback):
                await progress_callback(message)
            else:
                progress_callback(message)
    
    # Telepítési útvonal létrehozása JOGOSULTSÁGOKKAL együtt
    await log("Telepítési mappa létrehozása...")
    try:
        import stat
        current_uid = os.getuid()
        current_gid = os.getgid()
        
        # Mappa létrehozása
        install_path.mkdir(parents=True, exist_ok=True)
        
        # AZONNAL beállítjuk a jogosultságokat (0x602 hiba elkerülésére)
        # FONTOS: A mappa létrehozása után azonnal kell beállítani!
        try:
            # Jogosultságok: 755 (rwxr-xr-x)
            os.chmod(install_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
            # Tulajdonjog: aktuális felhasználó
            os.chown(install_path, current_uid, current_gid)
            await log("✓ Telepítési mappa létrehozva megfelelő jogosultságokkal")
        except (PermissionError, OSError) as e:
            await log(f"⚠️ Jogosultságok beállítása sikertelen: {e}")
            await log("ℹ️ Folytatjuk a telepítést...")
    except Exception as e:
        await log(f"⚠️ Mappa létrehozása sikertelen: {e}")
        # Próbáljuk meg úgyis létrehozni
        install_path.mkdir(parents=True, exist_ok=True)
        # AZONNAL beállítjuk a jogosultságokat (ne root jogosultságokkal jöjjön létre!)
        try:
            os.chmod(install_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
            os.chown(install_path, current_uid, current_gid)
        except (PermissionError, OSError):
            pass
    
    # FONTOS: Jogosultságok beállítása a SteamCMD telepítés előtt (0x602 hiba elkerülésére)
    # A POK-manager.sh script is ezt csinálja: "Ensure ServerFiles directory has correct permissions to prevent SteamCMD error 0x602"
    # MEGJEGYZÉS: Nem használunk sudo-t, mert a felhasználók nem tudják minden telepítésnél megadni
    # Csak akkor próbáljuk meg beállítani a jogosultságokat, ha közvetlenül lehetséges
    await log("Jogosultságok beállítása a telepítési útvonalra (0x602 hiba elkerülésére)...")
    try:
        import stat
        current_uid = os.getuid()
        current_gid = os.getgid()
        
        # Mappa jogosultságok beállítása: 755 (rwxr-xr-x) - csak akkor, ha lehetséges
        try:
            os.chmod(install_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        except (PermissionError, OSError):
            pass  # Ha nincs jogosultság, folytatjuk
        
        # Tulajdonjog beállítása (ha lehetséges) - csak akkor, ha lehetséges
        try:
            os.chown(install_path, current_uid, current_gid)
        except (PermissionError, OSError):
            pass  # Ha nincs jogosultság, folytatjuk
        
        # Ha van már tartalom, akkor az összes mappát és fájlt is beállítjuk - csak akkor, ha lehetséges
        if install_path.exists():
            try:
                # Próbáljuk meg közvetlenül, de ne blokkoljuk a telepítést, ha nem sikerül
                for root, dirs, files in os.walk(install_path):
                    for d in dirs:
                        try:
                            dir_path = os.path.join(root, d)
                            os.chmod(dir_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)  # 755
                            os.chown(dir_path, current_uid, current_gid)
                        except (PermissionError, OSError):
                            pass  # Ha nincs jogosultság, folytatjuk
                    
                    for f in files:
                        try:
                            file_path = os.path.join(root, f)
                            os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)  # 644
                            os.chown(file_path, current_uid, current_gid)
                        except (PermissionError, OSError):
                            pass  # Ha nincs jogosultság, folytatjuk
            except Exception:
                pass  # Ha bármi hiba van, folytatjuk
        
        await log("✓ Jogosultságok beállítva (ahol lehetséges volt)")
    except Exception as e:
        await log(f"⚠️ Jogosultságok beállítása részben sikertelen: {e}")
        await log("ℹ️ Folytatjuk a telepítést - a SteamCMD próbálja meg felülírni a fájlokat")
    
    # Ha már van telepítés, de hiányos (pl. csak Saved mappa van), töröljük
    # hogy teljes újratelepítést csinálhassunk
    shooter_game = install_path / "ShooterGame"
    if shooter_game.exists():
        binaries = shooter_game / "Binaries"
        if not binaries.exists():
            # Hiányos telepítés - töröljük a ShooterGame mappát, hogy újratelepítsük
            import shutil
            import stat
            await log("⚠️ Hiányos telepítés észlelve (nincs Binaries mappa). Régi telepítés törlése...")
            
            # Először próbáljuk meg a Saved mappát külön törölni (ez okozza a problémát)
            saved_dir = shooter_game / "Saved"
            if saved_dir.exists():
                await log("Saved mappa törlése (ez okozhatja a 0x602 hibát)...")
                try:
                    # Jogosultságok javítása először
                    try:
                        for root, dirs, files in os.walk(saved_dir):
                            for d in dirs:
                                try:
                                    dir_path = os.path.join(root, d)
                                    os.chmod(dir_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                                    if os.name != 'nt':
                                        os.chown(dir_path, os.getuid(), os.getgid())
                                except (PermissionError, OSError):
                                    pass
                            for f in files:
                                try:
                                    file_path = os.path.join(root, f)
                                    os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                                    if os.name != 'nt':
                                        os.chown(file_path, os.getuid(), os.getgid())
                                except (PermissionError, OSError):
                                    pass
                    except Exception:
                        pass
                    
                    # Most próbáljuk meg törölni
                    shutil.rmtree(saved_dir)
                    await log("✓ Saved mappa törölve")
                except Exception as e:
                    await log(f"⚠️ Saved mappa törlése sikertelen: {e}")
                    # Próbáljuk meg átnevezni (ha törölni nem lehet)
                    try:
                        saved_backup = shooter_game / "Saved.backup"
                        if saved_backup.exists():
                            shutil.rmtree(saved_backup)
                        saved_dir.rename(saved_backup)
                        await log("✓ Saved mappa átnevezve (Saved.backup)")
                    except Exception:
                        pass
            
            # Most próbáljuk meg törölni az egész ShooterGame mappát
            try:
                # Először javítjuk a jogosultságokat
                try:
                    for root, dirs, files in os.walk(shooter_game):
                        for d in dirs:
                            try:
                                dir_path = os.path.join(root, d)
                                os.chmod(dir_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                                if os.name != 'nt':
                                    os.chown(dir_path, os.getuid(), os.getgid())
                            except (PermissionError, OSError):
                                pass
                        for f in files:
                            try:
                                file_path = os.path.join(root, f)
                                os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                                if os.name != 'nt':
                                    os.chown(file_path, os.getuid(), os.getgid())
                            except (PermissionError, OSError):
                                pass
                except Exception:
                    pass
                
                # Most töröljük
                shutil.rmtree(shooter_game)
                await log("✓ Régi telepítés törölve")
            except Exception as e:
                await log(f"⚠️ Régi telepítés törlése sikertelen: {e}")
                await log("ℹ️ Folytatjuk a telepítést - a SteamCMD felülírja a fájlokat.")
    
    # SteamCMD parancs összeállítása
    # Ark Survival Ascended App ID: 2430930
    app_id = "2430930"
    
    # SteamCMD parancsok argumentumként
    # ARK Survival Ascended szerverfájlok telepítése
    # FONTOS: A force_install_dir-t a login ELŐTT kell megadni!
    # Linux-on nem kell a platform type paraméter, mert a SteamCMD automatikusan
    # a megfelelő platformot választja (Linux binárisokat tölt le Linux-on)
    # FONTOS: NEM használunk validate opciót az első telepítésnél, mert az verify fázist indít,
    # ami 0x602 hibát okozhat. A validate-t csak újratelepítésnél használjuk.
    steamcmd_args = [
        str(steamcmd_path),
        "+force_install_dir", str(install_path.absolute()),  # Először a telepítési útvonal
        "+login", "anonymous",  # Utána a bejelentkezés
        "+app_update", app_id,  # Teljes telepítés (validate NÉLKÜL - 0x602 hiba elkerülésére)
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
        download_complete = False
        download_progress = 0.0
        max_progress = 0.0
        verifying = False
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            line_text = line.decode('utf-8', errors='ignore').strip()
            if line_text:
                await log(line_text)
                # Ellenőrizzük, hogy a letöltés befejeződött-e
                if "Success!" in line_text or "fully installed" in line_text.lower():
                    download_complete = True
                # Ellenőrizzük, hogy verify fázisban van-e
                if "verifying" in line_text.lower() or "0x81" in line_text:
                    verifying = True
                # Progress követése
                if "progress:" in line_text.lower():
                    try:
                        # Kinyerjük a progress értéket (pl. "progress: 53.18")
                        import re
                        progress_match = re.search(r'progress:\s*(\d+\.?\d*)', line_text)
                        if progress_match:
                            download_progress = float(progress_match.group(1))
                            if download_progress > max_progress:
                                max_progress = download_progress
                    except Exception:
                        pass
        
        # Visszatérési kód ellenőrzése - várjuk meg, amíg a folyamat teljesen befejeződik
        return_code = await process.wait()
        
        # Ellenőrizzük, hogy a letöltés ténylegesen befejeződött-e
        if return_code == 0:
            if max_progress > 0 and max_progress < 100.0 and not verifying:
                await log(f"⚠️ Figyelmeztetés: SteamCMD exit code 0, de a letöltés csak {max_progress}% volt!")
                await log("⚠️ Lehet, hogy a telepítés nem teljes. Ellenőrizzük a fájlokat...")
            elif verifying:
                await log("ℹ️ SteamCMD verify fázisban volt, ez normális")
        
        # Folyamat befejeződése után várunk, hogy a fájlrendszer műveletek befejeződjenek
        await log("SteamCMD folyamat befejeződött, várakozás a fájlrendszer stabilizálódására...")
        await asyncio.sleep(2)  # Rövid várakozás a fájlrendszer műveletek befejezésére
        
        # FONTOS: SteamCMD után AZONNAL beállítjuk a jogosultságokat (SteamCMD root-ként hozhatja létre a mappákat!)
        await log("Jogosultságok beállítása a SteamCMD által létrehozott mappákra...")
        try:
            from app.services.symlink_service import ensure_permissions
            # Rekurzívan beállítjuk az összes mappa és fájl jogosultságát
            ensure_permissions(install_path, recursive=True)
            await log("✓ Jogosultságok beállítva a SteamCMD telepítésre")
        except Exception as e:
            await log(f"⚠️ Jogosultságok beállítása sikertelen: {e}")
            # Próbáljuk meg manuálisan is
            try:
                import stat
                current_uid = os.getuid()
                current_gid = os.getgid()
                for root, dirs, files in os.walk(install_path):
                    for d in dirs:
                        try:
                            dir_path = Path(root) / d
                            os.chmod(dir_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                            if os.name != 'nt':
                                os.chown(dir_path, current_uid, current_gid)
                        except (PermissionError, OSError):
                            pass
                    for f in files:
                        try:
                            file_path = Path(root) / f
                            os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                            if os.name != 'nt':
                                os.chown(file_path, current_uid, current_gid)
                        except (PermissionError, OSError):
                            pass
                await log("✓ Jogosultságok beállítva (manuális módszerrel)")
            except Exception as e2:
                await log(f"⚠️ Manuális jogosultság beállítás is sikertelen: {e2}")
        
        # SteamCMD néhány exit code esetén is sikeres lehet (pl. 8 = részben sikeres)
        # Ellenőrizzük, hogy a bináris létezik-e, mert az a fontos
        if return_code == 0:
            # Ellenőrizzük, hogy a letöltés ténylegesen befejeződött-e
            if max_progress > 0 and max_progress < 100.0 and not verifying and not download_complete:
                await log(f"⚠️ Figyelmeztetés: SteamCMD exit code 0, de a letöltés csak {max_progress}% volt!")
                await log("⚠️ A letöltés nem fejeződött be teljesen. Újratelepítés indítása...")
                # Újratelepítés indítása, mert a letöltés nem fejeződött be
                try:
                    import shutil
                    shooter_game = install_path / "ShooterGame"
                    if shooter_game.exists():
                        # Töröljük a hiányos telepítést - csak akkor, ha lehetséges (sudo nélkül)
                        await log("Hiányos telepítés törlése...")
                        try:
                            shutil.rmtree(shooter_game)
                            await log("✓ Hiányos telepítés törölve")
                        except (PermissionError, OSError) as e:
                            await log(f"⚠️ Nincs jogosultság a hiányos telepítés törléséhez: {e}")
                            await log("ℹ️ Folytatjuk a telepítést - a SteamCMD felülírja a fájlokat")
                    # Újratelepítés
                    await asyncio.sleep(2)
                    await log("Újratelepítés indítása SteamCMD-vel...")
                    process2 = await asyncio.create_subprocess_exec(
                        str(steamcmd_path),
                        "+force_install_dir", str(install_path.absolute()),
                        "+login", "anonymous",
                        "+app_update", app_id,  # Teljes telepítés (validate NÉLKÜL - 0x602 hiba elkerülésére)
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
                    await log("Újratelepítés befejeződött, várakozás a fájlrendszer stabilizálódására...")
                    await asyncio.sleep(3)
                    # FONTOS: Újratelepítés után AZONNAL beállítjuk a jogosultságokat
                    try:
                        from app.services.symlink_service import ensure_permissions
                        ensure_permissions(install_path, recursive=True)
                        await log("✓ Jogosultságok beállítva az újratelepítésre")
                    except Exception as perm_e:
                        await log(f"⚠️ Jogosultságok beállítása sikertelen: {perm_e}")
                except Exception as e:
                    await log(f"⚠️ Újratelepítés sikertelen: {e}")
                    import traceback
                    traceback.print_exc()
            else:
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
                    import shutil
                    # Törlés - csak akkor, ha lehetséges (sudo nélkül)
                    törlés_sikeres = False
                    try:
                        shutil.rmtree(shooter_game)
                        await log("✓ ShooterGame mappa törölve")
                        törlés_sikeres = True
                    except (PermissionError, OSError) as e:
                        await log(f"⚠️ Nincs jogosultság a ShooterGame mappa törléséhez: {e}")
                        await log("ℹ️ Folytatjuk a telepítést - a SteamCMD felülírja a fájlokat")
                    
                    # Újratelepítés (akkor is, ha a törlés nem sikerült)
                    await log("Újratelepítés indítása SteamCMD-vel...")
                    await asyncio.sleep(2)
                    # Újratelepítés SteamCMD-vel
                    # FONTOS: A force_install_dir-t a login ELŐTT kell megadni!
                    process2 = await asyncio.create_subprocess_exec(
                        str(steamcmd_path),
                        "+force_install_dir", str(install_path.absolute()),  # Először a telepítési útvonal
                        "+login", "anonymous",  # Utána a bejelentkezés
                        "+app_update", app_id,  # Teljes telepítés (validate NÉLKÜL - 0x602 hiba elkerülésére)
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
                    # FONTOS: Újratelepítés után AZONNAL beállítjuk a jogosultságokat
                    try:
                        from app.services.symlink_service import ensure_permissions
                        ensure_permissions(install_path, recursive=True)
                        await log("✓ Jogosultságok beállítva az újratelepítésre")
                    except Exception as perm_e:
                        await log(f"⚠️ Jogosultságok beállítása sikertelen: {perm_e}")
                except Exception as e:
                    await log(f"⚠️ Újratelepítés sikertelen: {e}")
            
            # Ellenőrizzük, hogy a bináris létezik-e (Linux vagy Windows)
            # Lehet, hogy a linux64/ mappában van közvetlenül (más rendszerekben így van)
            # Várunk egy kicsit, hogy a fájlrendszer biztosan frissüljön
            await asyncio.sleep(2)
            
            linux_binary_shootergame = install_path / "ShooterGame" / "Binaries" / "Linux" / "ShooterGameServer"
            linux_binary_linux64 = install_path / "linux64" / "ShooterGameServer"
            win64_binary = install_path / "ShooterGame" / "Binaries" / "Win64" / "ShooterGameServer.exe"
            
            # Először a ShooterGame/Binaries/Linux-t, majd a linux64/ mappát ellenőrizzük
            linux_binary = linux_binary_shootergame if linux_binary_shootergame.exists() else (linux_binary_linux64 if linux_binary_linux64.exists() else None)
            
            # Részletes ellenőrzés logolása
            await log(f"Bináris ellenőrzés:")
            await log(f"  - Linux (ShooterGame/Binaries/Linux): {linux_binary_shootergame.exists()}")
            await log(f"  - Linux (linux64/): {linux_binary_linux64.exists()}")
            await log(f"  - Windows: {win64_binary.exists()}")
            
            if not linux_binary and not win64_binary.exists():
                error_msg = f"HIBA: A telepítés sikeres volt, de a ShooterGameServer bináris nem található (sem Linux, sem Windows)"
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
            
            if linux_binary:
                await log(f"✓ Linux ShooterGameServer bináris megtalálva: {linux_binary}")
                await log("✓ Telepítés teljesen befejeződött!")
            elif win64_binary.exists():
                await log(f"✓ Windows ShooterGameServer.exe bináris megtalálva: {win64_binary}")
                await log("✓ Telepítés teljesen befejeződött! (Windows bináris, Wine-nal fog futni)")
            return True, '\n'.join(log_lines)
        elif return_code == 8:
            # Exit code 8 gyakran előfordul, de a telepítés mégis sikeres lehet
            # Ellenőrizzük, hogy a bináris létezik-e
            await log(f"⚠️ SteamCMD exit code 8 (gyakori, nem feltétlenül hiba)")
            await log("Ellenőrizzük, hogy a telepítés sikeres volt-e...")
            
            # Ellenőrizzük, hogy a bináris létezik-e (Linux vagy Windows)
            # Lehet, hogy a linux64/ mappában van közvetlenül (más rendszerekben így van)
            linux_binary_shootergame = install_path / "ShooterGame" / "Binaries" / "Linux" / "ShooterGameServer"
            linux_binary_linux64 = install_path / "linux64" / "ShooterGameServer"
            win64_binary = install_path / "ShooterGame" / "Binaries" / "Win64" / "ShooterGameServer.exe"
            
            # Várunk, amíg a bináris létrejön (max 60 másodperc, de csak akkor várunk, ha még nincs)
            max_wait_time = 60  # Maximum 60 másodperc
            check_interval = 2  # 2 másodpercenként ellenőrzünk
            waited_time = 0
            
            while waited_time < max_wait_time:
                # Részletes ellenőrzés
                # Először a ShooterGame/Binaries/Linux-t, majd a linux64/ mappát ellenőrizzük
                linux_binary = linux_binary_shootergame if linux_binary_shootergame.exists() else (linux_binary_linux64 if linux_binary_linux64.exists() else None)
                
                if linux_binary:
                    await log(f"✓ Linux bináris megtalálva: {linux_binary}")
                    await log("✓ Telepítés sikeres (exit code 8, de bináris létezik)!")
                    return True, '\n'.join(log_lines)
                elif win64_binary.exists():
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
            error_msg = f"Telepítés sikertelen (exit code 8, bináris nem található {max_wait_time} másodperc után sem)"
            await log(f"✗ {error_msg}")
            await log("Próbáld meg újratelepíteni a szerverfájlokat!")
            return False, '\n'.join(log_lines)
        else:
            error_msg = f"Telepítés sikertelen (visszatérési kód: {return_code})"
            await log(f"✗ {error_msg}")
            
            # Mégis ellenőrizzük, hogy esetleg a bináris létezik-e
            await asyncio.sleep(2)
            linux_binary_shootergame = install_path / "ShooterGame" / "Binaries" / "Linux" / "ShooterGameServer"
            linux_binary_linux64 = install_path / "linux64" / "ShooterGameServer"
            win64_binary = install_path / "ShooterGame" / "Binaries" / "Win64" / "ShooterGameServer.exe"
            
            # Először a ShooterGame/Binaries/Linux-t, majd a linux64/ mappát ellenőrizzük
            linux_binary = linux_binary_shootergame if linux_binary_shootergame.exists() else (linux_binary_linux64 if linux_binary_linux64.exists() else None)
            
            if linux_binary:
                await log("⚠️ Linux bináris mégis létezik, telepítés valószínűleg sikeres volt!")
                await log(f"✓ Linux bináris: {linux_binary}")
                return True, '\n'.join(log_lines)
            elif win64_binary.exists():
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
            "+force_install_dir", str(install_path.absolute()),  # Először a telepítési útvonal
            "+login", "anonymous",
            "+app_update", app_id,  # Frissítés ellenőrzés (validate NÉLKÜL - 0x602 hiba elkerülésére)
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

