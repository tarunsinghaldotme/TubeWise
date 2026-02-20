#!/usr/bin/env python3
"""
agent.py — TubeWise: Main Entry Point
=======================================
This is the file you run from the command line. It orchestrates the entire flow:

  YouTube URL → Transcript → LLM Summary → Notion Page

USAGE EXAMPLES:
  # Basic: summarize and push to Notion
  tubewise "https://www.youtube.com/watch?v=VIDEO_ID"

  # YouTube playlist (processes all videos)
  tubewise "https://www.youtube.com/playlist?list=PLAYLIST_ID"

  # Terminal only (no Notion): prints summary and saves locally
  tubewise "https://www.youtube.com/watch?v=VIDEO_ID" --no-notion

  # Specify transcript language (e.g., Hindi)
  tubewise "https://www.youtube.com/watch?v=VIDEO_ID" --language hi

  # Async mode: submit job to background queue
  tubewise "https://www.youtube.com/watch?v=VIDEO_ID" --async

  # Check queue status
  tubewise --status

  # Manage background worker
  tubewise --worker start
  tubewise --worker stop
  tubewise --worker status

  # Check your configuration
  tubewise --show-config

THE PIPELINE:
  ┌──────────┐     ┌──────────────┐     ┌──────────────────┐     ┌──────────┐
  │  Step 1   │────▶│   Step 2      │────▶│    Step 3         │────▶│  Step 4   │
  │ Extract   │     │  Summarize    │     │  Save Locally     │     │  Publish  │
  │ Transcript│     │  via Bedrock  │     │  (always)         │     │ to Notion │
  └──────────┘     └──────────────┘     └──────────────────┘     └──────────┘
  transcript.py     summarizer.py       This file (agent.py)    notion_publisher.py

WHY THIS IS SEPARATE FROM THE OTHER MODULES:
- This file handles CLI (command line interface) and orchestration
- Other modules handle specific responsibilities
- This separation means you could swap the CLI with a web interface or API
  without changing any of the core logic
"""

from __future__ import annotations

import sys
import multiprocessing

# ── PyInstaller freeze support (MUST be called before any multiprocessing) ──
# When running as a frozen binary (PyInstaller), multiprocessing spawns
# worker subprocesses by re-invoking sys.executable. Without freeze_support(),
# the subprocess re-runs main() instead of running the worker function,
# causing an infinite spawn loop or silent crash.
# This must be called as early as possible, before any imports that might
# trigger multiprocessing or ProcessPoolExecutor usage.
multiprocessing.freeze_support()

import argparse
import time
import logging

from logging_config import setup_logging
from config import Config

# NOTE: Heavy imports (transcript, summarizer, notion_publisher) are done
# LAZILY inside the functions that need them, not here at module level.
# This is critical for binary startup speed — importing langchain_aws alone
# takes ~500ms (pulls in NumPy, OpenBLAS, Neptune graph DB, embeddings,
# etc.) even though TubeWise only uses ChatBedrock.
#
# Without lazy imports, even "tubewise --help" would take 5-30 seconds
# in a PyInstaller binary because EVERY module gets loaded at startup.

logger = logging.getLogger("tubewise.agent")


def print_banner() -> None:
    """
    Print a nice banner when the agent starts.
    Just cosmetic — makes the terminal output look professional.
    """
    print("""
╔══════════════════════════════════════════════════════════╗
║       🧠 TubeWise — Get wise from any tube video         ║
║       Powered by AWS Bedrock (Claude) + LangChain        ║
╚══════════════════════════════════════════════════════════╝
    """)


def save_local_output(summary: str, video_title: str) -> str:
    """
    Save the summary as a local Markdown file.

    This ALWAYS runs (even when publishing to Notion) as a backup.
    The file is saved in the current directory with the video title as filename.

    WHY:
    - Acts as a backup in case Notion publishing fails
    - Useful for offline reference
    - Can be committed to git, shared via email, etc.

    Args:
        summary:     The raw summary text from Claude
        video_title: Video title (used to generate the filename)

    Returns:
        The filename where the summary was saved
    """
    safe_title = "".join(c for c in video_title if c.isalnum() or c in " -_").strip()
    max_len = Config.FILENAME_MAX_LENGTH
    safe_title = safe_title[:max_len] if len(safe_title) > max_len else safe_title

    filename = f"summary_{safe_title}.md"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# {video_title}\n\n")
        f.write(summary)

    return filename


