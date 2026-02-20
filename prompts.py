"""
prompts.py — All LLM Prompts Used by TubeWise
================================================
This file contains ALL the prompts (instructions) sent to Claude via Bedrock.

WHY A SEPARATE FILE?
- Prompts are the #1 lever for improving output quality.
- You can tweak prompts without touching any Python code.
- Makes it easy to A/B test different prompt styles.

HOW PROMPTS WORK:
- A prompt is just text instructions you send to the LLM (Claude).
- The better your instructions, the better the output.
- Think of it like giving a detailed brief to a smart intern — the more
  specific you are, the better work they produce.

THREE PROMPTS IN THIS FILE:
1. SYSTEM_PROMPT    → Sets Claude's "personality" and role (used in every call)
2. SUMMARY_PROMPT   → The main prompt for short/medium videos (single-shot)
3. CHUNK_MAP_PROMPT → Used for each chunk of a long video (map step)
4. CHUNK_REDUCE_PROMPT → Combines chunk summaries into final output (reduce step)

CUSTOMIZATION TIPS:
- Add more sections by adding new ### SECTION_NAME blocks in the prompts
- Change the number of takeaways by editing "5-10" to whatever you want
- Add your own output preferences (e.g., "write in Hindi", "focus on code examples")
- The {placeholders} are filled in automatically by the code — don't remove them
"""

from __future__ import annotations


# ══════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════
# This is sent as the "system message" in every LLM call.
# It sets Claude's role and overall behavior.
# 
# Think of it as Claude's "job description" — it stays consistent
# across all interactions within this agent.
#
# CUSTOMIZATION:
# - Change the tone (e.g., "Write in a casual, friendly tone")
# - Add domain expertise (e.g., "You are an expert in AWS and cloud computing")
# - Add language preference (e.g., "Always respond in Hindi")
# ══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are an expert content analyst and knowledge extractor. 
Your job is to analyze video transcripts and produce comprehensive, well-structured summaries 
that capture ALL the knowledge from the video so the reader doesn't need to watch it.

You write in a clear, professional tone. You are thorough but concise — no filler.
When explaining concepts, use simple language and real-world analogies.
Always structure your output exactly as requested."""


# ══════════════════════════════════════════════════════════════
# MAIN SUMMARY PROMPT (for short/medium videos)
# ══════════════════════════════════════════════════════════════
# This is the primary prompt used when the entire transcript fits
# within Claude's context window (videos under ~50K words).
# 
# It sends the FULL transcript to Claude in one shot and asks for
# all sections at once. This produces the highest quality output
# because Claude can see the entire context.
#
# PLACEHOLDERS (filled automatically by code):
#   {title}      → Video title from YouTube
#   {channel}    → Channel/creator name
#   {duration}   → Human-readable duration (e.g., "45m 30s")
#   {transcript} → The full transcript text
#
# CUSTOMIZATION:
# - Add/remove sections by editing the ### blocks below
# - Change "5-10 key takeaways" to any number you prefer
# - Add section like "### TECHNICAL_DETAILS" for tech-focused videos
# - Add "Write all explanations at a beginner level" for simpler output
# ══════════════════════════════════════════════════════════════

SUMMARY_PROMPT = """Analyze the following YouTube video transcript and produce a comprehensive knowledge extraction.

**Video Title:** {title}
**Channel:** {channel}
**Duration:** {duration}

---
**TRANSCRIPT:**
{transcript}
---

Produce the following sections. Be thorough — the goal is that someone reading this gets ALL the value from the video without watching it.

## OUTPUT FORMAT (follow this exactly):

### SUMMARY
Write a clear 2-3 paragraph executive summary of the video. Cover the main thesis, key arguments, and conclusion. Write it so someone can understand the entire video's message in 30 seconds.

### KEY_TAKEAWAYS
List 5-10 key takeaways. Each should be:
- Actionable and specific (not vague)
- One clear sentence each
- Numbered 1, 2, 3...
Focus on insights that are genuinely valuable and non-obvious.

### TOPICS_COVERED
List each distinct topic/section covered in the video. For each topic:
- **Topic Name**: Brief 2-3 sentence explanation of what was discussed
Keep the explanations substantive — not just "they talked about X" but what was actually said about X.

### CONCEPT_EXPLANATIONS
Identify 3-5 complex or important concepts mentioned in the video. For each:
- **Concept Name**: Clear explanation in simple terms, with an analogy or example if helpful.
These should help someone unfamiliar with the topic understand the key ideas.

