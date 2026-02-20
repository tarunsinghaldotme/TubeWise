"""
test_playlist.py — Unit tests for playlist.py pure functions
"""

from __future__ import annotations

import pytest

from playlist import is_playlist_url, extract_playlist_id


class TestIsPlaylistUrl:
    """Test playlist URL detection."""

    def test_playlist_url(self):
        url = "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
        assert is_playlist_url(url) is True

    def test_video_with_playlist(self):
        url = "https://www.youtube.com/watch?v=abc123&list=PLrAXtmErZgOe"
        assert is_playlist_url(url) is True

    def test_regular_video_url(self):
        url = "https://www.youtube.com/watch?v=abc123"
        assert is_playlist_url(url) is False

    def test_short_url(self):
        url = "https://youtu.be/abc123"
        assert is_playlist_url(url) is False

    def test_empty_string(self):
        assert is_playlist_url("") is False


class TestExtractPlaylistId:
    """Test playlist ID extraction."""

    def test_standard_playlist_url(self):
        url = "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
        assert extract_playlist_id(url) == "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"

    def test_video_with_playlist(self):
        url = "https://www.youtube.com/watch?v=abc123&list=PLxyz789abc"
        assert extract_playlist_id(url) == "PLxyz789abc"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Could not extract playlist ID"):
            extract_playlist_id("https://www.youtube.com/watch?v=abc123")

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="Could not extract playlist ID"):
            extract_playlist_id("")
