# voice-to-prompt

Universal voice typing via a global hotkey. Press **F9** anywhere → speak →
stop talking → your words are **typed into whatever text field has focus**.
Works in terminals (opencode, Windows Terminal), browsers, chat apps, IDEs —
anywhere you can type.

Powered by [Groq](https://groq.com) Whisper API (`whisper-large-v3`) — fast
(~1–2 s), free tier, excellent multilingual accuracy including Bahasa
Indonesia.

## Features

- **Push-hotkey dictation** — beep = speak, silence 2 s = done, beep-beep = typed
- **Manual stop** — press the hotkey again mid-recording to stop instantly
  (silence auto-stop stays as a fallback)
- **Auto-cleanup** — optional LLM pass removes filler words ("eee", "umm"),
  applies your mid-sentence corrections, and fixes punctuation. If it fails,
  the raw transcript is used — you never lose text.
- **Settings UI (bilingual: Indonesian/English)** — tray icon → Settings:
  sliders, dropdowns, API key field with a one-click "get a free key" button
  and live key validation. Everything applies instantly, no restart.
- **Cross-platform hotkeys & typing** — via pynput (Windows/macOS/Linux-X11)
- **App-agnostic** — types at the OS input level; not tied to any specific app
- **Mic selection by name** — survives audio-device index reshuffles
  (Bluetooth headset connect/disconnect safe)
- **Configurable** — hotkey, thresholds, engine, language, auto-type on/off
- **Clipboard fallback** — transcript is always copied too

## Quickstart

```bash
git clone <repo-url> voice-to-prompt
cd voice-to-prompt
python -m venv venv
venv/Scripts/pip install -r requirements.txt   # Windows
# source venv/bin/activate; pip install -r requirements.txt   # macOS/Linux
```

1. Run: `python voice_to_prompt.py` — or use the launcher:
   `start-voice-to-prompt.cmd` (Windows) / `./start-voice-to-prompt.sh` (macOS/Linux)
2. First run opens the **Settings** window automatically — click
   **"Dapatkan kunci gratis"** (free Groq key via Google/email sign-up, no
   credit card), paste the key, press **"Tes kunci"** to verify, then **Simpan**.
3. Focus any text field, press **F9**, speak after the beep.

## Configuration

**Easiest way: the Settings UI** — right-click the tray icon → **Settings…**
A window opens with sliders (silence delay, thresholds), dropdowns
(microphone, model, language), and toggles. **Save applies instantly, no
restart needed.** The UI writes to `config.local.toml` (auto-gitignored),
which overrides `config.toml` — so the committed config stays clean.

Prefer editing files? See [`config.toml`](config.toml) — every option is
documented inline. Highlights:

| Option | Default | Notes |
|---|---|---|
| `hotkey` | `"f9"` | e.g. `"f8"`, `"ctrl+alt+v"`, `"pause"` |
| `ui_language` | `"en"` | Settings UI language: `"en"` / `"id"` |
| `auto_type` | `true` | `false` = clipboard only |
| `recording.device` | `""` | mic name substring; empty = system default |
| `recording.silence_threshold` | `0.012` | raise in noisy rooms |
| `recording.silence_stop_after` | `2.0` | raise if you think mid-sentence |
| `recording.stop_with_hotkey` | `true` | press hotkey again to stop manually |
| `transcription.model` | `whisper-large-v3` | `whisper-large-v3-turbo` is faster |
| `transcription.language` | `""` (auto) | pin to `"id"`, `"en"`, … |
| `cleanup.enabled` | `true` | LLM pass that removes filler words etc. |
| `cleanup.model` | `qwen/qwen3.8-27b` | tested best at self-corrections |

## Platform notes

Global hotkeys and typing are handled by **pynput** (cross-platform).

- **Windows**: fully tested. Apps running *as Administrator* may block
  synthetic typing from a non-elevated listener (Windows UIPI) — run the
  listener as Administrator in that case.
- **macOS**: grant *Accessibility* permission to your terminal/Python when
  prompted. No sudo needed. Use `start-voice-to-prompt.sh`.
- **Linux**: works on X11. Wayland deliberately restricts global hotkeys and
  synthetic input — use an X11 session if you need full functionality.

## Testing

```bash
pip install -r requirements-dev.txt
pytest -v
```

158 unit tests cover: config loading & local overrides, the full hotkey
capture matrix (every keyboard key must produce a pynput-parseable value —
regression guard for the "slash" bug), API key resolution, and transcription /
cleanup flows with HTTP mocked. CI runs them on Python 3.11–3.13
(`.github/workflows/ci.yml`).

## Roadmap

- [x] System tray icon + bilingual Settings UI
- [x] Manual stop via hotkey (press again to stop)
- [ ] Local/offline engine (faster-whisper)
- [ ] OpenAI-compatible transcription endpoint support
- [ ] Push-to-talk mode (hold key) as an alternative to silence detection
- [ ] Stop-word by voice ("stop") — needs streaming transcription

## Bahasa Indonesia

Dikte universal pakai hotkey global. Tekan **F9** di mana saja → bicara →
berhenti sejenak (atau tekan F9 lagi) → transkrip terketik otomatis di input
yang sedang fokus. Gratis pakai Groq Whisper API. Semua pengaturan bisa lewat
jendela Pengaturan (klik kanan ikon tray), tersedia dalam Bahasa Indonesia
dan English — tanpa perlu menyunting file apa pun.

## License

MIT — see [LICENSE](LICENSE).
