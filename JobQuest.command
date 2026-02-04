#!/bin/bash
# Double-click this file to launch JobQuest in your browser
cd "$(dirname "$0")"
source venv/bin/activate
python web_ui.py
