"""
summarizer.py — TubeWise Summarization Engine (LangChain + AWS Bedrock)
========================================================================
This is the "brain" of TubeWise. It takes the video transcript
and sends it to Claude on AWS Bedrock via LangChain to generate
a structured summary.

HOW IT WORKS:
1. Initializes a connection to Claude via AWS Bedrock (using LangChain's ChatBedrock)
2. Decides whether to use single-shot or map-reduce strategy based on transcript length
3. Sends the transcript to Claude with the appropriate prompt
4. Returns the raw summary text (which gets parsed later by notion_publisher.py)

TWO STRATEGIES:
- Short videos (<40K words): Send entire transcript at once → get complete summary
- Long videos (>40K words): Split into chunks → summarize each → combine results

KEY CONCEPTS FOR BEGINNERS:
- LangChain: A Python framework that makes it easy to build LLM-powered apps.
  It provides connectors for various LLMs (OpenAI, Bedrock, Ollama, etc.)
  so you don't have to write raw API calls yourself.
  
- AWS Bedrock: AWS's managed service for accessing foundation models (LLMs).
  Instead of calling Anthropic's API directly, you call it through AWS.
  Benefits: uses your existing AWS billing, IAM security, VPC endpoints, etc.
  
- ChatBedrock: LangChain's connector specifically for AWS Bedrock.
  It wraps boto3 (AWS SDK) calls in a clean interface.

CUSTOMIZATION:
- Change the model by updating Config.BEDROCK_MODEL_ID
- Adjust the 40K word threshold if you want to force chunking earlier/later
- The prompts used here come from prompts.py — edit there to change output
"""

from __future__ import annotations

import logging

from langchain_aws import ChatBedrock
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_text_splitters import RecursiveCharacterTextSplitter
import boto3
import botocore
from botocore.config import Config as BotoConfig

from config import Config
from models import ContentInfo
from prompts import (
    SYSTEM_PROMPT,
    SUMMARY_PROMPT,
    CHUNK_MAP_PROMPT,
    CHUNK_REDUCE_PROMPT,
)

logger = logging.getLogger("tubewise.summarizer")

# Keep backward compat import path
VideoInfo = ContentInfo


# ══════════════════════════════════════════════════════════════
# LLM INITIALIZATION
# ══════════════════════════════════════════════════════════════

def _create_bedrock_client_with_bearer_token():
    """
    Create a boto3 Bedrock Runtime client using Bearer Token authentication.
    
    WHY THIS EXISTS:
    When you generate an API key from the Bedrock Console, AWS gives you a
    Bearer Token (AWS_BEARER_TOKEN_BEDROCK). This uses a different auth mechanism
    than standard IAM Access Key + Secret Key.
    
    Standard IAM auth: boto3 uses SigV4 signing (Access Key + Secret Key)
    Bearer Token auth: boto3 sends the token in the Authorization header
    
    LangChain's ChatBedrock doesn't natively support bearer tokens, so we
    create a custom boto3 client with bearer token auth and pass it to ChatBedrock.
    
    HOW BEARER TOKEN AUTH WORKS IN BOTO3:
    1. We create a boto3 Session with no credentials (anonymous)
    2. We create a bedrock-runtime client from that session
    3. We register an event handler that injects the Bearer Token
       into the Authorization header of every API request
    4. We pass this pre-configured client to LangChain's ChatBedrock
    
    Returns:
        boto3 bedrock-runtime client configured with bearer token auth
    """
    # ── Create a boto3 session without any IAM credentials ──
    # We pass empty strings because we don't want boto3 to use IAM auth.
    # The bearer token will handle authentication instead.
    session = boto3.Session(
        region_name=Config.AWS_REGION,
        aws_access_key_id="",          # Empty — not using IAM keys
        aws_secret_access_key="",      # Empty — not using IAM keys
    )

    # ── Create the Bedrock Runtime client ──
    # "bedrock-runtime" is the service for invoking models (InvokeModel API)
    # "bedrock" (without -runtime) is for management operations (listing models, etc.)
    client = session.client(
        "bedrock-runtime",
        region_name=Config.AWS_REGION,
        config=BotoConfig(
            signature_version=botocore.UNSIGNED,
            read_timeout=Config.BEDROCK_READ_TIMEOUT,
            connect_timeout=10,
            retries={"max_attempts": 2},  # Retry once on transient failures
        ),
    )

    # ── Register event handler to inject Bearer Token into every request ──
    # boto3 has an event system where you can hook into the request lifecycle.
    # "before-sign.bedrock-runtime.*" fires before every Bedrock API request is signed.
    # Our handler replaces the Authorization header with the Bearer Token.
    token = Config.AWS_BEARER_TOKEN_BEDROCK
    
    def _inject_bearer_token(request, **kwargs):
        """
        Event handler that adds the Bearer Token to the HTTP request headers.
        This runs automatically before every API call to Bedrock.
        """
        request.headers["Authorization"] = f"Bearer {token}"
    
    # Register the handler for all bedrock-runtime API calls
    client.meta.events.register(
        "before-sign.bedrock-runtime.*",
        _inject_bearer_token,
    )

    return client


