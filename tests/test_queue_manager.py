"""
test_queue_manager.py — Unit tests for queue_manager.py
"""

from __future__ import annotations

import os
import pytest

from queue_manager import QueueManager, _truncate, _calc_duration


class TestQueueManager:
    """Test QueueManager with a temporary database."""

    @pytest.fixture
    def qm(self, tmp_path):
        """Create a QueueManager with a temp database."""
        db_path = str(tmp_path / "test_queue.db")
        return QueueManager(db_path=db_path)

    def test_enqueue_returns_job_id(self, qm):
        job_id = qm.enqueue("https://youtube.com/watch?v=abc123")
        assert isinstance(job_id, int)
        assert job_id >= 1

    def test_enqueue_increments_id(self, qm):
        id1 = qm.enqueue("https://youtube.com/watch?v=abc123")
        id2 = qm.enqueue("https://youtube.com/watch?v=def456")
        assert id2 == id1 + 1

    def test_enqueue_detects_youtube(self, qm):
        qm.enqueue("https://youtube.com/watch?v=abc123")
        jobs = qm.get_status(limit=1)
        assert jobs[0]["source"] == "youtube"

    def test_get_status_returns_recent_first(self, qm):
        qm.enqueue("https://youtube.com/watch?v=first")
        qm.enqueue("https://youtube.com/watch?v=second")
        jobs = qm.get_status()
        assert "second" in jobs[0]["url"]
        assert "first" in jobs[1]["url"]

    def test_get_status_limit(self, qm):
        for i in range(5):
            qm.enqueue(f"https://youtube.com/watch?v=video{i}")
        jobs = qm.get_status(limit=3)
        assert len(jobs) == 3

    def test_get_next_pending(self, qm):
        qm.enqueue("https://youtube.com/watch?v=abc123")
        job = qm.get_next_pending()
        assert job is not None
        assert job["status"] == "processing"
        assert job["url"] == "https://youtube.com/watch?v=abc123"

    def test_get_next_pending_returns_none_when_empty(self, qm):
        assert qm.get_next_pending() is None

    def test_mark_completed(self, qm):
        job_id = qm.enqueue("https://youtube.com/watch?v=abc123")
        qm.get_next_pending()  # Claim it
        qm.mark_completed(job_id, notion_url="https://notion.so/page", local_file="summary.md")
        jobs = qm.get_status()
        assert jobs[0]["status"] == "completed"
        assert jobs[0]["notion_page_url"] == "https://notion.so/page"

    def test_mark_failed(self, qm):
        job_id = qm.enqueue("https://youtube.com/watch?v=abc123")
        qm.get_next_pending()
        qm.mark_failed(job_id, "No transcript available")
        jobs = qm.get_status()
        assert jobs[0]["status"] == "failed"
        assert "No transcript" in jobs[0]["error_message"]

    def test_mark_failed_truncates_long_error(self, qm):
        job_id = qm.enqueue("https://youtube.com/watch?v=abc123")
        qm.get_next_pending()
        long_error = "x" * 1000
        qm.mark_failed(job_id, long_error)
        jobs = qm.get_status()
        assert len(jobs[0]["error_message"]) == 500

    def test_reset_stale_jobs(self, qm):
        qm.enqueue("https://youtube.com/watch?v=abc123")
        qm.get_next_pending()  # Set to processing
        reset_count = qm.reset_stale_jobs()
        assert reset_count == 1
        jobs = qm.get_status()
        assert jobs[0]["status"] == "pending"

    def test_worker_state_lifecycle(self, qm):
        state = qm.get_worker_state()
        assert state["status"] == "stopped"

        qm.set_worker_state(12345, "running", 2)
        state = qm.get_worker_state()
        assert state["status"] == "running"
        assert state["pid"] == 12345
        assert state["worker_count"] == 2

    def test_format_status_table_empty(self, qm):
        table = qm.format_status_table()
        assert "TubeWise Queue Status" in table
        assert "No jobs" in table or "empty" in table.lower()

    def test_format_status_table_with_jobs(self, qm):
        qm.enqueue("https://youtube.com/watch?v=abc123")
        table = qm.format_status_table()
        assert "abc123" in table
        assert "Queued" in table


class TestTruncate:
    """Test the _truncate helper function."""

    def test_short_text_unchanged(self):
        assert _truncate("hello", 10) == "hello"

    def test_long_text_truncated(self):
        result = _truncate("hello world", 8)
        assert len(result) == 8
        assert result.endswith("…")

    def test_empty_text(self):
        assert _truncate("", 10) == ""

    def test_none_text(self):
        assert _truncate(None, 10) == ""

    def test_exact_limit(self):
        assert _truncate("hello", 5) == "hello"


class TestCalcDuration:
    """Test the _calc_duration helper function."""

    def test_seconds(self):
        assert _calc_duration("2024-01-01 00:00:00", "2024-01-01 00:00:45") == "45s"

    def test_minutes(self):
        assert _calc_duration("2024-01-01 00:00:00", "2024-01-01 00:02:30") == "2m 30s"

    def test_hours(self):
        assert _calc_duration("2024-01-01 00:00:00", "2024-01-01 01:30:00") == "1h 30m"

    def test_invalid_dates(self):
        assert _calc_duration("invalid", "also invalid") == "—"
