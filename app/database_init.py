"""
Adatbázis inicializálás
"""

import sys
from pathlib import Path

# Projekt gyökér hozzáadása a Python path-hoz
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.database import (
    Base, engine, SessionLocal, User, UserRole,
    Ticket, TicketMessage, TicketRating, TicketStatus,
    ChatRoom, ChatMessage, Game, ServerInstance, TokenExtensionRequest, CartItem, TokenRequest,
    TokenPricingRule, TokenBasePrice, Cluster, ArkServerFiles
)
from app.services.auth_service import get_password_hash
from app.config import settings

def init_db():
    """Adatbázis táblák létrehozása"""
    print("Adatbázis táblák létrehozása...")
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        
        # Először csak a régi táblákat hozzuk létre (ha még nincsenek)
        # Az új táblákat (tickets, chat) manuálisan hozzuk létre
        old_tables = ['users', 'tokens', 'notifications', 'server_admin_admins', 'servers', 'admin_servers']
        tables_to_create = [t for t in old_tables if t not in existing_tables]
        
        if tables_to_create:
            # Csak a régi táblák modelljeit használjuk
            from app.database import User, Token, Notification, ServerAdminAdmin, Server, AdminServer
            Base.metadata.create_all(bind=engine, tables=[
                User.__table__,
                Token.__table__,
                Notification.__table__,
                ServerAdminAdmin.__table__,
                Server.__table__,
                AdminServer.__table__
            ])
            print("✓ Régi táblák létrehozva")
        else:
            print("✓ Régi táblák már léteznek")
        
        # Users tábla ellenőrzése
        if 'users' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('users')]
            indexes = [idx['name'] for idx in inspector.get_indexes('users')]
            
            # created_by_id oszlop hozzáadása ha hiányzik
            if 'created_by_id' not in columns:
                print("created_by_id oszlop hozzáadása a users táblához...")
                with engine.connect() as conn:
                    # Először az oszlop
                    conn.execute(text("""
                        ALTER TABLE users 
                        ADD COLUMN created_by_id INT(11) UNSIGNED NULL
                    """))
                    conn.commit()
                    
                    # Aztán az index, ha még nincs
                    if 'idx_created_by' not in indexes:
                        conn.execute(text("""
                            ALTER TABLE users 
                            ADD INDEX idx_created_by (created_by_id)
                        """))
                        conn.commit()
                print("✓ created_by_id oszlop hozzáadva")
        
        # Tokens tábla ellenőrzése
        if 'tokens' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('tokens')]
            indexes = [idx['name'] for idx in inspector.get_indexes('tokens')]
            
            # generated_by_id oszlop hozzáadása ha hiányzik
            # Először ellenőrizzük, hogy van-e generated_by (régi név)
            has_generated_by = 'generated_by' in columns
            has_generated_by_id = 'generated_by_id' in columns
            
            if not has_generated_by_id:
                print("generated_by_id oszlop hozzáadása a tokens táblához...")
                with engine.connect() as conn:
                    # Ha van generated_by oszlop, átnevezzük generated_by_id-re
                    if has_generated_by:
                        print("  generated_by oszlop átnevezése generated_by_id-re...")
                        conn.execute(text("""
                            ALTER TABLE tokens 
                            CHANGE COLUMN generated_by generated_by_id INT(11) UNSIGNED NOT NULL
                        """))
                        conn.commit()
                    else:
                        # Ha nincs egyik sem, hozzáadjuk
                        # Először NULL-ként adjuk hozzá, hogy ne legyen probléma ha vannak régi rekordok
                        conn.execute(text("""
                            ALTER TABLE tokens 
                            ADD COLUMN generated_by_id INT(11) UNSIGNED NULL
                        """))
                        conn.commit()
                        
                        # Kitöltjük a meglévő rekordokat (ha vannak) az első Manager Admin ID-jával
                        conn.execute(text("""
                            UPDATE tokens 
                            SET generated_by_id = (SELECT id FROM users WHERE role = 'manager_admin' LIMIT 1)
                            WHERE generated_by_id IS NULL
                        """))
                        conn.commit()
                        
                        # Most már NOT NULL-ra állíthatjuk
                        conn.execute(text("""
                            ALTER TABLE tokens 
                            MODIFY COLUMN generated_by_id INT(11) UNSIGNED NOT NULL
                        """))
                        conn.commit()
                    
                    # Foreign key hozzáadása
                    try:
                        conn.execute(text("""
                            ALTER TABLE tokens 
                            ADD CONSTRAINT fk_tokens_generated_by 
                            FOREIGN KEY (generated_by_id) REFERENCES users(id) ON DELETE CASCADE
                        """))
                        conn.commit()
                    except Exception as e:
                        # Ha már létezik a foreign key, akkor nem baj
                        if "Duplicate foreign key" not in str(e) and "already exists" not in str(e).lower():
                            print(f"  Figyelmeztetés: Foreign key hozzáadása: {e}")
                    
                    # Index hozzáadása, ha még nincs
                    token_indexes = [idx['name'] for idx in inspector.get_indexes('tokens')]
                    if 'ix_tokens_generated_by_id' not in token_indexes:
                        try:
                            conn.execute(text("""
                                ALTER TABLE tokens 
                                ADD INDEX ix_tokens_generated_by_id (generated_by_id)
                            """))
                            conn.commit()
                        except Exception as e:
                            if "Duplicate key name" not in str(e):
                                print(f"  Figyelmeztetés: Index hozzáadása: {e}")
                print("✓ generated_by_id oszlop hozzáadva")
        
        # Új táblák létrehozása (tickets, chat stb.) - külön kezelés foreign key problémák miatt
        # Frissítjük a létező táblák listáját
        existing_tables = inspector.get_table_names()
        
        # Helper függvény a users.id típusának lekéréséhez
        def get_users_id_type():
            """Lekéri a users.id oszlop típusát"""
            # Közvetlenül az adatbázisból kérdezzük le, hogy biztosan jó legyen
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT COLUMN_TYPE 
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_SCHEMA = DATABASE() 
                    AND TABLE_NAME = 'users' 
                    AND COLUMN_NAME = 'id'
                """))
                row = result.fetchone()
                if row:
                    return row[0]
            # Ha nem találjuk, próbáljuk meg az inspector-ral
            users_columns = inspector.get_columns('users')
            for col in users_columns:
                if col['name'] == 'id':
                    col_type = col['type']
                    # SQLAlchemy típusból MySQL típus
                    type_str = str(col_type).upper()
                    if 'UNSIGNED' in type_str or 'INT UNSIGNED' in type_str:
                        return "INT(11) UNSIGNED"
                    elif 'INT' in type_str or 'INTEGER' in type_str:
                        return "INT(11)"
            return "INT(11)"  # Alapértelmezés (nem UNSIGNED, mert a kimenet szerint INT(11))
        
        id_type = get_users_id_type()
        print(f"  users.id típusa: {id_type}")
        
        # Tickets tábla
        if 'tickets' not in existing_tables:
            print("tickets tábla létrehozása...")
            try:
                with engine.connect() as conn:
                    # Először a táblát foreign key nélkül
                    conn.execute(text(f"""
                        CREATE TABLE tickets (
                            id {id_type} NOT NULL AUTO_INCREMENT,
                            user_id {id_type} NOT NULL,
                            title VARCHAR(255) NOT NULL,
                            description TEXT NOT NULL,
                            status VARCHAR(20) NOT NULL,
                            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            closed_at DATETIME NULL,
                            closed_by_id {id_type} NULL,
                            PRIMARY KEY (id),
                            INDEX ix_tickets_user_id (user_id),
                            INDEX ix_tickets_status (status),
                            INDEX ix_tickets_created_at (created_at)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """))
                    conn.commit()
                    print("  ✓ tickets tábla létrehozva (foreign key nélkül)")
                    
                    # Foreign key-ek hozzáadása külön
                    try:
                        conn.execute(text("""
                            ALTER TABLE tickets
                            ADD CONSTRAINT fk_tickets_user_id
                            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                        """))
                        conn.commit()
                        print("  ✓ user_id foreign key hozzáadva")
                    except Exception as e:
                        error_str = str(e).lower()
                        if "duplicate foreign key" not in error_str and "already exists" not in error_str:
                            print(f"    ⚠ Figyelmeztetés: user_id foreign key: {e}")
                        else:
                            print("  ✓ user_id foreign key már létezik")
                    
                    try:
                        conn.execute(text("""
                            ALTER TABLE tickets
                            ADD CONSTRAINT fk_tickets_closed_by_id
                            FOREIGN KEY (closed_by_id) REFERENCES users(id) ON DELETE SET NULL
                        """))
                        conn.commit()
                        print("  ✓ closed_by_id foreign key hozzáadva")
                    except Exception as e:
                        error_str = str(e).lower()
                        if "duplicate foreign key" not in error_str and "already exists" not in error_str:
                            print(f"    ⚠ Figyelmeztetés: closed_by_id foreign key: {e}")
                        else:
                            print("  ✓ closed_by_id foreign key már létezik")
                print("✓ tickets tábla létrehozva")
            except Exception as e:
                print(f"  ✗ Hiba a tickets tábla létrehozásakor: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("✓ tickets tábla már létezik")
        
        # Frissítjük a létező táblák listáját
        existing_tables = inspector.get_table_names()
        
        # Helper függvény a tickets.id típusának lekéréséhez
        def get_tickets_id_type():
            """Lekéri a tickets.id oszlop típusát"""
            try:
                with engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT COLUMN_TYPE 
                        FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_SCHEMA = DATABASE() 
                        AND TABLE_NAME = 'tickets' 
                        AND COLUMN_NAME = 'id'
                    """))
                    row = result.fetchone()
                    if row:
                        return row[0]
            except:
                pass
            return id_type  # Fallback
        
        # Ticket messages tábla - csak akkor hozzuk létre, ha a tickets tábla létezik
        if 'tickets' in existing_tables and 'ticket_messages' not in existing_tables:
            print("ticket_messages tábla létrehozása...")
            try:
                tickets_id_type = get_tickets_id_type()
                with engine.connect() as conn:
                    conn.execute(text(f"""
                        CREATE TABLE ticket_messages (
                            id {id_type} NOT NULL AUTO_INCREMENT,
                            ticket_id {tickets_id_type} NOT NULL,
                            user_id {id_type} NOT NULL,
                            message TEXT NOT NULL,
                            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            PRIMARY KEY (id),
                            INDEX ix_ticket_messages_ticket_id (ticket_id),
                            INDEX ix_ticket_messages_user_id (user_id),
                            INDEX ix_ticket_messages_created_at (created_at),
                            CONSTRAINT fk_ticket_messages_ticket_id
                                FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
                            CONSTRAINT fk_ticket_messages_user_id
                                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """))
                    conn.commit()
                    print("✓ ticket_messages tábla létrehozva")
            except Exception as e:
                print(f"  Figyelmeztetés: ticket_messages tábla: {e}")
                import traceback
                traceback.print_exc()
        elif 'tickets' not in existing_tables:
            print("  Figyelmeztetés: ticket_messages tábla nem hozható létre, mert a tickets tábla nem létezik")
        
        # Ticket ratings tábla - csak akkor hozzuk létre, ha a tickets tábla létezik
        if 'tickets' in existing_tables and 'ticket_ratings' not in existing_tables:
            print("ticket_ratings tábla létrehozása...")
            try:
                tickets_id_type = get_tickets_id_type()
                with engine.connect() as conn:
                    conn.execute(text(f"""
                        CREATE TABLE ticket_ratings (
                            id {id_type} NOT NULL AUTO_INCREMENT,
                            ticket_id {tickets_id_type} NOT NULL,
                            user_id {id_type} NOT NULL,
                            rating INTEGER NOT NULL,
                            comment TEXT NULL,
                            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            PRIMARY KEY (id),
                            UNIQUE KEY uq_ticket_ratings_ticket_id (ticket_id),
                            INDEX ix_ticket_ratings_user_id (user_id),
                            CONSTRAINT fk_ticket_ratings_ticket_id
                                FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
                            CONSTRAINT fk_ticket_ratings_user_id
                                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """))
                    conn.commit()
                print("✓ ticket_ratings tábla létrehozva")
            except Exception as e:
                print(f"  Figyelmeztetés: ticket_ratings tábla: {e}")
                import traceback
                traceback.print_exc()
        elif 'tickets' not in existing_tables:
            print("  Figyelmeztetés: ticket_ratings tábla nem hozható létre, mert a tickets tábla nem létezik")
        
        # Chat rooms tábla
        if 'chat_rooms' not in existing_tables:
            print("chat_rooms tábla létrehozása...")
            try:
                with engine.connect() as conn:
                    conn.execute(text(f"""
                        CREATE TABLE chat_rooms (
                            id {id_type} NOT NULL AUTO_INCREMENT,
                            name VARCHAR(100) NOT NULL,
                            game_name VARCHAR(100) NULL,
                            description TEXT NULL,
                            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            PRIMARY KEY (id),
                            UNIQUE KEY uq_chat_rooms_name (name),
                            INDEX ix_chat_rooms_game_name (game_name)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """))
                    conn.commit()
                print("✓ chat_rooms tábla létrehozva")
            except Exception as e:
                print(f"  Figyelmeztetés: chat_rooms tábla: {e}")
        
        # Frissítjük a létező táblák listáját
        existing_tables = inspector.get_table_names()
        
        # Helper függvény a chat_rooms.id típusának lekéréséhez
        def get_chat_rooms_id_type():
            """Lekéri a chat_rooms.id oszlop típusát"""
            try:
                with engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT COLUMN_TYPE 
                        FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_SCHEMA = DATABASE() 
                        AND TABLE_NAME = 'chat_rooms' 
                        AND COLUMN_NAME = 'id'
                    """))
                    row = result.fetchone()
                    if row:
                        return row[0]
            except:
                pass
            return id_type  # Fallback
        
        # Chat messages tábla - csak akkor hozzuk létre, ha a chat_rooms tábla létezik
        if 'chat_rooms' in existing_tables and 'chat_messages' not in existing_tables:
            print("chat_messages tábla létrehozása...")
            try:
                chat_rooms_id_type = get_chat_rooms_id_type()
                with engine.connect() as conn:
                    conn.execute(text(f"""
                        CREATE TABLE chat_messages (
                            id {id_type} NOT NULL AUTO_INCREMENT,
                            room_id {chat_rooms_id_type} NOT NULL,
                            user_id {id_type} NOT NULL,
                            message TEXT NOT NULL,
                            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            PRIMARY KEY (id),
                            INDEX ix_chat_messages_room_id (room_id),
                            INDEX ix_chat_messages_user_id (user_id),
                            INDEX ix_chat_messages_created_at (created_at),
                            CONSTRAINT fk_chat_messages_room_id
                                FOREIGN KEY (room_id) REFERENCES chat_rooms(id) ON DELETE CASCADE,
                            CONSTRAINT fk_chat_messages_user_id
                                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """))
                    conn.commit()
                print("✓ chat_messages tábla létrehozva")
            except Exception as e:
                print(f"  Figyelmeztetés: chat_messages tábla: {e}")
                import traceback
                traceback.print_exc()
        elif 'chat_rooms' not in existing_tables:
            print("  Figyelmeztetés: chat_messages tábla nem hozható létre, mert a chat_rooms tábla nem létezik")
        
        # Games tábla
        if 'games' not in existing_tables:
            print("games tábla létrehozása...")
            try:
                with engine.connect() as conn:
                    conn.execute(text(f"""
                        CREATE TABLE games (
                            id {id_type} NOT NULL AUTO_INCREMENT,
                            name VARCHAR(100) NOT NULL,
                            steam_app_id VARCHAR(50) NULL,
                            description TEXT NULL,
                            is_active TINYINT(1) NOT NULL DEFAULT 1,
                            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            PRIMARY KEY (id),
                            UNIQUE KEY uq_games_name (name),
                            INDEX ix_games_steam_app_id (steam_app_id),
                            INDEX ix_games_is_active (is_active)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """))
                    conn.commit()
                print("✓ games tábla létrehozva")
            except Exception as e:
                print(f"  Figyelmeztetés: games tábla: {e}")
        
        # Server instances tábla
        if 'server_instances' not in existing_tables:
            print("server_instances tábla létrehozása...")
            try:
                with engine.connect() as conn:
                    # Ellenőrizzük a games.id típusát
                    games_id_type = id_type
                    if 'games' in inspector.get_table_names():
                        result = conn.execute(text("""
                            SELECT COLUMN_TYPE 
                            FROM INFORMATION_SCHEMA.COLUMNS 
                            WHERE TABLE_SCHEMA = DATABASE() 
                            AND TABLE_NAME = 'games' 
                            AND COLUMN_NAME = 'id'
                        """))
                        row = result.fetchone()
                        if row:
                            games_id_type = row[0]
                    
                    # Ellenőrizzük a tokens.id típusát
                    tokens_id_type = id_type
                    if 'tokens' in inspector.get_table_names():
                        result = conn.execute(text("""
                            SELECT COLUMN_TYPE 
                            FROM INFORMATION_SCHEMA.COLUMNS 
                            WHERE TABLE_SCHEMA = DATABASE() 
                            AND TABLE_NAME = 'tokens' 
                            AND COLUMN_NAME = 'id'
                        """))
                        row = result.fetchone()
                        if row:
                            tokens_id_type = row[0]
                    
                    conn.execute(text(f"""
                        CREATE TABLE server_instances (
                            id {id_type} NOT NULL AUTO_INCREMENT,
                            game_id {games_id_type} NOT NULL,
                            server_admin_id {id_type} NOT NULL,
                            name VARCHAR(100) NOT NULL,
                            port INT NULL,
                            status VARCHAR(20) NOT NULL DEFAULT 'stopped',
                            config JSON NULL,
                            token_used_id {tokens_id_type} NULL,
                            token_expires_at DATETIME NULL,
                            scheduled_deletion_date DATETIME NULL,
                            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            started_at DATETIME NULL,
                            stopped_at DATETIME NULL,
                            PRIMARY KEY (id),
                            INDEX ix_server_instances_game_id (game_id),
                            INDEX ix_server_instances_server_admin_id (server_admin_id),
                            INDEX ix_server_instances_status (status),
                            INDEX ix_server_instances_token_used_id (token_used_id),
                            INDEX ix_server_instances_token_expires_at (token_expires_at),
                            INDEX ix_server_instances_scheduled_deletion_date (scheduled_deletion_date),
                            INDEX ix_server_instances_created_at (created_at),
                            CONSTRAINT fk_server_instances_game_id
                                FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
                            CONSTRAINT fk_server_instances_server_admin_id
                                FOREIGN KEY (server_admin_id) REFERENCES users(id) ON DELETE CASCADE,
                            CONSTRAINT fk_server_instances_token_used_id
                                FOREIGN KEY (token_used_id) REFERENCES tokens(id) ON DELETE SET NULL
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """))
                    conn.commit()
                print("✓ server_instances tábla létrehozva")
            except Exception as e:
                print(f"  Figyelmeztetés: server_instances tábla: {e}")
        
        # Ha a server_instances tábla már létezik, ellenőrizzük az új oszlopokat
        if 'server_instances' in inspector.get_table_names():
            existing_columns = [col['name'] for col in inspector.get_columns('server_instances')]
            
            # token_expires_at oszlop hozzáadása, ha nincs
            if 'token_expires_at' not in existing_columns:
                print("token_expires_at oszlop hozzáadása a server_instances táblához...")
                try:
                    with engine.connect() as conn:
                        conn.execute(text("""
                            ALTER TABLE server_instances 
                            ADD COLUMN token_expires_at DATETIME NULL,
                            ADD INDEX ix_server_instances_token_expires_at (token_expires_at)
                        """))
                        conn.commit()
                    print("✓ token_expires_at oszlop hozzáadva")
                except Exception as e:
                    print(f"  Figyelmeztetés: token_expires_at oszlop: {e}")
            
            # scheduled_deletion_date oszlop hozzáadása, ha nincs
            if 'scheduled_deletion_date' not in existing_columns:
                print("scheduled_deletion_date oszlop hozzáadása a server_instances táblához...")
                try:
                    with engine.connect() as conn:
                        conn.execute(text("""
                            ALTER TABLE server_instances 
                            ADD COLUMN scheduled_deletion_date DATETIME NULL,
                            ADD INDEX ix_server_instances_scheduled_deletion_date (scheduled_deletion_date)
                        """))
                        conn.commit()
                    print("✓ scheduled_deletion_date oszlop hozzáadva")
                except Exception as e:
                    print(f"  Figyelmeztetés: scheduled_deletion_date oszlop: {e}")
        
        # Token extension requests tábla
        if 'token_extension_requests' not in existing_tables:
            print("token_extension_requests tábla létrehozása...")
            try:
                with engine.connect() as conn:
                    # Ellenőrizzük a tokens.id típusát
                    tokens_id_type = id_type
                    if 'tokens' in inspector.get_table_names():
                        result = conn.execute(text("""
                            SELECT COLUMN_TYPE 
                            FROM INFORMATION_SCHEMA.COLUMNS 
                            WHERE TABLE_SCHEMA = DATABASE() 
                            AND TABLE_NAME = 'tokens' 
                            AND COLUMN_NAME = 'id'
                        """))
                        row = result.fetchone()
                        if row:
                            tokens_id_type = row[0]
                    
                    conn.execute(text(f"""
                        CREATE TABLE token_extension_requests (
                            id {id_type} NOT NULL AUTO_INCREMENT,
                            token_id {tokens_id_type} NOT NULL,
                            user_id {id_type} NOT NULL,
                            requested_days INT NOT NULL,
                            status VARCHAR(20) NOT NULL DEFAULT 'pending',
                            notes TEXT NULL,
                            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            processed_at DATETIME NULL,
                            processed_by_id {id_type} NULL,
                            PRIMARY KEY (id),
                            INDEX ix_token_extension_requests_token_id (token_id),
                            INDEX ix_token_extension_requests_user_id (user_id),
                            INDEX ix_token_extension_requests_status (status),
                            INDEX ix_token_extension_requests_created_at (created_at),
                            CONSTRAINT fk_token_extension_requests_token_id
                                FOREIGN KEY (token_id) REFERENCES tokens(id) ON DELETE CASCADE,
                            CONSTRAINT fk_token_extension_requests_user_id
                                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                            CONSTRAINT fk_token_extension_requests_processed_by_id
                                FOREIGN KEY (processed_by_id) REFERENCES users(id) ON DELETE SET NULL
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """))
                    conn.commit()
                print("✓ token_extension_requests tábla létrehozva")
            except Exception as e:
                print(f"  Figyelmeztetés: token_extension_requests tábla: {e}")
        
        # Cart items tábla
        if 'cart_items' not in existing_tables:
            print("cart_items tábla létrehozása...")
            try:
                with engine.connect() as conn:
                    # Ellenőrizzük a tokens.id típusát
                    tokens_id_type = id_type
                    if 'tokens' in inspector.get_table_names():
                        result = conn.execute(text("""
                            SELECT COLUMN_TYPE 
                            FROM INFORMATION_SCHEMA.COLUMNS 
                            WHERE TABLE_SCHEMA = DATABASE() 
                            AND TABLE_NAME = 'tokens' 
                            AND COLUMN_NAME = 'id'
                        """))
                        row = result.fetchone()
                        if row:
                            tokens_id_type = row[0]
                    
                    conn.execute(text(f"""
                        CREATE TABLE cart_items (
                            id {id_type} NOT NULL AUTO_INCREMENT,
                            user_id {id_type} NOT NULL,
                            item_type VARCHAR(20) NOT NULL,
                            token_type VARCHAR(20) NULL,
                            quantity INT NOT NULL DEFAULT 1,
                            requested_days INT NULL,
                            expires_in_days INT NULL,
                            token_id {tokens_id_type} NULL,
                            notes TEXT NULL,
                            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            PRIMARY KEY (id),
                            INDEX ix_cart_items_user_id (user_id),
                            INDEX ix_cart_items_item_type (item_type),
                            INDEX ix_cart_items_token_id (token_id),
                            INDEX ix_cart_items_created_at (created_at),
                            CONSTRAINT fk_cart_items_user_id
                                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                            CONSTRAINT fk_cart_items_token_id
                                FOREIGN KEY (token_id) REFERENCES tokens(id) ON DELETE CASCADE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """))
                    conn.commit()
                print("✓ cart_items tábla létrehozva")
            except Exception as e:
                print(f"  Figyelmeztetés: cart_items tábla: {e}")
        
        # Ha a cart_items tábla már létezik, ellenőrizzük az új oszlopokat
        if 'cart_items' in inspector.get_table_names():
            existing_columns = [col['name'] for col in inspector.get_columns('cart_items')]
            
            # expires_in_days oszlop hozzáadása, ha nincs
            if 'expires_in_days' not in existing_columns:
                print("expires_in_days oszlop hozzáadása a cart_items táblához...")
                try:
                    with engine.connect() as conn:
                        conn.execute(text("""
                            ALTER TABLE cart_items 
                            ADD COLUMN expires_in_days INT NULL
                        """))
                        conn.commit()
                    print("✓ expires_in_days oszlop hozzáadva")
                except Exception as e:
                    print(f"  Figyelmeztetés: expires_in_days oszlop: {e}")
        
        # Token requests tábla létrehozása
        existing_tables = inspector.get_table_names()
        if 'token_requests' not in existing_tables:
            print("token_requests tábla létrehozása...")
            try:
                with engine.connect() as conn:
                    # Users és tokens tábla ID típusának lekérése
                    result = conn.execute(text("""
                        SELECT COLUMN_TYPE 
                        FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_SCHEMA = DATABASE() 
                        AND TABLE_NAME = 'users' 
                        AND COLUMN_NAME = 'id'
                    """))
                    row = result.fetchone()
                    users_id_type = row[0] if row else id_type
                    
                    conn.execute(text(f"""
                        CREATE TABLE token_requests (
                            id {users_id_type} NOT NULL AUTO_INCREMENT,
                            user_id {users_id_type} NOT NULL,
                            token_type VARCHAR(20) NOT NULL,
                            quantity INT NOT NULL DEFAULT 1,
                            expires_in_days INT NULL,
                            status VARCHAR(20) NOT NULL DEFAULT 'pending',
                            notes TEXT NULL,
                            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            processed_at DATETIME NULL,
                            processed_by_id {users_id_type} NULL,
                            PRIMARY KEY (id),
                            INDEX ix_token_requests_user_id (user_id),
                            INDEX ix_token_requests_status (status),
                            INDEX ix_token_requests_created_at (created_at),
                            CONSTRAINT fk_token_requests_user_id
                                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                            CONSTRAINT fk_token_requests_processed_by_id
                                FOREIGN KEY (processed_by_id) REFERENCES users(id) ON DELETE SET NULL
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """))
                    conn.commit()
                print("✓ token_requests tábla létrehozva")
            except Exception as e:
                print(f"  Figyelmeztetés: token_requests tábla: {e}")
        
        # Token base prices tábla létrehozása
        existing_tables = inspector.get_table_names()
        if 'token_base_prices' not in existing_tables:
            print("token_base_prices tábla létrehozása...")
            try:
                with engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT COLUMN_TYPE 
                        FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_SCHEMA = DATABASE() 
                        AND TABLE_NAME = 'users' 
                        AND COLUMN_NAME = 'id'
                    """))
                    row = result.fetchone()
                    users_id_type = row[0] if row else id_type
                    
                    conn.execute(text(f"""
                        CREATE TABLE token_base_prices (
                            id {users_id_type} NOT NULL AUTO_INCREMENT,
                            token_type VARCHAR(20) NOT NULL,
                            item_type VARCHAR(20) NOT NULL,
                            base_price INT NOT NULL,
                            price_per_day INT NULL,
                            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            PRIMARY KEY (id),
                            UNIQUE KEY uk_token_base_prices (token_type, item_type),
                            INDEX ix_token_base_prices_token_type (token_type),
                            INDEX ix_token_base_prices_item_type (item_type)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """))
                    conn.commit()
                print("✓ token_base_prices tábla létrehozva")
            except Exception as e:
                print(f"  Figyelmeztetés: token_base_prices tábla: {e}")
        
        # Token pricing rules tábla létrehozása
        existing_tables = inspector.get_table_names()
        if 'token_pricing_rules' not in existing_tables:
            print("token_pricing_rules tábla létrehozása...")
            try:
                with engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT COLUMN_TYPE 
                        FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_SCHEMA = DATABASE() 
                        AND TABLE_NAME = 'users' 
                        AND COLUMN_NAME = 'id'
                    """))
                    row = result.fetchone()
                    users_id_type = row[0] if row else id_type
                    
                    conn.execute(text(f"""
                        CREATE TABLE token_pricing_rules (
                            id {users_id_type} NOT NULL AUTO_INCREMENT,
                            name VARCHAR(100) NOT NULL,
                            rule_type VARCHAR(20) NOT NULL,
                            is_active BOOLEAN NOT NULL DEFAULT TRUE,
                            discount_percent INT NULL,
                            min_quantity INT NULL,
                            quantity_discount_percent INT NULL,
                            min_duration_days INT NULL,
                            duration_discount_percent INT NULL,
                            applies_to_token_type VARCHAR(20) NULL,
                            applies_to_item_type VARCHAR(20) NULL,
                            valid_from DATETIME NULL,
                            valid_until DATETIME NULL,
                            priority INT NOT NULL DEFAULT 0,
                            notes TEXT NULL,
                            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            PRIMARY KEY (id),
                            INDEX ix_token_pricing_rules_rule_type (rule_type),
                            INDEX ix_token_pricing_rules_is_active (is_active)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """))
                    conn.commit()
                print("✓ token_pricing_rules tábla létrehozva")
            except Exception as e:
                print(f"  Figyelmeztetés: token_pricing_rules tábla: {e}")
        
        # Clusters tábla létrehozása
        existing_tables = inspector.get_table_names()
        if 'clusters' not in existing_tables:
            print("clusters tábla létrehozása...")
            try:
                with engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT COLUMN_TYPE 
                        FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_SCHEMA = DATABASE() 
                        AND TABLE_NAME = 'users' 
                        AND COLUMN_NAME = 'id'
                    """))
                    row = result.fetchone()
                    users_id_type = row[0] if row else id_type
                    
                    conn.execute(text(f"""
                        CREATE TABLE clusters (
                            id {users_id_type} NOT NULL AUTO_INCREMENT,
                            server_admin_id {users_id_type} NOT NULL,
                            cluster_id VARCHAR(50) NOT NULL UNIQUE,
                            name VARCHAR(100) NOT NULL,
                            description TEXT NULL,
                            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            PRIMARY KEY (id),
                            INDEX ix_clusters_server_admin_id (server_admin_id),
                            INDEX ix_clusters_cluster_id (cluster_id),
                            CONSTRAINT fk_clusters_server_admin_id
                                FOREIGN KEY (server_admin_id) REFERENCES users(id) ON DELETE CASCADE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """))
                    conn.commit()
                print("✓ clusters tábla létrehozva")
            except Exception as e:
                print(f"  Figyelmeztetés: clusters tábla: {e}")
        
        # Ark server files tábla létrehozása
        existing_tables = inspector.get_table_names()
        if 'ark_server_files' not in existing_tables:
            print("ark_server_files tábla létrehozása...")
            try:
                with engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT COLUMN_TYPE 
                        FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_SCHEMA = DATABASE() 
                        AND TABLE_NAME = 'users' 
                        AND COLUMN_NAME = 'id'
                    """))
                    row = result.fetchone()
                    users_id_type = row[0] if row else id_type
                    
                    conn.execute(text(f"""
                        CREATE TABLE ark_server_files (
                            id {users_id_type} NOT NULL AUTO_INCREMENT,
                            version VARCHAR(50) NOT NULL,
                            install_path VARCHAR(500) NOT NULL,
                            is_active BOOLEAN NOT NULL DEFAULT TRUE,
                            installed_by_id {users_id_type} NULL,
                            installed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            notes TEXT NULL,
                            PRIMARY KEY (id),
                            INDEX ix_ark_server_files_is_active (is_active),
                            INDEX ix_ark_server_files_installed_at (installed_at),
                            CONSTRAINT fk_ark_server_files_installed_by_id
                                FOREIGN KEY (installed_by_id) REFERENCES users(id) ON DELETE SET NULL
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """))
                    conn.commit()
                print("✓ ark_server_files tábla létrehozva")
            except Exception as e:
                print(f"  Figyelmeztetés: ark_server_files tábla: {e}")
        
        # Server instances tábla bővítése (cluster_id, max_players, active_mods, passive_mods, query_port, server_path)
        if 'server_instances' in inspector.get_table_names():
            existing_columns = [col['name'] for col in inspector.get_columns('server_instances')]
            
            # cluster_id oszlop hozzáadása
            if 'cluster_id' not in existing_columns:
                print("cluster_id oszlop hozzáadása a server_instances táblához...")
                try:
                    with engine.connect() as conn:
                        # Először ellenőrizzük, hogy létezik-e a clusters tábla
                        if 'clusters' in inspector.get_table_names():
                            clusters_id_type = id_type
                            result = conn.execute(text("""
                                SELECT COLUMN_TYPE 
                                FROM INFORMATION_SCHEMA.COLUMNS 
                                WHERE TABLE_SCHEMA = DATABASE() 
                                AND TABLE_NAME = 'clusters' 
                                AND COLUMN_NAME = 'id'
                            """))
                            row = result.fetchone()
                            if row:
                                clusters_id_type = row[0]
                            
                            conn.execute(text(f"""
                                ALTER TABLE server_instances 
                                ADD COLUMN cluster_id {clusters_id_type} NULL,
                                ADD INDEX ix_server_instances_cluster_id (cluster_id)
                            """))
                            conn.commit()
                            
                            # Foreign key hozzáadása
                            try:
                                conn.execute(text("""
                                    ALTER TABLE server_instances 
                                    ADD CONSTRAINT fk_server_instances_cluster_id
                                    FOREIGN KEY (cluster_id) REFERENCES clusters(id) ON DELETE SET NULL
                                """))
                                conn.commit()
                            except Exception as e:
                                if "Duplicate foreign key" not in str(e) and "already exists" not in str(e).lower():
                                    print(f"    Figyelmeztetés: cluster_id foreign key: {e}")
                            
                            print("✓ cluster_id oszlop hozzáadva")
                except Exception as e:
                    print(f"  Figyelmeztetés: cluster_id oszlop: {e}")
            
            # Egyéb új oszlopok hozzáadása
            new_columns = {
                'max_players': 'INT NOT NULL DEFAULT 40',
                'query_port': 'INT NULL',
                'active_mods': 'JSON NULL',
                'passive_mods': 'JSON NULL',
                'server_path': 'VARCHAR(500) NULL'
            }
            
            for col_name, col_def in new_columns.items():
                if col_name not in existing_columns:
                    print(f"{col_name} oszlop hozzáadása a server_instances táblához...")
                    try:
                        with engine.connect() as conn:
                            conn.execute(text(f"""
                                ALTER TABLE server_instances 
                                ADD COLUMN {col_name} {col_def}
                            """))
                            conn.commit()
                        print(f"✓ {col_name} oszlop hozzáadva")
                    except Exception as e:
                        print(f"  Figyelmeztetés: {col_name} oszlop: {e}")
        
    except Exception as e:
        print(f"✗ Hiba a táblák létrehozásakor: {e}")
        raise

def create_default_admin():
    """Alapértelmezett Manager Admin létrehozása"""
    db = SessionLocal()
    try:
        # Ellenőrzés: van-e már Manager Admin
        existing = db.query(User).filter(User.role == UserRole.MANAGER_ADMIN).first()
        if existing:
            print("✓ Manager Admin már létezik")
            return
        
        # Alapértelmezett admin létrehozása
        admin = User(
            username="admin",
            email="admin@example.com",
            password_hash=get_password_hash("admin123"),
            role=UserRole.MANAGER_ADMIN,
            email_verified=True
        )
        
        db.add(admin)
        db.commit()
        print("✓ Alapértelmezett Manager Admin létrehozva")
        print("  Email: admin@example.com")
        print("  Jelszó: admin123")
        print("  ⚠️  FONTOS: Változtasd meg az első bejelentkezés után!")
    except Exception as e:
        print(f"✗ Hiba: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("ZedinArkManager - Adatbázis inicializálás\n")
    init_db()
    create_default_admin()
    print("\n✓ Kész!")

