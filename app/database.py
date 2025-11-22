"""
Adatbázis kapcsolat és modell
"""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Enum, Text, ForeignKey, JSON, TypeDecorator
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum

from app.config import settings

# Database URL
DATABASE_URL = f"mysql+pymysql://{settings.db_user}:{settings.db_pass}@{settings.db_host}/{settings.db_name}?charset=utf8mb4"

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Enum TypeDecorator - kezeli a string -> enum konverziót
class EnumType(TypeDecorator):
    impl = String(20)
    cache_ok = True
    
    def __init__(self, enum_class, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enum_class = enum_class
    
    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, self.enum_class):
            return value.value
        return value
    
    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, self.enum_class):
            return value
        # String értékből enum-ot csinál
        try:
            return self.enum_class(value)
        except ValueError:
            # Ha nincs egyezés, próbáljuk meg a nagybetűs verziót
            for enum_item in self.enum_class:
                if enum_item.value.lower() == value.lower():
                    return enum_item
            raise

# Enums
class UserRole(str, enum.Enum):
    MANAGER_ADMIN = "manager_admin"
    SERVER_ADMIN = "server_admin"
    ADMIN = "admin"
    USER = "user"

class TokenType(str, enum.Enum):
    SERVER_ADMIN = "server_admin"
    USER = "user"

class ServerStatus(str, enum.Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    RESTARTING = "restarting"

# Models
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(EnumType(UserRole), default=UserRole.USER, nullable=False, index=True)
    email_verified = Column(Boolean, default=False, nullable=False)
    email_verification_token = Column(String(100), nullable=True)
    email_verification_expires = Column(DateTime, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    created_by = relationship("User", remote_side=[id], backref="created_users")
    tokens = relationship("Token", foreign_keys="Token.user_id", back_populates="user")
    generated_tokens = relationship("Token", foreign_keys="Token.generated_by_id", back_populates="generated_by")
    notifications = relationship("Notification", back_populates="user")
    servers = relationship("Server", back_populates="server_admin")
    admin_servers = relationship("AdminServer", back_populates="admin")
    tickets = relationship("Ticket", foreign_keys="Ticket.user_id", back_populates="user")
    ticket_messages = relationship("TicketMessage", back_populates="user")
    ticket_ratings = relationship("TicketRating", back_populates="user")
    chat_messages = relationship("ChatMessage", back_populates="user")

class Token(Base):
    __tablename__ = "tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(100), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    token_type = Column(EnumType(TokenType), nullable=False)
    # Explicit oszlopnév megadása - ha az adatbázisban generated_by van, akkor azt használja
    generated_by_id = Column("generated_by_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)
    activated_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="tokens")
    generated_by = relationship("User", foreign_keys=[generated_by_id], back_populates="generated_tokens")

class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    
    # Relationships
    user = relationship("User", back_populates="notifications")

class ServerAdminAdmin(Base):
    __tablename__ = "server_admin_admins"
    
    id = Column(Integer, primary_key=True, index=True)
    server_admin_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    admin_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    server_admin = relationship("User", foreign_keys=[server_admin_id])
    admin = relationship("User", foreign_keys=[admin_id])

class Server(Base):
    __tablename__ = "servers"
    
    id = Column(Integer, primary_key=True, index=True)
    server_admin_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(EnumType(ServerStatus), default=ServerStatus.STOPPED, nullable=False)
    config = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    server_admin = relationship("User", back_populates="servers")
    admin_servers = relationship("AdminServer", back_populates="server")

class AdminServer(Base):
    __tablename__ = "admin_servers"
    
    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    server_id = Column(Integer, ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    admin = relationship("User", back_populates="admin_servers")
    server = relationship("Server", back_populates="admin_servers")

class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"

class Ticket(Base):
    __tablename__ = "tickets"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(EnumType(TicketStatus), default=TicketStatus.OPEN, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False, index=True)
    closed_at = Column(DateTime, nullable=True)
    closed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="tickets")
    closed_by = relationship("User", foreign_keys=[closed_by_id])
    messages = relationship("TicketMessage", back_populates="ticket", order_by="TicketMessage.created_at")
    rating = relationship("TicketRating", back_populates="ticket", uselist=False)

class TicketMessage(Base):
    __tablename__ = "ticket_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    
    # Relationships
    ticket = relationship("Ticket", back_populates="messages")
    user = relationship("User", back_populates="ticket_messages")

class TicketRating(Base):
    __tablename__ = "ticket_ratings"
    
    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rating = Column(Integer, nullable=False)  # 1-5
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    ticket = relationship("Ticket", back_populates="rating")
    user = relationship("User", back_populates="ticket_ratings")

class ChatRoom(Base):
    __tablename__ = "chat_rooms"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    game_name = Column(String(100), nullable=True, index=True)  # Játék neve
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    messages = relationship("ChatMessage", back_populates="room", order_by="ChatMessage.created_at")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    
    # Relationships
    room = relationship("ChatRoom", back_populates="messages")
    user = relationship("User", back_populates="chat_messages")

class Game(Base):
    """Steam játékok, amiket a Manager Admin engedélyez"""
    __tablename__ = "games"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)  # Játék neve
    steam_app_id = Column(String(50), nullable=True, index=True)  # Steam App ID
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    server_instances = relationship("ServerInstance", back_populates="game")

class ServerInstance(Base):
    """Indított szerver példányok"""
    __tablename__ = "server_instances"
    
    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    server_admin_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # Szerver neve
    port = Column(Integer, nullable=True)  # Port szám
    status = Column(EnumType(ServerStatus), default=ServerStatus.STOPPED, nullable=False, index=True)
    config = Column(JSON, nullable=True)  # Szerver konfiguráció
    token_used_id = Column(Integer, ForeignKey("tokens.id", ondelete="SET NULL"), nullable=True, index=True)  # Használt token
    token_expires_at = Column(DateTime, nullable=True, index=True)  # Token lejárat dátuma
    scheduled_deletion_date = Column(DateTime, nullable=True, index=True)  # Ütemezett törlési dátum (30 nap a token lejárata után)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    started_at = Column(DateTime, nullable=True)
    stopped_at = Column(DateTime, nullable=True)
    
    # Relationships
    game = relationship("Game", back_populates="server_instances")
    server_admin = relationship("User", foreign_keys=[server_admin_id])
    token_used = relationship("Token", foreign_keys=[token_used_id])

class TokenExtensionRequest(Base):
    __tablename__ = "token_extension_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    token_id = Column(Integer, ForeignKey("tokens.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_days = Column(Integer, nullable=False)  # Hány napra szeretné meghosszabbítani
    status = Column(String(20), default="pending", nullable=False, index=True)  # pending, approved, rejected
    notes = Column(Text, nullable=True)  # Opcionális megjegyzés
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    processed_at = Column(DateTime, nullable=True)
    processed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Relationships
    token = relationship("Token", foreign_keys=[token_id])
    user = relationship("User", foreign_keys=[user_id])
    processed_by = relationship("User", foreign_keys=[processed_by_id])

# Dependency
def get_db():
    """Database session dependency"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

