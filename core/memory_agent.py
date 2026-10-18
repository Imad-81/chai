import re
import json
import asyncio
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from pathlib import Path
import ollama

from config import (
    MEMORY_RESOLVER_MODEL, 
    MEMORY_AUTO_SUMMARIZE, 
    OLLAMA_HOST
)
from core.db import get_session, MessageRecord, SessionRecord
from core.memory import MemoryManager
from core.logger import get_logger

logger = get_logger("memory_agent")

@dataclass
class ResolvedContext:
    is_follow_up: bool
    topic_changed: bool
    resolved_prompt: str
    context_summary: str
    session_id: str

class MemoryAgent:
    """
    Dedicated local LLM agent (powered by Qwen 2.5 0.5B) for:
    1. Pronoun and conversational context resolution in real time (< 150ms).
    2. Intent and topic boundary detection.
    3. Asynchronous episodic session summarization and durable fact extraction.
    """

    PRONOUN_CUES = re.compile(
        r"\b(?:it|that|this|the\s+error|the\s+bug|the\s+issue|why|again|retry|"
        r"not\s+working|same\s+thing|fix\s+it|run\s+it|check\s+it|do\s+it|"
        r"what\s+about|instead|what\s+did\s+you\s+do|explain\s+that)\b",
        re.IGNORECASE
    )

    @classmethod
    async def resolve_context(
        cls, 
        user_prompt: str, 
        sender_jid: str, 
        workspace_path: str
    ) -> ResolvedContext:
        """
        Resolves ambiguous pronouns, follow-ups, and context references
        against the active session's working memory turns using the fast resolver model.
        """
        # Ensure active session exists
        active_session = MemoryManager.get_or_create_active_session(sender_jid, workspace_path)
        session_id = active_session.session_id

        # Fetch prior turns from the active session (excluding any message matching current prompt)
        history = MemoryManager.get_active_session_history(sender_jid, limit=6)
        # Filter out current prompt if already inserted into history
        prior_turns = [
            t for t in history 
            if not (t.get("role") == "user" and t.get("content", "").strip() == user_prompt.strip())
        ]

        # If there are no prior turns in this active session, it's a fresh prompt
        if not prior_turns:
            return ResolvedContext(
                is_follow_up=False,
                topic_changed=False,
                resolved_prompt=user_prompt,
                context_summary="",
                session_id=session_id
            )

        # Skip LLM call for direct slash commands or status checks
        clean = user_prompt.strip()
        if clean.startswith("/") or clean.startswith("!"):
            return ResolvedContext(
                is_follow_up=False,
                topic_changed=False,
                resolved_prompt=user_prompt,
                context_summary="",
                session_id=session_id
            )

        # Check if the prompt looks like a follow-up or contains pronouns
        words = clean.split()
        looks_like_followup = (
            len(words) <= 6 or
            bool(cls.PRONOUN_CUES.search(clean))
        )

        if not looks_like_followup:
            return ResolvedContext(
                is_follow_up=False,
                topic_changed=False,
                resolved_prompt=user_prompt,
                context_summary="",
                session_id=session_id
            )

        # Build concise conversation snippet for resolver model
        snippet_lines = []
        for t in prior_turns[-4:]:
            role_name = "User" if t["role"] == "user" else "Assistant"
            content = t["content"].replace("\n", " ")[:140]
            snippet_lines.append(f"{role_name}: {content}")
        turns_text = "\n".join(snippet_lines)

        ws_name = Path(workspace_path).name

        prompt = (
            f"You are a context and pronoun resolver for a developer assistant.\n"
            f"Active Project: {ws_name}\n\n"
            f"Recent Conversation:\n"
            f"{turns_text}\n\n"
            f"New User Input: \"{clean}\"\n\n"
            f"Determine if the user's input is a follow-up or refers to previous items (e.g. 'it', 'fix that', 'why?').\n"
            f"If it is a follow-up, rewrite it into a complete, standalone instruction specifying what to do.\n"
            f"If it is a new topic or already clear, return the exact input.\n\n"
            f"Respond ONLY with a JSON object:\n"
            f'{{"is_follow_up": true, "resolved_prompt": "clear rewritten instruction"}}'
        )

        try:
            # Call fast resolver model with strict 2.5s timeout
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    ollama.chat,
                    model=MEMORY_RESOLVER_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.1, "num_predict": 128}
                ),
                timeout=2.5
            )
            raw = (response.get("message", {}).get("content") or "").strip()
            
            # Extract JSON from model output
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                is_follow_up = bool(data.get("is_follow_up", False))
                resolved = data.get("resolved_prompt", clean).strip()
                if resolved and is_follow_up and resolved != clean:
                    logger.info(f"ContextResolver: '{clean}' -> '{resolved}'")
                    return ResolvedContext(
                        is_follow_up=True,
                        topic_changed=False,
                        resolved_prompt=resolved,
                        context_summary=f"Resolved from context: {clean}",
                        session_id=session_id
                    )
        except Exception as e:
            logger.debug(f"Fast resolver fallback due to: {e}")

        # Fallback heuristic: If prompt is very short and has pronouns, attach last turn
        if len(words) <= 4 and cls.PRONOUN_CUES.search(clean):
            last_turn = prior_turns[-1]["content"].replace("\n", " ")[:100]
            resolved = f"Context: Previous turn was \"{last_turn}\". User instruction: \"{clean}\""
            return ResolvedContext(
                is_follow_up=True,
                topic_changed=False,
                resolved_prompt=resolved,
                context_summary="",
                session_id=session_id
            )

        return ResolvedContext(
            is_follow_up=False,
            topic_changed=False,
            resolved_prompt=user_prompt,
            context_summary="",
            session_id=session_id
        )

    @classmethod
    def schedule_session_summary(cls, session_id: str):
        """Schedules asynchronous episodic summarization in the background."""
        if not MEMORY_AUTO_SUMMARIZE:
            return

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(cls.summarize_session_async(session_id))
        except RuntimeError:
            # If no running loop in current thread, spawn background thread
            asyncio.run(cls.summarize_session_async(session_id))

    @classmethod
    async def summarize_session_async(cls, session_id: str):
        """
        Background worker: Reads all messages for a sealed session,
        extracts a 2-sentence summary and any durable technical facts,
        and saves them into SessionRecord and LongTermFact.
        """
        with get_session() as session:
            stmt = select(MessageRecord).where(
                MessageRecord.session_id == session_id
            ).order_by(MessageRecord.id)
            records = session.exec(stmt).all()

        if len(records) < 2:
            return

        turns_text = "\n".join(
            f"{'User' if r.role == 'user' else 'Assistant'}: {r.content[:150]}"
            for r in records[:12]
        )

        prompt = (
            f"You are an episodic memory summarizer for a personal developer assistant.\n"
            f"Summarize the completed conversation below:\n\n"
            f"{turns_text}\n\n"
            f"Extract:\n"
            f"1. A short title (max 5 words)\n"
            f"2. A concise 1-2 sentence summary of what was worked on or decided\n"
            f"3. Any permanent technical facts or user preferences discovered (e.g. 'Vite port is 5173')\n\n"
            f"Respond ONLY in valid JSON:\n"
            f'{{\n'
            f'  "title": "Short Title",\n'
            f'  "summary": "1-2 sentence summary of session.",\n'
            f'  "key_facts": ["fact 1", "fact 2"]\n'
            f'}}'
        )

        try:
            res = await asyncio.to_thread(
                ollama.chat,
                model=MEMORY_RESOLVER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.2, "num_predict": 256}
            )
            raw = (res.get("message", {}).get("content") or "").strip()
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                title = data.get("title", "Conversation Session").strip()
                summary = data.get("summary", "").strip()
                key_facts = data.get("key_facts", [])

                if summary:
                    MemoryManager.update_session_summary(
                        session_id=session_id,
                        title=title,
                        summary=summary,
                        key_facts=json.dumps(key_facts) if key_facts else None
                    )
                    logger.info(f"Episodic memory saved for session {session_id}: '{title}' - {summary}")

                # Save durable facts to LongTermFact table
                if isinstance(key_facts, list):
                    for fact_str in key_facts:
                        if isinstance(fact_str, str) and len(fact_str.strip()) > 5:
                            MemoryManager.save_fact(
                                fact=fact_str.strip(),
                                category="session_derived",
                                source_session_id=session_id
                            )
        except Exception as e:
            logger.warning(f"Error during async session summarization for {session_id}: {e}")
