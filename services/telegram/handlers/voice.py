"""Voice message handler for Telegram bot."""
import io
import logging
from datetime import datetime
from typing import TYPE_CHECKING

import grpc.aio
import librosa
from telegram import Update
from telegram.ext import ContextTypes

from audio_utils import (
    prepare_audio_for_stt,
    AudioValidationError,
    MAX_AUDIO_DURATION_SECONDS,
    MAX_AUDIO_SIZE_BYTES
)

if TYPE_CHECKING:
    from june_grpc_api import asr as asr_shim

logger = logging.getLogger(__name__)


async def handle_voice_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    config,
    stt_address: str,
    get_metrics_storage
):
    """Handle incoming voice messages."""
    voice = update.message.voice
    
    # Check file size
    if voice.file_size and voice.file_size > config.max_file_size:
        await update.message.reply_text(
            f"? Voice message too large. Maximum size: {config.max_file_size / (1024 * 1024):.1f} MB"
        )
        return
    
    # Send processing status
    status_msg = await update.message.reply_text("?? Processing your voice message...")
    
    try:
        # Step 1: Download voice file from Telegram
        file = await context.bot.get_file(voice.file_id)
        audio_data = await file.download_as_bytearray()
        audio_data_bytes = bytes(audio_data)
        
        logger.info(f"Downloaded voice file: {len(audio_data_bytes)} bytes")
        
        # Step 2: Convert OGG to WAV and prepare for STT (16kHz mono)
        try:
            stt_audio = prepare_audio_for_stt(audio_data_bytes, is_ogg=True)
            logger.info(f"Prepared audio for STT: {len(stt_audio)} bytes")
        except AudioValidationError as e:
            await status_msg.edit_text(
                f"? Audio validation failed: {str(e)}\n\n"
                "Please ensure your voice message is:\n"
                f"? Under {MAX_AUDIO_DURATION_SECONDS} seconds\n"
                f"? Under {MAX_AUDIO_SIZE_BYTES / (1024 * 1024):.0f} MB"
            )
            return
        except Exception as e:
            logger.error(f"Error preparing audio: {e}", exc_info=True)
            await status_msg.edit_text(
                f"? Error processing audio: {str(e)}\n\n"
                "Please try again."
            )
            return
        
        # Step 3: Send to STT
        await status_msg.edit_text("?? Transcribing your voice message...")
        start_time = datetime.now()
        original_audio_size = len(audio_data_bytes)
        original_audio_format = "ogg"  # Telegram sends OGG/OPUS
        
        try:
            # Import here to avoid circular dependencies
            from june_grpc_api import asr as asr_shim
            
            async with grpc.aio.insecure_channel(stt_address) as channel:
                stt_client = asr_shim.SpeechToTextClient(channel)
                cfg = asr_shim.RecognitionConfig(language="en", interim_results=False)
                result = await stt_client.recognize(
                    stt_audio,
                    sample_rate=16000,
                    encoding="wav",
                    config=cfg
                )
                transcript = result.transcript
            
            # Calculate processing time and audio duration
            processing_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            # Calculate audio duration from the prepared audio
            try:
                audio_array, sr = librosa.load(io.BytesIO(stt_audio), sr=16000)
                audio_duration = len(audio_array) / sr
            except Exception:
                # Fallback: estimate from size (rough approximation)
                audio_duration = len(stt_audio) / (16000 * 2)  # 16kHz, 16-bit = 2 bytes/sample
            
            # Record metrics
            try:
                metrics = get_metrics_storage()
                metrics.record_transcription(
                    audio_format=original_audio_format,
                    audio_duration_seconds=audio_duration,
                    audio_size_bytes=original_audio_size,
                    sample_rate=16000,
                    transcript_length=len(transcript),
                    confidence=getattr(result, "confidence", 0.9),
                    processing_time_ms=processing_time_ms,
                    source="telegram",
                    metadata={
                        "telegram_file_id": voice.file_id,
                        "telegram_duration": getattr(voice, "duration", None),
                        "prepared_audio_size": len(stt_audio)
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to record transcription metrics: {e}")
            
            logger.info(f"Transcription: {transcript}")
        except Exception as e:
            # Record error metrics
            try:
                processing_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                metrics = get_metrics_storage()
                metrics.record_transcription(
                    audio_format=original_audio_format,
                    audio_duration_seconds=0.0,  # Unknown due to error
                    audio_size_bytes=original_audio_size,
                    sample_rate=16000,
                    transcript_length=0,
                    confidence=0.0,
                    processing_time_ms=processing_time_ms,
                    source="telegram",
                    error_message=str(e),
                    metadata={
                        "telegram_file_id": voice.file_id,
                        "telegram_duration": getattr(voice, "duration", None)
                    }
                )
            except Exception as metrics_error:
                logger.warning(f"Failed to record error metrics: {metrics_error}")
            
            logger.error(f"STT error: {e}", exc_info=True)
            await status_msg.edit_text(
                f"? Transcription failed: {str(e)}\n\n"
                "Please try again."
            )
            return
        
        # TODO: Steps 4-7 will be implemented in next phases
        # Step 4: Send to LLM
        # Step 5: Send to TTS
        # Step 6: Convert to OGG
        # Step 7: Send response
        
        await status_msg.edit_text(
            f"?? **Transcription:**\n\n{transcript}\n\n"
            "?? LLM and TTS processing will be implemented in Phase 3-4."
        )
    except Exception as e:
        logger.error(f"Error processing voice message: {e}", exc_info=True)
        await status_msg.edit_text(
            f"? Error processing voice message: {str(e)}\n\n"
            "Please try again later."
        )
