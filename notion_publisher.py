"""
notion_publisher.py — TubeWise Notion Page Creator & Formatter
===============================================================
This module takes the raw summary text from Claude and creates a beautifully
formatted Notion page with headings, callouts, toggles, quotes, and more.

HOW IT WORKS:
1. Parse the raw summary into sections (SUMMARY, KEY_TAKEAWAYS, etc.)
2. Convert each section into Notion "blocks" (the building units of Notion pages)
3. Create a new page under your parent page via the Notion API
4. Append all blocks to the page

NOTION API BASICS FOR BEGINNERS:
- Notion's API treats everything as "blocks" — paragraphs, headings, lists, etc.
- Each block is a JSON object with a specific structure
- To create a page, you: (1) create the page, (2) add blocks to it
- The API limits you to 100 blocks per request, so we batch if needed

BLOCK TYPES USED IN THIS MODULE:
- heading_2, heading_3  → Section titles
- paragraph             → Regular text
- bulleted_list_item    → Bullet points
- numbered_list_item    → Numbered lists (for takeaways)
- callout               → Highlighted info boxes with emoji icons
- quote                 → Indented quote blocks (for notable quotes)
- toggle                → Expandable/collapsible sections (for topics)
- code                  → Code blocks (for Mermaid diagrams)
- bookmark              → Embedded link preview (for YouTube URL)
- divider               → Horizontal line separator

CUSTOMIZATION:
- Change emoji icons by editing the emoji parameters in block functions
- Change callout colors by modifying the "color" parameter
- Add new block types by creating new helper functions
- Modify parse_summary_sections() to handle additional sections
"""

from __future__ import annotations

import re
import logging
from typing import Any

from notion_client import Client
from config import Config

logger = logging.getLogger("tubewise.notion")

# Type alias for Notion block dictionaries
NotionBlock = dict[str, Any]


# ══════════════════════════════════════════════════════════════
# NOTION CLIENT INITIALIZATION
# ══════════════════════════════════════════════════════════════

def get_notion_client() -> Client:
    """
    Create and return a Notion API client.
    
    Uses the Internal Integration Token from your .env file.
    This client handles all HTTP requests to Notion's REST API.
    
    Returns:
        notion_client.Client instance
    
    TROUBLESHOOTING:
    - 401 Unauthorized → Your token is wrong or expired
    - 403 Forbidden → You haven't shared the page with your integration
    - 404 Not Found → The parent page ID is wrong
    """
    return Client(auth=Config.NOTION_TOKEN)


# ══════════════════════════════════════════════════════════════
# SECTION PARSER
# ══════════════════════════════════════════════════════════════

def parse_summary_sections(raw_summary: str) -> dict:
    """
    Parse Claude's raw output into named sections.
    
    Claude returns markdown-formatted text with ### headers for each section.
    This function splits that text into a dictionary where:
      key = section name (e.g., "summary", "key_takeaways")
      value = the text content of that section
    
    EXAMPLE INPUT:
        ### SUMMARY
        This video covers...
        
        ### KEY_TAKEAWAYS
        1. First takeaway
        2. Second takeaway
    
    EXAMPLE OUTPUT:
        {
            "summary": "This video covers...",
            "key_takeaways": "1. First takeaway\n2. Second takeaway",
            ...
        }
    
    Args:
        raw_summary: The complete text output from Claude
    
    Returns:
        Dictionary mapping section names to their text content
    """
    # Initialize all expected sections with empty strings
    # If Claude's output is missing a section, it'll just be empty (no crash)
    sections = {
        "summary": "",
        "key_takeaways": "",
        "topics_covered": "",
        "concept_explanations": "",
        "action_items": "",
        "diagram_description": "",
        "notable_quotes": "",
        "resources_mentioned": "",
    }

    # State variables for tracking which section we're currently in
    current_section = None    # The dictionary key of the current section
    current_content = []      # Lines of text belonging to the current section

    # Process line by line
    for line in raw_summary.split("\n"):
        # Check if this line is a section header (starts with ###)
        header_match = re.match(r"^###\s*(.+)", line.strip())
        
        if header_match:
            # ── We found a new section header ──
            
            # First, save any content we've collected for the previous section
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            
            # Map the header text to one of our expected section keys
            # We normalize to uppercase and replace spaces with underscores
            # So "### Key Takeaways" becomes "KEY_TAKEAWAYS" which matches "key_takeaways"
            header = header_match.group(1).strip().upper().replace(" ", "_")
            
            # Find the matching section key
            for key in sections:
                if key.upper() in header or header in key.upper():
                    current_section = key
                    current_content = []
                    break
            else:
                # Header didn't match any known section — skip it
                current_section = None
                current_content = []
        elif current_section:
            # ── We're inside a section — collect the content ──
            current_content.append(line)

    # Don't forget to save the last section!
    if current_section:
        sections[current_section] = "\n".join(current_content).strip()

    return sections


