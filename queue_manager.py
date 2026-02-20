"""
queue_manager.py — TubeWise Async Job Queue (SQLite)
======================================================
Manages a persistent job queue backed by SQLite for async processing
of YouTube content.

ARCHITECTURE:
  tubewise "URL" --async  → enqueue() → queue.db
  tubewise --status       → get_status() → formatted table
  tubewise --worker start → worker.py polls queue.db → processes jobs

JOB STATE MACHINE:
  pending ──(worker claims)──> processing ──(success)──> completed
                                    │
                                (failure)
                                    │
                                    ▼
                                  failed

DATABASE LOCATION:
  ~/.tubewise/queue.db (configurable via QUEUE_DB_PATH in .env)

CONCURRENCY:
  SQLite WAL mode enables concurrent reads. Job claiming uses
  atomic UPDATE...RETURNING to prevent duplicate processing.
"""

from __future__ import annotations

import os
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

from config import Config

logger = logging.getLogger("tubewise.queue")

# ANSI color codes for terminal output
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RED = "\033[91m"
_GRAY = "\033[90m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


class QueueManager:
    """
    Manages the SQLite-backed job queue for async processing.

    Usage:
        qm = QueueManager()
        job_id = qm.enqueue("https://youtube.com/...", "en", False)
        print(qm.format_status_table())
    """

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or Config.QUEUE_DB_PATH
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Create a new connection with WAL mode and row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _ensure_db(self) -> None:
        """Create database tables if they don't exist."""
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'youtube',
                    status TEXT NOT NULL DEFAULT 'pending',
                    language TEXT DEFAULT 'en',
                    no_notion INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    started_at TEXT,
                    completed_at TEXT,
                    error_message TEXT,
                    notion_page_url TEXT,
                    local_file_path TEXT,
                    worker_pid INTEGER
                );

                CREATE TABLE IF NOT EXISTS worker_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    pid INTEGER,
                    started_at TEXT,
                    status TEXT DEFAULT 'stopped',
                    worker_count INTEGER DEFAULT 2
                );

                INSERT OR IGNORE INTO worker_state (id, status) VALUES (1, 'stopped');
            """)
            conn.commit()
        finally:
            conn.close()

    def enqueue(self, url: str, language: str = "en", no_notion: bool = False) -> int:
        """
        Add a job to the queue.

        Args:
            url:       Content URL (YouTube video or playlist)
            language:  Transcript language code
            no_notion: If True, skip Notion publishing

        Returns:
            The job ID
        """
        source = "youtube"
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "INSERT INTO jobs (url, source, language, no_notion) VALUES (?, ?, ?, ?)",
                (url, source, language, int(no_notion)),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_status(self, limit: int = 20) -> list[dict]:
        """
        Get status of recent jobs.

        Args:
            limit: Maximum number of jobs to return

        Returns:
            List of job dicts, most recent first
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_next_pending(self) -> dict | None:
        """
        Atomically claim the next pending job for processing.

        Uses UPDATE with a subquery to prevent race conditions when
        multiple workers try to claim jobs simultaneously.

        Returns:
            Job dict if a pending job was claimed, None otherwise
        """
        conn = self._get_conn()
        try:
            # Atomically update the first pending job
            conn.execute(
                """UPDATE jobs
                   SET status = 'processing',
                       started_at = datetime('now'),
                       worker_pid = ?
                   WHERE id = (
                       SELECT id FROM jobs
                       WHERE status = 'pending'
                       ORDER BY id ASC
                       LIMIT 1
                   )""",
                (os.getpid(),),
            )
            conn.commit()

            # Fetch the job we just claimed
            row = conn.execute(
                "SELECT * FROM jobs WHERE status = 'processing' AND worker_pid = ? ORDER BY id DESC LIMIT 1",
                (os.getpid(),),
            ).fetchone()

            return dict(row) if row else None
        finally:
            conn.close()

    def mark_completed(self, job_id: int, notion_url: str = "", local_file: str = "") -> None:
        """Mark a job as successfully completed."""
        conn = self._get_conn()
        try:
            conn.execute(
                """UPDATE jobs
                   SET status = 'completed',
                       completed_at = datetime('now'),
                       notion_page_url = ?,
                       local_file_path = ?
                   WHERE id = ?""",
                (notion_url, local_file, job_id),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_failed(self, job_id: int, error: str) -> None:
        """Mark a job as failed with an error message."""
        conn = self._get_conn()
        try:
            conn.execute(
                """UPDATE jobs
                   SET status = 'failed',
                       completed_at = datetime('now'),
                       error_message = ?
                   WHERE id = ?""",
                (error[:500], job_id),  # Truncate long errors
            )
            conn.commit()
        finally:
            conn.close()

    def reset_stale_jobs(self) -> int:
        """
        Reset jobs stuck in 'processing' state (from crashed workers).
        Called on worker startup.

        Returns:
            Number of jobs reset
        """
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "UPDATE jobs SET status = 'pending', worker_pid = NULL, started_at = NULL "
                "WHERE status = 'processing'"
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def get_worker_state(self) -> dict | None:
        """Get current worker daemon state."""
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM worker_state WHERE id = 1").fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def set_worker_state(self, pid: int, status: str, worker_count: int) -> None:
        """Update worker daemon state."""
        conn = self._get_conn()
        try:
            conn.execute(
                """UPDATE worker_state
                   SET pid = ?, started_at = datetime('now'), status = ?, worker_count = ?
                   WHERE id = 1""",
                (pid, status, worker_count),
            )
            conn.commit()
        finally:
            conn.close()

    def format_status_table(self) -> str:
        """
        Generate a beautiful CLI status table with colors and box-drawing chars.

        Returns:
            Formatted string ready to print to terminal
        """
        jobs = self.get_status(limit=20)
        worker = self.get_worker_state()

        lines = []

        # ── Header ──
        lines.append(f"╔{'═' * 72}╗")
        lines.append(f"║{'🧠 TubeWise Queue Status':^72}║")
        lines.append(f"╠{'═' * 72}╣")

        # ── Worker status ──
        if worker and worker["status"] == "running":
            # Check if worker PID is actually alive
            pid_alive = _is_pid_alive(worker["pid"]) if worker["pid"] else False
            if pid_alive:
                w_str = f"  {_GREEN}●{_RESET} Worker: Running (PID: {worker['pid']}, {worker['worker_count']} workers)"
            else:
                w_str = f"  {_YELLOW}●{_RESET} Worker: Stale (PID {worker['pid']} not found)"
        else:
            w_str = f"  {_GRAY}○{_RESET} Worker: Not running"
        lines.append(f"║ {w_str:<79}║")

        # ── Table header ──
        lines.append(f"╠{'═' * 4}╦{'═' * 38}╦{'═' * 12}╦{'═' * 14}╣")
        lines.append(f"║{'ID':^4}║{'URL':^38}║{'Status':^12}║{'Info':^14}║")
        lines.append(f"╠{'═' * 4}╬{'═' * 38}╬{'═' * 12}╬{'═' * 14}╣")

        if not jobs:
            lines.append(f"║{'No jobs in queue':^72}║")
        else:
            for job in jobs:
                job_id = str(job["id"])
                url = _truncate(job["url"], 36)
                status = job["status"]
                info = ""

                if status == "completed":
                    status_str = f"{_GREEN}✅ Done{_RESET}"
                    if job.get("started_at") and job.get("completed_at"):
                        info = _calc_duration(job["started_at"], job["completed_at"])
                elif status == "processing":
                    status_str = f"{_YELLOW}⚙️  Running{_RESET}"
                    if job.get("started_at"):
                        info = _time_ago(job["started_at"]) + "..."
                elif status == "failed":
                    status_str = f"{_RED}❌ Failed{_RESET}"
                    info = _truncate(job.get("error_message", ""), 12)
                else:  # pending
                    status_str = f"{_GRAY}⏳ Queued{_RESET}"
                    info = "—"

                lines.append(
                    f"║{job_id:>4}║ {url:<37}║ {status_str:<21}║ {info:<13}║"
                )

        # ── Footer with summary ──
        lines.append(f"╠{'═' * 4}╩{'═' * 38}╩{'═' * 12}╩{'═' * 14}╣")

        if jobs:
            counts = {}
            for job in jobs:
                s = job["status"]
                counts[s] = counts.get(s, 0) + 1

            parts = []
            if counts.get("completed"):
                parts.append(f"{_GREEN}{counts['completed']} done{_RESET}")
            if counts.get("processing"):
                parts.append(f"{_YELLOW}{counts['processing']} running{_RESET}")
            if counts.get("pending"):
                parts.append(f"{_GRAY}{counts['pending']} queued{_RESET}")
            if counts.get("failed"):
                parts.append(f"{_RED}{counts['failed']} failed{_RESET}")

            summary = "  " + " · ".join(parts)
            lines.append(f"║ {summary:<79}║")
        else:
            lines.append(f"║{'Queue is empty':^72}║")

        lines.append(f"╚{'═' * 72}╝")

        # Add Notion URLs for completed jobs
        completed_with_urls = [
            j for j in jobs if j["status"] == "completed" and j.get("notion_page_url")
        ]
        if completed_with_urls:
            lines.append("")
            lines.append(f"{_BOLD}Notion Pages:{_RESET}")
            for j in completed_with_urls[:5]:
                lines.append(f"  #{j['id']}: {j['notion_page_url']}")

        return "\n".join(lines)


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis if too long."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _is_pid_alive(pid: int) -> bool:
    """Check if a process is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _calc_duration(start: str, end: str) -> str:
    """Calculate human-readable duration between two ISO datetime strings."""
    try:
        s = datetime.fromisoformat(start)
        e = datetime.fromisoformat(end)
        delta = (e - s).total_seconds()
        if delta < 60:
            return f"{int(delta)}s"
        elif delta < 3600:
            return f"{int(delta // 60)}m {int(delta % 60)}s"
        else:
            return f"{int(delta // 3600)}h {int((delta % 3600) // 60)}m"
    except Exception:
        return "—"


def _time_ago(start: str) -> str:
    """Calculate elapsed time since a datetime string."""
    try:
        s = datetime.fromisoformat(start)
        delta = (datetime.now() - s).total_seconds()
        if delta < 60:
            return f"{int(delta)}s"
        elif delta < 3600:
            return f"{int(delta // 60)}m {int(delta % 60)}s"
        else:
            return f"{int(delta // 3600)}h {int((delta % 3600) // 60)}m"
    except Exception:
        return "—"
