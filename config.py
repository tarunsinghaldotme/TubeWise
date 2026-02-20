"""
config.py — TubeWise Configuration Loader & Validator
======================================================
This is the central configuration file for TubeWise.
It reads all settings from a .env file and makes them available
across the project via the Config class.

WHY THIS EXISTS:
- Keeps all secrets (API keys, tokens) out of code
- One place to change settings without touching multiple files
- Validates everything upfront so you get clear errors before anything runs

.env FILE LOCATION:
TubeWise looks for .env in this order:
  1. ~/.tubewise/.env  (recommended — works from anywhere)
  2. ./.env            (current directory — fallback for development)

To set up once:
  mkdir -p ~/.tubewise
  cp .env.example ~/.tubewise/.env
  # Edit ~/.tubewise/.env with your values

CUSTOMIZATION:
- Change BEDROCK_MODEL_ID to use a different Claude model (Haiku for speed, Opus for depth)
- Adjust TEMPERATURE to control how creative vs focused the summaries are
- Modify CHUNK_SIZE if you find long videos are losing context
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from dotenv import load_dotenv  # Reads .env file and loads values into environment

# ──────────────────────────────────────────────────────────────────
# LOAD .env FILE
# ──────────────────────────────────────────────────────────────────
# We check two locations for the .env file:
#   1. ~/.tubewise/.env  → Fixed home directory location (works from anywhere)
#   2. ./.env            → Current working directory (for development)
#
# The first one found wins. This means once you set up ~/.tubewise/.env,
# you can run 'tubewise' from any folder on your system.
# ──────────────────────────────────────────────────────────────────

# Try home directory first
_home_env = Path.home() / ".tubewise" / ".env"
if _home_env.exists():
    # override=True ensures these values win, even if env vars are already set
    # from a different .env file or shell session
    load_dotenv(_home_env, override=True)
else:
    # Fall back to current directory's .env
    # Also check the project installation directory
    _project_env = Path(__file__).parent / ".env"
    if _project_env.exists():
        load_dotenv(_project_env, override=True)
    else:
        load_dotenv()


class Config:
    """
    Central configuration for TubeWise agent.
    
    All settings are class-level variables, so you can access them anywhere like:
        Config.AWS_REGION
        Config.NOTION_TOKEN
    
    No need to create an instance — just import and use directly.
    """

    # ══════════════════════════════════════════════════════════════
    # AWS SETTINGS
    # ══════════════════════════════════════════════════════════════
    
    # AWS_REGION: The AWS region where you have Bedrock access.
    # Common regions with Bedrock + Claude: us-east-1, us-west-2, eu-west-1
    # You can check available regions in AWS Console → Bedrock → Model Access
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")

    # ── AWS Authentication ──
    # TubeWise supports TWO authentication methods. Use whichever you have:
    #
    # METHOD 1: Bearer Token (from Bedrock Console)
    #   - Generated from: AWS Console → Bedrock → API Keys
    #   - Set AWS_BEARER_TOKEN_BEDROCK in your .env
    #   - Scoped to Bedrock only (more secure, limited blast radius)
    #   - Can have auto-expiry date
    #
    # METHOD 2: Standard IAM Access Keys
    #   - Generated from: AWS Console → IAM → Users → Security Credentials
    #   - Set AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY in your .env
    #   - Or configure via AWS CLI (aws configure) → stored in ~/.aws/credentials
    #   - boto3 credential chain priority:
    #       Priority 1: Environment variables
    #       Priority 2: ~/.aws/credentials file
    #       Priority 3: IAM role (if running on EC2/ECS/Lambda)
    #
    # HOW IT DECIDES:
    #   If AWS_BEARER_TOKEN_BEDROCK is set → uses Bearer Token auth
    #   Otherwise → falls back to standard IAM credentials (env vars or ~/.aws/credentials)
    
    # Bearer Token from Bedrock Console (Method 1)
    AWS_BEARER_TOKEN_BEDROCK: str = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "")
    
    # Standard IAM Access Keys (Method 2 — fallback)
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")

    @classmethod
    def is_bearer_token_auth(cls) -> bool:
        """Check if Bearer Token authentication is configured."""
        return bool(cls.AWS_BEARER_TOKEN_BEDROCK)

    # ══════════════════════════════════════════════════════════════
    # BEDROCK MODEL SETTINGS
    # ══════════════════════════════════════════════════════════════
    
    # BEDROCK_MODEL_ID: The exact model identifier for Claude on Bedrock.
    # Format: us.anthropic.<model-name>
    # 
    # Available Claude models on Bedrock (as of 2025):
    #   - us.anthropic.claude-sonnet-4-20250514   ← RECOMMENDED (best quality-to-cost ratio)
    #   - us.anthropic.claude-haiku-4-5-20251001  ← Faster & cheaper, slightly less detailed
    #   - us.anthropic.claude-opus-4-20250918     ← Most powerful, but slower & more expensive
    #
    # WHEN TO CHANGE:
    #   - If summaries feel shallow → try Opus
    #   - If you want faster/cheaper results → try Haiku
    #   - If you're just testing → Haiku saves money
    #
    # To check which models you have access to: AWS Console → Bedrock → Model Access
    BEDROCK_MODEL_ID: str = os.getenv(
        "BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514"
    )

    # MAX_TOKENS: Maximum number of tokens (≈ words) the LLM can generate in its response.
    # 4096 tokens ≈ ~3000 words — enough for most video summaries.
    # 
    # WHEN TO CHANGE:
    #   - If you notice summaries getting cut off mid-sentence → increase to 8192
    #   - For very long videos (3+ hours) → set to 8192
    # Note: More tokens = slightly higher cost per API call.
    MAX_TOKENS: int = 4096

    # TEMPERATURE: Controls how "creative" vs "focused" the LLM output is.
    # Range: 0.0 to 1.0
    #   - 0.0 = Very deterministic, factual, consistent (same input → same output)
    #   - 0.3 = Slightly flexible but still focused ← WE USE THIS
    #   - 0.7 = Balanced creativity
    #   - 1.0 = Very creative, varied, sometimes unpredictable
    # 
    # For summaries, you want low temperature (accuracy over creativity).
    # If you ever use this for creative content, bump it to 0.7-0.8.
    TEMPERATURE: float = 0.3

    # ══════════════════════════════════════════════════════════════
    # NOTION SETTINGS
    # ══════════════════════════════════════════════════════════════
    
    # NOTION_TOKEN: Your Notion integration's "Internal Integration Token"
    # 
    # HOW TO GET IT:
    #   1. Go to https://www.notion.so/my-integrations
    #   2. Click "New integration"
    #   3. Give it a name like "TubeWise"
    #   4. Select your workspace
    #   5. Copy the token (looks like: "secret_abc123xyz...")
    # 
    # ⚠️ CRITICAL STEP MOST PEOPLE MISS:
    # After creating the integration, you MUST share your target Notion page with it.
    # How: Open the page in Notion → click "..." menu → Connections → Add your integration
    # Without this, you'll get a 401/403 error when trying to create pages.
    NOTION_TOKEN: str = os.getenv("NOTION_TOKEN", "")

    # NOTION_PARENT_PAGE_ID: The Notion page where all video summaries will be created.
    # Each video summary becomes a child/sub-page under this parent page.
    # Think of it like a folder — this is the folder, each summary is a file inside it.
    # 
    # HOW TO FIND THE PAGE ID:
    #   1. Open the page in Notion (in browser)
    #   2. Look at the URL: https://www.notion.so/Your-Page-Title-abc123def456789...
    #   3. The 32-character hex string at the END of the URL is your page ID
    #   4. Example: "abc123def456789012345678901234ab"
    #   5. Copy it with or without dashes — both work
    NOTION_PARENT_PAGE_ID: str = os.getenv("NOTION_PARENT_PAGE_ID", "")

    # ══════════════════════════════════════════════════════════════
    # TRANSCRIPT SETTINGS
    # ══════════════════════════════════════════════════════════════
    
    # TRANSCRIPT_LANGUAGE: Default language for YouTube transcript extraction.
    # Uses ISO 639-1 language codes:
    #   "en" = English, "hi" = Hindi, "es" = Spanish, "fr" = French,
    #   "de" = German, "ja" = Japanese, "ko" = Korean, etc.
    # 
    # If the video doesn't have captions in this language, the agent will:
    #   1. Try to find manually created subtitles in this language
    #   2. Try auto-generated subtitles in this language
    #   3. Find ANY available transcript and auto-translate it
    # So even if the video is in another language, it'll still work (with some quality loss).
    TRANSCRIPT_LANGUAGE: str = os.getenv("TRANSCRIPT_LANGUAGE", "en")

    # ══════════════════════════════════════════════════════════════
    # CHUNKING SETTINGS (for long videos)
    # ══════════════════════════════════════════════════════════════
    # 
    # WHY CHUNKING?
    # When a video transcript is very long (e.g., a 3-hour conference talk),
    # even though Claude supports 200K tokens, quality degrades with very long inputs.
    # It's more reliable to:
    #   1. Split the transcript into smaller pieces (chunks)
    #   2. Summarize each chunk separately (the "map" step)
    #   3. Combine all summaries into one final output (the "reduce" step)
    # This is called the "map-reduce" strategy — same concept as in distributed computing.
    
    # CHUNK_SIZE: How many characters per chunk.
    # 12000 chars ≈ ~3000 tokens ≈ about 8-10 minutes of speech.
    # 
    # WHEN TO CHANGE:
    #   - If chunk summaries feel disconnected from each other → increase to 16000-20000
    #   - If you're hitting token limits → decrease to 8000
    CHUNK_SIZE: int = 12000

    # CHUNK_OVERLAP: How many characters overlap between consecutive chunks.
    # This ensures we don't lose context at chunk boundaries.
    #
    # Example: If chunk 1 ends with "...and machine learning is important because"
    # and chunk 2 starts fresh, we'd lose that sentence. With 500 char overlap,
    # chunk 2 will also contain the end of chunk 1, preserving the context.
    #
    # WHEN TO CHANGE:
    #   - If you see ideas getting split awkwardly → increase to 800-1000
    #   - If processing is slow → decrease to 200 (minor quality trade-off)
    CHUNK_OVERLAP: int = 500

    # ══════════════════════════════════════════════════════════════
    # PROCESSING THRESHOLDS
    # ══════════════════════════════════════════════════════════════

    # WORD_THRESHOLD_SINGLE_SHOT: Transcripts under this word count use single-shot
    # summarization (entire transcript sent to Claude at once). Above this, the
    # map-reduce strategy is used (split → summarize each → combine).
    # 40K words ≈ 50-60K tokens. Claude handles 200K, but quality is better below 50K.
    WORD_THRESHOLD_SINGLE_SHOT: int = int(os.getenv("WORD_THRESHOLD_SINGLE_SHOT", "40000"))

    # SUB_PAGE_WORD_THRESHOLD: Transcripts above this word count get a multi-page
    # Notion layout (parent + 3 sub-pages). Below this, everything fits on one page.
    # ~2500 words ≈ 15 minutes of speech.
    SUB_PAGE_WORD_THRESHOLD: int = int(os.getenv("SUB_PAGE_WORD_THRESHOLD", "2500"))

    # NOTION_BLOCK_BATCH_SIZE: Notion API limits blocks per request. Default is 100.
    NOTION_BLOCK_BATCH_SIZE: int = int(os.getenv("NOTION_BLOCK_BATCH_SIZE", "100"))

    # BEDROCK_READ_TIMEOUT: Seconds to wait for Claude's response. Opus needs up to 5 min
    # for very long transcripts.
    BEDROCK_READ_TIMEOUT: int = int(os.getenv("BEDROCK_READ_TIMEOUT", "300"))

    # FILENAME_MAX_LENGTH: Maximum characters for saved summary filenames.
    FILENAME_MAX_LENGTH: int = int(os.getenv("FILENAME_MAX_LENGTH", "80"))

    # ══════════════════════════════════════════════════════════════
    # ASYNC QUEUE SETTINGS
    # ══════════════════════════════════════════════════════════════

    # Path to the SQLite database for the async job queue
    QUEUE_DB_PATH: str = os.getenv(
        "QUEUE_DB_PATH", str(Path.home() / ".tubewise" / "queue.db")
    )

    # Default number of parallel workers for async processing
    DEFAULT_WORKER_COUNT: int = int(os.getenv("DEFAULT_WORKER_COUNT", "2"))

    # Log file path for debug logs and worker output
    LOG_FILE_PATH: str = os.getenv(
        "LOG_FILE_PATH", str(Path.home() / ".tubewise" / "tubewise.log")
    )

    # Log level for console output (DEBUG, INFO, WARNING, ERROR)
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def validate(cls, skip_notion: bool = False) -> list[str]:
        """
        Validate that all required configuration values are present.
        
        This runs BEFORE any processing starts, so you get clear error messages
        upfront instead of cryptic failures halfway through processing.
        
        Args:
            skip_notion: If True, skip Notion validation.
                         Used when running with --no-notion flag (terminal-only output).
        
        Returns:
            List of error messages. Empty list means everything is configured correctly.
        """
        errors = []

        # ── Check AWS region is set ──
        # We don't strictly validate AWS credentials here because boto3 has its own
        # credential resolution chain. But we do need a region to know where to call.
        if not cls.AWS_REGION:
            errors.append("AWS_REGION is not set")

        # ── Check Notion settings (skip if user doesn't want Notion output) ──
        if not skip_notion:
            if not cls.NOTION_TOKEN:
                errors.append(
                    "NOTION_TOKEN is not set. Get it from https://www.notion.so/my-integrations"
                )
            if not cls.NOTION_PARENT_PAGE_ID:
                errors.append(
                    "NOTION_PARENT_PAGE_ID is not set. Copy the page ID from your Notion page URL"
                )

        return errors

    @classmethod
    def print_config(cls):
        """
        Print current configuration with secrets masked.
        Useful for debugging — shows what's set vs what's missing
        without exposing sensitive values.
        
        Run with: python agent.py --show-config
        """
        print("\n📋 Current Configuration:")
        # Show which .env file is being used
        _home_env = Path.home() / ".tubewise" / ".env"
        _project_env = Path(__file__).parent / ".env"
        if _home_env.exists():
            print(f"   Config file:  {_home_env}")
        elif _project_env.exists():
            print(f"   Config file:  {_project_env}")
        else:
            print(f"   Config file:  ⚠️  No .env found! Expected at {_home_env}")
        print(f"   AWS Region:     {cls.AWS_REGION}")
        print(f"   Auth Method:    {'🔑 Bearer Token' if cls.is_bearer_token_auth() else '🔐 IAM Access Keys'}")
        print(f"   Bedrock Model:  {cls.BEDROCK_MODEL_ID}")
        print(f"   Notion Token:   {'✅ Set' if cls.NOTION_TOKEN else '❌ Missing'}")
        print(f"   Notion Page ID: {'✅ Set' if cls.NOTION_PARENT_PAGE_ID else '❌ Missing'}")
        print(f"   Language:       {cls.TRANSCRIPT_LANGUAGE}")
        print()