def _process_single_url(url: str, no_notion: bool) -> None:
    """
    Run the full pipeline for a single YouTube video URL.

    Args:
        url:       The content URL to process
        no_notion: If True, skip Notion publishing
    """
    # ── Lazy imports: only load heavy deps when actually processing ──
    from transcript import fetch_video_info
    from summarizer import generate_summary
    from notion_publisher import publish_to_notion

    # ── Step 1: Extract content information ──
    logger.info("\n" + "=" * 50)
    logger.info("STEP 1: Extracting Content Information")
    logger.info("=" * 50)

    content = fetch_video_info(url, Config.TRANSCRIPT_LANGUAGE)

    # ── Step 2: Generate AI summary ──
    logger.info("\n" + "=" * 50)
    logger.info("STEP 2: Generating AI Summary")
    logger.info("=" * 50)
    raw_summary = generate_summary(content)

    # ── Step 3: Save locally (always) ──
    logger.info("\n" + "=" * 50)
    logger.info("STEP 3: Saving Output")
    logger.info("=" * 50)
    local_file = save_local_output(raw_summary, content.title)
    logger.info(f"💾 Local file saved: {local_file}")

    # ── Step 4: Publish to Notion (unless --no-notion) ──
    if not no_notion:
        logger.info("\n" + "=" * 50)
        logger.info("STEP 4: Publishing to Notion")
        logger.info("=" * 50)
        page_url = publish_to_notion(
            raw_summary=raw_summary,
            video_url=content.url,
            video_title=content.title,
            channel=content.creator,
            duration=content.duration_formatted,
            word_count=content.word_count,
        )
        logger.info(f"\n🎉 Notion page: {page_url}")
    else:
        print("\n📋 Summary Output:")
        print("=" * 50)
        print(raw_summary)


def _process_playlist(url: str, no_notion: bool) -> None:
    """
    Process an entire YouTube playlist — summarize each video and create
    a Notion index page linking to all summaries.

    Args:
        url:       The playlist URL
        no_notion: If True, skip Notion publishing
    """
    # ── Lazy imports: only load heavy deps when actually processing ──
    from transcript import fetch_video_info
    from summarizer import generate_summary
    from notion_publisher import publish_to_notion, create_playlist_index_page, get_notion_client
    from playlist import get_playlist_videos

    playlist_data = get_playlist_videos(url)
    videos = playlist_data["videos"]
    playlist_title = playlist_data["playlist_title"]

    logger.info(f"\n🎵 Playlist: {playlist_title} ({len(videos)} videos)")

    video_pages = []
    for i, video_entry in enumerate(videos):
        logger.info(f"\n{'─' * 50}")
        logger.info(f"📹 Video {i + 1}/{len(videos)}: {video_entry['title']}")
        logger.info(f"{'─' * 50}")

        try:
            content = fetch_video_info(video_entry["url"], Config.TRANSCRIPT_LANGUAGE)
            raw_summary = generate_summary(content)
            save_local_output(raw_summary, content.title)

            notion_url = ""
            if not no_notion:
                notion_url = publish_to_notion(
                    raw_summary=raw_summary,
                    video_url=content.url,
                    video_title=content.title,
                    channel=content.creator,
                    duration=content.duration_formatted,
                    word_count=content.word_count,
                )
            video_pages.append({
                "title": content.title,
                "url": video_entry["url"],
                "notion_url": notion_url,
                "status": "success",
            })
            logger.info(f"   ✅ Done: {content.title}")

        except Exception as e:
            logger.error(f"   ❌ Failed: {video_entry['title']} — {e}")
            video_pages.append({
                "title": video_entry["title"],
                "url": video_entry["url"],
                "notion_url": "",
                "status": f"failed: {e}",
            })
            continue

    # Create playlist index page on Notion
    if not no_notion and video_pages:
        logger.info(f"\n📑 Creating playlist index page...")
        client = get_notion_client()
        index_url = create_playlist_index_page(client, playlist_title, video_pages)
        logger.info(f"🎉 Playlist index: {index_url}")

    # Summary
    succeeded = sum(1 for v in video_pages if v["status"] == "success")
    failed = len(video_pages) - succeeded
    logger.info(f"\n📊 Playlist complete: {succeeded} succeeded, {failed} failed")


