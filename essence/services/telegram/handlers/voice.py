"""Voice message handler for Telegram bot."""
import io
import logging
import tempfile
import os
import sys
import time
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from pathlib import Path

import grpc.aio
import librosa
from pydub import AudioSegment
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import (
    TelegramError,
    TimedOut,
    NetworkError,
    BadRequest,
    RetryAfter,
    Conflict,
)

from essence.services.telegram.conversation_storage import ConversationStorage
from essence.services.telegram.language_preferences import (
    get_supported_languages,
    is_language_supported,
    DEFAULT_LANGUAGE,
)
import re

from essence.services.telegram.cost_tracking import (
    calculate_stt_cost,
    calculate_tts_cost,
    calculate_llm_cost,
    record_cost,
    get_conversation_id_from_user_chat,
)

from essence.services.telegram.audio_utils import (
    enhance_audio_for_stt,
    prepare_audio_for_stt,  # Keep for backward compatibility
    AudioValidationError,
    MAX_AUDIO_DURATION_SECONDS,
    MAX_AUDIO_SIZE_BYTES,
    export_audio_to_ogg_optimized,
    find_optimal_compression,
)

from essence.chat.utils.tracing import get_tracer
from opentelemetry import trace

# Import metrics
from essence.services.shared_metrics import (
    GRPC_REQUESTS_TOTAL,
    GRPC_REQUEST_DURATION_SECONDS,
    VOICE_MESSAGES_PROCESSED_TOTAL,
    VOICE_PROCESSING_DURATION_SECONDS,
    STT_TRANSCRIPTION_DURATION_SECONDS,
    TTS_SYNTHESIS_DURATION_SECONDS,
    LLM_GENERATION_DURATION_SECONDS,
    ERRORS_TOTAL,
)
from essence.services.grpc_metrics import record_grpc_call

PLATFORM = "telegram"
SERVICE_NAME = "telegram"

if TYPE_CHECKING:
    from june_grpc_api import asr as asr_shim

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


def is_transient_telegram_error(error: Exception) -> bool:
    """
    Determine if a Telegram API error is transient (retryable).

    Transient errors include:
    - Rate limit errors (RetryAfter, 429)
    - Network errors (NetworkError, TimedOut)
    - Temporary server errors (5xx)

    Permanent errors include:
    - BadRequest (400) - invalid file, too large, etc.
    - Conflict (409) - message conflicts
    - Other client errors (4xx)

    Args:
        error: Exception from Telegram API

    Returns:
        True if error is transient and retryable, False otherwise
    """
    if isinstance(error, RetryAfter):
        return True  # Rate limit - definitely retryable
    if isinstance(error, (NetworkError, TimedOut)):
        return True  # Network issues - retryable
    if isinstance(error, BadRequest):
        # BadRequest can be permanent (invalid file) or transient (temporary API issue)
        # Check error message for clues
        error_msg = str(error).lower()
        # Permanent: file too large, invalid format, duration limits
        if any(
            keyword in error_msg
            for keyword in ["too large", "too long", "invalid", "format", "duration"]
        ):
            return False
        # Otherwise, might be transient API issue
        return True
    if isinstance(error, Conflict):
        return False  # Conflict errors are usually permanent
    if isinstance(error, TelegramError):
        # Check if it's a 5xx server error (transient) vs 4xx client error (permanent)
        # TelegramError doesn't expose status code directly, so we check the message
        error_msg = str(error).lower()
        if (
            "500" in error_msg
            or "502" in error_msg
            or "503" in error_msg
            or "504" in error_msg
        ):
            return True
        if (
            "400" in error_msg
            or "401" in error_msg
            or "403" in error_msg
            or "404" in error_msg
        ):
            return False
    # Default: assume non-retryable for unknown errors
    return False


def get_telegram_error_message(error: Exception, transcript: str = "") -> str:
    """
    Get user-friendly error message for Telegram API errors.

    Args:
        error: Exception from Telegram API
        transcript: Optional transcript text for context

    Returns:
        User-friendly error message
    """
    if isinstance(error, RetryAfter):
        retry_after = getattr(error, "retry_after", None)
        if retry_after:
            return (
                f"⏱️ **Rate limit reached:**\n\n"
                f"Telegram API is temporarily limiting requests. Please wait {retry_after} seconds and try again."
            )
        return (
            "⏱️ **Rate limit reached:**\n\n"
            "Telegram API is temporarily limiting requests. Please wait a moment and try again."
        )

    if isinstance(error, (NetworkError, TimedOut)):
        return (
            "🔌 **Network error:**\n\n"
            "Unable to connect to Telegram servers. This might be due to:\n"
            "• Network connectivity issues\n"
            "• Telegram servers temporarily unavailable\n\n"
            "Please check your connection and try again."
        )

    if isinstance(error, BadRequest):
        error_msg = str(error).lower()
        if "too large" in error_msg or "file size" in error_msg:
            return (
                "❌ **File too large:**\n\n"
                "The voice message file exceeds Telegram's size limit. "
                "Please try with a shorter message or contact support if this persists."
            )
        if "too long" in error_msg or "duration" in error_msg:
            return (
                "❌ **Message too long:**\n\n"
                "The voice message duration exceeds Telegram's limit. "
                "Please try with a shorter message."
            )
        if "invalid" in error_msg or "format" in error_msg:
            return (
                "❌ **Invalid audio format:**\n\n"
                "The audio file format is not supported by Telegram. "
                "Please try again or contact support."
            )
        return (
            f"❌ **Invalid request:**\n\n"
            f"Telegram API rejected the request: {str(error)}\n\n"
            "Please try again. If the problem persists, contact support."
        )

    if isinstance(error, Conflict):
        return (
            "⚠️ **Conflict error:**\n\n"
            "There was a conflict with the Telegram API. Please try again."
        )

    # Generic error message
    return (
        f"❌ **Failed to send voice response:**\n\n"
        f"An error occurred: {str(error)}\n\n"
        "Please try again. If the problem persists, contact support."
    )


async def send_voice_with_error_handling(
    update: Update,
    ogg_audio_path: str,
    transcript: str,
    status_msg,
    max_retries: int = 3,
) -> bool:
    """
    Send voice message to Telegram with comprehensive error handling and retry logic.

    This function:
    - Handles transient errors (rate limits, network issues) with retry logic
    - Provides user-friendly error messages for different error types
    - Logs all errors with full context
    - Ensures temporary files are cleaned up even on failure

    Args:
        update: Telegram Update object
        ogg_audio_path: Path to OGG audio file to send
        transcript: Transcript text for caption/context
        status_msg: Status message object to update with error messages
        max_retries: Maximum number of retry attempts for transient errors (default: 3)

    Returns:
        True if voice message was sent successfully, False otherwise
    """
    user_id = update.effective_user.id if update.effective_user else "unknown"
    chat_id = update.effective_chat.id if update.effective_chat else "unknown"
    ogg_file_size = (
        os.path.getsize(ogg_audio_path) if os.path.exists(ogg_audio_path) else 0
    )

    # Track retry attempts for detailed logging (use mutable container to persist across retries)
    retry_attempts = {"count": 0}

    async def _send_voice():
        """Inner function to send voice - will be retried for transient errors."""
        retry_attempts["count"] += 1
        attempt_num = retry_attempts["count"]

        try:
            # Create informative caption with transcript preview
            caption = None
            if transcript:
                # Format caption with transcript preview (Telegram caption limit is 1024 chars, using 180 for preview)
                transcript_preview = (
                    transcript[:180] + "..." if len(transcript) > 180 else transcript
                )
                caption = f"🎤 Response to:\n\n{transcript_preview}"

            with open(ogg_audio_path, "rb") as audio_file:
                await update.message.reply_voice(voice=audio_file, caption=caption)

            logger.info(
                f"Voice response sent successfully (attempt {attempt_num}): "
                f"file_size={ogg_file_size / 1024:.1f} KB, "
                f"user_id={user_id}, "
                f"chat_id={chat_id}, "
                f"transcript_length={len(transcript) if transcript else 0}"
            )
            return True
        except Exception as e:
            # Log retry attempt with detailed context
            if is_transient_telegram_error(e) and attempt_num <= max_retries:
                # Calculate delay for next retry (exponential backoff: 1s, 2s, 4s)
                delay = min(1.0 * (2.0 ** (attempt_num - 1)), 60.0)
                logger.warning(
                    f"Telegram API transient error on attempt {attempt_num}/{max_retries + 1}: "
                    f"error_type={type(e).__name__}, "
                    f"error={str(e)}, "
                    f"user_id={user_id}, "
                    f"chat_id={chat_id}, "
                    f"retrying_after={delay:.2f}s"
                )
            elif not is_transient_telegram_error(e):
                # Non-retryable error - log immediately
                logger.error(
                    f"Telegram API non-retryable error on attempt {attempt_num}: "
                    f"error_type={type(e).__name__}, "
                    f"error={str(e)}, "
                    f"user_id={user_id}, "
                    f"chat_id={chat_id}"
                )
            raise

    # Ensure status message is set at the start (in case function is called without setting it)
    try:
        await status_msg.edit_text("🔄 Sending voice response...")
    except Exception:
        # If status message update fails, log but continue
        logger.warning(
            "Failed to update status message at start of send_voice_with_error_handling"
        )

    try:
        # Custom retry logic that uses is_transient_telegram_error for accurate error classification
        # This ensures 5xx server errors and other transient errors are properly retried
        import asyncio
        import random

        last_exception = None
        delay = 1.0  # Initial delay: 1s

        for attempt in range(max_retries + 1):
            try:
                result = await _send_voice()
                # Success - update status and return
                await status_msg.edit_text("✅ Voice response sent!")

                # Optional: Clean up status message after a short delay (3 seconds)
                # This provides user feedback but doesn't clutter the chat
                try:
                    await asyncio.sleep(3)
                    await status_msg.delete()
                except Exception:
                    # If deletion fails (e.g., message already deleted), just log and continue
                    logger.debug(
                        "Status message cleanup skipped (may have been deleted already)"
                    )

                return True
            except Exception as e:
                last_exception = e

                # Check if error is transient using our classification function
                if is_transient_telegram_error(e):
                    # If this was the last attempt, raise the exception
                    if attempt >= max_retries:
                        logger.error(
                            f"Telegram API transient error after {max_retries} retries: "
                            f"error_type={type(e).__name__}, "
                            f"error={str(e)}, "
                            f"user_id={user_id}, "
                            f"chat_id={chat_id}",
                            exc_info=True,
                        )
                        raise

                    # Calculate delay with exponential backoff (1s, 2s, 4s)
                    delay = min(1.0 * (2.0**attempt), 60.0)
                    # Add small jitter to avoid thundering herd
                    jitter = delay * 0.1 * random.random()
                    delay = delay + jitter

                    # Update status message with progress indicator for retry
                    try:
                        await status_msg.edit_text(
                            f"🔄 Sending voice response...\n"
                            f"_Retrying after error (attempt {attempt + 1}/{max_retries + 1})_"
                        )
                    except Exception:
                        # If status update fails, log but continue
                        logger.debug("Failed to update status message during retry")

                    # Log retry attempt (already logged in _send_voice, but log here too for clarity)
                    logger.warning(
                        f"Retrying Telegram API call after {delay:.2f}s "
                        f"(attempt {attempt + 1}/{max_retries + 1}): "
                        f"error_type={type(e).__name__}, "
                        f"user_id={user_id}, "
                        f"chat_id={chat_id}"
                    )

                    # Wait before retrying
                    await asyncio.sleep(delay)
                else:
                    # Non-retryable error - fail immediately
                    logger.error(
                        f"Telegram API non-retryable error: "
                        f"error_type={type(e).__name__}, "
                        f"error={str(e)}, "
                        f"user_id={user_id}, "
                        f"chat_id={chat_id}",
                        exc_info=True,
                    )
                    raise

        # Should never reach here, but handle it just in case
        if last_exception:
            raise last_exception
        raise RuntimeError("Retry logic failed unexpectedly")

    except RetryAfter as e:
        # Rate limit error - all retries exhausted
        logger.error(
            f"Telegram API rate limit error after {max_retries} retries: {e}",
            exc_info=True,
        )
        error_message = get_telegram_error_message(e, transcript)
        await status_msg.edit_text(error_message)
        return False

    except (NetworkError, TimedOut) as e:
        # Network/timeout error - all retries exhausted
        logger.error(
            f"Telegram API network/timeout error after {max_retries} retries: {e}",
            exc_info=True,
        )
        error_message = get_telegram_error_message(e, transcript)
        await status_msg.edit_text(error_message)
        return False

    except BadRequest as e:
        # Bad request - permanent error, don't retry
        logger.error(f"Telegram API bad request error (permanent): {e}", exc_info=True)
        error_message = get_telegram_error_message(e, transcript)
        await status_msg.edit_text(error_message)
        return False

    except Conflict as e:
        # Conflict error - permanent
        logger.error(f"Telegram API conflict error: {e}", exc_info=True)
        error_message = get_telegram_error_message(e, transcript)
        await status_msg.edit_text(error_message)
        return False

    except TelegramError as e:
        # Other Telegram errors
        logger.error(f"Telegram API error: {e}", exc_info=True)
        error_message = get_telegram_error_message(e, transcript)
        await status_msg.edit_text(error_message)
        return False

    except Exception as e:
        # Unexpected errors
        logger.error(f"Unexpected error sending voice response: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ **Failed to send voice response:**\n\n"
            f"An unexpected error occurred: {str(e)}\n\n"
            "Please try again. If the problem persists, contact support."
        )
        return False


