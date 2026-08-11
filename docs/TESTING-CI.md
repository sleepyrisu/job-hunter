# Testing & CI

## Toolchain

| Tool | Role | Gate |
|------|------|------|
| pytest | Unit/integration tests | 195 passing |
| coverage | Code coverage | `fail_under = 90` |
| ruff | Lint + import sorting | `select = E,F,I,UP,B,SIM` |
| mypy | Static type checks | core modules clean |
| bandit | Security scan | 0 findings on core |

## Local commands

```bash
# Full test suite
pytest

# With coverage (measures the domain + webapp core, gate at 90%)
pytest --cov=webapp --cov=rule_filter --cov=score_adjuster --cov=database `
       --cov=config --cov=app --cov=models --cov=repositories `
       --cov=schema_migrations --cov=resume_scanner --cov=resume_parser `
       --cov-report=term-missing --cov-report=xml`

# Lint (project-wide rules)
ruff check .
ruff check --select I .        # import sorting only

# Type checks (maintained files)
mypy webapp models.py repositories.py schema_migrations.py config.py database.py
     rule_filter.py score_adjuster.py resume_parser.py resume_scanner.py app.py

# Security scan (core; pyproject must be passed explicitly)
bandit -c pyproject.toml webapp app.py models.py repositories.py schema_migrations.py \
       rule_filter.py score_adjuster.py resume_parser.py resume_scanner.py config.py database.py
```

## CI pipeline (`.github/workflows/ci.yml`)

Two jobs, both running on `ubuntu-latest`:

### `lint-type-security`
```
ruff check .
ruff check --select I .
mypy <10 core targets>
bandit -c pyproject.toml <core files> -r webapp
```
Failures block the merge.

### `test`
Matrix: **Python 3.11 and 3.12** (`pip install -r requirements-dev.txt`).
Runs the full coverage command above; the `--cov-fail-under` gate fails if
coverage drops below 90. Uploads `coverage.xml` as a per-python artifact
(`coverage-report-py<ver>`) so it can be inspected from the GitHub Actions UI.

## pfk_testing conventions

- `tests/conftest.py` sets `DASHBOARD_TOKEN=test-token` and provides an app fixture
  via `webapp.create_app()` so `request.test_client()` exercises the real middleware
  (auth required → tests must send `X-Auth-Token`).
- Rate limit / CSRF auto-skip when `TESTING` is configured — heavier flows don't
  trip the 429 path.
- `tests/test_500.py` asserts the middleware returns a clean JSON 500 (no stack
  trace / HTML leakage) on an intentionally-raising route.
- Tests never write to the real `jobs.db` / `settings.json` (fixtures point them at
  temp dirs).
- Legacy scraper modules are excluded from mypy/bandit via `[tool.mypy] overrides`
  and explicit path lists.

## Coverage targets by area

| Area | What is exercised |
|------|-------------------|
| `webapp/` | create_app, middleware (401/403/429/CSP), all blueprints, state/scheduler |
| `rule_filter` / `score_adjuster` | every scoring dimension + adjustment path |
| `models` / `repositories` / `schema_migrations` | validation, CRUD, migration v1→v2 |
| `config.py` | env overrides, placeholders, warnings |
| `database.py` | upserts / cascade delete / errors |
| `resume_parser` / `resume_scanner` | text extraction, keyword sync |
| `app.py` | entry + legacy re-exports |