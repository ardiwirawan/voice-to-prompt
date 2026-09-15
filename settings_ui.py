"""
settings_ui.py — jendela Pengaturan (tkinter) untuk voice-to-prompt.

Menulis override ke config.local.toml (bukan mengubah config.toml),
lalu memanggil callback reload agar perubahan langsung berlaku tanpa restart.
Antarmuka dwibahasa (Indonesia/English) mengikuti cfg["ui_language"].
"""

import os
import tkinter as tk
import webbrowser
from tkinter import ttk

import sounddevice as sd
import tomli_w

from i18n import LANG_NAMES, tr

GROQ_KEYS_URL = "https://console.groq.com/keys"


def _input_device_names() -> list[str]:
    names = []
    for d in sd.query_devices():
        if d["max_input_channels"] > 0:
            names.append(d["name"])
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


class SettingsWindow:
    def __init__(self, cfg: dict, local_path: str, key_path: str, on_save):
        self.cfg = cfg
        self.local_path = local_path
        self.key_path = key_path
        self.on_save = on_save
        self.reopen_requested = False

        self.root = tk.Tk()
        self.root.title(tr(cfg, "settings_title"))
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        r = cfg["recording"]
        t = cfg["transcription"]

        # ---- state variables ----
        self.v_ui_language = tk.StringVar(value=cfg.get("ui_language", "id"))
        self.v_hotkey = tk.StringVar(value=cfg["hotkey"])
        self.v_auto_type = tk.BooleanVar(value=cfg["auto_type"])
        self.v_beeps = tk.BooleanVar(value=cfg["beeps"])
        self.v_typing_delay = tk.DoubleVar(value=cfg["typing_delay"])
        self.v_silence_stop = tk.DoubleVar(value=r["silence_stop_after"])
        self.v_threshold = tk.DoubleVar(value=r["silence_threshold"])
        self.v_initial_timeout = tk.DoubleVar(value=r["initial_timeout"])
        self.v_max_seconds = tk.DoubleVar(value=r["max_seconds"])
        self.v_device = tk.StringVar(value=r.get("device", ""))
        self.v_model = tk.StringVar(value=t["model"])
        self.v_language = tk.StringVar(value=t.get("language", ""))
        self.v_cleanup = tk.BooleanVar(value=cfg["cleanup"]["enabled"])
        self.v_cleanup_model = tk.StringVar(value=cfg["cleanup"]["model"])
        self.v_stop_hotkey = tk.BooleanVar(value=r.get("stop_with_hotkey", True))

        pad = {"padx": 8, "pady": 4, "sticky": "w"}

        # ---- Umum / General ----
        frm = ttk.LabelFrame(self.root, text=tr(cfg, "section_general"))
        frm.pack(fill="x", padx=10, pady=6)

        ttk.Label(frm, text=tr(cfg, "ui_language_label")).grid(row=0, column=0, **pad)
        lang_display = {code: name for code, name in LANG_NAMES.items()}
        self.v_ui_language_display = tk.StringVar(value=LANG_NAMES.get(self.v_ui_language.get(), "Bahasa Indonesia"))
        cb_lang = ttk.Combobox(frm, textvariable=self.v_ui_language_display,
                               values=list(LANG_NAMES.values()), width=16, state="readonly")
        cb_lang.grid(row=0, column=1, **pad)
        cb_lang.bind("<<ComboboxSelected>>", lambda _e: self.v_ui_language.set(
            {v: k for k, v in lang_display.items()}[self.v_ui_language_display.get()]))

        ttk.Label(frm, text=tr(cfg, "hotkey_label")).grid(row=1, column=0, **pad)
        hk_bar = ttk.Frame(frm)
        hk_bar.grid(row=1, column=1, **pad)
        ttk.Entry(hk_bar, textvariable=self.v_hotkey, width=14).pack(side="left")
        self.record_btn = ttk.Button(hk_bar, text=tr(cfg, "record_hotkey"),
                                     command=self._start_capture)
        self.record_btn.pack(side="left", padx=6)
        ttk.Checkbutton(frm, text=tr(cfg, "auto_type_label"),
                        variable=self.v_auto_type).grid(row=2, column=0, columnspan=2, **pad)
        ttk.Checkbutton(frm, text=tr(cfg, "beeps_label"),
                        variable=self.v_beeps).grid(row=3, column=0, columnspan=2, **pad)
        self._scale(frm, 4, tr(cfg, "typing_delay_label"), self.v_typing_delay, 0.0, 0.05, "{:.3f}")

        # ---- Perekaman / Recording ----
        frm = ttk.LabelFrame(self.root, text=tr(cfg, "section_recording"))
        frm.pack(fill="x", padx=10, pady=6)
        self._scale(frm, 0, tr(cfg, "silence_stop_label"),
                    self.v_silence_stop, 0.5, 6.0, "{:.1f}")
        self._scale(frm, 1, tr(cfg, "threshold_label"),
                    self.v_threshold, 0.001, 0.05, "{:.3f}")
        self._spin(frm, 2, tr(cfg, "initial_timeout_label"), self.v_initial_timeout, 2, 20)
        self._spin(frm, 3, tr(cfg, "max_seconds_label"), self.v_max_seconds, 10, 300)
        ttk.Checkbutton(frm, text=tr(cfg, "stop_hotkey_label"),
                        variable=self.v_stop_hotkey).grid(row=4, column=0, columnspan=2, **pad)
        ttk.Label(frm, text=tr(cfg, "mic_label")).grid(row=5, column=0, **pad)
        devices = [tr(cfg, "system_default")] + _input_device_names()
        cur = self.v_device.get()
        cb = ttk.Combobox(frm, textvariable=self.v_device, values=devices, width=34, state="normal")
        cb.grid(row=5, column=1, **pad)
        if not cur:
            self.v_device.set(tr(cfg, "system_default"))

        # ---- Kunci API ----
        frm = ttk.LabelFrame(self.root, text=tr(cfg, "section_api"))
        frm.pack(fill="x", padx=10, pady=6)

        current_key = ""
        if os.path.exists(self.key_path):
            with open(self.key_path, "r", encoding="utf-8") as f:
                current_key = f.read().strip()
        self.v_apikey = tk.StringVar(value=current_key)

        ttk.Label(frm, text=tr(cfg, "paste_key_label")).grid(row=0, column=0, **pad)
        self.key_entry = ttk.Entry(frm, textvariable=self.v_apikey, width=30, show="●")
        self.key_entry.grid(row=0, column=1, **pad)
        ttk.Button(frm, text=tr(cfg, "show_key"), width=8,
                   command=self._toggle_key_visible).grid(row=0, column=2, **pad)

        row2 = ttk.Frame(frm)
        row2.grid(row=1, column=0, columnspan=3, sticky="w", padx=8, pady=4)
        ttk.Button(row2, text=tr(cfg, "get_key"),
                   command=lambda: webbrowser.open(GROQ_KEYS_URL)).pack(side="left")
        ttk.Button(row2, text=tr(cfg, "test_key"), command=self._test_key).pack(side="left", padx=6)
        self.key_status = ttk.Label(row2, text="")
        self.key_status.pack(side="left", padx=4)

        ttk.Label(frm, text=tr(cfg, "key_help"),
                  foreground="#555").grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 6))

        # ---- Transkripsi / Transcription ----
        frm = ttk.LabelFrame(self.root, text=tr(cfg, "section_transcription"))
        frm.pack(fill="x", padx=10, pady=6)
        ttk.Label(frm, text=tr(cfg, "model_label")).grid(row=0, column=0, **pad)
        ttk.Combobox(frm, textvariable=self.v_model,
                     values=["whisper-large-v3", "whisper-large-v3-turbo"],
                     width=26, state="readonly").grid(row=0, column=1, **pad)
        ttk.Label(frm, text=tr(cfg, "language_label")).grid(row=1, column=0, **pad)
        ttk.Combobox(frm, textvariable=self.v_language,
                     values=["(auto)", "id", "en", "jv", "su"],
                     width=26, state="readonly").grid(row=1, column=1, **pad)
        if not self.v_language.get():
            self.v_language.set("(auto)")

        ttk.Checkbutton(frm, text=tr(cfg, "cleanup_label"),
                        variable=self.v_cleanup).grid(row=2, column=0, columnspan=2, **pad)
        ttk.Label(frm, text=tr(cfg, "cleanup_model_label")).grid(row=3, column=0, **pad)
        ttk.Combobox(frm, textvariable=self.v_cleanup_model,
                     values=["qwen/qwen3.8-27b", "qwen/qwen3.6-27b",
                             "openai/gpt-oss-20b", "openai/gpt-oss-120b"],
                     width=26, state="readonly").grid(row=3, column=1, **pad)

        # ---- Tombol ----
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=10, pady=10)
        self.status = ttk.Label(bar, text="")
        self.status.pack(side="left")
        ttk.Button(bar, text=tr(cfg, "reset_btn"), command=self._reset).pack(side="right", padx=4)
        ttk.Button(bar, text=tr(cfg, "save_btn"), command=self._save).pack(side="right", padx=4)

    def _scale(self, parent, row, label, var, lo, hi, fmt):
        ttk.Label(parent, text=label).grid(row=row, column=0, padx=8, pady=4, sticky="w")
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=1, padx=8, pady=4, sticky="w")
        val = ttk.Label(frame, text=fmt.format(var.get()), width=6)
        val.pack(side="right")
        s = ttk.Scale(frame, from_=lo, to=hi, variable=var, length=200,
                      command=lambda _v: val.config(text=fmt.format(var.get())))
        s.pack(side="left")

    def _spin(self, parent, row, label, var, lo, hi):
        ttk.Label(parent, text=label).grid(row=row, column=0, padx=8, pady=4, sticky="w")
        ttk.Spinbox(parent, from_=lo, to=hi, textvariable=var, width=8).grid(
            row=row, column=1, padx=8, pady=4, sticky="w")

    def _values(self) -> dict:
        device = self.v_device.get()
        if device == tr(self.cfg, "system_default"):
            device = ""
        lang = self.v_language.get()
        if lang == "(auto)":
            lang = ""
        return {
            "ui_language": self.v_ui_language.get(),
            "hotkey": self.v_hotkey.get().strip() or "f9",
            "auto_type": self.v_auto_type.get(),
            "beeps": self.v_beeps.get(),
            "typing_delay": round(self.v_typing_delay.get(), 3),
            "recording": {
                "silence_stop_after": round(self.v_silence_stop.get(), 1),
                "silence_threshold": round(self.v_threshold.get(), 3),
                "initial_timeout": round(self.v_initial_timeout.get(), 1),
                "max_seconds": round(self.v_max_seconds.get(), 1),
                "device": device,
                "stop_with_hotkey": self.v_stop_hotkey.get(),
            },
            "transcription": {
                "model": self.v_model.get(),
                "language": lang,
            },
            "cleanup": {
                "enabled": self.v_cleanup.get(),
                "model": self.v_cleanup_model.get(),
            },
        }

    def _toggle_key_visible(self):
        self.key_entry.config(show="" if self.key_entry.cget("show") else "●")

    # ---- rekam hotkey: tangkap tombol fisik, isi field otomatis ----
    _MODKEYS = {"control_l": "ctrl", "control_r": "ctrl",
                "alt_l": "alt", "alt_r": "alt",
                "shift_l": "shift", "shift_r": "shift"}

    def _start_capture(self):
        self._mods = set()
        self.record_btn.config(text=tr(self.cfg, "press_key_hint"))
        self.root.bind("<KeyPress>", self._cap_press)
        self.root.bind("<KeyRelease>", self._cap_release)
        self.root.focus_force()

    def _stop_capture(self):
        self.root.unbind("<KeyPress>")
        self.root.unbind("<KeyRelease>")
        self.record_btn.config(text=tr(self.cfg, "record_hotkey"))

    def _cap_press(self, event):
        from voice_to_prompt import normalize_captured_key
        ks = event.keysym.lower()
        if ks in self._MODKEYS:
            self._mods.add(self._MODKEYS[ks])
            return "break"
        key = normalize_captured_key(event.keysym, event.char)
        if key is None:  # Esc = batal
            self._mods.clear()
            self._stop_capture()
            return "break"
        if key == "":    # modifier berulang, tunggu tombol sebenarnya
            return "break"
        combo = "+".join(sorted(self._mods) + [key]) if self._mods else key
        # Tolak kombinasi yang tidak dikenali pynput, jangan sampai disimpan
        try:
            from pynput import keyboard as _pk
            from voice_to_prompt import to_pynput_hotkey
            _pk.HotKey.parse(to_pynput_hotkey(combo))
        except Exception:
            self._mods.clear()
            self._stop_capture()
            self.status.config(text=f"Tombol '{combo}' tidak bisa dipakai, coba yang lain.")
            return "break"
        self.v_hotkey.set(combo)
        self._mods.clear()
        self._stop_capture()
        return "break"

    def _cap_release(self, event):
        ks = event.keysym.lower()
        if ks in self._MODKEYS:
            self._mods.discard(self._MODKEYS[ks])
        return "break"

    def _test_key(self):
        cfg = self.cfg
        key = self.v_apikey.get().strip()
        if not key:
            self.key_status.config(text=tr(cfg, "key_empty"), foreground="#b91c1c")
            return
        self.key_status.config(text=tr(cfg, "key_testing"), foreground="#555")
        self.root.update_idletasks()
        try:
            import requests
            resp = requests.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {key}"}, timeout=15)
            if resp.status_code == 200:
                self.key_status.config(text=tr(cfg, "key_valid"), foreground="#15803d")
            elif resp.status_code == 401:
                self.key_status.config(text=tr(cfg, "key_invalid"), foreground="#b91c1c")
            else:
                self.key_status.config(text=tr(cfg, "key_unexpected", code=resp.status_code),
                                       foreground="#b91c1c")
        except Exception as e:
            self.key_status.config(text=tr(cfg, "key_conn_fail", err=e), foreground="#b91c1c")

    def _save(self):
        lang_changed = self.v_ui_language.get() != self.cfg.get("ui_language", "id")
        with open(self.local_path, "wb") as f:
            tomli_w.dump(self._values(), f)
        key = self.v_apikey.get().strip()
        if key:
            with open(self.key_path, "w", encoding="utf-8") as f:
                f.write(key + "\n")
        self.on_save()
        if lang_changed:
            self.status.config(text=tr(self.cfg, "lang_changed_status"))
            self.reopen_requested = True
            self.root.after(500, self.root.destroy)
        else:
            self.status.config(text=tr(self.cfg, "saved_status"))

    def _reset(self):
        if os.path.exists(self.local_path):
            os.remove(self.local_path)
        self.on_save()
        self.status.config(text=tr(self.cfg, "reset_status"))

    def run(self):
        self.root.mainloop()


def open_settings(get_cfg, local_path: str, key_path: str, on_save) -> None:
    """Jalankan jendela settings (panggil di thread sendiri).

    get_cfg: callable yang mengembalikan config TERBARU (supaya ganti bahasa
    bisa membuka ulang jendela dengan string baru).
    """
    while True:
        win = SettingsWindow(get_cfg(), local_path, key_path, on_save)
        win.run()
        if not win.reopen_requested:
            break
