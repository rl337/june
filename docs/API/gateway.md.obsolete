# Gateway Service API

The Gateway Service is the main entry point for June Agent, providing REST endpoints, WebSocket support, authentication, rate limiting, and streaming capabilities.

## Base URL

```
http://localhost:8000
```

## Authentication

Most endpoints require authentication using JWT Bearer tokens. Include the token in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

### Authentication Endpoints

#### POST `/auth/login`

Authenticate a user and receive access and refresh tokens.

**Request Body:**
```json
{
  "username": "string (optional)",
  "password": "string (optional)",
  "user_id": "string (optional)"
}
```

**Response:**
```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Example (curl):**
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "user", "password": "pass"}'
```

**Example (Python):**
```python
import requests

response = requests.post(
    "http://localhost:8000/auth/login",
    json={"username": "user", "password": "pass"}
)
tokens = response.json()
```

#### POST `/auth/refresh`

Refresh an access token using a refresh token.

**Request Body:**
```json
{
  "refresh_token": "string"
}
```

**Response:**
```json
{
  "access_token": "string",
  "token_type": "bearer",
  "expires_in": 3600
}
```

#### POST `/auth/logout`

Logout and revoke a refresh token.

**Request Body:**
```json
{
  "refresh_token": "string"
}
```

#### POST `/auth/token`

Create a JWT token (backward compatibility endpoint).

**Query Parameters:**
- `user_id` (optional): User ID for token creation

**Response:**
```json
{
  "access_token": "string",
  "token_type": "bearer"
}
```

### Admin Authentication

#### POST `/admin/auth/login`

Admin login endpoint.

**Request Body:**
```json
{
  "username": "string",
  "password": "string"
}
```

**Response:**
```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "bearer",
  "expires_in": 3600
}
```

## Core API Endpoints

### Audio Transcription

#### POST `/api/v1/audio/transcribe`

Transcribe audio and optionally perform full round-trip (STT → LLM → TTS).

**Request:**
- `audio` (file): Audio file to transcribe (multipart/form-data)
- `full_round_trip` (query, optional): If "true", perform full round-trip (default: "false")
- `language` (query, optional): Language code (ISO 639-1, e.g., "en", "es", "fr")

**Response (transcription only):**
```json
{
  "transcript": "string",
  "detected_language": "en"
}
```

**Response (full round-trip):**
```json
{
  "transcript": "string",
  "detected_language": "en",
  "llm_response": "string",
  "audio_b64": "string",
  "sample_rate": 16000
}
```

**Example (curl):**
```bash
curl -X POST http://localhost:8000/api/v1/audio/transcribe \
  -H "Authorization: Bearer <token>" \
  -F "audio=@audio.wav" \
  -F "full_round_trip=true" \
  -F "language=en"
```

**Example (Python):**
```python
import requests

with open("audio.wav", "rb") as f:
    response = requests.post(
        "http://localhost:8000/api/v1/audio/transcribe",
        headers={"Authorization": f"Bearer {token}"},
        files={"audio": f},
        params={"full_round_trip": "true", "language": "en"}
    )
result = response.json()
```

### LLM Generation

#### POST `/api/v1/llm/generate`

Generate text using the LLM.

**Request Body:**
```json
{
  "prompt": "string (1-100000 characters)"
}
```

**Response:**
```json
{
  "text": "string"
}
```

**Example (curl):**
```bash
curl -X POST http://localhost:8000/api/v1/llm/generate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello, how are you?"}'
```

**Example (Python):**
```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/llm/generate",
    headers={"Authorization": f"Bearer {token}"},
    json={"prompt": "Hello, how are you?"}
)
result = response.json()
```

### Text-to-Speech

#### POST `/api/v1/tts/speak`

Synthesize text to speech.

**Request Body:**
```json
{
  "text": "string (1-50000 characters)",
  "language": "en (ISO 639-1 code)",
  "voice_id": "default"
}
```

**Response:**
```json
{
  "audio_b64": "string (base64-encoded audio)",
  "sample_rate": 16000
}
```

**Example (curl):**
```bash
curl -X POST http://localhost:8000/api/v1/tts/speak \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "language": "en", "voice_id": "default"}'
```

