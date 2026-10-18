import re
import time
import asyncio
from typing import Dict, Any, Optional
import ollama
from config import DISPATCHER_MODEL, OLLAMA_HOST
from core.workspace_manager import WorkspaceManager
from core.logger import get_logger

logger = get_logger("triage")

# Instant canned responses for common chit-chat greetings (0ms latency)
FAST_GREETINGS = {
    "hi": "Hello! How can I assist you today?",
    "hello": "Hi there! What can I help you with?",
    "hey": "Hey! Ready to help with code, assignments, or terminal tasks.",
    "hiya": "Hi! How can I help today?",
    "yo": "Yo! What are we working on?",
    "good morning": "Good morning! Ready for today's tasks.",
    "good afternoon": "Good afternoon! How can I help?",
    "good evening": "Good evening! What can I assist you with?",
    "how are you": "I'm running fast and ready to help! How are you doing?",
    "who are you": "I am Chai, your personal Linux assistant powered by local AI and Antigravity.",
    "what can you do": (
        "Here is what I can do:\n"
        "• 💻 *Coding & Terminal:* Ask me to edit code, run tests, fix bugs, or git operations.\n"
        "• 📄 *Academic Assignments:* Ask for an essay, report, or paper to compile a styled PDF.\n"
        "• 📁 *Workspace Switching:* Use `projects` or `cd <repo>` to switch contexts.\n"
        "• 🎙️ *Voice Notes:* Send voice notes and I will transcribe and execute them.\n"
        "• 🛠️ *Diagnostics:* Run `/debug status`, `/ping`, or `/status`."
    ),
    "thanks": "You're very welcome!",
    "thank you": "Glad to help! Let me know if you need anything else.",
    "thx": "Anytime! Let me know what's next.",
    "ok": "Understood! Standing by.",
    "okay": "Got it! Standing by.",
    "great": "Awesome! Let me know what you'd like to do next.",
    "cool": "Glad you like it! What's next?",
    "bye": "Goodbye! Have a great day.",
    "goodbye": "See you later! Feel free to reach out anytime."
}

# Regex patterns for deterministic action classification (< 1ms)
RE_WORKSPACE_LS = re.compile(r"^(?:list\s+projects|ls\s+projects|projects|ls)$", re.IGNORECASE)
RE_WORKSPACE_SWITCH = re.compile(r"^(?:switch\s+to|cd|open\s+project|open\s+workspace)\s+(.+)$", re.IGNORECASE)
RE_WORKSPACE_INFO = re.compile(r"^(?:workspace|pwd|current\s+workspace|where\s+am\s+i)$", re.IGNORECASE)

RE_ASSIGNMENT_CREATE = re.compile(
    r"(?:write\s+(?:an?\s+)?(?:essay|assignment|report|paper|article)|"
    r"create\s+(?:an?\s+)?(?:assignment|report|pdf|paper|doc)|"
    r"generate\s+(?:an?\s+)?(?:report|assignment|pdf|essay)|"
    r"prepare\s+(?:an?\s+)?(?:assignment|report|paper)|"
    r"homework\s+on\s+)",
    re.IGNORECASE
)

RE_ASSIGNMENT_REVISE = re.compile(
    r"(?:revise\s+(?:the\s+)?(?:assignment|report|pdf|paper)|"
    r"update\s+(?:the\s+)?(?:assignment|report|pdf|paper)|"
    r"edit\s+(?:the\s+)?(?:assignment|report|pdf|paper)|"
    r"change\s+(?:the\s+)?(?:assignment|report|pdf|section))",
    re.IGNORECASE
)

