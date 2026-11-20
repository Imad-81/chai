#!/usr/bin/env python3
"""
Chai Universal Cross-Platform Launcher
Boots Chai backend and web UI, opens your default browser, and runs detached.
Zero terminal dependencies, works on Linux, macOS, and Windows.
"""

import os
import sys
import time
import socket
import shutil
import subprocess
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "chai.log"

def get_venv_python() -> str:
    """Finds Python in .venv across platforms."""
    candidates = [
        BASE_DIR / ".venv" / "bin" / "python3",
        BASE_DIR / ".venv" / "bin" / "python",
        BASE_DIR / ".venv" / "Scripts" / "python.exe",
        BASE_DIR / ".venv" / "Scripts" / "python",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return sys.executable

def clean_ports(ports=(3000, 5055, 5056)):
    """Cross-platform port cleaner using psutil."""
    try:
        import psutil
        for p in psutil.process_iter(['pid', 'name']):
            try:
                for conn in p.net_connections(kind='inet'):
                    if conn.laddr and conn.laddr.port in ports:
                        p.terminate()
            except Exception:
                pass
    except Exception:
        pass

def is_port_open(port: int, host="127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False

def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def main():
    print("=" * 60)
    print("☕ CHAI UNIVERSAL LAUNCHER")
    print("=" * 60)

    clean_ports()
    time.sleep(0.5)

    py_bin = get_venv_python()
    log_fp = open(LOG_FILE, "a", encoding="utf-8")

    spawn_kwargs = {}
    if sys.platform == "win32":
        spawn_kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        )
    else:
        spawn_kwargs["start_new_session"] = True

    # 1. Start Python Backend
    print("⚙️  Starting Chai Backend Core...")
    backend_proc = subprocess.Popen(
        [py_bin, str(BASE_DIR / "main.py")],
        cwd=str(BASE_DIR),
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        **spawn_kwargs
    )

    # Wait for backend
    for _ in range(30):
        if is_port_open(5055):
            print("✅ Backend ready on port 5055.")
            break
        time.sleep(0.3)
    else:
        print("⚠️ Backend took longer than expected to start; check data/logs/chai.log.")

    # 2. Check Next.js build & Start Web UI
    web_dir = BASE_DIR / "web"
    next_dist = web_dir / ".next"
    npm_bin = shutil.which("npm") or "npm"
    npx_bin = shutil.which("npx") or "npx"

    if not next_dist.exists():
        print("📦 Building Next.js production bundle (first time run)...")
        subprocess.run([npm_bin, "run", "build"], cwd=str(web_dir), check=True)

    print("🚀 Starting Chai Web UI Server...")
    web_proc = subprocess.Popen(
        [npx_bin, "next", "start", "-H", "0.0.0.0", "-p", "3000"],
        cwd=str(web_dir),
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        **spawn_kwargs
    )

    # Wait for Web UI
    for _ in range(35):
        if is_port_open(3000):
            print("✅ Web UI ready on port 3000.")
            break
        time.sleep(0.4)

    local_ip = get_local_ip()
    url = "http://localhost:3000"
    print("\n" + "=" * 60)
    print(f"💻 Desktop UI:      {url}")
    print(f"📱 Mobile / LAN:    http://{local_ip}:3000")
    print("🌐 Launching Chai in your browser...")
    print("=" * 60 + "\n")

    # Automatically launch in browser
    webbrowser.open(url)

    if "--foreground" in sys.argv:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down services...")
            backend_proc.terminate()
            web_proc.terminate()

if __name__ == "__main__":
    main()