### ACTION_ITEMS
List 3-7 practical action items or next steps that a viewer should take based on the video content.
- Be specific and actionable
- Include any resources, tools, or links mentioned in the video

### DIAGRAM_DESCRIPTION
Describe a concept map or flow diagram that captures the main relationships between ideas in this video.
Write it as a Mermaid.js diagram using this format:
```mermaid
graph TD
    A[Main Topic] --> B[Subtopic 1]
    A --> C[Subtopic 2]
    B --> D[Detail]
```
Make the diagram meaningful — it should show how concepts relate to each other, not just list them.

### NOTABLE_QUOTES
Extract 3-5 notable or impactful quotes from the transcript (exact or near-exact wording).
Format as: "Quote text here"

### RESOURCES_MENTIONED
List any tools, websites, books, papers, people, or resources mentioned in the video.
Format as: **Resource Name** - Brief description of what it is and why it was mentioned
If none were mentioned, write "No specific resources mentioned."
"""


# ══════════════════════════════════════════════════════════════
# CHUNK MAP PROMPT (for long videos — processing each chunk)
# ══════════════════════════════════════════════════════════════
# When a video is too long to process in one shot, we split the
# transcript into chunks and process each one separately.
# This prompt handles ONE chunk at a time.
#
# The "map" in "map-reduce":
#   - "Map" = process each piece individually (this prompt)
#   - "Reduce" = combine all pieces into final output (next prompt)
#
# PLACEHOLDERS:
#   {title}        → Video title
#   {chunk_number} → Which chunk this is (e.g., 3)
#   {total_chunks} → Total number of chunks (e.g., 8)
#   {chunk}        → The transcript text for this specific chunk
#
# CUSTOMIZATION:
# - This prompt is intentionally simpler than SUMMARY_PROMPT because
#   we're just extracting raw information here, not formatting final output.
# - The REDUCE prompt handles the final formatting.
# ══════════════════════════════════════════════════════════════

CHUNK_MAP_PROMPT = """Analyze this portion of a YouTube video transcript and extract key information.

**Video Title:** {title}
**Section:** Part {chunk_number} of {total_chunks}

---
**TRANSCRIPT SECTION:**
{chunk}
---

Extract:
1. **Main points** discussed in this section (3-5 bullet points)
2. **Key concepts** introduced or explained
3. **Notable quotes** or statements
4. **Resources** or tools mentioned
5. **Action items** or advice given

Be thorough but concise. Focus on substantive information, not filler."""


# ══════════════════════════════════════════════════════════════
# CHUNK REDUCE PROMPT (for long videos — combining all chunks)
# ══════════════════════════════════════════════════════════════
# After all chunks have been processed (map step), this prompt
# takes ALL the chunk summaries and combines them into one
# coherent, well-structured final output.
#
# This is where the final quality is determined for long videos.
# The prompt format mirrors SUMMARY_PROMPT so the output is identical
# whether a video was processed in one shot or via map-reduce.
#
# PLACEHOLDERS:
#   {title}              → Video title
#   {channel}            → Channel name
#   {duration}           → Video duration
#   {combined_summaries} → All chunk summaries concatenated together
#
# CUSTOMIZATION:
# - Keep this in sync with SUMMARY_PROMPT — if you add a section
#   to SUMMARY_PROMPT, add it here too so output is consistent.
# ══════════════════════════════════════════════════════════════

CHUNK_REDUCE_PROMPT = """You have been given extracted summaries from different sections of a YouTube video.
Combine them into a single comprehensive knowledge extraction.

**Video Title:** {title}
**Channel:** {channel}
**Duration:** {duration}

---
**EXTRACTED SECTIONS:**
{combined_summaries}
---

Now produce the final comprehensive summary following this exact format:

### SUMMARY
Write a clear 2-3 paragraph executive summary covering the entire video.

### KEY_TAKEAWAYS
List 5-10 key takeaways (numbered, actionable, specific).

### TOPICS_COVERED
List each topic with a substantive 2-3 sentence explanation.

### CONCEPT_EXPLANATIONS
3-5 complex concepts explained simply with analogies.

### ACTION_ITEMS
3-7 practical, specific next steps.

### DIAGRAM_DESCRIPTION
A Mermaid.js concept map showing relationships between main ideas:
```mermaid
graph TD
    A[Topic] --> B[Subtopic]
```

### NOTABLE_QUOTES
3-5 impactful quotes from the video.

### RESOURCES_MENTIONED
Tools, websites, books, people mentioned. If none, say so.
"""