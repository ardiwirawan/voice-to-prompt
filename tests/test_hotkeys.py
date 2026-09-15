"""Pengujian logika hotkey: konversi pynput, normalisasi tangkapan tombol.

Bagian terpenting: memastikan TIDAK ADA tombol yang menghasilkan nilai
yang membuat crash (pelajaran dari bug 'ctrl+slash').

Catatan: tes yang memverifikasi parse pynput ada di test_hotkeys_pynput.py
(skip otomatis di lingkungan headless tanpa X server).
"""
import pytest

from voice_to_prompt import normalize_captured_key, to_pynput_hotkey


@pytest.mark.parametrize("masukan,harapan", [
    ("f9", "<f9>"),
    ("F9", "<f9>"),
    ("ctrl+alt+v", "<ctrl>+<alt>+v"),
    ("alt+ctrl+v", "<alt>+<ctrl>+v"),     # urutan tidak masalah
    ("shift+f5", "<shift>+<f5>"),
    ("pause", "<pause>"),
    ("enter", "<enter>"),
    ("space", "<space>"),
    ("v", "v"),
    ("ctrl+/", "<ctrl>+/"),
    ("win+1", "<cmd>+1"),
])
def test_konversi_pynput(masukan, harapan):
    assert to_pynput_hotkey(masukan) == harapan


# Matriks tombol nyata: (keysym tkinter, char tkinter) -> hotkey internal
MATRIX = [
    ("a", "a", "a"), ("z", "z", "z"),
    ("0", "0", "0"), ("9", "9", "9"),
    ("slash", "/", "/"), ("question", "?", "?"), ("period", ".", "."),
    ("comma", ",", ","), ("semicolon", ";", ";"), ("apostrophe", "'", "'"),
    ("bracketleft", "[", "["), ("bracketright", "]", "]"),
    ("backslash", "\\", "\\"), ("minus", "-", "-"), ("equal", "=", "="),
    ("grave", "`", "`"),
    ("exclam", "!", "!"), ("at", "@", "@"), ("numbersign", "#", "#"),
    ("dollar", "$", "$"), ("percent", "%", "%"), ("asciicircum", "^", "^"),
    ("ampersand", "&", "&"), ("asterisk", "*", "*"),
    ("parenleft", "(", "("), ("parenright", ")", ")"),
    ("underscore", "_", "_"), ("plus", "+", "+"),
    ("braceleft", "{", "{"), ("braceright", "}", "}"),
    ("bar", "|", "|"), ("colon", ":", ":"), ("quotedbl", '"', '"'),
    ("less", "<", "<"), ("greater", ">", ">"), ("asciitilde", "~", "~"),
    ("F1", "", "f1"), ("F9", "", "f9"), ("F12", "", "f12"),
    ("Return", "\r", "enter"), ("Tab", "\t", "tab"), ("space", " ", "space"),
    ("BackSpace", "\x08", "backspace"), ("Delete", "", "delete"),
    ("Insert", "", "insert"), ("Home", "", "home"), ("End", "", "end"),
    ("Prior", "", "page_up"), ("Next", "", "page_down"),
    ("Up", "", "up"), ("Down", "", "down"), ("Left", "", "left"), ("Right", "", "right"),
    ("Pause", "", "pause"), ("Print", "", "print_screen"),
    ("Scroll_Lock", "", "scroll_lock"), ("Caps_Lock", "", "caps_lock"),
    ("KP_Add", "+", "+"), ("KP_Subtract", "-", "-"),
    ("KP_Multiply", "*", "*"), ("KP_Divide", "/", "/"),
    ("KP_Decimal", ".", "."), ("KP_Enter", "\r", "enter"),
]


@pytest.mark.parametrize("keysym,char,harapan", MATRIX)
def test_normalisasi_matriks_lengkap(keysym, char, harapan):
    assert normalize_captured_key(keysym, char) == harapan


def test_modifier_tunggal_belum_lengkap():
    assert normalize_captured_key("Control_L", "") == ""
    assert normalize_captured_key("Shift_R", "") == ""
    assert normalize_captured_key("Alt_L", "") == ""


def test_escape_artinya_batal():
    assert normalize_captured_key("Escape", "\x1b") is None


def test_kombinasi_modifier_plus_tombol_valid():
    """Simulasi alur capture utuh seperti di SettingsWindow:
    modifier dilacak terpisah oleh UI (lihat _MODKEYS), fungsi murni hanya
    untuk tombol terakhir."""
    assert normalize_captured_key("Control_L", "") == ""  # modifier -> tunggu
    key = normalize_captured_key("slash", "/")
    assert key == "/"
    mods = {"ctrl"}   # akumulasi UI
    combo = "+".join(sorted(mods) + [key])
    assert combo == "ctrl+/"