# ══════════════════════════════════════════════════════════════
# NOTION BLOCK BUILDER FUNCTIONS
# ══════════════════════════════════════════════════════════════
# Each function below creates ONE type of Notion block.
# Blocks are JSON objects that Notion's API understands.
#
# These are building blocks (pun intended) — the main function
# build_notion_blocks() uses these to assemble the full page.
#
# IMPORTANT: Notion has a 2000-character limit per rich_text item.
# The safe_rich_text() helper automatically splits long text into
# multiple rich_text items so we never hit this limit.
# ══════════════════════════════════════════════════════════════

# Notion's hard limit for a single rich text item
NOTION_TEXT_LIMIT = 2000


def _split_text(text: str, limit: int = NOTION_TEXT_LIMIT) -> list[str]:
    """
    Split text into chunks of at most `limit` characters.
    
    Tries to split at natural boundaries (sentence endings, spaces)
    rather than cutting mid-word.
    
    WHY THIS EXISTS:
    Notion's API rejects any rich_text item longer than 2000 characters.
    Claude sometimes generates long paragraphs, especially for detailed
    concept explanations. This function ensures we never hit that limit.
    
    Args:
        text:  The text to split
        limit: Maximum characters per chunk (default: 2000)
    
    Returns:
        List of text chunks, each ≤ limit characters
    """
    if len(text) <= limit:
        return [text]
    
    chunks = []
    remaining = text
    
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        
        # Try to find a natural break point within the limit
        # Priority: sentence end (. ), then comma, then space
        chunk = remaining[:limit]
        
        # Look for last sentence break
        break_point = chunk.rfind(". ")
        if break_point == -1 or break_point < limit // 2:
            # No good sentence break — try comma
            break_point = chunk.rfind(", ")
        if break_point == -1 or break_point < limit // 2:
            # No good comma break — try space
            break_point = chunk.rfind(" ")
        if break_point == -1:
            # No space found at all — hard cut (rare, very long word)
            break_point = limit
        else:
            break_point += 1  # Include the space/period in this chunk
        
        chunks.append(remaining[:break_point])
        remaining = remaining[break_point:]
    
    return chunks


def safe_rich_text(content: str, bold: bool = False, italic: bool = False, code: bool = False, color: str = "default") -> list[dict]:
    """
    Create a LIST of Notion rich text objects, auto-splitting if content > 2000 chars.
    
    This is a drop-in replacement for rich_text() that handles the Notion limit.
    Instead of returning a single dict, it returns a list of dicts.
    
    Args:
        content: The text string (any length)
        bold, italic, code, color: Formatting options (applied to all chunks)
    
    Returns:
        List of rich text dicts, each ≤ 2000 characters
    """
    chunks = _split_text(content)
    return [
        {
            "type": "text",
            "text": {"content": chunk},
            "annotations": {
                "bold": bold,
                "italic": italic,
                "code": code,
                "color": color,
            },
        }
        for chunk in chunks
    ]


def rich_text(content: str, bold: bool = False, italic: bool = False, code: bool = False, color: str = "default") -> dict:
    """
    Create a single Notion "rich text" object — the smallest unit of text.
    
    ⚠️ WARNING: This creates ONE rich text item. If content > 2000 chars,
    Notion will reject it. Use safe_rich_text() instead when text length
    is unpredictable (e.g., LLM output).
    
    For headings and short labels, this is fine. For paragraph content
    from Claude, always use safe_rich_text().
    
    Args:
        content: The text string (should be ≤ 2000 chars)
        bold:    Make text bold
        italic:  Make text italic
        code:    Make text look like inline code
        color:   Text color
    
    Returns:
        Dict representing a single Notion rich text object
    """
    # Safety truncate — should never happen if safe_rich_text is used properly
    if len(content) > NOTION_TEXT_LIMIT:
        content = content[:NOTION_TEXT_LIMIT]
    
    return {
        "type": "text",
        "text": {"content": content},
        "annotations": {
            "bold": bold,
            "italic": italic,
            "code": code,
            "color": color,
        },
    }


def heading_block(text: str, level: int = 2) -> dict:
    """
    Create a heading block (like H1, H2, H3 in HTML).
    
    Notion supports three heading levels:
      - heading_1: Largest (page title level)
      - heading_2: Section headers ← we use this for main sections
      - heading_3: Subsection headers
    
    Args:
        text:  The heading text
        level: 1, 2, or 3 (default: 2)
    
    Returns:
        Dict representing a Notion heading block
    """
    key = f"heading_{level}"
    return {
        "object": "block",
        "type": key,
        key: {
            "rich_text": [rich_text(text)],
            "is_toggleable": False,  # Set to True if you want the heading to be collapsible
        },
    }


def paragraph_block(text: str, bold: bool = False, color: str = "default") -> dict:
    """
    Create a paragraph block — the most basic content block.
    Auto-splits text > 2000 chars into multiple rich_text items.
    
    Args:
        text:  The paragraph content (any length — auto-splits if needed)
        bold:  Make entire paragraph bold
        color: Text color
    
    Returns:
        Dict representing a Notion paragraph block
    """
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": safe_rich_text(text, bold=bold, color=color),
        },
    }


