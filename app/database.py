"""
Supabase database client and operations for Chorus bot.
"""
from supabase import create_client, Client
from datetime import datetime, timedelta
from typing import Optional
import json

from app.config import get_settings
from app.models import (
    SlackMessage, 
    SummaryMetadata, 
    Suggestion, 
    SuggestionStatus,
    ListeningChannel
)


class Database:
    """Database operations using Supabase."""
    
    def __init__(self):
        settings = get_settings()
        self.client: Client = create_client(
            settings.supabase_url, 
            settings.supabase_key
        )
    
    # ========================================================
    # Messages
    # ========================================================
    
    def save_message(self, message: SlackMessage) -> dict:
        """Save a message to the database."""
        data = {
            "channel_id": message.channel_id,
            "user_id": message.user_id,
            "text": message.text,
            "created_at": message.timestamp.isoformat()
        }
        result = self.client.table("messages").insert(data).execute()
        return result.data[0] if result.data else {}
    
    def get_messages_in_window(
        self, 
        channel_id: str, 
        window_minutes: int = 60
    ) -> list[SlackMessage]:
        """Get messages from the last N minutes."""
        cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
        
        result = self.client.table("messages") \
            .select("*") \
            .eq("channel_id", channel_id) \
            .gte("created_at", cutoff.isoformat()) \
            .order("created_at", desc=False) \
            .execute()
        
        messages = []
        for row in result.data:
            messages.append(SlackMessage(
                message_id=row["id"],
                channel_id=row["channel_id"],
                user_id=row["user_id"],
                text=row["text"],
                timestamp=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            ))
        return messages
    
    def get_unprocessed_messages(
        self, 
        channel_id: str, 
        since: Optional[datetime] = None
    ) -> list[SlackMessage]:
        """Get messages that haven't been summarized yet."""
        query = self.client.table("messages") \
            .select("*") \
            .eq("channel_id", channel_id)
        
        if since:
            query = query.gte("created_at", since.isoformat())
        
        result = query.order("created_at", desc=False).execute()
        
        messages = []
        for row in result.data:
            messages.append(SlackMessage(
                message_id=row["id"],
                channel_id=row["channel_id"],
                user_id=row["user_id"],
                text=row["text"],
                timestamp=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            ))
        return messages
    
    # ========================================================
    # Summaries
    # ========================================================
    
    def save_summary(
        self, 
        channel_id: str, 
        summary: str, 
        metadata: SummaryMetadata
    ) -> dict:
        """Save a conversation summary."""
        data = {
            "channel_id": channel_id,
            "summary": summary,
            "metadata": {
                "key_ideas": metadata.key_ideas,
                "opinions": metadata.opinions,
                "decisions": metadata.decisions,
                "interesting_phrases": metadata.interesting_phrases,
                "message_count": metadata.message_count,
                "window_start": metadata.window_start.isoformat(),
                "window_end": metadata.window_end.isoformat()
            }
        }
        result = self.client.table("summaries").insert(data).execute()
        return result.data[0] if result.data else {}
    
    def get_latest_summary(self, channel_id: str) -> Optional[dict]:
        """Get the most recent summary for a channel."""
        result = self.client.table("summaries") \
            .select("*") \
            .eq("channel_id", channel_id) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
        
        return result.data[0] if result.data else None
    
    def get_recent_summaries(
        self, 
        channel_id: str, 
        limit: int = 5
    ) -> list[dict]:
        """Get recent summaries for context."""
        result = self.client.table("summaries") \
            .select("*") \
            .eq("channel_id", channel_id) \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()
        
        return result.data
    
    # ========================================================
    # Suggestions
    # ========================================================
    
    def save_suggestion(self, suggestion: Suggestion) -> dict:
        """Save a content suggestion."""
        data = {
            "summary_id": suggestion.summary_id,
            "insight": suggestion.insight,
            "linkedin_draft": suggestion.linkedin_draft,
            "x_draft": suggestion.x_draft,
            "status": suggestion.status.value
        }
        result = self.client.table("suggestions").insert(data).execute()
        return result.data[0] if result.data else {}
    
    def update_suggestion_status(
        self, 
        suggestion_id: str, 
        status: SuggestionStatus
    ) -> dict:
        """Update the status of a suggestion."""
        result = self.client.table("suggestions") \
            .update({"status": status.value}) \
            .eq("id", suggestion_id) \
            .execute()
        return result.data[0] if result.data else {}
    
    def get_suggestion(self, suggestion_id: str) -> Optional[dict]:
        """Get a suggestion by ID."""
        result = self.client.table("suggestions") \
            .select("*") \
            .eq("id", suggestion_id) \
            .execute()
        return result.data[0] if result.data else None
    
    def get_suggestions_today(self) -> list[dict]:
        """Get all suggestions created today."""
        today_start = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        result = self.client.table("suggestions") \
            .select("*") \
            .gte("created_at", today_start.isoformat()) \
            .execute()
        return result.data
    
    def get_saved_suggestions(self, limit: int = 10) -> list[dict]:
        """Get saved suggestions."""
        result = self.client.table("suggestions") \
            .select("*") \
            .eq("status", SuggestionStatus.SAVED.value) \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()
        return result.data
    
    # ========================================================
    # Listening Channels
    # ========================================================
    
    def add_listening_channel(
        self, 
        channel_id: str, 
        user_id: str
    ) -> dict:
        """Add a channel to listen to."""
        data = {
            "channel_id": channel_id,
            "added_by": user_id,
            "added_at": datetime.utcnow().isoformat()
        }
        result = self.client.table("listening_channels") \
            .upsert(data, on_conflict="channel_id") \
            .execute()
        return result.data[0] if result.data else {}
    
    def remove_listening_channel(self, channel_id: str) -> bool:
        """Remove a channel from listening."""
        self.client.table("listening_channels") \
            .delete() \
            .eq("channel_id", channel_id) \
            .execute()
        return True
    
    def get_listening_channels(self) -> list[str]:
        """Get all channels the bot is listening to."""
        result = self.client.table("listening_channels") \
            .select("channel_id") \
            .execute()
        return [row["channel_id"] for row in result.data]
    
    def is_listening(self, channel_id: str) -> bool:
        """Check if bot is listening to a channel."""
        result = self.client.table("listening_channels") \
            .select("channel_id") \
            .eq("channel_id", channel_id) \
            .execute()
        return len(result.data) > 0


# Singleton instance
_db: Optional[Database] = None

def get_database() -> Database:
    """Get database singleton."""
    global _db
    if _db is None:
        _db = Database()
    return _db
