# TubeWise -- Get Wise from Any Tube Video

AI-powered CLI agent that extracts transcripts from YouTube videos and playlists, generates comprehensive summaries using Claude on AWS Bedrock, and publishes beautifully formatted pages to Notion. Supports async background processing, videos of any length with automatic chunking, and playlist batch processing.

**Stack:** Python + LangChain + AWS Bedrock (Claude) + Notion API + SQLite

---

## What It Does

Give it a YouTube URL (video or playlist), and it will:
- Extract the video transcript automatically
- Fetch video title and channel name
- Process it through Claude on AWS Bedrock
- Generate a structured summary with:
  - Executive Summary
  - Key Takeaways
  - Topics Covered (expandable toggles)
  - Concept Deep-Dives (callout blocks)
  - Action Items
  - Mermaid Concept Map (with interactive link)
  - Notable Quotes
  - Resources Mentioned
- Push everything to a beautifully formatted Notion page
- Save a local Markdown backup

**For playlists**, it processes every video and creates an index page linking to all summaries.

**For async mode**, it queues jobs to a background worker daemon so you can submit multiple URLs and walk away.

---

## Quick Start

### Prerequisites

#### 1. AWS Bedrock Setup
1. Go to AWS Console -> **Bedrock** -> **Model Catalog**
2. Search for **Claude** -> click on it -> **Open in Playground**
3. First-time users: Submit use case details when prompted (one-time, takes minutes)
4. Generate a Bedrock API key: Bedrock Console -> **API Keys** -> Generate long-term key
5. Copy the `AWS_BEARER_TOKEN_BEDROCK` value

#### 2. Notion Setup
1. Go to https://www.notion.so/my-integrations
2. Create a new integration -> name it **"TubeWise"**
3. Copy the **Internal Integration Token**
4. Create a Notion page where summaries will be stored
5. **Share that page with your integration** (click `...` -> Connections -> add TubeWise)
6. Copy the page ID from the URL (the 32-char hex string at the end)

#### 3. Python Setup
```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/tubewise.git
cd tubewise

# Create virtual environment
python -m venv venv

# Activate it
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate          # Windows

# Install dependencies
pip install -r requirements.txt
```

#### 4. Configuration
```bash
cp .env.example .env
# Edit .env with your values
```

Your `.env` needs these values:
```dotenv
AWS_REGION=us-east-1
AWS_BEARER_TOKEN_BEDROCK=your-bearer-token-here
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-20250514
NOTION_TOKEN=secret_your-notion-integration-token
NOTION_PARENT_PAGE_ID=your-notion-page-id-32-hex-chars
```

---

## Usage

### YouTube Video
```bash
# Summarize and push to Notion
python agent.py "https://www.youtube.com/watch?v=VIDEO_ID"

# Terminal only (skip Notion)
python agent.py "https://www.youtube.com/watch?v=VIDEO_ID" --no-notion

# Specify transcript language
python agent.py "https://www.youtube.com/watch?v=VIDEO_ID" --language hi
```

### YouTube Playlist
Processes all videos in the playlist and creates an index page linking to every summary.
```bash
python agent.py "https://www.youtube.com/playlist?list=PLAYLIST_ID"
```

### Async Queue (Background Processing)
Submit jobs and let a background worker process them:
```bash
# Submit a job to the queue (returns immediately)
python agent.py "https://www.youtube.com/watch?v=VIDEO_ID" --async

# Check queue status (shows a formatted table with colors)
python agent.py --status

# Start the background worker daemon
python agent.py --worker start

# Start with more parallel workers (default: 2)
python agent.py --worker start --workers 4

# Stop the worker
python agent.py --worker stop

# Check worker status
python agent.py --worker status
```

The `--status` command displays a rich CLI table:
```
+------+-----------------------------+------------+----------+
|  ID  | URL                         | Status     | Time     |
+------+-----------------------------+------------+----------+
|   5  | youtu.be/abc123             | Done       | 45s      |
|   4  | youtu.be/xyz789             | Running    | 1m 23s   |
|   3  | youtu.be/def456             | Failed     | Error... |
|   2  | youtu.be/ghi789             | Queued     | --       |
+------+-----------------------------+------------+----------+
```

### Other Commands
```bash
# Check configuration
python agent.py --show-config
```

---

## Run from Anywhere (Global CLI)

### Option A: Install as CLI tool (requires Python)
```bash
# One-time setup
cd tubewise
pip install -e .

# Move config to permanent location
mkdir -p ~/.tubewise
cp .env ~/.tubewise/.env

# Now run from anywhere
tubewise "https://www.youtube.com/watch?v=VIDEO_ID"
tubewise "https://www.youtube.com/playlist?list=PLAYLIST_ID"
tubewise "URL" --async
tubewise --status
tubewise --worker start
```

### Option B: Build standalone binary (no Python needed)

Creates a single executable -- no Python, no pip, no virtualenv required to run it.

