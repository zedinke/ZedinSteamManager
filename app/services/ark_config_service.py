"""
Ark szerver konfigurációs fájlok kezelése
GameUserSettings.ini és Game.ini fájlok beolvasása és mentése
"""

import configparser
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import re
from app.services.symlink_service import get_server_dedicated_config_path

# Beállítások kategóriák szerinti csoportosítása
SETTING_CATEGORIES = {
    # GameUserSettings.ini kategóriák
    # Megjegyzés: SessionName, ServerAdminPassword, ServerPassword, MaxPlayers, RCONEnabled, MessageOfTheDay, MOTDDuration
    # ezek a szerver szerkesztés oldalon vannak, ezért itt nincsenek
    "Általános Szerver Beállítások": {
        "ServerSettings": ["ServerName", "ServerPVE", "ServerHardcore", "ServerAutoSave"],
        "SessionSettings": ["Port", "QueryPort"]
    },
    "RCON Beállítások": {
        "ServerSettings": ["RCONPort"],
        "SessionSettings": ["RCONPort"]
    },
    "Üzenetek és Értesítések": {
        "ServerSettings": ["AlwaysNotifyPlayerLeft", "DontAlwaysNotifyPlayerJoined"]
    },
    "Játékmenet Beállítások": {
        "ServerSettings": ["ServerCrosshair", "ServerForceNoHud", "ShowFloatingDamageText", "AllowThirdPersonPlayer", "EnablePvPGamma", "EnablePvEGamma"]
    },
    "Karakter és Tárgy Letöltés/Feltöltés": {
        "ServerSettings": ["PreventDownloadSurvivors", "PreventDownloadItems", "PreventDownloadDinos", "PreventUploadSurvivors", "PreventUploadItems", "PreventUploadDinos", "NoTributeDownloads"]
    },
    "Dinoszaurusz Limit Beállítások": {
        "ServerSettings": ["MaxTamedDinos", "MaxTamedDinosPerPlayer", "MaxPlatformSaddleStructureLimit"]
    },
    "Törzs Beállítások": {
        "ServerSettings": ["MaxNumberOfPlayersInTribe", "MaxTribes", "MaxTribeLogs", "OneMaxTribeLogPerPlayer", "PvEAllowTribeWar", "PvEAllowTribeWarCancel"]
    },
    "PvE Beállítások": {
        "ServerSettings": ["DisableStructureDecayPvE", "AllowFlyerCarryPvE", "EnablePvEAllowFriendlyFire", "PvEStructureDecayPeriodMultiplier", "PvEStructureDecayDestructionPeriod", "PvEDisableStructureDecayPvE", "DisableDinoDecayPvE"]
    },
    "PvP Beállítások": {
        "ServerSettings": ["PvPStructureDecay", "PvPStructureDecayPeriodMultiplier", "DisableDinoDecayPvP", "AllowFlyerCarryPvP", "PvPZoneStructureDamageMultiplier"]
    },
    "Struktúra Beállítások": {
        "ServerSettings": ["DisableStructurePlacementCollision", "EnableExtraStructurePreventionVolumes", "StructureDamageRepairCooldown", "StructureDamageRepairCooldownInSeconds", "StructureDamageRepairCooldownMultiplier", "StructureDamageRepairCooldownExcludeTime", "StructureDamageRepairCooldownExcludeTimeInSeconds", "StructureDamageRepairCooldownExcludeTimeMultiplier"]
    },
    "Gyors Pusztulás Beállítások": {
        "ServerSettings": ["FastDecayInterval", "FastDecayUnclaimedBuildingTime", "FastDecayUnclaimedItemTime"]
    },
    "Speciális Játékmenet Beállítások": {
        "ServerSettings": ["AllowRaidDinoFeeding", "PreventDiseases", "PreventMateBoost", "PreventImprint", "PreventSpawnLoci", "PreventFleeing", "PreventCrateSpawnsOnTopOfStructures", "ForceAllowCaveFlyers", "UseOptimizedHarvestingHealth", "AllowIntegratedSaddleBuff", "AllowMultipleAttachedC4", "ClampResourceHarvestDamage"]
    },
    "Hang Chat Beállítások": {
        "ServerSettings": ["GlobalVoiceChat", "ProximityChat", "NoVoiceChat"]
    },
    # Game.ini kategóriák
    "Nehézség Beállítások": {
        "ServerSettings": ["DifficultyOffset", "OverrideOfficialDifficulty", "OverrideOfficialDifficultyValue", "MaxDifficulty"]
    },
    "Idő Beállítások": {
        "ServerSettings": ["DayCycleSpeedScale", "DayTimeSpeedScale", "NightTimeSpeedScale"]
    },
    "Sebzés Szorzók": {
        "ServerSettings": ["DinoDamageMultiplier", "PlayerDamageMultiplier", "StructureDamageMultiplier"]
    },
    "Ellenállás Szorzók": {
        "ServerSettings": ["PlayerResistanceMultiplier", "DinoResistanceMultiplier", "StructureResistanceMultiplier"]
    },
    "Tapasztalat és Szelídítés": {
        "ServerSettings": ["XPMultiplier", "TamingSpeedMultiplier"]
    },
    "Erőforrás Gyűjtés": {
        "ServerSettings": ["HarvestAmountMultiplier", "HarvestHealthMultiplier", "HarvestResourceItemAmountMultiplier", "ResourcesRespawnPeriodMultiplier"]
    },
    "Játékos Fogyasztás": {
        "ServerSettings": ["PlayerCharacterWaterDrainMultiplier", "PlayerCharacterFoodDrainMultiplier", "PlayerCharacterStaminaDrainMultiplier", "PlayerCharacterHealthRecoveryMultiplier"]
    },
    "Dinoszaurusz Fogyasztás": {
        "ServerSettings": ["DinoCharacterFoodDrainMultiplier", "DinoCharacterStaminaDrainMultiplier", "DinoCharacterHealthRecoveryMultiplier"]
    },
    "Dinoszaurusz Spawn": {
        "ServerSettings": ["DinoCountMultiplier", "DinoSpawnWeightMultiplier"]
    },
    "Növénytermesztés": {
        "ServerSettings": ["CropGrowthSpeedMultiplier", "CropDecaySpeedMultiplier"]
    },
    "Párzás és Szaporodás": {
        "ServerSettings": ["LayEggIntervalMultiplier", "MatingIntervalMultiplier", "MatingSpeedMultiplier", "MatingRangeMultiplier"]
    },
    "Bébi és Imprint Beállítások": {
        "ServerSettings": ["EggHatchSpeedMultiplier", "BabyMatureSpeedMultiplier", "BabyFoodConsumptionSpeedMultiplier", "BabyCuddleIntervalMultiplier", "BabyCuddleGracePeriodMultiplier", "BabyCuddleLoseImprintQualitySpeedMultiplier", "BabyImprintingStatScaleMultiplier"]
    },
    "Struktúra Pusztulás": {
        "ServerSettings": ["PvEStructureDecayPeriodMultiplier"]
    }
}

