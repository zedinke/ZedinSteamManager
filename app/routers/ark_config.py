"""
Ark szerver konfigurációs fájlok kezelése
GameUserSettings.ini és Game.ini szerkesztése
"""

from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from pathlib import Path
from app.database import get_db, User, ServerInstance
from app.services.ark_config_service import (
    parse_ini_file, save_ini_file, get_setting_description,
    is_boolean_setting, get_server_config_files, get_setting_category
)
from app.services.symlink_service import get_user_serverfiles_path
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/ark/servers", tags=["ark_config"])

# Template-ek inicializálása
BASE_DIR = Path(__file__).parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

def require_server_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Server Admin jogosultság ellenőrzése"""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=302,
            detail="Nincs bejelentkezve",
            headers={"Location": "/login"}
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.role.value not in ["server_admin", "manager_admin"]:
        raise HTTPException(
            status_code=403,
            detail="Nincs jogosultságod - Server Admin szükséges"
        )
    return user

def get_server_path_from_instance(server_instance: ServerInstance) -> Path:
    """Szerver útvonal lekérése a server instance-ból"""
    user_serverfiles = get_user_serverfiles_path(server_instance.server_admin_id)
    server_path = user_serverfiles / f"server_{server_instance.id}"
    return server_path

@router.get("/{server_id}/config", response_class=HTMLResponse)
async def show_config(
    request: Request,
    server_id: int,
    config_file: str = "GameUserSettings",
    db: Session = Depends(get_db)
):
    """Szerver konfigurációs fájl szerkesztése"""
    current_user = require_server_admin(request, db)
    
    # Szerver lekérése
    server = db.query(ServerInstance).filter(
        ServerInstance.id == server_id,
        ServerInstance.server_admin_id == current_user.id
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    # Szerver útvonal
    server_path = get_server_path_from_instance(server)
    
    if not server_path.exists() and not server_path.is_symlink():
        raise HTTPException(
            status_code=404,
            detail="Szerver útvonal nem található. Először hozd létre a szervert!"
        )
    
    # Konfigurációs fájlok útvonalai
    game_user_settings_path, game_ini_path = get_server_config_files(server_path)
    
    # Kiválasztott fájl meghatározása
    if config_file == "GameUserSettings":
        config_file_path = game_user_settings_path
        config_file_name = "GameUserSettings.ini"
    elif config_file == "Game":
        config_file_path = game_ini_path
        config_file_name = "Game.ini"
    else:
        raise HTTPException(status_code=400, detail="Érvénytelen konfigurációs fájl")
    
    # Konfigurációs fájl beolvasása
    config_data = {}
    if config_file_path and config_file_path.exists():
        config_data = parse_ini_file(config_file_path)
        print(f"DEBUG: Config fájl beolvasva: {config_file_path}")
        print(f"DEBUG: Sections: {list(config_data.keys())}")
        for section, items in config_data.items():
            print(f"DEBUG: Section '{section}' - {len(items)} beállítás")
    else:
        print(f"DEBUG: Config fájl nem létezik: {config_file_path}")
    
    # Beállítások, amik a szerver szerkesztés oldalon vannak - ezeket ne jelenítsük meg itt
    # (mert automatikusan frissülnek a szerver szerkesztésnél)
    excluded_settings = {
        "ServerSettings": ["SessionName", "ServerAdminPassword", "ServerPassword", "MaxPlayers", "RCONEnabled", "MessageOfTheDay", "MOTDDuration"],
        "SessionSettings": ["SessionName", "ServerAdminPassword", "ServerPassword", "MaxPlayers", "RCONEnabled"]
    }
    
    # Beállítások formázása a template-hez - kategóriák szerint csoportosítva
    settings_by_category = {}
    for section, items in config_data.items():
        for key, value in items.items():
            # Kihagyjuk azokat a beállításokat, amik a szerver szerkesztés oldalon vannak
            if section in excluded_settings and key in excluded_settings[section]:
                continue
            
            is_bool = is_boolean_setting(section, key, value)
            description = get_setting_description(section, key)
            category = get_setting_category(section, key)
            
            # Debug információk
            if not description:
                print(f"DEBUG: Nincs leírás: {section}.{key}")
            if category == "Egyéb":
                print(f"DEBUG: Egyéb kategória: {section}.{key}")
            
            if category not in settings_by_category:
                settings_by_category[category] = []
            
            settings_by_category[category].append({
                "section": section,
                "key": key,
                "value": value,
                "is_boolean": is_bool,
                "description": description,
                "field_name": f"{section}__{key}"  # Form field name
            })
    
    # Kategóriák sorrendje (először a fontosabbak)
    category_order = [
        "Általános Szerver Beállítások",
        "RCON Beállítások",
        "Üzenetek és Értesítések",
        "Játékmenet Beállítások",
        "Nehézség Beállítások",
        "Idő Beállítások",
        "Sebzés Szorzók",
        "Ellenállás Szorzók",
        "Tapasztalat és Szelídítés",
        "Erőforrás Gyűjtés",
        "Játékos Fogyasztás",
        "Dinoszaurusz Fogyasztás",
        "Dinoszaurusz Spawn",
        "Növénytermesztés",
        "Párzás és Szaporodás",
        "Bébi és Imprint Beállítások",
        "Karakter és Tárgy Letöltés/Feltöltés",
        "Dinoszaurusz Limit Beállítások",
        "Törzs Beállítások",
        "PvE Beállítások",
        "PvP Beállítások",
        "Struktúra Beállítások",
        "Struktúra Pusztulás",
        "Gyors Pusztulás Beállítások",
        "Speciális Játékmenet Beállítások",
        "Hang Chat Beállítások",
        "Egyedi"
    ]
    
    # Rendezett kategóriák
    sorted_categories = []
    for cat in category_order:
        if cat in settings_by_category:
            sorted_categories.append(cat)
    
    # Hozzáadjuk azokat a kategóriákat, amik nincsenek a listában
    for cat in settings_by_category.keys():
        if cat not in sorted_categories:
            sorted_categories.append(cat)
    
    return templates.TemplateResponse("ark/server_config.html", {
        "request": request,
        "current_user": current_user,
        "server": server,
        "config_file": config_file,
        "config_file_name": config_file_name,
        "config_data": config_data,
        "settings_by_category": settings_by_category,
        "sorted_categories": sorted_categories,
        "game_user_settings_path": game_user_settings_path,
        "game_ini_path": game_ini_path
    })

@router.post("/{server_id}/config/{config_file}/save")
async def save_config(
    request: Request,
    server_id: int,
    config_file: str,
    db: Session = Depends(get_db)
):
    """Konfigurációs fájl mentése"""
    current_user = require_server_admin(request, db)
    
    # Szerver lekérése
    server = db.query(ServerInstance).filter(
        ServerInstance.id == server_id,
        ServerInstance.server_admin_id == current_user.id
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    # Szerver útvonal
    server_path = get_server_path_from_instance(server)
    
    if not server_path.exists() and not server_path.is_symlink():
        raise HTTPException(
            status_code=404,
            detail="Szerver útvonal nem található"
        )
    
    # Konfigurációs fájlok útvonalai
    game_user_settings_path, game_ini_path = get_server_config_files(server_path)
    
    # Kiválasztott fájl meghatározása
    if config_file == "GameUserSettings":
        config_file_path = game_user_settings_path
    elif config_file == "Game":
        config_file_path = game_ini_path
    else:
        raise HTTPException(status_code=400, detail="Érvénytelen konfigurációs fájl")
    
    if not config_file_path:
        raise HTTPException(
            status_code=404,
            detail="Konfigurációs fájl útvonal nem található"
        )
    
    # Form adatok feldolgozása
    form_data = await request.form()
    
    # Konfigurációs adatok újraépítése
    config_data = {}
    
    # Először beolvassuk az összes értéket
    form_dict = {}
    for field_name, value in form_data.items():
        if "__" in field_name:
            # Ha checkbox, akkor lehet több érték (hidden false + checkbox true)
            if field_name in form_dict:
                # Ha már van érték, akkor a checkbox be van jelölve (true)
                form_dict[field_name] = 'true'
            else:
                form_dict[field_name] = value
    
    # Beállítások, amik a szerver szerkesztés oldalon vannak - ezeket ne mentjük itt
    excluded_settings = {
        "ServerSettings": ["SessionName", "ServerAdminPassword", "ServerPassword", "MaxPlayers", "RCONEnabled", "MessageOfTheDay", "MOTDDuration"],
        "SessionSettings": ["SessionName", "ServerAdminPassword", "ServerPassword", "MaxPlayers", "RCONEnabled"]
    }
    
    for field_name, value in form_dict.items():
        if "__" in field_name:
            section, key = field_name.split("__", 1)
            
            # Kihagyjuk azokat a beállításokat, amik a szerver szerkesztés oldalon vannak
            if section in excluded_settings and key in excluded_settings[section]:
                continue
            
            if section not in config_data:
                config_data[section] = {}
            
            # Érték konvertálása
            if value.lower() in ('true', '1', 'yes', 'on'):
                config_data[section][key] = True
            elif value.lower() in ('false', '0', 'no', 'off'):
                config_data[section][key] = False
            else:
                # Próbáljuk meg számként értelmezni
                try:
                    if '.' in value:
                        config_data[section][key] = float(value)
                    else:
                        config_data[section][key] = int(value)
                except ValueError:
                    config_data[section][key] = value
    
    # Fájl mentése
    if save_ini_file(config_file_path, config_data):
        return RedirectResponse(
            url=f"/ark/servers/{server_id}/config?config_file={config_file}&success=Konfiguráció+mentve",
            status_code=302
        )
    else:
        raise HTTPException(
            status_code=500,
            detail="Konfiguráció mentése sikertelen"
        )

@router.get("/{server_id}/config/{config_file}/raw", response_class=HTMLResponse)
async def show_raw_config(
    request: Request,
    server_id: int,
    config_file: str,
    db: Session = Depends(get_db)
):
    """Raw konfigurációs fájl szerkesztése"""
    current_user = require_server_admin(request, db)
    
    # Szerver lekérése
    server = db.query(ServerInstance).filter(
        ServerInstance.id == server_id,
        ServerInstance.server_admin_id == current_user.id
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    # Szerver útvonal
    server_path = get_server_path_from_instance(server)
    
    if not server_path.exists() and not server_path.is_symlink():
        raise HTTPException(
            status_code=404,
            detail="Szerver útvonal nem található. Először hozd létre a szervert!"
        )
    
    # Konfigurációs fájlok útvonalai
    game_user_settings_path, game_ini_path = get_server_config_files(server_path)
    
    # Kiválasztott fájl meghatározása
    if config_file == "GameUserSettings":
        config_file_path = game_user_settings_path
        config_file_name = "GameUserSettings.ini"
    elif config_file == "Game":
        config_file_path = game_ini_path
        config_file_name = "Game.ini"
    else:
        raise HTTPException(status_code=400, detail="Érvénytelen konfigurációs fájl")
    
    # Fájl tartalmának beolvasása
    file_content = ""
    if config_file_path and config_file_path.exists():
        try:
            with open(config_file_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
        except Exception as e:
            print(f"Hiba a fájl beolvasásakor: {e}")
            file_content = ""
    
    return templates.TemplateResponse("ark/server_config_raw.html", {
        "request": request,
        "current_user": current_user,
        "server": server,
        "config_file": config_file,
        "config_file_name": config_file_name,
        "file_content": file_content,
        "config_file_path": config_file_path
    })

@router.post("/{server_id}/config/{config_file}/raw/save")
async def save_raw_config(
    request: Request,
    server_id: int,
    config_file: str,
    file_content: str = Form(...),
    db: Session = Depends(get_db)
):
    """Raw konfigurációs fájl mentése"""
    current_user = require_server_admin(request, db)
    
    # Szerver lekérése
    server = db.query(ServerInstance).filter(
        ServerInstance.id == server_id,
        ServerInstance.server_admin_id == current_user.id
    ).first()
    
    if not server:
        raise HTTPException(status_code=404, detail="Szerver nem található")
    
    # Szerver útvonal
    server_path = get_server_path_from_instance(server)
    
    if not server_path.exists() and not server_path.is_symlink():
        raise HTTPException(
            status_code=404,
            detail="Szerver útvonal nem található"
        )
    
    # Konfigurációs fájlok útvonalai
    game_user_settings_path, game_ini_path = get_server_config_files(server_path)
    
    # Kiválasztott fájl meghatározása
    if config_file == "GameUserSettings":
        config_file_path = game_user_settings_path
    elif config_file == "Game":
        config_file_path = game_ini_path
    else:
        raise HTTPException(status_code=400, detail="Érvénytelen konfigurációs fájl")
    
    if not config_file_path:
        raise HTTPException(
            status_code=404,
            detail="Konfigurációs fájl útvonal nem található"
        )
    
    # Fájl mentése
    try:
        # Szülő mappa létrehozása
        config_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Fájl írása
        with open(config_file_path, 'w', encoding='utf-8') as f:
            f.write(file_content)
        
        return RedirectResponse(
            url=f"/ark/servers/{server_id}/config/{config_file}/raw?success=Konfiguráció+mentve",
            status_code=302
        )
    except Exception as e:
        print(f"Hiba a fájl mentésekor: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Konfiguráció mentése sikertelen: {str(e)}"
        )

