"""
Configuration settings for Chorus bot.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Slack
    slack_bot_token: str
    slack_signing_secret: str
    slack_app_token: str
    
    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-4o-mini-2024-07-18"
    
    # Supabase
    supabase_url: str
    supabase_key: str
    
    # Bot behavior
    buffer_window_minutes: int = 60
    min_messages_for_summary: int = 8
    max_suggestions_per_day: int = 3
    
    # Target founder
    founder_user_id: str
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
