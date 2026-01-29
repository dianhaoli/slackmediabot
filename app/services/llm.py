"""
OpenAI LLM client wrapper for Chorus bot.
"""
from openai import OpenAI
import json
from typing import Optional

from app.config import get_settings
from app.prompts.templates import SYSTEM_PROMPT


class LLMClient:
    """OpenAI client wrapper with structured output parsing."""
    
    def __init__(self):
        settings = get_settings()
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
    
    def complete(
        self, 
        prompt: str, 
        system_prompt: str = SYSTEM_PROMPT,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """Get a completion from the LLM."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content.strip()
    
    def complete_json(
        self, 
        prompt: str, 
        system_prompt: str = SYSTEM_PROMPT,
        temperature: float = 0.3
    ) -> dict:
        """Get a JSON response from the LLM."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content.strip()
        return json.loads(content)


# Singleton instance
_llm: Optional[LLMClient] = None

def get_llm() -> LLMClient:
    """Get LLM client singleton."""
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm
