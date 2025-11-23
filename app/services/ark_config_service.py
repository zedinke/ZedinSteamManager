"""
Ark szerver konfigurációs fájlok kezelése
GameUserSettings.ini és Game.ini fájlok beolvasása és mentése
"""

import configparser
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import re
from app.services.symlink_service import get_server_dedicated_config_path

# Beállítások leírásai
SETTING_DESCRIPTIONS = {
    # GameUserSettings.ini beállítások
    "ServerSettings": {
        "ServerAdminPassword": "Szerver admin jelszó (RCON és admin parancsokhoz)",
        "ServerPassword": "Szerver jelszó (üres = nyilvános szerver)",
        "MaxPlayers": "Maximum játékosok száma",
        "RCONEnabled": "RCON engedélyezése (true/false)",
        "RCONPort": "RCON port száma",
        "ServerName": "Szerver neve (session name)",
        "MessageOfTheDay": "MOTD üzenet (Message of the Day)",
        "MOTDDuration": "MOTD megjelenítési időtartam másodpercben",
        "ServerCrosshair": "Kereszt célzó megjelenítése (true/false)",
        "ServerForceNoHud": "HUD elrejtése (true/false)",
        "ShowFloatingDamageText": "Lebegő sebzés szöveg megjelenítése (true/false)",
        "EnablePvPGamma": "PvP gamma engedélyezése (true/false)",
        "DisableStructureDecayPvE": "Struktúra pusztulás kikapcsolása PvE-n (true/false)",
        "AllowFlyerCarryPvE": "Repülő hordozás engedélyezése PvE-n (true/false)",
        "PreventDownloadSurvivors": "Karakter letöltés letiltása (true/false)",
        "PreventDownloadItems": "Tárgyak letöltés letiltása (true/false)",
        "PreventDownloadDinos": "Dinoszauruszok letöltés letiltása (true/false)",
        "PreventUploadSurvivors": "Karakter feltöltés letiltása (true/false)",
        "PreventUploadItems": "Tárgyak feltöltés letiltása (true/false)",
        "PreventUploadDinos": "Dinoszauruszok feltöltés letiltása (true/false)",
        "NoTributeDownloads": "Tribute letöltés letiltása (true/false)",
        "AllowThirdPersonPlayer": "Harmadik személy nézet engedélyezése (true/false)",
        "AlwaysNotifyPlayerLeft": "Játékos kilépés értesítés mindig (true/false)",
        "DontAlwaysNotifyPlayerJoined": "Játékos belépés értesítés nem mindig (true/false)",
        "ServerHardcore": "Hardcore mód (true/false)",
        "ServerPVE": "PvE mód (true/false)",
        "ServerAutoSave": "Automatikus mentés (true/false)",
        "MaxTamedDinos": "Maximum megszelídített dinoszauruszok száma",
        "MaxTamedDinosPerPlayer": "Maximum megszelídített dinoszauruszok száma játékosonként",
        "MaxPlatformSaddleStructureLimit": "Maximum platform nyereg struktúra limit",
        "MaxNumberOfPlayersInTribe": "Maximum játékosok száma törzsben",
        "MaxTribes": "Maximum törzsek száma",
        "MaxTribeLogs": "Maximum törzs logok száma",
        "OneMaxTribeLogPerPlayer": "Egy maximum törzs log játékosonként (true/false)",
        "AllowRaidDinoFeeding": "Rajtaütés dinoszaurusz etetés engedélyezése (true/false)",
        "PreventDiseases": "Betegségek megelőzése (true/false)",
        "PreventMateBoost": "Párzás boost megelőzése (true/false)",
        "PreventImprint": "Imprint megelőzése (true/false)",
        "PreventSpawnLoci": "Spawn lokációk megelőzése (true/false)",
        "PreventFleeing": "Menekülés megelőzése (true/false)",
        "PreventCrateSpawnsOnTopOfStructures": "Láda spawn struktúrák tetején megelőzése (true/false)",
        "ForceAllowCaveFlyers": "Barlang repülők kényszerített engedélyezése (true/false)",
        "EnablePvEAllowFriendlyFire": "PvE baráti tűz engedélyezése (true/false)",
        "EnablePvEGamma": "PvE gamma engedélyezése (true/false)",
        "PvEStructureDecayPeriodMultiplier": "PvE struktúra pusztulás időszorzó",
        "PvEStructureDecayDestructionPeriod": "PvE struktúra pusztulás megsemmisítési időszak",
        "PvEDisableStructureDecayPvE": "PvE struktúra pusztulás letiltása (true/false)",
        "PvPStructureDecay": "PvP struktúra pusztulás (true/false)",
        "PvPStructureDecayPeriodMultiplier": "PvP struktúra pusztulás időszorzó",
        "PvEAllowTribeWar": "PvE törzs háború engedélyezése (true/false)",
        "PvEAllowTribeWarCancel": "PvE törzs háború megszakítás engedélyezése (true/false)",
        "DisableDinoDecayPvE": "Dinoszaurusz pusztulás letiltása PvE-n (true/false)",
        "DisableDinoDecayPvP": "Dinoszaurusz pusztulás letiltása PvP-n (true/false)",
        "DisableStructurePlacementCollision": "Struktúra elhelyezés ütközés letiltása (true/false)",
        "EnableExtraStructurePreventionVolumes": "Extra struktúra megelőzési térfogatok engedélyezése (true/false)",
        "UseOptimizedHarvestingHealth": "Optimalizált gyűjtés egészség használata (true/false)",
        "AllowIntegratedSaddleBuff": "Integrált nyereg buff engedélyezése (true/false)",
        "AllowMultipleAttachedC4": "Több csatolt C4 engedélyezése (true/false)",
        "AllowFlyerCarryPvP": "Repülő hordozás engedélyezése PvP-n (true/false)",
        "FastDecayInterval": "Gyors pusztulás intervallum",
        "FastDecayUnclaimedBuildingTime": "Gyors pusztulás nem igényelt épület idő",
        "FastDecayUnclaimedItemTime": "Gyors pusztulás nem igényelt tárgy idő",
        "ClampResourceHarvestDamage": "Erőforrás gyűjtés sebzés szorítás (true/false)",
        "PvPZoneStructureDamageMultiplier": "PvP zóna struktúra sebzés szorzó",
        "GlobalVoiceChat": "Globális hang chat (true/false)",
        "ProximityChat": "Közelségi chat (true/false)",
        "NoVoiceChat": "Hang chat letiltása (true/false)",
        "StructureDamageRepairCooldown": "Struktúra sebzés javítás cooldown",
        "StructureDamageRepairCooldownInSeconds": "Struktúra sebzés javítás cooldown másodpercben",
        "StructureDamageRepairCooldownMultiplier": "Struktúra sebzés javítás cooldown szorzó",
        "StructureDamageRepairCooldownExcludeTime": "Struktúra sebzés javítás cooldown kizárt idő",
        "StructureDamageRepairCooldownExcludeTimeInSeconds": "Struktúra sebzés javítás cooldown kizárt idő másodpercben",
        "StructureDamageRepairCooldownExcludeTimeMultiplier": "Struktúra sebzés javítás cooldown kizárt idő szorzó",
        "StructureDamageRepairCooldownExcludeTimeInSeconds": "Struktúra sebzés javítás cooldown kizárt idő másodpercben",
        "StructureDamageRepairCooldownExcludeTimeMultiplier": "Struktúra sebzés javítás cooldown kizárt idő szorzó",
        "StructureDamageRepairCooldownExcludeTimeInSeconds": "Struktúra sebzés javítás cooldown kizárt idő másodpercben",
        "StructureDamageRepairCooldownExcludeTimeMultiplier": "Struktúra sebzés javítás cooldown kizárt idő szorzó",
    },
    "SessionSettings": {
        "SessionName": "Szerver munkamenet neve",
        "MaxPlayers": "Maximum játékosok száma",
        "Port": "Szerver port",
        "QueryPort": "Query port",
        "ServerPassword": "Szerver jelszó",
        "ServerAdminPassword": "Szerver admin jelszó",
        "RCONEnabled": "RCON engedélyezése (true/false)",
        "RCONPort": "RCON port",
        "ServerCrosshair": "Kereszt célzó megjelenítése (true/false)",
        "ServerForceNoHud": "HUD elrejtése (true/false)",
        "ShowFloatingDamageText": "Lebegő sebzés szöveg megjelenítése (true/false)",
        "EnablePvPGamma": "PvP gamma engedélyezése (true/false)",
        "DisableStructureDecayPvE": "Struktúra pusztulás kikapcsolása PvE-n (true/false)",
        "AllowFlyerCarryPvE": "Repülő hordozás engedélyezése PvE-n (true/false)",
    },
    # Game.ini beállítások
    "ServerSettings": {
        "DifficultyOffset": "Nehézségi offset (0.0-1.0)",
        "OverrideOfficialDifficulty": "Hivatalos nehézség felülírása (true/false)",
        "OverrideOfficialDifficultyValue": "Hivatalos nehézség érték felülírása",
        "MaxDifficulty": "Maximum nehézség",
        "DayCycleSpeedScale": "Nap ciklus sebesség szorzó",
        "DayTimeSpeedScale": "Nappali idő sebesség szorzó",
        "NightTimeSpeedScale": "Éjszakai idő sebesség szorzó",
        "DinoDamageMultiplier": "Dinoszaurusz sebzés szorzó",
        "PlayerDamageMultiplier": "Játékos sebzés szorzó",
        "StructureDamageMultiplier": "Struktúra sebzés szorzó",
        "PlayerResistanceMultiplier": "Játékos ellenállás szorzó",
        "DinoResistanceMultiplier": "Dinoszaurusz ellenállás szorzó",
        "StructureResistanceMultiplier": "Struktúra ellenállás szorzó",
        "XPMultiplier": "Tapasztalati pont szorzó",
        "TamingSpeedMultiplier": "Szelídítés sebesség szorzó",
        "HarvestAmountMultiplier": "Gyűjtés mennyiség szorzó",
        "HarvestHealthMultiplier": "Gyűjtés egészség szorzó",
        "PlayerCharacterWaterDrainMultiplier": "Játékos víz fogyasztás szorzó",
        "PlayerCharacterFoodDrainMultiplier": "Játékos élelem fogyasztás szorzó",
        "DinoCharacterFoodDrainMultiplier": "Dinoszaurusz élelem fogyasztás szorzó",
        "PlayerCharacterStaminaDrainMultiplier": "Játékos stamina fogyasztás szorzó",
        "DinoCharacterStaminaDrainMultiplier": "Dinoszaurusz stamina fogyasztás szorzó",
        "PlayerCharacterHealthRecoveryMultiplier": "Játékos egészség regeneráció szorzó",
        "DinoCharacterHealthRecoveryMultiplier": "Dinoszaurusz egészség regeneráció szorzó",
        "DinoCountMultiplier": "Dinoszaurusz szám szorzó",
        "DinoSpawnWeightMultiplier": "Dinoszaurusz spawn súly szorzó",
        "HarvestResourceItemAmountMultiplier": "Gyűjtés erőforrás tárgy mennyiség szorzó",
        "PvEStructureDecayPeriodMultiplier": "PvE struktúra pusztulás időszorzó",
        "ResourcesRespawnPeriodMultiplier": "Erőforrás újra spawn időszorzó",
        "CropGrowthSpeedMultiplier": "Növény növekedés sebesség szorzó",
        "CropDecaySpeedMultiplier": "Növény pusztulás sebesség szorzó",
        "LayEggIntervalMultiplier": "Tojás rakás intervallum szorzó",
        "MatingIntervalMultiplier": "Párzás intervallum szorzó",
        "EggHatchSpeedMultiplier": "Tojás kikelés sebesség szorzó",
        "BabyMatureSpeedMultiplier": "Bébi érés sebesség szorzó",
        "BabyFoodConsumptionSpeedMultiplier": "Bébi élelem fogyasztás sebesség szorzó",
        "BabyCuddleIntervalMultiplier": "Bébi simogatás intervallum szorzó",
        "BabyCuddleGracePeriodMultiplier": "Bébi simogatás kegyelem időszak szorzó",
        "BabyCuddleLoseImprintQualitySpeedMultiplier": "Bébi simogatás imprint minőség vesztés sebesség szorzó",
        "BabyImprintingStatScaleMultiplier": "Bébi imprinting stat skála szorzó",
        "MatingSpeedMultiplier": "Párzás sebesség szorzó",
        "MatingIntervalMultiplier": "Párzás intervallum szorzó",
        "MatingRangeMultiplier": "Párzás távolság szorzó",
        "MatingSpeedMultiplier": "Párzás sebesség szorzó",
        "MatingIntervalMultiplier": "Párzás intervallum szorzó",
        "MatingRangeMultiplier": "Párzás távolság szorzó",
    },
}

