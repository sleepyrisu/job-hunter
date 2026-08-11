"""
Resume scanner - extracts search keywords from resume.
Uses pure Python parser first, optionally agy AI for enhancement.
"""
import json
import os
import re

DIRECTORY = os.path.dirname(os.path.abspath(__file__))
RESUME_PATH = os.path.join(DIRECTORY, "resume.md")
SETTINGS_PATH = os.path.join(DIRECTORY, "settings.json")


def _find_agy():
    import shutil
    p = shutil.which("agy")
    if p:
        return p
    for c in [os.path.expanduser(r"~\AppData\Local\agy\bin\agy.exe"),
              os.path.expanduser(r"~\AppData\Local\agy\bin\agy")]:
        if os.path.isfile(c):
            return c
    return None


def generate_keywords_from_resume(file_path=None):
    """Parse resume and generate search keywords. Pure Python, no AI needed."""
    from resume_parser import parse_resume
    path = file_path or RESUME_PATH
    if not os.path.exists(path):
        return None
    parsed = parse_resume(path)
    if "error" in parsed:
        return None
    return parsed


def generate_keywords_with_agy(file_path=None):
    """Use agy AI to enhance keywords (optional)."""
    agy = _find_agy()
    if not agy:
        return None
    from resume_parser import read_resume
    path = file_path or RESUME_PATH
    if not os.path.exists(path):
        return None
    text = read_resume(path)
    if not text:
        return None

    import subprocess  # nosec B404
    prompt = f"""Read this resume and suggest 12 BEST job search keywords for Indeed/LinkedIn Malaysia.

CRITICAL:
- Education level affects targeting: Diploma = Junior/Entry Level, Bachelor = can go higher
- Target Penang-based roles, KL transfer paths possible
- Include level prefixes: "Junior", "Entry Level", "Fresh Graduate", "Trainee"
- Malaysia ONLY (Penang, KL). NO Singapore or overseas.

Return ONLY a JSON array of 12 strings, no other text:

Resume:
{text[:3000]}"""
    # Fixed argv list, shell=False - prompt text cannot inject commands.
    try:
        r = subprocess.run(  # nosec B603
            [agy, "--dangerously-skip-permissions", "-p", prompt, "--model", "gemini-3.6-flash-high"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ}
        )
        text_out = r.stdout.strip()
        if text_out.startswith("```"):
            text_out = re.sub(r"^```(?:json)?\s*", "", text_out)
            text_out = re.sub(r"\s*```$", "", text_out)
        data = json.loads(text_out)
        if isinstance(data, list) and len(data) > 0:
            return {"keywords": data[:12], "locations": ["Penang, Malaysia", "Pulau Pinang"], "source": "agy"}
    except Exception:
        # agy absence/parse failure falls back to rule-based keywords.
        pass  # nosec B110
    return None


def update_settings(keywords, locations=None):
    """Write keywords and locations into settings.json."""
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            settings = json.load(f)
    except Exception:
        settings = {}

    if "search" not in settings:
        settings["search"] = {}
    settings["search"]["keywords"] = keywords
    if locations:
        settings["search"]["locations"] = locations

    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def sync_from_resume(file_path=None, use_agy=False):
    """
    Scan resume and update settings with generated keywords.
    Returns summary dict.
    Pure Python parser is always used. agy is optional enhancement.
    """
    result = {"success": True, "source": "parser"}

    # Try agy first if requested
    if use_agy:
        agy_result = generate_keywords_with_agy(file_path)
        if agy_result:
            keywords = agy_result["keywords"]
            locations = agy_result.get("locations", ["Penang, Malaysia"])
            update_settings(keywords, locations)
            result["keywords"] = keywords
            result["locations"] = locations
            result["source"] = "agy"
            return result

    # Fall back to pure Python parser
    parsed = generate_keywords_from_resume(file_path)
    if not parsed:
        return {"success": False, "error": "Could not parse resume"}

    keywords = parsed.get("keywords", [])
    locations = parsed.get("locations", ["Penang, Malaysia"])

    if not keywords:
        keywords = ["Junior Developer", "Entry Level IT", "Trainee Programmer"]

    update_settings(keywords, locations)

    result["keywords"] = keywords
    result["locations"] = locations
    result["name"] = parsed.get("name", "")
    result["education"] = parsed.get("education", "")
    result["skills"] = parsed.get("skills", [])
    return result


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    r = sync_from_resume(path, use_agy=False)
    print(json.dumps(r, ensure_ascii=False, indent=2))
