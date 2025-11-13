# STT Service (Speech-to-Text) API

The STT Service provides gRPC endpoints for speech recognition and transcription.

## Service Definition

**Service Name:** `june.asr.SpeechToText`

**Default Address:** `localhost:50052`

## Protocol Buffer Definition

The service is defined in `proto/asr.proto`:

```protobuf
service SpeechToText {
  rpc RecognizeStream(stream AudioChunk) returns (stream RecognitionResult);
  rpc Recognize(RecognitionRequest) returns (RecognitionResponse);
  rpc HealthCheck(HealthRequest) returns (HealthResponse);
}
```

## Methods

### RecognizeStream

Streaming speech recognition for real-time transcription.

**Request (stream):**
```protobuf
message AudioChunk {
  bytes audio_data = 1;
  int32 sample_rate = 2;
  int32 channels = 3;
  string encoding = 4;  // "pcm", "opus", "webm"
  int64 timestamp_us = 5;
}
```

**Response (stream):**
```protobuf
message RecognitionResult {
  string transcript = 1;
  bool is_final = 2;
  float confidence = 3;
  repeated WordInfo words = 4;
  int64 start_time_us = 5;
  int64 end_time_us = 6;
  string speaker_id = 7;  // If diarization enabled
  string detected_language = 8;  // ISO 639-1 code
}
```

**Example (Python):**
```python
import grpc
import asyncio
from june_grpc_api import asr as asr_shim

async def recognize_stream():
    async with grpc.aio.insecure_channel("localhost:50052") as channel:
        client = asr_shim.SpeechToTextClient(channel)
        
        # Read audio file in chunks
        with open("audio.wav", "rb") as f:
            audio_data = f.read()
            chunk_size = 4096
            
            async def audio_chunks():
                for i in range(0, len(audio_data), chunk_size):
                    chunk = audio_data[i:i+chunk_size]
                    yield asr_shim.AudioChunk(
                        audio_data=chunk,
                        sample_rate=16000,
                        channels=1,
                        encoding="pcm"
                    )
            
            async for result in client.recognize_stream(audio_chunks()):
                if result.is_final:
                    print(f"Final: {result.transcript}")
                    print(f"Confidence: {result.confidence}")
                    print(f"Language: {result.detected_language}")
                else:
                    print(f"Interim: {result.transcript}")

asyncio.run(recognize_stream())
```

### Recognize

One-shot speech recognition.

**Request:**
```protobuf
message RecognitionRequest {
  bytes audio_data = 1;
  int32 sample_rate = 2;
  string encoding = 3;
  RecognitionConfig config = 4;
}

message RecognitionConfig {
  string language = 1;  // ISO 639-1 code, e.g. "en"
  bool interim_results = 2;
  bool enable_vad = 3;  // Voice Activity Detection
  bool enable_diarization = 4;
  bool enable_timestamps = 5;
}
```

**Response:**
```protobuf
message RecognitionResponse {
  repeated RecognitionResult results = 1;
  int32 processing_time_ms = 2;
}
```

**Example (Python):**
```python
import grpc
import asyncio
from june_grpc_api import asr as asr_shim

async def recognize():
    async with grpc.aio.insecure_channel("localhost:50052") as channel:
        client = asr_shim.SpeechToTextClient(channel)
        
        # Read audio file
        with open("audio.wav", "rb") as f:
            audio_data = f.read()
        
        config = asr_shim.RecognitionConfig(
            language="en",
            interim_results=False,
            enable_vad=True,
            enable_diarization=False,
            enable_timestamps=True
        )
        
        request = asr_shim.RecognitionRequest(
            audio_data=audio_data,
            sample_rate=16000,
            encoding="wav",
            config=config
        )
        
        response = await client.recognize(request)
        
        for result in response.results:
            print(f"Transcript: {result.transcript}")
            print(f"Confidence: {result.confidence}")
            if result.words:
                print("Words:")
                for word in result.words:
                    print(f"  {word.word} (confidence: {word.confidence})")

asyncio.run(recognize())
```

### HealthCheck

Check service health.

**Request:**
```protobuf
message HealthRequest {}
```

**Response:**
```protobuf
message HealthResponse {
  bool healthy = 1;
  string version = 2;
  string model_name = 3;
}
```

