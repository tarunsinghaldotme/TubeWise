"""
models.py — TubeWise Shared Data Models
=========================================
Contains the canonical data models used across all modules.

ContentInfo is the universal container for content from any source
(YouTube, local files, etc.). It replaces the old VideoInfo dataclass
while maintaining backward compatibility via property aliases.

ContentSource enum identifies where the content came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ContentSource(Enum):
    """Identifies the source platform of the content."""
    YOUTUBE = "youtube"
    SPOTIFY = "spotify"
    LOCAL_FILE = "local_file"


@dataclass
class ContentInfo:
    """
    Universal container for content from any source (YouTube, etc.).

    This is passed through the entire pipeline — the summarizer reads the
    transcript from it, and the Notion publisher reads the metadata.

    Field naming is source-agnostic:
      - content_id: video ID, episode ID, file hash, etc.
      - creator:    channel name, podcast host, author, etc.
      - source:     which platform this came from

    Backward-compatible properties (.video_id, .channel) are provided
    so existing code that used the old VideoInfo dataclass still works.

    Attributes:
        content_id:       Unique identifier for the content (11-char YouTube ID, etc.)
        url:              Original URL (YouTube or file path)
        title:            Content title
        creator:          Creator/channel/host name
        transcript:       Full transcript text as a single string
        duration_seconds: Content duration in seconds
        language:         Language code of the transcript
        source:           Which platform this came from (ContentSource enum)
        playlist_id:      Optional playlist/show ID if part of a collection
        playlist_title:   Optional playlist/show title
        episode_number:   Optional episode number (for podcasts)
    """
    content_id: str
    url: str
    title: str
    creator: str
    transcript: str
    duration_seconds: int
    language: str
    source: ContentSource = ContentSource.YOUTUBE
    playlist_id: str | None = None
    playlist_title: str | None = None
    episode_number: int | None = None

    @property
    def duration_formatted(self) -> str:
        """
        Convert raw seconds into human-readable format.
        Example: 3661 seconds -> "1h 1m 1s"
        """
        hours = self.duration_seconds // 3600
        minutes = (self.duration_seconds % 3600) // 60
        seconds = self.duration_seconds % 60
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        return f"{minutes}m {seconds}s"

    @property
    def word_count(self) -> int:
        """Approximate word count of the transcript."""
        return len(self.transcript.split())

    # ── Backward compatibility aliases ──
    # These let code that used VideoInfo.video_id or VideoInfo.channel
    # continue to work without changes.

    @property
    def video_id(self) -> str:
        """Backward compat alias for content_id."""
        return self.content_id

    @property
    def channel(self) -> str:
        """Backward compat alias for creator."""
        return self.creator