RE_CODE_TRIGGERS = re.compile(
    r"^(?:fix|debug|run|test|pytest|git|npm|node|python|python3|pip|cargo|mvn|docker|"
    r"compile|build|refactor|inspect|grep|bash|terminal|checkout|commit|push|pull)\b|"
    r"(?:please\s+(?:fix|debug|run|test)|can\s+you\s+(?:fix|debug|run|test|create\s+file|edit))|"
    r"\b(?:git\s+status|git\s+diff|git\s+log|git\s+branch|git\s+commit|git\s+push|git\s+pull)\b|"
    r"\b(?:run\s+tests|run\s+pytest|run\s+build|unit\s+test|fix\s+bug|fix\s+error)\b",
    re.IGNORECASE
)

# Preferred lightweight router model tag
FAST_ROUTER_MODEL = "qwen2.5:0.5b"

class FastTriage:
    """Multi-tiered zero-latency and low-latency intent triage engine."""

    @classmethod
    def match_fast_path(cls, user_text: str) -> Optional[Dict[str, Any]]:
        """
        Tier 0: Rule & Regex Matcher.
        Returns classified intent dict if matched, or None to fall through.
        Latency: < 0.1ms.
        """
        text = user_text.strip()
        clean = re.sub(r"[^\w\s]", "", text.lower()).strip()

        # 1. Instant chit-chat greetings
        if clean in FAST_GREETINGS:
            return {"action": "FAST_CHAT", "reply": FAST_GREETINGS[clean]}

        # 2. Workspace queries
        if RE_WORKSPACE_LS.match(text):
            available = "\n".join(f"• `{p}`" for p in WorkspaceManager.list_available_projects())
            current = WorkspaceManager.get_current_workspace_info()
            return {"action": "DIRECT_REPLY", "reply": f"{current}\n\n📁 **Available Projects:**\n{available}"}

        switch_match = RE_WORKSPACE_SWITCH.match(text)
        if switch_match:
            target = switch_match.group(1).strip()
            success, msg = WorkspaceManager.switch_workspace(target)
            return {"action": "DIRECT_REPLY", "reply": msg}

        if RE_WORKSPACE_INFO.match(text):
            return {"action": "DIRECT_REPLY", "reply": WorkspaceManager.get_current_workspace_info()}

        # 3. Direct Code / Developer triggers -> ANTIGRAVITY
        if RE_CODE_TRIGGERS.search(text):
            return {"action": "ANTIGRAVITY", "task": text}

        # 4. Academic Document triggers -> ASSIGNMENT_CREATE / REVISE
        if RE_ASSIGNMENT_REVISE.search(text):
            return {"action": "ASSIGNMENT_REVISE", "changes": text}

        if RE_ASSIGNMENT_CREATE.search(text):
            # Extract basic title from prompt
            title_candidate = re.sub(RE_ASSIGNMENT_CREATE, "", text).strip()
            title = title_candidate[:40].title() if title_candidate else "Academic Assignment"
            return {"action": "ASSIGNMENT_CREATE", "title": title, "topic": text}

        return None

    RE_QUESTION_WORDS = re.compile(
        r"^(?:why|what|how|who|when|where|can\s+you\s+explain|explain|tell\s+me|is\s+it|are\s+there|does|do\s+you|describe)\b",
        re.IGNORECASE
    )

    RE_DEV_AMBIGUOUS = re.compile(
        r"\b(?:check|deploy|install|setup|configure|restart|status|process|port|script|file|repo|server|docker)\b",
        re.IGNORECASE
    )

    @classmethod
    async def classify_ambiguous(cls, user_text: str) -> str:
        """
        Tier 1: High-Speed Triage for unpatterned queries.
        Recognizes question patterns instantly as CHAT without LLM call.
        """
        text = user_text.strip()

        # Instant check: Questions and conversational queries default to CHAT (< 0.1ms)
        if cls.RE_QUESTION_WORDS.search(text):
            return "CHAT"

        # Check for developer/system verbs
        if cls.RE_DEV_AMBIGUOUS.search(text):
            return "ANTIGRAVITY"

        # Safe default is CHAT (single-pass conversational generation)
        return "CHAT"
