"""
NLP-enhanced skill extraction - lightweight alternative to spaCy.
Uses regex patterns and alias maps for skill extraction from resumes and job descriptions.
"""
import re

# Common skill aliases and normalization
SKILL_ALIASES = {
    # Programming Languages
    "js": "JavaScript", "javascript": "JavaScript", "es6": "JavaScript",
    "ts": "TypeScript", "typescript": "TypeScript",
    "py": "Python", "python": "Python", "python3": "Python",
    "java": "Java", "jdk": "Java",
    "c#": "C#", "csharp": "C#", "c sharp": "C#", ".net": ".NET", "dotnet": ".NET",
    "c++": "C++", "cpp": "C++",
    "c": "C",
    "ruby": "Ruby", "rb": "Ruby",
    "go": "Go", "golang": "Go",
    "rust": "Rust",
    "php": "PHP",
    "swift": "Swift",
    "kotlin": "Kotlin", "kt": "Kotlin",
    "r": "R",
    "scala": "Scala",
    "perl": "Perl",

    # Web
    "html": "HTML", "html5": "HTML",
    "css": "CSS", "css3": "CSS", "scss": "SCSS", "sass": "SASS",
    "react": "React", "reactjs": "React", "react.js": "React",
    "vue": "Vue", "vuejs": "Vue", "vue.js": "Vue",
    "angular": "Angular", "angularjs": "Angular",
    "node": "Node.js", "nodejs": "Node.js", "node.js": "Node.js",
    "express": "Express", "expressjs": "Express",
    "next": "Next.js", "nextjs": "Next.js", "next.js": "Next.js",
    "nuxt": "Nuxt.js", "nuxtjs": "Nuxt.js",

    # Data
    "sql": "SQL", "mysql": "MySQL", "postgresql": "PostgreSQL", "postgres": "PostgreSQL",
    "mongodb": "MongoDB", "mongo": "MongoDB",
    "redis": "Redis",
    "elasticsearch": "Elasticsearch",
    "pandas": "Pandas", "numpy": "NumPy",
    "matplotlib": "Matplotlib",
    "jupyter": "Jupyter",

    # AI/ML
    "ml": "Machine Learning", "machine learning": "Machine Learning",
    "ai": "Artificial Intelligence", "artificial intelligence": "Artificial Intelligence",
    "deep learning": "Deep Learning", "dl": "Deep Learning",
    "nlp": "NLP", "natural language processing": "NLP",
    "tensorflow": "TensorFlow", "tf": "TensorFlow",
    "pytorch": "PyTorch", "torch": "PyTorch",
    "keras": "Keras",
    "scikit-learn": "scikit-learn", "sklearn": "scikit-learn",
    "huggingface": "Hugging Face", "transformers": "Transformers",

    # Cloud & DevOps
    "aws": "AWS", "amazon web services": "AWS",
    "gcp": "GCP", "google cloud": "GCP",
    "azure": "Azure", "microsoft azure": "Azure",
    "docker": "Docker",
    "k8s": "Kubernetes", "kubernetes": "Kubernetes",
    "jenkins": "Jenkins",
    "ci/cd": "CI/CD", "cicd": "CI/CD",
    "terraform": "Terraform",
    "ansible": "Ansible",
    "git": "Git", "github": "GitHub", "gitlab": "GitLab",
    "linux": "Linux",
    "bash": "Bash", "shell": "Shell",
    "powershell": "PowerShell",

    # RPA & Automation
    "rpa": "RPA", "robotic process automation": "RPA",
    "uipath": "UiPath", "ui path": "UiPath",
    "power automate": "Power Automate", "powerautomate": "Power Automate",
    "blue prism": "Blue Prism", "blueprism": "Blue Prism",
    "automation anywhere": "Automation Anywhere",

    # Data Tools
    "excel": "Excel", "microsoft excel": "Excel",
    "power bi": "Power BI", "powerbi": "Power BI",
    "tableau": "Tableau",
    "alteryx": "Alteryx",
    "sql server": "SQL Server", "mssql": "SQL Server",

    # Soft Skills
    "communication": "Communication",
    "leadership": "Leadership",
    "teamwork": "Teamwork",
    "problem solving": "Problem Solving",
    "critical thinking": "Critical Thinking",
}

