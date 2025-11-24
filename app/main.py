"""
ZedinArkManager - FastAPI fő alkalmazás
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pathlib import Path
from app.config import settings
from app.middleware import catch_exceptions_middleware, session_role_refresh_middleware
import asyncio
import logging

# Projekt gyökér
BASE_DIR = Path(__file__).parent.parent

# FastAPI app
app = FastAPI(
    title="ZedinArkManager",
    description="Játék szerver kezelő manager rendszer",
    version="2.0.0",
    debug=True
)

# Exception handler middleware (legelső)
app.middleware("http")(catch_exceptions_middleware)

# Session role refresh middleware (session ellenőrzés után)
app.middleware("http")(session_role_refresh_middleware)

# Session middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    max_age=3600 * 24 * 7  # 7 nap
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Statikus fájlok
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Template-ek
templates_dir = BASE_DIR / "templates"
if not templates_dir.exists():
    templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))

# Routers importálása
from app.routers import auth, dashboard, tokens, admin, notifications, api, notifications_admin, update, system, settings, tickets, tickets_admin, chat, server_management, games_admin, servers, ai_chat, cart, cart_admin, pricing, ark_admin, ark_servers, ark_evolved_servers, ark_setup, mods, ark_serverfiles, ark_config, ark_backup

# Routers regisztrálása
app.include_router(auth.router, tags=["Auth"])
app.include_router(dashboard.router, tags=["Dashboard"])
app.include_router(tokens.router, tags=["Tokens"])
app.include_router(admin.router, tags=["Admin"])
app.include_router(notifications.router, tags=["Notifications"])
app.include_router(notifications_admin.router, tags=["Admin Notifications"])
app.include_router(update.router, tags=["Update"])
app.include_router(system.router, tags=["System"])
app.include_router(settings.router, tags=["Settings"])
app.include_router(tickets.router, tags=["Tickets"])
app.include_router(tickets_admin.router, tags=["Tickets Admin"])
app.include_router(chat.router, tags=["Chat"])
app.include_router(server_management.router, tags=["Server Management"])
app.include_router(games_admin.router, tags=["Games Admin"])
app.include_router(servers.router, tags=["Servers"])
app.include_router(ai_chat.router, tags=["AI Chat"])
app.include_router(cart.router, tags=["Cart"])
app.include_router(cart_admin.router, tags=["Cart Admin"])
app.include_router(pricing.router, tags=["Pricing"])
app.include_router(ark_admin.router, tags=["Ark Admin"])
app.include_router(ark_servers.router, tags=["Ark Servers"])
app.include_router(ark_evolved_servers.router, tags=["Ark Evolved Servers"])
app.include_router(ark_setup.router, tags=["Ark Setup"])
app.include_router(mods.router, tags=["Mods"])
app.include_router(ark_serverfiles.router, tags=["Ark Server Files"])
app.include_router(ark_config.router, tags=["Ark Config"])
app.include_router(ark_backup.router, tags=["Ark Backup"])
app.include_router(api.router, prefix="/api", tags=["API"])

# Token lejárat kezelés - háttérben futó task
@app.on_event("startup")
async def startup_event():
    """Alkalmazás indításakor elindítjuk a token lejárat ellenőrzést"""
    # FONTOS: Ellenőrizzük és javítjuk a root jogosultságokkal létező mappákat
    try:
        import os
        from app.config import settings
        from pathlib import Path
        import stat
        import shutil
        
        base_path = Path(settings.ark_serverfiles_base)
        current_uid = os.getuid()
        current_gid = os.getgid()
        
        # FONTOS: Először ellenőrizzük és javítjuk a base mappa szülő mappáit is
        # Mert ha a base mappa szülő mappája root jogosultságokkal létezik, akkor az új mappák is root jogosultságokkal jönnek létre
        parent_path = base_path.parent
        if parent_path.exists():
            try:
                stat_info = parent_path.stat()
                if stat_info.st_uid == 0 and current_uid != 0:
                    logging.warning(f"Root jogosultságokkal létező szülő mappa észlelve: {parent_path}")
                    try:
                        os.chmod(parent_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                        os.chown(parent_path, current_uid, current_gid)
                        logging.info(f"✓ Szülő mappa jogosultságok javítva: {parent_path}")
                    except (PermissionError, OSError) as e:
                        logging.error(f"⚠️ Nem sikerült javítani a szülő mappa jogosultságait {parent_path}: {e}")
            except (PermissionError, OSError):
                pass
        
        # FONTOS: Ellenőrizzük és javítjuk a base mappát is!
        # Ha a base mappa root jogosultságokkal létezik, akkor az új mappák is root jogosultságokkal jönnek létre
        if base_path.exists():
            try:
                stat_info = base_path.stat()
                if stat_info.st_uid == 0 and current_uid != 0:
                    logging.warning(f"Root jogosultságokkal létező base mappa észlelve: {base_path}")
                    try:
                        os.chmod(base_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                        os.chown(base_path, current_uid, current_gid)
                        logging.info(f"✓ Base mappa jogosultságok javítva: {base_path}")
                    except (PermissionError, OSError) as e:
                        logging.error(f"⚠️ Nem sikerült javítani a base mappa jogosultságait {base_path}: {e}")
            except (PermissionError, OSError):
                pass
        
        # FONTOS: NE hozzuk létre a base mappát, csak ellenőrizzük, ha már létezik!
        # Ha a base mappa nem létezik, NE hozzuk létre automatikusan!
        # Csak akkor ellenőrizzük, ha már létezik
        if base_path.exists():
            # Végigmegyünk az összes user_* mappán (csak akkor, ha a base mappa létezik)
            try:
                user_dirs = list(base_path.glob("user_*"))
            except (PermissionError, OSError):
                user_dirs = []
            
            for user_dir in user_dirs:
                if user_dir.is_dir():
                    try:
                        stat_info = user_dir.stat()
                        if stat_info.st_uid == 0 and current_uid != 0:
                            logging.warning(f"Root jogosultságokkal létező mappa észlelve: {user_dir}")
                            # Próbáljuk meg javítani a jogosultságokat
                            try:
                                # Rekurzívan beállítjuk a jogosultságokat
                                for root, dirs, files in os.walk(user_dir):
                                    for d in dirs:
                                        try:
                                            dir_path = Path(root) / d
                                            os.chmod(dir_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                                            os.chown(dir_path, current_uid, current_gid)
                                        except (PermissionError, OSError):
                                            pass
                                    for f in files:
                                        try:
                                            file_path = Path(root) / f
                                            os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                                            os.chown(file_path, current_uid, current_gid)
                                        except (PermissionError, OSError):
                                            pass
                                # A mappa maga is
                                os.chmod(user_dir, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                                os.chown(user_dir, current_uid, current_gid)
                                logging.info(f"✓ Jogosultságok javítva: {user_dir}")
                            except (PermissionError, OSError) as e:
                                logging.error(f"⚠️ Nem sikerült javítani a jogosultságokat {user_dir}: {e}")
                                # Ha nem sikerült javítani, próbáljuk meg átnevezni
                                try:
                                    backup_path = base_path / f"{user_dir.name}.root_backup"
                                    if backup_path.exists():
                                        # Ha már létezik a backup, próbáljuk meg törölni
                                        try:
                                            shutil.rmtree(backup_path)
                                        except:
                                            pass
                                    user_dir.rename(backup_path)
                                    logging.warning(f"⚠️ Root jogosultságokkal létező mappa átnevezve: {backup_path}")
                                    logging.warning(f"⚠️ FONTOS: Manuálisan töröld ezt a mappát sudo-val: sudo rm -rf {backup_path}")
                                except (PermissionError, OSError) as rename_e:
                                    logging.error(f"⚠️ Nem sikerült átnevezni a mappát {user_dir}: {rename_e}")
                                    logging.error(f"⚠️ FONTOS: Manuálisan javítsd a jogosultságokat sudo-val: sudo chown -R {current_uid}:{current_gid} {user_dir}")
                    except (PermissionError, OSError):
                        pass
    except Exception as e:
        logging.warning(f"Startup ellenőrzés során hiba: {e}")
    
    # FONTOS: Ellenőrizzük, hogy nincs-e automatikusan elindított steamcmd folyamat
    # Ha van pending vagy installing státuszú telepítés, akkor NEM indítjuk újra automatikusan
    try:
        from app.database import SessionLocal, UserServerFiles
        db = SessionLocal()
        try:
            pending_installations = db.query(UserServerFiles).filter(
                UserServerFiles.installation_status.in_(["pending", "installing"])
            ).all()
            if pending_installations:
                logging.warning(f"⚠️ {len(pending_installations)} pending/installing telepítés található az adatbázisban")
                logging.warning("⚠️ Ezek a telepítések NEM indítódnak újra automatikusan startup-nál")
                # Átállítjuk failed-re, hogy ne maradjon pending állapotban
                for installation in pending_installations:
                    installation.installation_status = "failed"
                    installation.installation_log = (installation.installation_log or "") + "\n[SYSTEM] Telepítés megszakadt a manager újraindításakor"
                db.commit()
                logging.info(f"✓ {len(pending_installations)} telepítés átállítva failed státuszra")
        except Exception as e:
            logging.warning(f"Pending telepítések ellenőrzése során hiba: {e}")
            db.rollback()
        finally:
            db.close()
    except Exception as e:
        logging.warning(f"Pending telepítések ellenőrzése során hiba: {e}")
    
    from app.tasks.token_expiry_task import token_expiry_worker
    asyncio.create_task(token_expiry_worker())
    logging.info("Token lejárat ellenőrzés elindítva")
    
    # FONTOS: Végül ismét ellenőrizzük, hogy ne jöjjön létre root jogosultságokkal mappa
    # (valami más folyamat hozhatja létre a startup event után)
    try:
        base_path = Path(settings.ark_serverfiles_base)
        current_uid = os.getuid()
        current_gid = os.getgid()
        
        if base_path.exists():
            try:
                user_dirs = list(base_path.glob("user_*"))
            except (PermissionError, OSError):
                user_dirs = []
            
            for user_dir in user_dirs:
                if user_dir.is_dir():
                    try:
                        stat_info = user_dir.stat()
                        if stat_info.st_uid == 0 and current_uid != 0:
                            logging.warning(f"⚠️ Root jogosultságokkal létező mappa észlelve startup után: {user_dir}")
                            # Próbáljuk meg javítani
                            try:
                                os.chmod(user_dir, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                                os.chown(user_dir, current_uid, current_gid)
                                logging.info(f"✓ Jogosultságok javítva: {user_dir}")
                            except (PermissionError, OSError):
                                # Ha nem sikerül, próbáljuk meg átnevezni
                                try:
                                    backup_path = base_path / f"{user_dir.name}.root_backup"
                                    if backup_path.exists():
                                        import shutil
                                        shutil.rmtree(backup_path)
                                    user_dir.rename(backup_path)
                                    logging.warning(f"⚠️ Mappa átnevezve: {backup_path}")
                                except (PermissionError, OSError):
                                    pass
                    except (PermissionError, OSError):
                        pass
    except Exception as e:
        logging.warning(f"Végső ellenőrzés során hiba: {e}")

# Updating oldal router
from fastapi.responses import HTMLResponse

@app.get("/updating", response_class=HTMLResponse)
async def updating_page(request: Request):
    """Updating oldal - frissítés közben"""
    return templates.TemplateResponse("updating.html", {"request": request})

# Template globális elérhetővé tétele
def get_templates():
    return templates

@app.get("/")
async def root(request: Request):
    """Főoldal - átirányítás login-ra"""
    return RedirectResponse(url="/login", status_code=302)

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "version": "2.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
