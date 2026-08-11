"""Tests for the pure-Python resume parser."""
import resume_parser

RESUME_TEXT = """LEE SONG JUN
Data Analyst
lee.songjun@example.com

## Target Roles
Target Role: Data Analyst, RPA Developer

## Technical Skills
- Languages: Python, SQL, C#
- Tools: Power Automate, RPA
- Data: Data Analysis

## Experience
2 years of professional experience as Data Analyst at Nexa Analytics

## Education
Diploma in Computer Science

## Preferred Locations
- Penang, Malaysia
- Kuala Lumpur, Malaysia
"""


def _write_md(tmp_path, content=RESUME_TEXT):
    path = tmp_path / "resume.md"
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_read_resume_markdown(tmp_path):
    path = _write_md(tmp_path)
    assert resume_parser.read_resume(path).startswith("LEE SONG JUN")


def test_read_resume_unknown_extension(tmp_path):
    path = tmp_path / "resume.txt"
    path.write_text("plain text", encoding="utf-8")
    assert resume_parser.read_resume(str(path)) == ""


def test_read_resume_missing_pdf_returns_empty(tmp_path):
    assert resume_parser.read_resume(str(tmp_path / "missing.pdf")) == ""


def test_read_resume_missing_docx_returns_empty(tmp_path):
    assert resume_parser.read_resume(str(tmp_path / "missing.docx")) == ""


def test_parse_resume_returns_structured_data(tmp_path):
    parsed = resume_parser.parse_resume(_write_md(tmp_path))
    assert "error" not in parsed
    assert parsed["name"] == "LEE SONG JUN"
    assert parsed["email"] == "lee.songjun@example.com"
    assert parsed["education"] == "Diploma"
    assert parsed["experience_years"] == 2
    assert "Python" in parsed["skills"]
    assert "Power Automate" in parsed["skills"]
    assert any("RPA" in k for k in parsed["keywords"])
    assert "Penang, Malaysia" in parsed["locations"]
    assert parsed["sections"]["skills"]


def test_parse_resume_empty_file_returns_error(tmp_path):
    path = tmp_path / "empty.md"
    path.write_text("", encoding="utf-8")
    assert "error" in resume_parser.parse_resume(str(path))


def test_extract_section_returns_missing_empty():
    assert resume_parser.extract_section("no headings here", "Skills") == ""


def test_generate_search_keywords_diploma_prefix(tmp_path):
    parsed = resume_parser.parse_resume(_write_md(tmp_path))
    assert any(k.startswith("Junior") for k in parsed["keywords"])


def test_extract_education_phd_and_master():
    assert resume_parser.extract_education("PhD in Computer Science") == "PhD"
    assert resume_parser.extract_education("Master of Engineering") == "Master"
    assert resume_parser.extract_education("something nothing") == "Unknown"