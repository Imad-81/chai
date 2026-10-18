import os
import subprocess
import asyncio
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
import ollama

from config import PROJECTS_ROOT, BASE_DIR, DISPATCHER_MODEL, TASK_SYNTHESIZER_MODEL
from core.memory import MemoryManager
from core.repo_inspector import RepoInspector
from core.logger import get_logger

logger = get_logger("context_engine")

class ContextEngine:
    """Provides dynamic developer profile, workspace state, and multi-turn task synthesis."""

    DEVELOPER_NAME = "Imad"
    GITHUB_USERNAME = "Imad-81"
    DEVELOPER_EMAIL = "shaikimaduddin10@gmail.com"

    @classmethod
    def get_active_workspace_summary(cls) -> Dict[str, Any]:
        """Returns details about the currently active repository."""
        active_str = MemoryManager.get_active_workspace()
        active_path = Path(active_str)
        name = active_path.name

        branch = "unknown"
        dirty = False
        last_commit = "none"

        if (active_path / ".git").exists():
            try:
                branch = subprocess.check_output(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=str(active_path), stderr=subprocess.DEVNULL, text=True
                ).strip()
                status = subprocess.check_output(
                    ["git", "status", "--short"],
                    cwd=str(active_path), stderr=subprocess.DEVNULL, text=True
                ).strip()
                dirty = bool(status)
                last_commit = subprocess.check_output(
                    ["git", "log", "-1", "--format=%h: %s (%cr)"],
                    cwd=str(active_path), stderr=subprocess.DEVNULL, text=True
                ).strip()
            except Exception:
                pass

        return {
            "name": name,
            "path": str(active_path),
            "branch": branch,
            "dirty": dirty,
            "last_commit": last_commit,
            "tech_stack": RepoInspector.detect_tech_stack(active_path)
        }

    @classmethod
    def build_system_prompt(cls, sender_jid: Optional[str] = None) -> str:
        """
        Dynamically constructs the system prompt with rich developer identity,
        active workspace state, local project index, durable facts, and recent session summaries.
        """
        ws = cls.get_active_workspace_summary()

        # Build concise project directory listing
        projects_brief = []
        if PROJECTS_ROOT.exists():
            for d in sorted(PROJECTS_ROOT.iterdir()):
                if d.is_dir() and not d.name.startswith("."):
                    stack = RepoInspector.detect_tech_stack(d)
                    projects_brief.append(f"{d.name} ({stack})")
        projects_str = ", ".join(projects_brief[:10])

        # Retrieve relevant durable facts for active workspace
        facts = MemoryManager.get_relevant_facts(workspace=ws["path"], limit=5)
        facts_section = ""
        if facts:
            facts_list = "\n".join(f"  • {f}" for f in facts)
            facts_section = f"\nRemembered Facts & Preferences:\n{facts_list}\n"

        # Retrieve recent session summaries (episodic memory)
        summaries = MemoryManager.get_recent_session_summaries(workspace=ws["path"], limit=2)
        summaries_section = ""
        if summaries:
            sum_list = "\n".join(f"  • {s['title']}: {s['summary']}" for s in summaries)
            summaries_section = f"\nRecent Context & Decisions:\n{sum_list}\n"

        prompt = (
            f"You are Chai, the personal AI assistant for {cls.DEVELOPER_NAME} (GitHub: {cls.GITHUB_USERNAME}).\n"
            f"You run locally on {cls.DEVELOPER_NAME}'s Linux computer.\n\n"
            f"Developer Environment:\n"
            f"• User: {cls.DEVELOPER_NAME} ({cls.GITHUB_USERNAME})\n"
            f"• Active Project: {ws['name']} ({ws['path']})\n"
            f"• Branch: {ws['branch']} {'(dirty)' if ws['dirty'] else '(clean)'}\n"
            f"• Latest Commit: {ws['last_commit']}\n"
            f"• Available Projects: {projects_str}\n"
            f"{facts_section}"
            f"{summaries_section}\n"
            f"Instructions:\n"
            f"• Always recognize that references to 'my repo', 'my projects', or repo names refer to {cls.DEVELOPER_NAME}'s local repositories.\n"
            f"• Answer concisely, directly, and technically in Telegram markdown format.\n"
            f"• Avoid unnecessary pleasantries or filler phrases."
        )
        return prompt

    @classmethod
    def synthesize_multi_turn_task(cls, current_prompt: str, history: List[Dict[str, str]]) -> str:
        """
        Synthesizes the current user prompt with previous context turns
        to resolve pronouns ('it', 'that', 'my repo', 'the project') before
        passing to Antigravity or tools.
        """
        if not history:
            return current_prompt

        # Find the last user turn if it exists
        previous_user_turns = [
            turn["content"] for turn in history 
            if turn.get("role") == "user" and turn.get("content") != current_prompt
        ]

        if not previous_user_turns:
            return current_prompt

        last_user_query = previous_user_turns[-1].strip()

        # Check if the current prompt looks like a clarification or follow-up
        lower = current_prompt.lower().replace("’", "'").replace("‘", "'")
        follow_up_cues = [
            "i mean", "i'm talking about", "im talking about", "i am talking about",
            "not that", "the other one", "also", "and then", "what about",
            "fix it", "run it", "check it", "do it"
        ]

        is_follow_up = any(cue in lower for cue in follow_up_cues) or len(current_prompt.split()) <= 4

        if is_follow_up:
            synthesized = f"Previous context: User asked \"{last_user_query}\". Clarification / follow-up: \"{current_prompt}\". Fulfill the user's intent."
            logger.info(f"Synthesized multi-turn task: '{synthesized}'")
            return synthesized

        return current_prompt

    RE_DIRECT_COMMAND = re.compile(
        r"^(?:git|pytest|npm|yarn|pnpm|bun|cargo|mvn|docker|python|python3|pip|bash|sh|curl|wget)\b|"
        r"^(?:ls|cd|pwd|cat|grep|kill|ps)\b",
        re.IGNORECASE
    )

    @classmethod
    async def synthesize_antigravity_task(
        cls, 
        prompt: str, 
        sender_jid: str, 
        workspace_path: str,
        timeout: float = 4.5
    ) -> str:
        """
        Transforms casual user speech / voice notes into a structured engineering specification
        using TASK_SYNTHESIZER_MODEL before handing to the Antigravity CLI runner.
        Bypasses synthesis for direct shell commands or already structured inputs.
        """
        clean = prompt.strip()

        # 1. Fast Bypass Check: Direct terminal / shell commands (e.g. 'git status', 'pytest')
        if cls.RE_DIRECT_COMMAND.match(clean) or clean.startswith("/"):
            logger.info(f"TaskSynthesizer: Bypassing synthesis for direct command '{clean}'")
            return clean

        # 2. Gather active context
        ws = cls.get_active_workspace_summary()
        recent_turns = MemoryManager.get_active_session_history(sender_jid, limit=3, exclude_last_if_current=True)
        facts = MemoryManager.get_relevant_facts(workspace=workspace_path, limit=3)

        turns_snippet = ""
        if recent_turns:
            lines = [f"{'User' if t['role'] == 'user' else 'Assistant'}: {t['content'][:120].replace(chr(10), ' ')}" for t in recent_turns]
            turns_snippet = "Recent Conversation:\n" + "\n".join(lines) + "\n\n"

        facts_snippet = ""
        if facts:
            facts_snippet = "Known Project Facts:\n" + "\n".join(f"• {f}" for f in facts) + "\n\n"

        synthesis_prompt = (
            f"You are a Staff Software Engineer preparing a high-signal task specification for an autonomous developer agent (Antigravity).\n\n"
            f"Workspace Context:\n"
            f"• Project: {ws['name']} ({ws['path']})\n"
            f"• Tech Stack: {ws['tech_stack']}\n"
            f"• Branch: {ws['branch']} {'(dirty)' if ws['dirty'] else '(clean)'}\n"
            f"• Latest Commit: {ws['last_commit']}\n\n"
            f"{facts_snippet}"
            f"{turns_snippet}"
            f"User Prompt: \"{clean}\"\n\n"
            f"Convert this prompt into a concise, actionable engineering specification.\n"
            f"Rules:\n"
            f"1. Clearly state the engineering goal and expected outcome.\n"
            f"2. Reference relevant project components or files if implied.\n"
            f"3. Include safety/verification instructions (e.g. run tests, avoid breaking existing behavior).\n"
            f"4. DO NOT dictate exact code implementations. State WHAT needs to be done, leaving HOW to the coding agent.\n\n"
            f"Output the specification directly without conversational preamble or markdown fences."
        )

        try:
            res = await asyncio.wait_for(
                asyncio.to_thread(
                    ollama.chat,
                    model=TASK_SYNTHESIZER_MODEL,
                    messages=[{"role": "user", "content": synthesis_prompt}],
                    options={"temperature": 0.2, "num_predict": 256}
                ),
                timeout=timeout
            )
            msg_obj = res.get("message", {})
            synthesized = (msg_obj.get("content") or getattr(msg_obj, "content", "") or "").strip()
            if not synthesized:
                thinking = getattr(msg_obj, "thinking", None) or (msg_obj.get("thinking") if isinstance(msg_obj, dict) else None)
                if thinking:
                    synthesized = str(thinking).strip()

            if synthesized and len(synthesized) >= 15:
                logger.info(f"TaskSynthesizer: Enhanced prompt for AGY:\n{synthesized[:100]}...")
                return synthesized
        except asyncio.TimeoutError:
            logger.warning(f"TaskSynthesizer: Task synthesis timed out after {timeout}s, falling back to prompt.")
        except Exception as e:
            logger.warning(f"TaskSynthesizer: Synthesis fallback due to: {e}")

        return clean
