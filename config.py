import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_DIR = DATA_DIR / "audio_temp"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

ARTIFACTS_DIR = DATA_DIR / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "chai.log"

DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() in ("true", "1", "yes")

# Database
DB_PATH = DATA_DIR / "assistant.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

# Network Ports
BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "5056"))
PYTHON_WEBHOOK_PORT = int(os.getenv("PYTHON_WEBHOOK_PORT", "5055"))
BRIDGE_URL = f"http://127.0.0.1:{BRIDGE_PORT}"

# Ollama & Models
# Challenge Architecture:
# - Lighter tasks (memory retrieval, pronoun resolution): qwen3.5:2b (or qwen3.5:4b if only 4b is available)
# - Heavier tasks (dispatcher chat, PDF writeup): qwen3.5:4b
# - Coding & tool execution: Google Antigravity (agy)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
DISPATCHER_MODEL = os.getenv("DISPATCHER_MODEL", "qwen3.5:4b")
MEMORY_RESOLVER_MODEL = os.getenv("MEMORY_RESOLVER_MODEL", "qwen3.5:4b")
TASK_SYNTHESIZER_MODEL = os.getenv("TASK_SYNTHESIZER_MODEL", "qwen3.5:4b")
MEMORY_SESSION_TIMEOUT_MINUTES = int(os.getenv("MEMORY_SESSION_TIMEOUT_MINUTES", "30"))
MEMORY_AUTO_SUMMARIZE = os.getenv("MEMORY_AUTO_SUMMARIZE", "true").lower() in ("true", "1", "yes")

# Whisper
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base.en")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")

# Antigravity CLI & UI Execution (Cross-Platform)
def resolve_agy_binary() -> str:
    env_bin = os.getenv("AGY_BINARY", "").strip()
    if env_bin and Path(env_bin).exists():
        return env_bin
    
    # 1. Check system PATH
    which_path = shutil.which("agy")
    if which_path:
        return which_path

    # 2. Check standard user directories across platforms
    home = Path.home()
    candidates = [
        home / ".gemini" / "bin" / "agy",
        home / ".local" / "bin" / "agy",
        home / "bin" / "agy",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
            
    return "agy"

AGY_BINARY = resolve_agy_binary()
# Default to false so all runs stream directly into the UI with no external terminal windows
AGY_SPAWN_TERMINAL = os.getenv("AGY_SPAWN_TERMINAL", "false").lower() in ("true", "1", "yes")
AGY_TERMINAL_EMULATOR = os.getenv("AGY_TERMINAL_EMULATOR", "")
AGY_UI_MODE = os.getenv("AGY_UI_MODE", "print").lower()
PROJECTS_ROOT = Path(os.getenv("PROJECTS_ROOT") or (Path.home() / "projects"))
DEFAULT_WORKSPACE = str(BASE_DIR)

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_ALLOWED_USERS = [
    int(uid.strip()) 
    for uid in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",") 
    if uid.strip().isdigit()
]

# Security: Allowed phone numbers (for archived WhatsApp bridge)
ALLOWED_PHONE_NUMBERS = [
    num.strip() 
    for num in os.getenv("ALLOWED_PHONE_NUMBERS", "").split(",") 
    if num.strip()
]
