"""
Conversation summarization service for Chorus bot.
"""
from datetime import datetime
import logging
from typing import Optional

from app.models import SlackMessage, ConversationSummary, SummaryMetadata
from app.database import get_database
from app.services.llm import get_llm
from app.services.buffer import get_buffer_service
from app.prompts.templates import SUMMARIZER_PROMPT

logger = logging.getLogger(__name__)


class SummarizerService:
    """
    Summarizes conversations and extracts key insights.
    
    Trigger: Every 60 minutes OR buffer > N messages
    """
    
    def __init__(self):
        self.db = get_database()
        self.llm = get_llm()
        self.buffer_service = get_buffer_service()
    
    def summarize_conversation(
        self, 
        messages: list[SlackMessage]
    ) -> Optional[ConversationSummary]:
        """
        Summarize a conversation and extract insights.
        
        Returns None if conversation is too casual or empty.
        """
        if not messages:
            logger.warning("No messages to summarize")
            return None
        
        # Format messages for LLM
        formatted = self.buffer_service.format_messages_for_llm(messages)
        
        # Build prompt
        prompt = SUMMARIZER_PROMPT.format(messages=formatted)
        
        try:
            # Get LLM response
            result = self.llm.complete_json(prompt, temperature=0.3)
            
            summary = ConversationSummary(
                summary=result.get("summary", ""),
                key_ideas=result.get("key_ideas", []),
                opinions=result.get("opinions", []),
                decisions=result.get("decisions", []),
                interesting_phrases=result.get("interesting_phrases", [])
            )
            
            logger.info(f"Generated summary with {len(summary.key_ideas)} key ideas")
            return summary
            
        except Exception as e:
            logger.error(f"Failed to summarize conversation: {e}")
            return None
    
    def process_channel(self, channel_id: str) -> Optional[dict]:
        """
        Process a channel's buffer and create a summary.
        
        Returns the saved summary record or None.
        """
        # Check if should summarize
        if not self.buffer_service.should_summarize(channel_id):
            logger.debug(f"Channel {channel_id} not ready for summarization")
            return None
        
        # Get messages
        messages = self.buffer_service.get_messages_for_summary(channel_id)
        if not messages:
            return None
        
        # Generate summary
        summary = self.summarize_conversation(messages)
        if not summary or not summary.summary:
            logger.info(f"No meaningful summary generated for channel {channel_id}")
            self.buffer_service.clear_buffer(channel_id)
            return None
        
        # Create metadata
        metadata = SummaryMetadata(
            key_ideas=summary.key_ideas,
            opinions=summary.opinions,
            decisions=summary.decisions,
            interesting_phrases=summary.interesting_phrases,
            message_count=len(messages),
            window_start=messages[0].timestamp,
            window_end=messages[-1].timestamp
        )
        
        # Save to database
        saved = self.db.save_summary(channel_id, summary.summary, metadata)
        
        # Clear buffer
        self.buffer_service.clear_buffer(channel_id)
        
        logger.info(f"Saved summary for channel {channel_id}: {saved.get('id')}")
        return saved
    
    def process_all_channels(self) -> list[dict]:
        """Process all listening channels."""
        channels = self.db.get_listening_channels()
        results = []
        
        for channel_id in channels:
            result = self.process_channel(channel_id)
            if result:
                results.append(result)
        
        return results


# Singleton instance
_summarizer: Optional[SummarizerService] = None

def get_summarizer() -> SummarizerService:
    """Get summarizer service singleton."""
    global _summarizer
    if _summarizer is None:
        _summarizer = SummarizerService()
    return _summarizer
