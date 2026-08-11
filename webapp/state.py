"""
Shared application state and the background job-hunting runner.

Holds the run lock / running flag / status that drive the scraper pipeline,
the browser-agent flag, and the scheduler state helpers. This module is
imported by the web routes and by the entry point so the status is visible
to both the API and the CLI.
"""
from __future__ import annotations

import contextlib
import json
import os
import threading
import time
from typing import Any

import config
import main as job_hunter_main

DIRECTORY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _status_file() -> str:
    return os.path.join(DIRECTORY, "status.json")


def _requests_log() -> str:
    return os.path.join(DIRECTORY, "requests.log")


def _error_log() -> str:
    return os.path.join(DIRECTORY, "error.log")


def _settings_file() -> str:
    # Route settings persistence through config so tests can redirect it.
    return config.SETTINGS_FILE

run_lock = threading.Lock()
is_running_flag = False
current_status = "idle"
browser_running = False

# Guard ensuring only ONE process (gunicorn worker) runs the pipeline at a time.
# The in-memory flag above is per-process; an advisory OS file lock extends the
# mutual-exclusion to multiple workers sharing the project directory.
_lock_fd: int | None = None


def _run_lock_path() -> str:
    return os.path.join(DIRECTORY, ".job_hunter.run.lock")


def _acquire_crossprocess_run_lock() -> bool:
    """Best-effort non-blocking advisory lock for the pipeline run.

    Returns True if THIS process acquired it (safe to run), False if another
    process already holds it. On failure (unusual/unlocked FS) the run is NOT
    blocked: the in-memory flag still gives single-worker correctness.
    """
    global _lock_fd
    try:
        path = _run_lock_path()
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"0")
        os.lseek(fd, 0, os.SEEK_SET)
        if os.name == "nt":  # pragma: win32
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:  # pragma: posix
            import fcntl  # pragma: no cover
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]  # pragma: no cover
        _lock_fd = fd
        return True
    except OSError:
        with contextlib.suppress(OSError):
            os.close(fd)
        _lock_fd = None
        return False
    except Exception:
        with contextlib.suppress(OSError):
            os.close(fd)
        _lock_fd = None
        return False


def _release_crossprocess_run_lock() -> None:
    global _lock_fd
    fd = _lock_fd
    _lock_fd = None
    if fd is None:
        return
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        with contextlib.suppress(Exception):
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:  # pragma: posix
                import fcntl  # pragma: no cover
                fcntl.flock(fd, fcntl.LOCK_UN)  # type: ignore[attr-defined]  # pragma: no cover
    finally:
        os.close(fd)


def update_status(status_msg: str, is_running: bool | None = None, progress: dict | None = None) -> None:
    """Persist the current run status to status.json (best effort)."""
    global current_status, is_running_flag
    with run_lock:
        current_status = status_msg
        if is_running is not None:
            is_running_flag = is_running
        payload: dict[str, Any] = {"status": current_status, "is_running": is_running_flag}
        if progress is not None:
            payload["progress"] = progress
        with contextlib.suppress(Exception), open(_status_file(), "w", encoding="utf-8") as f:
            json.dump(payload, f)


update_status("idle", False)


def run_job_hunter_async() -> None:
    """Run the full job-hunting pipeline in the background. No-op if already running."""
    global is_running_flag
    with run_lock:
        if is_running_flag:
            return
        # Reject the run when another worker process holds the advisory lock so
        # ``gunicorn --workers N`` cannot launch the scraper N times in parallel.
        if not _acquire_crossprocess_run_lock():
            print("Another worker process is already running the pipeline; skipping this run.")
            return
        is_running_flag = True
    try:
        update_status("scraping", True)
        config.load_settings()
        job_hunter_main.main()
    except Exception as e:
        import traceback
        err_msg = f"Error in background run: {e}\n{traceback.format_exc()}"
        print(err_msg)
        with contextlib.suppress(Exception), open(_error_log(), "w", encoding="utf-8") as err_f:
                err_f.write(err_msg)
        update_status(f"Error: {str(e)}", False)
    finally:
        with run_lock:
            is_running_flag = False
        _release_crossprocess_run_lock()
        try:
            with open(_status_file(), encoding="utf-8") as sf:
                current_sf = json.load(sf)
            if not current_sf.get("status", "").startswith("Error"):
                update_status("idle", False)
        except Exception:
            update_status("idle", False)
        print("Scraper run finished. Flag reset to idle.")


def get_run_status() -> dict[str, Any]:
    """Return the current run status (from status.json if available)."""
    with contextlib.suppress(Exception):
        if os.path.exists(_status_file()):
            with open(_status_file(), encoding="utf-8") as f:
                return json.load(f)
    return {"status": current_status, "is_running": is_running_flag}


def start_background_run() -> bool:
    """Start the pipeline in a daemon thread. Returns False if already running."""
    global is_running_flag
    if is_running_flag:
        return False
    thread = threading.Thread(target=run_job_hunter_async, daemon=True)
    thread.start()
    return True


def reset_status() -> None:
    """Force the run status back to idle."""
    update_status("idle", False)


# ---------------------------------------------------------------------------
# Scheduler state persistence
# ---------------------------------------------------------------------------


def load_scheduler_state() -> dict[str, Any]:
    cfg = config.load_settings().get("scheduler", {})
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "interval_hours": int(cfg.get("interval_hours", 6)),
        "next_run_at": cfg.get("next_run_at"),
    }


def save_scheduler_state(state: dict[str, Any]) -> None:
    settings_file = _settings_file()
    try:
        with open(settings_file, encoding="utf-8") as f:
            current = json.load(f)
    except Exception:
        current = {}
    current.setdefault("scheduler", {})
    for key in ("enabled", "interval_hours", "next_run_at"):
        if key in state:
            current["scheduler"][key] = state[key]
    with open(settings_file, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2, ensure_ascii=False)
    config.load_settings()


def scheduler_loop() -> None:
    """Daemon loop: periodically trigger the pipeline when the scheduler is enabled."""
    while True:
        try:
            state = load_scheduler_state()
            if state["enabled"]:
                now = time.time()
                next_at = state.get("next_run_at")
                due = next_at is None or now >= float(next_at)
                if due:
                    with run_lock:
                        already_running = is_running_flag
                    if not already_running:
                        print(f"Scheduler: starting scheduled run ({state['interval_hours']}h interval)")
                        start_background_run()
                    state["next_run_at"] = now + state["interval_hours"] * 3600
                    save_scheduler_state(state)
        except Exception as e:
            print(f"Scheduler loop error: {e}")
        time.sleep(30)
