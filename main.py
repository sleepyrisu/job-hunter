import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import config
import database as db
import telegram_notifier
from application_tracker import ApplicationTracker
from company_risk import assess_company_risk
from job_alerts import check_and_send_alerts
from job_freshness import extract_posted_days_ago, format_age
from jobspy_scraper import get_all_jobs as jobspy_get_all_jobs
from notifier import save_local_html_report, send_email_report
from rule_filter import RuleFilter
from salary_parser import extract_salary, format_salary
from score_adjuster import adjust_score
from scraper import fetch_job_description, get_all_jobs

logger = logging.getLogger("jobhunter")

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

STATUS_FILE = os.path.join(os.path.dirname(__file__), "status.json")


def update_status(status_msg, is_running=True, progress=None):
    """Single-writer status persistence, routed through webapp.state when the
    web stack is importable (avoids two modules fighting over status.json)."""
    try:
        from webapp.state import update_status as _update
        _update(status_msg, is_running, progress=progress)
        return
    except Exception:
        pass  # nosec B110  -- standalone CLI fallback below
    payload = {"status": status_msg, "is_running": is_running}
    if progress:
        payload["progress"] = progress
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:
        pass  # nosec B110


def _align_evaluator_results(batch_results, batch_size):
    """Map evaluator results onto 1-based batch positions.

    The pipeline contract is 1-based (main builds batch input with
    ``index = position + 1``). Some legacy filters historically returned
    0-based results, so a strict 0..N-1 family is translated; anything else is
    kept as-is and a lookup miss degrades to a zero-score placeholder with a
    warning instead of silently guessing.
    """
    by_index = {}
    for r in batch_results:
        try:
            by_index[int(r.get("index", 0))] = r
        except (TypeError, ValueError):
            logger.warning("Evaluator returned a non-integer index: %r (dropped)", r.get("index"))
    if by_index and min(by_index) == 0:
        by_index = {key + 1: val for key, val in sorted(by_index.items())}
    for position in range(1, batch_size + 1):
        if position not in by_index:
            logger.warning("Evaluator did not return a result for batch position %d", position)
            by_index[position] = {"index": position, "score": 0, "reason": "Result not returned by evaluator."}
    return by_index


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Starting AI Job Hunter - %s", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    warnings = config.validate_config()
    for w in warnings:
        logger.warning("%s", w)

    db.init_db()
    logger.info("Loaded database containing %d historical jobs.", db.count_jobs())

    settings = config.load_settings()
    use_ai = settings["preferences"].get("use_ai", False)

    try:
        from resume_scanner import sync_from_resume
        scan = sync_from_resume(use_agy=use_ai)
        if scan.get("success"):
            logger.info("Resume scan: %d keywords, source=%s", len(scan.get('keywords', [])), scan.get('source'))
        settings = config.load_settings()  # pick up any keyword updates written by the resume scan
    except Exception as e:
        logger.warning("Resume scan optional: %s", e)

    update_status("scraping job listings", True)
    keywords = settings["search"]["keywords"]
    locations = settings["search"]["locations"]
    platforms = settings["search"].get("platforms", {"indeed": True, "linkedin": True, "jobstreet": True})
    match_threshold = settings["preferences"]["match_threshold"]
    custom_requirements = settings["preferences"].get("custom_requirements", "")
    use_jobspy = settings["search"].get("use_jobspy", True)  # Default to JobSpy
    logger.info("Configured keywords: %s", keywords)
    logger.info("Configured locations: %s", locations)
    logger.info("Enabled platforms: %s", [k for k, v in platforms.items() if v])
    logger.info("Scraper: %s", 'JobSpy' if use_jobspy else 'Legacy')
    logger.info("AI evaluation: %s", 'ON' if use_ai else 'OFF (resume-driven rule-based matching, no AI needed)')

    if use_jobspy:
        raw_jobs = jobspy_get_all_jobs(keywords, locations, platforms)
    else:
        raw_jobs = get_all_jobs(keywords, locations, platforms)
    logger.info("Total unique raw jobs fetched from all sources: %d", len(raw_jobs))

    new_jobs = [job for job in raw_jobs if not db.job_exists(job["id"])]
    logger.info("New unseen jobs to evaluate: %d", len(new_jobs))

    if not new_jobs:
        logger.info("No new jobs found. All already evaluated. Exiting.")
        return

    update_status("fetching job descriptions", True,
                  {"step": "jd_fetch", "current": 0, "total": len(new_jobs),
                   "message": f"Fetching descriptions for {len(new_jobs)} jobs..."})
    logger.info("Fetching job descriptions in parallel (up to 15 concurrent)...")

    def fetch_jd_for_job(job):
        jd = fetch_job_description(job["url"], job["platform"])
        if not jd:
            jd = job.get("snippet", job["title"])
        return job["id"], jd

    jd_map = {}
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(fetch_jd_for_job, job): job for job in new_jobs}
        for done, future in enumerate(as_completed(futures), start=1):
            try:
                job_id, jd = future.result()
                jd_map[job_id] = jd
            except Exception:
                job = futures[future]
                jd_map[job["id"]] = job.get("snippet", job["title"])
            logger.info(f"  JD fetched: {done}/{len(new_jobs)}")
            if done % 3 == 0 or done == len(new_jobs):
                update_status(f"fetching descriptions {done}/{len(new_jobs)}", True,
                              {"step": "jd_fetch", "current": done, "total": len(new_jobs),
                               "message": f"Fetching descriptions: {done}/{len(new_jobs)}"})

    logger.info(f"All {len(new_jobs)} job descriptions fetched.")

    if use_ai:
        from agnes_filter import AgnesFilter
        from agy_filter import AgyFilter
        from ai_filter import BATCH_SIZE, AIFilter
        from gemini_filter import GeminiFilter
        agnes_filter = AgnesFilter()
        gemini_filter = GeminiFilter()
        nvidia_filter = AIFilter()
        agy_filter = AgyFilter()
        if agnes_filter.is_configured:
            ai_filter = agnes_filter
            logger.info("Using Agnes AI for evaluation.")
        elif agy_filter.is_configured:
            ai_filter = agy_filter
            logger.info("Using agy (Antigravity CLI) for evaluation.")
        elif gemini_filter.is_configured:
            ai_filter = gemini_filter
            logger.info("Using Gemini AI for evaluation.")
        elif nvidia_filter.is_configured:
            ai_filter = nvidia_filter
            logger.info("Using NVIDIA AI for evaluation.")
        else:
            ai_filter = RuleFilter()
            logger.warning("AI enabled but no API key configured. Using rule-based evaluation (no API key needed).")
    else:
        ai_filter = RuleFilter()
        BATCH_SIZE = 12
        logger.info("AI disabled (use_ai=false). Using resume-driven rule-based evaluation — no AI needed.")

    tracker = ApplicationTracker()

    new_matched_jobs = []

    total_batches = (len(new_jobs) + BATCH_SIZE - 1) // BATCH_SIZE
    logger.info("Running evaluation in %d batches of up to %d jobs...", total_batches, BATCH_SIZE)
    
    for batch_start in range(0, len(new_jobs), BATCH_SIZE):
        batch_jobs = new_jobs[batch_start : batch_start + BATCH_SIZE]
        batch_num = (batch_start // BATCH_SIZE) + 1
        update_status(f"evaluating batch {batch_num}/{total_batches}", True,
                      {"step": "ai_evaluation", "current": batch_start + len(batch_jobs), "total": len(new_jobs),
                       "message": f"AI evaluating batch {batch_num}/{total_batches}..."})
        logger.info("[Batch %d/%d] Evaluating %d jobs...", batch_num, total_batches, len(batch_jobs))

        batch_input = []
        for i, job in enumerate(batch_jobs):
            batch_input.append({
                "index": i + 1,
                "title": job["title"],
                "company": job["company"],
                "location": job.get("location", ""),
                "description": jd_map.get(job["id"], job.get("snippet", job["title"]))
            })

        if ai_filter:
            batch_results = ai_filter.evaluate_job_batch(batch_input, custom_requirements)
        else:
            batch_results = [
            {"index": j["index"], "score": 0, "reason": "AI filter not configured."}
            for j in batch_input
        ]

        # Single 1-based alignment contract: no guessing about 0/1-indexing.
        result_map = _align_evaluator_results(batch_results, len(batch_jobs))

        cover_letter_tasks = []
        batch_db_updates = {}
        
        for i, job in enumerate(batch_jobs):
            r = result_map.get(i + 1, {"score": 0, "reason": "Result not returned by AI."})

            logger.info("  [%s] -> %s%%", job['title'][:40], r['score'])

            job["scraped_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            job["cover_letter"] = None

            jd_text = jd_map.get(job["id"], job.get("snippet", job["title"]))
            risk = assess_company_risk(job["company"], jd_text, r.get("risk"))
            job["risk"] = risk
            # Stash the JD on the job for the preference layer (requirement
            # scorer scans title/company/location/description for relocation
            # /work-mode/industry evidence). Not persisted to the DB.
            job["description"] = jd_text

            rule_sal, sal_raw = extract_salary(jd_text)
            ai_sal = r.get("salary")
            if isinstance(ai_sal, (int, float)) and ai_sal > 0:
                salary_monthly = rule_sal if rule_sal is not None else int(ai_sal)
            else:
                salary_monthly = rule_sal
            if salary_monthly is not None:
                salary_raw = format_salary(salary_monthly)
            elif ai_sal is not None:
                salary_raw = f"~RM {int(ai_sal):,}/mo (AI estimate)"
            else:
                salary_raw = sal_raw or "Salary not stated"
            
            posted_days_ago = extract_posted_days_ago(jd_text)
            job["posted_days_ago"] = posted_days_ago
            job["posted_age_label"] = format_age(posted_days_ago)
            job["salary_monthly"] = salary_monthly
            job["salary_raw"] = salary_raw
            job["location"] = job.get("location", "")

            score, reason, extras = adjust_score(job, r, settings)
            
            job["score"] = score
            job["reason"] = reason
            job["kl_transfer"] = extras["kl_transfer"]
            job["kl_potential"] = extras["kl_potential"]
            job["fit_type"] = extras["fit_type"]

            if score >= match_threshold and ai_filter:
                cover_letter_tasks.append(job)

            batch_db_updates[job["id"]] = {
                "title": job["title"],
                "company": job["company"],
                "url": job["url"],
                "platform": job["platform"],
                "location": job["location"],
                "score": score,
                "reason": reason,
                "risk": risk,
                "salary_monthly": salary_monthly,
                "salary_raw": salary_raw,
                "kl_transfer": extras["kl_transfer"],
                "kl_potential": extras["kl_potential"],
                "fit_type": extras["fit_type"],
                "posted_days_ago": posted_days_ago,
                "posted_age_label": job["posted_age_label"],
                "scraped_at": job["scraped_at"],
                "cover_letter": None
            }
        
        if cover_letter_tasks:
            logger.info("  Generating %d cover letters in parallel...", len(cover_letter_tasks))
            update_status("writing cover letters...", True,
                          {"step": "cover_letters", "current": 0, "total": len(cover_letter_tasks),
                           "message": f"Generating {len(cover_letter_tasks)} cover letters..."})
            
            def gen_cl(cover_job):
                job_desc = jd_map.get(cover_job["id"], cover_job.get("snippet", cover_job["title"]))
                try:
                    cl = ai_filter.generate_cover_letter(cover_job["title"], cover_job["company"], job_desc)
                    return cover_job["id"], cl
                except Exception:
                    logger.exception("Cover letter failed for %s", cover_job['title'])
                    return cover_job["id"], None

            cl_done = 0
            with ThreadPoolExecutor(max_workers=5) as cl_executor:
                cl_futures = {cl_executor.submit(gen_cl, j): j for j in cover_letter_tasks}
                for cl_future in as_completed(cl_futures):
                    jid, cl_text = cl_future.result()
                    job = next((j for j in batch_jobs if j["id"] == jid), None)
                    if job and job["score"] >= match_threshold:
                        if cl_text:
                            job["cover_letter"] = cl_text
                            batch_db_updates[jid]["cover_letter"] = cl_text
                        new_matched_jobs.append(job)
                        tracker.add_application(
                            company=job["company"],
                            role=job["title"],
                            job_url=job["url"],
                            overall_score=job["score"],
                            verdict=job["reason"]
                        )
                        logger.info("    Match for %s (%s%%)%s",
                                    job['title'][:30], job['score'],
                                    "" if cl_text else " [cover letter skipped]")
                    cl_done += 1
                    update_status(f"cover letters {cl_done}/{len(cover_letter_tasks)}", True,
                                  {"step": "cover_letters", "current": cl_done, "total": len(cover_letter_tasks),
                                   "message": f"Cover letters: {cl_done}/{len(cover_letter_tasks)}"})
        
        db.upsert_jobs_batch(batch_db_updates)

    logger.info("Evaluation Complete. Evaluated %d new jobs.", len(new_jobs))

    if new_matched_jobs:
        logger.info(
            "Found %d new matching jobs above %s%%. Generating reports...",
            len(new_matched_jobs), match_threshold,
        )
        save_local_html_report(new_matched_jobs)
        email_sent = send_email_report(new_matched_jobs)
        if email_sent:
            logger.info("Match report email sent successfully.")

        try:
            telegram_notifier.send_telegram_report(new_matched_jobs)
        except Exception as te:
            logger.exception("Error sending Telegram notifications: %s", te)

        # Send job alerts (email/Telegram)
        try:
            check_and_send_alerts(new_matched_jobs)
        except Exception as ae:
            logger.exception("Error sending job alerts: %s", ae)
    else:
        logger.info("No new jobs met the match threshold.")

    logger.info("Database saved. Run finished.")

if __name__ == "__main__":
    main()
