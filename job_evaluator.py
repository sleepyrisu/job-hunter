"""
Enhanced Job Evaluation Module
5-dimension scoring framework based on MadsLorentzen/ai-job-search
"""
import json

from openai import OpenAI

import config


class JobEvaluator:
    """Enhanced job evaluator with 5-dimension scoring framework."""
    
    WEIGHTS = {
        "technical_skills": 0.30,
        "experience_match": 0.25,
        "behavioral_fit": 0.15,
        "career_alignment": 0.30
    }
    
    THRESHOLDS = {
        "strong_fit": 75,
        "good_fit": 60,
        "moderate_fit": 45,
        "weak_fit": 30
    }
    
    def __init__(self):
        self.profile = self._load_profile()
        settings = config.load_settings()
        
        self.api_key = settings.get("ai", {}).get("agnes_api_key") or settings["ai"]["api_key"]
        self.base_url = settings.get("ai", {}).get("agnes_base_url") or settings["ai"]["base_url"]
        self.model_name = settings.get("ai", {}).get("agnes_model") or settings["ai"].get("model", "meta/llama-3.1-70b-instruct")
        
        self.is_configured = bool(self.api_key)
        
        if self.is_configured:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        else:
            self.client = None
    
    def _load_profile(self):
        """Load candidate profile from profile directory."""
        import os
        profile_dir = os.path.join(os.path.dirname(__file__), "profile")
        profile = {}
        profile_files = {
            "candidate": "01-candidate-profile.md",
            "behavioral": "02-behavioral-profile.md",
            "evaluation": "03-job-evaluation.md"
        }
        for key, filename in profile_files.items():
            filepath = os.path.join(profile_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, encoding='utf-8') as f:
                    profile[key] = f.read()
        if not profile:
            resume_path = os.path.join(os.path.dirname(__file__), "resume.md")
            if os.path.exists(resume_path):
                with open(resume_path, encoding='utf-8') as f:
                    profile["candidate"] = f.read()
        return profile
    
    def read_resume(self):
        """Read resume content for use in evaluations."""
        return self.profile.get("candidate", "No resume details available.")
    
    def evaluate_job(self, job_title, job_company, job_description, job_location=""):
        if not self.is_configured or not self.client:
            return self._default_result("AI Filter is not configured.")
        
        candidate_info = self.read_resume()
        behavioral_info = self.profile.get("behavioral", "")
        
        prompt = f"""You are an expert career advisor evaluating a job posting for a candidate.

CANDIDATE PROFILE:
{candidate_info}

BEHAVIORAL PROFILE:
{behavioral_info}

JOB POSTING:
- Title: {job_title}
- Company: {job_company}
- Location: {job_location}
- Description:
\"\"\"
{job_description[:2000]}
\"\"\"

Evaluate this job posting using the 5-dimension scoring framework:

1. **Technical Skills Match (0-100)**: How well do required skills align with candidate's Python, RPA (UiPath/Power Automate), C#, data analytics, and automation background?
2. **Experience Match (0-100)**: Does work history align with the role requirements?
3. **Behavioral/Culture Fit (0-100)**: Does the role and company culture match the behavioral profile? Consider: MNC preference, KL+Penang presence preference.
4. **Location & Logistics (PASS/FAIL)**: Is the location acceptable? Preferred: Penang, KL/Selangor, Singapore, Remote.
5. **Career Alignment & Motivation (0-100)**: Does this role advance career goals?

CRITICAL SCORING RULES:
- Location: Strongly prefer Penang, KL/Selangor, Singapore, or Remote. Penalize other locations heavily.
- Company Type: Strongly prefer MNCs or large companies with branches in BOTH KL and Penang. Penalize small local agencies and startups.
- Skills: Match Python, RPA (UiPath/Power Automate), C#, data analytics, automation.

Respond with JSON in this exact format:
{{
    "technical_skills": {{"score": 85, "notes": "brief explanation"}},
    "experience_match": {{"score": 70, "notes": "brief explanation"}},
    "behavioral_fit": {{"score": 80, "notes": "brief explanation"}},
    "location": {{"status": "PASS", "notes": "brief explanation"}},
    "career_alignment": {{"score": 75, "notes": "brief explanation"}},
    "verdict": "Good Fit",
    "strengths": ["strength 1", "strength 2"],
    "gaps": ["gap 1", "gap 2"],
    "recommendation": "1-2 sentence recommendation"
}}

Only output the raw JSON. Do not wrap it in markdown formatting.
"""
        
        try:
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2
            )
            
            response_text = completion.choices[0].message.content.strip()
            
            if response_text.startswith("```"):
                lines = response_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                response_text = "\n".join(lines).strip()
            
            result = json.loads(response_text)
            overall_score = self._calculate_overall_score(result)
            result["overall_score"] = overall_score
            result["verdict"] = self._get_verdict(overall_score)
            return result
            
        except Exception as e:
            print(f"Evaluation error: {e}")
            return self._default_result(f"Evaluation failed: {str(e)}")
    
    def _calculate_overall_score(self, dimensions):
        try:
            technical = dimensions.get("technical_skills", {}).get("score", 0)
            experience = dimensions.get("experience_match", {}).get("score", 0)
            behavioral = dimensions.get("behavioral_fit", {}).get("score", 0)
            career = dimensions.get("career_alignment", {}).get("score", 0)
            overall = (
                technical * self.WEIGHTS["technical_skills"] +
                experience * self.WEIGHTS["experience_match"] +
                behavioral * self.WEIGHTS["behavioral_fit"] +
                career * self.WEIGHTS["career_alignment"]
            )
            return round(overall)
        except Exception:
            return 0
    
    def _get_verdict(self, score):
        if score >= self.THRESHOLDS["strong_fit"]:
            return "Strong Fit"
        elif score >= self.THRESHOLDS["good_fit"]:
            return "Good Fit"
        elif score >= self.THRESHOLDS["moderate_fit"]:
            return "Moderate Fit"
        elif score >= self.THRESHOLDS["weak_fit"]:
            return "Weak Fit"
        else:
            return "Poor Fit"
    
    def _default_result(self, reason):
        return {
            "overall_score": 0,
            "technical_skills": {"score": 0, "notes": reason},
            "experience_match": {"score": 0, "notes": reason},
            "behavioral_fit": {"score": 0, "notes": reason},
            "location": {"status": "UNKNOWN", "notes": reason},
            "career_alignment": {"score": 0, "notes": reason},
            "verdict": "Unable to evaluate",
            "strengths": [],
            "gaps": [reason],
            "recommendation": "Cannot evaluate without AI configuration."
        }
    
    def format_evaluation(self, result, job_title, job_company):
        output = f"""
## Job Fit Evaluation: {job_title} at {job_company}

| Dimension | Score | Notes |
|-----------|-------|-------|
| Technical Skills | {result['technical_skills']['score']}/100 | {result['technical_skills']['notes']} |
| Experience Match | {result['experience_match']['score']}/100 | {result['experience_match']['notes']} |
| Behavioral Fit | {result['behavioral_fit']['score']}/100 | {result['behavioral_fit']['notes']} |
| Location | {result['location']['status']} | {result['location']['notes']} |
| Career Alignment | {result['career_alignment']['score']}/100 | {result['career_alignment']['notes']} |

**Overall Score: {result['overall_score']}/100**

### Verdict: {result['verdict']}

### Key Strengths
"""
        for strength in result.get('strengths', []):
            output += f"- {strength}\n"
        
        output += "\n### Gaps to Address\n"
        for gap in result.get('gaps', []):
            output += f"- {gap}\n"
        
        output += f"\n### Recommendation\n{result.get('recommendation', 'N/A')}\n"
        return output


if __name__ == "__main__":
    evaluator = JobEvaluator()
    print("Job Evaluator initialized.")
    print(f"Profile loaded: {list(evaluator.profile.keys())}")
