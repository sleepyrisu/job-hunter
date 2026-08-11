"""Additional tests for config env overrides, placeholder normalization, and validate_config."""
import json

import config

_AI_EMPTY = {
    "ai": {"api_key": "", "gemini_api_key": "", "base_url": "",
           "model": "", "agnes_api_key": "", "agnes_base_url": ""}
}


def _write_settings(tmp_path, data):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def _clean_env(monkeypatch):
    for var in ("AI_API_KEY", "AI_BASE_URL", "AI_MODEL", "AGNES_API_KEY", "AGNES_BASE_URL",
                "GEMINI_API_KEY", "EMAIL_SENDER", "EMAIL_PASSWORD", "EMAIL_RECEIVER",
                "SEARCH_KEYWORDS", "LOCATIONS", "MATCH_THRESHOLD", "USE_AI", "DASHBOARD_TOKEN"):
        monkeypatch.delenv(var, raising=False)


def test_top_level_non_dict_section_falls_back(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setattr(config, "SETTINGS_FILE", _write_settings(tmp_path, {
        "search": {"keywords": ["Only Me"]},
        "scheduler": "not a dict",
    }))
    settings = config.load_settings()
    assert settings["scheduler"] == "not a dict"
    assert settings["search"]["keywords"] == ["Only Me"]


def test_invalid_json_settings_prints_and_uses_defaults(tmp_path, monkeypatch, capsys):
    _clean_env(monkeypatch)
    path = tmp_path / "settings.json"
    path.write_text("{not valid json!!!", encoding="utf-8")
    monkeypatch.setattr(config, "SETTINGS_FILE", str(path))
    settings = config.load_settings()
    assert "Error reading settings.json" in capsys.readouterr().out
    assert settings["preferences"]["use_ai"] is False


def test_env_overrides_ai_fields(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setattr(config, "SETTINGS_FILE", _write_settings(tmp_path, _AI_EMPTY))
    monkeypatch.setenv("AI_API_KEY", "env-api-key")
    monkeypatch.setenv("AI_BASE_URL", "https://env.example/v1")
    monkeypatch.setenv("AI_MODEL", "env-model")
    monkeypatch.setenv("AGNES_API_KEY", "env-agnes-key")
    monkeypatch.setenv("AGNES_BASE_URL", "https://env-agnes.example/v1")
    settings = config.load_settings()
    assert settings["ai"]["api_key"] == "env-api-key"
    assert settings["ai"]["base_url"] == "https://env.example/v1"
    assert settings["ai"]["model"] == "env-model"
    assert settings["ai"]["agnes_api_key"] == "env-agnes-key"
    assert settings["ai"]["agnes_base_url"] == "https://env-agnes.example/v1"


def test_env_overrides_search_keywords_and_locations(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setattr(config, "SETTINGS_FILE", _write_settings(tmp_path, {
        "search": {"keywords": [], "locations": []}
    }))
    monkeypatch.setenv("SEARCH_KEYWORDS", "Data Analyst, RPA Developer, ")
    monkeypatch.setenv("LOCATIONS", "Penang, Malaysia")
    settings = config.load_settings()
    assert settings["search"]["keywords"] == ["Data Analyst", "RPA Developer"]
    assert settings["search"]["locations"] == ["Penang", "Malaysia"]


def test_match_threshold_non_numeric_ignored(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setattr(config, "SETTINGS_FILE", _write_settings(tmp_path, {}))
    monkeypatch.setenv("MATCH_THRESHOLD", "abc")
    settings = config.load_settings()
    assert settings["preferences"]["match_threshold"] == 80


def test_email_env_enables_notifications(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setattr(config, "SETTINGS_FILE", _write_settings(tmp_path, {}))
    monkeypatch.setenv("EMAIL_SENDER", "me@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "s3cret")
    monkeypatch.setenv("EMAIL_RECEIVER", "you@example.com")
    settings = config.load_settings()
    assert settings["notifications"]["email_enabled"] is True
    assert settings["notifications"]["email_sender"] == "me@example.com"
    assert settings["notifications"]["email_password"] == "s3cret"
    assert settings["notifications"]["email_receiver"] == "you@example.com"


def test_validate_config_warns_when_ai_has_no_key(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    settings = {"preferences": {"use_ai": True}}
    settings.update(_AI_EMPTY)
    monkeypatch.setattr(config, "SETTINGS_FILE", _write_settings(tmp_path, settings))
    warnings = config.validate_config()
    assert any("no AI API key" in w for w in warnings)


def test_validate_config_warns_email_placeholders(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    settings = {
        "preferences": {"use_ai": True},
        "ai": {"api_key": "AIzaSy-0123456789abcdefghijklmnopqrstuv", "gemini_api_key": "",
               "agnes_api_key": ""},
        "notifications": {"email_enabled": True, "email_sender": "your_email@gmail.com",
                          "email_password": "changeme"},
    }
    monkeypatch.setattr(config, "SETTINGS_FILE", _write_settings(tmp_path, settings))
    warnings = config.validate_config()
    assert any("EMAIL_SENDER" in w for w in warnings)
    assert any("EMAIL_PASSWORD" in w for w in warnings)
    assert not any("no AI API key" in w for w in warnings)


def test_placeholder_normalization_for_gemini_key(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    realsettings = {
        "ai": {"api_key": "changeme", "gemini_api_key": "your_api_key_here"}
    }
    monkeypatch.setattr(config, "SETTINGS_FILE", _write_settings(tmp_path, realsettings))
    settings = config.load_settings()
    assert settings["ai"]["api_key"] == ""
    assert settings["ai"]["gemini_api_key"] == ""