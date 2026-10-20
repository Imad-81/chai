#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

# 1. Kill any leftover processes from a previous run
echo "[run.sh] Cleaning up old processes on ports 3000, 5055, 5056..."
fuser -k 3000/tcp 2>/dev/null || true
fuser -k 5055/tcp 2>/dev/null || true
fuser -k 5056/tcp 2>/dev/null || true
pkill -f "python3.*main.py" 2>/dev/null || true
pkill -f "next-(server|dev)" 2>/dev/null || true
sleep 1

# 2. Activate Python virtual environment
if [ -f "$DIR/.venv/bin/activate" ]; then
    source "$DIR/.venv/bin/activate"
fi

# Detect Local IP for mobile PWA access
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$LOCAL_IP" ]; then
    LOCAL_IP="127.0.0.1"
fi

echo "==============================================================="
echo "☕ CHAI MULTI-SESSION AI PLATFORM (CHATGPT-STYLE PWA)"
echo "==============================================================="
echo "💻 Host Laptop:   http://localhost:3000"
echo "📱 Mobile (Wi-Fi): http://${LOCAL_IP}:3000"
echo "⚙️ Backend Core:  http://127.0.0.1:5055"
echo "==============================================================="

# Cleanup handler on exit
cleanup() {
    echo ""
    echo "[run.sh] Shutting down Chai services..."
    if [ -n "$PY_PID" ]; then kill -TERM "$PY_PID" 2>/dev/null || true; fi
    if [ -n "$WEB_PID" ]; then kill -TERM "$WEB_PID" 2>/dev/null || true; fi
    wait 2>/dev/null || true
    echo "[run.sh] Goodbye!"
}
trap cleanup EXIT INT TERM

# 3. Launch Python Core (Dispatcher, Antigravity, Whisper, SQLite)
python3 "$DIR/main.py" &
PY_PID=$!

# Wait briefly for backend port 5055 to become active
for i in {1..15}; do
    if curl -s http://127.0.0.1:5055/health >/dev/null 2>&1; then
        echo "✅ Python backend ready."
        break
    fi
    sleep 0.5
done

# 4. Launch Next.js Web UI Server (bound to 0.0.0.0 for LAN/PWA access)
cd "$DIR/web"

if [ "$1" == "--dev" ]; then
    echo "🚀 Starting Next.js in DEVELOPMENT mode..."
    npx next dev -H 0.0.0.0 -p 3000 &
    WEB_PID=$!
else
    # Build if .next doesn't exist
    if [ ! -d ".next" ]; then
        echo "📦 Building Next.js production bundle..."
        npm run build
    fi
    echo "🚀 Starting Next.js in PRODUCTION mode (0.0.0.0:3000)..."
    npx next start -H 0.0.0.0 -p 3000 &
    WEB_PID=$!
fi

# Wait on both services
wait
