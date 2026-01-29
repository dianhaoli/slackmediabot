"""
Prompt templates for Chorus bot LLM interactions.
All prompts are drop-in ready as specified in the PRD.
"""

# ============================================================
# SYSTEM PROMPT (GLOBAL)
# ============================================================

SYSTEM_PROMPT = """You are a quiet observer embedded in a founding team's daily Slack.

You watch everything - product debates, growth experiments, hiring frustrations, random jokes, code snippets, late-night rabbit holes, half-baked ideas, and the occasional existential crisis.

Your job is to notice when something genuinely interesting surfaces. Not manufactured insights - the real stuff that emerges organically when smart people are just talking.

You have taste. You know the difference between a throwaway comment and a hard-won realization. You never force content. Most conversations are just conversations. But sometimes someone says something worth sharing - and you catch it."""


# ============================================================
# CONVERSATION SUMMARIZER
# ============================================================

SUMMARIZER_PROMPT = """Summarize the following Slack conversation from a founding team.

This could be anything - product strategy, growth experiments, technical debates, hiring rants, random tangents, jokes, or just people thinking out loud. Treat it all as raw material.

Extract:
- Key ideas discussed (product, growth, tech, team, whatever came up)
- Opinions or strong views (even if casual or half-joking)
- Decisions made (if any)
- Interesting phrasing, metaphors, or turns of phrase
- Any hard-won realizations or "aha" moments

Be concise but insightful. Capture the texture of the conversation.

Conversation:
{messages}

Respond with a JSON object in this exact format:
{{
  "summary": "A concise summary of the conversation",
  "key_ideas": ["idea 1", "idea 2"],
  "opinions": ["opinion 1", "opinion 2"],
  "decisions": ["decision 1"],
  "interesting_phrases": ["phrase 1", "phrase 2"]
}}"""


# ============================================================
# POST-WORTHINESS DETECTOR
# ============================================================

POST_WORTHINESS_PROMPT = """Based on the summary below, decide if there is any post-worthy insight.

A post-worthy insight is:
- Founder-relevant
- Non-obvious
- Opinionated or reflective
- Something others would save or share

If nothing qualifies, return:
{{ "is_post_worthy": false, "ideas": [] }}

If something qualifies, return structured ideas.

Summary:
{summary}

Key ideas from conversation:
{key_ideas}

Interesting phrases:
{interesting_phrases}

Respond with a JSON object in this exact format:
{{
  "is_post_worthy": true,
  "ideas": [
    {{
      "core_insight": "The main insight in one clear sentence",
      "why_it_works": "Why this would resonate with founders"
    }}
  ]
}}

Only include genuinely interesting insights. Quality over quantity."""


# ============================================================
# LINKEDIN POST GENERATOR
# ============================================================

LINKEDIN_PROMPT = """Write a LinkedIn post in the voice of a thoughtful founder.

Guidelines:
- 5–8 short paragraphs
- Plainspoken, honest
- No emojis
- No marketing language
- No hashtags
- End with a reflective question

Insight:
{core_insight}

Context:
{summary}

Why this works:
{why_it_works}

Write the post directly, no preamble or explanation. Just the post content."""


# ============================================================
# X POST GENERATOR
# ============================================================

X_POST_PROMPT = """Write a Twitter/X post.

Guidelines:
- Max 280 characters
- Direct and opinionated
- Founder-to-founder tone
- No hashtags unless essential
- No emojis

Insight:
{core_insight}

Write the post directly, no preamble or explanation. Just the tweet."""


# ============================================================
# REWRITE PROMPTS
# ============================================================

REWRITE_LINKEDIN_PROMPT = """Rewrite this LinkedIn post with a fresh angle.

Original post:
{original_draft}

Core insight:
{core_insight}

Context:
{summary}

Guidelines:
- 5–8 short paragraphs
- Plainspoken, honest
- No emojis
- No marketing language
- No hashtags
- End with a reflective question
- Take a DIFFERENT angle than the original

Write the post directly, no preamble or explanation."""


REWRITE_X_PROMPT = """Rewrite this tweet with a fresh angle.

Original tweet:
{original_draft}

Core insight:
{core_insight}

Guidelines:
- Max 280 characters
- Direct and opinionated
- Founder-to-founder tone
- No hashtags unless essential
- No emojis
- Take a DIFFERENT angle than the original

Write the tweet directly, no preamble or explanation."""


# ============================================================
# DEDUPLICATION CHECK
# ============================================================

DEDUPLICATION_PROMPT = """Compare these insights and determine if the new insight is too similar to any existing ones.

Existing insights:
{existing_insights}

New insight:
{new_insight}

Return JSON:
{{
  "is_duplicate": true/false,
  "reason": "Brief explanation if duplicate"
}}

Only mark as duplicate if the core idea is essentially the same."""


# ============================================================
# SENSITIVITY CHECK
# ============================================================

SENSITIVITY_PROMPT = """Review this insight for any sensitive or private information that should NOT be shared publicly.

Insight:
{insight}

Context summary:
{summary}

Check for:
- Personal financial details
- Health information
- Private business metrics (revenue, runway, etc.)
- Names of people who haven't consented
- Confidential deal or partnership details
- Anything that could harm someone's reputation

Return JSON:
{{
  "is_sensitive": true/false,
  "reason": "Explanation if sensitive"
}}"""