# Beállítások részletes leírásai
SETTING_DESCRIPTIONS = {
    # GameUserSettings.ini beállítások
    "ServerSettings": {
        "ServerAdminPassword": "Szerver admin jelszó - RCON és admin parancsokhoz használható. Fontos: Erős jelszót használj!",
        "ServerPassword": "Szerver jelszó - Ha be van állítva, csak jelszóval lehet csatlakozni. Üresen hagyva a szerver nyilvános lesz.",
        "MaxPlayers": "Maximum játékosok száma - Egyszerre hány játékos lehet a szerveren. Alapértelmezett: 70",
        "RCONEnabled": "RCON engedélyezése - Ha True, akkor RCON protokollal lehet távolról kezelni a szervert. Alapértelmezett: True",
        "RCONPort": "RCON port száma - Melyik porton figyeljen a RCON. Alapértelmezett: 27020",
        "ServerName": "Szerver neve - Ez jelenik meg a szerverlistában. Ez lesz a session name is.",
        "MessageOfTheDay": "MOTD üzenet (Message of the Day) - Ez az üzenet jelenik meg amikor valaki csatlakozik a szerverhez.",
        "MOTDDuration": "MOTD megjelenítési időtartam másodpercben - Mennyi ideig jelenjen meg a MOTD üzenet. Alapértelmezett: 10",
        "ServerCrosshair": "Kereszt célzó megjelenítése - Ha True, akkor a játékosoknak megjelenik a célzókereszt. Alapértelmezett: False",
        "ServerForceNoHud": "HUD elrejtése - Ha True, akkor a HUD (fejlécek, élet, stb.) el lesz rejtve. Alapértelmezett: False",
        "ShowFloatingDamageText": "Lebegő sebzés szöveg megjelenítése - Ha True, akkor lebegő számok jelennek meg amikor valaki sebzést szenved. Alapértelmezett: True",
        "EnablePvPGamma": "PvP gamma engedélyezése - Ha True, akkor PvP módban lehet gamma-t állítani (világosság). Alapértelmezett: False",
        "DisableStructureDecayPvE": "Struktúra pusztulás kikapcsolása PvE-n - Ha True, akkor PvE módban nem pusztulnak el az épületek idővel. Alapértelmezett: False",
        "AllowFlyerCarryPvE": "Repülő hordozás engedélyezése PvE-n - Ha True, akkor PvE módban a repülők hordozhatnak más lényeket/játékosokat. Alapértelmezett: True",
        "PreventDownloadSurvivors": "Karakter letöltés letiltása - Ha True, akkor nem lehet karaktereket letölteni más szerverekről. Alapértelmezett: False",
        "PreventDownloadItems": "Tárgyak letöltés letiltása - Ha True, akkor nem lehet tárgyakat letölteni más szerverekről. Alapértelmezett: False",
        "PreventDownloadDinos": "Dinoszauruszok letöltés letiltása - Ha True, akkor nem lehet dinoszauruszokat letölteni más szerverekről. Alapértelmezett: False",
        "PreventUploadSurvivors": "Karakter feltöltés letiltása - Ha True, akkor nem lehet karaktereket feltölteni más szerverekre. Alapértelmezett: False",
        "PreventUploadItems": "Tárgyak feltöltés letiltása - Ha True, akkor nem lehet tárgyakat feltölteni más szerverekre. Alapértelmezett: False",
        "PreventUploadDinos": "Dinoszauruszok feltöltés letiltása - Ha True, akkor nem lehet dinoszauruszokat feltölteni más szerverekre. Alapértelmezett: False",
        "NoTributeDownloads": "Tribute letöltés letiltása - Ha True, akkor nem lehet tribute fájlokat letölteni. Alapértelmezett: False",
        "AllowThirdPersonPlayer": "Harmadik személy nézet engedélyezése - Ha True, akkor a játékosok harmadik személy nézetet használhatnak. Alapértelmezett: True",
        "AlwaysNotifyPlayerLeft": "Játékos kilépés értesítés mindig - Ha True, akkor mindig értesítést kapnak a játékosok amikor valaki kilép. Alapértelmezett: False",
        "DontAlwaysNotifyPlayerJoined": "Játékos belépés értesítés nem mindig - Ha True, akkor nem mindig jelenik meg értesítés belépéskor. Alapértelmezett: False",
        "ServerHardcore": "Hardcore mód - Ha True, akkor hardcore módban fut a szerver (halálkor minden tárgy elveszik). Alapértelmezett: False",
        "ServerPVE": "PvE mód - Ha True, akkor PvE módban fut a szerver (játékosok nem sebzhetik egymást). Alapértelmezett: False",
        "ServerAutoSave": "Automatikus mentés - Ha True, akkor a szerver rendszeresen automatikusan ment. Alapértelmezett: True",
        "MaxTamedDinos": "Maximum megszelídített dinoszauruszok száma - Összesen hány megszelídített dinó lehet a szerveren. Alapértelmezett: 5000",
        "MaxTamedDinosPerPlayer": "Maximum megszelídített dinoszauruszok száma játékosonként - Játékosonként hány megszelídített dinó lehet. Alapértelmezett: 200",
        "MaxPlatformSaddleStructureLimit": "Maximum platform nyereg struktúra limit - Hány struktúra lehet egy platform nyeregen. Alapértelmezett: 88",
        "MaxNumberOfPlayersInTribe": "Maximum játékosok száma törzsben - Hány játékos lehet egy törzsben. Alapértelmezett: 50",
        "MaxTribes": "Maximum törzsek száma - Hány törzs lehet összesen a szerveren. Alapértelmezett: 1000",
        "MaxTribeLogs": "Maximum törzs logok száma - Hány log bejegyzés lehet egy törzsben. Alapértelmezett: 100",
        "OneMaxTribeLogPerPlayer": "Egy maximum törzs log játékosonként - Ha True, akkor játékosonként csak egy log bejegyzés lehet. Alapértelmezett: False",
        "AllowRaidDinoFeeding": "Rajtaütés dinoszaurusz etetés engedélyezése - Ha True, akkor rajtaütéskor lehet etetni a dinókat. Alapértelmezett: False",
        "PreventDiseases": "Betegségek megelőzése - Ha True, akkor nem lehet betegséget kapni. Alapértelmezett: False",
        "PreventMateBoost": "Párzás boost megelőzése - Ha True, akkor nem lehet párzás boost-ot kapni. Alapértelmezett: False",
        "PreventImprint": "Imprint megelőzése - Ha True, akkor nem lehet imprint-et kapni. Alapértelmezett: False",
        "PreventSpawnLoci": "Spawn lokációk megelőzése - Ha True, akkor nem lehet spawn lokációkat használni. Alapértelmezett: False",
        "PreventFleeing": "Menekülés megelőzése - Ha True, akkor a dinoszauruszok nem menekülnek. Alapértelmezett: False",
        "PreventCrateSpawnsOnTopOfStructures": "Láda spawn struktúrák tetején megelőzése - Ha True, akkor nem spawnolnak ládák struktúrák tetején. Alapértelmezett: False",
        "ForceAllowCaveFlyers": "Barlang repülők kényszerített engedélyezése - Ha True, akkor barlangokban is repülhetnek a repülők. Alapértelmezett: False",
        "EnablePvEAllowFriendlyFire": "PvE baráti tűz engedélyezése - Ha True, akkor PvE módban is lehet baráti tűz. Alapértelmezett: False",
        "EnablePvEGamma": "PvE gamma engedélyezése - Ha True, akkor PvE módban is lehet gamma-t állítani. Alapértelmezett: False",
        "PvEStructureDecayPeriodMultiplier": "PvE struktúra pusztulás időszorzó - Mennyivel lassabban pusztulnak el az épületek PvE-n. 1.0 = normál, 2.0 = kétszer lassabban. Alapértelmezett: 1.0",
        "PvEStructureDecayDestructionPeriod": "PvE struktúra pusztulás megsemmisítési időszak - Mennyi idő után pusztuljon el egy épület PvE-n (másodpercben).",
        "PvEDisableStructureDecayPvE": "PvE struktúra pusztulás letiltása - Ha True, akkor PvE módban egyáltalán nem pusztulnak el az épületek. Alapértelmezett: False",
        "PvPStructureDecay": "PvP struktúra pusztulás - Ha True, akkor PvP módban pusztulnak el az épületek idővel. Alapértelmezett: True",
        "PvPStructureDecayPeriodMultiplier": "PvP struktúra pusztulás időszorzó - Mennyivel lassabban pusztulnak el az épületek PvP-n. 1.0 = normál. Alapértelmezett: 1.0",
        "PvEAllowTribeWar": "PvE törzs háború engedélyezése - Ha True, akkor PvE módban is lehet törzs háború. Alapértelmezett: False",
        "PvEAllowTribeWarCancel": "PvE törzs háború megszakítás engedélyezése - Ha True, akkor PvE módban lehet megszakítani a törzs háborút. Alapértelmezett: False",
        "DisableDinoDecayPvE": "Dinoszaurusz pusztulás letiltása PvE-n - Ha True, akkor PvE módban nem pusztulnak el a dinoszauruszok idővel. Alapértelmezett: False",
        "DisableDinoDecayPvP": "Dinoszaurusz pusztulás letiltása PvP-n - Ha True, akkor PvP módban nem pusztulnak el a dinoszauruszok idővel. Alapértelmezett: False",
        "DisableStructurePlacementCollision": "Struktúra elhelyezés ütközés letiltása - Ha True, akkor lehet struktúrákat ütközés nélkül elhelyezni. Alapértelmezett: False",
        "EnableExtraStructurePreventionVolumes": "Extra struktúra megelőzési térfogatok engedélyezése - Ha True, akkor extra térfogatokkal lehet megelőzni az építést. Alapértelmezett: False",
        "UseOptimizedHarvestingHealth": "Optimalizált gyűjtés egészség használata - Ha True, akkor optimalizált algoritmust használ a gyűjtésnél. Alapértelmezett: False",
        "AllowIntegratedSaddleBuff": "Integrált nyereg buff engedélyezése - Ha True, akkor a nyeregek integrált buff-ot adnak. Alapértelmezett: False",
        "AllowMultipleAttachedC4": "Több csatolt C4 engedélyezése - Ha True, akkor több C4 is csatolható egyszerre. Alapértelmezett: False",
        "AllowFlyerCarryPvP": "Repülő hordozás engedélyezése PvP-n - Ha True, akkor PvP módban a repülők hordozhatnak más lényeket/játékosokat. Alapértelmezett: True",
        "FastDecayInterval": "Gyors pusztulás intervallum - Mennyi időnként ellenőrizze a gyors pusztulást (másodpercben).",
        "FastDecayUnclaimedBuildingTime": "Gyors pusztulás nem igényelt épület idő - Mennyi idő után pusztuljon el egy nem igényelt épület (másodpercben).",
        "FastDecayUnclaimedItemTime": "Gyors pusztulás nem igényelt tárgy idő - Mennyi idő után pusztuljon el egy nem igényelt tárgy (másodpercben).",
        "ClampResourceHarvestDamage": "Erőforrás gyűjtés sebzés szorítás - Ha True, akkor a gyűjtés sebzés korlátozva van. Alapértelmezett: False",
        "PvPZoneStructureDamageMultiplier": "PvP zóna struktúra sebzés szorzó - Mennyivel több sebzést szenvednek az épületek PvP zónában. 1.0 = normál. Alapértelmezett: 1.0",
        "GlobalVoiceChat": "Globális hang chat - Ha True, akkor a hang chat globális (mindenki hallja). Alapértelmezett: False",
        "ProximityChat": "Közelségi chat - Ha True, akkor a hang chat közelségi (csak a közelben lévők hallják). Alapértelmezett: True",
        "NoVoiceChat": "Hang chat letiltása - Ha True, akkor egyáltalán nincs hang chat. Alapértelmezett: False",
        "StructureDamageRepairCooldown": "Struktúra sebzés javítás cooldown - Mennyi idő után javítható egy struktúra újra (másodpercben).",
        "StructureDamageRepairCooldownInSeconds": "Struktúra sebzés javítás cooldown másodpercben - Ugyanaz mint a fenti, de másodpercben.",
        "StructureDamageRepairCooldownMultiplier": "Struktúra sebzés javítás cooldown szorzó - Mennyivel lassabban javítható egy struktúra. 1.0 = normál.",
        "StructureDamageRepairCooldownExcludeTime": "Struktúra sebzés javítás cooldown kizárt idő - Mennyi idő kizárva a cooldown-ból.",
        "StructureDamageRepairCooldownExcludeTimeInSeconds": "Struktúra sebzés javítás cooldown kizárt idő másodpercben - Ugyanaz mint a fenti, de másodpercben.",
        "StructureDamageRepairCooldownExcludeTimeMultiplier": "Struktúra sebzés javítás cooldown kizárt idő szorzó - Mennyivel módosul a kizárt idő.",
    },
    "SessionSettings": {
        "SessionName": "Szerver munkamenet neve - Ez jelenik meg a szerverlistában. Ez a szerver neve.",
        "MaxPlayers": "Maximum játékosok száma - Egyszerre hány játékos lehet a szerveren.",
        "Port": "Szerver port - Melyik porton figyeljen a szerver. Alapértelmezett: 7777",
        "QueryPort": "Query port - Melyik porton legyen elérhető a szerver query. Alapértelmezett: 27015",
        "ServerPassword": "Szerver jelszó - Ha be van állítva, csak jelszóval lehet csatlakozni.",
        "ServerAdminPassword": "Szerver admin jelszó - RCON és admin parancsokhoz használható.",
        "RCONEnabled": "RCON engedélyezése - Ha True, akkor RCON protokollal lehet távolról kezelni a szervert.",
        "RCONPort": "RCON port száma - Melyik porton figyeljen a RCON.",
        "ServerCrosshair": "Kereszt célzó megjelenítése - Ha True, akkor a játékosoknak megjelenik a célzókereszt.",
        "ServerForceNoHud": "HUD elrejtése - Ha True, akkor a HUD el lesz rejtve.",
        "ShowFloatingDamageText": "Lebegő sebzés szöveg megjelenítése - Ha True, akkor lebegő számok jelennek meg sebzéskor.",
        "EnablePvPGamma": "PvP gamma engedélyezése - Ha True, akkor PvP módban lehet gamma-t állítani.",
        "DisableStructureDecayPvE": "Struktúra pusztulás kikapcsolása PvE-n - Ha True, akkor PvE módban nem pusztulnak el az épületek.",
        "AllowFlyerCarryPvE": "Repülő hordozás engedélyezése PvE-n - Ha True, akkor PvE módban a repülők hordozhatnak más lényeket.",
    },
    # Game.ini beállítások
    "ServerSettings": {
        "DifficultyOffset": "Nehézségi offset - A játék nehézségi szintje. 0.0 = könnyű, 1.0 = nehéz. Alapértelmezett: 0.2",
        "OverrideOfficialDifficulty": "Hivatalos nehézség felülírása - Ha True, akkor felülírja a hivatalos nehézséget. Alapértelmezett: False",
        "OverrideOfficialDifficultyValue": "Hivatalos nehézség érték felülírása - Milyen nehézségi értéket használjon. 1.0-10.0 között.",
        "MaxDifficulty": "Maximum nehézség - Maximum nehézségi szint. Alapértelmezett: 1.0",
        "DayCycleSpeedScale": "Nap ciklus sebesség szorzó - Mennyivel gyorsabban teljen el egy nap. 1.0 = normál (50 perc), 2.0 = kétszer gyorsabban (25 perc). Alapértelmezett: 1.0",
        "DayTimeSpeedScale": "Nappali idő sebesség szorzó - Mennyivel gyorsabban teljen el a nappal. 1.0 = normál. Alapértelmezett: 1.0",
        "NightTimeSpeedScale": "Éjszakai idő sebesség szorzó - Mennyivel gyorsabban teljen el az éjszaka. 1.0 = normál. Alapértelmezett: 1.0",
        "DinoDamageMultiplier": "Dinoszaurusz sebzés szorzó - Mennyivel több sebzést okozzanak a dinoszauruszok. 1.0 = normál, 2.0 = kétszer több. Alapértelmezett: 1.0",
        "PlayerDamageMultiplier": "Játékos sebzés szorzó - Mennyivel több sebzést okozzanak a játékosok. 1.0 = normál. Alapértelmezett: 1.0",
        "StructureDamageMultiplier": "Struktúra sebzés szorzó - Mennyivel több sebzést szenvedjenek az épületek. 1.0 = normál. Alapértelmezett: 1.0",
        "PlayerResistanceMultiplier": "Játékos ellenállás szorzó - Mennyivel kevesebb sebzést szenvedjenek a játékosok. 1.0 = normál, 0.5 = fele sebzés. Alapértelmezett: 1.0",
        "DinoResistanceMultiplier": "Dinoszaurusz ellenállás szorzó - Mennyivel kevesebb sebzést szenvedjenek a dinoszauruszok. 1.0 = normál. Alapértelmezett: 1.0",
        "StructureResistanceMultiplier": "Struktúra ellenállás szorzó - Mennyivel kevesebb sebzést szenvedjenek az épületek. 1.0 = normál. Alapértelmezett: 1.0",
        "XPMultiplier": "Tapasztalati pont szorzó - Mennyivel gyorsabban szerezzenek tapasztalatot a játékosok. 1.0 = normál, 2.0 = kétszer gyorsabban. Alapértelmezett: 1.0",
        "TamingSpeedMultiplier": "Szelídítés sebesség szorzó - Mennyivel gyorsabban szelídíthetők meg a dinoszauruszok. 1.0 = normál, 2.0 = kétszer gyorsabban. Alapértelmezett: 1.0",
        "HarvestAmountMultiplier": "Gyűjtés mennyiség szorzó - Mennyivel több erőforrást gyűjtsenek a játékosok. 1.0 = normál, 2.0 = kétszer több. Alapértelmezett: 1.0",
        "HarvestHealthMultiplier": "Gyűjtés egészség szorzó - Mennyivel több egészséggel rendelkezzenek az erőforrások. 1.0 = normál. Alapértelmezett: 1.0",
        "PlayerCharacterWaterDrainMultiplier": "Játékos víz fogyasztás szorzó - Mennyivel gyorsabban fogyjon a víz. 1.0 = normál, 0.5 = fele gyorsabban. Alapértelmezett: 1.0",
        "PlayerCharacterFoodDrainMultiplier": "Játékos élelem fogyasztás szorzó - Mennyivel gyorsabban fogyjon az élelem. 1.0 = normál. Alapértelmezett: 1.0",
        "DinoCharacterFoodDrainMultiplier": "Dinoszaurusz élelem fogyasztás szorzó - Mennyivel gyorsabban fogyjon az élelem a dinoszauruszoknál. 1.0 = normál. Alapértelmezett: 1.0",
        "PlayerCharacterStaminaDrainMultiplier": "Játékos stamina fogyasztás szorzó - Mennyivel gyorsabban fogyjon a stamina. 1.0 = normál. Alapértelmezett: 1.0",
        "DinoCharacterStaminaDrainMultiplier": "Dinoszaurusz stamina fogyasztás szorzó - Mennyivel gyorsabban fogyjon a stamina a dinoszauruszoknál. 1.0 = normál. Alapértelmezett: 1.0",
        "PlayerCharacterHealthRecoveryMultiplier": "Játékos egészség regeneráció szorzó - Mennyivel gyorsabban regenerálódjon az egészség. 1.0 = normál, 2.0 = kétszer gyorsabban. Alapértelmezett: 1.0",
        "DinoCharacterHealthRecoveryMultiplier": "Dinoszaurusz egészség regeneráció szorzó - Mennyivel gyorsabban regenerálódjon az egészség a dinoszauruszoknál. 1.0 = normál. Alapértelmezett: 1.0",
        "DinoCountMultiplier": "Dinoszaurusz szám szorzó - Mennyivel több dinoszaurusz legyen a világban. 1.0 = normál, 2.0 = kétszer több. Alapértelmezett: 1.0",
        "DinoSpawnWeightMultiplier": "Dinoszaurusz spawn súly szorzó - Mennyivel nagyobb eséllyel spawnoljanak dinoszauruszok. 1.0 = normál. Alapértelmezett: 1.0",
        "HarvestResourceItemAmountMultiplier": "Gyűjtés erőforrás tárgy mennyiség szorzó - Mennyivel több tárgyat kapjanak gyűjtéskor. 1.0 = normál. Alapértelmezett: 1.0",
        "PvEStructureDecayPeriodMultiplier": "PvE struktúra pusztulás időszorzó - Mennyivel lassabban pusztuljanak el az épületek PvE-n. 1.0 = normál.",
        "ResourcesRespawnPeriodMultiplier": "Erőforrás újra spawn időszorzó - Mennyivel gyorsabban spawnoljanak újra az erőforrások. 1.0 = normál, 0.5 = fele idő alatt. Alapértelmezett: 1.0",
        "CropGrowthSpeedMultiplier": "Növény növekedés sebesség szorzó - Mennyivel gyorsabban nőjenek a növények. 1.0 = normál, 2.0 = kétszer gyorsabban. Alapértelmezett: 1.0",
        "CropDecaySpeedMultiplier": "Növény pusztulás sebesség szorzó - Mennyivel gyorsabban pusztuljanak el a növények. 1.0 = normál. Alapértelmezett: 1.0",
        "LayEggIntervalMultiplier": "Tojás rakás intervallum szorzó - Mennyivel gyorsabban rakjanak tojást a dinoszauruszok. 1.0 = normál, 0.5 = fele idő alatt. Alapértelmezett: 1.0",
        "MatingIntervalMultiplier": "Párzás intervallum szorzó - Mennyivel gyorsabban párzhatnak a dinoszauruszok. 1.0 = normál, 0.5 = fele idő alatt. Alapértelmezett: 1.0",
        "EggHatchSpeedMultiplier": "Tojás kikelés sebesség szorzó - Mennyivel gyorsabban keljenek ki a tojások. 1.0 = normál, 2.0 = kétszer gyorsabban. Alapértelmezett: 1.0",
        "BabyMatureSpeedMultiplier": "Bébi érés sebesség szorzó - Mennyivel gyorsabban érjenek fel a bébik. 1.0 = normál, 2.0 = kétszer gyorsabban. Alapértelmezett: 1.0",
        "BabyFoodConsumptionSpeedMultiplier": "Bébi élelem fogyasztás sebesség szorzó - Mennyivel gyorsabban fogyjon az élelem a bébiknél. 1.0 = normál, 0.5 = fele gyorsabban. Alapértelmezett: 1.0",
        "BabyCuddleIntervalMultiplier": "Bébi simogatás intervallum szorzó - Mennyivel gyorsabban kell simogatni a bébiket. 1.0 = normál, 0.5 = fele idő alatt. Alapértelmezett: 1.0",
        "BabyCuddleGracePeriodMultiplier": "Bébi simogatás kegyelem időszak szorzó - Mennyivel hosszabb legyen a kegyelem időszak. 1.0 = normál. Alapértelmezett: 1.0",
        "BabyCuddleLoseImprintQualitySpeedMultiplier": "Bébi simogatás imprint minőség vesztés sebesség szorzó - Mennyivel gyorsabban veszítse el az imprint minőséget. 1.0 = normál.",
        "BabyImprintingStatScaleMultiplier": "Bébi imprinting stat skála szorzó - Mennyivel több stat boost-ot kapjon az imprint. 1.0 = normál. Alapértelmezett: 1.0",
        "MatingSpeedMultiplier": "Párzás sebesség szorzó - Mennyivel gyorsabban fejeződjön be a párzás. 1.0 = normál. Alapértelmezett: 1.0",
        "MatingRangeMultiplier": "Párzás távolság szorzó - Mennyivel nagyobb távolságból párzhatnak a dinoszauruszok. 1.0 = normál. Alapértelmezett: 1.0",
    },
}

