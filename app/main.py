"""
Chorus - Main FastAPI application.
A Slack bot that turns founder conversations into LinkedIn/X post suggestions.
"""
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager
import logging
import asyncio

from app.config import get_settings
from app.slack_handler import get_slack_bot
from app.services.pipeline import get_pipeline
from app.database import get_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Scheduler for background jobs
scheduler = AsyncIOScheduler()

# Socket mode handler (will be initialized in lifespan)
socket_handler = None


async def scheduled_pipeline_run():
    """
    Background job to process channels periodically.
    Runs every 60 minutes by default.
    """
    logger.info("Running scheduled pipeline...")
    
    try:
        pipeline = get_pipeline()
        settings = get_settings()
        slack_bot = get_slack_bot()
        
        # Process all channels
        suggestions = await pipeline.process_all_channels()
        
        if suggestions:
            logger.info(f"Generated {len(suggestions)} suggestion(s)")
            
            # Send suggestions to founder
            for suggestion in suggestions:
                content = suggestion.get("content")
                if content:
                    await slack_bot.send_dm_suggestion(
                        user_id=settings.founder_user_id,
                        content=content,
                        suggestion_id=suggestion.get("id", ""),
                        client=slack_bot.app.client
                    )
        else:
            logger.info("No suggestions generated this run")
            
    except Exception as e:
        logger.error(f"Pipeline run failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global socket_handler
    
    # Startup
    logger.info("Starting Chorus bot...")
    
    settings = get_settings()
    slack_bot = get_slack_bot()
    
    # Start Socket Mode handler for Slack events
    socket_handler = AsyncSocketModeHandler(
        slack_bot.get_app(),
        settings.slack_app_token
    )
    asyncio.create_task(socket_handler.start_async())
    logger.info("Socket Mode handler started - Slack events are now being received!")
    
    # Schedule the pipeline to run periodically
    scheduler.add_job(
        scheduled_pipeline_run,
        "interval",
        minutes=settings.buffer_window_minutes,
        id="pipeline_run",
        replace_existing=True
    )
    scheduler.start()
    logger.info(f"Scheduler started (interval: {settings.buffer_window_minutes} min)")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Chorus bot...")
    if socket_handler:
        await socket_handler.close_async()
    scheduler.shutdown()


# Create FastAPI app
app = FastAPI(
    title="Chorus",
    description="Slack bot that turns founder conversations into post suggestions",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================================
# Routes
# ============================================================

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "Chorus"}


@app.get("/health")
async def health():
    """Detailed health check."""
    settings = get_settings()
    db = get_database()
    
    return {
        "status": "healthy",
        "listening_channels": len(db.get_listening_channels()),
        "suggestions_today": len(db.get_suggestions_today()),
        "max_daily_suggestions": settings.max_suggestions_per_day
    }


@app.post("/api/trigger")
async def trigger_pipeline(background_tasks: BackgroundTasks):
    """
    Manually trigger the content pipeline.
    Useful for testing or forcing a run.
    """
    background_tasks.add_task(scheduled_pipeline_run)
    return {"status": "triggered", "message": "Pipeline run queued"}


@app.get("/api/channels")
async def list_channels():
    """List channels the bot is listening to."""
    db = get_database()
    channels = db.get_listening_channels()
    return {"channels": channels, "count": len(channels)}


@app.post("/api/channels/{channel_id}")
async def add_channel(channel_id: str):
    """Add a channel to listen to."""
    db = get_database()
    settings = get_settings()
    db.add_listening_channel(channel_id, settings.founder_user_id)
    return {"status": "added", "channel_id": channel_id}


@app.delete("/api/channels/{channel_id}")
async def remove_channel(channel_id: str):
    """Remove a channel from listening."""
    db = get_database()
    db.remove_listening_channel(channel_id)
    return {"status": "removed", "channel_id": channel_id}


@app.get("/api/suggestions")
async def list_suggestions(status: str = None, limit: int = 10):
    """List suggestions, optionally filtered by status."""
    db = get_database()
    
    if status == "saved":
        suggestions = db.get_saved_suggestions(limit=limit)
    else:
        suggestions = db.get_suggestions_today()
    
    return {"suggestions": suggestions, "count": len(suggestions)}


@app.get("/api/suggestions/{suggestion_id}")
async def get_suggestion(suggestion_id: str):
    """Get a specific suggestion."""
    db = get_database()
    suggestion = db.get_suggestion(suggestion_id)
    
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    
    return suggestion


@app.get("/api/debug")
async def debug_status():
    """Debug endpoint showing buffer and message status."""
    from app.services.buffer import get_buffer_service
    
    db = get_database()
    settings = get_settings()
    buffer_service = get_buffer_service()
    
    channels = db.get_listening_channels()
    channel_status = []
    
    for channel_id in channels:
        messages = buffer_service.get_buffer_from_db(channel_id)
        channel_status.append({
            "channel_id": channel_id,
            "message_count": len(messages),
            "min_required": settings.min_messages_for_summary,
            "ready_to_summarize": buffer_service.should_summarize(channel_id),
            "recent_messages": [
                {"user": m.user_id[-4:], "text": m.text[:50] + "..." if len(m.text) > 50 else m.text}
                for m in messages[-5:]  # Show last 5 messages
            ]
        })
    
    return {
        "listening_channels": len(channels),
        "min_messages_for_summary": settings.min_messages_for_summary,
        "buffer_window_minutes": settings.buffer_window_minutes,
        "channels": channel_status
    }


@app.post("/api/trigger/force")
async def force_trigger_pipeline(background_tasks: BackgroundTasks):
    """
    Force trigger pipeline even with fewer messages (for testing).
    Temporarily lowers threshold to 1 message.
    """
    from app.services.buffer import get_buffer_service
    from app.services.summarizer import get_summarizer
    from app.services.detector import get_detector
    from app.services.generator import get_generator
    from app.models import SummaryMetadata
    
    settings = get_settings()
    db = get_database()
    buffer_service = get_buffer_service()
    summarizer = get_summarizer()
    detector = get_detector()
    generator = get_generator()
    slack_bot = get_slack_bot()
    
    channels = db.get_listening_channels()
    results = []
    
    for channel_id in channels:
        messages = buffer_service.get_buffer_from_db(channel_id)
        if not messages:
            results.append({"channel": channel_id, "status": "no messages"})
            continue
        
        logger.info(f"Force processing {len(messages)} messages from {channel_id}")
        
        # Summarize
        summary = summarizer.summarize_conversation(messages)
        if not summary:
            results.append({"channel": channel_id, "status": "summarization failed"})
            continue
        
        # Save summary
        metadata = SummaryMetadata(
            key_ideas=summary.key_ideas,
            opinions=summary.opinions,
            decisions=summary.decisions,
            interesting_phrases=summary.interesting_phrases,
            message_count=len(messages),
            window_start=messages[0].timestamp,
            window_end=messages[-1].timestamp
        )
        summary_record = db.save_summary(channel_id, summary.summary, metadata)
        
        # Clear buffer
        buffer_service.clear_buffer(channel_id)
        
        # Detect post-worthy
        detection = detector.detect_post_worthy(summary)
        if not detection.is_post_worthy:
            results.append({
                "channel": channel_id, 
                "status": "no post-worthy insights",
                "summary": summary.summary[:200]
            })
            continue
        
        # Generate content
        for idea in detection.ideas[:1]:  # Just first idea for testing
            content = generator.generate_content(idea, summary.summary)
            saved = generator.save_suggestion(content, summary_record.get("id"))
            
            # Send DM
            await slack_bot.send_dm_suggestion(
                user_id=settings.founder_user_id,
                content=content,
                suggestion_id=saved.get("id", ""),
                client=slack_bot.app.client
            )
            
            results.append({
                "channel": channel_id,
                "status": "suggestion sent!",
                "insight": idea.core_insight
            })
    
    return {"results": results}


# ============================================================
# Error Handlers
# ============================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )


# ============================================================
# Main Entry Point
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=3000,
        reload=True
    )
