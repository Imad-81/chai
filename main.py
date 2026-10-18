import asyncio
import os
import signal
import sys
import time
import shutil
from pathlib import Path
from aiohttp import web
import httpx
import psutil

from config import (
    PYTHON_WEBHOOK_PORT, 
    BASE_DIR, 
    DATA_DIR,
    OLLAMA_HOST,
    DISPATCHER_MODEL,
    WHISPER_MODEL_SIZE,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_ALLOWED_USERS
)
from core.db import init_db
from core.memory import MemoryManager
from core.transcriber import VoiceTranscriber
from core.dispatcher import Dispatcher
from core.agy_runner import AntigravityRunner
from core.logger import get_logger, tail_logs
from core.telegram_bot import create_telegram_app

logger = get_logger("orchestrator")

_start_time = time.time()
_tg_app = None

async def handle_health(request: web.Request):
    """Simple REST health check endpoint."""
    return web.json_response({
        "status": "ok",
        "service": "chai-orchestrator",
        "uptimeSeconds": int(time.time() - _start_time),
        "telegramConfigured": bool(TELEGRAM_BOT_TOKEN),
        "telegramRunning": _tg_app is not None and _tg_app.updater is not None and _tg_app.updater.running,
        "port": PYTHON_WEBHOOK_PORT
    })

async def handle_debug_state(request: web.Request):
    """Detailed JSON diagnostic state endpoint."""
    cpu_pct = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    total, used, free = shutil.disk_usage(DATA_DIR)

    # Check Ollama
    ollama_info = {"status": "offline", "models": []}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(f"{OLLAMA_HOST}/api/tags")
            if res.status_code == 200:
                models = [m.get("name") for m in res.json().get("models", [])]
                ollama_info = {"status": "online", "models": models}
    except Exception:
        pass

    return web.json_response({
        "uptimeSeconds": int(time.time() - _start_time),
        "cpuPercent": cpu_pct,
        "ram": {
            "usedGb": round(mem.used / (1024 ** 3), 2),
            "totalGb": round(mem.total / (1024 ** 3), 2),
            "percent": mem.percent
        },
        "disk": {
            "freeGb": round(free / (1024 ** 3), 2),
            "totalGb": round(total / (1024 ** 3), 2)
        },
        "activeWorkspace": MemoryManager.get_active_workspace(),
        "ollama": ollama_info,
        "antigravity": AntigravityRunner.get_status(),
        "whisperModel": WHISPER_MODEL_SIZE,
        "telegram": {
            "configured": bool(TELEGRAM_BOT_TOKEN),
            "allowedUsers": TELEGRAM_ALLOWED_USERS
        }
    })

async def handle_debug_logs(request: web.Request):
    """Returns recent log lines as plain text."""
    count = 50
    try:
        count = int(request.query.get("n", 50))
    except ValueError:
        pass
    lines = tail_logs(count)
    return web.Response(text="".join(lines), content_type="text/plain")

async def handle_legacy_webhook(request: web.Request):
    """Legacy endpoint preserved for archived WhatsApp bridge."""
    try:
        payload = await request.json()
        event = payload.get("event")
        if event == "connected":
            logger.info(f"Archived WhatsApp bridge connected: {payload.get('myJid')}")
            return web.json_response({"status": "ok"})
        return web.json_response({"status": "received"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def shutdown():
    global _tg_app
    logger.info("Shutting down Chai Assistant...")
    if _tg_app and _tg_app.updater and _tg_app.updater.running:
        try:
            await _tg_app.updater.stop()
            await _tg_app.stop()
            await _tg_app.shutdown()
        except Exception as e:
            logger.warning(f"Error stopping Telegram app: {e}")
    sys.exit(0)

async def main():
    global _tg_app

    logger.info("=" * 60)
    logger.info("🤖 CHAI ASSISTANT (TELEGRAM EDITION)")
    logger.info("=" * 60)
    
    # 1. Initialize SQLite Database
    init_db()
    logger.info("Database initialized (data/assistant.db)")

    # 2. Setup Diagnostics HTTP Server
    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_get("/debug/state", handle_debug_state)
    app.router.add_get("/debug/logs", handle_debug_logs)
    app.router.add_post("/webhook", handle_legacy_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", PYTHON_WEBHOOK_PORT, reuse_address=True, reuse_port=True)
    await site.start()
    logger.info(f"Diagnostics server listening on http://127.0.0.1:{PYTHON_WEBHOOK_PORT}")

    # 3. Start Telegram Bot
    if TELEGRAM_BOT_TOKEN:
        try:
            _tg_app = create_telegram_app()
            await _tg_app.initialize()
            await _tg_app.start()
            await _tg_app.updater.start_polling()

            bot_info = await _tg_app.bot.get_me()
            logger.info("=" * 60)
            logger.info(f"✈️ TELEGRAM BOT CONNECTED: @{bot_info.username} ({bot_info.first_name})")
            logger.info(f"Open Telegram and search for @{bot_info.username} to chat!")
            logger.info("=" * 60)
        except Exception as e:
            logger.error(f"Failed to start Telegram Bot: {e}", exc_info=True)
    else:
        print("\n" + "=" * 60)
        print("⚠️  TELEGRAM BOT TOKEN NOT CONFIGURED")
        print("=" * 60)
        print("To connect your Telegram bot in under 1 minute:")
        print("1. Open Telegram on your phone or PC")
        print("2. Search for @BotFather and send /newbot")
        print("3. Choose a name and username (e.g. MyChaiAssistantBot)")
        print("4. Copy the API Token and add it to your .env file:")
        print("   TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ")
        print("5. (Optional) Restrict access to your Telegram user ID:")
        print("   TELEGRAM_ALLOWED_USERS=your_user_id (get it from @userinfobot)")
        print("6. Run ./run.sh again!")
        print("=" * 60 + "\n")

    # Keep server running until interrupt
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: stop_event.set())

    await stop_event.wait()
    await shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
