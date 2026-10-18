#!/usr/bin/env python3
"""
Chai Offline Diagnostic & Component Test Suite
Verifies all 7 subsystems without requiring live Telegram interactions:
1. SQLite Database & State Management
2. Local Ollama LLM Connectivity & Model Verification
3. Whisper Speech-to-Text Engine
4. PDF Compilation Pipeline
5. Antigravity CLI Verification
6. Telegram Bot Interface
7. DebugRouter In-Chat Command Suite
"""

import sys
import time
import shutil
import asyncio
from pathlib import Path

# Ensure root dir is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import httpx
from config import (
    BASE_DIR, 
    DATA_DIR, 
    DATABASE_URL, 
    OLLAMA_HOST, 
    DISPATCHER_MODEL, 
    BRIDGE_URL, 
    AGY_BINARY,
    WHISPER_MODEL_SIZE,
    WHISPER_DEVICE
)
from core.db import init_db
from core.memory import MemoryManager
from core.pdf_compiler import PDFCompiler
from core.debug_router import DebugRouter
from core.agy_runner import AntigravityRunner
from core.logger import get_logger

logger = get_logger("diagnostics")

PASS = "\033[32m[PASS]\033[0m"
FAIL = "\033[31m[FAIL]\033[0m"
WARN = "\033[33m[WARN]\033[0m"

async def test_database() -> bool:
    print("\n1. Testing SQLite Database & State...")
    try:
        init_db()
        ws = MemoryManager.get_active_workspace()
        print(f"   {PASS} Database initialized successfully.")
        print(f"   {PASS} Active workspace retrieved: '{ws}'")
        return True
    except Exception as e:
        print(f"   {FAIL} Database error: {e}")
        return False

