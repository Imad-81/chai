import os
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

# Database
DB_PATH = DATA_DIR / "assistant.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

# Network Ports
BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "5056"))
PYTHON_WEBHOOK_PORT = int(os.getenv("PYTHON_WEBHOOK_PORT", "5055"))
BRIDGE_URL = f"http://127.0.0.1:{BRIDGE_PORT}"

# Ollama & Models
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
DISPATCHER_MODEL = os.getenv("DISPATCHER_MODEL", "qwen2.5-coder:7b")

# Whisper
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base.en")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")

# Antigravity CLI
AGY_BINARY = os.getenv("AGY_BINARY", str(Path.home() / ".local" / "bin" / "agy"))
PROJECTS_ROOT = Path(os.getenv("PROJECTS_ROOT", str(Path.home() / "projects")))
DEFAULT_WORKSPACE = str(BASE_DIR)

# Security: Allowed phone numbers (optional extra check; bridge enforces self-JID)
ALLOWED_PHONE_NUMBERS = [
    num.strip() 
    for num in os.getenv("ALLOWED_PHONE_NUMBERS", "").split(",") 
    if num.strip()
]
