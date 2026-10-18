# Chai ☕

An autonomous personal AI Assistant for Linux powered by the **Telegram Bot API**, local LLMs (**Ollama**), and the **Antigravity CLI (`agy`)**.

Chai allows you to manage software repositories, run agentic coding tasks via Antigravity, generate professional styled PDF reports, query local git histories, and converse with local LLMs—all from your phone or desktop via Telegram voice notes or text messages.

---

## 🌟 Key Capabilities

- 🤖 **Native Telegram Bot**: Pure Python asynchronous client (`python-telegram-bot` v21+) operating via long-polling. Requires **no open ports**, no port forwarding, no webhooks, no QR code scans, and experiences zero session desynchronization.
- ⚡ **Multi-Tier Fast Triage Engine**:
  - **Tier 0 (< 0.1ms)**: Deterministic regex and rule-based fast-path for instant chit-chat greetings, workspace switching, direct git inspection, code action triggers, and PDF assignment workflows.
  - **Tier 1 (< 150ms)**: Ultra-fast micro-classifier powered by a lightweight local model (`qwen2.5:0.5b`) to categorize ambiguous requests.
  - **Tier 2 / Default**: Grounded single-pass conversational chat via the primary dispatcher model (`gemma4:12b` or custom model).
- 🧠 **Smart Hierarchical Memory Management**:
  - **Active Working Memory**: Maintains recent conversational turns within the active session.
  - **Episodic Sessions**: Automatically tracks sessions, sealing them upon configurable inactivity timeouts (`MEMORY_SESSION_TIMEOUT_MINUTES`, default 30 min) or workspace switches, and generating structured episodic summaries.
  - **Durable Long-Term Facts**: Manually save technical preferences and persistent facts using `/remember <fact>` and prune them with `/forget <id|keyword>`. Relevant facts are automatically injected into the developer prompt when working in that workspace.
- 🎯 **Dedicated Memory & Context Agent (`MemoryAgent`)**:
  - Employs a dedicated local micro-agent (`qwen2.5:0.5b`) to resolve conversational follow-ups and ambiguous pronouns (*"fix it"*, *"why did that happen?"*, *"retry the error"*, *"same thing"*) against working memory in under 150ms before delegating to Antigravity or the LLM.
- 🔍 **Instant Git & Repo Inspector (`RepoInspector`)**:
  - Zero-overhead (< 10ms) local git inspector that resolves natural language repository mentions (e.g. *"what was the last commit on chai?"*, *"show git status"*, *"list my repos"*).
  - Fetches branches, commit logs, uncommitted changes, remotes, and detects repository tech stacks directly without model hallucinations.
- 💻 **Antigravity CLI (`agy`) Runner & Interactive Screen Sessions**:
  - Dispatches tasks directly to Google Antigravity (`agy`) in the active workspace.
  - **Autonomous Task Synthesizer**: Converts informal Telegram voice notes and conversational requests into crisp, structured engineering specifications with goals, scope, and safety constraints before dispatching to Antigravity.
  - **Live Visible Terminal**: When running on a graphical Linux desktop (`DISPLAY` or `WAYLAND_DISPLAY`), Chai can spawn a visible terminal emulator (e.g. `gnome-terminal`, `xterm`) running `agy` in native interactive TUI mode (`AGY_UI_MODE=interactive`), allowing you to observe and interact with the agent in real time on your screen.
  - **Headless Fallback**: Automatically streams output to logs with task tracking and kill controls (`/debug agy kill`) when running in headless environments.
- 💬 **In-Place Status Updates**:
  - Uses an intelligent single-message tracker (`InPlaceStatusTracker`) on Telegram that edits a single status message in-place and cleans it up upon completion, eliminating notification sound spam and chat bubble clutter.
- 🎙️ **Local Voice Transcription**:
  - Offline audio transcription for Telegram voice notes using `faster-whisper` (`base.en` or custom size) running on CPU or CUDA.
- 📄 **Automatic Document Detection & Telegram Delivery (`FileDetector`)**:
  - Whenever Antigravity creates or modifies `.pdf` or `.docx` files during an execution (e.g. exporting reports, compiling documentation, converting markdown), Chai automatically detects the new or modified files, captures referenced paths from Antigravity's response, and uploads the actual files directly to Telegram.
  - Supports instant document retrieval (e.g. *"send me the pdf"*, *"return me the docx"*, *"send report.pdf"*) in < 0.1ms via Tier-0 fast-path without invoking LLM models.
- 📄 **Styled PDF Document Compiler**:
  - Compiles academic essays, technical reports, and assignment summaries into formatted PDFs using ReportLab (custom palettes, running headers, pagination, styled code/tables) and uploads them directly to Telegram.