def parse_ini_file(file_path: Path) -> Dict[str, Dict[str, Any]]:
    """
    INI fájl beolvasása és feldolgozása
    
    Args:
        file_path: INI fájl útvonala
    
    Returns:
        Dict: {section: {key: value}}
    """
    if not file_path.exists():
        return {}
    
    config = configparser.ConfigParser()
    config.optionxform = str  # Case-sensitive kulcsok
    
    try:
        config.read(file_path, encoding='utf-8')
        
        result = {}
        for section in config.sections():
            result[section] = {}
            for key, value in config.items(section):
                # Próbáljuk meg konvertálni a típusokat
                result[section][key] = convert_value(value)
        
        return result
    except Exception as e:
        print(f"Hiba az INI fájl beolvasásakor: {e}")
        return {}

def convert_value(value: str) -> Any:
    """
    String érték konvertálása megfelelő típusra
    
    Args:
        value: String érték
    
    Returns:
        Konvertált érték (bool, int, float, vagy string)
    """
    value = value.strip()
    
    # Boolean értékek
    if value.lower() in ('true', '1', 'yes', 'on'):
        return True
    if value.lower() in ('false', '0', 'no', 'off'):
        return False
    
    # Szám értékek
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        pass
    
    # String marad
    return value

def save_ini_file(file_path: Path, data: Dict[str, Dict[str, Any]]) -> bool:
    """
    INI fájl mentése
    
    Args:
        file_path: INI fájl útvonala
        data: {section: {key: value}}
    
    Returns:
        True ha sikeres, False egyébként
    """
    try:
        config = configparser.ConfigParser()
        config.optionxform = str  # Case-sensitive kulcsok
        
        for section, items in data.items():
            if section not in config.sections():
                config.add_section(section)
            
            for key, value in items.items():
                # Konvertáljuk vissza string-re
                if isinstance(value, bool):
                    config.set(section, key, 'True' if value else 'False')
                else:
                    config.set(section, key, str(value))
        
        # Szülő mappa létrehozása
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Fájl mentése
        with open(file_path, 'w', encoding='utf-8') as f:
            config.write(f, space_around_delimiters=False)
        
        return True
    except Exception as e:
        print(f"Hiba az INI fájl mentésekor: {e}")
        import traceback
        traceback.print_exc()
        return False

