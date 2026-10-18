from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field, create_engine, Session, select
from config import DATABASE_URL, DEFAULT_WORKSPACE

engine = create_engine(DATABASE_URL, echo=False)

class MessageRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    msg_id: Optional[str] = Field(default=None, index=True)
    sender_jid: str
    role: str # "user" | "assistant" | "system"
    content_type: str # "text" | "voice" | "pdf"
    content: str
    audio_path: Optional[str] = None
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
