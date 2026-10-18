import time
import os
import shutil
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx
from sqlmodel import select, func

from config import (
    OLLAMA_HOST, 
    DISPATCHER_MODEL, 
    BRIDGE_URL, 
    DATA_DIR, 
    BASE_DIR,
    TELEGRAM_BOT_TOKEN
)
from core.db import get_session, MessageRecord, AssignmentRecord, SessionRecord, LongTermFact
from core.memory import MemoryManager
from core.agy_runner import AntigravityRunner
from core.logger import get_logger, tail_logs

logger = get_logger("debug_router")

# Global runtime debug verbose toggle
_RUNTIME_DEBUG_VERBOSE = False
_START_TIME = time.time()

def get_uptime_str() -> str:
    uptime_sec = int(time.time() - _START_TIME)
    mins, sec = divmod(uptime_sec, 60)
    hours, mins = divmod(mins, 60)
    days, hours = divmod(hours, 24)
    if days > 0:
        return f"{days}d {hours}h {mins}m"
    if hours > 0:
        return f"{hours}h {mins}m {sec}s"
    return f"{mins}m {sec}s"

def is_debug_verbose() -> bool:
    global _RUNTIME_DEBUG_VERBOSE
    return _RUNTIME_DEBUG_VERBOSE

def set_debug_verbose(enabled: bool):
    global _RUNTIME_DEBUG_VERBOSE
    _RUNTIME_DEBUG_VERBOSE = enabled

