"""Voice message handler for Telegram bot."""
import io
import logging
import tempfile
import os
from datetime import datetime
from typing import TYPE_CHECKING

import grpc.aio
import librosa
from pydub import AudioSegment
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
        
        # Step 4: Send transcript to LLM service
        await status_msg.edit_text("?? Processing with LLM...")
        try:
            from june_grpc_api.shim.llm import LLMClient
            from dependencies.config import get_llm_address
            
            llm_address = get_llm_address()
            
            # Initialize conversation storage for maintaining history via HTTP API
            # Try to use conversation API if available, otherwise fall back to simple prompt
            conversation_api_url = os.getenv("CONVERSATION_API_URL", "http://gateway:8080")
            user_id = str(update.effective_user.id)
            chat_id = str(update.effective_chat.id)
            messages = []
            
            try:
                import httpx
                
                # Get or create conversation and retrieve history
                async with httpx.AsyncClient(timeout=5.0) as client:
                    # Get conversation with history (last 20 messages or up to 4000 tokens)
                    response = await client.get(
                        f"{conversation_api_url}/conversations/{user_id}/{chat_id}",
                        params={"limit": 20, "max_tokens": 4000}
                    )
                    
                    if response.status_code == 200:
                        conversation = response.json()
                        messages = conversation.get('messages', [])
                        logger.info(f"Retrieved {len(messages)} messages from conversation history")
                    elif response.status_code == 404:
                        # Conversation doesn't exist yet, create it
                        create_response = await client.post(
                            f"{conversation_api_url}/conversations/{user_id}/{chat_id}"
                        )
                        if create_response.status_code == 200:
                            conversation = create_response.json()
                            messages = conversation.get('messages', [])
                            logger.info(f"Created new conversation, retrieved {len(messages)} messages")
                    else:
                        logger.warning(f"Failed to get conversation: {response.status_code}, using simple prompt")
                        
            except Exception as conv_error:
                # If conversation API fails, fall back to simple prompt
                logger.warning(f"Failed to load conversation history: {conv_error}, using simple prompt")
            
            # Format conversation history into prompt string
            if messages:
                prompt_parts = []
                for msg in messages:
                    role = msg.get('role', 'user')
                    content = msg.get('content', '')
                    if role == 'user':
                        prompt_parts.append(f"User: {content}")
                    elif role == 'assistant':
                        prompt_parts.append(f"Assistant: {content}")
                    elif role == 'system':
                        prompt_parts.append(f"System: {content}")
                
                # Add new user message (transcript)
                prompt_parts.append(f"User: {transcript}")
                prompt_parts.append("Assistant:")
                
                # Combine into single prompt
                llm_prompt = "\n\n".join(prompt_parts)
                logger.info(f"LLM prompt with {len(messages)} previous messages")
            else:
                # No conversation history available, use simple prompt
                llm_prompt = transcript
            
            async with grpc.aio.insecure_channel(llm_address) as channel:
                llm_client = LLMClient(channel)
                llm_response = await llm_client.generate(llm_prompt)
                
            if not llm_response or not llm_response.strip():
                await status_msg.edit_text(
                    f"?? **Transcription:**\n\n{transcript}\n\n"
                    "?? LLM returned an empty response. Please try again."
                )
                return
            
            # Add messages to conversation history via HTTP API
            try:
                import httpx
                conversation_api_url = os.getenv("CONVERSATION_API_URL", "http://gateway:8080")
                
                async with httpx.AsyncClient(timeout=5.0) as client:
                    # Add user message (transcript)
                    user_msg_response = await client.post(
                        f"{conversation_api_url}/conversations/{user_id}/{chat_id}/messages",
                        json={"role": "user", "content": transcript}
                    )
                    
                    # Add assistant message (LLM response)
                    assistant_msg_response = await client.post(
                        f"{conversation_api_url}/conversations/{user_id}/{chat_id}/messages",
                        json={"role": "assistant", "content": llm_response}
                    )
                    
                    if user_msg_response.status_code in (200, 201) and assistant_msg_response.status_code in (200, 201):
                        logger.info(f"Added user and assistant messages to conversation {user_id}/{chat_id}")
                    else:
                        logger.warning(f"Failed to save messages: user={user_msg_response.status_code}, assistant={assistant_msg_response.status_code}")
            except Exception as save_error:
                logger.warning(f"Failed to save conversation history: {save_error}")
            
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
        try:
            from june_grpc_api.shim.tts import TextToSpeechClient
            from dependencies.config import get_tts_address
            
            tts_address = get_tts_address()
            
            async with grpc.aio.insecure_channel(tts_address) as channel:
                tts_client = TextToSpeechClient(channel)
                tts_audio_bytes = await tts_client.synthesize(
                    llm_response,
                    voice_id="default",
                    language="en"
                )
            
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
        
        # Step 6: Convert TTS audio to OGG format (Telegram voice message format)
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
            with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as temp_file:
                ogg_audio_path = temp_file.name
            
            # Export to OGG format (OPUS codec)
            tts_audio.export(ogg_audio_path, format="ogg", codec="libopus")
            
            logger.info(f"Converted TTS audio to OGG: {ogg_audio_path}")
        except Exception as e:
            logger.error(f"Audio conversion error: {e}", exc_info=True)
            # Clean up temp file if created
            if ogg_audio_path and os.path.exists(ogg_audio_path):
                try:
                    os.unlink(ogg_audio_path)
                except Exception:
                    pass
            
            await status_msg.edit_text(
                f"?? **Transcription:**\n\n{transcript}\n\n"
                f"? Audio conversion failed: {str(e)}\n\n"
                "Please try again."
            )
            return
        
        # Step 7: Send voice response back to Telegram
        try:
            await status_msg.edit_text("?? Sending voice response...")
            
            with open(ogg_audio_path, 'rb') as audio_file:
                await update.message.reply_voice(
                    voice=audio_file,
                    caption=f"Response to: {transcript[:100]}..."
                )
            
            logger.info("Voice response sent successfully")
            
            # Delete temporary OGG file
            try:
                os.unlink(ogg_audio_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp file {ogg_audio_path}: {e}")
            
            # Update status message to indicate success
            await status_msg.edit_text("? Voice response sent!")
            
        except Exception as e:
            logger.error(f"Telegram API error: {e}", exc_info=True)
            
            # Clean up temp file
            if ogg_audio_path and os.path.exists(ogg_audio_path):
                try:
                    os.unlink(ogg_audio_path)
                except Exception:
                    pass
            
            await status_msg.edit_text(
                f"?? **Transcription:**\n\n{transcript}\n\n"
                f"? Failed to send voice response: {str(e)}\n\n"
                "Please try again."
            )
            return
    except Exception as e:
        logger.error(f"Error processing voice message: {e}", exc_info=True)
        await status_msg.edit_text(
            f"? Error processing voice message: {str(e)}\n\n"
            "Please try again later."
        )