def bulleted_list_block(text: str, bold_prefix: str = None) -> dict:
    """
    Create a bulleted list item (• bullet point).
    Auto-splits long text to stay within Notion's 2000-char limit.
    
    Args:
        text:        The list item text
        bold_prefix: Optional bold text before the main text
    
    Returns:
        Dict representing a Notion bulleted list item block
    """
    items = []
    if bold_prefix:
        items.append(rich_text(bold_prefix[:NOTION_TEXT_LIMIT], bold=True))
        items.extend(safe_rich_text(text))
    else:
        items.extend(safe_rich_text(text))

    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": items,
        },
    }


def numbered_list_block(text: str) -> dict:
    """
    Create a numbered list item (1. 2. 3. etc.).
    Auto-splits long text to stay within Notion's 2000-char limit.
    
    Args:
        text: The list item text
    
    Returns:
        Dict representing a Notion numbered list item block
    """
    return {
        "object": "block",
        "type": "numbered_list_item",
        "numbered_list_item": {
            "rich_text": safe_rich_text(text),
        },
    }


def callout_block(text: str, emoji: str = "💡") -> dict:
    """
    Create a callout block — a highlighted box with an emoji icon.
    Auto-splits long text to stay within Notion's 2000-char limit.
    
    Args:
        text:  The callout content (any length)
        emoji: The emoji icon shown on the left side
    
    Returns:
        Dict representing a Notion callout block
    """
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": safe_rich_text(text),
            "icon": {"type": "emoji", "emoji": emoji},
            "color": "blue_background",
        },
    }


def quote_block(text: str) -> dict:
    """
    Create a quote block — indented text with a left border.
    Auto-splits long text to stay within Notion's 2000-char limit.
    
    Args:
        text: The quote text (auto-italicized)
    
    Returns:
        Dict representing a Notion quote block
    """
    return {
        "object": "block",
        "type": "quote",
        "quote": {
            "rich_text": safe_rich_text(text, italic=True),
        },
    }


def divider_block() -> dict:
    """
    Create a horizontal divider/separator line.
    Used between sections for visual separation.
    
    Returns:
        Dict representing a Notion divider block
    """
    return {"object": "block", "type": "divider", "divider": {}}


def code_block(code: str, language: str = "mermaid") -> dict:
    """
    Create a code block with syntax highlighting.
    Auto-splits long code to stay within Notion's 2000-char limit.
    
    Args:
        code:     The code content (any length)
        language: Programming language for syntax highlighting
    
    Returns:
        Dict representing a Notion code block
    """
    return {
        "object": "block",
        "type": "code",
        "code": {
            "rich_text": safe_rich_text(code),
            "language": language,
        },
    }


def bookmark_block(url: str) -> dict:
    """
    Create a bookmark block — embeds a URL as a rich link preview.
    
    When you add a bookmark in Notion, it shows a preview card with
    the page title, description, and thumbnail. We use this for the
    original YouTube video link at the top of the summary page.
    
    Args:
        url: The URL to embed as a bookmark
    
    Returns:
        Dict representing a Notion bookmark block
    """
    return {
        "object": "block",
        "type": "bookmark",
        "bookmark": {"url": url},
    }


def toggle_block(title: str, children: list) -> dict:
    """
    Create a toggle (expandable/collapsible) block.
    
    Click the arrow to expand and see the content inside.
    Great for topics — keeps the page clean while still having all the detail.
    
    Example in Notion:
      ▶ 📌 Machine Learning Basics     ← collapsed (click to expand)
      ▼ 📌 Machine Learning Basics     ← expanded
          ML is a subset of AI that...   (child content)
    
    Args:
        title:    The toggle header text (always visible)
        children: List of block objects shown when expanded
    
    Returns:
        Dict representing a Notion toggle block
    """
    return {
        "object": "block",
        "type": "toggle",
        "toggle": {
            "rich_text": [rich_text(title, bold=True)],
            "children": children,  # Blocks shown when the toggle is expanded
        },
    }


# ══════════════════════════════════════════════════════════════
# TEXT PARSING HELPERS
# ══════════════════════════════════════════════════════════════
# These functions help extract structured data from Claude's
# free-form text output. Claude returns markdown-style text,
# and we need to parse it into individual items for Notion blocks.
# ══════════════════════════════════════════════════════════════


def parse_bullet_lines(text: str) -> list[str]:
    """
    Extract individual bullet points from text.
    
    Claude might format bullets in various ways:
      - Dash bullet
      * Asterisk bullet
      • Unicode bullet
      1. Numbered item
      2) Numbered with parenthesis
    
    This function handles all these formats and returns clean text.
    
    Args:
        text: Raw text containing bullet points
    
    Returns:
        List of cleaned bullet point strings
    """
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue  # Skip empty lines
        # Remove leading bullet markers: "1. ", "2) ", "- ", "* ", "• "
        cleaned = re.sub(r"^[\d]+[\.\)]\s*", "", line)   # Remove numbered prefixes
        cleaned = re.sub(r"^[-*•]\s*", "", cleaned)       # Remove bullet prefixes
        if cleaned:
            lines.append(cleaned)
    return lines


