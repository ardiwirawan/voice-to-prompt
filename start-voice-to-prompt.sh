#!/usr/bin/env bash
# Launcher macOS/Linux untuk voice-to-prompt.
# Setup dulu:  python3 -m venv venv && venv/bin/pip install -r requirements.txt
cd "$(dirname "$0")"
if [ -x "venv/bin/python" ]; then
  PY="venv/bin/python"
else
  PY="python3"
fi
exec "$PY" voice_to_prompt.py --config config.toml
