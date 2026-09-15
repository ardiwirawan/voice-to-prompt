#!/usr/bin/env python3
"""
voice-to-prompt — universal voice typing via a global hotkey.

Press the hotkey anywhere -> beep -> speak -> stop talking -> the transcript
is typed into whatever text field has focus (and copied to the clipboard).

Works with any application: terminals, browsers, chat apps, IDEs, docs.

Usage:
    python voice_to_prompt.py [--config path/to/config.toml]

Config resolution order:
    1. --config <path>
    2. ./config.toml
    3. ~/.config/voice-to-prompt/config.toml
    4. built-in defaults

API key resolution order:
    1. env var named by [transcription].api_key_env (default GROQ_API_KEY)
    2. key file named by [transcription].api_key_file (default groq_key.txt,
       relative to the config file's directory)
"""

from __future__ import annotations

import io
import os
import sys
import threading
import time
import wave

import numpy as np

# sounddevice hanya dibutuhkan saat merekam; guard supaya modul tetap bisa
# diimpor di lingkungan tanpa PortAudio (mis. CI headless / Linux minimal).
try:
    import sounddevice as sd
except Exception:  # pragma: no cover
    sd = None

# stdout/stderr bisa memakai cp1252 saat output dialihkan (tanpa console) —
# emoji akan crash tanpa ini.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="backslashreplace")
    except Exception:
        pass

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    tomllib = None

# ----------------------------------------------------------------------------
# Feedback (beeps) — cross-platform
# ----------------------------------------------------------------------------
if sys.platform == "win32":
    import winsound

    def _beep(freq: int, ms: int) -> None:
        winsound.Beep(freq, ms)
elif sys.platform == "darwin":
    def _beep(freq: int, ms: int) -> None:
        os.system("afplay /System/Library/Sounds/Tink.aiff &")
else:
    def _beep(freq: int, ms: int) -> None:  # terminal bell fallback
        print("\a", end="", flush=True)


# ----------------------------------------------------------------------------
# Hotkey & pengetikan — pynput (cross-platform: Windows/macOS/Linux-X11)
# Konversi format hotkey umum ("ctrl+alt+v", "f9") ke format pynput.
# ----------------------------------------------------------------------------
def to_pynput_hotkey(hotkey: str) -> str:
    mods = {"ctrl": "<ctrl>", "control": "<ctrl>", "alt": "<alt>",
            "shift": "<shift>", "cmd": "<cmd>", "win": "<cmd>", "super": "<cmd>"}
    out = []
    for part in (p.strip().lower() for p in hotkey.split("+")):
        if part in mods:
            out.append(mods[part])
        elif len(part) > 1:      # f9, enter, space, pause, dst.
            out.append(f"<{part}>")
        else:
            out.append(part)     # huruf/angka tunggal
    return "+".join(out)


def normalize_captured_key(keysym: str, char: str) -> str | None:
    """Normalisasi penekanan tombol (event tkinter) menjadi nama hotkey.

    :param keysym: event.keysym (mis. "F9", "slash", "Return")
    :param char:   event.char (karakter printable, "" untuk tombol khusus)
    :return: nama hotkey internal ("f9", "ctrl+/", "enter", ...); "" saat
             tombol adalah modifier (tunggu tombol berikut); None saat batal.
    """
    ks = (keysym or "").lower()
    if ks == "escape":
        return None
    if ks in ("control_l", "control_r", "alt_l", "alt_r", "shift_l", "shift_r"):
        return ""
    key_map = {"return": "enter", "prior": "page_up", "next": "page_down",
               "print": "print_screen", "kp_enter": "enter", "space": "space"}
    if ks in key_map:
        return key_map[ks]
    if char and char.isprintable():
        return char
    return ks