**Example (Python):**
```python
import requests
import base64

response = requests.post(
    "http://localhost:8000/api/v1/tts/speak",
    headers={"Authorization": f"Bearer {token}"},
    json={"text": "Hello world", "language": "en", "voice_id": "default"}
)
result = response.json()
audio_data = base64.b64decode(result["audio_b64"])
```

### Chat Endpoint

#### POST `/chat`

REST API chat endpoint for text and audio messages.

**Request Body:**
```json
{
  "type": "text | audio",
  "content": "string",
  "conversation_id": "string (optional)"
}
```

**Response:**
```json
{
  "type": "text | audio",
  "content": "string",
  "conversation_id": "string"
}
```

**Example (curl):**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"type": "text", "content": "Hello!"}'
```

## WebSocket API

### WebSocket `/ws/{user_id}`

Real-time WebSocket endpoint for bidirectional communication.

**Connection:**
```
ws://localhost:8000/ws/{user_id}
```

**Message Format:**
```json
{
  "type": "text | audio",
  "content": "string",
  "conversation_id": "string (optional)"
}
```

**Response Format:**
```json
{
  "type": "text | audio",
  "content": "string",
  "conversation_id": "string",
  "timestamp": "ISO 8601 timestamp"
}
```

**Example (Python):**
```python
import asyncio
import websockets
import json

async def chat():
    uri = "ws://localhost:8000/ws/user123"
    async with websockets.connect(uri) as websocket:
        # Send message
        message = {
            "type": "text",
            "content": "Hello!"
        }
        await websocket.send(json.dumps(message))
        
        # Receive response
        response = await websocket.recv()
        result = json.loads(response)
        print(result)

asyncio.run(chat())
```

## Analytics Endpoints

### GET `/conversations/analytics/metrics`

Get analytics metrics for a specific conversation.

**Query Parameters:**
- `user_id` (required): User ID
- `chat_id` (required): Chat ID (session_id)

**Response:**
```json
{
  "message_count": 10,
  "user_message_count": 5,
  "assistant_message_count": 5,
  "average_response_time": 1.5,
  "engagement_score": 0.8,
  "first_message_at": "2025-01-01T00:00:00Z",
  "last_message_at": "2025-01-01T01:00:00Z"
}
```

### GET `/conversations/analytics/dashboard`

Get dashboard analytics.

**Query Parameters:**
- `start_date` (optional): Start date filter (ISO format)
- `end_date` (optional): End date filter (ISO format)

**Response:**
```json
{
  "total_conversations": 100,
  "total_messages": 1000,
  "active_users": 50,
  "average_response_time": 1.5
}
```

### GET `/conversations/analytics/report`

Get analytics report.

**Query Parameters:**
- `start_date` (optional): Start date filter (ISO format)
- `end_date` (optional): End date filter (ISO format)
- `format` (optional): Report format ("json" or "csv")

## Admin Endpoints

### User Management

#### GET `/admin/users`

List all users (admin only).

**Query Parameters:**
- `limit` (optional): Maximum number of results (default: 100)
- `offset` (optional): Offset for pagination (default: 0)

**Response:**
```json
[
  {
    "user_id": "string",
    "username": "string",
    "email": "string",
    "role": "user | admin | moderator",
    "status": "active | blocked | inactive",
    "created_at": "ISO 8601 timestamp"
  }
]
```

#### GET `/admin/users/stats`

Get user statistics.

**Response:**
```json
{
  "total_users": 100,
  "active_users": 80,
  "blocked_users": 5,
  "inactive_users": 15
}
```

#### GET `/admin/users/{user_id}`

Get user details.

**Response:**
```json
{
  "user_id": "string",
  "username": "string",
  "email": "string",
  "role": "string",
  "status": "string",
  "created_at": "ISO 8601 timestamp"
}
```

#### POST `/admin/users`

Create a new user.

**Request Body:**
```json
{
  "username": "string",
  "email": "string (optional)",
  "password": "string (optional, min 8 characters)",
  "role": "user | admin | moderator",
  "status": "active | blocked | inactive"
}
```

#### PUT `/admin/users/{user_id}`

Update a user.

**Request Body:**
```json
{
  "username": "string (optional)",
  "email": "string (optional)",
  "password": "string (optional)",
  "role": "string (optional)",
  "status": "string (optional)"
}
```

#### DELETE `/admin/users/{user_id}`

Delete a user.

### Conversation Management

#### GET `/admin/conversations`

List conversations.

**Query Parameters:**
- `user_id` (optional): Filter by user ID
- `limit` (optional): Maximum number of results
- `offset` (optional): Offset for pagination

#### GET `/admin/conversations/{conversation_id}`

Get conversation details.

#### GET `/admin/conversations/search`

Search conversations.

**Query Parameters:**
- `query` (required): Search query
- `limit` (optional): Maximum number of results

#### DELETE `/admin/conversations/{conversation_id}`

Delete a conversation.

### Bot Management

#### GET `/admin/bot/config`

Get bot configuration.

#### PUT `/admin/bot/config`

Update bot configuration.

**Request Body:**
```json
{
  "config": {
    "max_file_size": 10485760,
    "supported_languages": ["en", "es", "fr"]
  }
}
```

#### GET `/admin/bot/status`

Get bot status.

#### GET `/admin/bot/stats`

Get bot statistics.

#### GET `/admin/bot/commands`

List bot commands.

#### POST `/admin/bot/commands`

Create a bot command.

#### PUT `/admin/bot/commands/{command_id}`

Update a bot command.

#### DELETE `/admin/bot/commands/{command_id}`

Delete a bot command.

### System Monitoring

#### GET `/admin/monitoring/services`

Get health status of all services.

**Response:**
```json
{
  "gateway": {"healthy": true, "uptime": 3600},
  "stt": {"healthy": true, "uptime": 3600},
  "tts": {"healthy": true, "uptime": 3600},
  "llm": {"healthy": true, "uptime": 3600}
}
```

#### GET `/admin/monitoring/metrics`

Get system metrics.

#### GET `/admin/monitoring/health`

Get overall system health.

### System Configuration

#### GET `/admin/config`

Get system configuration.

#### PUT `/admin/config`

Update system configuration.

**Request Body:**
```json
{
  "config": {
    "key": "value"
  }
}
```

#### GET `/admin/config/history`

Get configuration change history.

## Health and Status

### GET `/health`

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "gateway",
  "version": "0.2.0",
  "uptime": 3600,
  "timestamp": "ISO 8601 timestamp"
}
```