def handle_voice_language_command(
    transcript: str, user_id: str, chat_id: str
) -> tuple[bool, str]:
    """
    Handle voice command for changing language.

    Supports patterns like:
    - "change language to Spanish"
    - "set language to es"
    - "switch language to French"
    - "change language to español"

    Args:
        transcript: The transcribed text
        user_id: Telegram user ID
        chat_id: Telegram chat ID

    Returns:
        Tuple of (is_command, response_message)
        If is_command is True, the language was changed and response_message contains confirmation
        If is_command is False, response_message is empty
    """
    # Normalize transcript to lowercase for matching
    transcript_lower = transcript.lower().strip()

    # Pattern to match language change commands
    # Matches: "change/set/switch language to <language>"
    patterns = [
        r"(?:change|set|switch)\s+language\s+to\s+(\w+)",
        r"language\s+(?:change|set|switch)\s+to\s+(\w+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, transcript_lower)
        if match:
            language_input = match.group(1).strip()

            # Try to match language by code or name
            supported = get_supported_languages()
            language_code = None

            # First, try direct code match (e.g., "es", "en")
            if is_language_supported(language_input):
                language_code = language_input.lower()
            else:
                # Try to match by language name (case-insensitive)
                for code, name in supported.items():
                    if name.lower() == language_input.lower():
                        language_code = code
                        break
                    # Also check common variations
                    if (
                        language_input.lower() in name.lower()
                        or name.lower() in language_input.lower()
                    ):
                        language_code = code
                        break

            if language_code:
                # Set language preference
                if ConversationStorage.set_language_preference(
                    user_id, chat_id, language_code
                ):
                    lang_name = supported[language_code]
                    return (
                        True,
                        f"✅ Language changed to **{lang_name}** ({language_code})",
                    )
                else:
                    return True, "❌ Failed to change language. Please try again."
            else:
                # Language not found
                lang_list = ", ".join(
                    [f"{code} ({name})" for code, name in sorted(supported.items())]
                )
                return (
                    True,
                    f"❌ Language '{language_input}' not recognized.\n\nSupported languages: {lang_list}",
                )

    return False, ""


async def handle_voice_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    config,
    stt_address: str,
    get_metrics_storage,
):
    """Handle incoming voice messages - publishes to queue if enabled, otherwise processes directly.

    This function:
    1. Validates Telegram Voice message type
    2. Extracts voice file metadata (file_id, duration, file_size, mime_type)
    3. Validates file size and duration limits
    4. Downloads voice file from Telegram's servers
    5. Processes the voice message (queued or direct)
    """
    # Extract voice message from Telegram Update
    if not update.message or not update.message.voice:
        logger.warning(
            f"Received update without voice message: update_id={update.update_id}"
        )
        return

    voice = update.message.voice

    # Extract and log voice message metadata
    voice_metadata = {
        "file_id": voice.file_id,
        "duration": getattr(voice, "duration", None),
        "file_size": getattr(voice, "file_size", None),
        "mime_type": getattr(voice, "mime_type", None),
        "file_unique_id": getattr(voice, "file_unique_id", None),
    }
    logger.info(
        f"Received voice message: file_id={voice_metadata['file_id']}, "
        f"duration={voice_metadata['duration']}s, "
        f"file_size={voice_metadata['file_size']} bytes, "
        f"mime_type={voice_metadata['mime_type']}"
    )

    # Validate file size limits
    # Check against both config.max_file_size and MAX_AUDIO_SIZE_BYTES
    max_file_size = min(
        config.max_file_size
        if hasattr(config, "max_file_size")
        else MAX_AUDIO_SIZE_BYTES,
        MAX_AUDIO_SIZE_BYTES,
    )

    if voice_metadata["file_size"] is not None:
        if voice_metadata["file_size"] > max_file_size:
            await update.message.reply_text(
                f"❌ Voice message too large. Maximum size: {max_file_size / (1024 * 1024):.1f} MB\n"
                f"Your file: {voice_metadata['file_size'] / (1024 * 1024):.1f} MB"
            )
            logger.warning(
                f"Voice message rejected: file_size={voice_metadata['file_size']} bytes "
                f"exceeds limit={max_file_size} bytes"
            )
            return
    elif voice_metadata["file_size"] is None:
        # File size not provided by Telegram - we'll validate after download
        logger.debug(
            "Voice message file_size not provided by Telegram, will validate after download"
        )

    # Validate duration limits (early validation using Telegram's duration if available)
    if voice_metadata["duration"] is not None:
        if voice_metadata["duration"] > MAX_AUDIO_DURATION_SECONDS:
            await update.message.reply_text(
                f"❌ Voice message too long. Maximum duration: {MAX_AUDIO_DURATION_SECONDS:.0f} seconds\n"
                f"Your message: {voice_metadata['duration']:.0f} seconds"
            )
            logger.warning(
                f"Voice message rejected: duration={voice_metadata['duration']}s "
                f"exceeds limit={MAX_AUDIO_DURATION_SECONDS}s"
            )
            return
        elif voice_metadata["duration"] < 0.1:
            await update.message.reply_text(
                "❌ Voice message too short. Minimum duration: 0.1 seconds"
            )
            logger.warning(
                f"Voice message rejected: duration={voice_metadata['duration']}s "
                f"below minimum=0.1s"
            )
            return
    elif voice_metadata["duration"] is None:
        # Duration not provided by Telegram - we'll validate after processing
        logger.debug(
            "Voice message duration not provided by Telegram, will validate after processing"
        )

    # Check if queue processing is enabled
    use_queue = os.getenv("USE_VOICE_QUEUE", "false").lower() == "true"

    if use_queue:
        # Publish to queue for async processing
        try:
            from essence.services.telegram.voice_queue import VoiceMessageQueue

            # Download voice file
            with tracer.start_as_current_span("voice.download") as span:
                span.set_attribute("voice.file_id", voice.file_id)
                span.set_attribute(
                    "voice.file_size", voice_metadata.get("file_size", 0)
                )
                span.set_attribute(
                    "voice.mime_type", voice_metadata.get("mime_type", "unknown")
                )
                span.set_attribute("voice.from_queue", True)
                span.set_attribute("user.id", str(update.effective_user.id))
                span.set_attribute("chat.id", str(update.effective_chat.id))

                try:
                    file = await context.bot.get_file(voice.file_id)
                    audio_data = await file.download_as_bytearray()
                    audio_data_bytes = bytes(audio_data)
                    span.set_attribute("voice.downloaded_size", len(audio_data_bytes))
                    span.set_attribute("voice.download_success", True)
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    raise

            # Initialize queue
            queue = VoiceMessageQueue()
            await queue.connect()

            # Publish to queue
            user_id = str(update.effective_user.id)
            chat_id = str(update.effective_chat.id)
            metadata = {
                "update_id": update.update_id,
                "message_id": update.message.message_id if update.message else None,
                # Include voice message metadata
                "voice_duration": voice_metadata["duration"],
                "voice_file_size": voice_metadata["file_size"],
                "voice_mime_type": voice_metadata["mime_type"],
                "voice_file_unique_id": voice_metadata["file_unique_id"],
            }

            await queue.publish_voice_message(
                voice_file_id=voice.file_id,
                user_id=user_id,
                chat_id=chat_id,
                audio_data=audio_data_bytes,
                metadata=metadata,
            )

            await queue.disconnect()

            # Notify user that message is queued
            await update.message.reply_text(
                "✅ Voice message received and queued for processing. "
                "You'll receive a response shortly."
            )
            return
        except Exception as e:
            logger.error(f"Failed to queue voice message: {e}", exc_info=True)
            # Fall back to direct processing
            logger.info("Falling back to direct processing")

    # Direct processing (original behavior)
    # Send processing status
    status_msg = await update.message.reply_text("?? Processing your voice message...")

    # Start timing for overall voice processing
    voice_processing_start_time = time.time()
    status = "success"  # Will be updated if error occurs

    try:
        # Step 1: Download voice file from Telegram
        with tracer.start_as_current_span("voice.download") as span:
            span.set_attribute("voice.file_id", voice.file_id)
            span.set_attribute("voice.file_size", voice_metadata.get("file_size", 0))
            span.set_attribute(
                "voice.mime_type", voice_metadata.get("mime_type", "unknown")
            )
            span.set_attribute("user.id", str(update.effective_user.id))
            span.set_attribute("chat.id", str(update.effective_chat.id))

            try:
                file = await context.bot.get_file(voice.file_id)
                audio_data = await file.download_as_bytearray()
                audio_data_bytes = bytes(audio_data)

                span.set_attribute("voice.downloaded_size", len(audio_data_bytes))
                span.set_attribute("voice.download_success", True)

                logger.info(
                    f"Downloaded voice file: {len(audio_data_bytes)} bytes, "
                    f"file_id={voice_metadata['file_id']}"
                )
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

        # Validate file size after download (if not validated earlier)
        if voice_metadata["file_size"] is None:
            if len(audio_data_bytes) > max_file_size:
                await status_msg.edit_text(
                    f"❌ Voice message too large. Maximum size: {max_file_size / (1024 * 1024):.1f} MB\n"
                    f"Your file: {len(audio_data_bytes) / (1024 * 1024):.1f} MB"
                )
                logger.warning(
                    f"Voice message rejected after download: file_size={len(audio_data_bytes)} bytes "
                    f"exceeds limit={max_file_size} bytes"
                )
                return

        # Step 2: Enhance audio quality and prepare for STT
        # Apply noise reduction and volume normalization to improve transcription accuracy
        with tracer.start_as_current_span("voice.enhance_audio") as span:
            span.set_attribute("voice.input_size", len(audio_data_bytes))
            span.set_attribute("voice.input_format", "ogg")
            span.set_attribute("voice.enable_noise_reduction", True)
            span.set_attribute("voice.enable_volume_normalization", True)
            span.set_attribute("user.id", str(update.effective_user.id))
            span.set_attribute("chat.id", str(update.effective_chat.id))

            try:
                stt_audio = enhance_audio_for_stt(
                    audio_data_bytes,
                    is_ogg=True,
                    enable_noise_reduction=True,
                    enable_volume_normalization=True,
                    noise_reduction_strength=0.5,  # Moderate noise reduction
                    target_volume_db=-20.0,  # Normal volume level
                )
                span.set_attribute("voice.output_size", len(stt_audio))
                span.set_attribute("voice.enhancement_success", True)
                logger.info(f"Enhanced audio for STT: {len(stt_audio)} bytes")
            except AudioValidationError as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                await status_msg.edit_text(
                    f"? Audio validation failed: {str(e)}\n\n"
                    "Please ensure your voice message is:\n"
                    f"? Under {MAX_AUDIO_DURATION_SECONDS} seconds\n"
                    f"? Under {MAX_AUDIO_SIZE_BYTES / (1024 * 1024):.0f} MB"
                )
                return
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"Error preparing audio: {e}", exc_info=True)
                await status_msg.edit_text(
                    f"? Error processing audio: {str(e)}\n\n" "Please try again."
                )
                return

        # Step 3: Get language preference and send to STT with streaming
        await status_msg.edit_text("?? Transcribing your voice message...")
        start_time = datetime.now()
        original_audio_size = len(audio_data_bytes)
        original_audio_format = "ogg"  # Telegram sends OGG/OPUS

        # Get user language preference
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        preferred_language = ConversationStorage.get_language_preference(
            user_id, chat_id
        )

        # Initialize detected_language to preferred_language (will be updated if STT detects different language)
        detected_language = preferred_language

        logger.info(
            f"Processing voice message for user {user_id}, chat {chat_id}, preferred language: {preferred_language}"
        )

        try:
            # Import here to avoid circular dependencies
            from june_grpc_api import asr as asr_shim
            from june_grpc_api.shim.asr import (
                STTError,
                STTTimeoutError,
                STTConnectionError,
                STTServiceError,
            )
            from essence.services.telegram.dependencies.grpc_pool import get_grpc_pool
            from essence.services.telegram.dependencies.retry import (
                retry_with_exponential_backoff,
            )

            # Initialize variables for streaming transcription
            transcript = ""
            final_transcript = ""
            final_confidence = 0.9  # Default confidence
            last_result = None

            # Use connection pool for STT with tracing and metrics
            grpc_pool = get_grpc_pool()
            stt_start_time = time.time()
            stt_status = "ok"

            with tracer.start_as_current_span("stt.recognize_stream") as span:
                span.set_attribute("stt.language", preferred_language or "auto")
                span.set_attribute("stt.sample_rate", 16000)
                span.set_attribute("stt.encoding", "wav")
                span.set_attribute("stt.audio_size_bytes", len(stt_audio))
                span.set_attribute("user.id", str(user_id))
                span.set_attribute("chat.id", str(chat_id))

                try:
                    async with grpc_pool.get_stt_channel() as channel:
                        stt_client = asr_shim.SpeechToTextClient(channel)
                        # Use preferred_language for STT, or None for auto-detection
                        # STT service supports None/empty string for auto-detection
                        stt_language = (
                            preferred_language if preferred_language else None
                        )
                        cfg = asr_shim.RecognitionConfig(
                            language=stt_language,  # None enables auto-detection
                            interim_results=True,  # Enable interim results for streaming feedback
                        )

                        # Split audio into chunks for streaming (chunk size: ~1 second of audio at 16kHz, 16-bit)
                        chunk_size = 16000 * 2  # 1 second of 16-bit audio
                        audio_chunks = []
                        for i in range(0, len(stt_audio), chunk_size):
                            chunk = stt_audio[i : i + chunk_size]
                            audio_chunks.append(chunk)

                        # Create async generator for audio chunks
                        async def audio_chunk_generator():
                            for chunk in audio_chunks:
                                yield chunk

                        # Use streaming recognition for real-time feedback
                        last_update_time = datetime.now()

                        try:
                            async for result in stt_client.recognize_stream(
                                audio_chunk_generator(),
                                sample_rate=16000,
                                encoding="wav",
                                config=cfg,
                            ):
                                # Track the last result for confidence
                                last_result = result

                                # Update transcript with latest result
                                if result.transcript:
                                    transcript = result.transcript

                                # If this is a final result, save it
                                if result.is_final:
                                    final_transcript = result.transcript
                                    transcript = result.transcript
                                    final_confidence = result.confidence

                                    # Update detected language from final result
                                    stt_detected_language = getattr(
                                        result, "detected_language", None
                                    )
                                    if stt_detected_language:
                                        detected_language = stt_detected_language
                                        # Update language preference if detected language differs from preference
                                        if detected_language != preferred_language:
                                            logger.info(
                                                f"STT detected language {detected_language} differs from preference {preferred_language}, updating preference"
                                            )
                                            ConversationStorage.set_language_preference(
                                                user_id, chat_id, detected_language
                                            )

                                # Update Telegram message with interim results (throttle to avoid too many updates)
                                now = datetime.now()
                                if (
                                    now - last_update_time
                                ).total_seconds() >= 1.0:  # Update at most once per second
                                    if result.is_final:
                                        await status_msg.edit_text(
                                            f"✅ **Transcription complete:**\n\n{transcript}"
                                        )
                                    else:
                                        # Show interim result with indicator
                                        await status_msg.edit_text(
                                            f"🎤 **Transcribing...**\n\n{transcript}\n\n_Listening..._"
                                        )
                                    last_update_time = now

                            # Use final transcript if available, otherwise use last transcript
                            transcript = (
                                final_transcript if final_transcript else transcript
                            )

                            # Use confidence from last result if available
                            if last_result and not final_transcript:
                                final_confidence = last_result.confidence

                            # Set span attributes with results
                            span.set_attribute("stt.transcript_length", len(transcript))
                            span.set_attribute("stt.confidence", final_confidence)
                            if detected_language:
                                span.set_attribute(
                                    "stt.detected_language", detected_language
                                )
                        except Exception as e:
                            stt_status = "error"
                            span.record_exception(e)
                            span.set_status(
                                trace.Status(trace.StatusCode.ERROR, str(e))
                            )
                            raise
                        finally:
                            # Record STT metrics
                            stt_duration = time.time() - stt_start_time
                            record_grpc_call(
                                "stt", "recognize_stream", stt_duration, stt_status
                            )
                            STT_TRANSCRIPTION_DURATION_SECONDS.labels(
                                platform=PLATFORM, status=stt_status
                            ).observe(stt_duration)

                    # Handle empty or invalid transcriptions
                    if not transcript or not transcript.strip():
                        logger.warning(
                            "STT service returned empty or whitespace-only transcript"
                        )
                        await status_msg.edit_text(
                            "❌ **Transcription failed:**\n\n"
                            "The audio could not be transcribed. This might be due to:\n"
                            "• Background noise or unclear audio\n"
                            "• Audio too short or silent\n"
                            "• Unsupported language\n\n"
                            "Please try again with a clearer voice message."
                        )
                        return
                except Exception as e:
                    # Handle errors from the STT channel/streaming
                    stt_status = "error"
                    span.record_exception(e)
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    raise

                # Check for voice language change command
                (
                    is_language_command,
                    language_command_response,
                ) = handle_voice_language_command(transcript, user_id, chat_id)

                if is_language_command:
                    # This was a language change command, respond and return early
                    await status_msg.edit_text(language_command_response)
                    return

                # Calculate processing time and audio duration
                processing_time_ms = int(
                    (datetime.now() - start_time).total_seconds() * 1000
                )

                # Calculate audio duration from the prepared audio
                try:
                    audio_array, sr = librosa.load(io.BytesIO(stt_audio), sr=16000)
                    audio_duration = len(audio_array) / sr
                except Exception:
                    # Fallback: estimate from size (rough approximation)
                    audio_duration = len(stt_audio) / (
                        16000 * 2
                    )  # 16kHz, 16-bit = 2 bytes/sample

                # Record metrics (use final transcript confidence if available)
                try:
                    metrics = get_metrics_storage()
                    metrics.record_transcription(
                        audio_format=original_audio_format,
                        audio_duration_seconds=audio_duration,
                        audio_size_bytes=original_audio_size,
                        sample_rate=16000,
                        transcript_length=len(transcript),
                        confidence=final_confidence,
                        processing_time_ms=processing_time_ms,
                        source="telegram",
                        metadata={
                            "telegram_file_id": voice_metadata["file_id"],
                            "telegram_file_unique_id": voice_metadata["file_unique_id"],
                            "telegram_duration": voice_metadata["duration"],
                            "telegram_file_size": voice_metadata["file_size"],
                            "telegram_mime_type": voice_metadata["mime_type"],
                            "prepared_audio_size": len(stt_audio),
                            "streaming": True,
                        },
                    )
                except Exception as e:
                    logger.warning(f"Failed to record transcription metrics: {e}")

                # Record STT cost (non-blocking)
                try:
                    conversation_id = get_conversation_id_from_user_chat(
                        user_id, chat_id
                    )
                    stt_cost = calculate_stt_cost(audio_duration)
                    record_cost(
                        service="stt",
                        user_id=user_id,
                        conversation_id=conversation_id,
                        cost=stt_cost,
                        metadata={
                            "audio_duration_seconds": audio_duration,
                            "transcript_length": len(transcript),
                            "confidence": final_confidence,
                            "source": "telegram",
                        },
                    )
                except Exception as e:
                    logger.warning(f"Failed to record STT cost: {e}")

                logger.info(f"Transcription: {transcript}")
        except STTTimeoutError as e:
            # Handle timeout errors with specific user feedback
            logger.error(f"STT timeout error: {e}", exc_info=True)
            try:
                processing_time_ms = int(
                    (datetime.now() - start_time).total_seconds() * 1000
                )
                metrics = get_metrics_storage()
                metrics.record_transcription(
                    audio_format=original_audio_format,
                    audio_duration_seconds=0.0,
                    audio_size_bytes=original_audio_size,
                    sample_rate=16000,
                    transcript_length=0,
                    confidence=0.0,
                    processing_time_ms=processing_time_ms,
                    source="telegram",
                    error_message=f"Timeout: {str(e)}",
                    metadata={
                        "telegram_file_id": voice_metadata["file_id"],
                        "telegram_file_unique_id": voice_metadata["file_unique_id"],
                        "telegram_duration": voice_metadata["duration"],
                        "telegram_file_size": voice_metadata["file_size"],
                        "telegram_mime_type": voice_metadata["mime_type"],
                    },
                )
            except Exception as metrics_error:
                logger.warning(f"Failed to record error metrics: {metrics_error}")

            await status_msg.edit_text(
                "⏱️ **Transcription timeout:**\n\n"
                "The transcription request took too long to complete. This might be due to:\n"
                "• High server load\n"
                "• Network connectivity issues\n"
                "• Audio file too large\n\n"
                "Please try again in a moment."
            )
            return
        except STTConnectionError as e:
            # Handle connection errors with specific user feedback
            logger.error(f"STT connection error: {e}", exc_info=True)
            try:
                processing_time_ms = int(
                    (datetime.now() - start_time).total_seconds() * 1000
                )
                metrics = get_metrics_storage()
                metrics.record_transcription(
                    audio_format=original_audio_format,
                    audio_duration_seconds=0.0,
                    audio_size_bytes=original_audio_size,
                    sample_rate=16000,
                    transcript_length=0,
                    confidence=0.0,
                    processing_time_ms=processing_time_ms,
                    source="telegram",
                    error_message=f"Connection error: {str(e)}",
                    metadata={
                        "telegram_file_id": voice_metadata["file_id"],
                        "telegram_file_unique_id": voice_metadata["file_unique_id"],
                        "telegram_duration": voice_metadata["duration"],
                        "telegram_file_size": voice_metadata["file_size"],
                        "telegram_mime_type": voice_metadata["mime_type"],
                    },
                )
            except Exception as metrics_error:
                logger.warning(f"Failed to record error metrics: {metrics_error}")

            await status_msg.edit_text(
                "🔌 **Connection error:**\n\n"
                "Unable to connect to the transcription service. This might be due to:\n"
                "• Service temporarily unavailable\n"
                "• Network connectivity issues\n\n"
                "Please try again in a moment."
            )
            return
        except STTServiceError as e:
            # Handle service errors with specific user feedback
            logger.error(f"STT service error: {e}", exc_info=True)
            try:
                processing_time_ms = int(
                    (datetime.now() - start_time).total_seconds() * 1000
                )
                metrics = get_metrics_storage()
                metrics.record_transcription(
                    audio_format=original_audio_format,
                    audio_duration_seconds=0.0,
                    audio_size_bytes=original_audio_size,
                    sample_rate=16000,
                    transcript_length=0,
                    confidence=0.0,
                    processing_time_ms=processing_time_ms,
                    source="telegram",
                    error_message=f"Service error: {str(e)}",
                    metadata={
                        "telegram_file_id": voice_metadata["file_id"],
                        "telegram_file_unique_id": voice_metadata["file_unique_id"],
                        "telegram_duration": voice_metadata["duration"],
                        "telegram_file_size": voice_metadata["file_size"],
                        "telegram_mime_type": voice_metadata["mime_type"],
                    },
                )
            except Exception as metrics_error:
                logger.warning(f"Failed to record error metrics: {metrics_error}")

            await status_msg.edit_text(
                "⚠️ **Transcription service error:**\n\n"
                "The transcription service encountered an error. This might be due to:\n"
                "• Invalid audio format\n"
                "• Service configuration issue\n"
                "• Internal service error\n\n"
                "Please try again. If the problem persists, contact support."
            )
            return
        except STTError as e:
            # Handle other STT errors
            logger.error(f"STT error: {e}", exc_info=True)
            try:
                processing_time_ms = int(
                    (datetime.now() - start_time).total_seconds() * 1000
                )
                metrics = get_metrics_storage()
                metrics.record_transcription(
                    audio_format=original_audio_format,
                    audio_duration_seconds=0.0,
                    audio_size_bytes=original_audio_size,
                    sample_rate=16000,
                    transcript_length=0,
                    confidence=0.0,
                    processing_time_ms=processing_time_ms,
                    source="telegram",
                    error_message=f"STT error: {str(e)}",
                    metadata={
                        "telegram_file_id": voice_metadata["file_id"],
                        "telegram_file_unique_id": voice_metadata["file_unique_id"],
                        "telegram_duration": voice_metadata["duration"],
                        "telegram_file_size": voice_metadata["file_size"],
                        "telegram_mime_type": voice_metadata["mime_type"],
                    },
                )
            except Exception as metrics_error:
                logger.warning(f"Failed to record error metrics: {metrics_error}")

            await status_msg.edit_text(
                f"❌ **Transcription failed:**\n\n{str(e)}\n\n" "Please try again."
            )
            return
        except ValueError as e:
            # Handle validation errors (empty transcript, invalid audio, etc.)
            logger.error(f"STT validation error: {e}", exc_info=True)
            try:
                processing_time_ms = int(
                    (datetime.now() - start_time).total_seconds() * 1000
                )
                metrics = get_metrics_storage()
                metrics.record_transcription(
                    audio_format=original_audio_format,
                    audio_duration_seconds=0.0,
                    audio_size_bytes=original_audio_size,
                    sample_rate=16000,
                    transcript_length=0,
                    confidence=0.0,
                    processing_time_ms=processing_time_ms,
                    source="telegram",
                    error_message=f"Validation error: {str(e)}",
                    metadata={
                        "telegram_file_id": voice_metadata["file_id"],
                        "telegram_file_unique_id": voice_metadata["file_unique_id"],
                        "telegram_duration": voice_metadata["duration"],
                        "telegram_file_size": voice_metadata["file_size"],
                        "telegram_mime_type": voice_metadata["mime_type"],
                    },
                )
            except Exception as metrics_error:
                logger.warning(f"Failed to record error metrics: {metrics_error}")

            await status_msg.edit_text(
                f"❌ **Transcription validation error:**\n\n{str(e)}\n\n"
                "Please ensure your voice message is valid and try again."
            )
            return
        except Exception as e:
            # Handle unexpected errors
            logger.error(f"Unexpected STT error: {e}", exc_info=True)
            try:
                processing_time_ms = int(
                    (datetime.now() - start_time).total_seconds() * 1000
                )
                metrics = get_metrics_storage()
                metrics.record_transcription(
                    audio_format=original_audio_format,
                    audio_duration_seconds=0.0,
                    audio_size_bytes=original_audio_size,
                    sample_rate=16000,
                    transcript_length=0,
                    confidence=0.0,
                    processing_time_ms=processing_time_ms,
                    source="telegram",
                    error_message=f"Unexpected error: {str(e)}",
                    metadata={
                        "telegram_file_id": voice_metadata["file_id"],
                        "telegram_file_unique_id": voice_metadata["file_unique_id"],
                        "telegram_duration": voice_metadata["duration"],
                        "telegram_file_size": voice_metadata["file_size"],
                        "telegram_mime_type": voice_metadata["mime_type"],
                    },
                )
            except Exception as metrics_error:
                logger.warning(f"Failed to record error metrics: {metrics_error}")

            await status_msg.edit_text(
                f"❌ **Transcription failed:**\n\n{str(e)}\n\n" "Please try again."
            )
            return

        # Step 4: Send transcript to LLM service
        await status_msg.edit_text("?? Processing with LLM...")
        try:
            from june_grpc_api.shim.llm import LLMClient
            from essence.services.telegram.dependencies.config import get_llm_address

            llm_address = get_llm_address()

            # Conversation history is not available (gateway removed for MVP)
            # Using simple prompt without history
            user_id = str(update.effective_user.id)
            chat_id = str(update.effective_chat.id)
            messages = []

            logger.debug(
                f"Using simple prompt without conversation history (gateway removed for MVP)"
            )

            # Get custom prompt template if available
            system_prompt = None
            try:
                template = ConversationStorage.get_prompt_template_for_conversation(
                    user_id, chat_id
                )

                if template and template.get("template_text"):
                    template_text = template["template_text"]
                    # Format template with available variables
                    # Available variables: user_id, chat_id, transcript, detected_language
                    try:
                        system_prompt = template_text.format(
                            user_id=user_id,
                            chat_id=chat_id,
                            transcript=transcript,
                            detected_language=detected_language,
                        )
                        logger.info(
                            f"Using custom prompt template: {template.get('name')}"
                        )
                    except KeyError as e:
                        logger.warning(
                            f"Template variable not found: {e}, using template as-is"
                        )
                        system_prompt = template_text
                    except Exception as e:
                        logger.warning(
                            f"Error formatting template: {e}, using template as-is"
                        )
                        system_prompt = template_text
            except Exception as template_error:
                logger.debug(f"Could not load prompt template: {template_error}")

            # Prepare messages for chat API
            # Convert conversation history to chat message format
            chat_messages = []

            # Add system prompt if we have a custom template
            if system_prompt:
                chat_messages.append({"role": "system", "content": system_prompt})

            if messages:
                # Add existing conversation history
                for msg in messages:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    # Only include valid roles (skip system if we already added one)
                    if role in ("system", "user", "assistant", "tool"):
                        # Skip system messages if we already added a custom template
                        if role == "system" and system_prompt:
                            continue
                        chat_messages.append({"role": role, "content": content})
                logger.info(
                    f"Using {len(chat_messages)} messages from conversation history"
                )

            # Add new user message (transcript)
            chat_messages.append({"role": "user", "content": transcript})

            # Use chat_stream() method for streaming generation
            llm_start_time = time.time()
            llm_status = "ok"
            from essence.services.telegram.telegram_utils import (
                stream_llm_response_to_telegram,
            )

            # Update status message to show we're starting streaming
            await status_msg.edit_text("💬 Generating response...")

            # Use connection pool for LLM with retry logic
            from essence.services.telegram.dependencies.grpc_pool import get_grpc_pool
            from essence.services.telegram.dependencies.retry import (
                retry_with_exponential_backoff,
            )

            async def call_llm():
                with tracer.start_as_current_span("llm.chat_stream") as span:
                    span.set_attribute("llm.message_count", len(chat_messages))
                    span.set_attribute("llm.user_id", str(user_id))
                    span.set_attribute("llm.chat_id", str(chat_id))
                    input_length = sum(
                        len(msg.get("content", "")) for msg in chat_messages
                    )
                    span.set_attribute("llm.input_length", input_length)

                    grpc_pool = get_grpc_pool()
                    async with grpc_pool.get_llm_channel() as channel:
                        llm_client = LLMClient(channel)
                        try:
                            # Stream LLM response to Telegram
                            (
                                llm_response,
                                stream_success,
                            ) = await stream_llm_response_to_telegram(
                                message=status_msg,
                                llm_stream=llm_client.chat_stream(chat_messages),
                                prefix="💬 **Response:**\n\n",
                                update_interval=0.1,
                            )
                            span.set_attribute(
                                "llm.response_length",
                                len(llm_response) if llm_response else 0,
                            )
                            span.set_attribute("llm.stream_success", stream_success)
                            return llm_response, stream_success
                        except Exception as e:
                            span.record_exception(e)
                            span.set_status(
                                trace.Status(trace.StatusCode.ERROR, str(e))
                            )
                            raise

            try:
                llm_response, stream_success = await retry_with_exponential_backoff(
                    call_llm, max_retries=3, initial_delay=1.0
                )
            except Exception as e:
                llm_status = "error"
                raise
            finally:
                # Record LLM metrics
                llm_duration = time.time() - llm_start_time
                record_grpc_call("llm", "chat_stream", llm_duration, llm_status)
                LLM_GENERATION_DURATION_SECONDS.labels(
                    platform=PLATFORM, status=llm_status
                ).observe(llm_duration)

            # Record LLM cost (non-blocking)
            try:
                conversation_id = get_conversation_id_from_user_chat(user_id, chat_id)
                # Estimate tokens from characters (rough estimate: ~4 chars per token)
                # Count input and output characters
                input_chars = sum(len(msg.get("content", "")) for msg in chat_messages)
                output_chars = len(llm_response) if llm_response else 0
                llm_cost = calculate_llm_cost(
                    input_characters=input_chars, output_characters=output_chars
                )
                record_cost(
                    service="llm",
                    user_id=user_id,
                    conversation_id=conversation_id,
                    cost=llm_cost,
                    metadata={
                        "input_characters": input_chars,
                        "output_characters": output_chars,
                        "message_count": len(chat_messages),
                        "source": "telegram",
                        "streaming": True,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to record LLM cost: {e}")

            if not llm_response or not llm_response.strip():
                await status_msg.edit_text(
                    f"💬 **Transcription:**\n\n{transcript}\n\n"
                    "❌ LLM returned an empty response. Please try again."
                )
                return

            # Conversation history storage removed (gateway removed for MVP)
            # Language preference is stored via in-memory ConversationStorage
            logger.debug(f"Conversation history not saved (gateway removed for MVP)")

            logger.info(f"LLM response: {llm_response}")
        except Exception as e:
            logger.error(f"LLM error: {e}", exc_info=True)
            await status_msg.edit_text(
                f"?? **Transcription:**\n\n{transcript}\n\n"
                f"? LLM processing failed: {str(e)}\n\n"
                "Please try again."
            )
            return

        # Step 5: Send LLM response to TTS service
        await status_msg.edit_text("?? Generating voice response...")
        tts_start_time = time.time()
        tts_status = "ok"
        try:
            from june_grpc_api.shim.tts import TextToSpeechClient
            from essence.services.telegram.dependencies.config import get_tts_address

            tts_address = get_tts_address()

            # Use connection pool for TTS with retry logic
            grpc_pool = get_grpc_pool()
            from essence.services.telegram.dependencies.retry import (
                retry_with_exponential_backoff,
            )

            async def call_tts():
                with tracer.start_as_current_span("tts.synthesize") as span:
                    span.set_attribute("tts.text_length", len(llm_response))
                    span.set_attribute("tts.language", detected_language)
                    span.set_attribute("tts.voice_id", "default")
                    span.set_attribute("tts.user_id", str(user_id))
                    span.set_attribute("tts.chat_id", str(chat_id))

                    async with grpc_pool.get_tts_channel() as channel:
                        tts_client = TextToSpeechClient(channel)
                        # Use detected/preferred language for TTS
                        logger.info(f"Using language {detected_language} for TTS")
                        try:
                            tts_audio_bytes = await tts_client.synthesize(
                                llm_response,
                                voice_id="default",
                                language=detected_language,
                            )
                            span.set_attribute(
                                "tts.audio_size_bytes", len(tts_audio_bytes)
                            )
                            return tts_audio_bytes
                        except Exception as e:
                            span.record_exception(e)
                            span.set_status(
                                trace.Status(trace.StatusCode.ERROR, str(e))
                            )
                            raise

            try:
                tts_audio_bytes = await retry_with_exponential_backoff(
                    call_tts, max_retries=3, initial_delay=1.0
                )
            except Exception as e:
                tts_status = "error"
                raise
            finally:
                # Record TTS metrics
                tts_duration = time.time() - tts_start_time
                record_grpc_call("tts", "synthesize", tts_duration, tts_status)
                TTS_SYNTHESIS_DURATION_SECONDS.labels(
                    platform=PLATFORM, status=tts_status
                ).observe(tts_duration)

            # Calculate TTS audio duration and record cost (non-blocking)
            tts_audio_duration = 0.0
            try:
                # Estimate duration from audio size (rough estimate for WAV: sample_rate * channels * bytes_per_sample)
                # Assuming 16kHz, mono, 16-bit (2 bytes per sample)
                tts_audio_duration = (
                    len(tts_audio_bytes) / (16000 * 2) if tts_audio_bytes else 0.0
                )
                # Try to get actual duration using librosa if available
                try:
                    tts_audio_array, tts_sr = librosa.load(
                        io.BytesIO(tts_audio_bytes), sr=16000
                    )
                    tts_audio_duration = len(tts_audio_array) / tts_sr
                except Exception:
                    pass  # Use estimated duration

                conversation_id = get_conversation_id_from_user_chat(user_id, chat_id)
                tts_cost = calculate_tts_cost(tts_audio_duration)
                record_cost(
                    service="tts",
                    user_id=user_id,
                    conversation_id=conversation_id,
                    cost=tts_cost,
                    metadata={
                        "audio_duration_seconds": tts_audio_duration,
                        "text_length": len(llm_response),
                        "language": detected_language,
                        "source": "telegram",
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to record TTS cost: {e}")

            if not tts_audio_bytes or len(tts_audio_bytes) == 0:
                await status_msg.edit_text(
                    f"?? **Transcription:**\n\n{transcript}\n\n"
                    "? TTS returned empty audio. Please try again."
                )
                return

            logger.info(f"TTS generated audio: {len(tts_audio_bytes)} bytes")
        except Exception as e:
            logger.error(f"TTS error: {e}", exc_info=True)
            await status_msg.edit_text(
                f"?? **Transcription:**\n\n{transcript}\n\n"
                f"? TTS processing failed: {str(e)}\n\n"
                "Please try again."
            )
            return

        # Step 6: Convert TTS audio to OGG format (Telegram voice message format) with compression optimization
        await status_msg.edit_text("?? Preparing audio for delivery...")
        ogg_audio_path = None
        try:
            # Load TTS audio bytes - try multiple formats (pydub auto-detects)
            try:
                # Try WAV first (most common)
                tts_audio = AudioSegment.from_wav(io.BytesIO(tts_audio_bytes))
            except Exception:
                # Fallback to auto-detection (pydub tries multiple formats)
                try:
                    tts_audio = AudioSegment.from_file(io.BytesIO(tts_audio_bytes))
                except Exception as e:
                    raise ValueError(f"Could not decode TTS audio data: {e}")

            # Create temporary OGG file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_file:
                ogg_audio_path = temp_file.name

            # Find optimal compression preset based on audio characteristics
            optimal_preset, preset_info = find_optimal_compression(
                tts_audio,
                max_file_size=config.max_file_size
                if hasattr(config, "max_file_size")
                else 20 * 1024 * 1024,
                quality_threshold=0.7,  # Accept quality down to 70% of max bitrate
            )

            # Export to OGG format with optimized compression
            compression_info = export_audio_to_ogg_optimized(
                tts_audio, ogg_audio_path, preset=optimal_preset
            )

            logger.info(
                f"Converted TTS audio to OGG with compression: {ogg_audio_path}, "
                f"preset: {optimal_preset}, "
                f"size: {compression_info['compressed_size'] / 1024:.1f} KB, "
                f"compression ratio: {compression_info['compression_ratio']:.2f}x"
            )
        except Exception as e:
            logger.error(f"Audio conversion error: {e}", exc_info=True)

            await status_msg.edit_text(
                f"?? **Transcription:**\n\n{transcript}\n\n"
                f"? Audio conversion failed: {str(e)}\n\n"
                "Please try again."
            )
            return
        finally:
            # Clean up temp file if created (even if conversion failed)
            if ogg_audio_path and os.path.exists(ogg_audio_path):
                try:
                    os.unlink(ogg_audio_path)
                    logger.debug(
                        f"Cleaned up temporary file after conversion error: {ogg_audio_path}"
                    )
                except Exception as cleanup_error:
                    # Log warning but don't fail the operation
                    logger.warning(
                        f"Failed to delete temp file {ogg_audio_path} after conversion error: {cleanup_error}"
                    )

        # Step 7: Send voice response back to Telegram
        try:
            await status_msg.edit_text("🔄 Sending voice response...")

            # Use comprehensive error handling with retry logic
            success = await send_voice_with_error_handling(
                update=update,
                ogg_audio_path=ogg_audio_path,
                transcript=transcript,
                status_msg=status_msg,
                max_retries=3,
            )

            if not success:
                # Error handling and user feedback already done in send_voice_with_error_handling
                status = "error"
                return
        finally:
            # Clean up temporary OGG file in all code paths (success, error, exception)
            # Note: send_voice_with_error_handling handles cleanup internally, but we ensure it here too
            if ogg_audio_path and os.path.exists(ogg_audio_path):
                try:
                    os.unlink(ogg_audio_path)
                    logger.debug(f"Cleaned up temporary file: {ogg_audio_path}")
                except Exception as e:
                    # Log warning but don't fail the operation
                    logger.warning(f"Failed to delete temp file {ogg_audio_path}: {e}")

            # Record overall voice processing metrics
            voice_processing_duration = time.time() - voice_processing_start_time
            VOICE_MESSAGES_PROCESSED_TOTAL.labels(
                platform=PLATFORM, status=status
            ).inc()
            VOICE_PROCESSING_DURATION_SECONDS.labels(
                platform=PLATFORM, status=status
            ).observe(voice_processing_duration)
    except Exception as e:
        status = "error"
        error_type = type(e).__name__
        ERRORS_TOTAL.labels(service=SERVICE_NAME, error_type=error_type).inc()
        logger.error(f"Error processing voice message: {e}", exc_info=True)

        # Clean up any temporary files that might have been created
        # Note: ogg_audio_path is defined in the inner try block, so we need to check if it exists
        # This is a fallback cleanup in case the inner exception handlers didn't run
        try:
            # Check if ogg_audio_path was set in the outer scope
            if (
                "ogg_audio_path" in locals()
                and ogg_audio_path
                and os.path.exists(ogg_audio_path)
            ):
                try:
                    os.unlink(ogg_audio_path)
                    logger.debug(
                        f"Cleaned up temporary file in outer exception handler: {ogg_audio_path}"
                    )
                except Exception as cleanup_error:
                    logger.warning(
                        f"Failed to delete temp file {ogg_audio_path} in outer exception handler: {cleanup_error}"
                    )
        except Exception:
            # Ignore errors accessing locals() or file operations
            pass

        # Record metrics for failed voice processing
        try:
            voice_processing_duration = time.time() - voice_processing_start_time
            VOICE_MESSAGES_PROCESSED_TOTAL.labels(
                platform=PLATFORM, status=status
            ).inc()
            VOICE_PROCESSING_DURATION_SECONDS.labels(
                platform=PLATFORM, status=status
            ).observe(voice_processing_duration)
        except Exception:
            pass  # Don't fail if metrics recording fails

        await status_msg.edit_text(
            f"? Error processing voice message: {str(e)}\n\n" "Please try again later."
        )


async def handle_voice_message_from_queue(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    config,
    stt_address: str,
    get_metrics_storage,
    audio_data: bytes,
    metadata: Optional[dict] = None,
):
    """Handle voice message processing from queue (audio_data already downloaded).

    This is called by workers to process messages from the NATS queue.
    Similar to handle_voice_message but accepts audio_data directly.
    """
    voice = update.message.voice
    audio_data_bytes = audio_data

    # Send processing status
    status_msg = await update.message.reply_text("?? Processing your voice message...")

    try:
        logger.info(f"Processing queued voice file: {len(audio_data_bytes)} bytes")

        # Step 1: Enhance audio quality and prepare for STT
        with tracer.start_as_current_span("voice.enhance_audio") as span:
            span.set_attribute("voice.input_size", len(audio_data_bytes))
            span.set_attribute("voice.input_format", "ogg")
            span.set_attribute("voice.enable_noise_reduction", True)
            span.set_attribute("voice.enable_volume_normalization", True)
            span.set_attribute("voice.from_queue", True)
            span.set_attribute("user.id", str(update.effective_user.id))
            span.set_attribute("chat.id", str(update.effective_chat.id))

            try:
                stt_audio = enhance_audio_for_stt(
                    audio_data_bytes,
                    is_ogg=True,
                    enable_noise_reduction=True,
                    enable_volume_normalization=True,
                    noise_reduction_strength=0.5,
                    target_volume_db=-20.0,
                )
                span.set_attribute("voice.output_size", len(stt_audio))
                span.set_attribute("voice.enhancement_success", True)
                logger.info(f"Enhanced audio for STT: {len(stt_audio)} bytes")
            except AudioValidationError as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                await status_msg.edit_text(
                    f"? Audio validation failed: {str(e)}\n\n"
                    "Please ensure your voice message is:\n"
                    f"? Under {MAX_AUDIO_DURATION_SECONDS} seconds\n"
                    f"? Under {MAX_AUDIO_SIZE_BYTES / (1024 * 1024):.0f} MB"
                )
                return
            except Exception as e:
                # Handle other exceptions from audio enhancement
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                logger.error(f"Error preparing audio: {e}", exc_info=True)
                await status_msg.edit_text(
                    f"? Error processing audio: {str(e)}\n\n" "Please try again."
                )
                return

        # Step 2: Get language preference and send to STT with streaming
        await status_msg.edit_text("?? Transcribing your voice message...")
        start_time = datetime.now()
        original_audio_size = len(audio_data_bytes)
        original_audio_format = "ogg"

        # Get user language preference
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        preferred_language = ConversationStorage.get_language_preference(
            user_id, chat_id
        )
        detected_language = preferred_language

        logger.info(
            f"Processing voice message for user {user_id}, chat {chat_id}, preferred language: {preferred_language}"
        )

        try:
            # Import here to avoid circular dependencies
            from june_grpc_api import asr as asr_shim
            from june_grpc_api.shim.asr import (
                STTError,
                STTTimeoutError,
                STTConnectionError,
                STTServiceError,
            )

            # Initialize variables for streaming transcription
            transcript = ""
            final_transcript = ""
            final_confidence = 0.9
            last_result = None

            # Use connection pool for STT
            from essence.services.telegram.dependencies.grpc_pool import get_grpc_pool

            grpc_pool = get_grpc_pool()
            async with grpc_pool.get_stt_channel() as channel:
                stt_client = asr_shim.SpeechToTextClient(channel)
                # Use preferred_language for STT, or None for auto-detection
                # STT service supports None/empty string for auto-detection
                stt_language = preferred_language if preferred_language else None
                cfg = asr_shim.RecognitionConfig(
                    language=stt_language,  # None enables auto-detection
                    interim_results=True,
                )

                # Split audio into chunks for streaming
                chunk_size = 16000 * 2
                audio_chunks = []
                for i in range(0, len(stt_audio), chunk_size):
                    chunk = stt_audio[i : i + chunk_size]
                    audio_chunks.append(chunk)

                async def audio_chunk_generator():
                    for chunk in audio_chunks:
                        yield chunk

                last_update_time = datetime.now()

                async for result in stt_client.recognize_stream(
                    audio_chunk_generator(),
                    sample_rate=16000,
                    encoding="wav",
                    config=cfg,
                ):
                    last_result = result

                    if result.transcript:
                        transcript = result.transcript

                    if result.is_final:
                        final_transcript = result.transcript
                        transcript = result.transcript
                        final_confidence = result.confidence

                        stt_detected_language = getattr(
                            result, "detected_language", None
                        )
                        if stt_detected_language:
                            detected_language = stt_detected_language
                            if detected_language != preferred_language:
                                logger.info(
                                    f"STT detected language {detected_language} differs from preference {preferred_language}, updating preference"
                                )
                                ConversationStorage.set_language_preference(
                                    user_id, chat_id, detected_language
                                )

                    now = datetime.now()
                    if (now - last_update_time).total_seconds() >= 1.0:
                        if result.is_final:
                            await status_msg.edit_text(
                                f"✅ **Transcription complete:**\n\n{transcript}"
                            )
                        else:
                            await status_msg.edit_text(
                                f"🎤 **Transcribing...**\n\n{transcript}\n\n_Listening..._"
                            )
                        last_update_time = now

                transcript = final_transcript if final_transcript else transcript

                if last_result and not final_transcript:
                    final_confidence = last_result.confidence

                # Handle empty or invalid transcriptions
                if not transcript or not transcript.strip():
                    logger.warning(
                        "STT service returned empty or whitespace-only transcript"
                    )
                    await status_msg.edit_text(
                        "❌ **Transcription failed:**\n\n"
                        "The audio could not be transcribed. This might be due to:\n"
                        "• Background noise or unclear audio\n"
                        "• Audio too short or silent\n"
                        "• Unsupported language\n\n"
                        "Please try again with a clearer voice message."
                    )
                    return

            # Check for voice language change command
            (
                is_language_command,
                language_command_response,
            ) = handle_voice_language_command(transcript, user_id, chat_id)

            if is_language_command:
                await status_msg.edit_text(language_command_response)
                return

            # Calculate processing time and audio duration
            processing_time_ms = int(
                (datetime.now() - start_time).total_seconds() * 1000
            )

            try:
                audio_array, sr = librosa.load(io.BytesIO(stt_audio), sr=16000)
                audio_duration = len(audio_array) / sr
            except Exception:
                audio_duration = len(stt_audio) / (16000 * 2)

            # Record metrics
            try:
                metrics = get_metrics_storage()
                metrics.record_transcription(
                    audio_format=original_audio_format,
                    audio_duration_seconds=audio_duration,
                    audio_size_bytes=original_audio_size,
                    sample_rate=16000,
                    transcript_length=len(transcript),
                    confidence=final_confidence,
                    processing_time_ms=processing_time_ms,
                    source="telegram",
                    metadata={
                        "telegram_file_id": voice.file_id,
                        "telegram_duration": getattr(voice, "duration", None),
                        "prepared_audio_size": len(stt_audio),
                        "streaming": True,
                        "queued": True,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to record transcription metrics: {e}")

            # Record STT cost
            try:
                conversation_id = get_conversation_id_from_user_chat(user_id, chat_id)
                stt_cost = calculate_stt_cost(audio_duration)
                record_cost(
                    service="stt",
                    user_id=user_id,
                    conversation_id=conversation_id,
                    cost=stt_cost,
                    metadata={
                        "audio_duration_seconds": audio_duration,
                        "transcript_length": len(transcript),
                        "confidence": final_confidence,
                        "source": "telegram",
                        "queued": True,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to record STT cost: {e}")

            logger.info(f"Transcription: {transcript}")
        except STTTimeoutError as e:
            # Handle timeout errors with specific user feedback
            logger.error(f"STT timeout error: {e}", exc_info=True)
            try:
                processing_time_ms = int(
                    (datetime.now() - start_time).total_seconds() * 1000
                )
                metrics = get_metrics_storage()
                metrics.record_transcription(
                    audio_format=original_audio_format,
                    audio_duration_seconds=0.0,
                    audio_size_bytes=original_audio_size,
                    sample_rate=16000,
                    transcript_length=0,
                    confidence=0.0,
                    processing_time_ms=processing_time_ms,
                    source="telegram",
                    error_message=f"Timeout: {str(e)}",
                    metadata={
                        "telegram_file_id": voice.file_id,
                        "telegram_duration": getattr(voice, "duration", None),
                        "queued": True,
                    },
                )
            except Exception as metrics_error:
                logger.warning(f"Failed to record error metrics: {metrics_error}")

            await status_msg.edit_text(
                "⏱️ **Transcription timeout:**\n\n"
                "The transcription request took too long to complete. This might be due to:\n"
                "• High server load\n"
                "• Network connectivity issues\n"
                "• Audio file too large\n\n"
                "Please try again in a moment."
            )
            return
        except STTConnectionError as e:
            # Handle connection errors with specific user feedback
            logger.error(f"STT connection error: {e}", exc_info=True)
            try:
                processing_time_ms = int(
                    (datetime.now() - start_time).total_seconds() * 1000
                )
                metrics = get_metrics_storage()
                metrics.record_transcription(
                    audio_format=original_audio_format,
                    audio_duration_seconds=0.0,
                    audio_size_bytes=original_audio_size,
                    sample_rate=16000,
                    transcript_length=0,
                    confidence=0.0,
                    processing_time_ms=processing_time_ms,
                    source="telegram",
                    error_message=f"Connection error: {str(e)}",
                    metadata={
                        "telegram_file_id": voice.file_id,
                        "telegram_duration": getattr(voice, "duration", None),
                        "queued": True,
                    },
                )
            except Exception as metrics_error:
                logger.warning(f"Failed to record error metrics: {metrics_error}")

            await status_msg.edit_text(
                "🔌 **Connection error:**\n\n"
                "Unable to connect to the transcription service. This might be due to:\n"
                "• Service temporarily unavailable\n"
                "• Network connectivity issues\n\n"
                "Please try again in a moment."
            )
            return
        except STTServiceError as e:
            # Handle service errors with specific user feedback
            logger.error(f"STT service error: {e}", exc_info=True)
            try:
                processing_time_ms = int(
                    (datetime.now() - start_time).total_seconds() * 1000
                )
                metrics = get_metrics_storage()
                metrics.record_transcription(
                    audio_format=original_audio_format,
                    audio_duration_seconds=0.0,
                    audio_size_bytes=original_audio_size,
                    sample_rate=16000,
                    transcript_length=0,
                    confidence=0.0,
                    processing_time_ms=processing_time_ms,
                    source="telegram",
                    error_message=f"Service error: {str(e)}",
                    metadata={
                        "telegram_file_id": voice.file_id,
                        "telegram_duration": getattr(voice, "duration", None),
                        "queued": True,
                    },
                )
            except Exception as metrics_error:
                logger.warning(f"Failed to record error metrics: {metrics_error}")

            await status_msg.edit_text(
                "⚠️ **Transcription service error:**\n\n"
                "The transcription service encountered an error. This might be due to:\n"
                "• Invalid audio format\n"
                "• Service configuration issue\n"
                "• Internal service error\n\n"
                "Please try again. If the problem persists, contact support."
            )
            return
        except STTError as e:
            # Handle other STT errors
            logger.error(f"STT error: {e}", exc_info=True)
            try:
                processing_time_ms = int(
                    (datetime.now() - start_time).total_seconds() * 1000
                )
                metrics = get_metrics_storage()
                metrics.record_transcription(
                    audio_format=original_audio_format,
                    audio_duration_seconds=0.0,
                    audio_size_bytes=original_audio_size,
                    sample_rate=16000,
                    transcript_length=0,
                    confidence=0.0,
                    processing_time_ms=processing_time_ms,
                    source="telegram",
                    error_message=f"STT error: {str(e)}",
                    metadata={
                        "telegram_file_id": voice.file_id,
                        "telegram_duration": getattr(voice, "duration", None),
                        "queued": True,
                    },
                )
            except Exception as metrics_error:
                logger.warning(f"Failed to record error metrics: {metrics_error}")

            await status_msg.edit_text(
                f"❌ **Transcription failed:**\n\n{str(e)}\n\n" "Please try again."
            )
            return
        except ValueError as e:
            # Handle validation errors (empty transcript, invalid audio, etc.)
            logger.error(f"STT validation error: {e}", exc_info=True)
            try:
                processing_time_ms = int(
                    (datetime.now() - start_time).total_seconds() * 1000
                )
                metrics = get_metrics_storage()
                metrics.record_transcription(
                    audio_format=original_audio_format,
                    audio_duration_seconds=0.0,
                    audio_size_bytes=original_audio_size,
                    sample_rate=16000,
                    transcript_length=0,
                    confidence=0.0,
                    processing_time_ms=processing_time_ms,
                    source="telegram",
                    error_message=f"Validation error: {str(e)}",
                    metadata={
                        "telegram_file_id": voice.file_id,
                        "telegram_duration": getattr(voice, "duration", None),
                        "queued": True,
                    },
                )
            except Exception as metrics_error:
                logger.warning(f"Failed to record error metrics: {metrics_error}")

            await status_msg.edit_text(
                f"❌ **Transcription validation error:**\n\n{str(e)}\n\n"
                "Please ensure your voice message is valid and try again."
            )
            return
        except Exception as e:
            # Handle unexpected errors
            logger.error(f"Unexpected STT error: {e}", exc_info=True)
            try:
                processing_time_ms = int(
                    (datetime.now() - start_time).total_seconds() * 1000
                )
                metrics = get_metrics_storage()
                metrics.record_transcription(
                    audio_format=original_audio_format,
                    audio_duration_seconds=0.0,
                    audio_size_bytes=original_audio_size,
                    sample_rate=16000,
                    transcript_length=0,
                    confidence=0.0,
                    processing_time_ms=processing_time_ms,
                    source="telegram",
                    error_message=f"Unexpected error: {str(e)}",
                    metadata={
                        "telegram_file_id": voice.file_id,
                        "telegram_duration": getattr(voice, "duration", None),
                        "queued": True,
                    },
                )
            except Exception as metrics_error:
                logger.warning(f"Failed to record error metrics: {metrics_error}")

            await status_msg.edit_text(
                f"❌ **Transcription failed:**\n\n{str(e)}\n\n" "Please try again."
            )
            return

        # Step 3: Send transcript to LLM service (same as original handler)
        await status_msg.edit_text("?? Processing with LLM...")
        try:
            from june_grpc_api.shim.llm import LLMClient
            from essence.services.telegram.dependencies.config import get_llm_address

            llm_address = get_llm_address()
            # Conversation history is not available (gateway removed for MVP)
            messages = []
            logger.debug(
                f"Using simple prompt without conversation history (gateway removed for MVP)"
            )

            # Get custom prompt template if available
            system_prompt = None
            try:
                template = ConversationStorage.get_prompt_template_for_conversation(
                    user_id, chat_id
                )

                if template and template.get("template_text"):
                    template_text = template["template_text"]
                    try:
                        system_prompt = template_text.format(
                            user_id=user_id,
                            chat_id=chat_id,
                            transcript=transcript,
                            detected_language=detected_language,
                        )
                        logger.info(
                            f"Using custom prompt template: {template.get('name')}"
                        )
                    except KeyError as e:
                        logger.warning(
                            f"Template variable not found: {e}, using template as-is"
                        )
                        system_prompt = template_text
                    except Exception as e:
                        logger.warning(
                            f"Error formatting template: {e}, using template as-is"
                        )
                        system_prompt = template_text
            except Exception as template_error:
                logger.debug(f"Could not load prompt template: {template_error}")

            chat_messages = []

            if system_prompt:
                chat_messages.append({"role": "system", "content": system_prompt})

            if messages:
                for msg in messages:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if role in ("system", "user", "assistant", "tool"):
                        if role == "system" and system_prompt:
                            continue
                        chat_messages.append({"role": role, "content": content})
                logger.info(
                    f"Using {len(chat_messages)} messages from conversation history"
                )

            chat_messages.append({"role": "user", "content": transcript})

            llm_start_time = datetime.now()
            from essence.services.telegram.telegram_utils import (
                stream_llm_response_to_telegram,
            )

            # Update status message to show we're starting streaming
            await status_msg.edit_text("💬 Generating response...")

            # Use connection pool for LLM with retry logic
            from essence.services.telegram.dependencies.grpc_pool import get_grpc_pool
            from essence.services.telegram.dependencies.retry import (
                retry_with_exponential_backoff,
            )

            async def call_llm():
                with tracer.start_as_current_span("llm.chat_stream") as span:
                    span.set_attribute("llm.message_count", len(chat_messages))
                    span.set_attribute("llm.user_id", str(user_id))
                    span.set_attribute("llm.chat_id", str(chat_id))
                    input_length = sum(
                        len(msg.get("content", "")) for msg in chat_messages
                    )
                    span.set_attribute("llm.input_length", input_length)

                    grpc_pool = get_grpc_pool()
                    async with grpc_pool.get_llm_channel() as channel:
                        llm_client = LLMClient(channel)
                        try:
                            # Stream LLM response to Telegram
                            (
                                llm_response,
                                stream_success,
                            ) = await stream_llm_response_to_telegram(
                                message=status_msg,
                                llm_stream=llm_client.chat_stream(chat_messages),
                                prefix="💬 **Response:**\n\n",
                                update_interval=0.1,
                            )
                            span.set_attribute(
                                "llm.response_length",
                                len(llm_response) if llm_response else 0,
                            )
                            span.set_attribute("llm.stream_success", stream_success)
                            return llm_response, stream_success
                        except Exception as e:
                            span.record_exception(e)
                            span.set_status(
                                trace.Status(trace.StatusCode.ERROR, str(e))
                            )
                            raise

            llm_response, stream_success = await retry_with_exponential_backoff(
                call_llm, max_retries=3, initial_delay=1.0
            )

            # Record LLM cost
            try:
                conversation_id = get_conversation_id_from_user_chat(user_id, chat_id)
                input_chars = sum(len(msg.get("content", "")) for msg in chat_messages)
                output_chars = len(llm_response) if llm_response else 0
                llm_cost = calculate_llm_cost(
                    input_characters=input_chars, output_characters=output_chars
                )
                record_cost(
                    service="llm",
                    user_id=user_id,
                    conversation_id=conversation_id,
                    cost=llm_cost,
                    metadata={
                        "input_characters": input_chars,
                        "output_characters": output_chars,
                        "message_count": len(chat_messages),
                        "source": "telegram",
                        "queued": True,
                        "streaming": True,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to record LLM cost: {e}")

            if not llm_response or not llm_response.strip():
                await status_msg.edit_text(
                    f"💬 **Transcription:**\n\n{transcript}\n\n"
                    "❌ LLM returned an empty response. Please try again."
                )
                return

            # Conversation history storage removed (gateway removed for MVP)
            # Language preference is stored via in-memory ConversationStorage
            logger.debug(f"Conversation history not saved (gateway removed for MVP)")

            logger.info(f"LLM response: {llm_response}")
        except Exception as e:
            logger.error(f"LLM error: {e}", exc_info=True)
            await status_msg.edit_text(
                f"?? **Transcription:**\n\n{transcript}\n\n"
                f"? LLM processing failed: {str(e)}\n\n"
                "Please try again."
            )
            return

        # Step 4: Send LLM response to TTS service (same as original handler)
        await status_msg.edit_text("?? Generating voice response...")
        try:
            from june_grpc_api.shim.tts import TextToSpeechClient
            from essence.services.telegram.dependencies.config import get_tts_address

            tts_address = get_tts_address()

            # Use connection pool for TTS with retry logic
            from essence.services.telegram.dependencies.grpc_pool import get_grpc_pool
            from essence.services.telegram.dependencies.retry import (
                retry_with_exponential_backoff,
            )

            async def call_tts():
                with tracer.start_as_current_span("tts.synthesize") as span:
                    span.set_attribute("tts.text_length", len(llm_response))
                    span.set_attribute("tts.language", detected_language)
                    span.set_attribute("tts.voice_id", "default")
                    span.set_attribute("tts.user_id", str(user_id))
                    span.set_attribute("tts.chat_id", str(chat_id))

                    grpc_pool = get_grpc_pool()
                    async with grpc_pool.get_tts_channel() as channel:
                        tts_client = TextToSpeechClient(channel)
                        logger.info(f"Using language {detected_language} for TTS")
                        try:
                            tts_audio_bytes = await tts_client.synthesize(
                                llm_response,
                                voice_id="default",
                                language=detected_language,
                            )
                            span.set_attribute(
                                "tts.audio_size_bytes", len(tts_audio_bytes)
                            )
                            return tts_audio_bytes
                        except Exception as e:
                            span.record_exception(e)
                            span.set_status(
                                trace.Status(trace.StatusCode.ERROR, str(e))
                            )
                            raise

            tts_audio_bytes = await retry_with_exponential_backoff(
                call_tts, max_retries=3, initial_delay=1.0
            )

            # Calculate TTS audio duration and record cost
            tts_audio_duration = 0.0
            try:
                tts_audio_duration = (
                    len(tts_audio_bytes) / (16000 * 2) if tts_audio_bytes else 0.0
                )
                try:
                    tts_audio_array, tts_sr = librosa.load(
                        io.BytesIO(tts_audio_bytes), sr=16000
                    )
                    tts_audio_duration = len(tts_audio_array) / tts_sr
                except Exception:
                    pass

                conversation_id = get_conversation_id_from_user_chat(user_id, chat_id)
                tts_cost = calculate_tts_cost(tts_audio_duration)
                record_cost(
                    service="tts",
                    user_id=user_id,
                    conversation_id=conversation_id,
                    cost=tts_cost,
                    metadata={
                        "audio_duration_seconds": tts_audio_duration,
                        "text_length": len(llm_response),
                        "language": detected_language,
                        "source": "telegram",
                        "queued": True,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to record TTS cost: {e}")

            if not tts_audio_bytes or len(tts_audio_bytes) == 0:
                await status_msg.edit_text(
                    f"?? **Transcription:**\n\n{transcript}\n\n"
                    "? TTS returned empty audio. Please try again."
                )
                return

            logger.info(f"TTS generated audio: {len(tts_audio_bytes)} bytes")
        except Exception as e:
            logger.error(f"TTS error: {e}", exc_info=True)
            await status_msg.edit_text(
                f"?? **Transcription:**\n\n{transcript}\n\n"
                f"? TTS processing failed: {str(e)}\n\n"
                "Please try again."
            )
            return

        # Step 5: Convert TTS audio to OGG format
        await status_msg.edit_text("?? Preparing audio for delivery...")
        ogg_audio_path = None
        try:
            try:
                tts_audio = AudioSegment.from_wav(io.BytesIO(tts_audio_bytes))
            except Exception:
                try:
                    tts_audio = AudioSegment.from_file(io.BytesIO(tts_audio_bytes))
                except Exception as e:
                    raise ValueError(f"Could not decode TTS audio data: {e}")

            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_file:
                ogg_audio_path = temp_file.name

            optimal_preset, preset_info = find_optimal_compression(
                tts_audio,
                max_file_size=config.max_file_size
                if hasattr(config, "max_file_size")
                else 20 * 1024 * 1024,
                quality_threshold=0.7,
            )

            compression_info = export_audio_to_ogg_optimized(
                tts_audio, ogg_audio_path, preset=optimal_preset
            )

            logger.info(
                f"Converted TTS audio to OGG with compression: {ogg_audio_path}, "
                f"preset: {optimal_preset}, "
                f"size: {compression_info['compressed_size'] / 1024:.1f} KB, "
                f"compression ratio: {compression_info['compression_ratio']:.2f}x"
            )
        except Exception as e:
            logger.error(f"Audio conversion error: {e}", exc_info=True)

            await status_msg.edit_text(
                f"?? **Transcription:**\n\n{transcript}\n\n"
                f"? Audio conversion failed: {str(e)}\n\n"
                "Please try again."
            )
            return
        finally:
            # Clean up temp file if created (even if conversion failed)
            if ogg_audio_path and os.path.exists(ogg_audio_path):
                try:
                    os.unlink(ogg_audio_path)
                    logger.debug(
                        f"Cleaned up temporary file after conversion error: {ogg_audio_path}"
                    )
                except Exception as cleanup_error:
                    # Log warning but don't fail the operation
                    logger.warning(
                        f"Failed to delete temp file {ogg_audio_path} after conversion error: {cleanup_error}"
                    )

        # Step 6: Send voice response back to Telegram
        try:
            await status_msg.edit_text("🔄 Sending voice response...")

            # Use comprehensive error handling with retry logic
            success = await send_voice_with_error_handling(
                update=update,
                ogg_audio_path=ogg_audio_path,
                transcript=transcript,
                status_msg=status_msg,
                max_retries=3,
            )

            if not success:
                # Error handling and user feedback already done in send_voice_with_error_handling
                return
        finally:
            # Clean up temporary OGG file in all code paths (success, error, exception)
            if ogg_audio_path and os.path.exists(ogg_audio_path):
                try:
                    os.unlink(ogg_audio_path)
                    logger.debug(f"Cleaned up temporary file: {ogg_audio_path}")
                except Exception as e:
                    # Log warning but don't fail the operation
                    logger.warning(f"Failed to delete temp file {ogg_audio_path}: {e}")
    except Exception as e:
        logger.error(f"Error processing voice message from queue: {e}", exc_info=True)

        # Clean up any temporary files that might have been created
        # Note: ogg_audio_path is defined in the inner try block, so we need to check if it exists
        # This is a fallback cleanup in case the inner exception handlers didn't run
        try:
            # Check if ogg_audio_path was set in the outer scope
            if (
                "ogg_audio_path" in locals()
                and ogg_audio_path
                and os.path.exists(ogg_audio_path)
            ):
                try:
                    os.unlink(ogg_audio_path)
                    logger.debug(
                        f"Cleaned up temporary file in outer exception handler: {ogg_audio_path}"
                    )
                except Exception as cleanup_error:
                    logger.warning(
                        f"Failed to delete temp file {ogg_audio_path} in outer exception handler: {cleanup_error}"
                    )
        except Exception:
            # Ignore errors accessing locals() or file operations
            pass

        await status_msg.edit_text(
            f"? Error processing voice message: {str(e)}\n\n" "Please try again later."
        )