class HotkeyListener:
    """Hotkey global via Listener + HotKey langsung.

    Tidak memakai GlobalHotKeys karena pynput >= 1.8 mengabaikan event
    sintetis di sana; versi ini menerima keduanya (fisik & terinjeksi),
    sehingga bisa diuji otomatis.
    """

    def __init__(self, mapping: dict):
        from pynput import keyboard
        self._hotkeys = [
            keyboard.HotKey(keyboard.HotKey.parse(k), v) for k, v in mapping.items()
        ]
        self._listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release)

    def _on_press(self, key):
        canon = self._listener.canonical(key)
        for hk in self._hotkeys:
            hk.press(canon)

    def _on_release(self, key):
        canon = self._listener.canonical(key)
        for hk in self._hotkeys:
            hk.release(canon)

    def start(self):
        self._listener.start()

    def stop(self):
        self._listener.stop()


def beep_start() -> None:
    _beep(880, 150)


def beep_done() -> None:
    _beep(1175, 120)
    _beep(1568, 200)


def beep_fail() -> None:
    _beep(400, 350)


# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "hotkey": "f9",
    "auto_type": True,
    "typing_delay": 0.01,
    "beeps": True,
    "ui_language": "en",   # bahasa antarmuka: "id" | "en"
    "recording": {
        "sample_rate": 16000,
        "channels": 1,
        "silence_threshold": 0.012,
        "silence_stop_after": 2.0,
        "initial_timeout": 6.0,
        "min_seconds": 0.8,
        "max_seconds": 60.0,
        "device": "",  # substring nama device; kosong = default sistem
        "stop_with_hotkey": True,  # tekan hotkey lagi saat merekam = berhenti
    },
    "transcription": {
        "engine": "groq",
        "model": "whisper-large-v3",
        "language": "",  # kosong = auto-detect; atau "id", "en", dst.
        "api_key_env": "GROQ_API_KEY",
        "api_key_file": "groq_key.txt",
    },
    "cleanup": {
        "enabled": True,   # rapikan hasil: buang kata pengisi, pakai koreksi terakhir
        "model": "qwen/qwen3.8-27b",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(argv: list[str]) -> tuple[dict, str, str, str]:
    """Return (config_tergabung, config_dir, config.toml_path, config.local.toml_path).

    config.local.toml (ditulis oleh UI Settings) menimpa config.toml —
    config.toml tetap bersih untuk di-commit, override lokal terpisah.
    """
    cfg_path = None
    if "--config" in argv:
        i = argv.index("--config")
        if i + 1 < len(argv):
            cfg_path = argv[i + 1]
    if cfg_path is None and os.path.exists("config.toml"):
        cfg_path = "config.toml"
    if cfg_path is None:
        candidate = os.path.expanduser("~/.config/voice-to-prompt/config.toml")
        if os.path.exists(candidate):
            cfg_path = candidate

    cfg_dir = os.getcwd()
    base_path = cfg_path or os.path.join(cfg_dir, "config.toml")
    local_path = os.path.join(os.path.dirname(os.path.abspath(base_path)), "config.local.toml")

    cfg = DEFAULT_CONFIG
    if cfg_path:
        if tomllib is None:
            raise SystemExit("Butuh Python >= 3.11 untuk membaca config.toml")
        with open(cfg_path, "rb") as f:
            cfg = _deep_merge(DEFAULT_CONFIG, tomllib.load(f))
        cfg_dir = os.path.dirname(os.path.abspath(cfg_path))
    # override lokal (dari UI) paling akhir
    if os.path.exists(local_path) and tomllib is not None:
        with open(local_path, "rb") as f:
            cfg = _deep_merge(cfg, tomllib.load(f))
    return cfg, cfg_dir, base_path, local_path


# ----------------------------------------------------------------------------
# Recording (auto-stop on silence)
# ----------------------------------------------------------------------------
def assert_audio_available():
    if sd is None:
        raise RuntimeError(
            "Pustaka audio (PortAudio/sounddevice) tidak tersedia di sistem ini.")


def resolve_device(name_or_index: str):
    """Resolve substring nama device -> index, fresh setiap panggilan
    (index audio di Windows bisa bergeser saat headset Bluetooth lepas/pasang)."""
    if not name_or_index:
        return None
    try:
        return int(name_or_index)
    except ValueError:
        pass
    needle = name_or_index.lower()
    matches = [
        i for i, d in enumerate(sd.query_devices())
        if needle in d["name"].lower() and d["max_input_channels"] > 0
    ]
    return matches[0] if matches else None


def record(cfg: dict, stop_event: threading.Event | None = None) -> np.ndarray | None:
    r = cfg["recording"]
    sr, ch = r["sample_rate"], r["channels"]
    block = int(sr * 0.1)
    frames: list[np.ndarray] = []
    started = False
    silent_for = 0.0
    waited = 0.0

    assert_audio_available()
    device = resolve_device(str(r.get("device", "")))
    if cfg["beeps"]:
        beep_start()  # sinkron, jadi bunyi bip tidak ikut terekam
    with sd.InputStream(samplerate=sr, channels=ch, dtype="int16",
                        blocksize=block, device=device) as stream:
        for _ in range(int(r["max_seconds"] / 0.1)):
            if stop_event is not None and stop_event.is_set():
                if not started:
                    print("Rekaman dibatalkan lewat tombol.", file=sys.stderr)
                    if cfg["beeps"]:
                        beep_fail()
                    return None
                break  # berhenti manual: lanjut ke transkripsi
            data, _ = stream.read(block)
            frames.append(data.copy())
            rms = float(np.sqrt(np.mean(data.astype(np.float32) ** 2)) / 32768.0)
            if rms > r["silence_threshold"]:
                started = True
                silent_for = 0.0
            elif started:
                silent_for += 0.1
            else:
                waited += 0.1
                if waited >= r["initial_timeout"]:
                    if cfg["beeps"]:
                        beep_fail()
                    print("Tidak ada suara, rekaman dibatalkan.", file=sys.stderr)
                    return None
            if started and silent_for >= r["silence_stop_after"]:
                break

    duration = len(frames) * 0.1
    if duration < r["min_seconds"]:
        if cfg["beeps"]:
            beep_fail()
        print(f"Rekaman terlalu pendek ({duration:.1f} detik), dibatalkan.", file=sys.stderr)
        return None
    if cfg["beeps"]:
        beep_done()
    print(f"Rekaman {duration:.1f} detik, mengubah menjadi teks…", file=sys.stderr)
    return np.concatenate(frames, axis=0)


def to_wav_bytes(audio: np.ndarray, cfg: dict) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(cfg["recording"]["channels"])
        wf.setsampwidth(2)
        wf.setframerate(cfg["recording"]["sample_rate"])
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


# ----------------------------------------------------------------------------
# Transcription engines
# ----------------------------------------------------------------------------
def load_api_key(cfg: dict, cfg_dir: str) -> str:
    t = cfg["transcription"]
    key = os.environ.get(t["api_key_env"], "").strip()
    if key:
        return key
    for base in (cfg_dir, os.path.dirname(os.path.abspath(__file__))):
        p = os.path.join(base, t["api_key_file"])
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return f.read().strip()
    return ""


def transcribe_groq(wav_bytes: bytes, cfg: dict, api_key: str) -> str:
    import requests

    t = cfg["transcription"]
    data = {"model": t["model"], "response_format": "json"}
    if t.get("language"):
        data["language"] = t["language"]
    resp = requests.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {api_key}"},
        files={"file": ("voice.wav", wav_bytes, "audio/wav")},
        data=data,
        timeout=90,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Groq API {resp.status_code}: {resp.text[:300]}")
    return resp.json().get("text", "").strip()


def transcribe(wav_bytes: bytes, cfg: dict, api_key: str) -> str:
    engine = cfg["transcription"]["engine"]
    if engine == "groq":
        return transcribe_groq(wav_bytes, cfg, api_key)
    raise RuntimeError(f"Engine tidak dikenal: {engine!r} (saat ini: 'groq')")


# ----------------------------------------------------------------------------
# Cleanup: rapikan transkrip mentah via LLM (buang filler, pakai koreksi akhir)
# ----------------------------------------------------------------------------
CLEANUP_SYSTEM = (
    "Kamu perapi transkrip suara. Rapikan teks dari pembicara: "
    "buang kata pengisi seperti 'eee', 'umm', 'hmm', 'apa ya', 'gitu', 'nah ini' "
    "yang tidak perlu; jika pembicara mengoreksi diri di tengah kalimat, pakai "
    "maksud yang terakhir; perbaiki pengulangan kata yang tidak disengaja; "
    "tambahkan tanda baca yang wajar. Jangan mengubah makna, bahasa, atau gaya "
    "bicara. Jangan menambah atau mengurangi informasi. Jangan memberi komentar, "
    "tanda kutip, atau penjelasan apa pun — keluarkan hanya teks hasil rapi."
)


def cleanup_text(text: str, cfg: dict, api_key: str) -> str:
    """Rapikan transkrip. Jika gagal, kembalikan teks mentah (jangan rugikan user)."""
    if not cfg["cleanup"]["enabled"] or not text.strip():
        return text
    import requests

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": cfg["cleanup"]["model"],
            "messages": [
                {"role": "system", "content": CLEANUP_SYSTEM},
                {"role": "user", "content": text},
            ],
            "temperature": 0,
        },
        timeout=60,
    )
    if resp.status_code != 200:
        print(f"Cleanup gagal ({resp.status_code}), pakai teks mentah.", file=sys.stderr)
        return text
    cleaned = resp.json()["choices"][0]["message"]["content"].strip()
    return cleaned or text


