"""
test_agent.py — Unit tests for agent.py pure functions
"""

from __future__ import annotations

import os
import pytest

from agent import save_local_output


class TestSaveLocalOutput:
    """Test local file saving functionality."""

    def test_saves_markdown_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        summary = "# Test Summary\nThis is a test."
        filename = save_local_output(summary, "My Test Video")
        assert os.path.exists(tmp_path / filename)

    def test_filename_format(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        filename = save_local_output("content", "My Video Title")
        assert filename.startswith("summary_")
        assert filename.endswith(".md")

    def test_file_content_includes_title(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        filename = save_local_output("Summary body", "Video Title")
        content = (tmp_path / filename).read_text()
        assert "# Video Title" in content
        assert "Summary body" in content

    def test_special_chars_removed_from_filename(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        filename = save_local_output("content", "Video: The (Best) One! @2024")
        # Only alphanumeric, spaces, hyphens, underscores should remain
        assert ":" not in filename
        assert "(" not in filename
        assert "!" not in filename
        assert "@" not in filename

    def test_long_title_truncated(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        long_title = "A" * 200
        filename = save_local_output("content", long_title)
        # Filename should be reasonable length (summary_ prefix + truncated title + .md)
        assert len(filename) < 200


class TestSaveLocalOutputEdgeCases:
    """Edge case tests for save_local_output."""

    def test_empty_summary(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        filename = save_local_output("", "Empty Video")
        content = (tmp_path / filename).read_text()
        assert "# Empty Video" in content

    def test_empty_title(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        filename = save_local_output("content", "")
        assert os.path.exists(tmp_path / filename)
