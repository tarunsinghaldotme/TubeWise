"""
test_models.py — Unit tests for models.py
"""

from __future__ import annotations

import pytest

from models import ContentInfo, ContentSource


class TestContentInfo:
    """Test ContentInfo dataclass and its properties."""

    def _make_content(self, **overrides) -> ContentInfo:
        defaults = {
            "content_id": "abc123def45",
            "url": "https://youtube.com/watch?v=abc123def45",
            "title": "Test Video",
            "creator": "Test Channel",
            "transcript": "This is a test transcript with several words.",
            "duration_seconds": 3661,
            "language": "en",
            "source": ContentSource.YOUTUBE,
        }
        defaults.update(overrides)
        return ContentInfo(**defaults)

    def test_duration_formatted_hours(self):
        c = self._make_content(duration_seconds=3661)
        assert c.duration_formatted == "1h 1m 1s"

    def test_duration_formatted_minutes(self):
        c = self._make_content(duration_seconds=125)
        assert c.duration_formatted == "2m 5s"

    def test_duration_formatted_zero(self):
        c = self._make_content(duration_seconds=0)
        assert c.duration_formatted == "0m 0s"

    def test_word_count(self):
        c = self._make_content(transcript="one two three four five")
        assert c.word_count == 5

    def test_word_count_empty(self):
        c = self._make_content(transcript="")
        # "".split() returns [], so word_count is 0... but len([""])=1 when splitting empty
        # Actually "".split() returns [] so len is 0
        assert c.word_count == 0

    def test_backward_compat_video_id(self):
        c = self._make_content(content_id="myVideoId123")
        assert c.video_id == "myVideoId123"

    def test_backward_compat_channel(self):
        c = self._make_content(creator="My Channel")
        assert c.channel == "My Channel"

    def test_source_youtube(self):
        c = self._make_content(source=ContentSource.YOUTUBE)
        assert c.source == ContentSource.YOUTUBE
        assert c.source.value == "youtube"

    def test_optional_fields_default_none(self):
        c = self._make_content()
        assert c.playlist_id is None
        assert c.playlist_title is None
        assert c.episode_number is None

    def test_optional_fields_set(self):
        c = self._make_content(
            playlist_id="PLabc123",
            playlist_title="My Playlist",
            episode_number=5,
        )
        assert c.playlist_id == "PLabc123"
        assert c.playlist_title == "My Playlist"
        assert c.episode_number == 5