def parse_topic_entries(text: str) -> list[tuple[str, str]]:
    """
    Parse entries in "**Topic Name**: Description" format.
    
    Claude often formats topics, concepts, and resources like:
      - **Machine Learning**: A subset of AI that allows systems to learn...
      - **Docker**: Containerization tool used for...
    
    This function extracts the name and description separately,
    which lets us format them differently in Notion (bold name + regular description).
    
    Args:
        text: Raw text with **Name**: Description entries
    
    Returns:
        List of (name, description) tuples
    
    Example:
        Input:  "- **Docker**: A tool for containerization"
        Output: [("Docker", "A tool for containerization")]
    """
    entries = []
    current_topic = None    # Track the topic name we're building
    current_desc = []       # Track description lines (might span multiple lines)

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Try to match "**Topic Name**: Description" pattern
        # Also handles optional leading bullets (-, *, •)
        match = re.match(r"^[-*•]?\s*\*\*(.+?)\*\*[:\s-]*(.*)$", line)
        
        # Fallback: try "Topic Name: Description" without bold markers
        if not match:
            match = re.match(r"^[-*•]?\s*(.+?):\s+(.+)$", line)

        if match:
            # Found a new topic entry — save the previous one first
            if current_topic:
                entries.append((current_topic, " ".join(current_desc)))
            # Start tracking the new topic
            current_topic = match.group(1).strip()
            desc = match.group(2).strip() if match.group(2) else ""
            current_desc = [desc] if desc else []
        elif current_topic:
            # This line is a continuation of the current topic's description
            current_desc.append(line)

    # Don't forget to save the last topic!
    if current_topic:
        entries.append((current_topic, " ".join(current_desc)))

    return entries


# ══════════════════════════════════════════════════════════════
# PAGE BUILDER — Assembles all blocks into a complete page
# ══════════════════════════════════════════════════════════════