# ----------------------------------------------------------------------------
# Output: clipboard + type-at-cursor
# ----------------------------------------------------------------------------
def emit(text: str, cfg: dict) -> None:
    import pyperclip
    pyperclip.copy(text)

    if cfg["auto_type"]:
        from pynput.keyboard import Controller
        kb = Controller()
        # newline diratakan jadi spasi supaya tidak ke-enter duluan
        flat = " ".join(text.split())
        time.sleep(0.2)
        for ch in flat:
            kb.type(ch)
            time.sleep(cfg["typing_delay"])


# ----------------------------------------------------------------------------
# Tray icon (opsional — fallback ke mode console jika pystray tidak ada)
# ----------------------------------------------------------------------------
def _tray_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), fill=(37, 99, 235, 255))          # lingkaran biru
    d.rounded_rectangle((26, 14, 38, 34), radius=6, fill="white")  # badan mic
    d.arc((20, 24, 44, 46), start=0, end=180, fill="white", width=3)
    d.line((32, 46, 32, 54), fill="white", width=3)
    return img


def _run_with_tray(state, on_open_settings, on_quit) -> None:
    import pystray
    from i18n import tr
    cfg = state["cfg"]
    menu = pystray.Menu(
        pystray.MenuItem(tr(cfg, "menu_settings"), lambda: on_open_settings(), default=True),
        pystray.MenuItem(tr(cfg, "menu_quit"), lambda: on_quit()),
    )
    icon = pystray.Icon("voice-to-prompt", _tray_image(), "voice-to-prompt", menu)
    state["tray"] = icon
    icon.run()  # blocking di main thread