# Section headers to look for in resumes
SECTION_HEADERS = {
    "skills": ["skills", "technical skills", "technical expertise", "competencies",
               "technologies", "tools", "programming languages", "tech stack"],
    "experience": ["experience", "work experience", "employment", "professional experience",
                   "work history", "career"],
    "education": ["education", "academic", "qualifications", "degrees"],
    "projects": ["projects", "personal projects", "side projects", "portfolio"],
}


def extract_skills_from_text(text):
    """
    Extract skills from text using pattern matching.
    Returns a list of normalized skill names.
    """
    if not text:
        return []

    text_lower = text.lower()
    found_skills = set()

    # Check each alias
    for alias, normalized in SKILL_ALIASES.items():
        # Use word boundary matching for short aliases
        pattern = r'\b' + re.escape(alias) + r'\b' if len(alias) <= 2 else re.escape(alias)

        if re.search(pattern, text_lower):
            found_skills.add(normalized)

    return sorted(found_skills)


def extract_section(text, section_type):
    """
    Extract a specific section from resume text.
    section_type: 'skills', 'experience', 'education', 'projects'
    """
    if not text:
        return ""

    text_lower = text.lower()
    headers = SECTION_HEADERS.get(section_type, [])

    for header in headers:
        # Find section start
        pattern = r'(?:^|\n)\s*(?:#{1,3}\s*)?' + re.escape(header) + r'[\s:*\-]*\n'
        match = re.search(pattern, text_lower)
        if match:
            start = match.end()
            # Find next section (any header)
            next_section = re.search(r'\n\s*(?:#{1,3}\s*)?[A-Z][\w\s]+[\s:*\-]*\n', text[start:])
            end = start + next_section.start() if next_section else min(start + 2000, len(text))
            return text[start:end].strip()

    return ""


def compute_skill_match_score(resume_skills, job_text):
    """
    Compute a skill match score between resume skills and job description.
    Returns a score 0-100 and list of matched/missing skills.
    """
    job_skills = extract_skills_from_text(job_text)

    if not resume_skills or not job_skills:
        return 0, [], job_skills

    resume_set = set(s.lower() for s in resume_skills)
    job_set = set(s.lower() for s in job_skills)

    matched = resume_set & job_set
    missing = job_set - resume_set

    if not job_set:
        return 50, [], []

    score = int((len(matched) / len(job_set)) * 100)
    return score, list(matched), list(missing)


def get_skill_category(skill):
    """Get the category of a skill for weighted scoring."""
    categories = {
        "programming": [
            "Python", "Java", "JavaScript", "TypeScript", "C#", "C++",
            "Go", "Ruby", "PHP", "Swift", "Kotlin",
        ],
        "framework": ["React", "Vue", "Angular", "Node.js", "Django", "Flask", "Spring", "Express", "Next.js"],
        "data": ["SQL", "MongoDB", "Redis", "PostgreSQL", "MySQL", "Pandas", "NumPy"],
        "cloud": ["AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform"],
        "rpa": ["RPA", "UiPath", "Power Automate", "Blue Prism", "Automation Anywhere"],
        "ai_ml": ["Machine Learning", "Deep Learning", "NLP", "TensorFlow", "PyTorch"],
        "tools": ["Git", "Linux", "Excel", "Power BI", "Tableau"],
    }

    skill_lower = skill.lower()
    for category, skills in categories.items():
        for s in skills:
            if s.lower() == skill_lower:
                return category
    return "other"


if __name__ == "__main__":
    # Test skill extraction
    test_text = """
    Looking for a Junior RPA Developer with Python and Power Automate experience.
    Must have SQL skills and knowledge of UiPath. Docker and Git are a plus.
    """
    skills = extract_skills_from_text(test_text)
    print("Extracted skills:", skills)

    # Test section extraction
    test_resume = """
    # Skills
    - Python, JavaScript, SQL
    - Power Automate, RPA
    - Docker, Git

    # Experience
    - Data Analyst at Nexa Analytics (10 months)
    - RPA Intern at Vertex Logistics (3 months)

    # Education
    - Diploma in Computer Science
    """
    for section in ["skills", "experience", "education"]:
        content = extract_section(test_resume, section)
        print(f"\n{section.upper()}:")
        print(content[:200] if content else "Not found")
