"""
Entry point for the AI Job Hunter web dashboard.

Builds the Flask app via the ``webapp`` factory. Running this module directly
starts the scheduler loop and opens the dashboard in the default browser.

Compatible with ``gunicorn app:app`` and ``python run_app.py``.
"""
from __future__ import annotations

import sys
import threading

from webapp import create_app

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        # reconfigure is best-effort on older consoles.
        pass  # nosec B110

app = create_app()

# Re-exported for compatibility with the test suite and legacy imports.
from webapp.state import (  # noqa: E402, F401
    DIRECTORY,
    browser_running,
    current_status,
    is_running_flag,
    load_scheduler_state,
    reset_status,
    run_job_hunter_async,
    save_scheduler_state,
    scheduler_loop,
    update_status,
)

PORT = 8888


def start_scheduler():
    threading.Thread(target=scheduler_loop, daemon=True).start()


if __name__ == "__main__":
    import webbrowser

    url = f"http://localhost:{PORT}"
    print(f"Starting Flask server on port {PORT}...")
    print(f"Open browser to: {url}")
    import config

    if config.DASHBOARD_TOKEN:
        print("Dashboard access token is enabled (DASHBOARD_TOKEN).")
    threading.Thread(target=scheduler_loop, daemon=True).start()
    timer = threading.Timer(1.5, lambda: webbrowser.open(url))
    timer.start()
    # LAN dashboard; auth is enforced by DASHBOARD_TOKEN.
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)  # nosec B104
