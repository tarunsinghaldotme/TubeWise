"""
test_notion_publisher.py — Unit tests for notion_publisher.py pure functions
"""

from __future__ import annotations

import pytest

from notion_publisher import (
    parse_summary_sections,
    parse_bullet_lines,
    parse_topic_entries,
    _split_text,
    safe_rich_text,
    rich_text,
    heading_block,
    paragraph_block,
    bulleted_list_block,
    numbered_list_block,
    callout_block,
    quote_block,
    divider_block,
    code_block,
    bookmark_block,
    toggle_block,
    NOTION_TEXT_LIMIT,
)


# ══════════════════════════════════════════════════════════════
# parse_summary_sections()
# ══════════════════════════════════════════════════════════════

class TestParseSummarySections:
    """Test parsing Claude's raw output into named sections."""

    def test_parses_all_sections(self, sample_raw_summary):
        sections = parse_summary_sections(sample_raw_summary)
        assert "machine learning" in sections["summary"].lower()
        assert "Supervised learning" in sections["key_takeaways"]
        assert "Supervised Learning" in sections["topics_covered"]
        assert "Gradient Descent" in sections["concept_explanations"]
        assert "scikit-learn" in sections["action_items"]
        assert "mermaid" in sections["diagram_description"]
        assert "wrong" in sections["notable_quotes"]
        assert "scikit-learn" in sections["resources_mentioned"]

    def test_empty_input(self):
        sections = parse_summary_sections("")
        assert all(v == "" for v in sections.values())

    def test_missing_sections_are_empty(self):
        raw = "### SUMMARY\nJust a summary.\n"
        sections = parse_summary_sections(raw)
        assert "Just a summary" in sections["summary"]
        assert sections["key_takeaways"] == ""
        assert sections["topics_covered"] == ""

    def test_unknown_section_ignored(self):
        raw = "### RANDOM_SECTION\nThis should be ignored.\n### SUMMARY\nActual summary."
        sections = parse_summary_sections(raw)
        assert "Actual summary" in sections["summary"]

    def test_multiline_section_content(self):
        raw = "### SUMMARY\nLine 1\nLine 2\nLine 3"
        sections = parse_summary_sections(raw)
        assert "Line 1" in sections["summary"]
        assert "Line 3" in sections["summary"]


# ══════════════════════════════════════════════════════════════
# parse_bullet_lines()
# ══════════════════════════════════════════════════════════════

class TestParseBulletLines:
    """Test extraction of bullet points from various formats."""

    def test_dash_bullets(self):
        text = "- First item\n- Second item\n- Third item"
        result = parse_bullet_lines(text)
        assert result == ["First item", "Second item", "Third item"]

    def test_asterisk_bullets(self):
        text = "* Item A\n* Item B"
        result = parse_bullet_lines(text)
        assert result == ["Item A", "Item B"]

    def test_unicode_bullets(self):
        text = "• Alpha\n• Beta"
        result = parse_bullet_lines(text)
        assert result == ["Alpha", "Beta"]

    def test_numbered_dot(self):
        text = "1. First\n2. Second\n3. Third"
        result = parse_bullet_lines(text)
        assert result == ["First", "Second", "Third"]

    def test_numbered_paren(self):
        text = "1) First\n2) Second"
        result = parse_bullet_lines(text)
        assert result == ["First", "Second"]

    def test_empty_lines_skipped(self):
        text = "- Item 1\n\n- Item 2\n\n\n- Item 3"
        result = parse_bullet_lines(text)
        assert len(result) == 3

    def test_empty_input(self):
        assert parse_bullet_lines("") == []

    def test_plain_text_preserved(self):
        text = "Just plain text without bullets"
        result = parse_bullet_lines(text)
        assert result == ["Just plain text without bullets"]


# ══════════════════════════════════════════════════════════════
# parse_topic_entries()
# ══════════════════════════════════════════════════════════════

class TestParseTopicEntries:
    """Test parsing of **Name**: Description format."""

    def test_bold_format(self):
        text = "- **Docker**: A containerization tool\n- **Kubernetes**: Container orchestration"
        result = parse_topic_entries(text)
        assert len(result) == 2
        assert result[0] == ("Docker", "A containerization tool")
        assert result[1] == ("Kubernetes", "Container orchestration")

    def test_no_bold_format(self):
        text = "Python: A versatile programming language\nRust: A systems language"
        result = parse_topic_entries(text)
        assert len(result) == 2
        assert result[0][0] == "Python"
        assert result[1][0] == "Rust"

    def test_multiline_description(self):
        text = "- **Topic One**: First line\n  continues here\n- **Topic Two**: Short desc"
        result = parse_topic_entries(text)
        assert len(result) == 2
        assert "continues here" in result[0][1]

    def test_empty_input(self):
        assert parse_topic_entries("") == []

    def test_asterisk_bullets_with_bold(self):
        text = "* **Redis**: In-memory data store"
        result = parse_topic_entries(text)
        assert result[0] == ("Redis", "In-memory data store")


# ══════════════════════════════════════════════════════════════
# _split_text()
# ══════════════════════════════════════════════════════════════

