# Architecture

## Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        dashboard.html (Flask UI)                    │
│                         served by webapp/routes/dashboard.py         │
└───────────────┬─────────────────────────────────────────────────────┘
                │  fetch / 调用 REST API (fetch API, X-Auth-Token)
┌───────────────▼─────────────────────────────────────────────────────┐
│                         Flask Application (create_app)              │
│  app.py ──► webapp/__init__.py  (factory + middleware)               │
│                                                                      │
│   middleware (order):                                                │
│   1. log_request_info     2. require_auth      3. require_csrf       │
│   4. apply_rate_limit     5. apply_security_headers (after)          │
│                                                                      │
│   blueprints: dashboard · jobs · settings · run · scheduler         │
│               browser · resume                                        │
└──────┬──────────┬──────────────┬─────────────────┬──────────────────┘
       │          │              │                 │
       │  config  │  jobs        │  upload-resume  │  browser
       │  (get/   │  (CRUD +     │  (parse +       │  (Playwright
       │   post)  │   status)    │   auto-search)   │   agent)
       ▼          ▼              ▼                 ▼
  settings.json   jobs.db    resume.md         status.json
  .env      ──►   (SQLite)   resume<ext>        requests.log / error.log
```

## Module responsibilities

### `app.py` (entry point)
- Builds the app with `webapp.create_app()`
- Re-exports shared state (`DIRECTORY`, `run_job_hunter_async`, `scheduler_loop`, `is_running_flag`, ...) so legacy CLI/test imports keep working
- `if __name__ == "__main__"`: starts the scheduler thread, opens the dashboard, and runs `app.run(host="0.0.0.0", port=PORT)` — bind-all is intentional (LAN dashboard); auth is enforced by `DASHBOARD_TOKEN`
- Gunicorn-compatible (`gunicorn app:app`)

### `webapp/__init__.py` — app factory
- `create_app()` returns a configured Flask instance (no global side effects), which is what makes the whole app trivially testable with `app.test_client()`
- Registers the security middleware in a fixed order and all seven blueprints
- On startup resets status to `idle`

### `webapp/security.py` — middleware
- `require_auth`: when `config.DASHBOARD_TOKEN` is non-empty, validates `X-Auth-Token` with `hmac.compare_digest` (constant time). Missing/wrong → 401
- `require_csrf`: mutating methods (`POST/PUT/PATCH/DELETE`) must send `X-CSRF-Token: 1` when a dashboard token is configured → 403 otherwise
- `apply_rate_limit`: in-memory sliding-window, 60 req/min per client IP from their private address family; skipped during test runs (`TESTING`)
- `apply_security_headers`: CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, HSTS (when HTTPS), `Cache-Control: no-store`
- Helpers: `json_error(status, message)`, `wrap_route(fn)` (converts raised exceptions to 500 JSON)

### `webapp/state.py` — shared runtime state
Single source of truth for the scraper process:

- `run_lock` / `is_running_flag` / `current_status` — whether the pipeline is active
- `update_status(status, running)` — persists to `status.json` (best-effort)
- `run_job_hunter_async()` — wraps `main.run()`, locks against concurrent runs,
  writes `error.log` on failure, always resets to idle
- `scheduler_loop()` — daemon loop; when `scheduler.enabled` and due, kicks off a run
- `load_scheduler_state()` / `save_scheduler_state()` — persisted via `config.SETTINGS_FILE`

### `config.py` — configuration
- Defaults dict → `settings.json` → `.env` overrides (deep merge, env wins only when
  unset in file, placeholder detection for API keys)
- `_sync_globals()` publishes values to module globals used by legacy modules
- `validate_config()` warns on invalid combinations (e.g. `use_ai=true` with no key)

### `models.py` — domain layer
Typed dataclasses with validation:
- `Job` (`is_match` helper), `Application`, `UserProfile`
- `APPLICATION_STATUSES` + `VALID_STATUSES` + `can_transition(from, to)`
- `validate_job_id` (rejects control characters), `validate_application_status`,
  `validate_settings_update`

### `schema_migrations.py` + `database.py` — persistence
- `SCHEMA_VERSION = 2`, migrations keyed to `PRAGMA user_version`
- `database.init_db()` applies pending migrations then creates `user_profile` + indexes
- Thread-safe connection handling; JSON fields (`risk`, `preferences`) serialized
- `migrate_from_json()` one-off import from the legacy `jobs_db.json`

### `repositories.py` — repository layer
- `JobRepository` (list/get/upsert/delete/status/stats), `JobSearchStatsRepository`,
  `UserProfileRepository` — typed error classes (`JobNotFoundError`, `InvalidJobIdError`,
  `InvalidStatusError`)

### Scoring pipeline (rule-based, offline by default)
1. `jobspy_scraper` / `scraper` (RSS) / `browser_agent` (Playwright) fetch jobs
2. `resume_parser` extracts skills/education/experience/locations from resume.md
3. `rule_filter` scores each job 0-100:
   - skills (weighted by category: programming/framework/data/cloud/RPA/AI)
   - education (Diploma vs Degree), experience years, salary, company risk,
     posting freshness, location/transfer preference, news/exclusions
4. `score_adjuster` applies final tweaks (bonuses/penalties from custom requirements)
5. `main.run_job_hunter()` dedupes, persists to `jobs.db`, generates cover letters
   (`pdf_generator` / inline), fires `job_alerts` (email + Telegram)

## Data files

| File | Purpose |
|------|---------|
| `jobs.db` | SQLite: `jobs`, `user_profile` |
| `settings.json` | Search keywords, locations, preferences, AI/security keys |
| `status.json` | Live pipeline status (scratch) |
| `resume.md` | Latest resume plaintext used for scoring |
| `requests.log` / `error.log` | Request log + background-run errors |
| `job_search_tracker.csv` | Application tracker |

## Background vs foreground

- **Web/Scheduler runs** call `run_job_hunter_async` in a daemon thread; `/api/status`
  reflects progress and concurrency is guarded by a thread lock.
- The domain/repository/test layers are intentionally **import-order independent**:
  `webapp.state` and `webapp` don't create global Flask instances at import time.