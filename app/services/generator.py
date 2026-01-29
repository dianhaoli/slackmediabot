"""
Content generation service for Chorus bot.
Generates platform-specific post drafts.
"""
import logging
from typing import Optional

from app.models import PostIdea, GeneratedContent, Suggestion, SuggestionStatus
from app.database import get_database
from app.services.llm import get_llm
from app.prompts.templates import (
    LINKEDIN_PROMPT,
    X_POST_PROMPT,
    REWRITE_LINKEDIN_PROMPT,
    REWRITE_X_PROMPT
)

logger = logging.getLogger(__name__)


class GeneratorService:
    """
    Generates platform-specific content drafts.
    
    Platforms:
    - LinkedIn
    - X (Twitter)
    
    Constraints:
    - Platform-native tone
    - No emojis on LinkedIn
    - No hashtags by default
    - Not promotional
    """
    
    def __init__(self):
        self.db = get_database()
        self.llm = get_llm()
    
    def generate_linkedin_post(
        self, 
        idea: PostIdea, 
        summary: str
    ) -> str:
        """Generate a LinkedIn post draft."""
        prompt = LINKEDIN_PROMPT.format(
            core_insight=idea.core_insight,
            why_it_works=idea.why_it_works,
            summary=summary
        )
        
        try:
            draft = self.llm.complete(prompt, temperature=0.7, max_tokens=1000)
            return self._clean_linkedin_draft(draft)
        except Exception as e:
            logger.error(f"Failed to generate LinkedIn post: {e}")
            return ""
    
    def generate_x_post(self, idea: PostIdea) -> str:
        """Generate an X/Twitter post draft."""
        prompt = X_POST_PROMPT.format(core_insight=idea.core_insight)
        
        try:
            draft = self.llm.complete(prompt, temperature=0.8, max_tokens=100)
            return self._clean_x_draft(draft)
        except Exception as e:
            logger.error(f"Failed to generate X post: {e}")
            return ""
    
    def generate_content(
        self, 
        idea: PostIdea, 
        summary: str
    ) -> GeneratedContent:
        """Generate both LinkedIn and X drafts for an idea."""
        linkedin_draft = self.generate_linkedin_post(idea, summary)
        x_draft = self.generate_x_post(idea)
        
        return GeneratedContent(
            core_insight=idea.core_insight,
            why_it_works=idea.why_it_works,
            linkedin_draft=linkedin_draft,
            x_draft=x_draft
        )
    
    def rewrite_linkedin(
        self, 
        original_draft: str, 
        core_insight: str, 
        summary: str
    ) -> str:
        """Rewrite a LinkedIn post with a fresh angle."""
        prompt = REWRITE_LINKEDIN_PROMPT.format(
            original_draft=original_draft,
            core_insight=core_insight,
            summary=summary
        )
        
        try:
            draft = self.llm.complete(prompt, temperature=0.8, max_tokens=1000)
            return self._clean_linkedin_draft(draft)
        except Exception as e:
            logger.error(f"Failed to rewrite LinkedIn post: {e}")
            return original_draft
    
    def rewrite_x(
        self, 
        original_draft: str, 
        core_insight: str
    ) -> str:
        """Rewrite an X post with a fresh angle."""
        prompt = REWRITE_X_PROMPT.format(
            original_draft=original_draft,
            core_insight=core_insight
        )
        
        try:
            draft = self.llm.complete(prompt, temperature=0.9, max_tokens=100)
            return self._clean_x_draft(draft)
        except Exception as e:
            logger.error(f"Failed to rewrite X post: {e}")
            return original_draft
    
    def save_suggestion(
        self, 
        content: GeneratedContent, 
        summary_id: str
    ) -> dict:
        """Save a generated suggestion to the database."""
        suggestion = Suggestion(
            summary_id=summary_id,
            insight=content.core_insight,
            linkedin_draft=content.linkedin_draft,
            x_draft=content.x_draft,
            status=SuggestionStatus.PENDING
        )
        return self.db.save_suggestion(suggestion)
    
    def _clean_linkedin_draft(self, draft: str) -> str:
        """Clean up LinkedIn draft."""
        # Remove any accidental emojis
        import re
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+",
            flags=re.UNICODE
        )
        draft = emoji_pattern.sub('', draft)
        
        # Remove hashtags
        draft = re.sub(r'#\w+', '', draft)
        
        # Clean up extra whitespace
        draft = re.sub(r'\n{3,}', '\n\n', draft)
        
        return draft.strip()
    
    def _clean_x_draft(self, draft: str) -> str:
        """Clean up X draft."""
        import re
        
        # Remove hashtags (unless it feels essential)
        draft = re.sub(r'#\w+\s*', '', draft)
        
        # Remove emojis
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF"
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+",
            flags=re.UNICODE
        )
        draft = emoji_pattern.sub('', draft)
        
        # Ensure under 280 chars
        if len(draft) > 280:
            draft = draft[:277] + "..."
        
        return draft.strip()


# Singleton instance
_generator: Optional[GeneratorService] = None

def get_generator() -> GeneratorService:
    """Get generator service singleton."""
    global _generator
    if _generator is None:
        _generator = GeneratorService()
    return _generator
