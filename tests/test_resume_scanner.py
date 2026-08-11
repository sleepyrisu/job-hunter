"""Tests for the resume scanner (keyword generation + settings sync). No real agy CLI is invoked."""
import json
import sys

import resume_scanner

RESUME_TEXT = """LEE SONG JUN
Data Analyst

## Technical Skills
- Python, SQL, Power Automate, RPA

## Experience
2 years of professional experience

## Education
Diploma in Computer Science

## Preferred Locations
Penang, Malaysia
"""


def _write_md(tmp_path):
    path = tmp_path / "resume.md"
    path.write_text(RESUME_TEXT, encoding="utf-8")
    return str(path)


def test_generate_keywords_from_resume_success(tmp_path):
    parsed = resume_scanner.generate_keywords_from_resume(_write_md(tmp_path))
    assert parsed is not None
    assert isinstance(parsed.get("keywords", []), list)
    assert parsed["keywords"]
    assert parsed["name"] == "LEE SONG JUN"


def test_generate_keywords_from_resume_missing_file_returns_none(tmp_path):
    assert resume_scanner.generate_keywords_from_resume(str(tmp_path / "nope.md")) is None


def test_generate_keywords_from_resume_missing_default_path(tmp_path, monkeypatch):
    monkeypatch.setattr(resume_scanner, "RESUME_PATH", str(tmp_path / "nope.md"))
    assert resume_scanner.generate_keywords_from_resume() is None


def test_generate_keywords_with_agy_no_binary(tmp_path, monkeypatch):
    monkeypatch.setattr(resume_scanner, "_find_agy", lambda: None)
    assert resume_scanner.generate_keywords_with_agy(_write_md(tmp_path)) is None


def _fake_subprocess_cls(result=None, error=None):
    class _FakeCompleted:
        def __init__(self, stdout, stderr="", returncode=0):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    class _FakeModule:
        def run(self, *args, **kwargs):
            if error is not None:
                raise error
            return _FakeCompleted(stdout=result)

    return _FakeModule()


def test_generate_keywords_with_agy_success(tmp_path, monkeypatch):
    keywords = ["Junior Data Analyst", "Junior RPA Developer"]
    monkeypatch.setattr(resume_scanner, "_find_agy", lambda: "fake-agy.exe")
    monkeypatch.setitem(sys.modules, "subprocess",
                        _fake_subprocess_cls(result=json.dumps(keywords)))
    result = resume_scanner.generate_keywords_with_agy(_write_md(tmp_path))
    assert result is not None
    assert result["source"] == "agy"
    assert result["keywords"] == keywords


def test_generate_keywords_with_agy_strips_fences(tmp_path, monkeypatch):
    monkeypatch.setattr(resume_scanner, "_find_agy", lambda: "fake-agy.exe")
    monkeypatch.setitem(sys.modules, "subprocess",
                        _fake_subprocess_cls(result='```json\n["Junior Analyst"]\n```'))
    result = resume_scanner.generate_keywords_with_agy(_write_md(tmp_path))
    assert result["keywords"] == ["Junior Analyst"]


def test_generate_keywords_with_agy_error_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(resume_scanner, "_find_agy", lambda: "fake-agy.exe")
    monkeypatch.setitem(sys.modules, "subprocess",
                        _fake_subprocess_cls(error=RuntimeError("boom")))
    assert resume_scanner.generate_keywords_with_agy(_write_md(tmp_path)) is None


def test_update_settings_round_trip(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"search": {"keywords": ["Old"]}}), encoding="utf-8")
    monkeypatch.setattr(resume_scanner, "SETTINGS_PATH", str(settings_path))
    resume_scanner.update_settings(["Junior Data Analyst"], ["Penang, Malaysia"])
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["search"]["keywords"] == ["Junior Data Analyst"]
    assert settings["search"]["locations"] == ["Penang, Malaysia"]


def test_update_settings_creates_file_if_missing(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(resume_scanner, "SETTINGS_PATH", str(settings_path))
    resume_scanner.update_settings(["A"], ["Penang"])
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["search"]["keywords"] == ["A"]


def test_sync_from_resume_success_path(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(resume_scanner, "SETTINGS_PATH", str(settings_path))
    result = resume_scanner.sync_from_resume(_write_md(tmp_path))
    assert result["success"] is True
    assert result["source"] == "parser"
    assert result["keywords"]
    assert result["name"] == "LEE SONG JUN"
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["search"]["keywords"] == result["keywords"]


def test_sync_from_resume_failed_parse(tmp_path, monkeypatch):
    monkeypatch.setattr(resume_scanner, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    result = resume_scanner.sync_from_resume(str(tmp_path / "missing.md"))
    assert result["success"] is False
    assert "Could not parse" in result["error"]


def test_sync_from_resume_agy_unavailable_falls_back_to_parser(tmp_path, monkeypatch):
    monkeypatch.setattr(resume_scanner, "_find_agy", lambda: None)
    monkeypatch.setattr(resume_scanner, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    result = resume_scanner.sync_from_resume(_write_md(tmp_path), use_agy=True)
    assert result["success"] is True
    assert result["source"] == "parser"


def test_sync_from_resume_agy_success_updates_settings(tmp_path, monkeypatch):
    keywords = ["Junior Data Analyst"]
    monkeypatch.setattr(resume_scanner, "_find_agy", lambda: "fake-agy.exe")
    monkeypatch.setitem(sys.modules, "subprocess",
                        _fake_subprocess_cls(result=json.dumps(keywords)))
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(resume_scanner, "SETTINGS_PATH", str(settings_path))
    result = resume_scanner.sync_from_resume(_write_md(tmp_path), use_agy=True)
    assert result["source"] == "agy"
    assert result["keywords"] == keywords
    assert (tmp_path / "settings.json").exists()
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["search"]["keywords"] == keywords