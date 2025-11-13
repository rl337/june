# TTS Service (Text-to-Speech) API

The TTS Service provides gRPC endpoints for text-to-speech synthesis.

## Service Definition

**Service Name:** `june.tts.TextToSpeech`

**Default Address:** `localhost:50053`

## Protocol Buffer Definition

The service is defined in `proto/tts.proto`:

```protobuf
service TextToSpeech {
  rpc SynthesizeStream(stream SynthesisRequest) returns (stream AudioChunk);
  rpc Synthesize(SynthesisRequest) returns (AudioResponse);
  rpc HealthCheck(HealthRequest) returns (HealthResponse);
}
```

## Methods

### SynthesizeStream

Streaming text-to-speech synthesis for real-time audio generation.

**Request (stream):**
```protobuf
message SynthesisRequest {
  string text = 1;
  string voice_id = 2;
  string language = 3;  // ISO 639-1 code
  SynthesisConfig config = 4;
  bool stream = 5;  // Whether to stream audio chunks
}
```

**Response (stream):**
```protobuf
message AudioChunk {
  bytes audio_data = 1;
  int32 sample_rate = 2;
  int32 channels = 3;
  string encoding = 4;  // "pcm16", "opus", "mp3"
  bool is_final = 5;
  int64 timestamp_us = 6;
}
```

**Example (Python):**
```python
import grpc
import asyncio
from june_grpc_api import tts as tts_shim

async def synthesize_stream():
    async with grpc.aio.insecure_channel("localhost:50053") as channel:
        client = tts_shim.TextToSpeechClient(channel)
        
        config = tts_shim.SynthesisConfig(
            speed=1.0,
            pitch=0.0,
            energy=0.5,
            prosody="neutral"
        )
        
        request = tts_shim.SynthesisRequest(
            text="Hello, this is a test of streaming text-to-speech.",
            voice_id="default",
            language="en",
            config=config,
            stream=True
        )
        
        async for chunk in client.synthesize_stream([request]):
            if chunk.audio_data:
                # Process audio chunk
                print(f"Received {len(chunk.audio_data)} bytes")
                if chunk.is_final:
                    print("Stream complete")

asyncio.run(synthesize_stream())
```

### Synthesize

One-shot text-to-speech synthesis.

**Request:**
```protobuf
message SynthesisRequest {
  string text = 1;
  string voice_id = 2;
  string language = 3;  // ISO 639-1 code
  SynthesisConfig config = 4;
  bool stream = 5;
}
```

**Response:**
```protobuf
message AudioResponse {
  bytes audio_data = 1;
  int32 sample_rate = 2;
  string encoding = 3;
  int32 duration_ms = 4;
}
```

**Example (Python):**
```python
import grpc
import asyncio
from june_grpc_api import tts as tts_shim

async def synthesize():
    async with grpc.aio.insecure_channel("localhost:50053") as channel:
        client = tts_shim.TextToSpeechClient(channel)
        
        config = tts_shim.SynthesisConfig(
            speed=1.0,
            pitch=0.0,
            energy=0.5,
            prosody="neutral"
        )
        
        request = tts_shim.SynthesisRequest(
            text="Hello, world! This is a test of text-to-speech synthesis.",
            voice_id="default",
            language="en",
            config=config
        )
        
        response = await client.synthesize(request)
        
        # Save audio to file
        with open("output.wav", "wb") as f:
            f.write(response.audio_data)
        
        print(f"Generated {len(response.audio_data)} bytes")
        print(f"Sample rate: {response.sample_rate} Hz")
        print(f"Duration: {response.duration_ms} ms")

asyncio.run(synthesize())
```

### HealthCheck

Check service health and get available voices.

**Request:**
```protobuf
message HealthRequest {}
```

**Response:**
```protobuf
message HealthResponse {
  bool healthy = 1;
  string version = 2;
  repeated string available_voices = 3;
}
```

**Example (Python):**
```python
import grpc
import asyncio
from june_grpc_api import tts as tts_shim

async def health_check():
    async with grpc.aio.insecure_channel("localhost:50053") as channel:
        client = tts_shim.TextToSpeechClient(channel)
        response = await client.health_check(tts_shim.HealthRequest())
        
        print(f"Healthy: {response.healthy}")
        print(f"Version: {response.version}")
        print(f"Available voices: {', '.join(response.available_voices)}")

asyncio.run(health_check())
```

## Message Types

### SynthesisRequest

Text-to-speech synthesis request.

**Fields:**
- `text`: Text to synthesize (required)
- `voice_id`: Voice identifier (e.g., "default", "male", "female")
- `language`: Language code (ISO 639-1, e.g., "en", "es", "fr")
- `config`: Synthesis configuration
- `stream`: Whether to stream audio chunks (for streaming endpoint)

### SynthesisConfig

Synthesis configuration for prosody control.

```protobuf
message SynthesisConfig {
  float speed = 1;      // 0.5 to 2.0
  float pitch = 2;      // -0.5 to 0.5 semitones
  float energy = 3;     // 0.0 to 1.0
  string prosody = 4;   // "neutral", "happy", "sad", "angry", etc.
  bool enable_ssml = 5; // Support SSML tags
}
```

**Parameters:**
- `speed`: Speech rate (0.5 = half speed, 2.0 = double speed, 1.0 = normal)
- `pitch`: Pitch adjustment in semitones (-0.5 to +0.5)
- `energy`: Energy/intensity level (0.0 = quiet, 1.0 = loud)
- `prosody`: Emotional prosody ("neutral", "happy", "sad", "angry", "excited", "calm")
- `enable_ssml`: Enable SSML (Speech Synthesis Markup Language) support

### AudioChunk

Audio data chunk for streaming output.

**Fields:**
- `audio_data`: Raw audio bytes
- `sample_rate`: Sample rate in Hz (typically 16000 or 22050)
- `channels`: Number of audio channels (1 = mono, 2 = stereo)
- `encoding`: Audio encoding format ("pcm16", "opus", "mp3")
- `is_final`: Whether this is the final chunk
- `timestamp_us`: Timestamp in microseconds

### AudioResponse

Complete audio response for one-shot synthesis.

**Fields:**
- `audio_data`: Complete audio bytes
- `sample_rate`: Sample rate in Hz
- `encoding`: Audio encoding format
- `duration_ms`: Audio duration in milliseconds

## Voice Options

### Available Voices

Query available voices using the `HealthCheck` endpoint:

```python
async def list_voices():
    async with grpc.aio.insecure_channel("localhost:50053") as channel:
        client = tts_shim.TextToSpeechClient(channel)
        response = await client.health_check(tts_shim.HealthRequest())
        return response.available_voices
```

Common voice IDs:
- `default`: Default voice
- `male`: Male voice
- `female`: Female voice
- Language-specific voices (e.g., `en-us-male`, `es-female`)

## Prosody Control

### Speed Control

```python
# Slow speech (0.5x speed)
config = tts_shim.SynthesisConfig(speed=0.5)

# Normal speech
config = tts_shim.SynthesisConfig(speed=1.0)

# Fast speech (2x speed)
config = tts_shim.SynthesisConfig(speed=2.0)
```

### Pitch Control

```python
# Lower pitch (-0.5 semitones)
config = tts_shim.SynthesisConfig(pitch=-0.5)

# Normal pitch
config = tts_shim.SynthesisConfig(pitch=0.0)

# Higher pitch (+0.5 semitones)
config = tts_shim.SynthesisConfig(pitch=0.5)
```

### Emotional Prosody

```python
# Happy
config = tts_shim.SynthesisConfig(prosody="happy")

# Sad
config = tts_shim.SynthesisConfig(prosody="sad")

# Angry
config = tts_shim.SynthesisConfig(prosody="angry")

# Excited
config = tts_shim.SynthesisConfig(prosody="excited")

# Calm
config = tts_shim.SynthesisConfig(prosody="calm")

# Neutral (default)
config = tts_shim.SynthesisConfig(prosody="neutral")
```

## Usage Examples

### Basic Synthesis

```python
import grpc
import asyncio
from june_grpc_api import tts as tts_shim

async def speak(text, output_file="output.wav"):
    async with grpc.aio.insecure_channel("localhost:50053") as channel:
        client = tts_shim.TextToSpeechClient(channel)
        
        config = tts_shim.SynthesisConfig()
        request = tts_shim.SynthesisRequest(
            text=text,
            voice_id="default",
            language="en",
            config=config
        )
        
        response = await client.synthesize(request)
        
        with open(output_file, "wb") as f:
            f.write(response.audio_data)
        
        print(f"Saved to {output_file}")

# Usage
asyncio.run(speak("Hello, world!"))
```

### Multi-language Synthesis

