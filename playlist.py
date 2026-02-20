"""
playlist.py — TubeWise YouTube Playlist Handling
==================================================
Detects YouTube playlist URLs, extracts video metadata for all videos
in the playlist, and provides helpers for batch processing.

Uses yt-dlp with extract_flat=True to quickly list all videos
without downloading any content.

SUPPORTED URL FORMATS:
    - https://www.youtube.com/playlist?list=PLAYLIST_ID
    - https://www.youtube.com/watch?v=VIDEO_ID&list=PLAYLIST_ID
    - https://youtube.com/playlist?list=PLAYLIST_ID

USAGE:
    from playlist import is_playlist_url, get_playlist_videos

    if is_playlist_url(url):
        data = get_playlist_videos(url)
        for video in data["videos"]:
            process(video["url"])
"""

from __future__ import annotations

import re
import logging

logger = logging.getLogger("tubewise.playlist")


def is_playlist_url(url: str) -> bool:
    """
    Detect if a URL is or contains a YouTube playlist reference.

    Checks for the 'list=' query parameter which indicates a playlist.

    Args:
        url: Any URL string

    Returns:
        True if the URL references a YouTube playlist
    """
    return bool(re.search(r"[?&]list=|/playlist\?list=", url))


def extract_playlist_id(url: str) -> str:
    """
    Extract the playlist ID from a YouTube URL.

    Args:
        url: A YouTube URL containing a playlist reference

    Returns:
        The playlist ID string

    Raises:
        ValueError: If no playlist ID can be found
    """
    match = re.search(r"[?&]list=([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError(
            f"Could not extract playlist ID from: {url}\n"
            f"Expected format: youtube.com/playlist?list=PLAYLIST_ID"
        )
    return match.group(1)


def get_playlist_videos(url: str) -> dict:
    """
    Extract all video entries from a YouTube playlist using yt-dlp.

    Uses yt-dlp's extract_flat mode which lists all videos without
    downloading any content. This is fast — typically takes 2-5 seconds
    for playlists with up to 200 videos.

    Args:
        url: A YouTube playlist URL

    Returns:
        Dict with keys:
          - playlist_id:    The playlist ID
          - playlist_title: Human-readable playlist name
          - videos:         List of dicts, each with {id, title, url}

    Raises:
        Exception: If yt-dlp fails to extract playlist info
    """
    import yt_dlp

    logger.info(f"\n📋 Extracting playlist info...")

    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise Exception(
            f"Could not extract playlist info. "
            f"Make sure the playlist URL is valid and public. Error: {e}"
        ) from e

    playlist_title = info.get("title", "YouTube Playlist")
    entries = info.get("entries", [])

    videos = []
    for entry in entries:
        if entry and entry.get("id"):
            videos.append({
                "id": entry["id"],
                "title": entry.get("title", "Unknown"),
                "url": f"https://www.youtube.com/watch?v={entry['id']}",
            })

    playlist_id = extract_playlist_id(url) if "list=" in url else info.get("id", "unknown")

    logger.info(f"   📋 Playlist: {playlist_title}")
    logger.info(f"   📹 Videos found: {len(videos)}")

    return {
        "playlist_id": playlist_id,
        "playlist_title": playlist_title,
        "videos": videos,
    }