def get_setting_description(section: str, key: str) -> str:
    """
    Beállítás leírásának lekérése
    
    Args:
        section: INI section neve
        key: Beállítás kulcsa
    
    Returns:
        Leírás vagy üres string
    """
    descriptions = SETTING_DESCRIPTIONS.get(section, {})
    return descriptions.get(key, "")

def is_boolean_setting(section: str, key: str, value: Any) -> bool:
    """
    Ellenőrzi, hogy a beállítás boolean típusú-e
    
    Args:
        section: INI section neve
        key: Beállítás kulcsa
        value: Beállítás értéke
    
    Returns:
        True ha boolean, False egyébként
    """
    # Ha a leírás tartalmazza a "true/false" szöveget, akkor boolean
    description = get_setting_description(section, key)
    if "true/false" in description.lower():
        return True
    
    # Ha az érték boolean típusú
    if isinstance(value, bool):
        return True
    
    # Ha az érték string és boolean értékeket tartalmaz
    if isinstance(value, str):
        return value.lower() in ('true', 'false', '1', '0', 'yes', 'no', 'on', 'off')
    
    return False

def get_server_config_files(server_path: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Szerver konfigurációs fájlok útvonalainak lekérése
    A dedikált Saved mappában lévő config mappát használja (nem a symlink-et)
    
    Args:
        server_path: Szerver útvonal (symlink)
    
    Returns:
        (GameUserSettings.ini útvonal, Game.ini útvonal)
    """
    # A config mappa a dedikált Saved mappában van
    from app.services.symlink_service import get_server_dedicated_saved_path
    dedicated_saved_path = get_server_dedicated_saved_path(server_path)
    dedicated_config_path = dedicated_saved_path / "Config" / "WindowsServer"
    
    game_user_settings = dedicated_config_path / "GameUserSettings.ini"
    game_ini = dedicated_config_path / "Game.ini"
    
    return game_user_settings, game_ini
