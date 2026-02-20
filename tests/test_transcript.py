"""
test_transcript.py — Unit tests for transcript.py pure functions
"""

from __future__ import annotations

import pytest

from transcript import extract_video_id, _process_transcript_entries


# ══════════════════════════════════════════════════════════════
# extract_video_id()
# ══════════════════════════════════════════════════════════════

class TestExtractVideoId:
    """Test YouTube URL parsing for all supported formats."""

    def test_standard_url(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_short_url(self):
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_embed_url(self):
        url = "https://www.youtube.com/embed/dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_old_v_format(self):
        url = "https://www.youtube.com/v/dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_url_with_playlist_params(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_url_with_timestamp(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_bare_video_id(self):
        assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_id_with_hyphen_and_underscore(self):
        # YouTube video IDs are exactly 11 characters
        assert extract_video_id("abc-def_gh1") == "abc-def_gh1"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Could not extract video ID"):
            extract_video_id("https://www.google.com")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="Could not extract video ID"):
            extract_video_id("")

    def test_too_short_id_raises(self):
        with pytest.raises(ValueError, match="Could not extract video ID"):
            extract_video_id("abc123")


# ══════════════════════════════════════════════════════════════
# _process_transcript_entries()
# ══════════════════════════════════════════════════════════════

class TestProcessTranscriptEntries:
    """Test transcript entry processing for both dict and object formats."""

    def test_dict_format(self, sample_transcript_entries):
        text, duration = _process_transcript_entries(sample_transcript_entries)
        assert "Welcome to today's video." in text
        assert "Thank you for watching!" in text
        # Duration = last entry start (590) + last entry duration (2.0) = 592
        assert duration == 592

    def test_empty_entries(self):
        text, duration = _process_transcript_entries([])
        assert text == ""
        assert duration == 0

    def test_single_entry(self):
        entries = [{"text": "Hello world", "start": 0.0, "duration": 5.0}]
        text, duration = _process_transcript_entries(entries)
        assert text == "Hello world"
        assert duration == 5

    def test_entries_with_empty_text(self):
        entries = [
            {"text": "First", "start": 0.0, "duration": 2.0},
            {"text": "", "start": 2.0, "duration": 1.0},
            {"text": "Third", "start": 3.0, "duration": 2.0},
        ]
        text, duration = _process_transcript_entries(entries)
        assert text == "First Third"

    def test_duration_calculation(self):
        entries = [
            {"text": "Start", "start": 0.0, "duration": 10.0},
            {"text": "Middle", "start": 100.0, "duration": 5.0},
            {"text": "End", "start": 3600.0, "duration": 3.0},
        ]
        text, duration = _process_transcript_entries(entries)
        assert duration == 3603  # 3600 + 3

    def test_object_format(self):
        """Test with objects that have attributes instead of dict keys."""
        class Entry:
            def __init__(self, text, start, duration):
                self.text = text
                self.start = start
                self.duration = duration

        entries = [
            Entry("Hello", 0.0, 2.0),
            Entry("World", 2.0, 3.0),
        ]
        text, duration = _process_transcript_entries(entries)
        assert text == "Hello World"
        assert duration == 5
