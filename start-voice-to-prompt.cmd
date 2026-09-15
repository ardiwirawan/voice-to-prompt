@echo off
rem Windows launcher for voice-to-prompt (minimized).
rem Initial setup:  python -m venv venv ^&^& venv\Scripts\pip install -r requirements.txt
if exist "%~dp0venv\Scripts\python.exe" (
  start "voice-to-prompt" /min "%~dp0venv\Scripts\python.exe" "%~dp0voice_to_prompt.py" --config "%~dp0config.toml"
) else (
  start "voice-to-prompt" /min python "%~dp0voice_to_prompt.py" --config "%~dp0config.toml"
)
