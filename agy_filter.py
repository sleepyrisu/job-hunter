import json
import os
import re
import subprocess

import config
from base_filter import BaseFilter

AGY_PATH = None

def _find_agy():
    global AGY_PATH
    if AGY_PATH:
        return AGY_PATH
    try:
        import shutil
        AGY_PATH = shutil.which("agy")
        if AGY_PATH:
            return AGY_PATH
    except Exception:
        pass
    candidates = [
        os.path.expanduser(r"~\AppData\Local\agy\bin\agy.exe"),
        os.path.expanduser(r"~\AppData\Local\agy\bin\agy"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            AGY_PATH = c
            return c
    return None


def _check_agy():
    path = _find_agy()
    if not path:
        return False
    try:
        r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


class AgyFilter(BaseFilter):
    def __init__(self):
        super().__init__()
        self.is_configured = _check_agy()
        self.model = "gemini-3.6-flash-high"
        settings = config.load_settings()
        if "agy" in settings.get("ai", {}):
            self.model = settings["ai"]["agy"].get("model", self.model)

    def _run_agy(self, prompt, timeout=120):
        path = _find_agy()
        if not path:
            return None
        try:
            r = subprocess.run(
                [path, "--dangerously-skip-permissions", "-p", prompt, "--model", self.model],
                capture_output=True, text=True, timeout=timeout,
                env={**os.environ, "AGY_MODEL": self.model}
            )
            if r.returncode == 0:
                return r.stdout.strip()
            err = r.stderr.strip()
            print(f"[agy_filter] stderr: {err}")
            if r.stdout.strip():
                return r.stdout.strip()
            return None
        except subprocess.TimeoutExpired:
            print("[agy_filter] agy timed out")
            return None
        except Exception as e:
            print(f"[agy_filter] error: {e}")
            return None

    def evaluate_job_batch(self, jobs_batch, custom_requirements=""):
        if not self.is_configured:
            return [{"index": j["index"], "score": 0, "reason": "agy not available"} for j in jobs_batch]

        resume = self.read_resume()
        behavioral = self.profile.get("behavioral", "")
        eval_fw = self.profile.get("evaluation", "")

        jobs_text = "\n---\n".join(
            f"Job #{j['index']}: {j.get('title','?')} at {j.get('company','?')}\n"
            f"Location: {j.get('location','?')}\nSalary: {j.get('salary_raw','N/A')}\n"
            f"Description: {j.get('description','')[:2000]}"
            for j in jobs_batch
        )

        prompt = f"""You are a job matching AI assistant. Evaluate each job below for the candidate.

CRITICAL - The candidate's education is DIPLOMA (NOT a degree). Experience: ~1 year total (10mo Data Analyst + 3mo RPA intern).
Penalize jobs requiring "Bachelor's Degree" or "Degree" by -30 points. Penalize jobs asking "3+ years" by -20. Bonus +15 for "Diploma" or "Entry Level" or "Fresh Graduate" or "Training Provided".

CANDIDATE PROFILE:
{resume[:3000]}

BEHAVIORAL PREFERENCES:
{behavioral[:2000]}

EVALUATION FRAMEWORK:
{eval_fw[:2000]}

CUSTOM REQUIREMENTS:
{custom_requirements}

JOBS TO EVALUATE:
{jobs_text}

For each job, return a JSON array of objects with: index (number), score (0-100 integer), reason (short string in Chinese or English mentioning if it requires degree/experience), fit_type ("safe", "stretch", or "unknown").

Return ONLY a valid JSON array, no other text:"""
        agy_response = self._run_agy(prompt)
        if not agy_response:
            return [{"index": j["index"], "score": 0, "reason": "agy no response"} for j in jobs_batch]
        return self._parse_json(agy_response, jobs_batch)

    def generate_cover_letter(self, title, company, description):
        if not self.is_configured:
            return ""
        prompt = f"""Write a professional cover letter for a job application.

Position: {title}
Company: {company}
Description: {description[:2000]}

Candidate background: Strong in RPA/Power Automate automation and data operations/ML QA.
Coding skills are at academic level (C#/Python/Java) but solid automation mindset.

Write a concise, compelling cover letter (3-4 paragraphs). Return ONLY the letter text, no preamble:"""
        return self._run_agy(prompt) or ""

    def _parse_json(self, text, jobs_batch):
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [{**item, "score": max(0, min(100, int(item.get("score", 0)))), "index": item.get("index", j["index"])} for item, j in zip(data, jobs_batch, strict=False)]
            return self._fallback_results(jobs_batch)
        except json.JSONDecodeError:
            pass
        m = re.search(r"\[.*?\]", text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group())
                if isinstance(data, list):
                    return [{**item, "score": max(0, min(100, int(item.get("score", 0)))), "index": item.get("index", j["index"])} for item, j in zip(data, jobs_batch, strict=False)]
            except json.JSONDecodeError:
                pass
        return self._fallback_results(jobs_batch)

    def _fallback_results(self, jobs_batch):
        return [{"index": j["index"], "score": 0, "reason": "agy parse failed"} for j in jobs_batch]
