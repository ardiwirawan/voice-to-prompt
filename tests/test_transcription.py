"""Pengujian kunci API dan transkripsi/cleanup (semua jalur HTTP di-mock)."""
import pytest

from voice_to_prompt import cleanup_text, load_api_key, transcribe_groq


class FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def test_kunci_dari_env_menang_atas_file(monkeypatch, tmp_path):
    f = tmp_path / "groq_key.txt"
    f.write_text("kunci-dari-file", encoding="utf-8")
    monkeypatch.setenv("GROQ_API_KEY", "kunci-dari-env")
    cfg = {"transcription": {"api_key_env": "GROQ_API_KEY",
                             "api_key_file": f.name}}
    assert load_api_key(cfg, str(tmp_path)) == "kunci-dari-env"


def test_kunci_dari_file_saat_env_kosong(monkeypatch, tmp_path):
    f = tmp_path / "groq_key.txt"
    f.write_text("kunci-dari-file", encoding="utf-8")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    cfg = {"transcription": {"api_key_env": "GROQ_API_KEY",
                             "api_key_file": f.name}}
    assert load_api_key(cfg, str(tmp_path)) == "kunci-dari-file"


def test_kunci_kosong_saat_tidak_ada_mana_mana(monkeypatch, tmp_path):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    cfg = {"transcription": {"api_key_env": "GROQ_API_KEY",
                             "api_key_file": "tidak-ada.txt"}}
    assert load_api_key(cfg, str(tmp_path)) == ""


def test_transcribe_groq_sukses(monkeypatch):
    def fake_post(url, headers, files, data, timeout):
        assert data["model"] == "whisper-large-v3"
        return FakeResponse(200, {"text": " halo dunia "})
    import requests
    monkeypatch.setattr(requests, "post", fake_post)
    cfg = {"transcription": {"model": "whisper-large-v3", "language": ""}}
    assert transcribe_groq(b"WAV", cfg, "k") == "halo dunia"


def test_transcribe_groq_ikut_language(monkeypatch):
    def fake_post(url, headers, files, data, timeout):
        assert data["language"] == "id"
        return FakeResponse(200, {"text": "x"})
    import requests
    monkeypatch.setattr(requests, "post", fake_post)
    cfg = {"transcription": {"model": "m", "language": "id"}}
    assert transcribe_groq(b"WAV", cfg, "k") == "x"


def test_transcribe_groq_error_dinaikkan(monkeypatch):
    def fake_post(*a, **kw):
        return FakeResponse(429, text="rate limit")
    import requests
    monkeypatch.setattr(requests, "post", fake_post)
    cfg = {"transcription": {"model": "m", "language": ""}}
    with pytest.raises(RuntimeError):
        transcribe_groq(b"WAV", cfg, "k")


def test_cleanup_sukses(monkeypatch):
    def fake_post(url, headers, json, timeout):
        assert json["temperature"] == 0
        return FakeResponse(200, {"choices": [{"message": {"content": " Teks rapi. "}}]})
    import requests
    monkeypatch.setattr(requests, "post", fake_post)
    cfg = {"cleanup": {"enabled": True, "model": "qwen/x"}}
    assert cleanup_text("ee raw", cfg, "k") == "Teks rapi."


def test_cleanup_gagal_kembali_ke_teks_mentah(monkeypatch):
    """Prinsip: kegagalan cleanup tidak boleh menghilangkan teks user."""
    def fake_post(*a, **kw):
        return FakeResponse(500, text="boom")
    import requests
    monkeypatch.setattr(requests, "post", fake_post)
    cfg = {"cleanup": {"enabled": True, "model": "qwen/x"}}
    assert cleanup_text("teks mentah", cfg, "k") == "teks mentah"


def test_cleanup_off_tidak_memanggil_api(monkeypatch):
    def fake_post(*a, **kw):
        raise AssertionError("cleanup mati tapi API tetap dipanggil")
    import requests
    monkeypatch.setattr(requests, "post", fake_post)
    cfg = {"cleanup": {"enabled": False, "model": "qwen/x"}}
    assert cleanup_text("teks", cfg, "k") == "teks"