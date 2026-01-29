"""
Pydantic models for Chorus bot.
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum


# ============================================================
# Message Models
# ============================================================

class SlackMessage(BaseModel):
    """Raw message from Slack."""
    message_id: str
    channel_id: str
    user_id: str
    text: str
    timestamp: datetime


class MessageBuffer(BaseModel):
    """Buffer of messages for a channel."""
    channel_id: str
    messages: list[SlackMessage] = []
    started_at: datetime
    

# ============================================================
# Summary Models
# ============================================================

class ConversationSummary(BaseModel):
    """Output from conversation summarization."""
    summary: str
    key_ideas: list[str]
    opinions: list[str]
    decisions: list[str]
    interesting_phrases: list[str]


class SummaryMetadata(BaseModel):
    """Metadata stored with summaries."""
    key_ideas: list[str]
    opinions: list[str]
    decisions: list[str]
    interesting_phrases: list[str]
    message_count: int
    window_start: datetime
    window_end: datetime


# ============================================================
# Post-Worthiness Models
# ============================================================

class PostIdea(BaseModel):
    """A single post-worthy idea."""
    core_insight: str
    why_it_works: str


class PostWorthinessResult(BaseModel):
    """Result from post-worthiness detection."""
    is_post_worthy: bool
    ideas: list[PostIdea] = []


# ============================================================
# Content Generation Models
# ============================================================

class GeneratedContent(BaseModel):
    """Generated post drafts for an insight."""
    core_insight: str
    why_it_works: str
    linkedin_draft: str
    x_draft: str


# ============================================================
# Suggestion Models
# ============================================================

class SuggestionStatus(str, Enum):
    PENDING = "pending"
    SAVED = "saved"
    IGNORED = "ignored"
    REWRITTEN = "rewritten"


class Suggestion(BaseModel):
    """A content suggestion stored in DB."""
    id: Optional[str] = None
    summary_id: str
    insight: str
    linkedin_draft: str
    x_draft: str
    status: SuggestionStatus = SuggestionStatus.PENDING
    created_at: Optional[datetime] = None


# ============================================================
# Slack Interaction Models
# ============================================================

class ListeningChannel(BaseModel):
    """A channel the bot is listening to."""
    channel_id: str
    added_at: datetime
    added_by: str
