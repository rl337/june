"""Worker process for processing voice messages from NATS queue.

Note: This worker is optional and requires NATS. NATS is not available for MVP.
This worker will not function without NATS. Set USE_VOICE_QUEUE=false to disable
queue processing and use direct processing instead.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

from essence.services.telegram.voice_queue import VoiceMessageQueue, create_worker_subscription
from essence.services.telegram.handlers.voice import handle_voice_message_from_queue
from essence.services.telegram.dependencies.config import get_service_config, get_stt_address, get_metrics_storage

# Setup logging
from inference_core import setup_logging, config
setup_logging(config.monitoring.log_level, "telegram-worker")
logger = logging.getLogger(__name__)

# Global bot application instance (will be initialized in main)
bot_application = None


async def process_voice_message(msg_data: dict):
    """Process a voice message from the queue.
    
    Args:
        msg_data: Message data dict with voice_file_id, user_id, chat_id, audio_data, metadata
    """
    # Import here to avoid circular dependencies
    from telegram import Update, Voice, Bot
    from telegram.ext import ContextTypes
    
    if not bot_application:
        logger.error("Bot application not initialized")
        return
    
    # Create update object with real bot
    update = Update(
        update_id=msg_data.get('metadata', {}).get('update_id', 0),
        message=None
    )
    
    # Create a message-like object
    from telegram import Message, User, Chat
    from datetime import datetime
    
    user = User(
        id=int(msg_data['user_id']),
        is_bot=False,
        first_name="User"
    )
    
    chat = Chat(
        id=int(msg_data['chat_id']),
        type="private"
    )
    
    voice = Voice(
        file_id=msg_data['voice_file_id'],
        file_unique_id=msg_data['voice_file_id'],
        duration=None,
        file_size=len(msg_data['audio_data'])
    )
    
    message = Message(
        message_id=msg_data.get('metadata', {}).get('message_id', 0),
        from_user=user,
        date=datetime.now(),
        chat=chat,
        voice=voice
    )
    
    update.message = message
    update.effective_user = user
    update.effective_chat = chat
    
    # Create context with real bot
    context = ContextTypes.DEFAULT_TYPE()
    context.bot = bot_application.bot
    
    # Get config and addresses
    service_config = get_service_config()
    stt_address = get_stt_address()
    metrics_storage = get_metrics_storage()
    
    # Process the voice message
    await handle_voice_message_from_queue(
        update=update,
        context=context,
        config=service_config,
        stt_address=stt_address,
        get_metrics_storage=lambda: metrics_storage,
        audio_data=msg_data['audio_data'],
        metadata=msg_data.get('metadata', {})
    )


async def main():
    """Main worker entry point."""
    global bot_application
    
    worker_id = os.getenv("WORKER_ID", f"worker-{os.getpid()}")
    nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
    
    logger.info(f"Starting voice message worker: {worker_id}")
    logger.info(f"Connecting to NATS: {nats_url}")
    
    # Initialize Telegram bot application for sending messages
    from telegram.ext import Application
    from dependencies.config import get_service_config
    
    service_config = get_service_config()
    if not service_config.bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
    
    bot_application = Application.builder().token(service_config.bot_token).build()
    await bot_application.initialize()
    
    logger.info("Telegram bot application initialized")
    
    queue = VoiceMessageQueue(nats_url=nats_url)
    
    try:
        await create_worker_subscription(
            queue=queue,
            process_callback=process_voice_message,
            worker_id=worker_id
        )
    except KeyboardInterrupt:
        logger.info(f"Worker {worker_id} shutting down...")
    except Exception as e:
        logger.error(f"Worker {worker_id} fatal error: {e}", exc_info=True)
        raise
    finally:
        await queue.disconnect()
        if bot_application:
            await bot_application.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
