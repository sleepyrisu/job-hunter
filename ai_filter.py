import json
import time

from openai import OpenAI

import config
from base_filter import BaseFilter
from prompts import DEFAULT_PREFERENCES, OUTPUT_CONTRACT, cover_letter_prompt

BATCH_SIZE = 10

class AIFilter(BaseFilter):
    def __init__(self):
        super().__init__()
        settings = config.load_settings()
        self.api_key = settings["ai"]["api_key"]
        self.base_url = settings["ai"]["base_url"]
        self.model_name = settings["ai"].get("model", "meta/llama-3.1-70b-instruct")
        
        self.is_configured = bool(self.api_key)
        
        if self.is_configured:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        else:
            print("WARNING: AI API Key is not set. AI Filtering will be disabled (all jobs scored 0).")
            self.client = None

    def evaluate_job_batch(self, jobs_batch, custom_requirements=""):
        if not self.is_configured or not self.client:
            return [{"index": j["index"], "score": 0, "reason": "AI Filter is not configured."} for j in jobs_batch]

        resume_content = self.read_resume()
        jobs_text = self.build_jobs_text(jobs_batch)

        prompt = f"""You are an expert technical recruiter evaluating multiple job postings for a candidate.

## CANDIDATE RESUME
\"\"\"
{resume_content}
\"\"\"

## ADDITIONAL PREFERENCES
{custom_requirements if custom_requirements else DEFAULT_PREFERENCES}

## TASK
You are evaluating {len(jobs_batch)} job postings for this candidate. Match the job requirements against the candidate's resume and output a score + Chinese reason.

### HONEST SKILL ASSESSMENT
- **RPA (Power Automate) & Data Operations (ML QA, Classification)**: Strongest skills, recent hands-on professional experience
- **C#, C++, Java, SQL**: Academic level only (diploma projects, last actively coded ~2023-2024). Needs 2-4 weeks ramp-up.
- **Python**: Basic, learning. Not production-ready.
- **Pure software engineering roles** expecting production coding should score lower unless explicitly junior/grad program.

### SCORING (weighted content dimensions)
Score CONTENT ONLY: the candidate's skills, experience, education and role fit
against the job. Location, company type and salary are scored ONCE downstream
by the preference layer — never fold them into this "score".
1. **Technical Skills** (45%): RPA/data ops = strong match. Coding skills = academic level. Penalize roles requiring production coding experience.
2. **Experience Match** (30%): ~10 months pro experience + diploma. Junior/grad roles (0-2yr) = higher. Senior roles (3+yr) = max 60.
3. **Education Fit** (10%): Diploma holder. Degree-mandatory roles penalized; fresh-graduate-welcome roles boosted.
4. **Career Alignment & Growth** (15%): Does the role let the candidate contribute (RPA/data ops) while rebuilding coding skills through mentorship?

### FINAL SCALE
- 90-100: Excellent — strongest skills match (RPA/data ops), junior/grad friendly
- 80-89: Good — most skills match, junior-friendly
- 70-79: Moderate — partial skill match OR requires coding beyond current level
- 50-69: Weak — significant gaps OR wrong experience level OR no mentorship
- 0-49: Poor — major mismatch, senior role

### CRITICAL
0. **EDUCATION**: Candidate has a **DIPLOMA** in Computer Science (NOT a Bachelor's Degree). If job requires "Bachelor's Degree" / "Degree" → PENALIZE -30. If "Diploma welcome" / "Fresh Graduate" / "Entry Level" → BONUS +15.
1. **Experience**: Candidate has ~10 months Data Analyst + 3 months RPA intern (~1 year total). If job requires "3+ years" → PENALIZE -20. If "Entry Level" / "No experience needed" → BONUS.
2. Be honest about the coding confidence gap. Note which skills are production-ready vs academic-only.
3. Junior/grad roles with mentorship = BOOST score.
4. Production coding roles with no mention of training = PENALIZE.

### COMPANY RISK (heuristic, separate from match score)
{OUTPUT_CONTRACT}

{jobs_text}
"""

        max_retries = 3
        backoff_factor = 2
        
        for attempt in range(max_retries):
            try:
                kwargs = {
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2
                }
                
                if "nemotron" in self.model_name.lower():
                    kwargs["extra_body"] = {
                        "chat_template_kwargs": {"enable_thinking": True},
                        "reasoning_budget": 16384
                    }
                    kwargs["temperature"] = 1.0
                    
                completion = self.client.chat.completions.create(**kwargs)
                response_text = completion.choices[0].message.content.strip()
                
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
                sleep_time = backoff_factor ** attempt
                print(f"API Attempt {attempt + 1} failed: {e}. Retrying in {sleep_time}s...")
                if attempt == max_retries - 1:
                    print("Max retries reached. Returning fail results for this batch.")
                    return [{"index": j["index"], "score": 0, "reason": f"Nvidia API failed: {str(e)}"} for j in jobs_batch]
                time.sleep(sleep_time)

    def evaluate_job(self, job_title, job_company, job_description):
        results = self.evaluate_job_batch([{
            "index": 1, "title": job_title, "company": job_company, "description": job_description
        }])
        if results:
            return {"score": results[0]["score"], "reason": results[0]["reason"]}
        return {"score": 0, "reason": "Evaluation failed."}

    def generate_cover_letter(self, job_title, job_company, job_description):
        if not self.is_configured or not self.client:
            return "AI filter is not configured. Cannot generate cover letter."
            
        resume = self.read_resume()

        prompt = cover_letter_prompt(resume, job_title, job_company, job_description)

        max_retries = 3
        backoff_factor = 2
        for attempt in range(max_retries):
            try:
                kwargs = {
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7
                }
                
                if "nemotron" in self.model_name.lower():
                    kwargs["extra_body"] = {
                        "chat_template_kwargs": {"enable_thinking": True},
                        "reasoning_budget": 16384
                    }
                    kwargs["temperature"] = 1.0
                    
                completion = self.client.chat.completions.create(**kwargs)
                response_text = completion.choices[0].message.content.strip()
                
                if response_text.startswith("```"):
                    lines = response_text.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines[-1].startswith("```"):
                        lines = lines[:-1]
                    response_text = "\n".join(lines).strip()
                    
                return response_text
            except Exception as e:
                sleep_time = backoff_factor ** attempt
                print(f"Cover Letter API Attempt {attempt + 1} failed: {e}. Retrying in {sleep_time}s...")
                if attempt == max_retries - 1:
                    return f"Failed to generate cover letter: {str(e)}"
                time.sleep(sleep_time)

if __name__ == "__main__":
    f = AIFilter()
    test_batch = [
        {"index": 1, "title": "Data Analyst", "company": "Accenture", "description": "Python, SQL, PowerBI in KL office of global MNC."},
        {"index": 2, "title": "RPA Developer", "company": "Local SME", "description": "UiPath developer for Penang-based SME. No relocation required."},
    ]
    results = f.evaluate_job_batch(test_batch)
    print(json.dumps(results, ensure_ascii=False, indent=2))
