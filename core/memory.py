import os
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from uuid import uuid4
from sqlmodel import select, desc
from core.db import (
    get_session, 
    MessageRecord, 
    WorkspaceState, 
    AssignmentRecord, 
    SessionRecord, 
    LongTermFact
)
from config import DEFAULT_WORKSPACE, MEMORY_SESSION_TIMEOUT_MINUTES
from core.logger import get_logger

logger = get_logger("memory")

class MemoryManager:
    _cached_workspace: Optional[str] = None

    @classmethod
    def get_or_create_active_session(cls, sender_jid: str, workspace: Optional[str] = None) -> SessionRecord:
        """
        Retrieves the current active session for the user, or creates a new one
        if:
        1. No active session exists.
        2. The last interaction occurred more than MEMORY_SESSION_TIMEOUT_MINUTES ago.
        3. The active workspace was switched.
        """
        current_ws = workspace or cls.get_active_workspace()
        now = datetime.now(timezone.utc)

        with get_session() as session:
            stmt = select(SessionRecord).where(
                SessionRecord.sender_jid == sender_jid,
                SessionRecord.is_active == True
            ).order_by(desc(SessionRecord.id)).limit(1)
            active_rec = session.exec(stmt).first()

            if active_rec:
                # Ensure last_activity_at is timezone-aware
                last_act = active_rec.last_activity_at
                if last_act.tzinfo is None:
                    last_act = last_act.replace(tzinfo=timezone.utc)

                elapsed_minutes = (now - last_act).total_seconds() / 60.0

                # Check timeout or workspace change
                if elapsed_minutes > MEMORY_SESSION_TIMEOUT_MINUTES or (workspace and active_rec.workspace != current_ws):
                    logger.info(
                        f"Sealing previous session {active_rec.session_id} "
                        f"(idle: {elapsed_minutes:.1f}m > {MEMORY_SESSION_TIMEOUT_MINUTES}m or ws change: {active_rec.workspace} -> {current_ws})"
                    )
                    cls.reset_session_agy_state(sender_jid)
                    active_rec.is_active = False
                    active_rec.ended_at = now
                    session.add(active_rec)
                    session.commit()
                    
                    # Schedule summarization if needed
                    cls._on_session_sealed(active_rec.session_id, active_rec.turn_count)
                    active_rec = None

            if not active_rec:
                new_sid = uuid4().hex[:12]
                active_rec = SessionRecord(
                    session_id=new_sid,
                    sender_jid=sender_jid,
                    workspace=current_ws,
                    is_active=True,
                    turn_count=0,
                    started_at=now,
                    last_activity_at=now
                )
                session.add(active_rec)
                session.commit()
                session.refresh(active_rec)
                logger.info(f"Created new active conversation session {new_sid} for @{sender_jid} in '{current_ws}'")

            return active_rec

    @classmethod
    def get_active_session(cls, sender_jid: str) -> Optional[SessionRecord]:
        """Returns the currently active session for the sender if one exists."""
        with get_session() as session:
            stmt = select(SessionRecord).where(
                SessionRecord.sender_jid == sender_jid,
                SessionRecord.is_active == True
            ).order_by(desc(SessionRecord.id)).limit(1)
            return session.exec(stmt).first()

    @classmethod
    def seal_active_session(cls, sender_jid: str, summarize: bool = True) -> Optional[SessionRecord]:
        """Explicitly seals the active session (e.g. via /new or /reset command)."""
        now = datetime.now(timezone.utc)
        with get_session() as session:
            stmt = select(SessionRecord).where(
                SessionRecord.sender_jid == sender_jid,
                SessionRecord.is_active == True
            ).order_by(desc(SessionRecord.id)).limit(1)
            active_rec = session.exec(stmt).first()
            if active_rec:
                cls.reset_session_agy_state(sender_jid)
                active_rec.is_active = False
                active_rec.ended_at = now
                session.add(active_rec)
                session.commit()
                session.refresh(active_rec)
                logger.info(f"Explicitly sealed active session {active_rec.session_id}")
                if summarize and active_rec.turn_count >= 2:
                    cls._on_session_sealed(active_rec.session_id, active_rec.turn_count)
                return active_rec
            return None

    @classmethod
    def get_session_agy_state(cls, sender_jid: str, workspace: str) -> bool:
        """Checks if the current active session has an ongoing Antigravity conversation in the workspace."""
        active_sess = cls.get_active_session(sender_jid)
        if not active_sess:
            return False
        with get_session() as session:
            stmt = select(WorkspaceState).where(WorkspaceState.key == f"agy_session_{sender_jid}")
            state = session.exec(stmt).first()
            if state and state.value == f"{active_sess.session_id}:{workspace}":
                return True
        return False

    @classmethod
    def mark_session_agy_used(cls, sender_jid: str, workspace: str):
        """Marks that Antigravity has executed for this active session in this workspace."""
        active_sess = cls.get_or_create_active_session(sender_jid)
        with get_session() as session:
            stmt = select(WorkspaceState).where(WorkspaceState.key == f"agy_session_{sender_jid}")
            state = session.exec(stmt).first()
            val = f"{active_sess.session_id}:{workspace}"
            if state:
                state.value = val
            else:
                state = WorkspaceState(key=f"agy_session_{sender_jid}", value=val)
                session.add(state)
            session.commit()

    @classmethod
    def reset_session_agy_state(cls, sender_jid: str):
        """Clears the Antigravity conversation continuation state."""
        try:
            from core.agy_runner import AntigravityRunner
            AntigravityRunner.reset_session()
        except Exception:
            pass
        with get_session() as session:
            stmt = select(WorkspaceState).where(WorkspaceState.key == f"agy_session_{sender_jid}")
            state = session.exec(stmt).first()
            if state:
                session.delete(state)
                session.commit()

    @classmethod
    def _on_session_sealed(cls, session_id: str, turn_count: int):
        """Dispatches async summarization worker if turns exist."""
        try:
            from core.memory_agent import MemoryAgent
            MemoryAgent.schedule_session_summary(session_id)
        except Exception as e:
            logger.warning(f"Could not schedule session summary for {session_id}: {e}")

    @classmethod
    def save_message(
        cls, 
        sender_jid: str, 
        role: str, 
        content: str, 
        content_type: str = "text", 
        audio_path: Optional[str] = None,
        session_id: Optional[str] = None,
        workspace: Optional[str] = None
    ) -> MessageRecord:
        now = datetime.now(timezone.utc)
        active_ws = workspace or cls.get_active_workspace()
        
        # If session_id not explicitly provided, get or create active session
        if not session_id:
            active_session = cls.get_or_create_active_session(sender_jid, active_ws)
            sid = active_session.session_id
        else:
            sid = session_id

        with get_session() as session:
            record = MessageRecord(
                sender_jid=sender_jid,
                session_id=sid,
                workspace=active_ws,
                role=role,
                content=content,
                content_type=content_type,
                audio_path=audio_path,
                created_at=now
            )
            session.add(record)
            
            # Update session last activity & turn count
            stmt = select(SessionRecord).where(SessionRecord.session_id == sid)
            s_rec = session.exec(stmt).first()
            if s_rec:
                s_rec.last_activity_at = now
                s_rec.turn_count += 1
                session.add(s_rec)

            session.commit()
            session.refresh(record)
            return record

    @classmethod
    def get_active_session_history(
        cls, 
        sender_jid: str, 
        limit: int = 10,
        exclude_last_if_current: bool = False
    ) -> List[dict]:
        """
        Retrieves conversation history scoped strictly to the current active session.
        Prevents old sessions/topics from polluting the working context.
        """
        active_sess = cls.get_or_create_active_session(sender_jid)
        with get_session() as session:
            stmt = select(MessageRecord).where(
                MessageRecord.session_id == active_sess.session_id
            ).order_by(desc(MessageRecord.id)).limit(limit)
            records = session.exec(stmt).all()
            
            turns = [
                {"role": r.role, "content": r.content, "id": r.id}
                for r in reversed(records)
            ]
            if exclude_last_if_current and turns and turns[-1]["role"] == "user":
                turns = turns[:-1]
            return [{"role": t["role"], "content": t["content"]} for t in turns]

    @classmethod
    def get_recent_history(cls, limit: int = 8, sender_jid: Optional[str] = None) -> List[dict]:
        """
        Returns recent history. If sender_jid is provided, prioritizes
        the active session turns to keep context tightly focused.
        """
        if sender_jid:
            active_hist = cls.get_active_session_history(sender_jid, limit=limit)
            if active_hist:
                return active_hist

        with get_session() as session:
            stmt = select(MessageRecord).order_by(desc(MessageRecord.id)).limit(limit)
            records = session.exec(stmt).all()
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

    # Fact and Long-Term Memory Storage
    @staticmethod
    def save_fact(
        fact: str, 
        category: str = "general", 
        workspace: Optional[str] = None, 
        source_session_id: Optional[str] = None
    ) -> LongTermFact:
        with get_session() as session:
            record = LongTermFact(
                category=category,
                workspace=workspace,
                fact=fact.strip(),
                source_session_id=source_session_id,
                created_at=datetime.now(timezone.utc)
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            logger.info(f"Saved durable fact: '{fact[:60]}' [cat={category}, ws={workspace}]")
            return record

    @staticmethod
    def delete_fact(fact_id_or_keyword: str) -> int:
        with get_session() as session:
            if fact_id_or_keyword.isdigit():
                stmt = select(LongTermFact).where(LongTermFact.id == int(fact_id_or_keyword))
                records = session.exec(stmt).all()
            else:
                stmt = select(LongTermFact).where(LongTermFact.fact.contains(fact_id_or_keyword))
                records = session.exec(stmt).all()
            deleted_count = len(records)
            for r in records:
                session.delete(r)
            session.commit()
            return deleted_count

    @staticmethod
    def get_all_facts(workspace: Optional[str] = None, limit: int = 20) -> List[LongTermFact]:
        with get_session() as session:
            stmt = select(LongTermFact)
            if workspace:
                stmt = stmt.where((LongTermFact.workspace == workspace) | (LongTermFact.workspace == None))
            stmt = stmt.order_by(desc(LongTermFact.id)).limit(limit)
            return session.exec(stmt).all()

    @staticmethod
    def get_relevant_facts(query: str = "", workspace: Optional[str] = None, limit: int = 5) -> List[str]:
        facts = MemoryManager.get_all_facts(workspace=workspace, limit=limit)
        return [f.fact for f in facts]

    @staticmethod
    def get_recent_session_summaries(workspace: Optional[str] = None, limit: int = 3) -> List[dict]:
        with get_session() as session:
            stmt = select(SessionRecord).where(
                SessionRecord.is_active == False,
                SessionRecord.summary != None
            )
            if workspace:
                stmt = stmt.where(SessionRecord.workspace == workspace)
            stmt = stmt.order_by(desc(SessionRecord.ended_at)).limit(limit)
            records = session.exec(stmt).all()
            return [
                {
                    "session_id": r.session_id,
                    "title": r.title or "Untitled Session",
                    "summary": r.summary,
                    "workspace": r.workspace,
                    "ended_at": r.ended_at.strftime("%Y-%m-%d %H:%M") if r.ended_at else ""
                }
                for r in records
            ]

    @staticmethod
    def update_session_summary(session_id: str, title: str, summary: str, key_facts: Optional[str] = None):
        with get_session() as session:
            stmt = select(SessionRecord).where(SessionRecord.session_id == session_id)
            rec = session.exec(stmt).first()
            if rec:
                rec.title = title
                rec.summary = summary
                if key_facts:
                    rec.key_facts = key_facts
                session.add(rec)
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

    @classmethod
    def list_all_sessions(cls, limit: int = 100) -> List[Dict[str, Any]]:
        """Lists all conversation sessions ordered by last activity for the Web UI."""
        with get_session() as session:
            stmt = select(SessionRecord).order_by(desc(SessionRecord.last_activity_at)).limit(limit)
            records = session.exec(stmt).all()
            return [
                {
                    "session_id": r.session_id,
                    "title": r.title or "New Chat",
                    "workspace": r.workspace,
                    "turn_count": r.turn_count,
                    "is_active": r.is_active,
                    "agy_conversation_id": r.agy_conversation_id,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "last_activity_at": r.last_activity_at.isoformat() if r.last_activity_at else None,
                }
                for r in records
            ]

    @classmethod
    def get_session_by_id(cls, session_id: str) -> Optional[SessionRecord]:
        """Fetches a session record by its unique session_id."""
        with get_session() as session:
            stmt = select(SessionRecord).where(SessionRecord.session_id == session_id)
            return session.exec(stmt).first()

    @classmethod
    def create_chat_session(
        cls, 
        title: Optional[str] = None, 
        workspace: Optional[str] = None, 
        sender_jid: str = "web_user"
    ) -> SessionRecord:
        """Explicitly creates a new chat session for the Web UI."""
        now = datetime.now(timezone.utc)
        target_ws = workspace or cls.get_active_workspace()
        new_sid = uuid4().hex[:12]
        rec = SessionRecord(
            session_id=new_sid,
            sender_jid=sender_jid,
            workspace=target_ws,
            title=title or "New Chat",
            is_active=True,
            turn_count=0,
            started_at=now,
            last_activity_at=now
        )
        with get_session() as session:
            session.add(rec)
            session.commit()
            session.refresh(rec)
        logger.info(f"Created Web chat session {new_sid} in '{target_ws}'")
        return rec

    @classmethod
    def update_chat_session(
        cls, 
        session_id: str, 
        title: Optional[str] = None, 
        workspace: Optional[str] = None,
        agy_conversation_id: Optional[str] = None
    ) -> Optional[SessionRecord]:
        """Updates chat session properties."""
        with get_session() as session:
            stmt = select(SessionRecord).where(SessionRecord.session_id == session_id)
            rec = session.exec(stmt).first()
            if not rec:
                return None
            if title is not None:
                rec.title = title
            if workspace is not None:
                rec.workspace = workspace
            if agy_conversation_id is not None:
                rec.agy_conversation_id = agy_conversation_id
            session.add(rec)
            session.commit()
            session.refresh(rec)
            return rec

    @classmethod
    def set_session_agy_id(cls, session_id: str, agy_id: str):
        """Sets the Antigravity conversation UUID for a session."""
        cls.update_chat_session(session_id, agy_conversation_id=agy_id)

    @classmethod
    def delete_chat_session(cls, session_id: str) -> bool:
        """Deletes a chat session and all its messages."""
        with get_session() as session:
            stmt = select(SessionRecord).where(SessionRecord.session_id == session_id)
            rec = session.exec(stmt).first()
            if not rec:
                return False
            # Delete associated messages
            msg_stmt = select(MessageRecord).where(MessageRecord.session_id == session_id)
            messages = session.exec(msg_stmt).all()
            for m in messages:
                session.delete(m)
            session.delete(rec)
            session.commit()
            logger.info(f"Deleted chat session {session_id} and {len(messages)} messages")
            return True

    @classmethod
    def get_messages_for_session(cls, session_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        """Returns message history for a specific chat session in chronological order."""
        with get_session() as session:
            stmt = select(MessageRecord).where(
                MessageRecord.session_id == session_id
            ).order_by(MessageRecord.id.asc()).limit(limit)
            records = session.exec(stmt).all()
            return [
                {
                    "id": r.id,
                    "session_id": r.session_id,
                    "role": r.role,
                    "content": r.content,
                    "content_type": r.content_type,
                    "audio_path": r.audio_path,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in records
            ]