def build_notion_blocks(sections: dict, video_url: str, video_title: str, channel: str, duration: str) -> list:
    """
    Build the complete list of Notion blocks for the summary page.
    
    This is where the page layout is defined. Each section of the summary
    gets converted into the appropriate Notion block types.
    
    PAGE STRUCTURE:
    ┌─────────────────────────────────────┐
    │ 🎬 Callout: Channel, Duration, Link │  ← Video info at the top
    │ 📎 Bookmark: YouTube URL             │  ← Embedded video link
    │ ──────────────────────────────────── │
    │ 📝 Executive Summary                 │  ← Paragraphs
    │ ──────────────────────────────────── │
    │ 🎯 Key Takeaways                     │  ← Numbered list
    │ ──────────────────────────────────── │
    │ 📚 Topics Covered                    │  ← Toggle blocks (expandable)
    │ ──────────────────────────────────── │
    │ 💡 Concept Deep-Dive                 │  ← Callout blocks
    │ ──────────────────────────────────── │
    │ ✅ Action Items                       │  ← Bullet list with checkboxes
    │ ──────────────────────────────────── │
    │ 🗺️ Concept Map                       │  ← Mermaid code block + link
    │ ──────────────────────────────────── │
    │ 💬 Notable Quotes                    │  ← Quote blocks
    │ ──────────────────────────────────── │
    │ 🔗 Resources Mentioned               │  ← Bullet list with bold names
    └─────────────────────────────────────┘
    
    Args:
        sections:    Dict of parsed section content (from parse_summary_sections)
        video_url:   Original YouTube URL
        video_title: Video title
        channel:     Channel name
        duration:    Formatted duration string (e.g., "45m 30s")
    
    Returns:
        List of Notion block dicts, ready to be sent to the API
    
    CUSTOMIZATION:
    - Reorder sections by moving the block-building code blocks around
    - Remove sections by commenting out the relevant block
    - Add new sections by adding more heading + content block groups
    - Change icons by modifying the emoji parameters
    """
    blocks = []

    # ─────────────────────────────────────────────
    # SECTION: Video Information Header
    # A callout with video metadata + embedded bookmark link
    # ─────────────────────────────────────────────
    blocks.append(callout_block(
        f"📺 {channel}  •  ⏱️ {duration}  •  🔗 Watch the original video below",
        emoji="🎬",
    ))
    blocks.append(bookmark_block(video_url))  # Embedded YouTube link preview
    blocks.append(divider_block())

    # ─────────────────────────────────────────────
    # SECTION: Executive Summary
    # Regular paragraphs for the overview
    # ─────────────────────────────────────────────
    blocks.append(heading_block("📝 Executive Summary", level=2))
    summary_text = sections.get("summary", "No summary generated.")
    # Split by double newlines to create separate paragraphs
    for para in summary_text.split("\n\n"):
        para = para.strip()
        if para:
            blocks.append(paragraph_block(para))
    blocks.append(divider_block())

    # ─────────────────────────────────────────────
    # SECTION: Key Takeaways
    # Numbered list for clear priority/ordering
    # ─────────────────────────────────────────────
    blocks.append(heading_block("🎯 Key Takeaways", level=2))
    takeaways = parse_bullet_lines(sections.get("key_takeaways", ""))
    for item in takeaways:
        blocks.append(numbered_list_block(item))
    blocks.append(divider_block())

    # ─────────────────────────────────────────────
    # SECTION: Topics Covered
    # Toggle blocks so each topic is expandable
    # This keeps the page clean — users expand only what interests them
    # ─────────────────────────────────────────────
    blocks.append(heading_block("📚 Topics Covered", level=2))
    topics = parse_topic_entries(sections.get("topics_covered", ""))
    if topics:
        for topic_name, topic_desc in topics:
            # Each topic becomes a toggle: click to expand and see the description
            children = [paragraph_block(topic_desc)] if topic_desc else [paragraph_block("—")]
            blocks.append(toggle_block(f"📌 {topic_name}", children))
    else:
        # Fallback: if parsing failed, just render as simple bullets
        for line in parse_bullet_lines(sections.get("topics_covered", "")):
            blocks.append(bulleted_list_block(line))
    blocks.append(divider_block())

    # ─────────────────────────────────────────────
    # SECTION: Concept Explanations
    # Callout blocks with brain emoji — visually distinct from regular text
    # ─────────────────────────────────────────────
    blocks.append(heading_block("💡 Concept Deep-Dive", level=2))
    concepts = parse_topic_entries(sections.get("concept_explanations", ""))
    if concepts:
        for concept_name, concept_desc in concepts:
            # Each concept gets its own highlighted callout box
            blocks.append(callout_block(f"{concept_name}\n\n{concept_desc}", emoji="🧠"))
    else:
        # Fallback: render as callouts without name/desc separation
        for line in parse_bullet_lines(sections.get("concept_explanations", "")):
            blocks.append(callout_block(line, emoji="🧠"))
    blocks.append(divider_block())

    # ─────────────────────────────────────────────
    # SECTION: Action Items
    # Bullet points with checkbox emoji (☐) for a task-list feel
    # Note: These aren't actual Notion checkboxes (to_do blocks),
    # because we want them as regular text, not interactive checkboxes.
    # If you want real checkboxes, change bulleted_list_block to a to_do block.
    # ─────────────────────────────────────────────
    blocks.append(heading_block("✅ Action Items", level=2))
    actions = parse_bullet_lines(sections.get("action_items", ""))
    for item in actions:
        blocks.append(bulleted_list_block(f"☐ {item}"))
    blocks.append(divider_block())

    # ─────────────────────────────────────────────
    # SECTION: Concept Map (Mermaid Diagram)
    # A code block with the Mermaid.js diagram syntax
    # Plus a link to mermaid.live where you can see it rendered
    # ─────────────────────────────────────────────
    blocks.append(heading_block("🗺️ Concept Map", level=2))
    diagram_text = sections.get("diagram_description", "")
    
    # Extract the Mermaid code from between ```mermaid and ``` markers
    mermaid_match = re.search(r"```mermaid\s*\n(.+?)```", diagram_text, re.DOTALL)
    
    if mermaid_match:
        mermaid_code = mermaid_match.group(1).strip()
        # Add the Mermaid code as a code block in Notion
        blocks.append(code_block(mermaid_code, language="mermaid"))

        # Generate a link to mermaid.live so users can see the rendered diagram
        # mermaid.live is a free web tool that renders Mermaid diagrams in the browser
        import urllib.parse
        import base64
        import json

        try:
            # mermaid.live expects the state as a base64-encoded JSON object in the URL
            mermaid_state = json.dumps({
                "code": mermaid_code,
                "mermaid": {"theme": "default"},
                "autoSync": True,
                "updateDiagram": True,
            })
            encoded = base64.urlsafe_b64encode(mermaid_state.encode()).decode()
            mermaid_url = f"https://mermaid.live/edit#base64:{encoded}"
            blocks.append(paragraph_block(f"🔗 View interactive diagram: {mermaid_url}"))
        except Exception:
            pass  # If URL generation fails, skip it — not critical
    else:
        # No Mermaid code found — just show the raw text
        blocks.append(paragraph_block(diagram_text if diagram_text else "No diagram generated."))
    blocks.append(divider_block())

    # ─────────────────────────────────────────────
    # SECTION: Notable Quotes
    # Quote blocks with italic text for visual distinction
    # ─────────────────────────────────────────────
    blocks.append(heading_block("💬 Notable Quotes", level=2))
    quotes = parse_bullet_lines(sections.get("notable_quotes", ""))
    for q in quotes:
        # Clean up any existing quote marks to avoid double-quoting
        q = q.strip('"').strip('\u201c').strip('\u201d')  # Remove " " " characters
        blocks.append(quote_block(f'"{q}"'))
    blocks.append(divider_block())

    # ─────────────────────────────────────────────
    # SECTION: Resources Mentioned
    # Bullet list with bold resource names and descriptions
    # ─────────────────────────────────────────────
    blocks.append(heading_block("🔗 Resources Mentioned", level=2))
    resources = parse_topic_entries(sections.get("resources_mentioned", ""))
    if resources:
        for res_name, res_desc in resources:
            # Bold resource name followed by description
            blocks.append(bulleted_list_block(f" {res_desc}", bold_prefix=f"{res_name}: "))
    else:
        # Fallback: render as simple bullets
        for line in parse_bullet_lines(sections.get("resources_mentioned", "")):
            blocks.append(bulleted_list_block(line))

    return blocks


