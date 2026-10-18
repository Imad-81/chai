from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field, create_engine, Session, select
from config import DATABASE_URL, DEFAULT_WORKSPACE

from sqlalchemy import event
from sqlalchemy.engine import Engine

engine = create_engine(
    DATABASE_URL, 
    echo=False, 
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if "sqlite" in DATABASE_URL:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

class MessageRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    msg_id: Optional[str] = Field(default=None, index=True)
    session_id: Optional[str] = Field(default=None, index=True)
    workspace: Optional[str] = Field(default=None, index=True)
    sender_jid: str
    role: str # "user" | "assistant" | "system"
    content_type: str # "text" | "voice" | "pdf"
    content: str
    audio_path: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SessionRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(unique=True, index=True)
    sender_jid: str = Field(index=True)
    workspace: str = Field(index=True)
    title: Optional[str] = None
    summary: Optional[str] = None
    key_facts: Optional[str] = None # JSON string of extracted facts
    turn_count: int = Field(default=0)
    is_active: bool = Field(default=True, index=True)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None

class LongTermFact(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    category: str = Field(default="general", index=True) # preference | architecture | project_note | general
    workspace: Optional[str] = Field(default=None, index=True)
    fact: str
    source_session_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class WorkspaceState(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)
    value: str

class AssignmentRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    prompt: str
    markdown_content: str
    pdf_path: str
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

def init_db():
    # Safe SQLite schema migration for existing databases
    if "sqlite" in DATABASE_URL:
        with engine.connect() as conn:
            # Check existing columns in messagerecord if table exists
            table_check = conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='messagerecord'"
            ).fetchone()
            if table_check:
                cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(messagerecord)").fetchall()]
                if "session_id" not in cols:
                    conn.exec_driver_sql("ALTER TABLE messagerecord ADD COLUMN session_id TEXT")
                if "workspace" not in cols:
                    conn.exec_driver_sql("ALTER TABLE messagerecord ADD COLUMN workspace TEXT")
            conn.commit()

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        # Ensure default workspace key exists
        stmt = select(WorkspaceState).where(WorkspaceState.key == "active_workspace")
        state = session.exec(stmt).first()
        if not state:
            session.add(WorkspaceState(key="active_workspace", value=DEFAULT_WORKSPACE))
            session.commit()

def get_session():
    return Session(engine)
