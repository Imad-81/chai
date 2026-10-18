import os
import sys
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List

from telegram import Update, constants, BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from datetime import datetime, timezone

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_ALLOWED_USERS,
    DATA_DIR,
    AUDIO_DIR,
    MEMORY_SESSION_TIMEOUT_MINUTES
)
from core.memory import MemoryManager
from core.transcriber import VoiceTranscriber
from core.dispatcher import Dispatcher
from core.debug_router import DebugRouter
from core.workspace_manager import WorkspaceManager
from core.logger import get_logger

logger = get_logger("telegram")

def is_authorized(user_id: int) -> bool:
    """Checks if the user is authorized to use this personal assistant."""
    if not TELEGRAM_ALLOWED_USERS:
        return True
    return user_id in TELEGRAM_ALLOWED_USERS

async def send_safe_message(chat, text: str):
    """Sends text message with Markdown formatting and auto-fallback to plain text."""
    if not text:
        return

    # Telegram limit is 4096 characters per message
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try:
            await chat.send_message(chunk, parse_mode=constants.ParseMode.MARKDOWN)
        except Exception:
            # Fallback to plain text if Markdown parsing fails (e.g. unclosed backticks)
            await chat.send_message(chunk)

async def _send_result_payload(chat, result: Dict[str, Any], sender_id: str):
    """Delivers the dispatcher result (text and/or documents) to the Telegram chat."""
    files_to_send: List[Dict[str, Any]] = []
    if result.get("files"):
        for item in result["files"]:
            if isinstance(item, dict):
                files_to_send.append(item)
            elif isinstance(item, (str, Path)):
                files_to_send.append({
                    "filePath": str(item),
                    "fileName": Path(item).name,
                    "caption": f"📄 Delivered: `{Path(item).name}`"
                })
    elif result.get("filePath"):
        files_to_send.append({
            "filePath": result.get("filePath"),
            "fileName": result.get("fileName") or Path(result.get("filePath")).name,
            "caption": result.get("caption", "")
        })

    reply_text = result.get("text", "")

    # 1. Send text message if text content exists
    if reply_text:
        MemoryManager.save_message(
            sender_jid=sender_id,
            role="assistant",
            content=reply_text,
            content_type="text"
        )
        await send_safe_message(chat, reply_text)

    # 2. Upload and deliver all attached files
    for doc in files_to_send:
        f_path = doc.get("filePath")
        f_name = doc.get("fileName") or (Path(f_path).name if f_path else "document")
        f_caption = doc.get("caption") or f"📄 Delivered: `{f_name}`"
        if f_path and Path(f_path).exists():
            await chat.send_action(action=constants.ChatAction.UPLOAD_DOCUMENT)
            with open(f_path, "rb") as f:
                await chat.send_document(
                    document=f,
                    filename=f_name,
                    caption=f_caption,
                    parse_mode=constants.ParseMode.MARKDOWN
                )
            MemoryManager.save_message(
                sender_jid=sender_id,
                role="assistant",
                content=f"[Sent Document: {f_name}] {f_caption}",
                content_type="document"
            )
        else:
            await send_safe_message(chat, f"⚠️ Document compiled but file was not found at `{f_path}`")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text("⛔ Unauthorized: This personal assistant is restricted to authorized users.")
        return

    welcome_text = (
        f"🤖 *Hello, {user.first_name}!*\n\n"
        f"I am *Chai*, your personal Linux assistant powered by local Ollama & Antigravity.\n\n"
        f"✨ *Capabilities:*\n"
        f"• 🎙️ *Voice Notes:* Send voice messages and I'll transcribe & execute them.\n"
        f"• 💻 *Coding & Terminal:* Ask me to edit code, run commands, or fix bugs with Antigravity.\n"
        f"• 📄 *Academic Assignments:* Ask for an essay or report and I'll compile a styled PDF.\n"
        f"• 📁 *Workspace Switching:* Use `/projects` or `/cd <repo>` to switch contexts.\n"
        f"• 🛠️ *Diagnostics:* Use `/debug status`, `/ping`, or `/debug logs`.\n\n"
        f"_Type anything or send a voice note to get started!_"
    )
    await send_safe_message(update.effective_chat, welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_authorized(user.id):
        return

    help_text = (
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
    await send_safe_message(update.effective_chat, help_text)

async def projects_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    available = "\n".join(f"• `{p}`" for p in WorkspaceManager.list_available_projects())
    current = WorkspaceManager.get_current_workspace_info()
    await send_safe_message(update.effective_chat, f"{current}\n\n📁 *Available Projects:*\n{available}")

async def cd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    if not context.args:
        current = WorkspaceManager.get_current_workspace_info()
        await send_safe_message(update.effective_chat, f"{current}\n\nUsage: `/cd <project_name>`")
        return
    target = " ".join(context.args)
    success, msg = WorkspaceManager.switch_workspace(target)
    await send_safe_message(update.effective_chat, msg)

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts a clean, fresh conversation session and seals the previous one."""
    user = update.effective_user
    if not is_authorized(user.id):
        return
    sender_id = str(user.id)
    sealed = MemoryManager.seal_active_session(sender_id, summarize=True)
    new_sess = MemoryManager.get_or_create_active_session(sender_id)
    
    summary_note = f"\n• Sealed previous session `{sealed.session_id}` ({sealed.turn_count} turns)" if sealed else ""
    msg = (
        f"🔄 *New Conversation Session Started*\n\n"
        f"• *Active Session ID:* `{new_sess.session_id}`\n"
        f"• *Workspace:* `{new_sess.workspace}`{summary_note}\n\n"
        f"_Working memory has been reset. Stored facts and past session summaries are preserved._"
    )
    await send_safe_message(update.effective_chat, msg)

async def session_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays active session metadata, duration, turns, and idle timer."""
    user = update.effective_user
    if not is_authorized(user.id):
        return
    sender_id = str(user.id)
    sess = MemoryManager.get_or_create_active_session(sender_id)
    now = datetime.now(timezone.utc)
    
    start_time = sess.started_at
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    duration_m = int((now - start_time).total_seconds() / 60)
    
    last_act = sess.last_activity_at
    if last_act.tzinfo is None:
        last_act = last_act.replace(tzinfo=timezone.utc)
    idle_m = int((now - last_act).total_seconds() / 60)
    
    msg = (
        f"💬 *Active Session Details*\n\n"
        f"• *Session ID:* `{sess.session_id}`\n"
        f"• *Workspace:* `{sess.workspace}`\n"
        f"• *Turns in Session:* {sess.turn_count}\n"
        f"• *Session Age:* {duration_m}m (started {sess.started_at.strftime('%H:%M:%S')})\n"
        f"• *Idle Since:* {idle_m}m ago\n"
        f"• *Auto-seal Timeout:* {MEMORY_SESSION_TIMEOUT_MINUTES}m\n\n"
        f"_Send `/new` to seal this session and start fresh._"
    )
    await send_safe_message(update.effective_chat, msg)

async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays working memory turns, episodic summaries, and durable facts."""
    user = update.effective_user
    if not is_authorized(user.id):
        return
    sender_id = str(user.id)
    sess = MemoryManager.get_or_create_active_session(sender_id)
    
    # Working memory turns in active session
    active_turns = MemoryManager.get_active_session_history(sender_id, limit=5)
    turns_text = "\n".join(
        f"  {'👤' if t['role'] == 'user' else '🤖'} {t['content'][:50].replace(chr(10), ' ')}"
        for t in active_turns
    ) if active_turns else "  _No turns in active session yet_"
    
    # Recent session summaries
    summaries = MemoryManager.get_recent_session_summaries(limit=3)
    sum_text = "\n".join(
        f"  • *{s['title']}* ({s['ended_at']}):\n    _{s['summary']}_"
        for s in summaries
    ) if summaries else "  _No past session summaries yet_"
    
    # Long-term facts
    facts = MemoryManager.get_all_facts(limit=5)
    facts_text = "\n".join(
        f"  • [{f.id}] {f.fact}"
        for f in facts
    ) if facts else "  _No durable facts saved. Use `/remember <fact>` to save one._"
    
    msg = (
        f"🧠 *Chai Smart Memory State*\n\n"
        f"🔹 *Active Session (`{sess.session_id}`)*:\n{turns_text}\n\n"
        f"📜 *Recent Episodic Summaries*:\n{sum_text}\n\n"
        f"📌 *Durable Long-Term Facts*:\n{facts_text}\n\n"
        f"_Commands: `/new` (reset working memory), `/remember <fact>`, `/forget <id>`_"
    )
    await send_safe_message(update.effective_chat, msg)

async def remember_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saves a permanent fact or user preference."""
    user = update.effective_user
    if not is_authorized(user.id):
        return
    if not context.args:
        await send_safe_message(
            update.effective_chat, 
            "Usage: `/remember <fact to remember>`\nExample: `/remember We use Vite on port 5173`"
        )
        return
    fact_text = " ".join(context.args).strip()
    ws = MemoryManager.get_active_workspace()
    rec = MemoryManager.save_fact(fact=fact_text, category="user_specified", workspace=ws)
    await send_safe_message(
        update.effective_chat, 
        f"📌 *Fact Remembered (ID: {rec.id})*\n\n\"{rec.fact}\"\n\n_Tagged to workspace: `{Path(ws).name}`_"
    )

async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes a remembered fact by ID or keyword."""
    user = update.effective_user
    if not is_authorized(user.id):
        return
    if not context.args:
        await send_safe_message(
            update.effective_chat, 
            "Usage: `/forget <id or keyword>`\nExample: `/forget 3` or `/forget Vite`"
        )
        return
    query = " ".join(context.args).strip()
    deleted = MemoryManager.delete_fact(query)
    if deleted > 0:
        await send_safe_message(update.effective_chat, f"🗑️ Removed {deleted} remembered fact(s) matching `{query}`.")
    else:
        await send_safe_message(update.effective_chat, f"⚠️ No remembered facts matched `{query}`.")

class InPlaceStatusTracker:
    """Manages at most ONE in-place status message on Telegram to prevent spamming notification bubbles."""
    def __init__(self, chat):
        self.chat = chat
        self.status_msg: Optional[Any] = None
        self._lock = asyncio.Lock()

    async def update(self, text: str):
        if not text:
            return
        async with self._lock:
            try:
                if self.status_msg is None:
                    self.status_msg = await self.chat.send_message(
                        text, 
                        parse_mode=constants.ParseMode.MARKDOWN
                    )
                else:
                    await self.status_msg.edit_text(
                        text, 
                        parse_mode=constants.ParseMode.MARKDOWN
                    )
            except Exception:
                pass

    async def clear(self):
        async with self._lock:
            if self.status_msg:
                try:
                    await self.status_msg.delete()
                except Exception:
                    pass
                self.status_msg = None

    def updater_callback(self):
        return lambda msg: asyncio.create_task(self.update(msg))

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    user_text = update.message.text.strip()

    if not is_authorized(user.id):
        logger.warning(f"Unauthorized message attempt from user {user.id} ({user.username})")
        await update.message.reply_text("⛔ Unauthorized.")
        return

    logger.info(f"Telegram message from @{user.username or user.id}: '{user_text[:60]}'")
    sender_id = str(user.id)

    # 0. Handle in-chat help queries
    if user_text.lower() in ["help", "commands", "/commands", "?", "!help"]:
        await help_command(update, context)
        return

    # 1. Handle in-chat debug commands (/debug, /status, /ping, etc.)
    if DebugRouter.is_debug_command(user_text):
        diag_res = await DebugRouter.handle_debug_command(user_text, sender_id)
        await send_safe_message(chat, diag_res.get("text", ""))
        return

    # 2. Save user message in memory
    MemoryManager.save_message(
        sender_jid=sender_id,
        role="user",
        content=user_text,
        content_type="text"
    )

    # Send typing action
    await chat.send_action(action=constants.ChatAction.TYPING)

    # In-place status updater: keeps at most 1 status message that edits in-place and clears when done
    tracker = InPlaceStatusTracker(chat)

    try:
        result = await Dispatcher.process_user_input(
            user_text=user_text,
            sender_jid=sender_id,
            status_updater=tracker.updater_callback()
        )

        # Clear intermediate status message before sending final reply
        await tracker.clear()

        await _send_result_payload(chat, result, sender_id)

    except Exception as e:
        logger.error(f"Error processing Telegram request: {e}", exc_info=True)
        await send_safe_message(chat, f"❌ Error: {str(e)}")

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if not is_authorized(user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    voice = update.message.voice
    logger.info(f"Received voice note from @{user.username or user.id} ({voice.duration}s)")

    # Send typing / recording voice indicator
    await chat.send_action(action=constants.ChatAction.RECORD_VOICE)
    status_msg = await chat.send_message("🎙️ _Transcribing voice note with Whisper..._", parse_mode=constants.ParseMode.MARKDOWN)

    temp_path = AUDIO_DIR / f"telegram_voice_{update.message.message_id}.ogg"
    try:
        # Download voice file
        voice_file = await context.bot.get_file(voice.file_id)
        await voice_file.download_to_drive(custom_path=str(temp_path))

        # Transcribe with Faster-Whisper asynchronously in worker thread
        text_content = await asyncio.to_thread(VoiceTranscriber.transcribe, str(temp_path))
        if not text_content:
            await status_msg.edit_text("⚠️ Could not hear any speech in that voice note.")
            return

        # Echo transcription
        await status_msg.edit_text(f"🗣️ *You said:* \"{text_content}\"", parse_mode=constants.ParseMode.MARKDOWN)

        # Dispatch transcribed message to the core pipeline
        sender_id = str(user.id)
        MemoryManager.save_message(
            sender_jid=sender_id,
            role="user",
            content=text_content,
            content_type="voice",
            audio_path=str(temp_path)
        )

        tracker = InPlaceStatusTracker(chat)

        result = await Dispatcher.process_user_input(
            user_text=text_content,
            sender_jid=sender_id,
            status_updater=tracker.updater_callback()
        )

        await tracker.clear()

        await _send_result_payload(chat, result, sender_id)

    except Exception as e:
        logger.error(f"Failed to process voice note: {e}", exc_info=True)
        await send_safe_message(chat, f"❌ Voice note processing error: {str(e)}")
    finally:
        # Clean up temporary voice audio file
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass

async def set_bot_commands(application: Application):
    """Registers standard bot commands with Telegram for autocomplete menu."""
    commands = [
        BotCommand("help", "Show all available commands & capabilities"),
        BotCommand("projects", "List available code repositories"),
        BotCommand("cd", "Switch active workspace project"),
        BotCommand("new", "Start fresh session (reset working memory)"),
        BotCommand("session", "View active session info & duration"),
        BotCommand("memory", "View working memory, summaries & facts"),
        BotCommand("remember", "Save a permanent technical fact"),
        BotCommand("forget", "Delete a saved fact"),
        BotCommand("status", "System resource health & diagnostics"),
        BotCommand("ping", "Check bot & model latency"),
        BotCommand("debug", "Advanced diagnostics & log inspection"),
    ]
    try:
        await application.bot.set_my_commands(commands)
    except Exception as e:
        logger.warning(f"Could not register Telegram bot menu commands: {e}")

def create_telegram_app() -> Application:
    """Builds and configures the Telegram Application with all handlers."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set. Please set it in your .env file.")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).post_init(set_bot_commands).build()

    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("commands", help_command))
    app.add_handler(CommandHandler("projects", projects_command))
    app.add_handler(CommandHandler("ls", projects_command))
    app.add_handler(CommandHandler("cd", cd_command))
    app.add_handler(CommandHandler("new", new_command))
    app.add_handler(CommandHandler("reset", new_command))
    app.add_handler(CommandHandler("session", session_command))
    app.add_handler(CommandHandler("memory", memory_command))
    app.add_handler(CommandHandler("remember", remember_command))
    app.add_handler(CommandHandler("forget", forget_command))
    app.add_handler(CommandHandler("status", handle_text_message))
    app.add_handler(CommandHandler("sysinfo", handle_text_message))
    app.add_handler(CommandHandler("ping", handle_text_message))
    app.add_handler(CommandHandler("debug", handle_text_message))

    # Messages
    app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    return app
