# Discord Bot API

The Discord Bot service provides a chat assistant bot that processes text messages and responds with generated text.

## Bot Overview

The June Discord Bot is a chat assistant that:
1. Receives text messages from users
2. Processes them with LLM (Large Language Model)
3. Sends text responses back to users

## Commands

### User Commands

#### `!ping`

Test bot responsiveness.

**Usage:**
```
!ping
```

**Response:**
```
Pong!
```

#### `!help`

Display help information with available commands. This is a built-in Discord.py command.

**Usage:**
```
!help
```

**Response:**
```
Help
No Category:
  ping
    Respond to ping command.
```

### Message Processing

Regular messages (not commands) are automatically processed through the agent system:

1. **User sends a message** (without `!` prefix)
2. **Bot responds with status updates:**
   - ✅ "Received request"
   - 🔄 "Processing..."
   - ⚙️ "Generating..." (with dots)
3. **Bot sends final response** with the generated text

**Example Flow:**
```
User: Hello, how are you?
Bot: ✅ Received request
Bot: 🔄 Processing...
Bot: ⚙️ Generating...
Bot: Hello! I'm doing well, thank you for asking. How can I help you today?
```

## Bot Setup

### Prerequisites

1. **Create a Discord Bot:**
   - Go to https://discord.com/developers/applications
   - Create a new application
   - Navigate to "Bot" section
   - Create a bot and copy the token
   - Enable required intents:
     - Message Content Intent (required to read message content)
     - Server Members Intent (required for user information)

2. **Invite Bot to Server:**
   - Go to "OAuth2" → "URL Generator"
   - Select scopes: `bot`
   - Select bot permissions:
     - Send Messages
     - Read Message History
     - Use External Emojis
   - Copy the generated URL and open it in a browser
   - Select your server and authorize

### Configuration

#### Environment Variables

- `DISCORD_BOT_TOKEN`: Discord Bot API token (required)
- `DISCORD_AUTHORIZED_USERS`: Comma-separated list of authorized user IDs (optional, for access control)
- `DISCORD_SERVICE_PORT`: HTTP port for health checks and metrics (default: `8081`)
- `STT_SERVICE_URL`: STT service address (default: `stt:8080`)
- `TTS_SERVICE_URL`: TTS service address (default: `tts:8080`)
- `LLM_URL`: LLM service address (default: `tensorrt-llm:8000` for TensorRT-LLM, legacy: `inference-api:50051`)

#### Bot Configuration

Bot configuration is managed via environment variables. Update the service's environment variables in `docker-compose.yml` or your deployment configuration:

**Configuration via Environment Variables:**
```yaml
services:
  discord:
    environment:
      - DISCORD_BOT_TOKEN=your_bot_token
      - DISCORD_AUTHORIZED_USERS=123456789,987654321  # Optional: restrict access
      - DISCORD_SERVICE_PORT=8081
      - LLM_URL=tensorrt-llm:8000  # Default: TensorRT-LLM
      # ... other configuration variables
```

**Note:** Gateway service was removed for MVP. Bot configuration is now done via environment variables at service startup. To change configuration, update environment variables and restart the service.

## Message Format

Discord supports Markdown formatting natively. The bot uses Markdown format for responses:

- **Bold text**: `**text**`
- *Italic text*: `*text*`
- `Code blocks`: `` `code` ``
- Code blocks with syntax highlighting: ` ```python\ncode\n``` `

## Limits

- **Maximum message length**: 2000 characters (Discord limit)
- **Rate limiting**: Applied per user to prevent abuse
- **Message history**: All messages are tracked for debugging and analysis

## Health and Monitoring

### Health Check

Check bot health status:

```bash
curl http://localhost:8081/health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "discord",
  "version": "0.2.0",
  "uptime": 3600,
  "timestamp": "2025-01-01T12:00:00Z"
}
```

### Metrics

Prometheus metrics are available at:

```bash
curl http://localhost:8081/metrics
```

**Key Metrics:**
- `http_requests_total` - Total HTTP requests
- `http_request_duration_seconds` - Request duration histogram
- `grpc_requests_total` - Total gRPC requests (STT, TTS, LLM)
- `grpc_request_duration_seconds` - gRPC request duration histogram
- `voice_messages_processed_total` - Total messages processed
- `errors_total` - Total errors
- `service_health` - Service health status (1 = healthy, 0 = unhealthy)

## Monitoring

Monitor bot health and performance:

- **Service status**: Check health endpoint at `http://discord:8081/health`
- **Health endpoint**: `http://discord:8081/health` (HTTP health check)
- **Metrics**: Available at `http://discord:8081/metrics` (Prometheus format)
- **Logs**: Check service logs for errors and issues: `docker compose logs discord`

## Error Handling

### Common Errors

**Service unavailable:**
```
❌ Service temporarily unavailable. Please try again later.
```

**User not authorized:**
```
❌ You are not authorized to use this bot.
```

**Message too long:**
```
❌ Message exceeds maximum length (2000 characters).
```

## Best Practices

1. **Use clear, concise messages** - The bot processes text messages through the LLM
2. **Wait for responses** - The bot provides status updates during processing
3. **Check bot permissions** - Ensure the bot has required permissions in your server
4. **Monitor health** - Use health check endpoint to verify bot status
5. **Review logs** - Check service logs if the bot is not responding

## Integration with Agent System

The Discord bot uses the same agent system as the Telegram bot:

- **Agent scripts**: Uses `telegram_response_agent.sh` (shared with Telegram)
- **Message processing**: Same agentic flow (think → plan → execute → reflect)
- **Message history**: All messages are tracked for debugging
- **Formatting**: Uses Markdown format (Discord native support)

## See Also

- [Telegram Bot API](telegram.md) - Similar bot for Telegram platform
- [Inference API](inference.md) - LLM gRPC service documentation
- [Main README](../../README.md) - Project overview and setup