# ══════════════════════════════════════════════════════════════
# MAIN ENTRY POINT — Creates the Notion page(s)
# ══════════════════════════════════════════════════════════════

# Threshold moved to Config.SUB_PAGE_WORD_THRESHOLD
# Kept as a comment for code archaeology


def _create_sub_page(client, parent_page_id: str, title: str, blocks: list) -> str:
    """
    Create a sub-page under a parent page and append blocks to it.
    
    This is a helper for building the multi-page structure.
    Each sub-page gets its own title and content blocks.
    
    Args:
        client:         Notion API client
        parent_page_id: ID of the parent page to nest under
        title:          Sub-page title (e.g., "📚 Topics & Deep-Dives")
        blocks:         List of Notion block dicts for this sub-page
    
    Returns:
        URL of the created sub-page
    """
    if not blocks:
        return ""
    
    page = client.pages.create(
        parent={"page_id": parent_page_id},
        properties={
            "title": {
                "title": [{"text": {"content": title}}]
            }
        },
        children=blocks[:100],
    )
    
    page_id = page["id"]
    
    # Append remaining blocks in batches of 100
    if len(blocks) > 100:
        remaining = blocks[100:]
        while remaining:
            batch = remaining[:100]
            remaining = remaining[100:]
            client.blocks.children.append(block_id=page_id, children=batch)
    
    return page["url"]


def _build_topics_deep_dives_blocks(sections: dict) -> list:
    """
    Build blocks for the 📚 Topics & Deep-Dives sub-page.
    Combines Topics Covered + Concept Explanations into one page.
    """
    blocks = []
    
    # ── Topics Covered ──
    blocks.append(heading_block("📚 Topics Covered", level=2))
    topics = parse_topic_entries(sections.get("topics_covered", ""))
    if topics:
        for topic_name, topic_desc in topics:
            children = [paragraph_block(topic_desc)] if topic_desc else [paragraph_block("—")]
            blocks.append(toggle_block(f"📌 {topic_name}", children))
    else:
        for line in parse_bullet_lines(sections.get("topics_covered", "")):
            blocks.append(bulleted_list_block(line))
    blocks.append(divider_block())
    
    # ── Concept Deep-Dives ──
    blocks.append(heading_block("💡 Concept Deep-Dive", level=2))
    concepts = parse_topic_entries(sections.get("concept_explanations", ""))
    if concepts:
        for concept_name, concept_desc in concepts:
            blocks.append(callout_block(f"{concept_name}\n\n{concept_desc}", emoji="🧠"))
    else:
        for line in parse_bullet_lines(sections.get("concept_explanations", "")):
            blocks.append(callout_block(line, emoji="🧠"))
    
    return blocks


def _build_actions_resources_blocks(sections: dict) -> list:
    """
    Build blocks for the ✅ Action Items & Resources sub-page.
    Combines Action Items + Resources Mentioned into one page.
    """
    blocks = []
    
    # ── Action Items ──
    blocks.append(heading_block("✅ Action Items", level=2))
    actions = parse_bullet_lines(sections.get("action_items", ""))
    for item in actions:
        blocks.append(bulleted_list_block(f"☐ {item}"))
    blocks.append(divider_block())
    
    # ── Resources Mentioned ──
    blocks.append(heading_block("🔗 Resources Mentioned", level=2))
    resources = parse_topic_entries(sections.get("resources_mentioned", ""))
    if resources:
        for res_name, res_desc in resources:
            blocks.append(bulleted_list_block(f" {res_desc}", bold_prefix=f"{res_name}: "))
    else:
        for line in parse_bullet_lines(sections.get("resources_mentioned", "")):
            blocks.append(bulleted_list_block(line))
    
    return blocks