# ----------------------------------------------------------------------------
# Hotkey listener
# ----------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    cfg, cfg_dir, base_path, local_path = load_config(argv)
    key_path = os.path.join(cfg_dir, cfg["transcription"]["api_key_file"])

    busy = threading.Lock()
    state: dict = {
        "cfg": cfg,
        "tray": None,
        "hotkey_handle": None,
        "api_key": load_api_key(cfg, cfg_dir),
        "recording": False,
        "stop_event": threading.Event(),
        "settings_open": False,
    }

    def on_hotkey():
        c = state["cfg"]
        # F9 saat merekam = berhenti manual (jika diaktifkan)
        if state["recording"] and c["recording"].get("stop_with_hotkey", True):
            state["stop_event"].set()
            print("Berhenti manual lewat tombol.", flush=True)
            return
        if not busy.acquire(blocking=False):
            print("Masih memproses rekaman sebelumnya, diabaikan.", file=sys.stderr)
            return
        try:
            if not state["api_key"]:
                if c["beeps"]:
                    beep_fail()
                print("Kunci API belum diisi — buka Pengaturan dari ikon di area notifikasi.", file=sys.stderr)
                return
            state["stop_event"].clear()
            state["recording"] = True
            try:
                audio = record(c, state["stop_event"])
            finally:
                state["recording"] = False
            if audio is None:
                return
            text = transcribe(to_wav_bytes(audio, c), c, state["api_key"])
            if not text:
                if c["beeps"]:
                    beep_fail()
                print("Transkrip kosong.", file=sys.stderr)
                return
            if c["cleanup"]["enabled"]:
                text = cleanup_text(text, c, state["api_key"])
            print(f"Hasil: {text}", flush=True)
            emit(text, c)
        except Exception as e:  # noqa: BLE001 — listener tidak boleh mati
            if c["beeps"]:
                beep_fail()
            print(f"Error: {e}", file=sys.stderr)
        finally:
            busy.release()

    def register_hotkey():
        # Handler harus di thread baru: callback pynput berjalan di thread
        # listener; kalau record() blocking di sana, penekanan tombol berikutnya
        # (misal F9 untuk berhenti manual) tidak akan pernah terbaca.
        def make_listener(hotkey_str: str) -> HotkeyListener:
            mapping = {
                to_pynput_hotkey(hotkey_str):
                    lambda: threading.Thread(target=on_hotkey, daemon=True).start(),
            }
            return HotkeyListener(mapping)

        chosen = state["cfg"]["hotkey"]
        try:
            listener = make_listener(chosen)
        except Exception as e:
            print(f"Tombol '{chosen}' tidak dikenali ({e}); kembali ke F9.", file=sys.stderr)
            chosen = "f9"
            listener = make_listener(chosen)
        if state["hotkey_handle"] is not None:
            state["hotkey_handle"].stop()
        listener.start()
        state["hotkey_handle"] = listener
        print(f"Tombol pintasan aktif: {chosen.upper()}", flush=True)

    def reload_config():
        """Baca ulang config + kunci API, terapkan tanpa restart."""
        nonlocal cfg
        try:
            new_cfg, new_dir, *_ = load_config(argv)
            state["cfg"] = new_cfg
            state["api_key"] = load_api_key(new_cfg, new_dir)
            register_hotkey()  # jaga-jaga jika hotkey berubah
            print("Pengaturan dimuat ulang, langsung berlaku.", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"Gagal memuat ulang pengaturan: {e}", file=sys.stderr)

    def open_settings():
        # Singleton: klik berulang pada ikon tray tidak membuka jendela ganda.
        if state.get("settings_open"):
            return
        state["settings_open"] = True
        from settings_ui import open_settings as _open

        def _run():
            try:
                _open(lambda: state["cfg"], local_path, key_path, reload_config)
            finally:
                state["settings_open"] = False
        threading.Thread(target=_run, daemon=True).start()

    def quit_app():
        if state["tray"] is not None:
            state["tray"].stop()
        os._exit(0)

    register_hotkey()
    print(f"voice-to-prompt aktif. Tekan {state['cfg']['hotkey'].upper()} lalu bicara;", flush=True)
    print("berhenti bicara sejenak untuk mengakhiri rekaman.", flush=True)

    has_tray = False
    try:
        import pystray, PIL  # noqa: F401
        has_tray = True
    except ImportError:
        pass

    if not state["api_key"]:
        print("Kunci API belum diisi — jendela Pengaturan dibuka untuk pengisian.", flush=True)
        if has_tray:
            open_settings()  # pandu pengguna baru langsung ke tempat isi kunci
        else:
            t = cfg["transcription"]
            print(f"Mode console: isi env {t['api_key_env']} atau file {t['api_key_file']}.", flush=True)

    if has_tray:
        _run_with_tray(state, open_settings, quit_app)  # blocking
    else:
        threading.Event().wait()  # hotkey listener jalan di thread-nya sendiri
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
