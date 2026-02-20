"""
transcript.py — TubeWise YouTube Transcript & Metadata Extraction
==================================================================
This module handles everything related to getting data FROM YouTube:
  1. Parsing the video URL to extract the video ID
  2. Fetching the transcript/captions from YouTube
  3. Getting video metadata (title, channel name)

WHY SEPARATE MODULE?
- Keeps YouTube-specific logic isolated from LLM and Notion logic
- Easy to swap out if YouTube changes their API or you want to support other platforms
- Can be tested independently

KEY DEPENDENCY:
- youtube-transcript-api (v1.2+): A Python library that fetches YouTube captions
  without needing a YouTube Data API key. It works by accessing the same
  caption data that YouTube's own player uses.
  
  ⚠️ IMPORTANT: Version 1.2+ changed to an instance-based API.
  Old way (broken): YouTubeTranscriptApi.list_transcripts(video_id)
  New way (correct): YouTubeTranscriptApi().list(video_id)

CUSTOMIZATION IDEAS:
- Add support for other video platforms (Vimeo, etc.) by adding new extraction functions
- Add caching so you don't re-fetch transcripts for the same video
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass

from youtube_transcript_api import YouTubeTranscriptApi

logger = logging.getLogger("tubewise.transcript")


# ══════════════════════════════════════════════════════════════
# DATA MODEL
# ══════════════════════════════════════════════════════════════
# The canonical data model is ContentInfo in models.py.
# VideoInfo is kept as an alias for backward compatibility.

from models import ContentInfo

# Backward compatibility alias — existing code that imports VideoInfo still works
VideoInfo = ContentInfo


# ══════════════════════════════════════════════════════════════
# URL PARSING
# ══════════════════════════════════════════════════════════════

def extract_video_id(url: str) -> str:
    """
    Extract the 11-character video ID from various YouTube URL formats.
    
    YouTube has many URL formats, and users might paste any of them:
      - https://www.youtube.com/watch?v=dQw4w9WgXcQ              (standard)
      - https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxyz... (with playlist)
      - https://youtu.be/dQw4w9WgXcQ                              (short link)
      - https://www.youtube.com/embed/dQw4w9WgXcQ                 (embed URL)
      - https://www.youtube.com/v/dQw4w9WgXcQ                     (old format)
      - dQw4w9WgXcQ                                                (just the ID)
    
    This function handles ALL of these using regex pattern matching.
    
    Args:
        url: Any YouTube URL or bare video ID
    
    Returns:
        11-character video ID string
    
    Raises:
        ValueError: If no valid video ID can be extracted
    """
    # Each pattern tries to match the 11-character video ID from different URL formats
    # [a-zA-Z0-9_-]{11} = exactly 11 characters that are alphanumeric, underscore, or hyphen
    patterns = [
        # Pattern 1: Standard YouTube URLs (watch, short link, embed, v/ format)
        # Also handles URLs with extra query params like &list=PLxyz
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([a-zA-Z0-9_-]{11})',
        # Pattern 2: Just a bare 11-character video ID (no URL)
        r'^([a-zA-Z0-9_-]{11})$',
    ]

    # Try each pattern until one matches
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)  # group(1) = the captured video ID

    # If nothing matched, give a helpful error
    raise ValueError(
        f"Could not extract video ID from URL: {url}\n"
        f"Supported formats: youtube.com/watch?v=XXX, youtu.be/XXX"
    )


# ══════════════════════════════════════════════════════════════
# TRANSCRIPT FETCHING
# ══════════════════════════════════════════════════════════════

def get_transcript(video_id: str, language: str = "en") -> tuple[str, int, str]:
    """
    Fetch the transcript (captions) for a YouTube video.
    
    This is the most critical function — without a transcript, nothing else works.
    
    The function tries multiple strategies to get the best transcript:
      Strategy 1: Use the simple .fetch() method with desired language
      Strategy 2: If that fails, list all transcripts and find the best match
                  - Prefer manually created subtitles (highest quality)
                  - Fall back to auto-generated subtitles
                  - Last resort: get any transcript and translate it
    
    IMPORTANT (v1.2+ API change):
    The youtube-transcript-api library changed from static methods to instance methods.
    You must create an instance first: ytt = YouTubeTranscriptApi()
    Then call: ytt.fetch() or ytt.list()
    
    Args:
        video_id: The 11-character YouTube video ID
        language: Desired language code (e.g., "en", "hi", "es")
    
    Returns:
        Tuple of (transcript_text, duration_seconds, language_code_used)
        - transcript_text: The entire transcript as a single string
        - duration_seconds: Approximate video duration (from last caption timestamp)
        - language_code_used: The actual language of the transcript we got
    
    Raises:
        Exception: If no transcript is available at all (video has no captions)
    """
    
    # ── Create an instance of the API client (required in v1.2+) ──
    # Old way (broken in v1.2+): YouTubeTranscriptApi.list_transcripts(video_id)
    # New way: YouTubeTranscriptApi().list(video_id)
    ytt = YouTubeTranscriptApi()
    
    try:
        # ══════════════════════════════════════════
        # STRATEGY 1: Simple fetch with desired language
        # ══════════════════════════════════════════
        # .fetch() is a convenience method that:
        #   1. Lists available transcripts
        #   2. Finds the best match for your language
        #   3. Fetches and returns the transcript
        # It handles language fallback automatically.
        
        transcript_data = ytt.fetch(video_id, languages=[language])
        
        # ── Extract text and duration from the transcript data ──
        # transcript_data is iterable — each item is a snippet with text + timing
        full_text, duration = _process_transcript_entries(transcript_data)
        
        return full_text, duration, language
        
    except Exception as simple_error:
        # Strategy 1 failed — maybe the language isn't available.
        # Fall through to Strategy 2 for more control.
        pass
    
    try:
        # ══════════════════════════════════════════
        # STRATEGY 2: List all transcripts and find the best one
        # ══════════════════════════════════════════
        # .list() returns a TranscriptList with all available caption tracks.
        # We iterate through them to find the best option.
        
        transcript_list = ytt.list(video_id)
        
        transcript = None       # Will hold the transcript object we find
        lang_used = language    # Track which language we actually ended up with

        # ── Try to find a transcript in the desired language ──
        # Iterate through all available transcripts
        for t in transcript_list:
            # Check if this transcript matches our desired language
            if t.language_code == language:
                transcript = t
                lang_used = language
                break
        
        # ── If no exact match, take any transcript and translate ──
        if transcript is None:
            for t in transcript_list:
                transcript = t
                lang_used = t.language_code
                # If it's in a different language, try to translate
                if lang_used != language:
                    try:
                        transcript = t.translate(language)
                        lang_used = language
                    except Exception:
                        pass  # Translation not available — use original language
                break  # Take the first available one

        # ── If still no transcript found, give up ──
        if transcript is None:
            raise Exception(
                f"No transcript available for video {video_id}. "
                f"The video might not have captions enabled."
            )

        # ── Fetch the actual transcript content ──
        # .fetch() on a Transcript object downloads the caption data
        entries = transcript.fetch()
        
        # ── Process entries into text + duration ──
        full_text, duration = _process_transcript_entries(entries)
        
        return full_text, duration, lang_used

    except Exception as e:
        # Provide a helpful error message based on the type of failure
        if "No transcript" in str(e) or "disabled" in str(e).lower():
            raise Exception(
                f"No transcript available for this video. "
                f"Make sure the video has captions/subtitles enabled."
            ) from e
        raise  # Re-raise any other unexpected errors


def _process_transcript_entries(entries) -> tuple[str, int]:
    """
    Process transcript entries into a single text string and calculate duration.
    
    Transcript entries come in various formats depending on the library version:
    - Dict format: {"text": "Hello", "start": 0.0, "duration": 2.5}
    - Object format: entry.text, entry.start, entry.duration
    - FetchedTranscript: iterable of snippet objects
    
    This function handles all formats gracefully.
    
    Args:
        entries: Iterable of transcript entries (dicts or objects)
    
    Returns:
        Tuple of (full_text, duration_seconds)
    """
    texts = []       # Collect all text snippets
    last_start = 0   # Track timestamp of last entry for duration calculation
    last_duration = 0
    
    for entry in entries:
        # ── Extract text from entry (handles both dict and object formats) ──
        if isinstance(entry, dict):
            text = entry.get("text", "")
            start = entry.get("start", 0)
            dur = entry.get("duration", 0)
        else:
            # Object format — try attribute access
            text = getattr(entry, "text", str(entry))
            start = getattr(entry, "start", 0)
            dur = getattr(entry, "duration", 0)
        
        if text:
            texts.append(text)
        
        # Track the last entry's timing for duration calculation
        last_start = start
        last_duration = dur
    
    # ── Join all text snippets into one continuous string ──
    full_text = " ".join(texts)
    
    # ── Calculate approximate video duration ──
    # Last entry's start time + its duration ≈ total video length
    duration = int(last_start + last_duration)
    
    return full_text, duration


# ══════════════════════════════════════════════════════════════
# VIDEO METADATA
# ══════════════════════════════════════════════════════════════

def get_video_metadata(video_id: str) -> tuple[str, str]:
    """
    Get video title and channel name from YouTube.
    
    Uses 'yt-dlp' — the most reliable YouTube metadata extractor available.
    Unlike pytube which breaks frequently, yt-dlp is actively maintained
    and handles YouTube's constant page structure changes.
    
    Falls back gracefully if it fails — the summary still works with generic metadata.
    
    Args:
        video_id: The 11-character YouTube video ID
    
    Returns:
        Tuple of (title, channel_name)
        Falls back to ("YouTube Video", "Unknown Channel") if fetch fails
    """
    try:
        import yt_dlp
        
        # ── Configure yt-dlp to ONLY fetch metadata, not download the video ──
        # 'skip_download': We don't need the actual video file
        # 'quiet': Suppress yt-dlp's own console output
        # 'no_warnings': Don't print warnings
        ydl_opts = {
            "skip_download": True,   # Don't download the video — just get info
            "quiet": True,           # No console output from yt-dlp
            "no_warnings": True,     # Suppress warnings
        }
        
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # extract_info fetches all metadata without downloading
            info = ydl.extract_info(url, download=False)
            
            title = info.get("title", "YouTube Video")
            channel = info.get("channel", "") or info.get("uploader", "Unknown Channel")
            
            return title, channel
            
    except Exception:
        # If yt-dlp also fails, try pytube as last resort
        try:
            from pytube import YouTube
            yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
            return yt.title or "YouTube Video", yt.author or "Unknown Channel"
        except Exception:
            return "YouTube Video", "Unknown Channel"


# ══════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════

def fetch_video_info(url: str, language: str = "en") -> VideoInfo:
    """
    Main entry point for this module.
    
    Takes a YouTube URL and returns a complete VideoInfo object with
    everything needed for summarization and Notion publishing.
    
    This is the ONLY function other modules need to call from this file.
    It orchestrates all the steps:
      1. Parse URL → get video ID
      2. Fetch transcript
      3. Fetch metadata (title, channel)
      4. Package everything into a VideoInfo object
    
    Args:
        url:      YouTube video URL (any format) or bare video ID
        language: Desired transcript language (default: "en")
    
    Returns:
        VideoInfo object containing all video data
    
    Raises:
        ValueError: If URL can't be parsed
        Exception:  If transcript can't be fetched
    """
    # ── Parse the URL to get video ID ──
    logger.info(f"\n🔗 Processing URL: {url}")
    video_id = extract_video_id(url)
    logger.debug(f"Video ID: {video_id}")

    # ── Fetch the transcript ──
    logger.info("📝 Fetching transcript...")
    transcript, duration, lang_used = get_transcript(video_id, language)
    logger.info(f"   ✅ Transcript fetched ({len(transcript.split())} words, {lang_used})")

    # ── Fetch video metadata (title, channel) ──
    logger.info("ℹ️  Fetching video metadata...")
    title, channel = get_video_metadata(video_id)
    logger.info(f"   📺 Title: {title}")
    logger.info(f"   👤 Channel: {channel}")

    # ── Package everything into a VideoInfo object and return ──
    from models import ContentSource
    return VideoInfo(
        content_id=video_id,
        url=f"https://www.youtube.com/watch?v={video_id}",
        title=title,
        creator=channel,
        transcript=transcript,
        duration_seconds=duration,
        language=lang_used,
        source=ContentSource.YOUTUBE,
    )