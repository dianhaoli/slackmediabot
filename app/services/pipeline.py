"""
Content pipeline orchestrator for Chorus bot.
Coordinates the full flow from messages to suggestions.
"""
import logging
from typing import Optional
from datetime import datetime

from app.config import get_settings
from app.models import ConversationSummary, GeneratedContent
from app.database import get_database
from app.services.buffer import get_buffer_service
from app.services.summarizer import get_summarizer
from app.services.detector import get_detector
from app.services.generator import get_generator

logger = logging.getLogger(__name__)


class ContentPipeline:
    """
    Orchestrates the full content generation pipeline.
    
    Flow:
    1. Buffer messages
    2. Summarize conversations
    3. Detect post-worthy insights
    4. Generate drafts
    5. Deliver suggestions
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.db = get_database()
        self.buffer_service = get_buffer_service()
        self.summarizer = get_summarizer()
        self.detector = get_detector()
        self.generator = get_generator()
    
    async def process_channel(self, channel_id: str) -> list[dict]:
        """
        Process a single channel through the full pipeline.
        
        Returns list of created suggestion records.
        """
        results = []
        
        # Get message count for logging
        messages_in_buffer = self.buffer_service.get_buffer_from_db(channel_id)
        logger.info(f"Channel {channel_id}: {len(messages_in_buffer)} messages in buffer "
                   f"(need {self.settings.min_messages_for_summary} to summarize)")
        
        # Check if we should process
        if not self.buffer_service.should_summarize(channel_id):
            logger.info(f"Channel {channel_id} not ready - need more messages or time")
            return results
        
        # Check daily suggestion limit
        suggestions_today = self.db.get_suggestions_today()
        if len(suggestions_today) >= self.settings.max_suggestions_per_day:
            logger.info("Daily suggestion limit reached")
            return results
        
        # Step 1: Get messages and summarize
        messages = self.buffer_service.get_messages_for_summary(channel_id)
        if not messages:
            return results
        
        summary = self.summarizer.summarize_conversation(messages)
        if not summary or not summary.summary:
            logger.info(f"No meaningful summary for channel {channel_id}")
            self.buffer_service.clear_buffer(channel_id)
            return results
        
        # Save summary
        from app.models import SummaryMetadata
        metadata = SummaryMetadata(
            key_ideas=summary.key_ideas,
            opinions=summary.opinions,
            decisions=summary.decisions,
            interesting_phrases=summary.interesting_phrases,
            message_count=len(messages),
            window_start=messages[0].timestamp,
            window_end=messages[-1].timestamp
        )
        summary_record = self.db.save_summary(channel_id, summary.summary, metadata)
        summary_id = summary_record.get("id")
        
        # Clear buffer
        self.buffer_service.clear_buffer(channel_id)
        
        # Step 2: Detect post-worthy insights
        detection = self.detector.detect_post_worthy(summary)
        
        if not detection.is_post_worthy or not detection.ideas:
            logger.info(f"No post-worthy insights in channel {channel_id}")
            return results
        
        # Step 3: Filter ideas (dedup + sensitivity)
        filtered_ideas = self.detector.filter_ideas(
            detection.ideas, 
            summary.summary
        )
        
        if not filtered_ideas:
            logger.info("All ideas filtered out (duplicates or sensitive)")
            return results
        
        # Step 4: Generate content for each idea (respect daily limit)
        remaining_slots = self.settings.max_suggestions_per_day - len(suggestions_today)
        ideas_to_process = filtered_ideas[:remaining_slots]
        
        for idea in ideas_to_process:
            # Generate drafts
            content = self.generator.generate_content(idea, summary.summary)
            
            if not content.linkedin_draft or not content.x_draft:
                logger.warning(f"Failed to generate content for insight: {idea.core_insight[:50]}")
                continue
            
            # Save suggestion
            saved = self.generator.save_suggestion(content, summary_id)
            saved["content"] = content  # Attach for delivery
            results.append(saved)
            
            logger.info(f"Created suggestion: {saved.get('id')}")
        
        return results
    
    async def process_all_channels(self) -> list[dict]:
        """
        Process all listening channels.
        
        Returns all created suggestions.
        """
        all_results = []
        channels = self.db.get_listening_channels()
        
        for channel_id in channels:
            try:
                results = await self.process_channel(channel_id)
                all_results.extend(results)
            except Exception as e:
                logger.error(f"Failed to process channel {channel_id}: {e}")
        
        return all_results
    
    def run_sync(self) -> list[dict]:
        """
        Synchronous version for background jobs.
        """
        import asyncio
        return asyncio.run(self.process_all_channels())


# Singleton instance
_pipeline: Optional[ContentPipeline] = None

def get_pipeline() -> ContentPipeline:
    """Get pipeline singleton."""
    global _pipeline
    if _pipeline is None:
        _pipeline = ContentPipeline()
    return _pipeline
