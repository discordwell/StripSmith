"""Tests for the in-memory JobManager (sessions + jobs).

The cleanup deadlock test is a regression guard: cleanup_old_jobs() used to call
self.delete_session() while already holding self._lock. threading.Lock is not
reentrant, so an expired session would deadlock the cleanup task forever — and
with it every other job/session operation.
"""

from datetime import datetime, timedelta, timezone
import threading

import pytest

from backend.jobs import JobManager, JobStatus


def _utcnow():
    return datetime.now(timezone.utc)


def _expire_session(jm: JobManager, session_id: str):
    """Force a session's expiry into the past (test helper)."""
    jm._sessions[session_id]["expires_at"] = _utcnow() - timedelta(hours=3)


def test_create_and_get_session():
    jm = JobManager()
    jm.create_session("s1", openai_key="sk-o", anthropic_key="sk-ant")
    s = jm.get_session("s1")
    assert s is not None
    assert s["openai_key"] == "sk-o"
    assert s["anthropic_key"] == "sk-ant"


def test_expired_session_not_returned():
    jm = JobManager()
    jm.create_session("s1")
    _expire_session(jm, "s1")
    assert jm.get_session("s1") is None  # also evicts it


def test_delete_session_clears_keys():
    jm = JobManager()
    jm.create_session("s1", openai_key="sk-o", anthropic_key="sk-ant")
    jm.delete_session("s1")
    assert jm.get_session("s1") is None


def test_job_lifecycle():
    jm = JobManager()
    jm.create_session("s1")
    jm.create_job("j1", "s1", "story text", "story.txt")
    job = jm.get_job("j1")
    assert job["status"] == JobStatus.PENDING
    assert job["progress"] == 0

    jm.update_job_status("j1", JobStatus.PROCESSING, progress=50, stage="halfway")
    job = jm.get_job("j1")
    assert job["status"] == JobStatus.PROCESSING
    assert job["progress"] == 50
    assert job["stage"] == "halfway"

    jm.update_job_status("j1", JobStatus.COMPLETED, progress=100, result={"output_path": "/tmp/x"})
    job = jm.get_job("j1")
    assert job["status"] == JobStatus.COMPLETED
    assert job["result"]["output_path"] == "/tmp/x"


def test_update_unknown_job_is_noop():
    jm = JobManager()
    # Should not raise
    jm.update_job_status("nope", JobStatus.FAILED, error="x")
    assert jm.get_job("nope") is None


def test_get_all_sessions_redacts_keys():
    jm = JobManager()
    jm.create_session("s1", openai_key="sk-o", anthropic_key="sk-ant")
    all_sessions = jm.get_all_sessions()
    assert all_sessions["s1"]["openai_key"] == "***"
    assert all_sessions["s1"]["anthropic_key"] == "***"


def test_cleanup_removes_old_jobs():
    jm = JobManager()
    jm.create_job("old", "s1", "t", "f.txt")
    jm._jobs["old"]["created_at"] = _utcnow() - timedelta(hours=5)
    jm.create_job("fresh", "s1", "t", "f.txt")
    jm.cleanup_old_jobs(max_age_hours=2)
    assert jm.get_job("old") is None
    assert jm.get_job("fresh") is not None


def test_cleanup_with_expired_session_does_not_deadlock():
    """Regression: an expired session must not deadlock cleanup_old_jobs().

    Run cleanup in a worker thread and require it to finish quickly. Before the
    fix, the re-entrant lock acquisition hangs and the thread stays alive.
    """
    jm = JobManager()
    jm.create_session("s1", openai_key="sk-o", anthropic_key="sk-ant")
    _expire_session(jm, "s1")

    done = threading.Event()

    def run():
        jm.cleanup_old_jobs(max_age_hours=2)
        done.set()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    finished = done.wait(timeout=5.0)

    assert finished, "cleanup_old_jobs deadlocked on an expired session"
    # And the expired session was actually removed.
    assert "s1" not in jm._sessions


def test_cleanup_then_lock_still_usable():
    """After cleanup runs, the manager's lock must not be left held.

    cleanup runs in a worker thread with a timeout so that a *reintroduced*
    deadlock fails this test cleanly instead of hanging the whole pytest run
    (this test would otherwise call cleanup on the main thread).
    """
    jm = JobManager()
    jm.create_session("s1")
    _expire_session(jm, "s1")

    done = threading.Event()

    def run():
        jm.cleanup_old_jobs(max_age_hours=2)
        done.set()

    threading.Thread(target=run, daemon=True).start()
    assert done.wait(timeout=5.0), "cleanup_old_jobs deadlocked"

    # If the lock were left held, this non-blocking acquire would fail.
    acquired = jm._lock.acquire(blocking=False)
    assert acquired, "JobManager lock left held after cleanup"
    jm._lock.release()
