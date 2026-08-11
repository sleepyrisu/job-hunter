"""
BaseFilter - Abstract base class for all AI job evaluation filters.
Eliminates duplicate profile loading and output validation code.
"""
import os
from abc import ABC, abstractmethod


class BaseFilter(ABC):
    """Abstract base class providing common functionality for all AI filters."""
    
    def __init__(self):
        self.profile = self._load_profile()
    
    def _load_profile(self):
        """Load candidate profile from profile directory (shared by all filters)."""
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
    
    def validate_results(self, results):
        """Validate and clean AI output results (shared validation logic)."""
        output = []
        for r in results:
            raw_risk = r.get("risk") or {}
            rk_level = str(raw_risk.get("level", "low")).lower()
            if rk_level not in ("low", "medium", "high"):
                rk_level = "low"
            
            raw_salary = r.get("salary")
            salary_val = None
            if isinstance(raw_salary, (int, float)) and raw_salary > 0:
                salary_val = int(raw_salary)
            
            output.append({
                "index": int(r.get("index")),
                "score": max(0, min(100, int(r.get("score", 0)))),
                "reason": r.get("reason", "No reason provided."),
                "risk": {
                    "level": rk_level,
                    "reason": raw_risk.get("reason", "") if isinstance(raw_risk, dict) else ""
                },
                "salary": salary_val,
                # Legacy fields kept for compatibility; the preference layer
                # (score_adjuster) recomputes these from the requirement text.
                "kl_transfer": bool(r.get("kl_transfer")),
                "kl_potential": bool(r.get("kl_potential")),
                "fit_type": str(r.get("fit_type", "")).lower()
                if r.get("fit_type") in ("safe", "stretch", "unknown")
                else "",
            })
        return output
    
    def build_jobs_text(self, jobs_batch, max_desc_len=1200):
        """Build formatted jobs text for AI prompts."""
        jobs_text = ""
        for j in jobs_batch:
            desc = j['description']
            if len(desc) > max_desc_len:
                desc = desc[:max_desc_len] + "... (truncated for brevity)"
            jobs_text += f"""
--- JOB #{j['index']} ---
Title: {j['title']}
Company: {j['company']}
Description:
\"\"\"{desc}\"\"\"
"""
        return jobs_text
    
    @abstractmethod
    def evaluate_job_batch(self, jobs_batch, custom_requirements=""):
        """Evaluate a batch of jobs. Must be implemented by subclasses."""
        pass
    
    @abstractmethod
    def generate_cover_letter(self, job_title, job_company, job_description):
        """Generate a cover letter. Must be implemented by subclasses."""
        pass