def get_setting_category(section: str, key: str) -> str:
    """
    Beállítás kategóriájának lekérése
    
    Args:
        section: INI section neve
        key: Beállítás kulcsa
    
    Returns:
        Kategória neve vagy "Egyedi" (ha nincs kategória, akkor egyedi beállítás)
    """
    for category, sections in SETTING_CATEGORIES.items():
        if section in sections and key in sections[section]:
            return category
    return "Egyedi"

def parse_ini_file(file_path: Path) -> Dict[str, Dict[str, Any]]:
    """
    INI fájl beolvasása és feldolgozása
    Ark specifikus formátumot is kezeli (nincs section header esetén)
    
    Args:
        file_path: INI fájl útvonala
    
    Returns:
        Dict: {section: {key: value}}
    """
    if not file_path.exists():
        print(f"Config fájl nem létezik: {file_path}")
        return {}
    
    result = {}
    current_section = None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Először próbáljuk meg a standard configparser-rel
        # Duplikált kulcsok esetén manuális parsing-ra váltunk
        try:
            # Próbáljuk meg a strict=False paramétert (Python 3.2+)
            try:
                config = configparser.ConfigParser(allow_no_value=True, strict=False)
            except TypeError:
                # Régebbi Python verzió, strict paraméter nélkül
                config = configparser.ConfigParser(allow_no_value=True)
            
            config.optionxform = str  # Case-sensitive kulcsok
            config.read(file_path, encoding='utf-8')
            
            for section in config.sections():
                result[section] = {}
                for key, value in config.items(section):
                    result[section][key] = convert_value(value)
            
            if result:
                return result
        except (configparser.DuplicateOptionError, configparser.DuplicateSectionError) as e:
            print(f"ConfigParser hiba (duplikált kulcs/szekció), manuális parsing: {e}")
        except Exception as e:
            print(f"ConfigParser hiba, manuális parsing: {e}")
        
        # Ha a configparser nem működik, manuális parsing
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            
            # Üres sor vagy komment
            if not line or line.startswith('#'):
                continue
            
            # Section header: [SectionName]
            if line.startswith('[') and line.endswith(']'):
                current_section = line[1:-1].strip()
                if current_section not in result:
                    result[current_section] = {}
                continue
            
            # Key=Value pár
            if '=' in line:
                try:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Ha nincs section, akkor "DEFAULT" section-t használunk
                    if current_section is None:
                        current_section = "ServerSettings"
                        if current_section not in result:
                            result[current_section] = {}
                    
                    # Duplikált kulcs kezelése: ha már létezik, figyelmeztetünk és az utolsó értéket tartjuk meg
                    if key in result[current_section]:
                        print(f"Figyelmeztetés: Duplikált kulcs '{key}' a '{current_section}' szekcióban (sor {line_num}). Az utolsó értéket használjuk.")
                    
                    result[current_section][key] = convert_value(value)
                except Exception as e:
                    print(f"Hiba a sor feldolgozásakor (sor {line_num}): {line} - {e}")
                    continue
        
        return result
    except Exception as e:
        print(f"Hiba az INI fájl beolvasásakor: {e}")
        import traceback
        traceback.print_exc()
        return {}

