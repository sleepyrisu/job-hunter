"""
Gemini AI Integration Module
Google Gemini API integration for job evaluation and cover letter generation.
"""
import json
import time

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    try:
        import google.generativeai as genai
        GENAI_AVAILABLE = True
    except ImportError:
        GENAI_AVAILABLE = False
import config
from base_filter import BaseFilter
from prompts import DEFAULT_PREFERENCES, OUTPUT_CONTRACT, cover_letter_prompt


class GeminiFilter(BaseFilter):
    """Google Gemini AI filter for job evaluation and cover letter generation."""
    
    def __init__(self):
        super().__init__()
        settings = config.load_settings()
        
        self.api_key = settings.get("ai", {}).get("gemini_api_key") or None
        self.model_name = settings.get("ai", {}).get("gemini_model", "gemini-1.5-flash")
        
        self.is_configured = bool(self.api_key) and GENAI_AVAILABLE
        self.use_new_api = False
        self.client = None
        self.model = None
        
        if self.is_configured:
            try:
                self.client = genai.Client(api_key=self.api_key)
                self.model = self.client.models
                self.use_new_api = True
            except Exception:
                try:
                    genai.configure(api_key=self.api_key)
                    self.model = genai.GenerativeModel(self.model_name)
                    self.use_new_api = False
                except Exception as e:
                    print(f"WARNING: Gemini initialization failed: {e}")
                    self.is_configured = False
    
    def _generate_content(self, prompt):
        max_retries = 4
        backoff_factor = 2
        for attempt in range(max_retries):
            try:
                if self.use_new_api:
                    return self.client.models.generate_content(model=self.model_name, contents=prompt)
                else:
                    return self.model.generate_content(prompt)
            except Exception as e:
                sleep_time = backoff_factor ** attempt
                print(f"[GEMINI] Attempt {attempt + 1} failed: {e}. Retrying in {sleep_time}s...")
                if attempt == max_retries - 1:
                    raise
                time.sleep(sleep_time)
    
    def _build_eval_prompt(self, jobs_batch, custom_requirements):
        resume_content = self.read_resume()
        behavioral_content = self.profile.get("behavioral", "")
        jobs_text = self.build_jobs_text(jobs_batch)
        
        return f"""You are an expert technical recruiter evaluating multiple job postings for a single candidate.

Candidate Profile:
\"\"\"
{resume_content}
\"\"\"

Behavioral Profile:
\"\"\"
{behavioral_content}
\"\"\"

Additional Preferences:
{custom_requirements if custom_requirements else DEFAULT_PREFERENCES}

You are evaluating {len(jobs_batch)} job postings. For EACH job, provide a match score and reason.

CRITICAL scoring criteria:
0. **EDUCATION**: Candidate has a **DIPLOMA** in Computer Science (NOT a Bachelor's Degree). If job requires "Bachelor's Degree" / "Degree" → PENALIZE -30. If "Diploma welcome" / "Fresh Graduate" / "Entry Level" → BONUS +15.
1. **Experience**: Candidate has ~10 months Data Analyst + 3 months RPA intern (~1 year total). If job requires "3+ years" → PENALIZE -20. If "Entry Level" / "No experience needed" → BONUS.
2. **Skills**: Match candidate's Python, RPA (UiPath/Power Automate), C#, data analytics, and automation background. Coding skills are academic-level; production-coding roles score lower unless junior/grad.
3. Score CONTENT ONLY. Location, company type and salary are applied ONCE downstream by the preference layer — never fold them into this "score".

Score rubric (0-100):
- 90-100: Excellent - all content matches, junior/grad friendly
- 70-89: Good - most skills match
- 50-69: Moderate - partial skill match OR wrong experience level
- 0-49: Poor - major role/skills/experience mismatch

Also assess COMPANY RISK (heuristic, separate from match score).
{OUTPUT_CONTRACT}

{jobs_text}
"""
    
    def evaluate_job_batch(self, jobs_batch, custom_requirements=""):
        if not self.is_configured or not self.model:
            return [{"index": j["index"], "score": 0, "reason": "Gemini API is not configured."} for j in jobs_batch]
        
        prompt = self._build_eval_prompt(jobs_batch, custom_requirements)
        
        try:
            response = self._generate_content(prompt)
            response_text = response.text.strip()
            
            if response_text.startswith("```"):
                lines = response_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                response_text = "\n".join(lines).strip()
            
            results = json.loads(response_text)
            return self.validate_results(results)
            
        except Exception as e:
            print(f"Gemini API error: {e}")
            return [{"index": j["index"], "score": 0, "reason": f"Gemini API failed: {str(e)}"} for j in jobs_batch]
    
    def generate_cover_letter(self, job_title, job_company, job_description):
        if not self.is_configured or not self.model:
            return "Gemini API is not configured. Cannot generate cover letter."
        
        resume = self.read_resume()

        prompt = cover_letter_prompt(resume, job_title, job_company, job_description)
        
        try:
            response = self._generate_content(prompt)
            response_text = response.text.strip()
            if response_text.startswith("```"):
                lines = response_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                response_text = "\n".join(lines).strip()
            return response_text
        except Exception as e:
            return f"Failed to generate cover letter: {str(e)}"
    
    def evaluate_job(self, job_title, job_company, job_description):
        results = self.evaluate_job_batch([{
            "index": 1, "title": job_title, "company": job_company, "description": job_description
        }])
        if results:
            return {"score": results[0]["score"], "reason": results[0]["reason"]}
        return {"score": 0, "reason": "Evaluation failed."}


if __name__ == "__main__":
    f = GeminiFilter()
    print(f"Gemini Filter configured: {f.is_configured}")
    if f.is_configured:
        test_batch = [
            {"index": 1, "title": "Data Analyst", "company": "Accenture", "description": "Python, SQL, PowerBI in KL office of global MNC."},
            {"index": 2, "title": "RPA Developer", "company": "Local SME", "description": "UiPath developer for Penang-based SME. No relocation required."},
        ]
        results = f.evaluate_job_batch(test_batch)
        print(json.dumps(results, ensure_ascii=False, indent=2))