**Example (Python):**
```python
import grpc
import asyncio
from june_grpc_api import asr as asr_shim

async def health_check():
    async with grpc.aio.insecure_channel("localhost:50052") as channel:
        client = asr_shim.SpeechToTextClient(channel)
        response = await client.health_check(asr_shim.HealthRequest())
        print(f"Healthy: {response.healthy}")
        print(f"Model: {response.model_name}")

asyncio.run(health_check())
```

## Message Types

### AudioChunk

Audio data chunk for streaming.

**Fields:**
- `audio_data`: Raw audio bytes
- `sample_rate`: Sample rate in Hz (e.g., 16000, 44100)
- `channels`: Number of audio channels (1 = mono, 2 = stereo)
- `encoding`: Audio encoding format ("pcm", "opus", "webm")
- `timestamp_us`: Timestamp in microseconds

### RecognitionResult

Recognition result (partial or final).

**Fields:**
- `transcript`: Transcribed text
- `is_final`: Whether this is a final result (true) or interim (false)
- `confidence`: Confidence score (0.0-1.0)
- `words`: Word-level information (if timestamps enabled)
- `start_time_us`: Start time in microseconds
- `end_time_us`: End time in microseconds
- `speaker_id`: Speaker identifier (if diarization enabled)
- `detected_language`: Detected language code (ISO 639-1)

### WordInfo

Word-level information with timestamps.

```protobuf
message WordInfo {
  string word = 1;
  float confidence = 2;
  int64 start_time_us = 3;
  int64 end_time_us = 4;
}
```

### RecognitionConfig

Recognition configuration options.

**Fields:**
- `language`: Language code (ISO 639-1, e.g., "en", "es", "fr"). Use "auto" for automatic detection.
- `interim_results`: Return interim (partial) results during recognition
- `enable_vad`: Enable Voice Activity Detection to filter silence
- `enable_diarization`: Enable speaker diarization (identify different speakers)
- `enable_timestamps`: Include word-level timestamps

## Audio Format Requirements

### Supported Formats

- **PCM**: Raw PCM audio (16-bit, little-endian)
- **WAV**: WAV file format
- **Opus**: Opus codec
- **WebM**: WebM container with Opus audio

### Recommended Settings

- **Sample Rate**: 16000 Hz (16 kHz) or 44100 Hz (44.1 kHz)
- **Channels**: Mono (1 channel) recommended for best accuracy
- **Bit Depth**: 16-bit
- **Encoding**: PCM or WAV for best compatibility

### Audio File Conversion

**Example: Convert audio to required format (using ffmpeg):**
```bash
# Convert to 16kHz mono WAV
ffmpeg -i input.mp3 -ar 16000 -ac 1 -f wav output.wav

# Convert to PCM
ffmpeg -i input.mp3 -ar 16000 -ac 1 -f s16le output.pcm
```

## Usage Examples

### Basic Transcription

```python
import grpc
import asyncio
from june_grpc_api import asr as asr_shim

async def transcribe_file(filename):
    async with grpc.aio.insecure_channel("localhost:50052") as channel:
        client = asr_shim.SpeechToTextClient(channel)
        
        with open(filename, "rb") as f:
            audio_data = f.read()
        
        config = asr_shim.RecognitionConfig(language="en")
        request = asr_shim.RecognitionRequest(
            audio_data=audio_data,
            sample_rate=16000,
            encoding="wav",
            config=config
        )
        
        response = await client.recognize(request)
        return response.results[0].transcript if response.results else ""

# Usage
transcript = asyncio.run(transcribe_file("audio.wav"))
print(transcript)
```

### Real-time Streaming

```python
import grpc
import asyncio
from june_grpc_api import asr as asr_shim

async def stream_transcription(audio_source):
    async with grpc.aio.insecure_channel("localhost:50052") as channel:
        client = asr_shim.SpeechToTextClient(channel)
        
        async def audio_stream():
            # Read audio from source (microphone, file, etc.)
            while True:
                chunk = await audio_source.read_chunk()
                if not chunk:
                    break
                yield asr_shim.AudioChunk(
                    audio_data=chunk,
                    sample_rate=16000,
                    channels=1,
                    encoding="pcm"
                )
        
        config = asr_shim.RecognitionConfig(
            language="en",
            interim_results=True,
            enable_vad=True
        )
        
        async for result in client.recognize_stream(audio_stream()):
            if result.is_final:
                print(f"[FINAL] {result.transcript}")
            else:
                print(f"[INTERIM] {result.transcript}", end="\r")
```

