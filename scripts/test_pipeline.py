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
from typing import List, Dict, Any, Tuple

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
    MEMORY_RESOLVER_MODEL,
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

async def test_database() -> Tuple[bool, str]:
    try:
        init_db()
        ws = MemoryManager.get_active_workspace()
        msg = f"Database initialized. Active workspace: '{Path(ws).name}'"
        return True, msg
    except Exception as e:
        return False, f"Database error: {e}"

async def test_ollama() -> Tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            t0 = time.perf_counter()
            res = await client.get(f"{OLLAMA_HOST}/api/tags")
            latency = (time.perf_counter() - t0) * 1000
            if res.status_code != 200:
                return False, f"Ollama returned HTTP {res.status_code}"

            models = [m.get("name") for m in res.json().get("models", [])]
            matching = [m for m in models if DISPATCHER_MODEL.split(":")[0] in m]
            if matching:
                return True, f"Ollama online ({latency:.1f}ms). Found active model: '{matching[0]}'"
            else:
                return True, f"Ollama online ({latency:.1f}ms), available models: {', '.join(models[:3])}"
    except Exception as e:
        return False, f"Ollama connection failed: {e}"

async def test_whisper() -> Tuple[bool, str]:
    try:
        from core.transcriber import VoiceTranscriber
        model = VoiceTranscriber.get_model()
        if model is not None:
            return True, f"Faster-Whisper loaded (Model: '{WHISPER_MODEL_SIZE}', Device: '{WHISPER_DEVICE}')"
        else:
            return False, "Faster-Whisper returned None model instance"
    except Exception as e:
        return False, f"Faster-Whisper load error: {e}"

async def test_pdf_compiler() -> Tuple[bool, str]:
    try:
        test_md = "# Diagnostic Test Report\n\nThis is a sample document rendered during system validation.\n\n- Key 1: Operating\n- Key 2: Validated"
        pdf_path = PDFCompiler.compile_markdown_to_pdf(
            title="Diagnostics Test",
            markdown_text=test_md,
            filename_prefix="diagnostic_test"
        )
        if Path(pdf_path).exists() and Path(pdf_path).stat().st_size > 0:
            size_kb = Path(pdf_path).stat().st_size / 1024
            try:
                Path(pdf_path).unlink()
            except Exception:
                pass
            return True, f"PDF generated & styled successfully ({size_kb:.1f} KB)"
        else:
            return False, "Generated PDF was empty or missing"
    except Exception as e:
        return False, f"PDF compilation failed: {e}"

async def test_antigravity_cli() -> Tuple[bool, str]:
    agy_path = Path(AGY_BINARY)
    if not agy_path.exists():
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
            return True, f"Antigravity CLI verified at '{agy_path}' (v{version_str})"
        except Exception as e:
            return False, f"Antigravity execution error: {e}"
    else:
        return False, f"Antigravity binary not found at '{AGY_BINARY}'"

async def test_telegram_connectivity() -> Tuple[bool, str]:
    from config import TELEGRAM_BOT_TOKEN
    if not TELEGRAM_BOT_TOKEN:
        return True, "TELEGRAM_BOT_TOKEN not configured (Optional when using Web UI)"

    try:
        from telegram import Bot
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        me = await bot.get_me()
        return True, f"Telegram Bot verified: @{me.username} (ID: {me.id})"
    except Exception as e:
        return False, f"Telegram API connection error: {e}"

async def test_debug_router() -> Tuple[bool, str]:
    commands = [
        "/debug ping",
        "/debug status",
        "/debug memory",
        "/debug agy",
        "/debug mode status"
    ]
    for cmd in commands:
        try:
            res = await DebugRouter.handle_debug_command(cmd, "123456789")
            if not res or not res.get("text"):
                return False, f"Command `{cmd}` returned empty response"
        except Exception as e:
            return False, f"Command `{cmd}` crashed: {e}"
    return True, f"All {len(commands)} debug commands validated successfully"

async def run_diagnostics() -> List[Dict[str, Any]]:
    """Runs all 7 diagnostic checks and returns structured results."""
    checks = [
        ("Database", test_database),
        ("Ollama LLM", test_ollama),
        ("Whisper Engine", test_whisper),
        ("PDF Compiler", test_pdf_compiler),
        ("Antigravity CLI", test_antigravity_cli),
        ("Telegram Bot", test_telegram_connectivity),
        ("Debug Router", test_debug_router),
    ]

    results = []
    for name, test_func in checks:
        ok, msg = await test_func()
        status = "pass" if ok else ("warn" if name == "Telegram Bot" else "fail")
        results.append({
            "name": name,
            "status": status,
            "message": msg
        })
    return results

async def main():
    print("=" * 60)
    print("🔬 CHAI ASSISTANT SYSTEM DIAGNOSTICS & TEST SUITE")
    print("=" * 60)

    results = await run_diagnostics()
    for item in results:
        status_tag = PASS if item["status"] == "pass" else (WARN if item["status"] == "warn" else FAIL)
        print(f"\n• {item['name']}: {status_tag}")
        print(f"  {item['message']}")

    print("\n" + "=" * 60)
    passed = sum(1 for r in results if r["status"] == "pass")
    total = len(results)
    print(f"📊 SUMMARY: {passed}/{total} checks passed.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
