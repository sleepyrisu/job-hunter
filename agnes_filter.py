"""
Agnes AI Integration Module
Agnes AI API integration for job evaluation and cover letter generation.
"""
import json
import time

from openai import OpenAI

import config
from base_filter import BaseFilter
from prompts import DEFAULT_PREFERENCES, OUTPUT_CONTRACT, cover_letter_prompt


class AgnesFilter(BaseFilter):
    """Agnes AI filter for job evaluation and cover letter generation."""
    
    def __init__(self):
        super().__init__()
        settings = config.load_settings()
        
        self.api_key = settings.get("ai", {}).get("agnes_api_key") or None
        self.base_url = settings.get("ai", {}).get("agnes_base_url") or "https://apihub.agnes-ai.com/v1"
        self.model = settings.get("ai", {}).get("agnes_model", "agnes-2.0-flash")
        
        self.is_configured = bool(self.api_key)
        
        if self.is_configured:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        else:
            self.client = None
    
    def _build_eval_prompt(self, jobs_batch, custom_requirements):
        resume_content = self.read_resume()
        behavioral_content = self.profile.get("behavioral", "")
        evaluation_framework = self.profile.get("evaluation", "")
        jobs_text = self.build_jobs_text(jobs_batch)
        
        return f"""You are an expert technical recruiter evaluating multiple job postings for a candidate.

## CANDIDATE RESUME
\"\"\"
{resume_content}
\"\"\"

## BEHAVIORAL PROFILE
\"\"\"
{behavioral_content}
\"\"\"

## EVALUATION FRAMEWORK (use this to guide scoring)
\"\"\"
{evaluation_framework}
\"\"\"

## ADDITIONAL PREFERENCES
{custom_requirements if custom_requirements else DEFAULT_PREFERENCES}

## JOBS TO EVALUATE
{jobs_text}

## TASK
You are evaluating {len(jobs_batch)} job postings. For EACH job, do a detailed resume-to-job matching analysis, then output a score and Chinese reason.

### SCORING METHODOLOGY (weighted content dimensions)
Score CONTENT ONLY (skills / experience / education / role fit). Location,
company type and salary are applied ONCE downstream by the preference layer —
never fold them into this "score". Then compute the weighted final score:
1. **Technical Skills Match** (40%): Candidate's coding skills (C#, C++, Java, SQL) are at **academic level** — last used actively in diploma (~2023-2024). Needs 2-4 weeks ramp-up for production coding. **Strongest skills are RPA (Power Automate) and data operations (ML QA, classification)** — these are recent, hands-on professional experience. Compare each job requirement against this reality.
2. **Experience Match** (30%): ~10 months professional experience (Acme Corp data ops + Acme Logistics RPA internship). Junior/grad roles (0-2yr) = higher. Pure software engineering roles asking for coding production experience = penalize.
3. **Education Fit** (10%): Diploma holder. Degree-mandatory roles penalized; fresh-graduate-welcome roles boosted.
4. **Career Alignment & Growth** (20%): Does this role let candidate contribute from day 1 (RPA/data ops) while rebuilding coding skills through mentorship? Ideal = hybrid role where existing skills are primary value and coding is developed.

### FINAL SCALE (0-100)
- 90-100: Excellent — strongest skills match (RPA/data ops), explicit grad/junior program
- 80-89: Good — most skills match, junior-friendly
- 70-79: Moderate — partial skill match OR role requires coding skills beyond current level
- 50-69: Weak — significant skill gaps OR role expects mid-level coding productivity
- 0-49: Poor — major mismatch, senior role, or no alignment with candidate's actual experience

### CRITICAL RULES
0. **EDUCATION**: Candidate has a **DIPLOMA** in Computer Science (NOT a Bachelor's Degree). If job requires "Bachelor's Degree" / "Degree" / "Bachelor" → PENALIZE -30 points. If job mentions "Diploma holders welcome" / "Fresh Graduate" / "SPM/Diploma accepted" → BONUS +15. If job says "Master's" / "PhD" → score 0 (overqualified requirement).
1. **Coding confidence**: Candidate's programming skills (C#, Python, Java, C++) are at **academic/basic level, not production-ready**. If the job description emphasizes strong coding skills or expects immediate code output, SCORE ≤ 60. If the job explicitly says "junior", "grad program", "mentorship", "training provided" — BOOST score.
2. **Experience level**: Junior/grad roles (0-2yr) score well. Candidate has ~10 months Data Analyst + 3 months RPA intern (~1 year total). Roles asking "3+ years" = max score 50. Senior (5+yr) = max 30. Entry level / "no experience needed" = bonus.
3. **Honesty**: Be very honest about the coding gap. If ALL skills the job asks for are in the candidate's strongest areas (RPA, data ops, QA), boost score. If the job requires production coding skills the candidate hasn't used professionally, lower score.
4. **Reason format**: Each reason MUST mention: (a) which specific skills matched/didn't match, (b) whether role is appropriate for candidate's education (Diploma) and experience level (~1yr).

### COMPANY RISK ASSESSMENT (heuristic, separate from match score)
{OUTPUT_CONTRACT}
"""

    def _call_api(self, prompt, temperature=0.2):
        max_retries = 4
        backoff_factor = 2
        for attempt in range(max_retries):
            try:
                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature
                )
                return completion.choices[0].message.content.strip()
            except json.JSONDecodeError:
                raise
            except Exception:
                sleep_time = backoff_factor ** attempt
                if attempt == max_retries - 1:
                    raise
                time.sleep(sleep_time)

    def evaluate_job_batch(self, jobs_batch, custom_requirements=""):
        if not self.is_configured or not self.client:
            return [{"index": j["index"], "score": 0, "reason": "Agnes AI is not configured."} for j in jobs_batch]
        
        prompt = self._build_eval_prompt(jobs_batch, custom_requirements)
        
        for attempt in range(4):
            try:
                response_text = self._call_api(prompt)
                print(f"\n[AGNES RAW RESPONSE] len={len(response_text)} preview={response_text[:200]}")
                
                if response_text.startswith("```"):
                    lines = response_text.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines[-1].startswith("```"):
                        lines = lines[:-1]
                    response_text = "\n".join(lines).strip()

                results = json.loads(response_text)
                return self.validate_results(results)

            except json.JSONDecodeError as e:
                print(f"[AGNES JSON ERROR] {e}")
                if attempt == 3:
                    return [{"index": j["index"], "score": 0, "reason": f"Agnes AI returned invalid JSON: {str(e)[:50]}"} for j in jobs_batch]
                time.sleep(2 ** attempt)
            except Exception as e:
                print(f"[AGNES API ERROR] {type(e).__name__}: {e}")
                if attempt == 3:
                    return [{"index": j["index"], "score": 0, "reason": f"Agnes AI failed: {str(e)[:100]}"} for j in jobs_batch]
                time.sleep(2 ** attempt)
    
    def generate_cover_letter(self, job_title, job_company, job_description):
        if not self.is_configured or not self.client:
            return "Agnes AI is not configured. Cannot generate cover letter."
        
        resume = self.read_resume()
        behavioral = self.profile.get("behavioral", "")

        prompt = cover_letter_prompt(resume, job_title, job_company, job_description, behavioral=behavioral)
        
        try:
            response_text = self._call_api(prompt, temperature=0.7)
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
            return {"score": results[0]["score"], "reason": results[0]["reason"], "risk": results[0].get("risk"),
                    "salary": results[0].get("salary"), "kl_transfer": results[0].get("kl_transfer"),
                    "fit_type": results[0].get("fit_type", "")}
        return {"score": 0, "reason": "Evaluation failed.", "risk": None, "salary": None, "kl_transfer": False, "fit_type": ""}


if __name__ == "__main__":
    f = AgnesFilter()
    print(f"Agnes AI Filter configured: {f.is_configured}")
    if f.is_configured:
        test_batch = [
            {"index": 1, "title": "Data Analyst", "company": "Accenture", "description": "Python, SQL, PowerBI in KL office of global MNC."},
            {"index": 2, "title": "RPA Developer", "company": "Local SME", "description": "UiPath developer for Penang-based SME. No relocation required."},
        ]
        results = f.evaluate_job_batch(test_batch)
        print(json.dumps(results, ensure_ascii=False, indent=2))
