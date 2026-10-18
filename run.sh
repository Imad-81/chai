#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

# Kill any leftover processes from a previous run
echo "[run.sh] Cleaning up old processes..."
fuser -k 5055/tcp 2>/dev/null || true
fuser -k 5056/tcp 2>/dev/null || true
pkill -f "python3.*main.py" 2>/dev/null || true
pkill -f "node.*bridge.js" 2>/dev/null || true
sleep 1

if [ -f "$DIR/.venv/bin/activate" ]; then
    source "$DIR/.venv/bin/activate"
fi

exec python3 "$DIR/main.py" "$@"
