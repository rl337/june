"""
Telegram utility functions for streaming text messages.

Provides functions to stream LLM responses character-by-character to Telegram
using the edit_message API, improving perceived response time.
"""
import logging
import asyncio
from typing import Optional
from telegram import Message
from telegram.error import TelegramError, TimedOut, NetworkError

from essence.chat.message_history import get_message_history

logger = logging.getLogger(__name__)

# Telegram message length limit
TELEGRAM_MAX_MESSAGE_LENGTH = 4096


async def stream_text_message(
    message: Message, text: str, update_interval: float = 0.1, chunk_size: int = 1
) -> bool:
    """
    Stream text to a Telegram message character-by-character.

    Updates the message using edit_message API as text is streamed.
    Handles interruptions gracefully and respects Telegram's 4096 character limit.

    Args:
        message: Telegram Message object to update
        text: Text to stream
        update_interval: Minimum time between updates in seconds (default: 0.1)
        chunk_size: Number of characters to add per update (default: 1)

    Returns:
        True if streaming completed successfully, False if interrupted or failed
    """
    if not text:
        return True

    # Truncate if exceeds Telegram limit
    if len(text) > TELEGRAM_MAX_MESSAGE_LENGTH:
        text = text[: TELEGRAM_MAX_MESSAGE_LENGTH - 3] + "..."
        logger.warning(f"Text truncated to {TELEGRAM_MAX_MESSAGE_LENGTH} characters")

    current_text = ""
    last_update_time = asyncio.get_event_loop().time()

    try:
        for i in range(0, len(text), chunk_size):
            # Check for interruption (user sent new message)
            # This is a simple check - in production, you might want more sophisticated interruption handling
            try:
                # Update message with current text
                chunk = text[i : i + chunk_size]
                current_text += chunk

                # Rate limit updates to avoid hitting Telegram API limits
                current_time = asyncio.get_event_loop().time()
                time_since_update = current_time - last_update_time

                if time_since_update >= update_interval:
                    try:
                        await message.edit_text(current_text)
                        last_update_time = current_time
                    except TelegramError as e:
                        # Handle specific Telegram errors
                        if isinstance(e, TimedOut):
                            logger.warning(
                                "Telegram API timeout during streaming, continuing..."
                            )
                            # Continue streaming despite timeout
                            continue
                        elif isinstance(e, NetworkError):
                            logger.warning(
                                "Network error during streaming, continuing..."
                            )
                            continue
                        else:
                            # Other errors (e.g., message not found, too many requests)
                            logger.error(f"Telegram error during streaming: {e}")
                            # Try to send final message
                            try:
                                await message.edit_text(current_text)
                            except:
                                pass
                            return False

                # Small delay to allow other tasks to run
                await asyncio.sleep(0.01)

            except asyncio.CancelledError:
                # Task was cancelled (interrupted)
                logger.info("Streaming interrupted by cancellation")
                # Try to save current progress
                try:
                    await message.edit_text(
                        current_text if current_text else text[:100] + "..."
                    )
                except:
                    pass
                return False
            except Exception as e:
                logger.error(f"Unexpected error during streaming: {e}", exc_info=True)
                # Try to save current progress
                try:
                    await message.edit_text(
                        current_text if current_text else text[:100] + "..."
                    )
                except:
                    pass
                return False

        # Final update to ensure complete message is shown
        if current_text != text:
            try:
                await message.edit_text(text)
                # Track final message in history
                try:
                    user_id = str(message.chat.id) if message.chat else None
                    chat_id = str(message.chat.id) if message.chat else None
                    if user_id and chat_id:
                        get_message_history().add_message(
                            platform="telegram",
                            user_id=user_id,
                            chat_id=chat_id,
                            message_content=text,
                            message_type="text",
                            message_id=str(message.message_id) if message else None,
                            raw_text=text,
                            rendering_metadata={"streamed": True, "final_update": True},
                        )
                except Exception as e:
                    logger.debug(f"Failed to track final streamed message: {e}")
            except TelegramError as e:
                logger.warning(f"Failed final update: {e}, but streaming completed")

        return True

    except Exception as e:
        logger.error(f"Critical error in stream_text_message: {e}", exc_info=True)
        # Try to send whatever we have
        try:
            await message.edit_text(
                current_text if current_text else text[:100] + "..."
            )
        except:
            pass
        return False