def main() -> None:
    """
    Main function — the entry point of the entire agent.

    Handles:
    - Single video processing
    - Playlist processing
    - Async queue submission
    - Queue status display
    - Worker management
    - Hidden --_daemon flag (for PyInstaller binary worker daemon)
    """

    # ── Hidden daemon entry point (PyInstaller binary only) ──
    # When running as a frozen binary, `start_daemon()` in worker.py
    # can't use `python -c "..."` because sys.executable IS the binary,
    # not the Python interpreter. Instead, it re-invokes the binary with
    # `--_daemon N` which we intercept here BEFORE argparse runs.
    # This must happen early — no banner, no logging setup, just launch
    # the daemon directly.
    if len(sys.argv) >= 2 and sys.argv[1] == "--_daemon":
        worker_count = int(sys.argv[2]) if len(sys.argv) >= 3 else Config.DEFAULT_WORKER_COUNT
        from worker import _run_daemon
        _run_daemon(worker_count)
        return

    parser = argparse.ArgumentParser(
        description="🧠 TubeWise — Summarize YouTube content using AI and publish to Notion"
    )

    parser.add_argument(
        "url",
        nargs="?",
        default=None,
        help="YouTube video/playlist URL or video ID",
    )

    parser.add_argument(
        "--no-notion",
        action="store_true",
        help="Skip publishing to Notion (print to terminal and save locally)",
    )

    parser.add_argument(
        "--language", "-l",
        default=None,
        help="Transcript language code (default: en). Examples: en, hi, es, fr",
    )

    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Show current configuration and exit",
    )

    # ── Async queue flags ──
    parser.add_argument(
        "--async",
        dest="async_mode",
        action="store_true",
        help="Submit job to background queue instead of processing now",
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help="Show queue status",
    )

    parser.add_argument(
        "--worker",
        choices=["start", "stop", "status"],
        help="Manage background worker daemon (start/stop/status)",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help=f"Number of parallel workers (default: {Config.DEFAULT_WORKER_COUNT})",
    )

    args = parser.parse_args()

    # ══════════════════════════════════════════════
    # STARTUP
    # ══════════════════════════════════════════════

    setup_logging(level=Config.LOG_LEVEL, log_file=Config.LOG_FILE_PATH)
    print_banner()

    if args.language:
        Config.TRANSCRIPT_LANGUAGE = args.language

    if args.show_config:
        Config.print_config()
        return

    # ── Queue status ──
    if args.status:
        from queue_manager import QueueManager
        qm = QueueManager()
        print(qm.format_status_table())
        return

    # ── Worker management ──
    if args.worker:
        from worker import start_daemon, stop_daemon
        from queue_manager import QueueManager
        worker_count = args.workers or Config.DEFAULT_WORKER_COUNT

        if args.worker == "start":
            start_daemon(worker_count)
        elif args.worker == "stop":
            stop_daemon()
        elif args.worker == "status":
            qm = QueueManager()
            state = qm.get_worker_state()
            if state and state["status"] == "running":
                print(f"● Worker running (PID: {state['pid']}, {state['worker_count']} workers)")
            else:
                print("○ Worker not running")
        return

    # ── Check that a URL was provided ──
    if not args.url:
        parser.print_help()
        print("\n❌ Please provide a URL.")
        print('   Example: tubewise "https://www.youtube.com/watch?v=VIDEO_ID"')
        sys.exit(1)

    # ── Async mode: enqueue and exit ──
    if args.async_mode:
        from queue_manager import QueueManager
        qm = QueueManager()
        job_id = qm.enqueue(
            url=args.url,
            language=Config.TRANSCRIPT_LANGUAGE,
            no_notion=args.no_notion,
        )
        print(f"📥 Job #{job_id} queued: {args.url}")
        print("   Run 'tubewise --status' to check progress")
        print("   Run 'tubewise --worker start' to start processing")
        return

    # ══════════════════════════════════════════════
    # CONFIGURATION VALIDATION
    # ══════════════════════════════════════════════

    errors = Config.validate(skip_notion=args.no_notion)
    if errors:
        logger.error("❌ Configuration errors:")
        for error in errors:
            logger.error(f"   • {error}")
        logger.error("\n📝 Copy .env.example to .env and fill in your values.")
        sys.exit(1)

    start_time = time.time()

    try:
        from playlist import is_playlist_url

        if is_playlist_url(args.url):
            _process_playlist(args.url, args.no_notion)
        else:
            _process_single_url(args.url, args.no_notion)

        elapsed = time.time() - start_time
        logger.info(f"\n⏱️  Total time: {elapsed:.1f} seconds")
        logger.info("✨ Done!")

    except KeyboardInterrupt:
        print("\n\n⚠️  Cancelled by user.")
        sys.exit(0)

    except Exception as e:
        logger.error(f"\n❌ Error: {e}")
        logger.error("\n💡 Tips:")
        logger.error("   • Check that the URL is correct and has captions/transcript")
        logger.error("   • Verify your AWS credentials and Bedrock model access")
        logger.error("   • Make sure your Notion integration has access to the target page")
        logger.debug(f"Full error: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