- 🛠️ **In-Chat Diagnostics & Observability**:
  - Real-time diagnostic suite with `/status`, `/sysinfo`, `/ping`, `/debug logs [N]`, `/debug memory`, `/debug agy`, and execution timing toggles (`/debug mode on|off`).
- 🔬 **Offline Component Test Suite**:
  - Built-in validation script (`scripts/test_pipeline.py`) that tests all 7 internal subsystems (Database, Ollama, Whisper, PDF Compiler, Antigravity CLI, Telegram API, DebugRouter) without requiring external triggers.

---

## 🏗️ System Architecture

```
                    Telegram Cloud (Mobile / Desktop Clients)
                                       │
                                       ▼ Long Polling (HTTPS - No open ports)
               ┌─────────────────────────────────────────────────────────┐
               │              Chai Assistant (main.py)                   │
               │            python-telegram-bot + aiohttp                │
               └───────────┬─────────────────────────────────┬───────────┘
                           │                                 │
                           ▼                                 ▼
              ┌──────────────────────────┐     ┌──────────────────────────┐
              │    Fast Triage Engine    │     │   DebugRouter & System   │
              │ Tier 0: Regex (<0.1ms)   │     │ (/status, /ping, /debug, │
              │ Tier 1: Micro-Classifier │     │  /projects, /cd, /mode)  │
              └────────────┬─────────────┘     └──────────────────────────┘
                           │
       ┌───────────────────┼────────────────────────┐
       ▼                   ▼                        ▼
┌──────────────┐  ┌───────────────────┐  ┌──────────────────────┐
│ Voice Notes  │  │   ContextEngine   │  │   Smart Memory       │
│ faster-      │  │  & RepoInspector  │  │ • Working Memory     │
│ whisper ASR  │  │ (Local Git & Persona)│ • Episodic Sessions  │
└──────┬───────┘  └────────┬──────────┘  │ • Durable Facts      │
       │                   │             │ • MemoryAgent (0.5B) │
       │                   │             └──────────┬───────────┘
       └──────────────┐    │                        │
                      ▼    ▼                        ▼
               ┌─────────────────────────────────────────┐
               │            Dispatcher Router            │
               └───────────┬─────────────────┬───────────┘
                           │                 │
            ┌──────────────┴──────┐   ┌──────┴──────────────────────┐
            │   Ollama Local LLM  │   │     Antigravity Runner      │
            │  (gemma4:12b /      │   │         (`agy` CLI)         │
            │   qwen2.5:0.5b)     │   │  • Visible Interactive TUI  │
            └──────────────┬──────┘   │  • Headless Subprocess      │
                           │          └─────────────────────────────┘
                           ▼
            ┌─────────────────────────────┐
            │     ReportLab Compiler      │
            │  (Styled Assignment PDFs)   │
            └─────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Prerequisites

- **Linux OS** (Ubuntu, Debian, Fedora, Arch, etc.)
- **Python 3.10+**
- **[Ollama](https://ollama.com/)** running locally:
  ```bash
  ollama serve
  ```
  Pull the primary assistant model and the lightweight triage/memory resolver model:
  ```bash
  ollama pull gemma4:12b
  ollama pull qwen2.5:0.5b
  ```
- **[Antigravity CLI (`agy`)](https://github.com/google/antigravity)** installed and accessible in your `PATH` or configured via `AGY_BINARY`.
- *(Optional for visible TUI)*: A graphical desktop session (`gnome-terminal`, `xterm`, etc.).

### 2. Clone and Setup Environment

```bash
git clone git@github.com:Imad-81/chai.git
cd chai

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Create your Telegram Bot (1 minute)

