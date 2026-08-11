"""Tests for config: settings loading, env overrides, placeholder handling."""
import json
import os

import config

MISSING = os.path.join(os.path.dirname(os.path.abspath(config.__file__)), "tests", "fixtures", "missing.json")


def test_use_ai_defaults_off():
    settings = config.load_settings()
    assert settings["preferences"]["use_ai"] is False


def test_validate_config_silent_when_ai_off():
    assert config.validate_config() == []


def test_placeholder_api_keys_normalized_to_empty(tmp_path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "ai": {"api_key": "your_api_key_here", "gemini_api_key": "changeme"},
    }), encoding="utf-8")
    monkeypatch.setattr(config, "SETTINGS_FILE", str(settings_file))
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings = config.load_settings()
    assert settings["ai"]["api_key"] == ""
    assert settings["ai"]["gemini_api_key"] == ""


def test_env_override_use_ai(monkeypatch):
    monkeypatch.delenv("USE_AI", raising=False)
    monkeypatch.setattr(config, "SETTINGS_FILE", MISSING)
    monkeypatch.setenv("USE_AI", "true")
    assert config.load_settings()["preferences"]["use_ai"] is True


def test_env_override_match_threshold(monkeypatch):
    monkeypatch.delenv("MATCH_THRESHOLD", raising=False)
    monkeypatch.setattr(config, "SETTINGS_FILE", MISSING)
    monkeypatch.setenv("MATCH_THRESHOLD", "65")
    assert config.load_settings()["preferences"]["match_threshold"] == 65


def test_is_placeholder():
    assert config.is_placeholder("")
    assert config.is_placeholder("your_api_key_here")
    assert config.is_placeholder("changeme123")
    assert not config.is_placeholder("AIzaSy-real-key-abc")