async def stream_llm_response_to_telegram(
    message: Message,
    llm_stream,
    prefix: str = "",
    suffix: str = "",
    update_interval: float = 0.1,
) -> tuple[str, bool]:
    """
    Stream LLM response to Telegram message.

    Convenience function that combines LLM streaming with Telegram message updates.

    Args:
        message: Telegram Message object to update
        llm_stream: AsyncGenerator from LLM client (e.g., chat_stream)
        prefix: Optional prefix text to show before streaming starts
        suffix: Optional suffix text to append after streaming completes
        update_interval: Minimum time between updates in seconds

    Returns:
        Tuple of (final_response_text, success)
    """
    accumulated_text = prefix if prefix else ""
    last_update_time = asyncio.get_event_loop().time()
    chunk_buffer = ""

    try:
        async for chunk in llm_stream:
            if not chunk:
                continue

            chunk_buffer += chunk
            accumulated_text += chunk

            # Check if we've exceeded Telegram's limit
            full_text = accumulated_text + suffix
            if len(full_text) > TELEGRAM_MAX_MESSAGE_LENGTH:
                # Truncate and add ellipsis
                max_len = TELEGRAM_MAX_MESSAGE_LENGTH - len(suffix) - 3
                accumulated_text = accumulated_text[:max_len] + "..."
                logger.warning("LLM response truncated to fit Telegram limit")
                break

            # Rate limit updates
            current_time = asyncio.get_event_loop().time()
            time_since_update = current_time - last_update_time

            if time_since_update >= update_interval and chunk_buffer:
                try:
                    display_text = accumulated_text + suffix
                    await message.edit_text(display_text)
                    last_update_time = current_time
                    chunk_buffer = ""  # Clear buffer after update
                except TelegramError as e:
                    if isinstance(e, (TimedOut, NetworkError)):
                        logger.warning(
                            f"Telegram API issue during streaming: {e}, continuing..."
                        )
                        # Continue accumulating text
                    else:
                        logger.error(f"Telegram error during LLM streaming: {e}")
                        # Try to continue, but log the error
                except Exception as e:
                    logger.error(
                        f"Unexpected error during LLM streaming: {e}", exc_info=True
                    )

            # Small delay to allow other tasks
            await asyncio.sleep(0.01)

        # Final update with complete text
        final_text = accumulated_text + suffix
        if len(final_text) > TELEGRAM_MAX_MESSAGE_LENGTH:
            final_text = final_text[: TELEGRAM_MAX_MESSAGE_LENGTH - 3] + "..."

        try:
            await message.edit_text(final_text)
            # Track final message in history
            try:
                user_id = str(message.chat.id) if message.chat else None
                chat_id = str(message.chat.id) if message.chat else None
                if user_id and chat_id:
                    get_message_history().add_message(
                        platform="telegram",
                        user_id=user_id,
                        chat_id=chat_id,
                        message_content=final_text,
                        message_type="text",
                        message_id=str(message.message_id) if message else None,
                        raw_text=accumulated_text,
                        formatted_text=final_text,
                        rendering_metadata={
                            "streamed": True,
                            "llm_response": True,
                            "final_update": True,
                        },
                    )
            except Exception as e:
                logger.debug(f"Failed to track final LLM streamed message: {e}")
        except TelegramError as e:
            logger.warning(f"Failed final update: {e}")

        return accumulated_text, True

    except asyncio.CancelledError:
        logger.info("LLM streaming interrupted")
        # Try to save current progress
        final_text = accumulated_text + suffix
        if len(final_text) > TELEGRAM_MAX_MESSAGE_LENGTH:
            final_text = final_text[: TELEGRAM_MAX_MESSAGE_LENGTH - 3] + "..."
        try:
            await message.edit_text(final_text if accumulated_text else prefix + "...")
        except:
            pass
        return accumulated_text, False
    except Exception as e:
        logger.error(f"Error streaming LLM response: {e}", exc_info=True)
        # Try to save whatever we have
        final_text = accumulated_text + suffix
        if len(final_text) > TELEGRAM_MAX_MESSAGE_LENGTH:
            final_text = final_text[: TELEGRAM_MAX_MESSAGE_LENGTH - 3] + "..."
        try:
            await message.edit_text(
                final_text if accumulated_text else prefix + "Error occurred"
            )
        except:
            pass
        return accumulated_text, False
