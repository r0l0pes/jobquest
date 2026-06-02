#!/bin/bash
# JobQuest Hub — launch Pipeline, Tracker, and Discovery in one click
cd "$(dirname "$0")"

# Kill any existing JobQuest servers on these ports
lsof -ti:7860 -ti:7880 2>/dev/null | xargs kill -9 2>/dev/null
sleep 1

# Activate virtual environment
source venv/bin/activate

# Start Tracker server (serves Tracker + Discovery + API)
python serve_tracker.py --port 7880 &
TRACKER_PID=$!
echo "Tracker server starting on port 7880 (PID: $TRACKER_PID)..."

# Start Pipeline UI (Gradio)
python web_ui.py &
PIPELINE_PID=$!
echo "Pipeline UI starting on port 7860 (PID: $PIPELINE_PID)..."

# Wait for servers to be ready
sleep 3

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

# Wait for either process to exit
trap "kill $TRACKER_PID $PIPELINE_PID 2>/dev/null; exit 0" SIGINT SIGTERM
wait