class DebugRouter:
    """Handles /debug, /status, /ping, and system inspection commands directly."""

    @classmethod
    def is_debug_command(cls, text: str) -> bool:
        t = text.strip().lower()
        return (
            t.startswith("/debug") or
            t.startswith("!debug") or
            t in ["/ping", "ping", "/status", "/sysinfo", "/diag", "diagnostics"]
        )

    @classmethod
    async def handle_debug_command(cls, user_text: str, sender_jid: str) -> Dict[str, Any]:
        """Routes and executes a debug command, returning a formatted response."""
        parts = user_text.strip().split()
        cmd = parts[0].lower()
        subcmd = parts[1].lower() if len(parts) > 1 else ""
        arg = parts[2].lower() if len(parts) > 2 else ""

        # Normalize alias commands
        if cmd in ["/ping", "ping"]:
            subcmd = "ping"
        elif cmd in ["/status", "/sysinfo"]:
            subcmd = "status"
        elif cmd in ["/help", "help", "/commands", "commands", "?"]:
            subcmd = "help"

        logger.info(f"Handling debug subcmd='{subcmd}', arg='{arg}'")

        if subcmd == "ping":
            return await cls._handle_ping()
        elif subcmd in ["status", "sysinfo", ""]:
            return await cls._handle_status()
        elif subcmd == "logs":
            count = 20
            if subcmd == "logs" and len(parts) > 2:
                try:
                    count = int(parts[2])
                except ValueError:
                    count = 20
            return cls._handle_logs(count)
        elif subcmd == "memory":
            return cls._handle_memory(sender_jid)
        elif subcmd == "agy":
            return cls._handle_agy(arg)
        elif subcmd == "mode":
            return cls._handle_mode(arg)
        elif subcmd == "session":
            return cls._handle_session(arg)
        elif subcmd in ["help", "-h", "--help"]:
            return cls._handle_help()
        else:
            return {
                "type": "text",
                "text": f"❓ Unknown debug command: `{subcmd}`\n\nRun `/debug help` to see available commands."
            }

    @classmethod
    async def _handle_ping(cls) -> Dict[str, Any]:
        start = time.perf_counter()
        ollama_ok = False
        ollama_ms = 0.0

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                o_start = time.perf_counter()
                res = await client.get(f"{OLLAMA_HOST}/api/tags")
                ollama_ms = (time.perf_counter() - o_start) * 1000
                ollama_ok = res.status_code == 200
        except Exception:
            ollama_ok = False

        total_ms = (time.perf_counter() - start) * 1000

        msg = (
            f"🏓 *Pong!*\n\n"
            f"• *Orchestrator Uptime:* {get_uptime_str()}\n"
            f"• *Internal Latency:* {total_ms:.1f}ms\n"
            f"• *Ollama Latency:* {ollama_ms:.1f}ms ({'✅ Online' if ollama_ok else '❌ Offline'})\n"
            f"• *Active Model:* `{DISPATCHER_MODEL}`"
        )
        return {"type": "text", "text": msg}

    @classmethod
    async def _handle_status(cls) -> Dict[str, Any]:
        # System resources
        try:
            import psutil
            cpu_pct = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            mem_used_gb = mem.used / (1024 ** 3)
            mem_total_gb = mem.total / (1024 ** 3)
            mem_pct = mem.percent
        except Exception:
            cpu_pct = "N/A"
            mem_used_gb, mem_total_gb, mem_pct = 0, 0, 0

        # Disk usage of data dir
        try:
            total, used, free = shutil.disk_usage(DATA_DIR)
            disk_free_gb = free / (1024 ** 3)
            disk_total_gb = total / (1024 ** 3)
        except Exception:
            disk_free_gb, disk_total_gb = 0, 0

        # Active workspace
        active_ws = MemoryManager.get_active_workspace()

        # Database counts
        try:
            with get_session() as session:
                msg_count = session.exec(select(func.count(MessageRecord.id))).one()
                doc_count = session.exec(select(func.count(AssignmentRecord.id))).one()
        except Exception:
            msg_count, doc_count = 0, 0

        # Check Ollama
        ollama_status = "❌ Offline"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{OLLAMA_HOST}/api/tags")
                if res.status_code == 200:
                    models = [m.get("name") for m in res.json().get("models", [])]
                    ollama_status = f"✅ Online ({len(models)} models available)"
        except Exception:
            pass

        # Interface status
        telegram_status = "✅ Connected" if TELEGRAM_BOT_TOKEN else "⚠️ Token Not Configured"

        # Antigravity status
        agy_stat = AntigravityRunner.get_status()
        agy_text = f"⚙️ Running (PID {agy_stat['pid']}, {agy_stat['elapsed_seconds']}s)" if agy_stat['is_running'] else "💤 Idle"

        status_msg = (
            f"📊 *Chai System Diagnostics*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ *Uptime:* {get_uptime_str()}\n"
            f"💻 *CPU:* {cpu_pct}% | *RAM:* {mem_used_gb:.1f}/{mem_total_gb:.1f} GB ({mem_pct}%)\n"
            f"💾 *Disk Free:* {disk_free_gb:.1f} / {disk_total_gb:.1f} GB\n"
            f"📁 *Workspace:* `{active_ws}`\n"
            f"🤖 *Ollama:* {ollama_status}\n"
            f"✈️ *Telegram:* {telegram_status}\n"
            f"🚀 *Antigravity:* {agy_text}\n"
            f"📚 *Database:* {msg_count} messages, {doc_count} assignments\n"
            f"🔍 *Verbose Mode:* {'ON' if is_debug_verbose() else 'OFF'}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        return {"type": "text", "text": status_msg}

    @classmethod
    def _handle_logs(cls, count: int) -> Dict[str, Any]:
        count = max(5, min(count, 50))
        lines = tail_logs(count)
        joined = "".join(lines).strip()

        if len(joined) > 3000:
            joined = joined[-2900:]

        return {
            "type": "text",
            "text": f"📋 *Recent Logs (Last {count} lines):*\n```\n{joined}\n```"
        }

    @classmethod
    def _handle_memory(cls, sender_jid: str = "") -> Dict[str, Any]:
        with get_session() as session:
            msg_count = session.exec(select(func.count(MessageRecord.id))).one()
            session_count = session.exec(select(func.count(SessionRecord.id))).one()
            facts_count = session.exec(select(func.count(LongTermFact.id))).one()
            latest_assignment = MemoryManager.get_latest_assignment()

        active_sess = MemoryManager.get_active_session(sender_jid) if sender_jid else None
        active_sess_str = "None"
        turns_str = "_No turns in active session_"
        if active_sess:
            active_sess_str = f"`{active_sess.session_id}` ({active_sess.turn_count} turns, ws: `{Path(active_sess.workspace).name}`)"
            active_turns = MemoryManager.get_active_session_history(sender_jid, limit=5)
            if active_turns:
                turns_lines = [
                    f"{'👤' if t['role'] == 'user' else '🤖'} {t['content'][:55].replace(chr(10), ' ')}"
                    for t in active_turns
                ]
                turns_str = "\n".join(turns_lines)

        summaries = MemoryManager.get_recent_session_summaries(limit=2)
        sum_str = "\n".join(f"• *{s['title']}*: {s['summary']}" for s in summaries) if summaries else "_No summaries yet_"

        facts = MemoryManager.get_all_facts(limit=3)
        facts_str = "\n".join(f"• [{f.id}] {f.fact}" for f in facts) if facts else "_No durable facts_"

        latest_doc_str = f"*{latest_assignment.title}* (v{latest_assignment.version})" if latest_assignment else "None"

        return {
            "type": "text",
            "text": (
                f"🧠 *Memory & Context State*\n\n"
                f"• *Total Messages:* {msg_count} | *Sessions:* {session_count} | *Facts:* {facts_count}\n"
                f"• *Active Session:* {active_sess_str}\n"
                f"• *Latest Assignment:* {latest_doc_str}\n\n"
                f"💬 *Active Working Memory (Last 5 Turns):*\n{turns_str}\n\n"
                f"📜 *Recent Episodic Summaries:*\n{sum_str}\n\n"
                f"📌 *Durable Facts:*\n{facts_str}"
            )
        }

    @classmethod
    def _handle_agy(cls, action: str) -> Dict[str, Any]:
        if action == "kill":
            success, msg = AntigravityRunner.kill_active()
            return {"type": "text", "text": f"{'✅' if success else 'ℹ️'} {msg}"}
        else:
            status = AntigravityRunner.get_status()
            if status["is_running"]:
                task = status.get("active_task") or {}
                return {
                    "type": "text",
                    "text": (
                        f"⚙️ *Antigravity Task is Running*\n"
                        f"• *PID:* {status['pid']}\n"
                        f"• *Elapsed:* {status['elapsed_seconds']}s\n"
                        f"• *Workspace:* `{task.get('workspace', 'unknown')}`\n"
                        f"• *Prompt:* \"{task.get('prompt', '')[:100]}...\"\n\n"
                        f"_Send `/debug agy kill` to terminate it._"
                    )
                }
            else:
                last = status.get("last_execution")
                last_str = "None"
                if last:
                    last_str = (
                        f"\n• *Last Task:* \"{last.get('prompt', '')}\"\n"
                        f"• *Duration:* {last.get('duration_seconds')}s\n"
                        f"• *Exit Code:* {last.get('returncode')}\n"
                        f"• *Time:* {last.get('timestamp')}"
                    )
                can_term, term_bin = AntigravityRunner.can_spawn_terminal()
                term_info = f"• *Live Screen Terminal:* {'✅ ' + Path(term_bin).name if can_term else '❌ Headless'}\n"
                return {
                    "type": "text",
                    "text": f"💤 *Antigravity is Idle*\n{term_info}{last_str}"
                }

    @classmethod
    def _handle_mode(cls, arg: str) -> Dict[str, Any]:
        if arg in ["on", "enable", "1", "true"]:
            set_debug_verbose(True)
            return {"type": "text", "text": "✅ Verbose debug mode is now *ON*.\nExecution timing and intent footers will be attached to replies."}
        elif arg in ["off", "disable", "0", "false"]:
            set_debug_verbose(False)
            return {"type": "text", "text": "✅ Verbose debug mode is now *OFF*."}
        else:
            current = "ON" if is_debug_verbose() else "OFF"
            return {"type": "text", "text": f"Verbose debug mode is currently *{current}*.\nUse `/debug mode on` or `/debug mode off` to toggle."}

    @classmethod
    def _handle_session(cls, action: str) -> Dict[str, Any]:
        auth_dir = BASE_DIR / "bridge" / "auth_info_baileys"
        if not auth_dir.exists():
            return {"type": "text", "text": "⚠️ Auth directory does not exist."}

        if action in ["reset", "clean", "purge", "fix"]:
            deleted_count = 0
            for f in auth_dir.glob("session-*.json"):
                try:
                    f.unlink()
                    deleted_count += 1
                except Exception:
                    pass
            return {
                "type": "text",
                "text": (
                    f"✅ Purged {deleted_count} Signal session ratchet files.\n\n"
                    f"• *Login state:* Preserved (`creds.json` intact, no QR scan needed).\n"
                    f"• *Signal ratchet:* Auto-resets on next message to fix any Bad MAC desyncs."
                )
            }
        else:
            session_files = list(auth_dir.glob("session-*.json"))
            total_size_kb = sum(f.stat().st_size for f in session_files) / 1024
            return {
                "type": "text",
                "text": (
                    f"🔐 *Signal Session State*\n\n"
                    f"• *Active Session Files:* {len(session_files)}\n"
                    f"• *Total Session Storage:* {total_size_kb:.1f} KB\n\n"
                    f"_Send `/debug session reset` to purge corrupted session ratchets without logging out._"
                )
            }

    @classmethod
    def _handle_help(cls) -> Dict[str, Any]:
        return {
            "type": "text",
            "text": (
                "🤖 *Chai Assistant — Command Reference*\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "📁 *Workspaces & Code Projects*\n"
                "• `/projects` or `/ls` — List available local code repositories\n"
                "• `/cd <project>` — Switch active workspace repository\n\n"
                "🧠 *Contextual Memory & Sessions*\n"
                "• `/new` or `/reset` — Start fresh session (clears working memory)\n"
                "• `/session` — View active session info, turns & idle timer\n"
                "• `/memory` — View working turns, past summaries & stored facts\n"
                "• `/remember <fact>` — Save a durable technical fact or preference\n"
                "• `/forget <id|word>` — Remove a stored fact\n\n"
                "💻 *Coding & Terminal (Antigravity)*\n"
                "• Natural language triggers Antigravity on your machine:\n"
                "  _e.g., \"fix bug in bridge.js\", \"run pytest\", \"git status\"_\n"
                "• `/debug agy` — View Antigravity runner status & active task\n"
                "• `/debug agy kill` — Terminate running Antigravity task\n\n"
                "📄 *Academic Assignments & Research*\n"
                "• Natural language generates styled PDFs:\n"
                "  _e.g., \"write an essay on Distributed Systems\"_\n"
                "• Natural language revisions:\n"
                "  _e.g., \"revise the assignment to add a comparison table\"_\n\n"
                "🛠️ *System & Diagnostics*\n"
                "• `/status` or `/sysinfo` — View CPU, RAM, Disk, and service health\n"
                "• `/ping` — Measure round-trip bot & Ollama latency\n"
                "• `/debug logs [N]` — View recent log lines (default 20)\n"
                "• `/debug memory` — Deep database & session inspection\n"
                "• `/debug mode [on|off]` — Toggle response execution timing\n"
                "• `/help` — Display this command reference\n"
                "━━━━━━━━━━━━━━━━━━━━"
            )
        }
