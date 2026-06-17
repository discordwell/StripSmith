"""Job and session management for StripSmith."""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, Any, Optional
import threading


def _utcnow() -> datetime:
    """Timezone-aware UTC now.

    Replaces datetime.utcnow(), which returns a naive datetime and is
    deprecated (slated for removal) as of Python 3.12.
    """
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    """Job status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobManager:
    """
    Manages jobs and sessions in memory.

    Sessions store API keys (never persisted to disk).
    Jobs track comic generation progress.
    """

    def __init__(self):
        """Initialize job manager."""
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    # Session management
    def create_session(
        self,
        session_id: str,
        openai_key: Optional[str] = None,
        anthropic_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new session.

        Args:
            session_id: Unique session identifier
            openai_key: OpenAI API key (optional)
            anthropic_key: Anthropic API key (optional)

        Returns:
            Session data
        """
        with self._lock:
            session = {
                "session_id": session_id,
                "created_at": _utcnow(),
                "expires_at": _utcnow() + timedelta(hours=2),
                "openai_key": openai_key,
                "anthropic_key": anthropic_key,
            }
            self._sessions[session_id] = session
            return session

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session by ID.

        Args:
            session_id: Session identifier

        Returns:
            Session data or None if not found/expired
        """
        with self._lock:
            session = self._sessions.get(session_id)

            if not session:
                return None

            # Check expiration
            if _utcnow() > session["expires_at"]:
                del self._sessions[session_id]
                return None

            return session

    def delete_session(self, session_id: str):
        """
        Delete a session and its API keys.

        Args:
            session_id: Session identifier
        """
        with self._lock:
            if session_id in self._sessions:
                # Clear keys before deletion
                self._sessions[session_id]["openai_key"] = None
                self._sessions[session_id]["anthropic_key"] = None
                del self._sessions[session_id]

    # Job management
    def create_job(
        self,
        job_id: str,
        session_id: str,
        story_text: str,
        story_filename: str,
        style: Optional[str] = None,
        chapters: str = "all",
        output_format: str = "pdf"
    ) -> Dict[str, Any]:
        """
        Create a new job.

        Args:
            job_id: Unique job identifier
            session_id: Session ID (for API keys)
            story_text: Story content
            story_filename: Original filename
            style: Art style
            chapters: Chapters to process
            output_format: Output format

        Returns:
            Job data
        """
        with self._lock:
            job = {
                "job_id": job_id,
                "session_id": session_id,
                "story_text": story_text,
                "story_filename": story_filename,
                "style": style,
                "chapters": chapters,
                "output_format": output_format,
                "status": JobStatus.PENDING,
                "progress": 0,
                "stage": "Initializing...",
                "created_at": _utcnow(),
                "updated_at": _utcnow(),
                "result": None,
                "error": None,
            }
            self._jobs[job_id] = job
            return job

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job by ID.

        Args:
            job_id: Job identifier

        Returns:
            Job data or None if not found
        """
        with self._lock:
            return self._jobs.get(job_id)

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: Optional[int] = None,
        stage: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        """
        Update job status.

        Args:
            job_id: Job identifier
            status: New status
            progress: Progress percentage (0-100)
            stage: Current stage description
            result: Result data (for completed jobs)
            error: Error message (for failed jobs)
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return

            job["status"] = status
            job["updated_at"] = _utcnow()

            if progress is not None:
                job["progress"] = progress

            if stage is not None:
                job["stage"] = stage

            if result is not None:
                job["result"] = result

            if error is not None:
                job["error"] = error

    def delete_job(self, job_id: str):
        """
        Delete a job.

        Args:
            job_id: Job identifier
        """
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]

    def cleanup_old_jobs(self, max_age_hours: int = 2):
        """
        Remove jobs older than specified hours.

        Args:
            max_age_hours: Maximum age in hours
        """
        with self._lock:
            cutoff = _utcnow() - timedelta(hours=max_age_hours)
            jobs_to_delete = [
                job_id
                for job_id, job in self._jobs.items()
                if job["created_at"] < cutoff
            ]

            for job_id in jobs_to_delete:
                del self._jobs[job_id]

            # Also cleanup expired sessions. Delete inline rather than calling
            # self.delete_session(), which would re-acquire self._lock — a
            # threading.Lock is NOT reentrant, so that re-entry would deadlock
            # the cleanup task (and every other job/session operation with it).
            now = _utcnow()
            sessions_to_delete = [
                session_id
                for session_id, session in self._sessions.items()
                if session["expires_at"] < now
            ]

            for session_id in sessions_to_delete:
                # Clear keys before dropping the session (mirrors delete_session).
                self._sessions[session_id]["openai_key"] = None
                self._sessions[session_id]["anthropic_key"] = None
                del self._sessions[session_id]

    def get_all_jobs(self) -> Dict[str, Dict[str, Any]]:
        """Get all jobs (for debugging)."""
        with self._lock:
            return dict(self._jobs)

    def get_all_sessions(self) -> Dict[str, Dict[str, Any]]:
        """Get all sessions (for debugging, keys redacted)."""
        with self._lock:
            # Redact API keys for safety
            return {
                sid: {
                    **session,
                    "openai_key": "***" if session.get("openai_key") else None,
                    "anthropic_key": "***" if session.get("anthropic_key") else None,
                }
                for sid, session in self._sessions.items()
            }