```bash
# Install PyInstaller (one-time, inside your virtualenv)
pip install pyinstaller

# Build the binary
chmod +x build.sh
./build.sh
```

Build takes 1-2 minutes. Output: `dist/tubewise` (~100-150MB, bundles entire Python runtime).

```bash
# Install system-wide
sudo cp dist/tubewise /usr/local/bin/tubewise

# Make sure config is in place
mkdir -p ~/.tubewise
cp .env ~/.tubewise/.env

# Run from anywhere
tubewise "https://www.youtube.com/watch?v=VIDEO_ID"
```

You can share this binary with anyone -- they just need their own `~/.tubewise/.env` with credentials.

---

## How It Handles Long Videos

TubeWise automatically picks the best strategy based on transcript length:

| Video Length | Word Count | Strategy | How It Works |
|---|---|---|---|
| Short/Medium | < 40K words | **Single-shot** | Entire transcript sent to Claude at once. Best quality. |
| Long (2-5+ hrs) | > 40K words | **Map-reduce** | Split into chunks, summarize each, combine into final output. |

You don't configure this -- it decides automatically. Even 5-hour conference talks work out of the box.

The word threshold is configurable via `WORD_THRESHOLD_SINGLE_SHOT` in your `.env` if needed.

---

## Notion Page Structure

TubeWise adapts the Notion page layout based on summary length:

| Summary Length | Layout |
|---|---|
| < 2,500 words | Everything on **one page** |
| > 2,500 words | **Parent page** (summary + takeaways) + **3 sub-pages** (Topics, Actions, Quotes) |
| Playlist | Individual video pages + **playlist index page** linking to all summaries |

The sub-page threshold is configurable via `SUB_PAGE_WORD_THRESHOLD` in your `.env`.

---

## Configuration Reference

All settings are in `.env` (or `~/.tubewise/.env` for global CLI). See `.env.example` for the full template.

### Required Settings

| Setting | Description |
|---|---|
| `AWS_REGION` | AWS region with Bedrock access (default: `us-east-1`) |
| `AWS_BEARER_TOKEN_BEDROCK` | Bedrock API key (from Bedrock console) |
| `BEDROCK_MODEL_ID` | Claude model to use |
| `NOTION_TOKEN` | Notion integration token |
| `NOTION_PARENT_PAGE_ID` | Notion page ID where summaries are created |

### Optional Settings

| Setting | Default | Description |
|---|---|---|
| `TRANSCRIPT_LANGUAGE` | `en` | Default transcript language |
| `MAX_TOKENS` | `4096` | Max summary length. Set to `8192` for longer summaries |
| `TEMPERATURE` | `0.3` | Creativity (0.0 = focused, 1.0 = creative) |

### Processing Thresholds

| Setting | Default | Description |
|---|---|---|
| `WORD_THRESHOLD_SINGLE_SHOT` | `40000` | Above this word count: map-reduce strategy |
| `SUB_PAGE_WORD_THRESHOLD` | `2500` | Above this: multi-page Notion layout |
| `NOTION_BLOCK_BATCH_SIZE` | `100` | Notion API blocks per request |
| `BEDROCK_READ_TIMEOUT` | `300` | Seconds to wait for Claude's response |
| `FILENAME_MAX_LENGTH` | `80` | Max chars for local summary filenames |

### Async Queue Settings

| Setting | Default | Description |
|---|---|---|
| `QUEUE_DB_PATH` | `~/.tubewise/queue.db` | SQLite database path for job queue |
| `DEFAULT_WORKER_COUNT` | `2` | Number of parallel workers |
| `LOG_FILE_PATH` | `~/.tubewise/tubewise.log` | Debug log file path |
| `LOG_LEVEL` | `INFO` | Console log level (DEBUG, INFO, WARNING, ERROR) |

### Available Models
```dotenv
# Most powerful (slower, higher cost)
BEDROCK_MODEL_ID=us.anthropic.claude-opus-4-6-v1

# Recommended -- great quality, fast
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-20250514

# Budget -- good for testing
BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
```

### Authentication Methods

TubeWise supports two auth methods. It auto-detects which to use based on what's set in `.env`.

```dotenv
# Method 1: Bearer Token from Bedrock Console (recommended)
AWS_BEARER_TOKEN_BEDROCK=your-token-here

# Method 2: Standard IAM Access Keys from IAM Console (fallback)
# Only needed if NOT using Bearer Token above
# AWS_ACCESS_KEY_ID=AKIA...
# AWS_SECRET_ACCESS_KEY=wJal...
```

---

