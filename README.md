# Chai ☕

An autonomous personal AI assistant and engineering cockpit for Linux and macOS, featuring a modern **ChatGPT/Claude-style Web UI & Mobile PWA (Chai-T)** alongside a native **Telegram Bot**, powered by local LLMs (**Ollama**), **Faster-Whisper STT**, and **Google Antigravity (`agy`)**.

Chai allows you to manage software repositories, dispatch agentic coding tasks with persistent session continuation, monitor real-time host telemetry, compile professional styled PDF reports, query local git histories with zero hallucinations, and converse via voice or text—from your desktop browser, mobile phone (over local Wi-Fi PWA), or Telegram.

---

## 🌟 Key Capabilities

### 💻 Chai-T Multi-Session Web Interface & Mobile PWA
- **Modern Responsive Web UI**: Built with Next.js 16, React 19, Lucide Icons, and vanilla CSS variables matching modern Claude / ChatGPT dark styling.
- **Progressive Web App (PWA)**: Includes an offline service worker and web manifest. Installable as a standalone app on iOS, Android, macOS, and Linux.
- **Mobile Access over Local Wi-Fi**: Automatically discovers your local LAN IP on launch. Open `http://<LOCAL_IP>:3000` on your phone to code and talk with Chai from anywhere on your home or office network.
- **Real-Time SSE Streaming**: Server-Sent Events (`/api/chat/stream`) stream live agent thoughts, tool execution statuses, and replies to the interface in real time.
- **In-Browser Voice Memos**: Tap the microphone button in the browser to record voice notes using the MediaRecorder API, with automatic offline transcription powered by local Faster-Whisper (`/api/audio/transcribe`).
- **Multi-Session Chat Management**: Create new chats, rename threads, delete conversations, auto-title sessions from initial prompts, and search conversation history.
- **Interactive Workspace Switcher Modal**: Browse discovered projects in `PROJECTS_ROOT`, inspect tech stacks, and switch active repositories with a single click.
- **Live Host Diagnostics & Telemetry Modal**: Live-polling dashboard showing CPU usage, RAM utilization, disk space, Ollama connectivity, active models, and Antigravity process status.
- **Rich Code & Document Cards**: GitHub Flavored Markdown (GFM) rendering with code syntax highlighting, one-click clipboard copy, and download cards for generated `.pdf` and `.docx` artifacts.

### 🤖 Native Telegram Bot (Remote & Headless)
- **Zero Open Ports**: Pure Python asynchronous client (`python-telegram-bot` v21+) operating via long-polling. No port forwarding, reverse proxies, webhooks, or public URLs required.
- **In-Place Status Updates (`InPlaceStatusTracker`)**: Progress indicators update a single Telegram status bubble in-place and clean it up upon completion, avoiding notification spam and chat clutter.
- **Offline Voice Notes**: Download and transcribe Telegram voice notes locally using `faster-whisper` (`base.en` or custom model size) on CPU or CUDA.
- **Autonomous Task Synthesizer**: Converts informal voice notes and casual messages into crisp, structured engineering specifications with goals, scope, and safety constraints.

### 💻 Antigravity CLI (`agy`) Runner & Session Continuer
- **Persistent Session Continuation**: Associates the Antigravity conversation UUID (`agy_conversation_id`) with each chat session in SQLite. When you ask follow-up coding questions, `agy` continues the active conversation thread rather than restarting from scratch.
- **Grounded Task Synthesis**: Synthesizes structured developer prompts without AI hallucinations.
- **Visible Interactive TUI**: When running on a graphical desktop (`DISPLAY` or `WAYLAND_DISPLAY`), Chai can spawn a visible terminal emulator (e.g. `gnome-terminal`, `xterm`) running `agy` in native interactive TUI mode (`AGY_UI_MODE=interactive`), allowing you to observe tool calls live.
- **Headless Fallback**: Streams output to centralized logs with real-time progress callbacks and emergency process kill controls (`/debug agy kill`).

### 📄 Automatic Document Detection & Delivery (`FileDetector`)
- **Automatic Document Capture**: When Antigravity or compiler tools generate or edit `.pdf` or `.docx` files, Chai snapshots the filesystem before and after execution, extracts file paths from the output text, and delivers the files.
- **Dual Delivery**: Uploads documents directly to Telegram as native file attachments and provides instant download cards in the Chai-T Web UI.
- **Instant Document Fetching**: Retrieve documents (*"send me the pdf"*, *"return me the docx"*, *"send report.pdf"*) in < 0.1ms via Tier-0 fast-path without invoking LLM inference.

