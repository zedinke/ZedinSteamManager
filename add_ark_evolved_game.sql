-- Ark Survival Evolved játék hozzáadása az adatbázishoz
-- Futtasd ezt az SQL scriptet az adatbázisban

INSERT INTO games (name, steam_app_id, description, is_active, created_at)
VALUES ('Ark Survival Evolved', '376030', 'Ark Survival Evolved - Dedicated Server', 1, NOW())
ON DUPLICATE KEY UPDATE 
    is_active = 1,
    steam_app_id = '376030',
    description = 'Ark Survival Evolved - Dedicated Server';