## Project Structure
```
tubewise/
├── agent.py              # CLI entry point and pipeline orchestrator
├── config.py             # Configuration loader (.env -> Config class)
├── transcript.py         # YouTube transcript + metadata extraction (yt-dlp)
├── summarizer.py         # LangChain + Bedrock summarization engine
├── notion_publisher.py   # Notion page creation with rich formatting
├── prompts.py            # All LLM prompts (edit this to customize output)
├── models.py             # ContentInfo dataclass, ContentSource enum
├── playlist.py           # YouTube playlist detection and video listing
├── queue_manager.py      # SQLite job queue and CLI status table
├── worker.py             # Background daemon with parallel workers
├── logging_config.py     # Two-tier logging setup (console + file)
├── setup.py              # CLI tool installer (pip install -e .)
├── build.sh              # Standalone binary builder (PyInstaller)
├── requirements.txt      # Python dependencies
├── .env.example          # Environment variable template
├── pytest.ini            # Test configuration
├── tests/                # Unit test suite (121 tests)
│   ├── conftest.py       # Shared test fixtures
│   ├── test_agent.py
│   ├── test_config.py
│   ├── test_models.py
│   ├── test_transcript.py
│   ├── test_notion_publisher.py
│   ├── test_playlist.py
│   └── test_queue_manager.py
├── CLAUDE.md             # AI assistant project context
└── Readme.md             # This file
```

### Pipeline Flow

**Synchronous (default):**
```
YouTube URL (Video or Playlist)
    |
    +-- Single video   -> transcript.py (transcript + metadata via yt-dlp)
    +-- Playlist       -> playlist.py (list videos) -> loop per video
                |
                v
        summarizer.py (Claude via Bedrock, single-shot or map-reduce)
                |
                v
        Save local markdown backup (summary_TITLE.md)
                |
                v
        notion_publisher.py (Notion page with rich formatting)
```

**Asynchronous (--async):**
```
tubewise "URL" --async  ->  queue_manager.py (enqueue to SQLite)
tubewise --worker start ->  worker.py (daemon polls queue, parallel processing)
tubewise --status       ->  queue_manager.py (formatted CLI status table)
```

---

## Customization

### Tweak Summary Output
Edit `prompts.py` -- no code changes needed. All LLM instructions are in one file.

- Want more takeaways? Change "5-10 key takeaways" to "10-15"
- Want summaries in Hindi? Add "Write everything in Hindi" to `SYSTEM_PROMPT`
- Want a new section? Add a `### NEW_SECTION` block to the prompt template
- Want shorter summaries? Add "Be concise, limit each section to 2-3 sentences"

### Change Notion Formatting
Edit `notion_publisher.py` -- each section has its own block builder.

- Change emoji icons by editing the emoji parameters
- Change callout colors (`blue_background` -> `yellow_background`, etc.)
- Reorder sections by moving code blocks around
- Add new Notion block types (tables, to-do checkboxes, etc.)

---

## Testing

TubeWise has 121 unit tests covering all modules:

```bash
# Run all tests
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_transcript.py -v

# Run with the project virtualenv
~/.virtualenvs/tubewise/bin/python -m pytest tests/ -v
```

Test coverage includes:
- **test_transcript.py** -- URL parsing (all formats), transcript processing
- **test_notion_publisher.py** -- Section parsing, text splitting, block builders
- **test_config.py** -- Validation, auth detection, default values
- **test_models.py** -- ContentInfo properties, backward compat aliases
- **test_agent.py** -- Local file saving
- **test_queue_manager.py** -- Queue operations, status table, helpers
- **test_playlist.py** -- URL detection, playlist ID extraction

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "No transcript available" | Video has no captions. Try `--language` flag or a different video |
| "Read timeout" | Normal for Opus on long videos. Increase `BEDROCK_READ_TIMEOUT` or use Sonnet |
| Bedrock access denied | Check IAM permissions or regenerate Bedrock API key |
| "Invalid model identifier" | Use inference profile ID (`us.anthropic.claude-sonnet-4-20250514`) not raw model ID |
| Notion 401/403 error | Share the Notion page with your integration (`...` -> Connections -> Add) |
| "YouTube Video" as page title | Make sure `yt-dlp` is installed (`pip install yt-dlp`) |
| Summary getting cut off | Set `MAX_TOKENS=8192` in your `.env` |
| Worker won't start | Check `~/.tubewise/tubewise.log` for errors. Worker uses `os.fork()` (macOS/Linux only) |
| Queue jobs stuck in "processing" | Run `tubewise --worker stop` then `tubewise --worker start` to reset |

---

## Cost Estimate

| Model | Cost per Video | Best For |
|-------|---------------|----------|
| Claude Opus 4.6 | ~$0.15-0.50 | Deepest, most thorough summaries |
| Claude Sonnet 4 | ~$0.05-0.15 | Best quality-to-cost ratio |
| Claude Haiku 4.5 | ~$0.01-0.05 | Bulk processing, testing |

Notion API and YouTube transcript extraction are free.

---

## Roadmap

- **Spotify Podcast Support** -- Summarize Spotify podcast episodes (pending reliable transcript API)
- **Local Audio/Video File Support** -- Accept MP3/MP4 files, transcribe via AWS Transcribe or Whisper

---

## License

MIT