def get_llm() -> ChatBedrock:
    """
    Initialize and return the Bedrock LLM client.
    
    AUTHENTICATION FLOW:
    1. Check if Bearer Token is set (AWS_BEARER_TOKEN_BEDROCK in .env)
       → If yes: Create a custom boto3 client with bearer token auth
       → If no:  Let LangChain use standard IAM credentials (env vars / ~/.aws/credentials)
    
    2. Create ChatBedrock instance with the appropriate auth method
    
    This auto-detection means you just set the right env var in .env
    and the code figures out which auth to use. No code changes needed
    when switching between auth methods.
    
    Returns:
        ChatBedrock instance ready to process prompts
    
    TROUBLESHOOTING:
    - "AccessDeniedException" → Token expired or wrong permissions
    - "UnrecognizedClientException" → Bearer token format is wrong
    - "ResourceNotFoundException" → The model isn't available in your region
    - "ValidationException" → Check the model ID format
    """
    
    if Config.is_bearer_token_auth():
        # ── BEARER TOKEN AUTH ──
        # Create a custom boto3 client with the bearer token injected
        # and pass it directly to ChatBedrock
        logger.debug("Using Bearer Token authentication")
        bedrock_client = _create_bedrock_client_with_bearer_token()
        
        return ChatBedrock(
            # model_id: Which Claude model to use on Bedrock
            model_id=Config.BEDROCK_MODEL_ID,
            
            # region_name: Which AWS region to call
            region_name=Config.AWS_REGION,
            
            # client: Pass our custom boto3 client with bearer token auth
            # This tells LangChain "don't create your own client, use this one"
            client=bedrock_client,
            
            # model_kwargs: Additional parameters passed to Claude
            model_kwargs={
                "max_tokens": Config.MAX_TOKENS,    # Max length of Claude's response
                "temperature": Config.TEMPERATURE,   # Creativity level (0.3 = focused)
            },
        )
    else:
        # ── STANDARD IAM AUTH (fallback) ──
        # Let LangChain create the boto3 client internally using standard
        # IAM credential chain (env vars → ~/.aws/credentials → IAM role)
        logger.debug("Using IAM Access Key authentication")
        
        return ChatBedrock(
            model_id=Config.BEDROCK_MODEL_ID,
            region_name=Config.AWS_REGION,
            # config: Set generous timeout for large transcript processing
            # Opus 4.6 can take 2-3 minutes for long prompts
            config=BotoConfig(
                read_timeout=Config.BEDROCK_READ_TIMEOUT,
                connect_timeout=10,
                retries={"max_attempts": 2},
            ),
            model_kwargs={
                "max_tokens": Config.MAX_TOKENS,
                "temperature": Config.TEMPERATURE,
            },
        )


