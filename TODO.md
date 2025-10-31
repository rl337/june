# TODO.md - Telegram Voice-to-Text-to-Voice Service

This document tracks tasks required to implement a Telegram bot service that enables voice messages to be transcribed, processed by the LLM, and returned as voice responses.

## 🎯 Goal
Create a Telegram bot that:
1. Receives voice messages from users
2. Transcribes voice to text using STT service
3. Processes text through LLM (Inference API)
4. Converts LLM response to speech using TTS service
5. Sends voice response back to user via Telegram

## 📋 Implementation Tasks

### Phase 1: Telegram Bot Foundation
- [ ] Create `services/telegram/` directory structure
  - [ ] Main bot file (`main.py`)
  - [ ] Dockerfile for telegram service
  - [ ] Requirements file (`requirements.txt`)
  - [ ] Configuration management
- [ ] Set up Telegram Bot API integration
  - [ ] Install `python-telegram-bot` library
  - [ ] Configure bot token from environment
  - [ ] Implement basic command handlers (start, help, status)
  - [ ] Add webhook or polling configuration
- [ ] Add Telegram service to `docker-compose.yml`
  - [ ] Define service configuration
  - [ ] Set environment variables (TELEGRAM_BOT_TOKEN, etc.)
  - [ ] Configure network connectivity to other services
  - [ ] Add health check endpoint

### Phase 2: Voice Message Handling
- [ ] Implement voice message reception
  - [ ] Handle Telegram `Voice` message type
  - [ ] Download voice file from Telegram
  - [ ] Convert Telegram audio format (OGG) to WAV/PCM for STT
  - [ ] Implement file size and duration limits
- [ ] Integrate with STT service
  - [ ] Create gRPC client for STT service
  - [ ] Send audio to STT `Recognize` endpoint
  - [ ] Handle STT errors and timeouts
  - [ ] Extract transcribed text from STT response
- [ ] Add audio format conversion utilities
  - [ ] OGG to WAV conversion (using ffmpeg or pydub)
  - [ ] Sample rate conversion (16kHz for Whisper)
  - [ ] Mono channel conversion
  - [ ] Audio validation (duration, size checks)

### Phase 3: LLM Integration
- [ ] Integrate with Inference API service
  - [ ] Create gRPC client for Inference API
  - [ ] Send transcribed text to LLM `Chat` or `Generate` endpoint
  - [ ] Handle streaming vs. one-shot generation
  - [ ] Implement conversation context/history per user
- [ ] Implement conversation management
  - [ ] Store conversation history per user/chat
  - [ ] Maintain context window limits
  - [ ] Handle conversation resets (new command)
  - [ ] Optional: Store conversations in PostgreSQL

### Phase 4: TTS Integration
- [ ] Integrate with TTS service
  - [ ] Create gRPC client for TTS service
  - [ ] Send LLM response text to TTS `Synthesize` endpoint
  - [ ] Handle TTS errors and timeouts
  - [ ] Receive audio bytes from TTS response
- [ ] Implement audio format conversion for Telegram
  - [ ] Convert PCM/WAV to OGG/OPUS (Telegram's preferred format)
  - [ ] Optimize audio quality and file size
  - [ ] Handle audio duration limits (Telegram max ~1 minute)
  - [ ] Compress audio if needed

### Phase 5: Response Delivery
- [ ] Send voice response to Telegram
  - [ ] Upload audio file to Telegram as voice message
  - [ ] Handle Telegram API rate limits
  - [ ] Implement retry logic for failed sends
  - [ ] Provide user feedback (typing indicators, status messages)
- [ ] Add error handling and user feedback
  - [ ] Error messages for transcription failures
  - [ ] Error messages for LLM failures
  - [ ] Error messages for TTS failures
  - [ ] Error messages for Telegram API failures
  - [ ] Progress indicators (e.g., "Transcribing...", "Processing...")

### Phase 6: Testing & Validation
- [ ] Create unit tests for Telegram bot
  - [ ] Mock Telegram API calls
  - [ ] Mock STT/TTS/LLM service calls
  - [ ] Test audio format conversions
  - [ ] Test error handling paths
- [ ] Create integration tests
  - [ ] End-to-end voice message flow
  - [ ] Test with real services (STT, TTS, Inference API)
  - [ ] Test error scenarios
  - [ ] Test concurrent requests
- [ ] Add validation test suite
  - [ ] Test voice message round-trip accuracy
  - [ ] Test response quality and latency
  - [ ] Test with various audio qualities and lengths

### Phase 7: Deployment & Monitoring
- [ ] Add monitoring and logging
  - [ ] Prometheus metrics (requests, latencies, errors)
  - [ ] Structured logging for debugging
  - [ ] Health check endpoint
  - [ ] Request tracing
- [ ] Configure production settings
  - [ ] Webhook setup for production (vs. polling for dev)
  - [ ] Rate limiting per user
  - [ ] Resource limits (memory, CPU)
  - [ ] Graceful shutdown handling
- [ ] Documentation
  - [ ] Update README.md with Telegram bot setup
  - [ ] Document environment variables
  - [ ] Add usage examples
  - [ ] Troubleshooting guide

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
- See `AGENTS.md` for development guidelines
- See service-specific READMEs for API details

