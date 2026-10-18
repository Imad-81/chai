import asyncio
import os
import signal
import sys
from pathlib import Path
from aiohttp import web
import httpx

from config import (
    BRIDGE_PORT, 
    PYTHON_WEBHOOK_PORT, 
    BRIDGE_URL, 
    BASE_DIR, 
    DATA_DIR
)
from core.db import init_db
from core.memory import MemoryManager
from core.transcriber import VoiceTranscriber
from core.dispatcher import Dispatcher

bridge_process = None

async def send_whatsapp_text(jid: str, text: str):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{BRIDGE_URL}/send-text", json={"jid": jid, "text": text})
    except Exception as e:
        print(f"[Main] Failed to send text to WhatsApp: {e}")

async def send_whatsapp_file(jid: str, file_path: str, file_name: str, caption: str = ""):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(
                f"{BRIDGE_URL}/send-file", 
                json={
                    "jid": jid, 
                    "filePath": file_path, 
                    "fileName": file_name, 
                    "caption": caption,
                    "mimetype": "application/pdf"
                }
            )
    except Exception as e:
        print(f"[Main] Failed to send file to WhatsApp: {e}")

async def handle_webhook(request: web.Request):
    try:
        payload = await request.json()
        event = payload.get("event")

        if event == "connected":
            my_jid = payload.get("myJid")
            print(f"🎉 [Orchestrator] WhatsApp is connected! Logged in as: {my_jid}")
            return web.json_response({"status": "ok"})

        if event == "qr_ready":
            print("📱 [Orchestrator] QR Code is ready to scan. Check terminal above.")
            return web.json_response({"status": "ok"})

        if event == "incoming_message":
            sender_jid = payload.get("senderJid")
            text_content = payload.get("textContent", "").strip()
            audio_path = payload.get("audioFilePath")
            content_type = "voice" if audio_path else "text"

            # Guard: ignore any echo of bot responses or system status prefixes
            if text_content.startswith(("🤖", "⏳", "⚠️", "🗣️", "🎙️", "✍️", "📁")):
                print(f"[Orchestrator] Ignoring echo of bot text: '{text_content[:40]}...'")
                return web.json_response({"status": "ignored_bot_echo"})

            # 1. Voice Note Transcription
            if audio_path:
                print(f"[Orchestrator] Received voice note at: {audio_path}")
                # Send immediate acknowledgment
                asyncio.create_task(send_whatsapp_text(sender_jid, "🎙️ Transcribing voice note..."))
                try:
                    text_content = VoiceTranscriber.transcribe(audio_path)
                    if not text_content:
                        await send_whatsapp_text(sender_jid, "⚠️ Could not hear any speech in that voice note.")
                        return web.json_response({"status": "empty_transcription"})
                    
                    # Echo back the transcription to user
                    await send_whatsapp_text(sender_jid, f"🗣️ *You said:* \"{text_content}\"")
                except Exception as e:
                    print(f"[Orchestrator] Transcription failed: {e}")
                    await send_whatsapp_text(sender_jid, f"❌ Transcription error: {str(e)}")
                    return web.json_response({"status": "transcription_error"})

            if not text_content:
                return web.json_response({"status": "empty"})

            print(f"[Orchestrator] Processing: '{text_content}'")
            MemoryManager.save_message(
                sender_jid=sender_jid,
                role="user",
                content=text_content,
                content_type=content_type,
                audio_path=audio_path
            )

            # Define status updater callback to ping progress on WhatsApp
            def update_status(status_msg: str):
                asyncio.create_task(send_whatsapp_text(sender_jid, status_msg))

            # 2. Dispatch to Local LLM & Antigravity
            async def run_pipeline():
                try:
                    result = await Dispatcher.process_user_input(
                        user_text=text_content,
                        sender_jid=sender_jid,
                        status_updater=update_status
                    )

                    res_type = result.get("type", "text")
                    if res_type == "text":
                        reply_text = result.get("text", "")
                        MemoryManager.save_message(
                            sender_jid=sender_jid,
                            role="assistant",
                            content=reply_text,
                            content_type="text"
                        )
                        await send_whatsapp_text(sender_jid, reply_text)

                    elif res_type == "file":
                        file_path = result.get("filePath")
                        file_name = result.get("fileName")
                        caption = result.get("caption", "")
                        MemoryManager.save_message(
                            sender_jid=sender_jid,
                            role="assistant",
                            content=f"[Sent PDF: {file_name}] {caption}",
                            content_type="pdf"
                        )
                        await send_whatsapp_file(
                            jid=sender_jid,
                            file_path=file_path,
                            file_name=file_name,
                            caption=caption
                        )
                except Exception as e:
                    print(f"[Orchestrator] Error processing request: {e}")
                    await send_whatsapp_text(sender_jid, f"❌ An error occurred: {str(e)}")

            # Run pipeline asynchronously so webhook returns quickly
            asyncio.create_task(run_pipeline())

            return web.json_response({"status": "queued"})

        return web.json_response({"status": "ignored"})
    except Exception as e:
        print(f"[Orchestrator] Webhook error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def start_bridge():
    global bridge_process
    bridge_dir = BASE_DIR / "bridge"
    print(f"[Orchestrator] Launching WhatsApp Baileys bridge from: {bridge_dir}")
    bridge_process = await asyncio.create_subprocess_exec(
        "node", "bridge.js",
        cwd=str(bridge_dir),
        stdout=None, # Inherit stdout so QR code prints in terminal
        stderr=None  # Inherit stderr
    )

def shutdown():
    global bridge_process
    print("\n[Orchestrator] Shutting down...")
    if bridge_process:
        try:
            bridge_process.kill()
        except Exception:
            pass
    os.system("fuser -k 5055/tcp 5056/tcp 2>/dev/null || true")
    sys.exit(0)

async def main():
    print("=" * 60)
    print("🤖 ANTIGRAVITY WHATSAPP ASSISTANT")
    print("=" * 60)
    
    # 1. Initialize SQLite Database
    init_db()
    print("✅ Database initialized (data/assistant.db)")

    # 2. Setup Webhook Server with reuse_address
    app = web.Application()
    app.router.add_post("/webhook", handle_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", PYTHON_WEBHOOK_PORT, reuse_address=True, reuse_port=True)
    await site.start()
    print(f"✅ Webhook server listening on http://127.0.0.1:{PYTHON_WEBHOOK_PORT}")

    # 3. Start WhatsApp Bridge
    await start_bridge()

    # Wait for bridge
    try:
        await bridge_process.wait()
    except asyncio.CancelledError:
        shutdown()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda s, f: shutdown())
    signal.signal(signal.SIGTERM, lambda s, f: shutdown())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        shutdown()
