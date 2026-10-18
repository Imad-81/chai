# Chai ☕

An autonomous WhatsApp AI Assistant powered by local LLMs (Ollama) and the **Antigravity CLI (`agy`)**.

Send voice memos or texts from your phone to manage your software projects, run commands via Antigravity, generate PDF summaries, and converse with local models.

---

## 🌟 Key Features

- **WhatsApp Baileys Bridge**: Fast, native Node.js microservice (`@whiskeysockets/baileys`) running locally on port `5056`.
- **Local LLM Dispatcher**: Powered by Ollama (`qwen2.5-coder:7b` or custom models) with intent routing and conversation memory.
- **Antigravity CLI (`agy`) Runner**: Run real Antigravity commands, inspect tasks, and manage project workspaces directly through WhatsApp chat.
- **Voice Transcription**: Local offline audio transcription for WhatsApp voice notes using `faster-whisper`.
- **PDF Artifact Generator**: Compile documents and assignment summaries on the fly with ReportLab and send them back to WhatsApp.
- **SQLite Persistence**: Stores chat history, task states, and active workspaces locally in `data/assistant.db`.
- **Privacy & Security**: All credentials, keys, and session files remain on your local machine and are strictly ignored by git.

---

## 🏗️ Architecture

```
                 WhatsApp Cloud (Mobile / Web)
                              │
                              ▼
            ┌───────────────────────────────────┐
            │   Baileys Node Bridge (:5056)     │
            │   (Session Auth, Message Queue)   │
            └─────────────────┬─────────────────┘
                              │ HTTP Webhook
                              ▼
            ┌───────────────────────────────────┐
            │   Python Orchestrator (:5055)     │
            │   (main.py / aiohttp server)      │
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
- Node.js 18+ & npm
- [Ollama](https://ollama.com/) running locally:
  ```bash
  ollama serve
  ollama run qwen2.5-coder:7b
  ```
- (Optional) [Antigravity CLI](https://github.com/google/antigravity) (`agy`) installed in your PATH.

### 2. Setup Bridge Dependencies
```bash
cd bridge
npm install
cd ..
```

### 3. Setup Python Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Configuration
Copy the environment template and customize if needed:
```bash
cp .env.example .env
```

### 5. Run the Assistant
```bash
./run.sh
```
On first launch, scan the QR code printed in the terminal using WhatsApp (**Linked Devices**). Once authenticated, the session is saved locally in `bridge/auth_info_baileys/`.

---

## 📂 Project Structure

```
chai/
├── bridge/
│   ├── bridge.js              # Baileys WhatsApp client microservice
│   ├── package.json           # Node.js dependencies
│   └── package-lock.json
├── core/
│   ├── agy_runner.py          # Antigravity CLI subprocess execution
│   ├── db.py                  # SQLModel database models & schema
│   ├── dispatcher.py          # Intent classification & Ollama integration
│   ├── memory.py              # Context & conversation memory management
│   ├── pdf_compiler.py        # PDF report generator
│   ├── transcriber.py         # Whisper voice-to-text pipeline
│   └── workspace_manager.py   # Workspace context tracking
├── data/                      # Local sqlite db, artifacts, voice notes (gitignored)
├── config.py                  # Centralized configuration
├── main.py                    # Orchestrator & Aiohttp webhook server
├── requirements.txt           # Python dependencies
├── run.sh                     # Automated start script
└── .gitignore                 # Excludes node_modules, credentials & data
```

---

## 🔒 Security Note

Never commit:
- `bridge/auth_info_baileys/` (contains WhatsApp cryptographic keys and ratchets)
- `data/assistant.db` or `data/message_store.json` (contains private chat logs)
- `.env` (contains sensitive environment variables)

All of these are excluded by `.gitignore`.
