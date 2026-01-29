"""
Slack event handling and bot interactions for Chorus.
"""
from slack_bolt.async_app import AsyncApp
from datetime import datetime
import logging
import re
from typing import Optional

from app.config import get_settings
from app.models import SlackMessage, ConversationSummary, GeneratedContent, SuggestionStatus
from app.database import get_database
from app.services.buffer import get_buffer_service
from app.services.summarizer import get_summarizer
from app.services.detector import get_detector
from app.services.generator import get_generator

logger = logging.getLogger(__name__)


class SlackBot:
    """
    Slack bot for Chorus.
    
    Features:
    - Listens to specified channels
    - Sends DMs with suggestions
    - Handles emoji reactions for feedback
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.app = AsyncApp(
            token=self.settings.slack_bot_token,
            signing_secret=self.settings.slack_signing_secret
        )
        self.db = get_database()
        self.buffer_service = get_buffer_service()
        
        # Store suggestion IDs mapped to Slack message timestamps
        self._suggestion_message_map: dict[str, str] = {}
        
        self._register_handlers()
    
    def _register_handlers(self):
        """Register all event handlers."""
        # Single message handler that routes to appropriate handler
        self.app.event("message")(self._handle_all_messages)
        
        # Reaction events
        self.app.event("reaction_added")(self._handle_reaction)
        
        # App mention (commands)
        self.app.event("app_mention")(self._handle_mention)
    
    async def _handle_all_messages(self, event: dict, say, client):
        """Route messages to appropriate handler based on type."""
        # Ignore bot messages
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return
        
        # Route DMs to DM handler
        if event.get("channel_type") == "im":
            await self._handle_dm(event, say, client)
        else:
            # Route channel messages to channel handler
            await self._handle_channel_message(event, say, client)
    
    async def _handle_channel_message(self, event: dict, say, client):
        """Handle incoming messages in channels."""
        # Ignore thread replies (v1)
        if event.get("thread_ts"):
            return
        
        channel_id = event.get("channel")
        
        # Check if we're listening to this channel
        if not self.db.is_listening(channel_id):
            return
        
        # Create message object
        message = SlackMessage(
            message_id=event.get("ts", ""),
            channel_id=channel_id,
            user_id=event.get("user", ""),
            text=event.get("text", ""),
            timestamp=datetime.utcnow()
        )
        
        # Add to buffer
        self.buffer_service.add_message(message)
        logger.debug(f"Captured message in channel {channel_id}")
    
    async def _handle_dm(self, event: dict, say, client):
        """Handle direct messages to the bot."""
        text = event.get("text", "").lower().strip()
        user_id = event.get("user")
        logger.info(f"Processing DM command: '{text}' from user {user_id}")
        
        # Handle "start listening" command
        if "start listening" in text:
            await self._handle_start_listening(event, say, client)
        
        # Handle "stop listening" command
        elif "stop listening" in text:
            await self._handle_stop_listening(event, say, client)
        
        # Handle "status" command
        elif text in ["status", "stats", "info"]:
            await self._handle_status(event, say)
        
        # Handle "saved" command
        elif text in ["saved", "saved posts", "my posts"]:
            logger.info("Handling 'saved' command")
            await self._handle_show_saved(event, say)
        
        else:
            logger.info(f"Unknown DM command: '{text}'")
    
    async def _handle_mention(self, event: dict, say, client):
        """Handle @Chorus mentions."""
        text = event.get("text", "").lower()
        channel_id = event.get("channel")
        user_id = event.get("user")
        
        # Parse command from mention
        if "start listening" in text:
            self.db.add_listening_channel(channel_id, user_id)
            await say(
                text="👀 Got it! I'm now listening to this channel. "
                     "I'll stay quiet and only reach out when I spot something worth posting.",
                channel=channel_id
            )
        
        elif "stop listening" in text:
            self.db.remove_listening_channel(channel_id)
            await say(
                text="Okay, I've stopped listening to this channel.",
                channel=channel_id
            )
        
        elif "status" in text:
            channels = self.db.get_listening_channels()
            suggestions_today = len(self.db.get_suggestions_today())
            await say(
                text=f"📊 *Status*\n"
                     f"• Listening to {len(channels)} channel(s)\n"
                     f"• {suggestions_today} suggestion(s) today\n"
                     f"• Max {self.settings.max_suggestions_per_day} suggestions/day",
                channel=channel_id
            )
    
    async def _handle_start_listening(self, event: dict, say, client):
        """Handle start listening command via DM."""
        user_id = event.get("user")
        
        # Get list of channels user is in
        try:
            result = await client.users_conversations(
                user=user_id,
                types="public_channel,private_channel"
            )
            channels = result.get("channels", [])
            
            if not channels:
                await say("I couldn't find any channels. Invite me to a channel first!")
                return
            
            # Create a simple channel picker message
            channel_list = "\n".join(
                f"• #{ch['name']} (`{ch['id']}`)" 
                for ch in channels[:10]
            )
            
            await say(
                f"Which channel should I listen to?\n\n"
                f"{channel_list}\n\n"
                f"Reply with: `listen to #channel-name` or `listen to CHANNEL_ID`"
            )
            
        except Exception as e:
            logger.error(f"Failed to list channels: {e}")
            await say(
                "To start listening, mention me in a channel with:\n"
                "`@Chorus start listening`"
            )
    
    async def _handle_stop_listening(self, event: dict, say, client):
        """Handle stop listening command via DM."""
        channels = self.db.get_listening_channels()
        
        if not channels:
            await say("I'm not currently listening to any channels.")
            return
        
        for channel_id in channels:
            self.db.remove_listening_channel(channel_id)
        
        await say(f"Stopped listening to {len(channels)} channel(s).")
    
    async def _handle_status(self, event: dict, say):
        """Show bot status."""
        channels = self.db.get_listening_channels()
        suggestions_today = len(self.db.get_suggestions_today())
        saved = len(self.db.get_saved_suggestions(limit=100))
        
        await say(
            f"📊 *Chorus Status*\n\n"
            f"• Listening to {len(channels)} channel(s)\n"
            f"• {suggestions_today}/{self.settings.max_suggestions_per_day} suggestions today\n"
            f"• {saved} saved posts total"
        )
    
    async def _handle_show_saved(self, event: dict, say):
        """Show saved suggestions."""
        saved = self.db.get_saved_suggestions(limit=5)
        
        if not saved:
            await say("No saved posts yet. I'll suggest some when I spot good insights!")
            return
        
        message = "📚 *Your Saved Posts*\n\n"
        for i, s in enumerate(saved, 1):
            insight = s.get("insight", "")[:100]
            message += f"*{i}.* {insight}...\n\n"
        
        await say(message)
    
    async def _handle_reaction(self, event: dict, client):
        """Handle emoji reactions on suggestions."""
        reaction = event.get("reaction")
        item = event.get("item", {})
        message_ts = item.get("ts")
        channel = item.get("channel")
        
        # Find suggestion ID from message timestamp
        suggestion_id = self._suggestion_message_map.get(message_ts)
        if not suggestion_id:
            return
        
        if reaction == "+1" or reaction == "thumbsup":
            # Save the suggestion
            self.db.update_suggestion_status(
                suggestion_id, 
                SuggestionStatus.SAVED
            )
            logger.info(f"Suggestion {suggestion_id} saved")
            
            # Send confirmation
            try:
                await client.chat_postMessage(
                    channel=channel,
                    thread_ts=message_ts,
                    text="✅ Saved! Find it anytime with `saved posts`"
                )
            except Exception as e:
                logger.error(f"Failed to send save confirmation: {e}")
        
        elif reaction == "arrows_counterclockwise" or reaction == "repeat":
            # Rewrite the suggestion
            await self._rewrite_suggestion(suggestion_id, channel, message_ts, client)
        
        elif reaction == "x" or reaction == "negative_squared_cross_mark":
            # Ignore the suggestion
            self.db.update_suggestion_status(
                suggestion_id,
                SuggestionStatus.IGNORED
            )
            logger.info(f"Suggestion {suggestion_id} ignored")
    
    async def _rewrite_suggestion(
        self, 
        suggestion_id: str, 
        channel: str, 
        message_ts: str,
        client
    ):
        """Rewrite a suggestion with fresh angles."""
        suggestion = self.db.get_suggestion(suggestion_id)
        if not suggestion:
            return
        
        # Get the summary for context
        summary_id = suggestion.get("summary_id")
        summary_record = None
        if summary_id:
            # Would need to add get_summary method to db
            pass
        
        generator = get_generator()
        
        # Generate new drafts
        new_linkedin = generator.rewrite_linkedin(
            suggestion.get("linkedin_draft", ""),
            suggestion.get("insight", ""),
            ""  # Summary context if available
        )
        
        new_x = generator.rewrite_x(
            suggestion.get("x_draft", ""),
            suggestion.get("insight", "")
        )
        
        # Send new suggestion
        await self.send_suggestion(
            channel=channel,
            insight=suggestion.get("insight", ""),
            why_it_works="Fresh angle on your earlier insight",
            linkedin_draft=new_linkedin,
            x_draft=new_x,
            suggestion_id=suggestion_id,
            client=client
        )
    
    async def send_suggestion(
        self,
        channel: str,
        insight: str,
        why_it_works: str,
        linkedin_draft: str,
        x_draft: str,
        suggestion_id: str,
        client
    ):
        """Send a suggestion message to the founder."""
        message = self._format_suggestion_message(
            insight=insight,
            why_it_works=why_it_works,
            linkedin_draft=linkedin_draft,
            x_draft=x_draft
        )
        
        try:
            result = await client.chat_postMessage(
                channel=channel,
                text=message,
                mrkdwn=True
            )
            
            # Map message timestamp to suggestion ID for reaction handling
            message_ts = result.get("ts")
            if message_ts:
                self._suggestion_message_map[message_ts] = suggestion_id
            
            logger.info(f"Sent suggestion {suggestion_id} to channel {channel}")
            
        except Exception as e:
            logger.error(f"Failed to send suggestion: {e}")
    
    async def send_dm_suggestion(
        self,
        user_id: str,
        content: GeneratedContent,
        suggestion_id: str,
        client
    ):
        """Send a suggestion via DM to the founder."""
        try:
            # Open DM channel
            result = await client.conversations_open(users=[user_id])
            channel = result["channel"]["id"]
            
            await self.send_suggestion(
                channel=channel,
                insight=content.core_insight,
                why_it_works=content.why_it_works,
                linkedin_draft=content.linkedin_draft,
                x_draft=content.x_draft,
                suggestion_id=suggestion_id,
                client=client
            )
            
        except Exception as e:
            logger.error(f"Failed to send DM suggestion: {e}")
    
    def _format_suggestion_message(
        self,
        insight: str,
        why_it_works: str,
        linkedin_draft: str,
        x_draft: str
    ) -> str:
        """Format the suggestion message per PRD template."""
        return f"""👀 This might be worth posting:

*INSIGHT:*
{insight}

*Why this works:*
{why_it_works}

*LinkedIn Draft:*
---
{linkedin_draft}
---

*X Draft:*
---
{x_draft}
---

React with:
👍 Save   🔁 Rewrite   ❌ Ignore"""
    
    def get_app(self) -> AsyncApp:
        """Get the Slack Bolt app instance."""
        return self.app


# Singleton instance
_slack_bot: Optional[SlackBot] = None

def get_slack_bot() -> SlackBot:
    """Get Slack bot singleton."""
    global _slack_bot
    if _slack_bot is None:
        _slack_bot = SlackBot()
    return _slack_bot