def convert_value(value: str) -> Any:
    """
    String érték konvertálása megfelelő típusra
    Csak explicit true/false értékeket konvertál boolean-ná, nem számokat
    
    Args:
        value: String érték
    
    Returns:
        Konvertált érték (bool, int, float, vagy string)
    """
    value = value.strip()
    value_lower = value.lower()
    
    # Boolean értékek - csak explicit true/false, NEM számok (1, 0)
    if value_lower in ('true', 'false', 'yes', 'no', 'on', 'off'):
        if value_lower in ('true', 'yes', 'on'):
            return True
        if value_lower in ('false', 'no', 'off'):
            return False
    
    # Szám értékek - először próbáljuk meg számként értelmezni
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
        Leírás vagy alapértelmezett leírás egyedi beállításokhoz
    """
    # Próbáljuk meg a section-t
    descriptions = SETTING_DESCRIPTIONS.get(section, {})
    description = descriptions.get(key, "")
    
    # Ha nincs leírás, próbáljuk meg más section-öket is (Game.ini és GameUserSettings.ini is használhatja ugyanazokat a section-öket)
    if not description:
        # Próbáljuk meg a "ServerSettings" section-t is (mert Game.ini is használhatja)
        if section != "ServerSettings":
            server_settings_descriptions = SETTING_DESCRIPTIONS.get("ServerSettings", {})
            description = server_settings_descriptions.get(key, "")
    
    # Ha még mindig nincs leírás, akkor egyedi beállítás - adjunk alapértelmezett leírást
    if not description:
        description = f"Egyedi beállítás: {key} - Ez a beállítás nincs a standard Ark beállítások között. Kérjük, ellenőrizze az Ark dokumentációját vagy a mod dokumentációját a pontos leírásért."
    
    return description

def is_boolean_setting(section: str, key: str, value: Any) -> bool:
    """
    Ellenőrzi, hogy a beállítás boolean típusú-e
    Csak akkor True, ha ténylegesen True/False értéket vesz fel (nem szám)
    
    Args:
        section: INI section neve
        key: Beállítás kulcsa
        value: Beállítás értéke
    
    Returns:
        True ha boolean, False egyébként
    """
    # Ha az érték boolean típusú (Python bool)
    if isinstance(value, bool):
        return True
    
    # Ha az érték string, akkor ellenőrizzük
    if isinstance(value, str):
        value_lower = value.strip().lower()
        # Csak akkor boolean, ha explicit true/false értékeket tartalmaz
        # NEM számokat (1, 0 nem számít boolean-nak, mert lehet szám is)
        if value_lower in ('true', 'false', 'yes', 'no', 'on', 'off'):
            return True
    
    # Ha szám típusú (int vagy float), akkor NEM boolean
    if isinstance(value, (int, float)):
        return False
    
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

def update_config_from_server_settings(
    server_path: Path,
    session_name: Optional[str] = None,
    server_admin_password: Optional[str] = None,
    server_password: Optional[str] = None,
    max_players: Optional[int] = None,
    rcon_enabled: Optional[bool] = None,
    rcon_port: Optional[int] = None,
    motd: Optional[str] = None,
    motd_duration: Optional[int] = None
) -> bool:
    """
    Konfigurációs fájlok frissítése szerver beállítások alapján
    
    Args:
        server_path: Szerver útvonal (symlink)
        session_name: Szerver munkamenet neve
        server_admin_password: Szerver admin jelszó
        server_password: Szerver jelszó
        max_players: Maximum játékosok száma
        rcon_enabled: RCON engedélyezve
        rcon_port: RCON port száma
        motd: MOTD üzenet
        motd_duration: MOTD időtartam másodpercben
    
    Returns:
        True ha sikeres, False egyébként
    """
    try:
        # Konfigurációs fájlok útvonalai
        game_user_settings_path, _ = get_server_config_files(server_path)
        
        if not game_user_settings_path:
            print(f"GameUserSettings.ini útvonal nem található")
            return False
        
        # Fájl beolvasása
        config_data = parse_ini_file(game_user_settings_path)
        
        # ServerSettings section biztosítása
        if "ServerSettings" not in config_data:
            config_data["ServerSettings"] = {}
        
        # Beállítások frissítése (csak ha meg vannak adva)
        if session_name is not None:
            config_data["ServerSettings"]["SessionName"] = session_name
        
        if server_admin_password is not None and server_admin_password.strip():
            config_data["ServerSettings"]["ServerAdminPassword"] = server_admin_password
        
        if server_password is not None:
            # Ha üres string, akkor töröljük a beállítást (nyilvános szerver)
            if server_password.strip():
                config_data["ServerSettings"]["ServerPassword"] = server_password
            else:
                # Üres jelszó = nyilvános szerver, töröljük a beállítást
                config_data["ServerSettings"].pop("ServerPassword", None)
        
        if max_players is not None:
            config_data["ServerSettings"]["MaxPlayers"] = max_players
        
        if rcon_enabled is not None:
            config_data["ServerSettings"]["RCONEnabled"] = rcon_enabled
        
        if rcon_port is not None:
            config_data["ServerSettings"]["RCONPort"] = rcon_port
        
        if motd is not None:
            if motd.strip():
                config_data["ServerSettings"]["MessageOfTheDay"] = motd
            else:
                # Üres MOTD = töröljük a beállítást
                config_data["ServerSettings"].pop("MessageOfTheDay", None)
        
        if motd_duration is not None:
            config_data["ServerSettings"]["MOTDDuration"] = motd_duration
        
        # Fájl mentése
        return save_ini_file(game_user_settings_path, config_data)
    except Exception as e:
        print(f"Hiba a konfigurációs fájlok frissítésekor: {e}")
        import traceback
        traceback.print_exc()
        return False