def _build_quotes_diagram_blocks(sections: dict) -> list:
    """
    Build blocks for the 💬 Quotes & Concept Map sub-page.
    Combines Notable Quotes + Mermaid Concept Map into one page.
    """
    import urllib.parse
    import base64
    import json
    
    blocks = []
    
    # ── Notable Quotes ──
    blocks.append(heading_block("💬 Notable Quotes", level=2))
    quotes = parse_bullet_lines(sections.get("notable_quotes", ""))
    for q in quotes:
        q = q.strip('"').strip('\u201c').strip('\u201d')
        blocks.append(quote_block(f'"{q}"'))
    blocks.append(divider_block())
    
    # ── Concept Map (Mermaid) ──
    blocks.append(heading_block("🗺️ Concept Map", level=2))
    diagram_text = sections.get("diagram_description", "")
    mermaid_match = re.search(r"```mermaid\s*\n(.+?)```", diagram_text, re.DOTALL)
    
    if mermaid_match:
        mermaid_code = mermaid_match.group(1).strip()
        blocks.append(code_block(mermaid_code, language="mermaid"))
        try:
            mermaid_state = json.dumps({
                "code": mermaid_code,
                "mermaid": {"theme": "default"},
                "autoSync": True,
                "updateDiagram": True,
            })
            encoded = base64.urlsafe_b64encode(mermaid_state.encode()).decode()
            mermaid_url = f"https://mermaid.live/edit#base64:{encoded}"
            blocks.append(paragraph_block(f"🔗 View interactive diagram: {mermaid_url}"))
        except Exception:
            pass
    else:
        blocks.append(paragraph_block(diagram_text if diagram_text else "No diagram generated."))
    
    return blocks


def publish_to_notion(
    raw_summary: str,
    video_url: str,
    video_title: str,
    channel: str,
    duration: str,
    word_count: int = 0,
) -> str:
    """
    Main entry point: Parse LLM output and create formatted Notion page(s).
    
    STRUCTURE DECISION:
    - Short videos (< ~15 min / 2500 words): Everything on ONE page (same as before)
    - Longer videos: Parent page with essentials + sub-pages for heavy content
    
    LONG VIDEO STRUCTURE:
    ┌─────────────────────────────────────────────┐
    │ 📹 Video Title (Parent Page)                 │
    │ ├── 🎬 Video info callout + bookmark        │
    │ ├── 📝 Executive Summary                    │
    │ ├── 🎯 Key Takeaways                        │
    │ │                                            │
    │ ├── 📚 Topics & Deep-Dives (sub-page) ──────┤──▶ Topics + Concepts
    │ ├── ✅ Actions & Resources (sub-page) ──────┤──▶ Action Items + Resources
    │ └── 💬 Quotes & Concept Map (sub-page) ─────┤──▶ Quotes + Mermaid Diagram
    └─────────────────────────────────────────────┘
    
    Args:
        raw_summary:  The complete text output from Claude
        video_url:    Original YouTube URL
        video_title:  Video title (used as the Notion page title)
        channel:      Channel name
        duration:     Formatted duration string
        word_count:   Transcript word count (used to decide single vs multi-page)
    
    Returns:
        URL of the parent Notion page
    """
    logger.info("\n📤 Publishing to Notion...")
    
    # ── Step 1: Initialize and parse ──
    client = get_notion_client()
    sections = parse_summary_sections(raw_summary)
    
    # ── Step 2: Decide structure based on content length ──
    use_sub_pages = word_count > Config.SUB_PAGE_WORD_THRESHOLD
    
    if not use_sub_pages:
        # ════════════════════════════════════════
        # SHORT VIDEO → Single page (original behavior)
        # ════════════════════════════════════════
        logger.info("   📄 Creating single page (short video)...")
        blocks = build_notion_blocks(sections, video_url, video_title, channel, duration)
        
        page = client.pages.create(
            parent={"page_id": Config.NOTION_PARENT_PAGE_ID},
            properties={
                "title": {
                    "title": [{"text": {"content": f"📹 {video_title}"}}]
                }
            },
            children=blocks[:Config.NOTION_BLOCK_BATCH_SIZE],
        )
        
        page_id = page["id"]
        page_url = page["url"]
        
        # Append remaining blocks in batches
        if len(blocks) > Config.NOTION_BLOCK_BATCH_SIZE:
            remaining = blocks[Config.NOTION_BLOCK_BATCH_SIZE:]
            batch_num = 1
            while remaining:
                batch = remaining[:Config.NOTION_BLOCK_BATCH_SIZE]
                remaining = remaining[Config.NOTION_BLOCK_BATCH_SIZE:]
                logger.debug(f"Appending block batch {batch_num}")
                client.blocks.children.append(block_id=page_id, children=batch)
                batch_num += 1
        
        logger.info(f"   ✅ Page created: {page_url}")
        return page_url
    
    else:
        # ════════════════════════════════════════
        # LONGER VIDEO → Parent page + sub-pages
        # ════════════════════════════════════════
        logger.info("   📄 Creating parent page with sub-pages (longer video)...")
        
        # ── Build parent page blocks (essentials only) ──
        parent_blocks = []
        
        # Video info header
        parent_blocks.append(callout_block(
            f"📺 {channel}  •  ⏱️ {duration}  •  🔗 Watch the original video below",
            emoji="🎬",
        ))
        parent_blocks.append(bookmark_block(video_url))
        parent_blocks.append(divider_block())
        
        # Executive Summary (always on parent)
        parent_blocks.append(heading_block("📝 Executive Summary", level=2))
        summary_text = sections.get("summary", "No summary generated.")
        for para in summary_text.split("\n\n"):
            para = para.strip()
            if para:
                parent_blocks.append(paragraph_block(para))
        parent_blocks.append(divider_block())
        
        # Key Takeaways (always on parent)
        parent_blocks.append(heading_block("🎯 Key Takeaways", level=2))
        takeaways = parse_bullet_lines(sections.get("key_takeaways", ""))
        for item in takeaways:
            parent_blocks.append(numbered_list_block(item))
        parent_blocks.append(divider_block())
        
        # Navigation hint
        parent_blocks.append(callout_block(
            "👇 Detailed sections are organized in sub-pages below for easier navigation.",
            emoji="📂",
        ))
        
        # ── Create parent page ──
        page = client.pages.create(
            parent={"page_id": Config.NOTION_PARENT_PAGE_ID},
            properties={
                "title": {
                    "title": [{"text": {"content": f"📹 {video_title}"}}]
                }
            },
            children=parent_blocks[:100],
        )
        
        parent_page_id = page["id"]
        page_url = page["url"]
        
        # Append remaining parent blocks if needed
        if len(parent_blocks) > 100:
            remaining = parent_blocks[100:]
            while remaining:
                batch = remaining[:Config.NOTION_BLOCK_BATCH_SIZE]
                remaining = remaining[Config.NOTION_BLOCK_BATCH_SIZE:]
                client.blocks.children.append(block_id=parent_page_id, children=batch)
        
        # ── Create sub-pages under the parent ──
        
        # Sub-page 1: Topics & Deep-Dives
        topics_blocks = _build_topics_deep_dives_blocks(sections)
        if topics_blocks:
            logger.info("   📚 Creating sub-page: Topics & Deep-Dives...")
            _create_sub_page(client, parent_page_id, "📚 Topics & Deep-Dives", topics_blocks)
        
        # Sub-page 2: Action Items & Resources
        actions_blocks = _build_actions_resources_blocks(sections)
        if actions_blocks:
            logger.info("   ✅ Creating sub-page: Actions & Resources...")
            _create_sub_page(client, parent_page_id, "✅ Actions & Resources", actions_blocks)
        
        # Sub-page 3: Quotes & Concept Map
        quotes_blocks = _build_quotes_diagram_blocks(sections)
        if quotes_blocks:
            logger.info("   💬 Creating sub-page: Quotes & Concept Map...")
            _create_sub_page(client, parent_page_id, "💬 Quotes & Concept Map", quotes_blocks)
        
        logger.info(f"   ✅ Parent page created: {page_url}")
        logger.info(f"   📂 3 sub-pages created under it")
        return page_url


