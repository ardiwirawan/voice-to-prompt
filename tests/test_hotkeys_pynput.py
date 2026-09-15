"""Verifikasi parse pynput — butuh X server (Linux desktop).

Di lingkungan headless (CI tanpa display) pynput MENGIMPORT pynput.keyboard
lalu melempar di tengah jalan. `pytest.importorskip` tidak menangkap error
jenis itu, jadi dipakai try/except manual + skipif.
"""
import pytest

try:
    from pynput import keyboard
    PYNPUT_OK = True
except Exception:  # ImportError / X-display error di headless
    keyboard = None
    PYNPUT_OK = False

from voice_to_prompt import normalize_captured_key, to_pynput_hotkey  # noqa: E402

from test_hotkeys import MATRIX  # noqa: E402

pytestmark = pytest.mark.skipif(not PYNPUT_OK, reason="pynput membutuhkan X server (headless)")


@pytest.mark.parametrize("nama,harapan", [
    ("f9", "<f9>"), ("ctrl+alt+v", "<ctrl>+<alt>+v"),
])
def test_hasil_normalisasi_selalu_bisa_di_parse(nama, harapan):
    """Regresi: nilai dari capture harus selalu valid untuk pynput."""
    assert to_pynput_hotkey(nama) == harapan
    keyboard.HotKey.parse(to_pynput_hotkey(nama))   # tidak boleh raise


@pytest.mark.parametrize("keysym,char", [(k, c) for k, c, _ in MATRIX])
def test_matriks_tidak_pernah_crash_di_pynput(keysym, char):
    """Regresi besar: SETIAP tombol dari matriks harus menghasilkan nilai
    yang bisa di-parse pynput (pelajaran bug 'ctrl+slash')."""
    hasil = normalize_captured_key(keysym, char)
    assert hasil is not None and hasil != ""
    keyboard.HotKey.parse(to_pynput_hotkey(hasil))   # tidak boleh raise


def test_kombinasi_modifier_hasilnya_valid_di_pynput():
    assert normalize_captured_key("Control_L", "") == ""
    key = normalize_captured_key("slash", "/")
    combo = "+".join(sorted(["ctrl"]) + [key])
    assert combo == "ctrl+/"
    keyboard.HotKey.parse(to_pynput_hotkey(combo))