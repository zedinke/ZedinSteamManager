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
    ChatRoom, ChatMessage
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
                    else:
                        # Próbáljuk meg közvetlenül lekérdezni az adatbázisból
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
            return "INT(11) UNSIGNED"  # Alapértelmezés
        
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
                    
                    # Foreign key-ek hozzáadása külön
                    try:
                        conn.execute(text("""
                            ALTER TABLE tickets
                            ADD CONSTRAINT fk_tickets_user_id
                            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                        """))
                        conn.commit()
                    except Exception as e:
                        if "Duplicate foreign key" not in str(e) and "already exists" not in str(e).lower():
                            print(f"    Figyelmeztetés: user_id foreign key: {e}")
                    
                    try:
                        conn.execute(text("""
                            ALTER TABLE tickets
                            ADD CONSTRAINT fk_tickets_closed_by_id
                            FOREIGN KEY (closed_by_id) REFERENCES users(id) ON DELETE SET NULL
                        """))
                        conn.commit()
                    except Exception as e:
                        if "Duplicate foreign key" not in str(e) and "already exists" not in str(e).lower():
                            print(f"    Figyelmeztetés: closed_by_id foreign key: {e}")
                print("✓ tickets tábla létrehozva")
            except Exception as e:
                print(f"  Figyelmeztetés: tickets tábla: {e}")
        
        # Ticket messages tábla
        if 'ticket_messages' not in existing_tables:
            print("ticket_messages tábla létrehozása...")
            try:
                with engine.connect() as conn:
                    conn.execute(text("""
                        CREATE TABLE ticket_messages (
                            id INTEGER NOT NULL AUTO_INCREMENT,
                            ticket_id INTEGER NOT NULL,
                            user_id INTEGER NOT NULL,
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
        
        # Ticket ratings tábla
        if 'ticket_ratings' not in existing_tables:
            print("ticket_ratings tábla létrehozása...")
            try:
                with engine.connect() as conn:
                    conn.execute(text(f"""
                        CREATE TABLE ticket_ratings (
                            id {id_type} NOT NULL AUTO_INCREMENT,
                            ticket_id {id_type} NOT NULL,
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
        
        # Chat rooms tábla
        if 'chat_rooms' not in existing_tables:
            print("chat_rooms tábla létrehozása...")
            try:
                with engine.connect() as conn:
                    conn.execute(text("""
                        CREATE TABLE chat_rooms (
                            id INTEGER NOT NULL AUTO_INCREMENT,
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
        
        # Chat messages tábla
        if 'chat_messages' not in existing_tables:
            print("chat_messages tábla létrehozása...")
            try:
                with engine.connect() as conn:
                    conn.execute(text(f"""
                        CREATE TABLE chat_messages (
                            id {id_type} NOT NULL AUTO_INCREMENT,
                            room_id {id_type} NOT NULL,
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

