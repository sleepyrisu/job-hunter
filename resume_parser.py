"""
Pure Python resume parser - extracts keywords, skills, experience from resumes.
Supports: .md, .pdf, .docx files. No AI/API needed.
"""
import re
from pathlib import Path


def read_resume(file_path):
    """Read resume file and return text content."""
    ext = Path(file_path).suffix.lower()
    if ext == ".md":
        with open(file_path, encoding="utf-8") as f:
            return f.read()
    elif ext == ".pdf":
        return _read_pdf(file_path)
    elif ext in (".docx", ".doc"):
        return _read_docx(file_path)
    return ""


def _read_pdf(file_path):
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
        return text
    except Exception as e:
        print(f"PDF read error: {e}")
        return ""


def _read_docx(file_path):
    try:
        import docx
        doc = docx.Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception as e:
        print(f"DOCX read error: {e}")
        return ""


# ============================================================
# Section extraction
# ============================================================

def extract_section(text, heading_pattern):
    """Extract content under a markdown heading matching the pattern."""
    m = re.search(
        rf"#+\s*{heading_pattern}\s*\n(.*?)(?=\n##\s|\Z)",
        text, re.IGNORECASE | re.DOTALL
    )
    return m.group(1).strip() if m else ""


def extract_target_roles(text):
    """Extract target roles from 'Target Roles' or 'Job Search Preferences' section."""
    section = extract_section(text, r"(?:Target Roles|Job Search Preferences|Job Titles?|Desired Roles?)")
    if section:
        lines = section.split("\n")
        for line in lines:
            if "target role" in line.lower() or "desired" in line.lower():
                # Try to extract comma-separated list
                m = re.search(r":\s*(.+)", line)
                if m:
                    return [r.strip().lstrip("- *") for r in m.group(1).split(",") if r.strip()]
        # If no explicit list, try bullet points
        roles = []
        for line in lines:
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                roles.append(line[2:].strip().lstrip("- *"))
        return roles
    return []


def extract_skills(text):
    """Extract technical skills from resume."""
    # Try to find Technical Skills section
    section = extract_section(text, r"(?:Technical Skills?|Skills?|Technologies?|Tech Stack)")
    if section:
        skills = []
        for line in section.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                skill = line[2:].strip().lstrip("- *")
                # Handle comma-separated within a line
                if ":" in skill:
                    skill = skill.split(":", 1)[1]
                skills.extend([s.strip() for s in skill.split(",") if s.strip()])
            elif ":" in line:
                # e.g. "Languages: C++, Python, Java"
                parts = line.split(":", 1)
                skills.extend([s.strip() for s in parts[1].split(",") if s.strip()])
        return skills

    # Fallback: look for skill keywords in the whole text
    common_skills = [
        "python", "java", "c#", "c++", "javascript", "html", "css", "sql", "mysql",
        "react", "vue", "angular", "node.js", "django", "flask", "fastapi",
        "aws", "azure", "gcp", "docker", "kubernetes", "linux", "git",
        "power automate", "uipath", "rpa", "power bi", "tableau",
        "machine learning", "tensorflow", "pytorch", "data analysis",
        "excel", "pandas", "numpy", "scikit-learn", ".net", "dotnet",
    ]
    text_lower = text.lower()
    return [s for s in common_skills if s in text_lower]