### GET `/status`

Service status endpoint.

**Response:**
```json
{
  "status": "operational",
  "services": {
    "stt": "online",
    "tts": "online",
    "llm": "online"
  },
  "uptime": 3600,
  "timestamp": "ISO 8601 timestamp"
}
```

### GET `/metrics`

Prometheus metrics endpoint.

**Response:** Prometheus metrics format

## Rate Limiting

Rate limiting is applied per endpoint:

- `/api/v1/llm/generate`: 10 requests/minute, 100 requests/hour
- `/api/v1/tts/speak`: 20 requests/minute, 200 requests/hour
- `/api/v1/audio/transcribe`: 20 requests/minute, 200 requests/hour
- `/chat`: 30 requests/minute, 500 requests/hour
- Default: 60 requests/minute, 1000 requests/hour

**Rate Limit Headers:**
- `X-RateLimit-Limit`: Maximum requests allowed
- `X-RateLimit-Remaining`: Remaining requests
- `X-RateLimit-Reset`: Time when limit resets (Unix timestamp)

**Rate Limit Response (429):**
```json
{
  "detail": "Rate limit exceeded",
  "retry_after": 60
}
```

## Error Codes

- `400 Bad Request`: Invalid request parameters or body
- `401 Unauthorized`: Missing or invalid authentication token
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: Resource not found
- `409 Conflict`: Resource conflict (e.g., task already locked)
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server error
- `503 Service Unavailable`: Service temporarily unavailable

## Caching

The Gateway Service uses caching for:
- LLM responses (cached by prompt hash)
- TTS synthesis (cached by text, language, and voice_id)
- STT transcriptions (cached by audio data hash)

Cache keys are automatically generated and responses are served from cache when available.

## Security Headers

The Gateway Service includes security headers:
- `Content-Security-Policy`
- `Strict-Transport-Security`
- `X-Content-Type-Options`
- `X-Frame-Options`
- `X-XSS-Protection`

## CORS

CORS is configured via the `CORS_ORIGINS` environment variable. Default allows all origins (`*`) for development.