# ══════════════════════════════════════════════════════════════
# STRATEGY 1: SHORT VIDEO (Single-Shot Summarization)
# ══════════════════════════════════════════════════════════════

def summarize_short(llm: ChatBedrock, video: VideoInfo) -> str:
    """
    Summarize a short/medium video in a single LLM call.
    
    HOW IT WORKS:
    - Sends the ENTIRE transcript to Claude in one request
    - Claude reads the full transcript and generates the complete summary
    - Best quality because Claude has full context
    
    WHEN THIS IS USED:
    - Videos under ~40K words (roughly under 3 hours)
    - Claude Sonnet handles 200K tokens, so most videos fit easily
    
    Args:
        llm:   The ChatBedrock LLM client (from get_llm())
        video: VideoInfo object with transcript and metadata
    
    Returns:
        Raw summary text from Claude (will be parsed later by notion_publisher)
    """
    # ── Build the prompt by filling in the placeholders ──
    # The .format() method replaces {title}, {channel}, etc. with actual values
    prompt = SUMMARY_PROMPT.format(
        title=video.title,
        channel=video.channel,
        duration=video.duration_formatted,
        transcript=video.transcript,
    )

    # ── Create the message list ──
    # LangChain uses a chat-style interface with messages:
    # - SystemMessage: Tells Claude WHO it is (its role, personality)
    # - HumanMessage: The actual question/prompt we want answered
    # This mirrors how ChatGPT/Claude conversations work internally.
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),   # "You are an expert content analyst..."
        HumanMessage(content=prompt),            # "Here's the transcript, summarize it..."
    ]

    # ── Send to Claude via Bedrock and get response ──
    # .invoke() sends the request, waits for Claude to process, and returns the response
    # response.content contains the actual text output from Claude
    response = llm.invoke(messages)
    return response.content


# ══════════════════════════════════════════════════════════════
# STRATEGY 2: LONG VIDEO (Map-Reduce Summarization)
# ══════════════════════════════════════════════════════════════

