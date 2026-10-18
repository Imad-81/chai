from typing import List, Optional
from sqlmodel import select, desc
from core.db import get_session, MessageRecord, WorkspaceState, AssignmentRecord
from config import DEFAULT_WORKSPACE

class MemoryManager:
    _cached_workspace: Optional[str] = None

    @staticmethod
    def save_message(sender_jid: str, role: str, content: str, content_type: str = "text", audio_path: Optional[str] = None):
        with get_session() as session:
            record = MessageRecord(
                sender_jid=sender_jid,
                role=role,
                content=content,
                content_type=content_type,
                audio_path=audio_path
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    @staticmethod
    def get_recent_history(limit: int = 8) -> List[dict]:
        with get_session() as session:
            stmt = select(MessageRecord).order_by(desc(MessageRecord.id)).limit(limit)
            records = session.exec(stmt).all()
            # Return in chronological order
            return [
                {"role": r.role, "content": r.content}
                for r in reversed(records)
            ]

    @classmethod
    def get_active_workspace(cls) -> str:
        if cls._cached_workspace:
            return cls._cached_workspace
        with get_session() as session:
            stmt = select(WorkspaceState).where(WorkspaceState.key == "active_workspace")
            state = session.exec(stmt).first()
            if state:
                cls._cached_workspace = state.value
                return state.value
            cls._cached_workspace = DEFAULT_WORKSPACE
            return DEFAULT_WORKSPACE

    @classmethod
    def set_active_workspace(cls, path: str):
        cls._cached_workspace = path
        with get_session() as session:
            stmt = select(WorkspaceState).where(WorkspaceState.key == "active_workspace")
            state = session.exec(stmt).first()
            if state:
                state.value = path
            else:
                state = WorkspaceState(key="active_workspace", value=path)
                session.add(state)
            session.commit()

    @staticmethod
    def save_assignment(title: str, prompt: str, markdown_content: str, pdf_path: str, version: int = 1) -> AssignmentRecord:
        with get_session() as session:
            record = AssignmentRecord(
                title=title,
                prompt=prompt,
                markdown_content=markdown_content,
                pdf_path=pdf_path,
                version=version
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    @staticmethod
    def get_latest_assignment() -> Optional[AssignmentRecord]:
        with get_session() as session:
            stmt = select(AssignmentRecord).order_by(desc(AssignmentRecord.id)).limit(1)
            return session.exec(stmt).first()
