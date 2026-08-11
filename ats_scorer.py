"""
ATS (Applicant Tracking System) Resume Scorer.
Simulates how ATS systems evaluate resumes.
"""
import re


def score_resume_ats(resume_text):
    """
    Score a resume on ATS-friendliness.
    Returns a dict with score and detailed feedback.
    """
    if not resume_text:
        return {"score": 0, "feedback": ["无法读取简历内容"]}

    score = 0
    feedback = []
    details = {}

    # 1. Contact Information (15 points)
    contact_score = 0
    email = re.search(r'[\w.-]+@[\w.-]+\.\w+', resume_text)
    phone = re.search(r'\+?[\d\s-]{8,15}', resume_text)
    if email:
        contact_score += 8
        details["email"] = "已找到"
    else:
        feedback.append("缺少邮箱地址")
    if phone:
        contact_score += 7
        details["phone"] = "已找到"
    else:
        feedback.append("缺少电话号码")
    score += contact_score

    # 2. Section Structure (20 points)
    section_score = 0
    sections = {
        "skills": ["skills", "technical skills", "technologies", "competencies"],
        "experience": ["experience", "work experience", "employment"],
        "education": ["education", "academic", "qualifications"],
    }
    for section_name, headers in sections.items():
        for header in headers:
            if header in resume_text.lower():
                section_score += 7
                details[section_name] = "已找到"
                break
    score += min(20, section_score)

    # 3. Keywords Density (25 points)
    keyword_score = 0
    # Common ATS keywords
    ats_keywords = [
        "experience", "skills", "education", "developed", "implemented",
        "managed", "led", "created", "improved", "achieved", "results",
        "team", "project", "analysis", "design", "development"
    ]
    resume_lower = resume_text.lower()
    found_keywords = [kw for kw in ats_keywords if kw in resume_lower]
    keyword_score = min(25, len(found_keywords) * 2)
    score += keyword_score
    details["ats_keywords"] = len(found_keywords)

    # 4. Action Verbs (15 points)
    action_verbs = [
        "developed", "implemented", "managed", "led", "created", "designed",
        "improved", "achieved", "delivered", "built", "established", "launched",
        "optimized", "automated", "streamlined", "coordinated", "supervised"
    ]
    found_verbs = [v for v in action_verbs if v in resume_lower]
    verb_score = min(15, len(found_verbs) * 2)
    score += verb_score
    details["action_verbs"] = len(found_verbs)

    # 5. Length Check (10 points)
    word_count = len(resume_text.split())
    if 300 <= word_count <= 800:
        score += 10
        details["length"] = f"{word_count} words (理想)"
    elif 200 <= word_count <= 1200:
        score += 5
        details["length"] = f"{word_count} words (可接受)"
    else:
        feedback.append(f"简历长度{word_count}词，建议300-800词")

    # 6. Formatting (15 points)
    format_score = 0
    # Check for bullet points
    if re.search(r'[-•*]\s', resume_text):
        format_score += 5
    # Check for dates
    if re.search(r'\b(?:20\d{2}|19\d{2})\b', resume_text):
        format_score += 5
    # Check for proper capitalization (not all caps)
    if not resume_text.isupper() and resume_text[0].isupper():
        format_score += 5
    score += format_score

    # Clamp score
    score = max(0, min(100, score))

    # Generate recommendations
    recommendations = []
    if score < 60:
        recommendations.append("考虑添加更多量化成果（数字、百分比）")
        recommendations.append("确保包含关键词以通过ATS筛选")
    if not email:
        recommendations.append("在简历顶部添加专业邮箱")
    if not phone:
        recommendations.append("添加联系电话")
    if word_count < 300:
        recommendations.append("简历内容较少，建议添加更多项目经验")

    return {
        "score": score,
        "feedback": feedback,
        "details": details,
        "recommendations": recommendations,
        "grade": _get_grade(score),
    }


def _get_grade(score):
    """Get letter grade from score."""
    if score >= 90:
        return "A+"
    elif score >= 80:
        return "A"
    elif score >= 70:
        return "B+"
    elif score >= 60:
        return "B"
    elif score >= 50:
        return "C"
    else:
        return "D"


def tailor_resume_for_job(resume_text, job_text, resume_skills):
    """
    Suggest resume tailoring for a specific job.
    Returns suggestions for what to emphasize.
    """
    from nlp_skills import extract_skills_from_text

    job_skills = extract_skills_from_text(job_text)
    resume_set = set(s.lower() for s in resume_skills)
    job_set = set(s.lower() for s in job_skills)

    matched = resume_set & job_set
    missing = job_set - resume_set

    suggestions = []
    if matched:
        suggestions.append(f"强调这些匹配技能: {', '.join(list(matched)[:5])}")
    if missing:
        suggestions.append(f"考虑在简历中提及: {', '.join(list(missing)[:3])}")

    # Check for action verbs
    action_verbs = ["developed", "implemented", "managed", "led", "created"]
    has_verbs = any(verb in resume_text.lower() for verb in action_verbs)
    if not has_verbs:
        suggestions.append("添加更多动作动词（开发、实现、管理、领导）")

    return suggestions


if __name__ == "__main__":
    test_resume = """
    Tan Wei Ming
    Email: tanweiming@example.com
    Phone: +60 12-345 6789

    Skills
    - Python, Power Automate, RPA
    - SQL, Data Analysis
    - Docker, Git

    Experience
    Data Analyst at Nexa Analytics (10 months)
    - Developed automated reporting solutions
    - Managed data pipelines using Python

    Education
    Diploma in Computer Science
    """

    result = score_resume_ats(test_resume)
    print(f"ATS Score: {result['score']}/100 ({result['grade']})")
    print(f"Details: {result['details']}")
    if result['feedback']:
        print(f"Feedback: {result['feedback']}")
    if result['recommendations']:
        print(f"Recommendations: {result['recommendations']}")
