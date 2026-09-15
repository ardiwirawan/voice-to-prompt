@echo off
rem Launcher Windows untuk voice-to-prompt (mode minimize).
rem Jalankan setup dulu:  python -m venv venv ^&^& venv\Scripts\pip install -r requirements.txt
if exist "%~dp0venv\Scripts\python.exe" (
  start "voice-to-prompt" /min "%~dp0venv\Scripts\python.exe" "%~dp0voice_to_prompt.py" --config "%~dp0config.toml"
) else (
  start "voice-to-prompt" /min python "%~dp0voice_to_prompt.py" --config "%~dp0config.toml"
)
