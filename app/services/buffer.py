"""
Message buffering service for Chorus bot.
Implements rolling time-based window strategy.
"""
from datetime import datetime, timedelta
from typing import Optional
import logging

from app.config import get_settings
from app.models import SlackMessage, MessageBuffer
from app.database import get_database

logger = logging.getLogger(__name__)


class BufferService:
    """
    Manages message buffering with rolling time window.
    
    Strategy:
    - Messages appended to buffer as they arrive
    - Buffer resets after summarization
    - Minimum messages required before processing
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.db = get_database()
        # In-memory buffers per channel (for real-time tracking)
        self._buffers: dict[str, MessageBuffer] = {}
    
    def add_message(self, message: SlackMessage) -> None:
        """Add a message to the buffer and persist to DB."""
        channel_id = message.channel_id
        
        # Save to database
        self.db.save_message(message)
        
        # Update in-memory buffer
        if channel_id not in self._buffers:
            self._buffers[channel_id] = MessageBuffer(
                channel_id=channel_id,
                messages=[],
                started_at=datetime.utcnow()
            )
        
        self._buffers[channel_id].messages.append(message)
        logger.info(f"Added message to buffer for channel {channel_id}. "
                   f"Buffer size: {len(self._buffers[channel_id].messages)}")
    
    def get_buffer(self, channel_id: str) -> Optional[MessageBuffer]:
        """Get current buffer for a channel."""
        return self._buffers.get(channel_id)
    
    def get_buffer_from_db(self, channel_id: str) -> list[SlackMessage]:
        """Get buffered messages from database within the time window."""
        return self.db.get_messages_in_window(
            channel_id, 
            self.settings.buffer_window_minutes
        )
    
    def should_summarize(self, channel_id: str) -> bool:
        """
        Check if buffer should be summarized.
        
        Triggers:
        - Time window exceeded (60 minutes default)
        - Minimum message count reached (8 messages default)
        """
        buffer = self._buffers.get(channel_id)
        if not buffer or not buffer.messages:
            # Check database for messages
            db_messages = self.get_buffer_from_db(channel_id)
            if len(db_messages) >= self.settings.min_messages_for_summary:
                return True
            return False
        
        # Check message count
        if len(buffer.messages) >= self.settings.min_messages_for_summary:
            return True
        
        # Check time window
        window_elapsed = datetime.utcnow() - buffer.started_at
        if window_elapsed >= timedelta(minutes=self.settings.buffer_window_minutes):
            # Only summarize if we have at least some messages
            if len(buffer.messages) >= 3:
                return True
        
        return False
    
    def get_messages_for_summary(self, channel_id: str) -> list[SlackMessage]:
        """Get all messages that should be summarized."""
        # Prefer database source for completeness
        db_messages = self.get_buffer_from_db(channel_id)
        if db_messages:
            return db_messages
        
        # Fallback to in-memory
        buffer = self._buffers.get(channel_id)
        return buffer.messages if buffer else []
    
    def clear_buffer(self, channel_id: str) -> None:
        """Clear the buffer after summarization."""
        if channel_id in self._buffers:
            self._buffers[channel_id] = MessageBuffer(
                channel_id=channel_id,
                messages=[],
                started_at=datetime.utcnow()
            )
        logger.info(f"Cleared buffer for channel {channel_id}")
    
    def format_messages_for_llm(self, messages: list[SlackMessage]) -> str:
        """Format messages for LLM consumption."""
        formatted = []
        for msg in messages:
            timestamp = msg.timestamp.strftime("%H:%M")
            formatted.append(f"[{timestamp}] User {msg.user_id[-4:]}: {msg.text}")
        return "\n".join(formatted)


# Singleton instance
_buffer_service: Optional[BufferService] = None

def get_buffer_service() -> BufferService:
    """Get buffer service singleton."""
    global _buffer_service
    if _buffer_service is None:
        _buffer_service = BufferService()
    return _buffer_service