class TestSplitText:
    """Test text splitting for Notion's 2000-char limit."""

    def test_short_text_not_split(self):
        text = "Short text"
        result = _split_text(text)
        assert result == ["Short text"]

    def test_exact_limit_not_split(self):
        text = "x" * NOTION_TEXT_LIMIT
        result = _split_text(text)
        assert len(result) == 1

    def test_over_limit_gets_split(self):
        text = "word " * 500  # 2500 chars, over 2000 limit
        result = _split_text(text)
        assert len(result) >= 2
        for chunk in result:
            assert len(chunk) <= NOTION_TEXT_LIMIT

    def test_split_at_sentence_boundary(self):
        # Create text that forces a split, with a sentence boundary
        sentence = "This is a complete sentence. "
        text = sentence * 100  # ~2800 chars
        result = _split_text(text)
        assert len(result) >= 2
        # First chunk should end at a sentence boundary
        assert result[0].rstrip().endswith(".")

    def test_empty_text(self):
        result = _split_text("")
        assert result == [""]

    def test_custom_limit(self):
        text = "Hello World! " * 10  # ~130 chars
        result = _split_text(text, limit=50)
        assert len(result) >= 3
        for chunk in result:
            assert len(chunk) <= 50


# ══════════════════════════════════════════════════════════════
# safe_rich_text()
# ══════════════════════════════════════════════════════════════

class TestSafeRichText:
    """Test safe_rich_text() auto-splitting."""

    def test_short_text_single_item(self):
        result = safe_rich_text("Hello")
        assert len(result) == 1
        assert result[0]["text"]["content"] == "Hello"

    def test_long_text_multiple_items(self):
        text = "word " * 500  # Over 2000 chars
        result = safe_rich_text(text)
        assert len(result) >= 2

    def test_formatting_applied_to_all_chunks(self):
        text = "word " * 500
        result = safe_rich_text(text, bold=True, italic=True)
        for item in result:
            assert item["annotations"]["bold"] is True
            assert item["annotations"]["italic"] is True

    def test_color_applied(self):
        result = safe_rich_text("Colored text", color="red")
        assert result[0]["annotations"]["color"] == "red"


# ══════════════════════════════════════════════════════════════
# Block builder functions
# ══════════════════════════════════════════════════════════════

class TestBlockBuilders:
    """Test each Notion block builder function."""

    def test_heading_block_default_level(self):
        block = heading_block("My Heading")
        assert block["type"] == "heading_2"
        assert block["heading_2"]["rich_text"][0]["text"]["content"] == "My Heading"

    def test_heading_block_level_3(self):
        block = heading_block("Sub Heading", level=3)
        assert block["type"] == "heading_3"

    def test_paragraph_block(self):
        block = paragraph_block("Paragraph text")
        assert block["type"] == "paragraph"
        assert block["paragraph"]["rich_text"][0]["text"]["content"] == "Paragraph text"

    def test_paragraph_block_bold(self):
        block = paragraph_block("Bold text", bold=True)
        assert block["paragraph"]["rich_text"][0]["annotations"]["bold"] is True

    def test_bulleted_list_block(self):
        block = bulleted_list_block("List item")
        assert block["type"] == "bulleted_list_item"
        assert block["bulleted_list_item"]["rich_text"][0]["text"]["content"] == "List item"

    def test_bulleted_list_block_with_prefix(self):
        block = bulleted_list_block(" description", bold_prefix="Label: ")
        rich = block["bulleted_list_item"]["rich_text"]
        assert rich[0]["annotations"]["bold"] is True
        assert rich[0]["text"]["content"] == "Label: "

    def test_numbered_list_block(self):
        block = numbered_list_block("Numbered item")
        assert block["type"] == "numbered_list_item"

    def test_callout_block(self):
        block = callout_block("Important info", emoji="🔥")
        assert block["type"] == "callout"
        assert block["callout"]["icon"]["emoji"] == "🔥"

    def test_quote_block_italic(self):
        block = quote_block("A wise quote")
        assert block["type"] == "quote"
        assert block["quote"]["rich_text"][0]["annotations"]["italic"] is True

    def test_divider_block(self):
        block = divider_block()
        assert block["type"] == "divider"

    def test_code_block(self):
        block = code_block("graph TD\nA-->B", language="mermaid")
        assert block["type"] == "code"
        assert block["code"]["language"] == "mermaid"

    def test_bookmark_block(self):
        block = bookmark_block("https://youtube.com/watch?v=abc123")
        assert block["type"] == "bookmark"
        assert block["bookmark"]["url"] == "https://youtube.com/watch?v=abc123"

    def test_toggle_block(self):
        children = [paragraph_block("Hidden content")]
        block = toggle_block("Toggle Title", children)
        assert block["type"] == "toggle"
        assert block["toggle"]["rich_text"][0]["annotations"]["bold"] is True
        assert len(block["toggle"]["children"]) == 1

    def test_rich_text_truncates_over_limit(self):
        long_text = "x" * (NOTION_TEXT_LIMIT + 100)
        result = rich_text(long_text)
        assert len(result["text"]["content"]) == NOTION_TEXT_LIMIT
