"""Pengujian konfigurasi: default, config.toml, dan override config.local.toml."""
import tomli_w
import pytest

from voice_to_prompt import DEFAULT_CONFIG, _deep_merge, load_config


def test_default_ketika_tidak_ada_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)   # cwd bersih: tidak ada config.toml di mana pun
    cfg, cfg_dir, base, local = load_config([])
    assert cfg["hotkey"] == "f9"
    assert cfg["ui_language"] == "en"      # default English untuk pasar global
    assert cfg["cleanup"]["enabled"] is True
    assert cfg["recording"]["stop_with_hotkey"] is True
    assert local == str(tmp_path / "config.local.toml")


def test_load_config_dari_file(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text('hotkey = "f8"\n[transcription]\nmodel = "whisper-large-v3-turbo"\n',
                        encoding="utf-8")
    cfg, *_ = load_config(["--config", str(cfg_path)])
    assert cfg["hotkey"] == "f8"
    assert cfg["transcription"]["model"] == "whisper-large-v3-turbo"
    # field lain tetap bawaan
    assert cfg["auto_type"] is True
    assert cfg["recording"]["sample_rate"] == 16000


def test_override_config_local_toml(tmp_path):
    base = tmp_path / "config.toml"
    base.write_text('hotkey = "f9"\n', encoding="utf-8")
    local = tmp_path / "config.local.toml"
    with open(local, "wb") as f:
        tomli_w.dump({"recording": {"silence_stop_after": 4.5}, "hotkey": "f8"}, f)

    cfg, *_ = load_config(["--config", str(base)])
    assert cfg["hotkey"] == "f8"
    assert cfg["recording"]["silence_stop_after"] == 4.5
    assert cfg["recording"]["sample_rate"] == 16000    # bawaan tetap


def test_tanpa_local_override(tmp_path):
    base = tmp_path / "config.toml"
    base.write_text("hotkey = \"f9\"\n", encoding="utf-8")
    cfg, *_ = load_config(["--config", str(base)])
    assert cfg["recording"]["silence_stop_after"] == 2.0


def test_deep_merge_tidak_memutasikan_base():
    base = {"a": 1, "nested": {"x": 1, "y": 2}}
    hasil = _deep_merge(base, {"nested": {"y": 9}, "b": 3})
    assert hasil == {"a": 1, "nested": {"x": 1, "y": 9}, "b": 3}
    assert base == {"a": 1, "nested": {"x": 1, "y": 2}}   # tidak berubah


def test_config_toml_asli_valid(tmp_path):
    # config.toml yang dikirim bersama proyek harus valid tomllib
    import tomllib
    from pathlib import Path
    proyek = Path(__file__).resolve().parent.parent
    with open(proyek / "config.toml", "rb") as f:
        data = tomllib.load(f)
    assert data["hotkey"] == "f9"
    assert data["cleanup"]["model"].startswith("qwen/")


def test_default_config_lengkap_untuk_kode():
    """Setiap kunci yang dipakai kode harus ada di DEFAULT_CONFIG."""
    r = DEFAULT_CONFIG["recording"]
    for k in ("sample_rate", "channels", "silence_threshold", "silence_stop_after",
              "initial_timeout", "min_seconds", "max_seconds", "device",
              "stop_with_hotkey"):
        assert k in r, f"recording.{k} hilang"
    t = DEFAULT_CONFIG["transcription"]
    assert all(k in t for k in ("engine", "model", "language", "api_key_env", "api_key_file"))
    assert DEFAULT_CONFIG["cleanup"]["model"], "cleanup.model harus terisi"