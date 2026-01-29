"""
Post-worthiness detection service for Chorus bot.
"""
import logging
from typing import Optional

from app.models import PostWorthinessResult, PostIdea, ConversationSummary
from app.database import get_database
from app.services.llm import get_llm
from app.prompts.templates import (
    POST_WORTHINESS_PROMPT, 
    DEDUPLICATION_PROMPT,
    SENSITIVITY_PROMPT
)

logger = logging.getLogger(__name__)


class DetectorService:
    """
    Detects post-worthy insights from conversation summaries.
    
    Criteria:
    - Clear insight or opinion
    - Founder-relevant
    - Non-obvious
    - Expressed or implied conviction
    """
    
    def __init__(self):
        self.db = get_database()
        self.llm = get_llm()
    
    def detect_post_worthy(
        self, 
        summary: ConversationSummary
    ) -> PostWorthinessResult:
        """
        Analyze a summary for post-worthy insights.
        """
        # Format the prompt
        prompt = POST_WORTHINESS_PROMPT.format(
            summary=summary.summary,
            key_ideas="\n".join(f"- {idea}" for idea in summary.key_ideas),
            interesting_phrases="\n".join(f"- {phrase}" for phrase in summary.interesting_phrases)
        )
        
        try:
            result = self.llm.complete_json(prompt, temperature=0.4)
            
            ideas = []
            for idea_data in result.get("ideas", []):
                ideas.append(PostIdea(
                    core_insight=idea_data.get("core_insight", ""),
                    why_it_works=idea_data.get("why_it_works", "")
                ))
            
            return PostWorthinessResult(
                is_post_worthy=result.get("is_post_worthy", False),
                ideas=ideas
            )
            
        except Exception as e:
            logger.error(f"Failed to detect post-worthiness: {e}")
            return PostWorthinessResult(is_post_worthy=False, ideas=[])
    
    def check_duplicate(
        self, 
        new_insight: str, 
        existing_insights: list[str]
    ) -> bool:
        """
        Check if an insight is a duplicate of existing ones.
        """
        if not existing_insights:
            return False
        
        prompt = DEDUPLICATION_PROMPT.format(
            existing_insights="\n".join(f"- {i}" for i in existing_insights),
            new_insight=new_insight
        )
        
        try:
            result = self.llm.complete_json(prompt, temperature=0.2)
            is_dup = result.get("is_duplicate", False)
            
            if is_dup:
                logger.info(f"Duplicate insight detected: {result.get('reason', 'N/A')}")
            
            return is_dup
            
        except Exception as e:
            logger.error(f"Failed to check for duplicates: {e}")
            return False
    
    def check_sensitivity(
        self, 
        insight: str, 
        summary: str
    ) -> bool:
        """
        Check if an insight contains sensitive information.
        Returns True if sensitive (should not be posted).
        """
        prompt = SENSITIVITY_PROMPT.format(
            insight=insight,
            summary=summary
        )
        
        try:
            result = self.llm.complete_json(prompt, temperature=0.2)
            is_sensitive = result.get("is_sensitive", False)
            
            if is_sensitive:
                logger.warning(f"Sensitive content detected: {result.get('reason', 'N/A')}")
            
            return is_sensitive
            
        except Exception as e:
            logger.error(f"Failed to check sensitivity: {e}")
            # Err on the side of caution
            return True
    
    def filter_ideas(
        self, 
        ideas: list[PostIdea], 
        summary: str
    ) -> list[PostIdea]:
        """
        Filter ideas for duplicates and sensitivity.
        """
        # Get recent insights for deduplication
        recent_suggestions = self.db.get_saved_suggestions(limit=20)
        existing_insights = [s.get("insight", "") for s in recent_suggestions]
        
        filtered = []
        for idea in ideas:
            # Check for duplicates
            if self.check_duplicate(idea.core_insight, existing_insights):
                continue
            
            # Check for sensitivity
            if self.check_sensitivity(idea.core_insight, summary):
                continue
            
            filtered.append(idea)
            # Add to existing for cross-checking within batch
            existing_insights.append(idea.core_insight)
        
        return filtered


# Singleton instance
_detector: Optional[DetectorService] = None

def get_detector() -> DetectorService:
    """Get detector service singleton."""
    global _detector
    if _detector is None:
        _detector = DetectorService()
    return _detector
