import asyncio
import contextlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime

try:
    from playwright.async_api import TimeoutError as PwTimeout
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None
    PwTimeout = Exception


DIRECTORY = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.join(DIRECTORY, "status.json")
DB_FILE = os.path.join(DIRECTORY, "jobs_db.json")
SETTINGS_FILE = os.path.join(DIRECTORY, "settings.json")

_stop_event = threading.Event()
_agy_path = None


def _update_status(msg, is_running=True, progress=None):
    try:
        payload = {"status": msg, "is_running": is_running}
        if progress:
            payload["progress"] = progress
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:
        pass


def request_stop():
    _stop_event.set()

def clear_stop():
    _stop_event.clear()

def _load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_job(job):
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, encoding="utf-8") as f:
                db = json.load(f)
        else:
            db = {}
        job_id = job.get("id") or f"auto_{int(time.time())}_{random.randint(1000,9999)}"
        job["id"] = job_id
        job["scraped_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv = job.get("cover_letter")
        if cv and len(str(cv)) > 10:
            job["cover_letter"] = cv
        db[job_id] = job
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[browser_agent] save error: {e}")
        return False


def _find_agy():
    global _agy_path
    if _agy_path:
        return _agy_path
    import shutil
    _agy_path = shutil.which("agy")
    if _agy_path:
        return _agy_path
    for c in [os.path.expanduser(r"~\AppData\Local\agy\bin\agy.exe"),
              os.path.expanduser(r"~\AppData\Local\agy\bin\agy")]:
        if os.path.isfile(c):
            _agy_path = c
            return c
    return None


async def _screenshot(page) -> str:
    raw = await page.screenshot(type="png")
    path = os.path.join(tempfile.gettempdir(), f"agy_vision_{int(time.time())}_{random.randint(1000,9999)}.png")
    with open(path, "wb") as f:
        f.write(raw)
    return path


def _agy_vision_analyze(image_path: str, prompt: str, timeout=120) -> str:
    agy = _find_agy()
    if not agy:
        raise RuntimeError("agy not found — install Antigravity CLI first")
    full_prompt = f"{prompt}\n\nImage file: {image_path}"
    r = subprocess.run(
        [agy, "--dangerously-skip-permissions", "-p", full_prompt, "--model", "gemini-3.6-flash-high"],
        capture_output=True, text=True, timeout=timeout,
        env={**os.environ}
    )
    # Clean up temp image
    with contextlib.suppress(Exception):
        os.remove(image_path)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    if r.stdout.strip():
        return r.stdout.strip()
    raise RuntimeError(f"agy vision failed: {r.stderr[:200]}")


def _rand_delay(a=0.8, b=2.5):
    time.sleep(random.uniform(a, b))


JOB_SITES = {
    "indeed": "https://my.indeed.com",
    "jobstreet": "https://www.jobstreet.com.my",
    "linkedin": "https://www.linkedin.com/jobs",
}


class BrowserAgent:
    def __init__(self, headless=False):
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None
        self._stop = False

    async def start(self):
        if async_playwright is None:
            raise RuntimeError("playwright not installed")
        if not _find_agy():
            raise RuntimeError("agy not found — install Antigravity CLI first")
        p = await async_playwright().start()
        self.browser = await p.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        self.page = await self.context.new_page()
        _update_status("Browser ready (agy vision)")

    async def stop(self):
        self._stop = True
        if self.browser:
            await self.browser.close()
        _update_status("Browser stopped", is_running=False)

    async def search_indeed(self, keyword, location):
        if _stop_event.is_set():
            return []
        site = "https://my.indeed.com"
        await self.page.goto(site, wait_until="domcontentloaded")
        _rand_delay(1, 2)
        # Fill search
        try:
            search_box = await self.page.wait_for_selector("#text-input-what", timeout=8000)
            await search_box.fill("")
            await search_box.type(keyword, delay=random.randint(30, 80))
        except Exception:
            pass
        if _stop_event.is_set():
            return []
        _rand_delay(0.5, 1)
        try:
            loc_box = await self.page.wait_for_selector("#text-input-where", timeout=5000)
            await loc_box.fill("")
            await loc_box.type(location, delay=random.randint(30, 80))
        except Exception:
            pass
        _rand_delay(0.5, 1)
        if _stop_event.is_set():
            return []
        try:
            await self.page.click("button[type='submit']")
        except Exception:
            with contextlib.suppress(Exception):
                await self.page.keyboard.press("Enter")
        await self.page.wait_for_load_state("domcontentloaded")
        _rand_delay(1.5, 3)

        jobs = []
        seen_urls = set()
        for page_num in range(1, 4):
            if self._stop or _stop_event.is_set():
                break
            _update_status(f"Indeed: parsing page {page_num} of {keyword}")
            _rand_delay(1, 2.5)
            # Get listings
            cards = await self.page.query_selector_all(
                "div.job_seen_beacon, .jobsearch-SerpJobCard, .cardOutline, "
                "table[role='presentation'] td a[id^='job_']"
            )
            if not cards:
                jk_links = await self.page.query_selector_all("a.jcs-JobTitle")
                if jk_links:
                    cards = jk_links
            if not cards:
                break

            for idx, card in enumerate(cards[:15]):
                if self._stop or _stop_event.is_set():
                    break
                try:
                    link = await card.query_selector("a")
                    if not link:
                        link = card if await card.get_attribute("href") else None
                    if not link:
                        continue
                    href = await link.get_attribute("href")
                    if not href:
                        continue
                    url = href if href.startswith("http") else f"{site}{href}"
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    await link.click()
                    _rand_delay(1, 2.5)

                    # Wait for JD to load
                    with contextlib.suppress(Exception):
                        await self.page.wait_for_selector(
                            "#jobDescriptionText, .jobsearch-JobComponent-description, "
                            ".jobsearch-jobDescriptionText",
                            timeout=10000,
                        )
                    _rand_delay(0.5, 1.5)

                    # Use agy vision to analyze the job page
                    screenshot_path = await _screenshot(self.page)
                    prompt = (
                        "You are helping a job hunter. The candidate has a DIPLOMA (not degree) and ~1yr experience "
                        "(10mo Data Analyst + 3mo RPA intern). "
                        "Strongest skills: RPA/Power Automate, data QA/classification."
                        "Look at this job page. Extract: job_title, company, location, salary (if visible). "
                        "Rate fit 0-100. "
                        "PENALIZE -30 if requires 'Bachelor/Degree'. PENALIZE -20 if requires '3+ years'. "
                        "BONUS +15 if mentions 'Diploma'/'Entry Level'/'Training Provided'/'Fresh Graduate'."
                        "Return JSON: {\"title\":\"...\", \"company\":\"...\", \"location\":\"...\", "
                        "\"salary_raw\":\"...\", \"description_summary\":\"...\", \"score\":0-100, "
                        "\"fit_type\":\"safe|stretch|unknown\"}"
                    )
                    try:
                        result_text = _agy_vision_analyze(screenshot_path, prompt)
                    except Exception as e:
                        print(f"[browser_agent] agy vision error: {e}")
                        continue

                    # Parse JSON from response
                    job_data = _parse_gemini_json(result_text)
                    if job_data:
                        job_data["url"] = url
                        job_data["platform"] = "indeed"
                        job_data["id"] = f"auto_indeed_{int(time.time())}_{idx}"
                        jobs.append(job_data)
                        _save_job(job_data)

                except Exception as e:
                    print(f"[browser_agent] card error: {e}")
                    continue

            # Next page
            try:
                next_btn = await self.page.query_selector(
                "a[data-testid='pagination-page-next'], a[aria-label='Next'], "
                ".pagination a:has-text('Next')"
            )
                if next_btn:
                    await next_btn.click()
                    await self.page.wait_for_load_state("domcontentloaded")
                    _rand_delay(1.5, 3)
                else:
                    break
            except Exception:
                break

        return jobs

    async def search_jobstreet(self, keyword, location):
        if _stop_event.is_set():
            return []
        site = "https://www.jobstreet.com.my"
        await self.page.goto(f"{site}/en/job-search/{keyword}/", wait_until="domcontentloaded")
        _rand_delay(1, 2)
        return await self._search_listings(site, keyword)

    async def _search_listings(self, site, keyword):
        jobs = []
        seen_urls = set()
        for page_num in range(1, 3):
            if self._stop or _stop_event.is_set():
                break
            _update_status(f"Searching page {page_num} for {keyword}")
            _rand_delay(1, 2)
            cards = await self.page.query_selector_all(
                "article[data-automation*='jobCard'], div[data-automation*='jobCard'], "
                "a[data-automation*='jobTitle']"
            )
            if not cards:
                links = await self.page.query_selector_all("a[href*='/job/']")
                cards = links
            if not cards:
                break

            for idx, card in enumerate(cards[:20]):
                if self._stop or _stop_event.is_set():
                    break
                try:
                    href = await card.get_attribute("href")
                    if not href:
                        continue
                    url = href if href.startswith("http") else f"{site}{href}"
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    await self.page.goto(url, wait_until="domcontentloaded")
                    _rand_delay(1, 2)

                    ss_path = await _screenshot(self.page)
                    prompt = (
                        "Extract from this job page: title, company, location, salary(if any). "
                        "Candidate has DIPLOMA + 1yr experience. "
                        "Note if job requires Degree or 3+yr experience. "
                        "Return JSON: {\"title\":\"...\",\"company\":\"...\",\"location\":\"...\","
                        "\"salary_raw\":\"...\",\"requires_degree\":true/false,"
                        "\"min_experience_years\":0}"
                    )
                    try:
                        text = _agy_vision_analyze(ss_path, prompt)
                    except Exception:
                        continue
                    data = _parse_gemini_json(text)
                    if data:
                        data["url"] = url
                        data["platform"] = "jobstreet"
                        data["id"] = f"auto_js_{int(time.time())}_{idx}"
                        jobs.append(data)
                        _save_job(data)
                except Exception:
                    continue

            # Next page
            try:
                next_btn = await self.page.query_selector("a[data-automation*='next'], a:has-text('Next')")
                if next_btn:
                    await next_btn.click()
                    await self.page.wait_for_load_state("domcontentloaded")
                    _rand_delay(1.5, 3)
                else:
                    break
            except Exception:
                break
        return jobs


def _parse_gemini_json(text):
    text = text.strip()
    # Remove markdown wrapping
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    # Try extracting first JSON object
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None


# ========= Synchronous wrappers for Flask =========

def run_search_sync(keywords=None, locations=None, headless=False):
    """Run browser agent. If no keywords given, reads from resume + settings."""
    if not keywords or not locations:
        try:
            from resume_scanner import sync_from_resume
            r = sync_from_resume(use_agy=True)
            keywords = keywords or r.get("keywords")
            locations = locations or r.get("locations")
        except Exception as e:
            print(f"[browser_agent] resume scan error: {e}")
        if not keywords:
            try:
                import config as cfg
                keywords = keywords or cfg.SEARCH_KEYWORDS
                locations = locations or cfg.LOCATIONS
            except Exception:
                keywords = keywords or ["RPA Developer", "Data Analyst"]
                locations = locations or ["Penang, Malaysia"]

    agent = BrowserAgent(headless=headless)
    all_jobs = []

    async def _run():
        nonlocal all_jobs
        try:
            clear_stop()
            await agent.start()
            for kw in keywords:
                if _stop_event.is_set():
                    break
                for loc in locations:
                    if _stop_event.is_set():
                        break
                    _update_status(f"Searching: {kw} in {loc}")
                    try:
                        jobs = await agent.search_indeed(kw, loc)
                        all_jobs.extend(jobs)
                    except Exception as e:
                        print(f"[browser_agent] error searching {kw}/{loc}: {e}")
                        continue
        finally:
            await agent.stop()
            clear_stop()
        _update_status(f"Done. Found {len(all_jobs)} jobs", is_running=False)
        return all_jobs

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_run())
        loop.close()
        return result
    except Exception as e:
        _update_status(f"Error: {e}", is_running=False)
        return all_jobs


if __name__ == "__main__":
    kw = sys.argv[1] if len(sys.argv) > 1 else "RPA Developer"
    loc = sys.argv[2] if len(sys.argv) > 2 else "Penang, Malaysia"
    print(f"Testing browser agent: {kw} in {loc}")
    jobs = run_search_sync([kw], [loc], headless=False)
    print(f"Found {len(jobs)} jobs")
