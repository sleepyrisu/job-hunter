"""Gunicorn configuration (auto-loaded from the working directory).

``app.py`` only starts the scheduler loop when launched via ``python app.py``.
When run under gunicorn (Render, Docker) this file loads instead, so scheduled
runs keep working: the scheduler thread lives in the master process and shares
state with the web workers through ``status.json`` and the SQLite database.

Overrides for bind/workers/threads can still be passed on the command line.
"""
from __future__ import annotations

import threading

from webapp.state import scheduler_loop

bind = "0.0.0.0:8888"
workers = 1
threads = 4
timeout = 120


def when_ready(server):
    """Spawn the scheduler thread in the master process once workers are up."""
    threading.Thread(target=scheduler_loop, daemon=True).start()