def summarize_long(llm: ChatBedrock, video: VideoInfo) -> str:
    """
    Summarize a long video using the map-reduce strategy.
    
    WHY MAP-REDUCE?
    Even though Claude can handle 200K tokens, very long transcripts can lead to:
    - Some details getting lost in the middle (the "lost in the middle" problem)
    - Less focused summaries
    - Higher latency (longer wait times)
    
    Map-reduce fixes this by processing the video in manageable pieces.
    
    THE STRATEGY:
    ┌─────────────────────────────────────────────────────────┐
    │  STEP 1: SPLIT (divide transcript into chunks)          │
    │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐         │
    │  │Chunk1│ │Chunk2│ │Chunk3│ │Chunk4│ │Chunk5│         │
    │  └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘         │
    │     │        │        │        │        │               │
    │  STEP 2: MAP (summarize each chunk separately)          │
    │     ▼        ▼        ▼        ▼        ▼               │
    │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐         │
    │  │Sum 1 │ │Sum 2 │ │Sum 3 │ │Sum 4 │ │Sum 5 │         │
    │  └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘         │
    │     │        │        │        │        │               │
    │  STEP 3: REDUCE (combine all summaries into one)        │
    │     └────────┴────────┴────────┴────────┘               │
    │                       │                                  │
    │                       ▼                                  │
    │              ┌─────────────────┐                         │
    │              │  Final Summary  │                         │
    │              └─────────────────┘                         │
    └─────────────────────────────────────────────────────────┘
    
    Args:
        llm:   The ChatBedrock LLM client
        video: VideoInfo object with transcript and metadata
    
    Returns:
        Raw summary text from Claude (combined from all chunks)
    """
    
    # ══════════════════════════════════════════════
    # STEP 1: SPLIT the transcript into chunks
    # ══════════════════════════════════════════════
    # RecursiveCharacterTextSplitter tries to split at natural boundaries:
    #   First try: Split at paragraph breaks (\n\n)
    #   If too big: Split at line breaks (\n)
    #   If still too big: Split at sentence endings (. )
    #   Last resort: Split at spaces ( )
    #   Emergency: Split at character level ("")
    # This ensures chunks end at natural points, not mid-sentence.
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=Config.CHUNK_SIZE,        # Max characters per chunk (12000)
        chunk_overlap=Config.CHUNK_OVERLAP,  # Overlap between chunks (500)
        separators=["\n\n", "\n", ". ", " ", ""],  # Priority order for split points
    )
    
    # .split_text() returns a list of strings, each one a chunk of the transcript
    chunks = splitter.split_text(video.transcript)
    total_chunks = len(chunks)

    logger.info(f"   📦 Split into {total_chunks} chunks for processing")

    # ══════════════════════════════════════════════
    # STEP 2: MAP — summarize each chunk individually
    # ══════════════════════════════════════════════
    # We send each chunk to Claude with the CHUNK_MAP_PROMPT
    # and collect the individual summaries.
    chunk_summaries = []
    
    for i, chunk in enumerate(chunks):
        logger.info(f"   🔄 Processing chunk {i + 1}/{total_chunks}...")

        # Build the prompt for this specific chunk
        # {chunk_number} and {total_chunks} help Claude understand this is
        # part of a larger video, so it doesn't treat it as a complete piece
        prompt = CHUNK_MAP_PROMPT.format(
            title=video.title,
            chunk_number=i + 1,
            total_chunks=total_chunks,
            chunk=chunk,
        )

        # Send to Claude
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        response = llm.invoke(messages)
        
        # Store the summary with a section label for the reduce step
        chunk_summaries.append(f"--- Section {i + 1} ---\n{response.content}")

    # ══════════════════════════════════════════════
    # STEP 3: REDUCE — combine all chunk summaries
    # ══════════════════════════════════════════════
    # Now we take ALL the chunk summaries and send them to Claude
    # with the CHUNK_REDUCE_PROMPT, which asks it to merge everything
    # into one coherent, well-structured final summary.
    logger.info("   🔗 Combining all sections into final summary...")

    # Join all chunk summaries into one big text
    combined = "\n\n".join(chunk_summaries)

    # Build the reduce prompt
    reduce_prompt = CHUNK_REDUCE_PROMPT.format(
        title=video.title,
        channel=video.channel,
        duration=video.duration_formatted,
        combined_summaries=combined,
    )

    # Send to Claude for final combination
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=reduce_prompt),
    ]

    response = llm.invoke(messages)
    return response.content


# ══════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════

def generate_summary(video: VideoInfo) -> str:
    """
    Main entry point for summarization. Called by agent.py.
    
    This function:
    1. Initializes the LLM connection to Bedrock
    2. Checks the transcript length
    3. Automatically picks the best strategy (short vs long)
    4. Returns the raw summary text
    
    The caller (agent.py) then passes this text to notion_publisher.py
    for formatting and publishing.
    
    Decision logic:
    - Under 40,000 words → single-shot (faster, higher quality)
    - Over 40,000 words  → map-reduce (handles any length)
    
    WHY 40K WORDS?
    - 40K words ≈ 50K-60K tokens
    - Claude Sonnet handles 200K tokens, so 40K words fits easily
    - But empirically, summaries are better when the input is <50K tokens
    - For very long transcripts, map-reduce produces more thorough results
    
    Args:
        video: VideoInfo object with transcript and metadata
    
    Returns:
        Raw summary text from Claude (markdown-formatted sections)
    """
    # ── Initialize the LLM ──
    logger.info("\n🤖 Initializing Claude on AWS Bedrock...")
    llm = get_llm()

    # ── Check transcript length and pick strategy ──
    word_count = video.word_count
    logger.info(f"📊 Transcript: {word_count} words")

    if word_count < Config.WORD_THRESHOLD_SINGLE_SHOT:
        logger.info("⚡ Using single-shot summarization...")
        return summarize_short(llm, video)
    else:
        logger.info("📚 Long video detected — using map-reduce strategy...")
        return summarize_long(llm, video)