### ⚡ Multi-Tier Ultra-Low-Latency Triage Engine
- **Tier 0 (< 0.1ms)**: Deterministic regex and rule-based fast-path for chit-chat greetings, workspace switching, git inspection, document downloads, and direct code actions.
- **Tier 1 (< 150ms)**: Ultra-fast micro-classifier powered by a lightweight local model (`qwen2.5:0.5b`) to categorize ambiguous requests.
- **Tier 2 / Conversational**: Grounded single-pass conversational chat via the primary dispatcher model (`gemma4:12b` or custom model).

### 🧠 Smart Hierarchical Memory Management
- **Active Working Memory**: Maintains recent conversational turns within the active session.
- **Episodic Sessions**: Automatically seals sessions upon configurable inactivity timeouts (`MEMORY_SESSION_TIMEOUT_MINUTES`, default 30 min) or workspace switches, generating structured episodic summaries.
- **Durable Long-Term Facts**: Persist technical preferences and facts using `/remember <fact>` and prune them with `/forget <id|keyword>`. Relevant facts are automatically injected into developer prompts.
- **Dedicated Memory & Context Agent (`MemoryAgent`)**: Employs a local micro-agent (`qwen2.5:0.5b`) to resolve conversational follow-ups and ambiguous pronouns (*"fix it"*, *"why did that happen?"*, *"retry the error"*) in under 150ms before delegating.

### 🔍 Instant Zero-Hallucination Git Inspector (`RepoInspector`)
- Zero-overhead (< 10ms) local git inspector that resolves natural language repository mentions (e.g. *"what was the last commit on chai?"*, *"show git status"*, *"list my repos"*).
- Fetches branches, commit logs, uncommitted changes, remotes, and detects tech stacks directly without model hallucinations.

### 📄 Styled PDF Document Compiler (`PDFCompiler`)
- Generates formatted academic essays, technical reports, and assignment summaries using ReportLab (custom palettes, running headers, pagination, styled code blocks and tables).

---

## 🏗️ System Architecture

```
                    ┌─────────────────────────────────────────┐
                    │      Clients & Interfaces               │
                    ├────────────────────┬────────────────────┤
                    │   Chai-T Web UI    │    Telegram App    │
                    │   & Mobile PWA     │  (Mobile & Desktop)│
                    │(http://<LAN>:3000) │                    │
                    └─────────┬──────────┴─────────┬──────────┘
                              │                    │
              HTTP / REST / SSE Rewrites           │ HTTPS Long Polling
                              │                    │ (No open ports)
                              ▼                    ▼
                    ┌─────────────────────────────────────────┐
                    │       Chai Core Backend (main.py)       │
                    │      aiohttp (0.0.0.0:5055) + PTB       │
                    └─────────────────────┬───────────────────┘
                                          │
            ┌─────────────────────────────┼─────────────────────────────┐
            ▼                             ▼                             ▼
┌──────────────────────────┐  ┌───────────────────────┐  ┌─────────────────────────┐
│    Fast Triage Engine    │  │     Web REST & SSE    │  │   DebugRouter & System  │
│ Tier 0: Regex (<0.1ms)   │  │   (/api/chat/stream,  │  │ (/status, /ping, /debug,│
│ Tier 1: Micro-Classifier │  │   /api/sessions, etc.)│  │  /projects, /cd, /mode) │
└───────────┬──────────────┘  └───────────┬───────────┘  └─────────────────────────┘
            │                             │
            ├─────────────────────────────┘
            ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                            Dispatcher Orchestrator                           │
└───────┬──────────────┬──────────────┬──────────────┬──────────────┬──────────┘
        │              │              │              │              │
        ▼              ▼              ▼              ▼              ▼
┌──────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────────┐
│    Voice     │ │   Smart    │ │    Repo    │ │   File     │ │   Context      │
│ Transcriber  │ │   Memory   │ │ Inspector  │ │  Detector  │ │    Engine      │
│   (Faster-   │ │ (Sessions, │ │ (Git logs, │ │ (PDF/DOCX  │ │  (Autonomous   │
│   Whisper)   │ │  Facts, Qwen)│ status)    │ │  delivery) │ │Task Synthesizer│
└──────────────┘ └────────────┘ └────────────┘ └────────────┘ └───────┬────────┘
                                                                      │
                               ┌──────────────────────────────────────┴────────┐
                               ▼                                               ▼
                ┌──────────────────────────────┐                ┌──────────────────────────────┐
                │       Ollama Local LLM       │                │      Antigravity Runner      │
                │ (gemma4:12b / qwen2.5:0.5b)  │                │          (`agy` CLI)         │
                └──────────────┬───────────────┘                │ • Session Continuation       │
                               │                                │ • Visible Interactive TUI    │
                               ▼                                │ • Headless Stream & Tracking │
                ┌──────────────────────────────┐                └──────────────────────────────┘
                │     ReportLab Compiler       │
                │   (Styled Academic PDFs)     │
                └──────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Prerequisites

- **OS**: Linux (Ubuntu, Debian, Fedora, Arch) or macOS
- **Python**: 3.10+
- **Node.js**: 18+ and npm (for the Next.js Chai-T Web UI)
- **[Ollama](https://ollama.com/)** running locally:
  ```bash
  ollama serve
  ```
  Pull the primary model and the micro triage/memory model:
  ```bash
  ollama pull gemma4:12b
  ollama pull qwen2.5:0.5b
  ```
- **[Antigravity CLI (`agy`)](https://github.com/google/antigravity)** installed and in your `PATH` (or configured via `AGY_BINARY`).
- *(Optional for Telegram)*: A bot token from [@BotFather](https://t.me/BotFather).

---

### 2. Clone and Setup Environment

```bash
git clone git@github.com:Imad-81/chai.git
cd chai