1. Open Telegram and search for [@BotFather](https://t.me/BotFather).
2. Send `/newbot`, choose a friendly display name (e.g. `My Chai Assistant`) and a unique bot username (e.g. `my_chai_assistant_bot`).
3. Copy the HTTP API bot token provided by BotFather.
4. *(Recommended)* Find your numeric Telegram User ID using [@userinfobot](https://t.me/userinfobot) to restrict the bot exclusively to yourself.

### 4. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` and set your configuration:

```env
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
# Restrict bot to your Telegram user ID:
TELEGRAM_ALLOWED_USERS=123456789

# Ollama & Models
OLLAMA_HOST=http://127.0.0.1:11434
DISPATCHER_MODEL=gemma4:12b
MEMORY_RESOLVER_MODEL=qwen2.5:0.5b
MEMORY_SESSION_TIMEOUT_MINUTES=30
MEMORY_AUTO_SUMMARIZE=true

# Whisper Voice Transcription
WHISPER_MODEL_SIZE=base.en
WHISPER_DEVICE=cpu

# Antigravity CLI & Projects
AGY_BINARY=/home/imad/.local/bin/agy
AGY_SPAWN_TERMINAL=true
AGY_TERMINAL_EMULATOR=gnome-terminal
AGY_UI_MODE=interactive
PROJECTS_ROOT=/home/imad/projects

# Diagnostics & Webhook Port
PYTHON_WEBHOOK_PORT=5055
DEBUG_MODE=false
```

### 5. Run Offline Diagnostics & Verification

Validate your setup against all subsystems before starting the daemon:

```bash
python3 scripts/test_pipeline.py
```

Expected output:
```text
============================================================
🔬 CHAI ASSISTANT SYSTEM DIAGNOSTICS & TEST SUITE
============================================================
1. Testing SQLite Database & State...    [PASS]
2. Testing Ollama & Local Model...        [PASS]
3. Testing Whisper Speech-to-Text Engine... [PASS]
4. Testing PDF Compilation Engine...      [PASS]
5. Testing Antigravity CLI...             [PASS]
6. Testing Telegram Bot Interface...      [PASS]
7. Testing DebugRouter In-Chat Suite...   [PASS]
============================================================
Completed 7 diagnostic checks: 7/7 successful.
```

### 6. Start Chai

```bash
./run.sh
```

Or directly via Python:

```bash
python3 main.py
```

Open Telegram, search for your bot, send `/start`, and begin chatting or sending voice memos!

---

## 🛠️ In-Chat Commands Reference

| Category | Command | Description |
| :--- | :--- | :--- |
| **Workspaces** | `/projects` or `/ls` | List all discovered projects in `PROJECTS_ROOT` with detected tech stacks |
| | `/cd <project>` | Switch active workspace repository |
| **Memory & Sessions** | `/new` or `/reset` | Seal active session with summary & reset working memory for a fresh task |
| | `/session` | View active session ID, workspace, turn count, age, and idle countdown |
| | `/memory` | Inspect working memory turns, recent episodic summaries, and durable facts |
| | `/remember <fact>` | Persist a permanent technical preference or durable fact (e.g. `/remember Uses Python 3.12`) |
| | `/forget <id\|word>` | Delete a saved fact by ID or keyword search |
| **System & Health** | `/status` or `/sysinfo` | System overview: CPU, RAM, Disk, active workspace, Ollama, Antigravity status |
| | `/ping` | Test end-to-end bot responsiveness & Ollama round-trip inference latency |
| | `/debug logs [N]` | Tail the latest `N` lines of system logs (default: 20) |
| | `/debug memory` | Deep database record counts and session inspection |
| | `/debug agy` | Inspect Antigravity runner status, active PID, duration, and last task |
| | `/debug agy kill` | Immediately terminate a running Antigravity CLI task |
| | `/debug mode [on\|off]` | Toggle verbose execution timing and intent classification footers |
| **General** | `/start` | Display welcome banner and quick capabilities |
| | `/help` or `/commands` | Display complete in-chat command reference |

---

## 💡 Usage Scenarios & Natural Language Examples

### 1. Autonomous Coding with Antigravity
Chai detects coding, debugging, refactoring, and terminal intents and dispatches them to `agy` inside the active workspace:
- *"Fix the broken test in tests/test_memory.py"*
- *"Run pytest and resolve any failures"*
- *"Add docstrings and type hints to core/dispatcher.py"*
- If `AGY_SPAWN_TERMINAL=true` and a desktop display is active, a terminal window opens on your screen rendering `agy`'s interactive TUI, allowing you to watch the agent analyze files and run commands live.

### 2. Zero-Hallucination Git & Project Inspection
Ask about any local repository in natural language; Chai's `RepoInspector` intercepts the request and queries Git directly:
- *"What was the last commit on chai?"*
- *"Show git status for the current repo"*
- *"List recent commits on my frontend project"*
- *"What are my repos?"*

### 3. Smart Follow-ups & Pronoun Resolution
The dedicated `MemoryAgent` links conversational pronouns and references across turns:
- **User**: *"Run the test suite."*
- **Chai**: *"Ran 12 tests, 1 failed in test_auth.py: line 42 assertion error."*
- **User**: *"Fix it."* ➔ Resolved to: *"Fix the failed test in test_auth.py: line 42 assertion error"*
- **User**: *"Why did that happen?"* ➔ Resolved to context of the test failure.

### 4. Hands-Free Voice Notes
Send a voice memo from your mobile Telegram app while away from your desk:
1. Chai downloads the voice note and transcribes it locally using Faster-Whisper.
2. The transcription is echoed back (*"You said: 'Switch to chai and check git status'"*).
3. The command is routed and executed automatically.

### 5. Styled Academic & Technical PDFs
Ask Chai to write or revise academic assignments, research reports, or essays:
- *"Write an assignment on Raft Consensus Algorithm with architecture, state transitions, and leader election"*
- *"Revise the assignment to include a comparison table with Paxos"*
- Chai generates a structured, multi-section document, compiles it using ReportLab, and sends the `.pdf` directly to your Telegram chat.

---

## 📂 Project Structure

```
chai/
├── config.py                  # Central configuration & environment variables
├── main.py                    # Unified Telegram bot daemon & diagnostic webserver
├── requirements.txt           # Python dependencies
├── run.sh                     # Cleanup & launch script
├── .env.example               # Template environment configuration
├── core/
│   ├── agy_runner.py          # Antigravity CLI execution (Interactive TUI / Headless)
│   ├── context_engine.py      # Grounded developer persona & dynamic prompt synthesis
│   ├── db.py                  # SQLModel database models (Messages, Sessions, Facts, Docs)
│   ├── debug_router.py        # In-chat diagnostic suite (/status, /ping, /debug, etc.)
│   ├── dispatcher.py          # Intent routing & execution pipeline orchestrator
│   ├── logger.py              # Centralized rotating file & console logging
│   ├── memory.py              # Hierarchical memory manager (Working, Episodic, Durable)
│   ├── memory_agent.py        # Micro-agent (Qwen 0.5B) for pronoun resolution & summarization
│   ├── pdf_compiler.py        # ReportLab styled PDF report generator
│   ├── repo_inspector.py      # Zero-overhead local git & workspace inspector
│   ├── telegram_bot.py        # Telegram client, in-place status tracker, command handlers
│   ├── transcriber.py         # Faster-Whisper offline voice-to-text pipeline
│   ├── triage.py              # Multi-tier low-latency intent classifier (Tier 0 & Tier 1)
│   └── workspace_manager.py   # Workspace context tracking & project discovery
├── data/                      # Local sqlite db, artifacts, voice notes, logs (gitignored)
│   ├── assistant.db           # SQLite database
│   ├── artifacts/             # Generated PDF documents
│   ├── audio_temp/            # Temporary voice note storage
│   └── logs/                  # Centralized chai.log & agy task execution runs
├── scripts/
│   └── test_pipeline.py       # Offline component validation suite (7 diagnostic checks)
└── archive/
    └── whatsapp_bridge/       # Preserved Node.js Baileys WhatsApp bridge (for reference)
```

---

## ⚙️ Configuration Reference

| Environment Variable | Default | Description |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | *None* | HTTP API Token obtained from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_ALLOWED_USERS` | *Empty* | Comma-separated list of allowed numeric Telegram user IDs (from [@userinfobot](https://t.me/userinfobot)) |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | URL of the local Ollama API server |
| `DISPATCHER_MODEL` | `gemma4:12b` | Primary Ollama LLM for general conversation and task synthesis |
| `MEMORY_RESOLVER_MODEL` | `qwen2.5:0.5b` | Lightweight Ollama model for rapid (<150ms) pronoun resolution & triage |
| `MEMORY_SESSION_TIMEOUT_MINUTES` | `30` | Minutes of user inactivity before an active session is auto-sealed and summarized |
| `MEMORY_AUTO_SUMMARIZE` | `true` | Enables background LLM generation of episodic session titles and summaries |
| `WHISPER_MODEL_SIZE` | `base.en` | Faster-Whisper model tag (`tiny.en`, `base.en`, `small.en`, `medium.en`) |
| `WHISPER_DEVICE` | `cpu` | Inference device for Whisper (`cpu` or `cuda`) |
| `AGY_BINARY` | `~/.local/bin/agy` | Absolute path to the Antigravity CLI executable |
| `AGY_SPAWN_TERMINAL` | `true` | Whether to launch a visible GUI terminal window on screen when a desktop display is available |
| `AGY_TERMINAL_EMULATOR` | `gnome-terminal`| Preferred terminal emulator (`gnome-terminal`, `xterm`, `x-terminal-emulator`) |
| `AGY_UI_MODE` | `interactive` | Antigravity UI mode: `interactive` (live TUI) or `headless` (subcommand output) |
| `PROJECTS_ROOT` | `~/projects` | Parent directory scanned for software projects and repositories |
| `PYTHON_WEBHOOK_PORT` | `5055` | Port for the local diagnostic HTTP health server |
| `DEBUG_MODE` | `false` | Enable verbose execution timing on responses by default |

---

## 📦 Preserved WhatsApp Bridge (Archive)

The original Node.js Baileys WhatsApp bridge that powered earlier versions of Chai is fully preserved in [`archive/whatsapp_bridge/`](file:///home/imad/projects/chai/archive/whatsapp_bridge/README.md). If you wish to inspect or run the WhatsApp gateway alongside the Python orchestrator:

1. `cd archive/whatsapp_bridge`
2. `npm install`
3. `node bridge.js`

See [`archive/whatsapp_bridge/README.md`](file:///home/imad/projects/chai/archive/whatsapp_bridge/README.md) for further technical details.

---

## 📄 License

MIT License. Built with ❤️ for local, private, and autonomous AI-assisted development.