# ══════════════════════════════════════════════════════════════
# PLAYLIST INDEX PAGE
# ══════════════════════════════════════════════════════════════

def create_playlist_index_page(
    client: Client,
    playlist_title: str,
    video_pages: list[dict],
) -> str:
    """
    Create a Notion index page linking to all video summary pages in a playlist.

    Each entry shows the video title, status (success/failed), and a link
    to the Notion summary page.

    Args:
        client:         Notion API client
        playlist_title: Title of the YouTube playlist
        video_pages:    List of dicts with keys: title, url, notion_url, status

    Returns:
        URL of the created index page
    """
    blocks: list[NotionBlock] = []

    # Header
    succeeded = sum(1 for v in video_pages if v["status"] == "success")
    failed = len(video_pages) - succeeded
    blocks.append(callout_block(
        f"🎵 Playlist with {len(video_pages)} videos  •  ✅ {succeeded} summarized  •  ❌ {failed} failed",
        emoji="📑",
    ))
    blocks.append(divider_block())

    # Video list
    blocks.append(heading_block("📹 Video Summaries", level=2))
    for i, vp in enumerate(video_pages):
        if vp["status"] == "success" and vp.get("notion_url"):
            blocks.append(numbered_list_block(f"{vp['title']} — 🔗 {vp['notion_url']}"))
        else:
            blocks.append(numbered_list_block(f"{vp['title']} — ❌ {vp['status']}"))

    # Create the page
    batch = Config.NOTION_BLOCK_BATCH_SIZE
    page = client.pages.create(
        parent={"page_id": Config.NOTION_PARENT_PAGE_ID},
        properties={
            "title": {
                "title": [{"text": {"content": f"📑 {playlist_title}"}}]
            }
        },
        children=blocks[:batch],
    )

    page_id = page["id"]
    if len(blocks) > batch:
        remaining = blocks[batch:]
        while remaining:
            chunk = remaining[:batch]
            remaining = remaining[batch:]
            client.blocks.children.append(block_id=page_id, children=chunk)

    return page["url"]