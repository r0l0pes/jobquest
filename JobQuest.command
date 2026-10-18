#!/bin/bash
# JobQuest Hub — launch Pipeline, Tracker, and Discovery in one click
cd "$(dirname "$0")"
ROOT_DIR="$(pwd)"

# Kill any existing JobQuest servers on these ports
lsof -ti:7860 -ti:7880 2>/dev/null | xargs kill -9 2>/dev/null
sleep 1

# Use the project virtualenv interpreter directly. Never rely on a global `python`.
PYTHON="$ROOT_DIR/venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "ERROR: JobQuest virtualenv Python not found at: $PYTHON" >&2
  echo "Rebuild it with: python3 -m venv venv && venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
if ! "$PYTHON" -c 'import sys' >/dev/null 2>&1; then
  echo "ERROR: $PYTHON exists but cannot run. Rebuild the virtualenv." >&2
  exit 1
fi
echo "Using $("$PYTHON" -V 2>&1) → $PYTHON"

TRACKER_PID=""
PIPELINE_PID=""
cleanup() {
  trap - SIGINT SIGTERM EXIT
  echo ""
  echo "Stopping JobQuest servers..."
  [ -n "$TRACKER_PID" ] && kill "$TRACKER_PID" 2>/dev/null
  [ -n "$PIPELINE_PID" ] && kill "$PIPELINE_PID" 2>/dev/null
  wait 2>/dev/null
}
trap cleanup SIGINT SIGTERM EXIT

# Start Tracker server (serves Tracker + Discovery + API)
"$PYTHON" serve_tracker.py --port 7880 &
TRACKER_PID=$!
echo "Tracker server starting on port 7880 (PID: $TRACKER_PID)..."

# Start Pipeline UI (Gradio)
"$PYTHON" web_ui.py &
PIPELINE_PID=$!
echo "Pipeline UI starting on port 7860 (PID: $PIPELINE_PID)..."

# Wait until each server actually accepts connections before claiming success
wait_for_url() {
  local url="$1" pid="$2" name="$3"
  local deadline=$((SECONDS + 60))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if curl -fsS -o /dev/null --max-time 2 "$url" 2>/dev/null; then
      return 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "ERROR: $name exited before $url became available." >&2
      return 1
    fi
    sleep 1
  done
  echo "ERROR: $name did not respond at $url within 60s." >&2
  return 1
}

if ! wait_for_url http://127.0.0.1:7880/ "$TRACKER_PID" "Tracker server"; then
  echo "See the Tracker output above for the failure reason." >&2
  exit 1
fi
if ! wait_for_url http://127.0.0.1:7860/ "$PIPELINE_PID" "Pipeline UI"; then
  echo "See the Pipeline UI output above for the failure reason." >&2
  exit 1
fi

# Open 3 browser tabs
open http://127.0.0.1:7860   # Pipeline
open http://127.0.0.1:7880   # Tracker
open http://127.0.0.1:7880/queue  # Discovery

echo ""
echo "📋 JobQuest Hub is running:"
echo "   Pipeline  → http://127.0.0.1:7860"
echo "   Tracker   → http://127.0.0.1:7880"
echo "   Discovery → http://127.0.0.1:7880/queue"
echo ""
echo "Press Ctrl+C to stop all servers."

# Wait for either process to exit; cleanup trap stops the other one
wait
