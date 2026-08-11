# API Reference

Base URL: `http://localhost:8888` (configurable via `PORT` in `app.py`).

All endpoints return JSON. When `DASHBOARD_TOKEN` is set, every request must include
the header `X-Auth-Token: <token>`. Mutating requests also require the header
`X-CSRF-Token: 1` (see [SECURITY.md](SECURITY.md)).

> Job ids are full URLs (contain slashes), so **URL-based mutations accept the id in
> the JSON body**, not as a path segment. The legacy `DELETE /api/jobs/<id>` only works
> for simple ids.

---

## Dashboard

### `GET /`
### `GET /dashboard.html`
Serves the single-page dashboard.

---

## Jobs

### `GET /api/jobs`
Returns all scraped jobs. Each job has at least:

```json
{
  "id": "Indeed de3f...",
  "title": "Data Analyst",
  "company": "Penang Tech Sdn Bhd",
  "location": "Bayan Lepas, Penang",
  "salary": null,
  "score": 82,
  "status": "new",
  "url": "https://..."
}
```

### `GET /api/jobs/stats`
Application-status breakdown:

```json
{
  "new": 12, "saved": 0, "applied": 3, "interviewing": 1, "rejected": 1, "offered": 0,
  "avg_score": 76.5, "flagged": 2
}
```

### `POST /api/jobs/status`
Update a job's application status.

Body: `{"id": "<job_id>", "status": "applied"}`

Valid statuses: `new | saved | applied | interviewing | offered | rejected`
(invalid ids/statuses → `400`; missing job → `404`).

### `POST /api/jobs/delete`
Delete one job by id (id may be a URL).

Body: `{"id": "<job_id>"}`  (alias: `job_id`)

### `POST /api/jobs/delete-batch`
Delete many jobs at once.

Body: `{"ids": ["id1", "id2", ...]}` → `{"message": "Successfully deleted N jobs."}`

### `POST /api/jobs/clear-all`
Delete **all** jobs. → `{"message": "All job data cleared."}`

### `DELETE /api/jobs/<job_id>`
Legacy delete for simple ids. Prefer `POST /api/jobs/delete`.

### `GET /api/applications`
Returns the application-tracking CSV as a list of records (from `ApplicationTracker`).

---

## Resume

### `POST /api/upload-resume`
Upload a resume and update search configuration from it.

- Multipart field: `resume` (file)
- Allowed extensions: `.pdf .doc .docx .md .txt` (max 16 MB)
- Form field `auto_run` (default `1`): set to `0` to skip auto-searching

Behavior:
1. Saves file as `resume<ext>` and extracts plain text → `resume.md`
2. Persists profile in `user_profile` (SQLite)
3. Runs `resume_scanner.sync_from_resume(use_agy=False)` → updates `settings.json`
   keywords/locations from the resume
4. Unless `auto_run=0` or a run is already in progress, starts the full
   background job search automatically

Response:

```json
{
  "success": true,
  "message": "Resume uploaded: cv.pdf. Auto-searching matching jobs...",
  "filename": "cv.pdf",
  "auto_search": true
}
```

### `POST /api/resume-scan`
Re-extract keywords using the `agy` CLI (vision mode, optional). Returns the new
keywords/locations, or `500 {"success": false}`.

---

## Run / Status

### `POST /api/run`
Start one full background search run.

- `200 {"success": true}` if started
- `400 {"success": false, "message": "Scraper is already running..."}` if one is active

### `GET /api/status`
Current pipeline status:

```json
{
  "status": "scraping jobs...",
  "is_running": true
}
```

### `POST /api/reset`
Reset status to `idle`.

---

## Settings

### `GET /api/settings`
Returns the full merged settings object (defaults + `settings.json` + env overrides).

### `POST /api/settings`
Save settings. **Deep-merges** into the existing file so unrelated sections
(ai/security/notifications) are preserved.

Body example:

```json
{
  "search": { "keywords": ["Data Analyst", "RPA Developer"] },
  "preferences": { "match_threshold": 80 }
}
```

---

## Scheduler

### `GET /api/scheduler`
```json
{"enabled": true, "interval_hours": 6, "next_run_at": 1712345678.0}
```

### `POST /api/scheduler`
Set the schedule. `next_run_at` is auto-computed when enabling.

Body: `{"enabled": true, "interval_hours": 3}`

---

## Browser Agent

### `POST /api/browser/start`
Start a visible (headed) Playwright Chrome session to scrape listings.

Body (optional): `{"keywords": [...], "locations": [...]}` — defaults to settings.

### `POST /api/browser/stop`
Send a stop signal to the running browser agent.

---

## Errors

Errors use the shape `{"error": "<message>"}` and an HTTP status code:

| Code | Meaning |
|------|---------|
| 400 | Bad request / validation failed / already running |
| 401 | Missing or wrong `X-Auth-Token` |
| 403 | Missing `X-CSRF-Token` on a mutating request |
| 404 | Job not found |
| 429 | Rate limit exceeded (60/min) |
| 500 | Internal error (a `detail` field may include the traceback message) |