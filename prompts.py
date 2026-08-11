"""
Shared AI prompt building blocks.

The three AI filters (NVIDIA, Agnes, Gemini) each carry a distinct scoring
narrative, but they ALL share the same machine-readable output contract: the
fields the model must return (index/score/reason/risk/salary/fit_type), the
definition of salary/risk signals, the fit_type semantics, and the raw-JSON
response format. That boilerplate is defined ONCE here so a contract change
(e.g. adding a field) is a single-file edit instead of three divergent copies.

Relocation / location / company-type / salary-transparency signals are NOT part
of the AI contract anymore — they are derived deterministically from
``custom_requirements`` by ``requirement_scorer`` and applied once by
``score_adjuster``. Keeping them out of the LLM output avoids the model
guessing at boolean flags and keeps AI-on/AI-off results identical.
"""

DEFAULT_PREFERENCES = (
    "Penang-based role preferred; strong preference for a clear path to "
    "transfer/rotate to Kuala Lumpur (KL) for career development. MNC preferred."
)

# Content-match note: the LLM is explicitly told NOT to fold location, company
# type or salary into "score" - those are the preference layer applied once by
# score_adjuster.adjust_score, so the AI-on and rule-based pipelines stay
# comparable and no bonus is ever double counted.
OUTPUT_CONTRACT = """### OUTPUT CONTRACT (every field is REQUIRED for EVERY job)

Return a raw JSON array, one object per job, each EXACTLY with:

- "index": the job number given in the batch.
- "score": 0-100 integer, CONTENT MATCH ONLY. Score the candidate's skills,
  experience, education and role fit against the job. Do NOT raise or lower it
  for location, company type or salary -- those are handled downstream by a
  single preference layer, and double counting them would skew results.
- "reason": short Chinese reason, warm and specific.
- "risk": {"level": "low"|"medium"|"high", "reason": "..."}
- "salary": monthly salary in Malaysian Ringgit (RM) as an integer if stated
  ("RM 4,500", "RM 5k", "RM 4000-5000"; divide annual by 12); otherwise null.
  Never guess.
- "fit_type": "safe" | "stretch" | "unknown"

"safe" = the role's main value is the candidate's STRONG recent skills (RPA /
Power Automate, data operations, ML QA) and does not require daily production
coding.
"stretch" = requires production coding the candidate must rebuild, but offers
mentorship/training and is junior/grad.
"unknown" = cannot determine.

RISK SEMANTICS:
- "high": known scams / pyramid / MLM / disreputable employers, or red-flag
  descriptions (upfront fees, crypto/investment pitches, WhatsApp-only contact).
- "medium": unknown or opaque employer, or an agency hiding the real company.
- "low": recognizable legitimate employer or no red flags.

EXAMPLE:
[
  {{"index": 1, "score": 85, "reason": "中文原因，温暖鼓励且具体", "risk": {{"level": "low", "reason": "可识别正规雇主"}}, "salary": 4500, "fit_type": "safe"}}
]

Only output the raw JSON array. No markdown, no explanations, no trailing text.
"""


def cover_letter_prompt(resume, job_title, job_company, job_description, behavioral=None):
    """Single source for the tailored cover-letter prompt shared by all filters.

    ``behavioral`` is optional profile context (Agnes passes it).
    """
    behavioral_block = ""
    if behavioral:
        behavioral_block = f"""

## Candidate's Profile & Motivation
{behavioral[:1500]}
"""
    return f"""You are a career expert. Write a professional, highly targeted Cover Letter (in English) for the following job posting, tailored to the candidate's resume.

## Candidate's Resume
{resume}
{behavioral_block}
## Job Details
- Title: {job_title}
- Company: {job_company}
- Job Description:
{job_description[:2000]}

## Instructions
1. Address it professionally to the Hiring Manager at {job_company}.
2. Keep it within 3 to 4 concise, impactful paragraphs.
3. Align the candidate's core strengths (RPA development, Python coding, data analytics, automation) with the specific requirements in the job description.
4. Maintain an enthusiastic, professional, and convincing tone.
5. End with a standard professional sign-off (e.g. "Sincerely, John Doe").
6. Respond ONLY with the final cover letter text. Do not wrap it in markdown, explanations, or introductory text.
7. No em-dashes, no cliches, no empty filler.
"""