async def test_ollama() -> bool:
    print("\n2. Testing Ollama & Local Model...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            t0 = time.perf_counter()
            res = await client.get(f"{OLLAMA_HOST}/api/tags")
            latency = (time.perf_counter() - t0) * 1000
            if res.status_code != 200:
                print(f"   {FAIL} Ollama returned HTTP {res.status_code}")
                return False

            models = [m.get("name") for m in res.json().get("models", [])]
            print(f"   {PASS} Ollama host reached in {latency:.1f}ms ({len(models)} models available)")

            # Check if DISPATCHER_MODEL or compatible tag exists
            matching = [m for m in models if DISPATCHER_MODEL.split(":")[0] in m]
            if matching:
                print(f"   {PASS} Required model found: '{matching[0]}'")
            else:
                print(f"   {WARN} Model '{DISPATCHER_MODEL}' not explicitly found in: {models[:4]}")

            return True
    except Exception as e:
        print(f"   {FAIL} Ollama connection failed: {e}")
        return False

async def test_whisper() -> bool:
    print("\n3. Testing Whisper Speech-to-Text Engine...")
    try:
        from core.transcriber import VoiceTranscriber
        model = VoiceTranscriber.get_model()
        if model is not None:
            print(f"   {PASS} Faster-Whisper loaded successfully (Model: '{WHISPER_MODEL_SIZE}', Device: '{WHISPER_DEVICE}')")
            return True
        else:
            print(f"   {FAIL} Faster-Whisper returned None model instance")
            return False
    except Exception as e:
        print(f"   {FAIL} Faster-Whisper load error: {e}")
        return False

async def test_pdf_compiler() -> bool:
    print("\n4. Testing PDF Compilation Engine...")
    try:
        test_md = "# Diagnostic Test Report\n\nThis is a sample document rendered during system validation.\n\n- Key 1: Operating\n- Key 2: Validated"
        pdf_path = PDFCompiler.compile_markdown_to_pdf(
            title="Diagnostics Test",
            markdown_text=test_md,
            filename_prefix="diagnostic_test"
        )
        if Path(pdf_path).exists() and Path(pdf_path).stat().st_size > 0:
            size_kb = Path(pdf_path).stat().st_size / 1024
            print(f"   {PASS} PDF generated successfully: {Path(pdf_path).name} ({size_kb:.1f} KB)")
            # Clean up test artifact
            try:
                Path(pdf_path).unlink()
            except Exception:
                pass
            return True
        else:
            print(f"   {FAIL} Generated PDF file was empty or missing")
            return False
    except Exception as e:
        print(f"   {FAIL} PDF compilation failed: {e}")
        return False

async def test_antigravity_cli() -> bool:
    print("\n5. Testing Antigravity CLI...")
    agy_path = Path(AGY_BINARY)
    if not agy_path.exists():
        # Check in PATH
        resolved = shutil.which("agy")
        if resolved:
            agy_path = Path(resolved)

    if agy_path.exists():
        try:
            proc = await asyncio.create_subprocess_exec(
                str(agy_path), "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            version_str = stdout.decode("utf-8").strip() or stderr.decode("utf-8").strip()
            print(f"   {PASS} Antigravity CLI found at '{agy_path}': {version_str}")
            return True
        except Exception as e:
            print(f"   {FAIL} Antigravity execution error: {e}")
            return False
    else:
        print(f"   {WARN} Antigravity binary not found at '{AGY_BINARY}'. CLI tasks will require binary in PATH.")
        return False

async def test_telegram_connectivity() -> bool:
    print("\n6. Testing Telegram Bot Interface...")
    from config import TELEGRAM_BOT_TOKEN
    if not TELEGRAM_BOT_TOKEN:
        print(f"   {WARN} TELEGRAM_BOT_TOKEN not configured in .env (Add token from @BotFather).")
        return True  # Normal before user configures their token

    try:
        from telegram import Bot
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        me = await bot.get_me()
        print(f"   {PASS} Telegram Bot verified: @{me.username} ({me.first_name}, ID: {me.id})")
        return True
    except Exception as e:
        print(f"   {FAIL} Telegram API connection error: {e}")
        return False

async def test_debug_router() -> bool:
    print("\n7. Testing DebugRouter In-Chat Suite...")
    commands = [
        "/debug ping",
        "/debug status",
        "/debug memory",
        "/debug agy",
        "/debug mode status"
    ]
    all_ok = True
    for cmd in commands:
        try:
            res = await DebugRouter.handle_debug_command(cmd, "123456789")
            if res and "text" in res and res["text"]:
                title = cmd.replace("/debug ", "").upper()
                print(f"   {PASS} Command `{cmd}` responded ({len(res['text'])} chars)")
            else:
                print(f"   {FAIL} Command `{cmd}` returned empty response")
                all_ok = False
        except Exception as e:
            print(f"   {FAIL} Command `{cmd}` crashed: {e}")
            all_ok = False
    return all_ok

async def main():
    print("=" * 60)
    print("🔬 CHAI ASSISTANT SYSTEM DIAGNOSTICS & TEST SUITE")
    print("=" * 60)

    results = []
    results.append(("Database", await test_database()))
    results.append(("Ollama LLM", await test_ollama()))
    results.append(("Whisper Engine", await test_whisper()))
    results.append(("PDF Compiler", await test_pdf_compiler()))
    results.append(("Antigravity CLI", await test_antigravity_cli()))
    results.append(("Telegram Bot", await test_telegram_connectivity()))
    results.append(("Debug Router", await test_debug_router()))

    print("\n" + "=" * 60)
    print("📊 DIAGNOSTIC RESULTS SUMMARY")
    print("=" * 60)
    for name, success in results:
        status_tag = PASS if success else (WARN if name == "Telegram Bot" else FAIL)
        print(f"• {name:<20} {status_tag}")

    passed_count = sum(1 for _, ok in results if ok)
    print(f"\nCompleted {len(results)} diagnostic checks: {passed_count}/{len(results)} successful.")

if __name__ == "__main__":
    asyncio.run(main())
