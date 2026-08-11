"""Coverage for the background pipeline runner in webapp.state (mocked, no real scraping)."""
import contextlib

import webapp.state


class FakeThread:
    def __init__(self, target=None, daemon=None, **kw):
        self.target = target
        self.daemon = daemon

    def start(self):
        pass


def test_run_job_hunter_async_success(client, monkeypatch):
    """The full runner executes main() then resets the flag to idle (no real scraping)."""
    import webapp.state as state
    monkeypatch.setattr(state.threading, "Thread", FakeThread)
    calls = {"main": 0}

    def fake_main():
        calls["main"] += 1

    import types
    monkeypatch.setattr(state, "job_hunter_main", types.SimpleNamespace(main=fake_main))
    state.is_running_flag = False
    state.run_job_hunter_async()
    assert calls["main"] == 1
    assert state.is_running_flag is False
    assert state.current_status == "idle"


def test_run_job_hunter_async_noop_when_running(client):
    import webapp.state as state
    state.update_status("scraping", True)
    calls = {"main": 0}
    state.job_hunter_main.main = lambda: calls.__setitem__("main", calls["main"] + 1)
    state.run_job_hunter_async()
    assert calls["main"] == 0


def test_run_job_hunter_async_error_sets_error_status(client, monkeypatch):
    import webapp.state as state
    monkeypatch.setattr(state.threading, "Thread", FakeThread)

    def boom():
        raise RuntimeError("scraper exploded")

    import types
    monkeypatch.setattr(state, "job_hunter_main", types.SimpleNamespace(main=boom))
    state.is_running_flag = False
    state.run_job_hunter_async()
    assert state.is_running_flag is False
    assert state.current_status.startswith("Error")


def test_browser_thread_body_success(client, monkeypatch):
    """Exercise the browser background thread body through the /start route."""
    import webapp.routes.browser as br
    executed = {"n": 0}

    class TrackingThread(FakeThread):
        def start(self):
            self.target()
            executed["n"] += 1

    monkeypatch.setattr(br.threading, "Thread", TrackingThread)
    monkeypatch.setattr("webapp.state.browser_running", False)
    monkeypatch.setattr("webapp.routes.browser.config.SEARCH_KEYWORDS", ["k"])
    monkeypatch.setattr("webapp.routes.browser.config.LOCATIONS", ["Penang, Malaysia"])

    # The browser route imports run_search_sync from browser_agent at call time.
    import types
    fake_agent = types.ModuleType("browser_agent")
    fake_agent.run_search_sync = lambda *a, **k: []
    fake_agent.request_stop = lambda: None
    monkeypatch.setitem(__import__("sys").modules, "browser_agent", fake_agent)

    res = client.post("/api/browser/start", headers={"X-Auth-Token": "test-token"}, json={})
    assert res.status_code == 200
    assert executed["n"] == 1


def test_browser_thread_body_error(client, monkeypatch):
    import webapp.routes.browser as br
    executed = {"n": 0}

    class TrackingThread(FakeThread):
        def start(self):
            self.target()
            executed["n"] += 1

    monkeypatch.setattr(br.threading, "Thread", TrackingThread)
    monkeypatch.setattr("webapp.state.browser_running", False)
    monkeypatch.setattr("webapp.routes.browser.config.SEARCH_KEYWORDS", ["k"])
    monkeypatch.setattr("webapp.routes.browser.config.LOCATIONS", ["L"])

    import types
    fake_agent = types.ModuleType("browser_agent")
    fake_agent.run_search_sync = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("browser died"))
    fake_agent.request_stop = lambda: None
    monkeypatch.setitem(__import__("sys").modules, "browser_agent", fake_agent)

    res = client.post("/api/browser/start", headers={"X-Auth-Token": "test-token"}, json={})
    assert res.status_code == 200
    assert executed["n"] == 1


def test_state_scheduler_loop_due_keeps_next_run(client, monkeypatch):
    import time as _time

    import webapp.state as state
    monkeypatch.setattr(state.threading, "Thread", FakeThread)
    monkeypatch.setattr(webapp.state, "is_running_flag", False)
    calls = {"sleep": 0}

    def fake_sleep(_s):
        calls["sleep"] += 1
        if calls["sleep"] >= 1:
            raise SystemExit

    monkeypatch.setattr(_time, "sleep", fake_sleep)
    state.save_scheduler_state({"enabled": True, "interval_hours": 6, "next_run_at": None})
    with contextlib.suppress(SystemExit):
        state.scheduler_loop()
    # After a due run, next_run_at should be scheduled into the future.
    after = state.load_scheduler_state()
    assert after["next_run_at"] is not None
    assert after["next_run_at"] > 0


def test_state_jobspy_error_writes_error_log(client, monkeypatch):
    import webapp.state as state
    monkeypatch.setattr(state.threading, "Thread", FakeThread)

    def boom():
        raise RuntimeError("boom")

    import types
    monkeypatch.setattr(state, "job_hunter_main", types.SimpleNamespace(main=boom))
    state.update_status("idle", False)
    state.run_job_hunter_async()
    import os
    assert os.path.exists(state._error_log())


def test_crossprocess_lock_held_returns_false(client, monkeypatch, tmp_path):
    """A second acquirer must be refused while another holder owns the lock."""
    import os

    import webapp.state as state
    lock_path = str(tmp_path / "x.lock")
    monkeypatch.setattr(state, "_run_lock_path", lambda: lock_path)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    os.write(fd, b"0")
    os.lseek(fd, 0, os.SEEK_SET)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert state._acquire_crossprocess_run_lock() is False
        assert state._lock_fd is None
    finally:
        with contextlib.suppress(Exception):
            if os.name == "nt":
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_release_crossprocess_lock_without_hold(client):
    """Releasing when this process never acquired the lock is a no-op."""
    import webapp.state as state
    state._lock_fd = None
    state._release_crossprocess_run_lock()


def test_update_status_with_progress(client, monkeypatch, tmp_path):
    import webapp.state as state
    status_path = str(tmp_path / "s.json")
    monkeypatch.setattr(state, "_status_file", lambda: status_path)
    state.update_status("scraping", True, progress={"done": 2})
    payload = state.get_run_status()
    assert payload["status"] == "scraping"
    assert payload["is_running"] is True
    assert payload["progress"] == {"done": 2}