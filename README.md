# Chai ☕

An autonomous personal AI Assistant powered by **Telegram Bot API**, local LLMs (**Ollama**), and the **Antigravity CLI (`agy`)**.

Send voice memos or text messages from Telegram on your phone or desktop to manage your software projects, run commands via Antigravity, generate PDF summaries, and converse with local models.

---

## 🌟 Key Features

- **Native Telegram Bot**: Pure Python asynchronous client (`python-telegram-bot`) using long-polling. No open ports, no port forwarding, no QR scanning, and zero session ratcheting issues.
- **Local LLM Dispatcher**: Powered by Ollama (`qwen2.5-coder:7b` or custom models) with intent routing and conversation memory.
- **Antigravity CLI (`agy`) Runner**: Run real Antigravity commands, inspect tasks, and manage project workspaces directly through Telegram chat.
- **Voice Transcription**: Local offline audio transcription for Telegram voice notes using `faster-whisper`.
- **PDF Artifact Generator**: Compile documents and assignment summaries on the fly with ReportLab and send them directly to Telegram as documents.
- **SQLite Persistence**: Stores chat history, task states, and active workspaces locally in `data/assistant.db`.
- **In-Chat Diagnostics**: Built-in `/debug status`, `/ping`, `/debug logs`, and `/debug memory` commands.
- **Archived WhatsApp Bridge**: Original Node.js Baileys bridge is preserved in `archive/whatsapp_bridge/` for future reference.

---

## 🏗️ Architecture

```
                 Telegram Cloud (Mobile / Desktop)
                               │
                               ▼ Long Polling (No open ports required)
             ┌───────────────────────────────────┐
             │    Chai Assistant (main.py)       │
             │    python-telegram-bot + aiohttp  │
             └─────────┬──────────────┬──────────┘
                       │              │
         ┌─────────────┴──────┐ ┌─────┴────────────────┐
         │  Ollama Dispatcher │ │ Antigravity Runner   │
         │  & faster-whisper  │ │ (`agy` CLI tool)     │
         └────────────────────┘ └──────────────────────┘
```

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+
- [Ollama](https://ollama.com/) running locally:
  ```bash
  ollama serve
  ollama run qwen2.5-coder:7b
  ```
- (Optional) [Antigravity CLI](https://github.com/google/antigravity) (`agy`) installed in your PATH.

### 2. Setup Python Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Create your Telegram Bot (1 minute)
1. Open Telegram and search for [@BotFather](https://t.me/BotFather).
2. Send `/newbot`, choose a display name and username (e.g. `MyChaiAssistantBot`).
3. Copy the HTTP API token provided by BotFather.
4. Copy the environment template:
   ```bash
   cp .env.example .env
   ```
5. Edit `.env` and paste your token:
   ```env
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
   # (Optional) Restrict access to your Telegram user ID (from @userinfobot):
   TELEGRAM_ALLOWED_USERS=your_user_id
   ```

### 4. Run the Assistant
```bash
./run.sh
```
Open Telegram, search for your bot username, and send `/start` or a voice note!

---

## 🛠️ In-Chat Commands

| Command | Action |
| :--- | :--- |
| `/start` | Welcome message & capability overview |
| `/help` | Complete command reference |
| `/projects` or `/ls` | List available workspace repositories |
| `/cd <project>` | Switch active workspace repository |
| `/status` or `/sysinfo` | System health overview (CPU, RAM, Disk, Model) |
| `/ping` | Round-trip latency test with Ollama |
| `/debug logs [N]` | Tail recent system logs |
| `/debug memory` | Database record counts & recent conversation turns |
| `/debug agy` | Antigravity CLI status & active tasks |
| `/debug agy kill` | Terminate runaway Antigravity task |
| `/debug mode [on\|off]` | Toggle response execution timing footers |

---

## 📂 Project Structure

```
chai/
├── archive/
│   └── whatsapp_bridge/       # Preserved Node.js Baileys bridge
├── core/
│   ├── agy_runner.py          # Antigravity CLI subprocess execution
│   ├── db.py                  # SQLModel database models & schema
│   ├── debug_router.py        # In-chat diagnostic suite
│   ├── dispatcher.py          # Intent classification & Ollama integration
│   ├── logger.py              # Centralized rotating logging
│   ├── memory.py              # Context & conversation memory management
│   ├── pdf_compiler.py        # PDF report generator
│   ├── telegram_bot.py        # Telegram Bot integration
│   ├── transcriber.py         # Whisper voice-to-text pipeline
│   └── workspace_manager.py   # Workspace context tracking
├── data/                      # Local sqlite db, artifacts, voice notes (gitignored)
├── scripts/
│   └── test_pipeline.py       # Offline component validation suite
├── config.py                  # Centralized configuration
├── main.py                    # Unified Telegram & Diagnostics Orchestrator
├── requirements.txt           # Python dependencies
├── run.sh                     # Automated start script
└── .gitignore
```
