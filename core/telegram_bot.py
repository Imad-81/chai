import os
import sys
import asyncio
from pathlib import Path
from typing import Optional

from telegram import Update, constants
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_ALLOWED_USERS,
    DATA_DIR,
    AUDIO_DIR
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
        "📖 *Chai Command Reference*\n\n"
        "• `/projects` — List available code repositories\n"
        "• `/cd <project>` — Switch active workspace repository\n"
        "• `/status` or `/sysinfo` — View CPU, RAM, disk, and model status\n"
        "• `/ping` — Measure round-trip bot & Ollama latency\n"
        "• `/debug logs [N]` — View recent system logs\n"
        "• `/debug memory` — View database & conversation turn history\n"
        "• `/debug agy` — View Antigravity CLI status & active tasks\n"
        "• `/debug agy kill` — Kill running Antigravity task\n"
        "• `/debug mode [on|off]` — Toggle response execution timing footers\n"
        "• `/help` — Show this message"
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

    # Status updater callback for progress pings
    def status_updater(msg: str):
        asyncio.create_task(send_safe_message(chat, msg))

    try:
        result = await Dispatcher.process_user_input(
            user_text=user_text,
            sender_jid=sender_id,
            status_updater=status_updater
        )

        res_type = result.get("type", "text")
        if res_type == "text":
            reply_text = result.get("text", "")
            MemoryManager.save_message(
                sender_jid=sender_id,
                role="assistant",
                content=reply_text,
                content_type="text"
            )
            await send_safe_message(chat, reply_text)

        elif res_type == "file":
            file_path = result.get("filePath")
            file_name = result.get("fileName")
            caption = result.get("caption", "")
            MemoryManager.save_message(
                sender_jid=sender_id,
                role="assistant",
                content=f"[Sent PDF: {file_name}] {caption}",
                content_type="pdf"
            )
            if file_path and Path(file_path).exists():
                await chat.send_action(action=constants.ChatAction.UPLOAD_DOCUMENT)
                with open(file_path, "rb") as f:
                    await chat.send_document(
                        document=f,
                        filename=file_name,
                        caption=caption,
                        parse_mode=constants.ParseMode.MARKDOWN
                    )
            else:
                await send_safe_message(chat, f"⚠️ Document compiled but file was not found at `{file_path}`")

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

        # Transcribe with Faster-Whisper
        text_content = VoiceTranscriber.transcribe(str(temp_path))
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

        def status_updater(msg: str):
            asyncio.create_task(send_safe_message(chat, msg))

        result = await Dispatcher.process_user_input(
            user_text=text_content,
            sender_jid=sender_id,
            status_updater=status_updater
        )

        res_type = result.get("type", "text")
        if res_type == "text":
            reply_text = result.get("text", "")
            MemoryManager.save_message(
                sender_jid=sender_id,
                role="assistant",
                content=reply_text,
                content_type="text"
            )
            await send_safe_message(chat, reply_text)
        elif res_type == "file":
            file_path = result.get("filePath")
            file_name = result.get("fileName")
            caption = result.get("caption", "")
            if file_path and Path(file_path).exists():
                await chat.send_action(action=constants.ChatAction.UPLOAD_DOCUMENT)
                with open(file_path, "rb") as f:
                    await chat.send_document(
                        document=f,
                        filename=file_name,
                        caption=caption,
                        parse_mode=constants.ParseMode.MARKDOWN
                    )

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

def create_telegram_app() -> Application:
    """Builds and configures the Telegram Application with all handlers."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set. Please set it in your .env file.")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("projects", projects_command))
    app.add_handler(CommandHandler("ls", projects_command))
    app.add_handler(CommandHandler("cd", cd_command))
    app.add_handler(CommandHandler("status", handle_text_message))
    app.add_handler(CommandHandler("sysinfo", handle_text_message))
    app.add_handler(CommandHandler("ping", handle_text_message))
    app.add_handler(CommandHandler("debug", handle_text_message))

    # Messages
    app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    return app
