# AI Job Hunter

[English](README.md) | [中文](README.zh.md)

AI-driven job hunting assistant: automatically scrapes job postings, evaluates match against your resume, generates cover letters, and shows real-time progress in a web dashboard.

Upload your resume to the dashboard and it automatically starts searching for matching jobs — no need to click "Start".

## Core Features

- **Resume-driven setup**: upload a PDF / Word / Markdown / TXT resume; skills, keywords, and location preferences are extracted automatically and written back to `settings.json`; a background search kicks off immediately after upload
- **Multi-platform scraping**: Indeed, LinkedIn, JobStreet (RSS / jobspy / browser-agent backends)
- **Multi-dimension matching score**: skill weighting, education requirement, experience years, salary parsing, company risk, posting freshness, location preference (pluggable rule engine)
- **Cover letter generation**: batch-generates tailored cover letters for high-match roles
- **Scheduled background runs**: repeat the search automatically at a set interval (`/api/scheduler`)
- **Application tracking**: records applied / interview / offer / rejected status
- **Local dashboard**: Flask web UI with real-time progress and one-click run / stop / reset
- **Notifications**: email + Telegram alerts push new matching jobs instantly

## Quick Start

```bash
# 1. Configure environment variables (API keys, DASHBOARD_TOKEN)
copy .env.example .env

# 2. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt   # development / testing only

# 3. Optional: install Playwright browsers (only needed for browser-agent scraping)
playwright install chromium

# 4. Start
python app.py
```

Open <http://localhost:8888>. If `DASHBOARD_TOKEN` is set, you will be asked for a password on first visit.

> Fully offline capable: with the default `use_ai=false`, the full scrape + rule-scoring + basic cover-letter flow works with no AI API key at all.

## Workflow

```
Upload resume (resume.pdf/.docx/.md)
      │
      ▼
resume_parser ──► resume_scanner ──► settings.json (keywords/locations)
      │                                    │
      ▼                                    ▼
      └────────► main.run_job_hunter() ◄──  or dashboard [Run] / scheduler
                     │
      ┌──────────────┼───────────────┐
      ▼              ▼               ▼
 jobspy/RSS    rule-engine score    AI score (optional)
      │              │               │
      ▼              ▼               ▼
  dedupe/store ──► jobs.db ──► cover letters ──► email/Telegram alerts
```

## Scoring

Every job is scored 0-100 (see `rule_filter.py`, `score_adjuster.py`):

- Skill match (weighted keywords, split into programming / framework / data / cloud / RPA / AI)
- Education fit (Diploma/fresh-graduate friendly vs Degree required)
- Experience (penalty for 3+ years required)
- Salary parsing and comparison
- Company risk (scam / blacklist detection)
- Posting freshness (30-day window)
- Location and MNC / KL-transfer preferences

## Architecture

```
app.py                     entry point (app factory + startup, gunicorn-compatible)
webapp/
  __init__.py              create_app() factory: blueprint registration + security middleware
  security.py              Token auth / CSRF / rate limit / security headers
  state.py                 run state + background runner + scheduler
  routes/                  blueprints: dashboard / jobs / settings / run / scheduler / browser / resume
config.py                  config loading (settings.json + .env overrides + validation warnings)
models.py                  domain models (Job / Application / UserProfile) + validation
repositories.py            repository layer (JobRepository / UserProfileRepository)
schema_migrations.py       SQLite schema migrations (PRAGMA user_version)
database.py                database operations
rule_filter.py / score_adjuster.py / resume_parser.py ...   scoring/parsing core
tests/                     232 tests, 90%+ coverage
```

## API Overview

| Method | Path | Description |
|--------|------|-------------|
| GET  | `/` , `/dashboard.html` | Dashboard page |
| GET  | `/api/jobs` | All jobs |
| GET  | `/api/jobs/stats` | Application status stats |
| POST | `/api/jobs/status` | Update job status (`{id, status}`) |
| POST | `/api/jobs/delete` | Delete a job (`{id}`) |
| POST | `/api/jobs/delete-batch` | Batch delete (`{ids: []}`) |
| POST | `/api/jobs/clear-all` | Clear all |
| POST | `/api/upload-resume` | Upload resume (auto-starts search) |
| POST | `/api/resume-scan` | Re-extract keywords with agy |
| POST | `/api/run` | Start one full background search |
| GET  | `/api/status` | Current run state |
| POST | `/api/reset` | Reset state to idle |
| GET/POST | `/api/settings` | Read / deep-merge save settings |
| GET/POST | `/api/scheduler` | Read / set scheduled runs |
| POST | `/api/browser/start` , `/api/browser/stop` | Browser-agent scraping control |
| GET  | `/api/applications` | Application records |

Full details in [docs/API.md](docs/API.md).

## Security

- Optional `DASHBOARD_TOKEN` auth (constant-time `hmac.compare_digest`)
- CSRF validation for mutating requests (custom header)
- 60 req/min in-memory rate limiting
- Security headers (CSP, `X-Frame-Options: DENY`, nosniff, HSTS, no-store)
- Upload extension whitelist + 16MB limit + filename path-traversal guard + oversized-content truncation
- Production `SECRET_KEY` overrides the default
- Tests/CI use a fixed test `DASHBOARD_TOKEN`

## Testing & CI

```bash
pytest                                   # 232 tests
pytest --cov=webapp --cov=... --cov-report=term-missing   # coverage ≥90%
ruff check .                             # E,F,I,UP,B,SIM rules
mypy webapp models.py ...                # type checking (core modules)
bandit -c pyproject.toml webapp app.py ...  # security scan
```

CI (`.github/workflows/ci.yml`): Python 3.11/3.12 matrix, ruff + mypy + bandit + pytest/coverage gate (`fail_under = 90`).

## Deployment (Render.com / Docker)

- **Render**: Build `pip install -r requirements.txt && playwright install chromium --with-deps`; Start `gunicorn --bind 0.0.0.0:8888 --workers 2 --threads 4 app:app`
- **Docker**: `docker build -t ai-job-hunter .` (see `Dockerfile`)

## Docs

- `docs/API.md` — API reference
- `docs/ARCHITECTURE.md` — architecture & data flow
- `docs/SECURITY.md` — security model & threats

## Acknowledgements

- The multi-dimension scoring framework is inspired by [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) (MIT License)

## Disclaimer

- This tool is intended for personal use. Automated scraping of LinkedIn / Indeed / JobStreet may violate their terms of service. Keep request volumes low and use at your own risk.
- This project depends only on permissively licensed open-source libraries (MIT / BSD / Apache).

## License

MIT
