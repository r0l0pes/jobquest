#!/usr/bin/env bash
set -euo pipefail

# Move to repo root
cd "$(dirname "$0")/.."

# Activate venv
source venv/bin/activate

# Run smoke check
python3 scripts/smoke_check.py