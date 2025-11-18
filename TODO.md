# TODO.md - Telegram Voice-to-Text-to-Voice Service

> **⚠️ NOTE: This file is OUTDATED and kept for historical reference only.**
> 
> **All tasks listed in this file have been COMPLETED.** The Telegram bot service is fully implemented and operational.
> 
> **For current project status and tasks, see `REFACTOR_PLAN.md` which is the authoritative source.**

This document tracks tasks required to implement a Telegram bot service that enables voice messages to be transcribed, processed by the LLM, and returned as voice responses.

**Status:** ✅ **ALL TASKS COMPLETED** - The Telegram bot service is fully implemented with all features listed below.

## 🎯 Goal
Create a Telegram bot that:
1. Receives voice messages from users
2. Transcribes voice to text using STT service
3. Processes text through LLM (Inference API)
4. Converts LLM response to speech using TTS service
5. Sends voice response back to user via Telegram

## 📋 Implementation Tasks

### Phase 1: Telegram Bot Foundation
- [x] Create `services/telegram/` directory structure
  - [x] Main bot file (`main.py`)
  - [x] Dockerfile for telegram service
  - [x] Requirements file (`requirements.txt`)
  - [x] Configuration management
- [x] Set up Telegram Bot API integration
  - [x] Install `python-telegram-bot` library
  - [x] Configure bot token from environment
  - [x] Implement basic command handlers (start, help, status)
  - [x] Add webhook or polling configuration
- [x] Add Telegram service to `docker-compose.yml`
  - [x] Define service configuration
  - [x] Set environment variables (TELEGRAM_BOT_TOKEN, etc.)
  - [x] Configure network connectivity to other services
  - [x] Add health check endpoint

### Phase 2: Voice Message Handling
- [x] Implement voice message reception
  - [x] Handle Telegram `Voice` message type
  - [x] Download voice file from Telegram
  - [x] Convert Telegram audio format (OGG) to WAV/PCM for STT
  - [x] Implement file size and duration limits
- [x] Integrate with STT service
  - [x] Create gRPC client for STT service
  - [x] Send audio to STT `Recognize` endpoint
  - [x] Handle STT errors and timeouts
  - [x] Extract transcribed text from STT response
- [x] Add audio format conversion utilities
  - [x] OGG to WAV conversion (using ffmpeg or pydub)
  - [x] Sample rate conversion (16kHz for Whisper)
  - [x] Mono channel conversion
  - [x] Audio validation (duration, size checks)

### Phase 3: LLM Integration
- [x] Integrate with Inference API service
  - [x] Create gRPC client for Inference API
  - [x] Send transcribed text to LLM `Chat` or `Generate` endpoint
  - [x] Handle streaming vs. one-shot generation
  - [x] Implement conversation context/history per user
- [x] Implement conversation management
  - [x] Store conversation history per user/chat
  - [x] Maintain context window limits
  - [x] Handle conversation resets (new command)
  - [x] Optional: Store conversations in PostgreSQL (using in-memory storage instead)

### Phase 4: TTS Integration
- [x] Integrate with TTS service
  - [x] Create gRPC client for TTS service
  - [x] Send LLM response text to TTS `Synthesize` endpoint
  - [x] Handle TTS errors and timeouts
  - [x] Receive audio bytes from TTS response
- [x] Implement audio format conversion for Telegram
  - [x] Convert PCM/WAV to OGG/OPUS (Telegram's preferred format)
  - [x] Optimize audio quality and file size
  - [x] Handle audio duration limits (Telegram max ~1 minute)
  - [x] Compress audio if needed

### Phase 5: Response Delivery
- [x] Send voice response to Telegram
  - [x] Upload audio file to Telegram as voice message
  - [x] Handle Telegram API rate limits
  - [x] Implement retry logic for failed sends
  - [x] Provide user feedback (typing indicators, status messages)
- [x] Add error handling and user feedback
  - [x] Error messages for transcription failures
  - [x] Error messages for LLM failures
  - [x] Error messages for TTS failures
  - [x] Error messages for Telegram API failures
  - [x] Progress indicators (e.g., "Transcribing...", "Processing...")

### Phase 6: Testing & Validation
- [x] Create unit tests for Telegram bot
  - [x] Mock Telegram API calls
  - [x] Mock STT/TTS/LLM service calls
  - [x] Test audio format conversions
  - [x] Test error handling paths
- [x] Create integration tests
  - [x] End-to-end voice message flow
  - [x] Test with real services (STT, TTS, Inference API)
  - [x] Test error scenarios
  - [x] Test concurrent requests
- [x] Add validation test suite
  - [x] Test voice message round-trip accuracy
  - [x] Test response quality and latency
  - [x] Test with various audio qualities and lengths

### Phase 7: Deployment & Monitoring
- [x] Add monitoring and logging
  - [x] Prometheus metrics (requests, latencies, errors)
  - [x] Structured logging for debugging
  - [x] Health check endpoint
  - [x] Request tracing (OpenTelemetry)
- [x] Configure production settings
  - [x] Webhook setup for production (vs. polling for dev)
  - [x] Rate limiting per user
  - [x] Resource limits (memory, CPU)
  - [x] Graceful shutdown handling
- [x] Documentation
  - [x] Update README.md with Telegram bot setup
  - [x] Document environment variables
  - [x] Add usage examples
  - [x] Troubleshooting guide

## 🔧 Technical Details

### Service Dependencies
- **STT Service** (gRPC, port 50052): Speech-to-text conversion
- **TTS Service** (gRPC, port 50053): Text-to-speech synthesis
- **Inference API** (gRPC, port 50051): LLM text generation
- **Telegram Bot API**: Send/receive messages

### Audio Format Conversions
- **Telegram → STT**: OGG → WAV (16kHz, mono, PCM)
- **TTS → Telegram**: PCM/WAV → OGG/OPUS (optimized for voice)

### Environment Variables
```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_WEBHOOK_URL=https://your-domain.com/webhook  # Optional for production
TELEGRAM_MAX_FILE_SIZE=20971520  # 20MB default
STT_URL=grpc://stt:50052
TTS_URL=grpc://tts:50053
LLM_URL=grpc://inference-api:50051
```

### Expected Flow
```
User → Telegram (Voice) 
  → Telegram Bot (download, convert)
    → STT Service (transcribe)
      → Inference API (generate response)
        → TTS Service (synthesize)
          → Telegram Bot (convert, upload)
            → User (Voice response)
```

## 📝 Notes
- Consider using webhook mode for production (lower latency)
- Polling mode acceptable for development
- Implement conversation timeout (e.g., 30 minutes of inactivity)
- Add user feedback for long processing times
- Consider streaming responses for better UX (if Telegram supports)

## 🔗 Related Documentation
- See `README.md` for architecture overview
- See `docs/guides/AGENTS.md` for development guidelines
- See `docs/README.md` for comprehensive documentation index
- See service-specific READMEs for API details