def extract_experience_years(text):
    """Extract total years of experience from text."""
    patterns = [
        r"(\d+)[\+]?\s*years?\s*(?:of\s+)?(?:experience|work|professional)",
        r"experience[:\s]*(\d+)[\+]?\s*years?",
        r"(\d+)\+?\s*yr",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return 0


def extract_education(text):
    """Extract education level from resume."""
    text_lower = text.lower()
    if any(kw in text_lower for kw in ["phd", "ph.d", "doctorate", "doctoral"]):
        return "PhD"
    if any(kw in text_lower for kw in ["master", "m.s.", "m.sc.", "mba", "meng"]):
        return "Master"
    if any(kw in text_lower for kw in ["bachelor", "b.s.", "b.sc.", "b.eng", "degree", "b.a."]):
        return "Bachelor"
    if any(kw in text_lower for kw in ["diploma", "associate", "hnd"]):
        return "Diploma"
    return "Unknown"


def extract_location(text):
    """Extract preferred location from resume."""
    section = extract_section(text, r"(?:Preferred Locations?|Location|Work Location|Job Location)")
    if section:
        lines = [line.strip().lstrip("- *") for line in section.split("\n") if line.strip()]
        for line in lines:
            low = line.lower()
            if "penang" in low:
                return "Penang, Malaysia"
            if "kl" in low or "kuala lumpur" in low:
                return "Kuala Lumpur, Malaysia"
            if "singapore" in low:
                return "Singapore"
            if "remote" in low:
                return "Remote"
    # Fallback
    text_lower = text.lower()
    if "penang" in text_lower:
        return "Penang, Malaysia"
    if "kuala lumpur" in text_lower or "kl" in text_lower:
        return "Kuala Lumpur, Malaysia"
    if "singapore" in text_lower:
        return "Singapore"
    if "remote" in text_lower:
        return "Remote"
    return "Malaysia"


def generate_search_keywords(text):
    """
    Generate search keywords from resume text.
    Returns (keywords, locations) tuple.
    Pure Python, no AI needed.
    """
    target_roles = extract_target_roles(text)
    skills = extract_skills(text)
    education = extract_education(text)
    exp_years = extract_experience_years(text)
    location = extract_location(text)

    # Determine level prefix
    if education in ("Diploma", "Associate") or exp_years <= 1:
        level_prefixes = ["Junior", "Entry Level", "Fresh Graduate", "Trainee"]
    elif exp_years <= 3:
        level_prefixes = ["Junior", "Associate"]
    else:
        level_prefixes = [""]

    # Build keywords from target roles + skills
    keywords = []

    # Add target roles with level prefixes
    for role in target_roles:
        for prefix in level_prefixes[:2]:  # Use first 2 prefixes
            kw = f"{prefix} {role}" if prefix else role
            if kw not in keywords:
                keywords.append(kw)

    # Add skill-based roles
    skill_to_role = {
        "python": ["Python Developer", "Python Programmer"],
        "java": ["Java Developer"],
        "c#": ["C# Developer", ".NET Developer"],
        "javascript": ["Frontend Developer", "Web Developer"],
        "sql": ["Data Analyst", "Database Developer"],
        "power automate": ["RPA Developer", "Automation Engineer"],
        "uipath": ["RPA Developer"],
        "rpa": ["RPA Developer", "Automation Engineer"],
        "data analysis": ["Data Analyst"],
        "machine learning": ["ML Engineer", "Data Scientist"],
    }

    for skill in skills:
        skill_lower = skill.lower()
        for known_skill, roles in skill_to_role.items():
            if known_skill in skill_lower:
                for role in roles:
                    for prefix in level_prefixes[:1]:
                        kw = f"{prefix} {role}" if prefix else role
                        if kw not in keywords:
                            keywords.append(kw)

    # Ensure we have at least some keywords
    if not keywords:
        keywords = ["Junior Developer", "Entry Level IT", "Trainee Programmer"]

    # Build locations
    locations = ["Penang, Malaysia"]
    if location and "Penang" not in location:
        locations.insert(0, location)
    # Add KL if mentioned
    text_lower = text.lower()
    if "kuala lumpur" in text_lower or "kl" in text_lower:
        locations.append("Kuala Lumpur, Malaysia")

    return keywords[:12], locations[:4]


# ============================================================
# Convenience function
# ============================================================

def parse_resume(file_path):
    """
    Parse a resume file and return structured data.
    Returns dict with: name, email, phone, education, skills, keywords, locations, raw_text
    """
    text = read_resume(file_path)
    if not text:
        return {"error": "Could not read file"}

    # Extract email
    email_m = re.search(r"[\w.-]+@[\w.-]+\.\w+", text)
    email = email_m.group(0) if email_m else ""

    # Extract phone
    phone_m = re.search(r"\+?[\d\s-]{8,15}", text)
    phone = phone_m.group(0).strip() if phone_m else ""

    # Extract name (first line that looks like a name)
    lines = text.strip().split("\n")
    name = ""
    for line in lines[:5]:
        line = line.strip()
        if line and not line.startswith("#") and "@" not in line and len(line) < 50:
            name = line
            break

    education = extract_education(text)
    skills = extract_skills(text)
    exp_years = extract_experience_years(text)
    keywords, locations = generate_search_keywords(text)

    # Extract sections for section-aware matching
    sections = {
        "skills": extract_section(text, r"(?:Skills?|Technical(?:\s+Skills?)?|Technologies|Competencies|Tech Stack)"),
        "experience": extract_section(
            text,
            r"(?:Experience|Work(?:\s+Experience)?|Employment|"
            r"Professional(?:\s+Experience)?|Career)",
        ),
        "education": extract_section(text, r"(?:Education|Academic|Qualifications|Degrees?)"),
        "projects": extract_section(text, r"(?:Projects?|Personal\s+Projects?|Side\s+Projects?|Portfolio)"),
    }

    return {
        "name": name,
        "email": email,
        "phone": phone,
        "education": education,
        "experience_years": exp_years,
        "skills": skills,
        "keywords": keywords,
        "locations": locations,
        "raw_text": text[:5000],  # Increased for semantic matching
        "sections": sections,
    }


if __name__ == "__main__":
    import json
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "resume.md"
    result = parse_resume(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