### Multi-language Detection

```python
import grpc
import asyncio
from june_grpc_api import asr as asr_shim

async def detect_language(filename):
    async with grpc.aio.insecure_channel("localhost:50052") as channel:
        client = asr_shim.SpeechToTextClient(channel)
        
        with open(filename, "rb") as f:
            audio_data = f.read()
        
        # Use "auto" for automatic language detection
        config = asr_shim.RecognitionConfig(language="auto")
        request = asr_shim.RecognitionRequest(
            audio_data=audio_data,
            sample_rate=16000,
            encoding="wav",
            config=config
        )
        
        response = await client.recognize(request)
        if response.results:
            result = response.results[0]
            print(f"Detected language: {result.detected_language}")
            print(f"Transcript: {result.transcript}")
```

### Word-level Timestamps

```python
import grpc
import asyncio
from june_grpc_api import asr as asr_shim

async def transcribe_with_timestamps(filename):
    async with grpc.aio.insecure_channel("localhost:50052") as channel:
        client = asr_shim.SpeechToTextClient(channel)
        
        with open(filename, "rb") as f:
            audio_data = f.read()
        
        config = asr_shim.RecognitionConfig(
            language="en",
            enable_timestamps=True
        )
        request = asr_shim.RecognitionRequest(
            audio_data=audio_data,
            sample_rate=16000,
            encoding="wav",
            config=config
        )
        
        response = await client.recognize(request)
        if response.results and response.results[0].words:
            for word in response.results[0].words:
                start_sec = word.start_time_us / 1_000_000
                end_sec = word.end_time_us / 1_000_000
                print(f"{start_sec:.2f}s - {end_sec:.2f}s: {word.word} (confidence: {word.confidence:.2f})")
```

## Error Handling

gRPC errors follow standard gRPC status codes:

- `OK (0)`: Success
- `INVALID_ARGUMENT (3)`: Invalid audio format or parameters
- `RESOURCE_EXHAUSTED (8)`: Rate limit exceeded
- `INTERNAL (13)`: Internal server error
- `UNAVAILABLE (14)`: Service unavailable

**Example:**
```python
import grpc
from june_grpc_api import asr as asr_shim

async def recognize_with_error_handling(filename):
    try:
        async with grpc.aio.insecure_channel("localhost:50052") as channel:
            client = asr_shim.SpeechToTextClient(channel)
            
            with open(filename, "rb") as f:
                audio_data = f.read()
            
            request = asr_shim.RecognitionRequest(
                audio_data=audio_data,
                sample_rate=16000,
                encoding="wav",
                config=asr_shim.RecognitionConfig(language="en")
            )
            
            response = await client.recognize(request)
            return response.results[0].transcript if response.results else ""
            
    except grpc.aio.AioRpcError as e:
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            print(f"Invalid audio format: {e.details()}")
        elif e.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:
            print(f"Rate limit exceeded: {e.details()}")
        else:
            print(f"Error: {e.code()}: {e.details()}")
        return None
```

## Connection Pooling

For production use, use connection pooling:

```python
from june_grpc_api.grpc_pool import get_grpc_pool

async def use_pool():
    pool = get_grpc_pool()
    async with pool.get_stt_channel() as channel:
        client = asr_shim.SpeechToTextClient(channel)
        # Use client...
```

## Rate Limiting

Rate limiting is typically handled at the Gateway service level. Direct gRPC connections may have different limits. Check service documentation for specific rate limits.

## Best Practices

1. **Use appropriate sample rate**: 16kHz is sufficient for most use cases and reduces bandwidth
2. **Enable VAD for long audio**: Voice Activity Detection filters silence and improves accuracy
3. **Use streaming for real-time**: Use `RecognizeStream` for live transcription
4. **Handle interim results**: Show partial transcripts for better UX
5. **Check confidence scores**: Low confidence may indicate poor audio quality
6. **Specify language when known**: Improves accuracy vs. auto-detection