```python
async def speak_multilingual():
    async with grpc.aio.insecure_channel("localhost:50053") as channel:
        client = tts_shim.TextToSpeechClient(channel)
        
        texts = [
            ("Hello, world!", "en", "output_en.wav"),
            ("Hola, mundo!", "es", "output_es.wav"),
            ("Bonjour, le monde!", "fr", "output_fr.wav")
        ]
        
        for text, lang, filename in texts:
            request = tts_shim.SynthesisRequest(
                text=text,
                voice_id="default",
                language=lang,
                config=tts_shim.SynthesisConfig()
            )
            
            response = await client.synthesize(request)
            with open(filename, "wb") as f:
                f.write(response.audio_data)
            print(f"Generated {filename}")

asyncio.run(speak_multilingual())
```

### Streaming Synthesis

```python
async def stream_synthesis(text):
    async with grpc.aio.insecure_channel("localhost:50053") as channel:
        client = tts_shim.TextToSpeechClient(channel)
        
        config = tts_shim.SynthesisConfig()
        request = tts_shim.SynthesisRequest(
            text=text,
            voice_id="default",
            language="en",
            config=config,
            stream=True
        )
        
        audio_chunks = []
        async for chunk in client.synthesize_stream([request]):
            if chunk.audio_data:
                audio_chunks.append(chunk.audio_data)
                print(f"Received chunk: {len(chunk.audio_data)} bytes")
            if chunk.is_final:
                break
        
        # Combine chunks
        full_audio = b''.join(audio_chunks)
        with open("streamed_output.wav", "wb") as f:
            f.write(full_audio)
        print(f"Saved {len(full_audio)} bytes")

asyncio.run(stream_synthesis("This is a long text that will be streamed."))
```

### Custom Prosody

```python
async def speak_with_prosody():
    async with grpc.aio.insecure_channel("localhost:50053") as channel:
        client = tts_shim.TextToSpeechClient(channel)
        
        # Happy, fast, high-pitched voice
        config = tts_shim.SynthesisConfig(
            speed=1.2,
            pitch=0.3,
            energy=0.8,
            prosody="happy"
        )
        
        request = tts_shim.SynthesisRequest(
            text="I'm so excited to tell you this great news!",
            voice_id="default",
            language="en",
            config=config
        )
        
        response = await client.synthesize(request)
        with open("excited.wav", "wb") as f:
            f.write(response.audio_data)
```

## Audio Format

### Supported Encodings

- **pcm16**: 16-bit PCM (uncompressed, best quality)
- **opus**: Opus codec (compressed, good quality)
- **mp3**: MP3 format (compressed, widely compatible)

### Sample Rates

- **16000 Hz**: Standard for voice (recommended)
- **22050 Hz**: Higher quality
- **44100 Hz**: CD quality (may be overkill for TTS)

### Channels

- **Mono (1 channel)**: Standard for TTS
- **Stereo (2 channels)**: For spatial audio (if supported)

## Error Handling

gRPC errors follow standard gRPC status codes:

- `OK (0)`: Success
- `INVALID_ARGUMENT (3)`: Invalid text or parameters
- `RESOURCE_EXHAUSTED (8)`: Rate limit exceeded
- `INTERNAL (13)`: Internal server error
- `UNAVAILABLE (14)`: Service unavailable

**Example:**
```python
import grpc
from june_grpc_api import tts as tts_shim

async def synthesize_with_error_handling(text):
    try:
        async with grpc.aio.insecure_channel("localhost:50053") as channel:
            client = tts_shim.TextToSpeechClient(channel)
            request = tts_shim.SynthesisRequest(
                text=text,
                voice_id="default",
                language="en",
                config=tts_shim.SynthesisConfig()
            )
            response = await client.synthesize(request)
            return response.audio_data
    except grpc.aio.AioRpcError as e:
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            print(f"Invalid request: {e.details()}")
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
    async with pool.get_tts_channel() as channel:
        client = tts_shim.TextToSpeechClient(channel)
        # Use client...
```

## Rate Limiting

Rate limiting is typically handled at the Gateway service level. Direct gRPC connections may have different limits. Check service documentation for specific rate limits.

## Best Practices

1. **Use appropriate language code**: Specify the correct language for better pronunciation
2. **Choose voice carefully**: Different voices may work better for different content types
3. **Adjust speed for clarity**: Slower speed (0.8-0.9) improves comprehension
4. **Use streaming for long text**: Stream synthesis for better latency on long texts
5. **Cache common phrases**: Cache frequently used phrases to reduce load
6. **Handle errors gracefully**: TTS can fail for various reasons (invalid text, service issues)