# 1. Setup Python virtual environment & backend dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Setup Web UI dependencies
cd web
npm install
cd ..
```

---

### 3. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` and adjust to your environment:

```env
# Telegram Bot Configuration (Optional if using Web UI exclusively)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
# Restrict bot to your Telegram user ID (from @userinfobot):
TELEGRAM_ALLOWED_USERS=123456789

# Network Ports
PYTHON_WEBHOOK_PORT=5055

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

# Diagnostics
DEBUG_MODE=false
```

---

### 4. Run Offline Diagnostics & Verification

Validate your local setup against all 7 subsystems:

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

---

### 5. Launch Chai

Run the unified start script:

```bash
./run.sh
```

Or run with Next.js development hot-reloading:

```bash
./run.sh --dev
```

Terminal output:
```text
===============================================================
☕ CHAI MULTI-SESSION AI PLATFORM (CHATGPT-STYLE PWA)
===============================================================
💻 Host Laptop:    http://localhost:3000
📱 Mobile (Wi-Fi): http://192.168.1.50:3000
⚙️ Backend Core:   http://127.0.0.1:5055
===============================================================
```

- **Desktop Browser**: Open [http://localhost:3000](http://localhost:3000)
- **Mobile Device**: Open `http://<YOUR_LOCAL_IP>:3000` while connected to the same Wi-Fi network. Tap **Add to Home Screen** to install as a standalone PWA.
- **Telegram**: Search for your bot username on Telegram and send `/start`.

---

## 🖥️ Chai-T Web UI Guide

| Feature | Description |
| :--- | :--- |
| **New Chat** | Click **+ New Chat** in the sidebar to start an isolated conversation thread. |
| **Session Continuation** | Consecutive coding prompts in the same chat session continue the existing Antigravity conversation thread without losing state. |
| **Workspace Modal** | Click the workspace button in the sidebar or top banner to view and switch between repositories found in `PROJECTS_ROOT`. |
| **Diagnostics Modal** | Click the activity icon or status pill to view real-time host telemetry (CPU %, RAM, disk, Ollama status, Antigravity PID). |
| **Voice Dictation** | Click the microphone button in the composer to record audio directly from your browser. Click again to stop; Whisper transcribes the audio into the input field automatically. |
| **Code Block Copy** | Code snippets rendered in markdown feature language tags and a 1-click clipboard copy button. |
| **File Downloads** | Generated `.pdf` and `.docx` files render as download cards with direct file download links (`/api/files/download?path=...`). |
| **Keyboard Shortcuts** | Press `Enter` to send; press `Shift + Enter` for a new line. |

---

## 🛠️ Telegram In-Chat Commands Reference

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

### 1. Interactive Coding with Antigravity
Chai detects coding, debugging, refactoring, and terminal intents and dispatches them to `agy` inside the active workspace:
- *"Fix the failing test in tests/test_memory.py"*
- *"Run pytest and resolve any failures"*
- *"Add docstrings and type annotations to core/dispatcher.py"*
- Follow-ups in the same session (e.g. *"Now add tests for the error cases"*) continue the active Antigravity conversation thread without resetting context.
- If `AGY_SPAWN_TERMINAL=true` and a desktop display is active, a terminal window opens on your screen rendering `agy`'s interactive TUI.

### 2. Automatic Document Delivery
Whenever Antigravity or the PDF compiler creates or updates documentation:
- *"Export the architecture diagram and documentation as a PDF"*
- *"Convert README.md into a styled docx"*
- Chai automatically detects the new `.pdf` or `.docx` file and delivers it:
  - **On Telegram**: Sent directly as a downloadable document attachment.
  - **On Web UI**: Rendered as an interactive download card.
- You can also request existing documents: *"Send me the latest report.pdf"* (<0.1ms retrieval).

### 3. Zero-Hallucination Git Inspection
Ask about any local repository in natural language; Chai's `RepoInspector` intercepts the request and queries Git directly:
- *"What was the last commit on chai?"*
- *"Show git status for the current repo"*
- *"List recent commits on my backend project"*
- *"What projects do I have?"*

### 4. Smart Follow-ups & Pronoun Resolution
The dedicated `MemoryAgent` links conversational pronouns and references across turns:
- **User**: *"Run the test suite."*
- **Chai**: *"Ran 14 tests, 1 failed in test_auth.py: line 42 assertion error."*
- **User**: *"Fix it."* ➔ Resolved to: *"Fix the failed test in test_auth.py: line 42 assertion error"*
- **User**: *"Why did that happen?"* ➔ Resolved to context of the test failure.

### 5. Hands-Free Voice Notes
Send a voice memo from your mobile Telegram app or tap the microphone in the Web UI:
1. Chai transcribes the audio locally using Faster-Whisper.
2. The transcription is displayed or echoed back.
3. The command is synthesized and executed automatically.

### 6. Styled Academic & Technical PDFs
Ask Chai to generate or revise structured academic reports:
- *"Write an assignment on the Raft Consensus Algorithm with architecture, state transitions, and leader election"*
- *"Revise the assignment to include a comparison table with Paxos"*
- Chai generates a multi-section document, compiles it using ReportLab, and sends the `.pdf` to your chat.

---

## 🔌 REST & SSE Web API Reference

The backend exposes an asynchronous REST and Server-Sent Events API on port `5055` (proxied by Next.js at `/api/chai/*`):

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Health check endpoint returning uptime and service states |
| `GET` | `/debug/state` | System telemetry JSON (CPU %, RAM, disk space, Ollama, Antigravity) |
| `GET` | `/debug/logs?n=50` | Stream recent plain-text log entries |
| `GET` | `/api/sessions` | List all conversation sessions ordered by last activity |
| `POST` | `/api/sessions` | Create a new conversation session (`{"title": "...", "workspace": "..."}`) |
| `GET` | `/api/sessions/{session_id}` | Retrieve session details and message history |
| `PATCH` | `/api/sessions/{session_id}` | Update session title, workspace, or Antigravity conversation UUID |
| `DELETE` | `/api/sessions/{session_id}` | Delete a conversation session and all its messages |
| `POST` | `/api/chat` | Send a message and receive the agent response (`{"text": "...", "session_id": "..."}`) |
| `GET` | `/api/chat/stream?session_id=...&text=...` | Server-Sent Events (SSE) streaming endpoint for real-time status and thoughts |
| `POST` | `/api/audio/transcribe` | Multipart audio file upload; transcribes speech using Faster-Whisper |
| `GET` | `/api/workspaces` | List discovered project directories and active workspace |
| `POST` | `/api/workspaces/select` | Switch active workspace repository (`{"workspace": "..."}`) |
| `GET` | `/api/files/download?path=...` | Download generated PDF reports and document artifacts |

---

## 📂 Project Structure

```
chai/
├── config.py                  # Central configuration & environment variables
├── main.py                    # Unified daemon: HTTP API, Web API, and Telegram bot
├── requirements.txt           # Python backend dependencies
├── run.sh                     # Unified startup script (LAN detection, backend & web UI)
├── .env.example               # Template environment configuration
├── core/
│   ├── agy_runner.py          # Antigravity CLI runner (interactive TUI / headless & continuation)
│   ├── context_engine.py      # Grounded developer persona & autonomous task synthesis
│   ├── db.py                  # SQLModel database models & SQLite WAL configuration
│   ├── debug_router.py        # Diagnostic suite (/status, /ping, /debug, etc.)
│   ├── dispatcher.py          # Intent routing & execution pipeline orchestrator
│   ├── file_detector.py       # Automatic .pdf/.docx detection, snapshotting & delivery
│   ├── logger.py              # Centralized rotating file and console logging
│   ├── memory.py              # Hierarchical memory manager (Working, Episodic, Durable)
│   ├── memory_agent.py        # Micro-agent (Qwen 0.5B) for pronoun resolution & summarization
│   ├── pdf_compiler.py        # ReportLab styled PDF report generator
│   ├── repo_inspector.py      # Zero-overhead local git & workspace inspector
│   ├── telegram_bot.py        # Telegram client, in-place status tracker, command handlers
│   ├── transcriber.py         # Faster-Whisper offline voice-to-text pipeline
│   ├── triage.py              # Multi-tier low-latency intent classifier (Tier 0 & Tier 1)
│   ├── web_api.py             # REST & SSE Web API routes for Chai-T Web UI
│   └── workspace_manager.py   # Workspace context tracking & project discovery
├── web/                       # Chai-T Next.js Web Interface & Mobile PWA
│   ├── app/                   # Next.js App Router (layout, page, global styling)
│   ├── components/            # React UI components:
│   │   ├── Composer.tsx       # Message input, keyboard shortcuts & voice recording
│   │   ├── MessageList.tsx    # Markdown rendering, code highlighting & copy buttons
│   │   ├── Sidebar.tsx        # Multi-session navigation, search & modals
│   │   ├── SystemModal.tsx    # Live host diagnostics & telemetry modal
│   │   └── WorkspaceModal.tsx # Project repository switcher modal
│   ├── public/                # PWA manifest, service worker (sw.js), icons & SVGs
│   ├── next.config.ts         # Next.js API rewrite proxy to Python backend (:5055)
│   ├── package.json           # Next.js, React 19, Lucide, remark-gfm dependencies
│   └── tsconfig.json          # TypeScript configuration
├── data/                      # Local SQLite database, artifacts, voice notes, logs (gitignored)
│   ├── assistant.db           # SQLite database
│   ├── artifacts/             # Generated PDF documents
│   ├── audio_temp/            # Temporary voice note storage
│   └── logs/                  # Centralized chai.log & agy execution outputs
├── scripts/
│   └── test_pipeline.py       # Offline component validation suite (7 diagnostic checks)
└── archive/
    └── whatsapp_bridge/       # Preserved Node.js Baileys WhatsApp bridge (for reference)
```

---

## ⚙️ Configuration Reference

| Environment Variable | Default | Description |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | *None* | HTTP API Token from [@BotFather](https://t.me/BotFather) (optional if using Web UI only) |
| `TELEGRAM_ALLOWED_USERS` | *Empty* | Comma-separated list of allowed numeric Telegram user IDs (from [@userinfobot](https://t.me/userinfobot)) |
| `PYTHON_WEBHOOK_PORT` | `5055` | Port for the local aiohttp REST & SSE backend API server |
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
| `DEBUG_MODE` | `false` | Enable verbose execution timing on responses by default |

---

## 📦 Preserved WhatsApp Bridge (Archive)

The original Node.js Baileys WhatsApp bridge that powered earlier versions of Chai is preserved in [`archive/whatsapp_bridge/`](archive/whatsapp_bridge/README.md). If you wish to inspect or run the WhatsApp gateway alongside the Python orchestrator:

1. `cd archive/whatsapp_bridge`
2. `npm install`
3. `node bridge.js`

See [`archive/whatsapp_bridge/README.md`](archive/whatsapp_bridge/README.md) for further technical details.

---

## 📄 License

MIT License. Built with ❤️ for local, private, and autonomous AI-assisted development.
