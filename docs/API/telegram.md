# Telegram Bot API

The Telegram Bot service provides a voice assistant bot that processes voice messages and responds with voice messages.

## Bot Overview

The June Telegram Bot is a voice assistant that:
1. Receives voice messages from users
2. Transcribes them using STT (Speech-to-Text)
3. Processes them with LLM (Large Language Model)
4. Generates voice responses using TTS (Text-to-Speech)
5. Sends voice responses back to users

## Commands

### User Commands

#### `/start`

Start interacting with the bot. Displays welcome message explaining bot capabilities.

**Usage:**
```
/start
```

**Response:**
```
👋 Hello! I'm June, your voice assistant.

Send me a voice message and I'll:
1️⃣ Transcribe it
2️⃣ Process it with AI
3️⃣ Send back a voice response

Use /help for more information.
```

#### `/help`

Display help information with available commands and usage instructions.

**Usage:**
```
/help
```

**Response:**
```
📖 June Voice Assistant Help

Commands:
/start - Start interacting with June
/help - Show this help message
/status - Check service status
/language - Set language for voice messages

Usage:
Just send me a voice message (🎤) and I'll respond with a voice message!

Limits:
📦 Maximum file size: 20.0 MB
⏱️ Maximum duration: ~1 minute
```

#### `/status`

Check service health status. Displays status of STT, TTS, and LLM services.

**Usage:**
```
/status
```

**Response:**
```
🔍 Service Status

✅ Bot: Online
✅ STT: Online (stt:8080)
✅ TTS: Online (tts:8080)
✅ LLM: Online (tensorrt-llm:8000)  # TensorRT-LLM (default) or inference-api:50051 (legacy)
```

#### `/language`

Set or view language preference for voice messages.

**Usage:**
```
/language          # View current language and available languages
/language <code>   # Set language (e.g., /language es for Spanish)
```

**Response (view):**
```
🌐 Language Settings

Current language: English (en)

Available languages:
  • en: English (current)
  • es: Spanish
  • fr: French
  • de: German
  ...

To change language, use:
/language <code>

Example: /language es for Spanish
```

**Response (set):**
```
✅ Language set to Spanish (es)

Your voice messages will now be processed in Spanish.
Language detection is also enabled, so the system will automatically
detect the language if it differs from your preference.
```

**Supported Language Codes:**
- `en`: English
- `es`: Spanish
- `fr`: French
- `de`: German
- `it`: Italian
- `pt`: Portuguese
- `ru`: Russian
- `ja`: Japanese
- `zh`: Chinese
- `ko`: Korean
- And more (check `/language` command for full list)

### Admin Commands

Admin commands require admin privileges. Users must be configured as admins in the system.

#### `/admin_help`

Show admin command help.

**Usage:**
```
/admin_help
```

**Response:**
```
🔐 Admin Commands

User Management:
/admin_block <user_id> [reason] - Block a user
/admin_unblock <user_id> - Unblock a user
/admin_list_blocked - List all blocked users

Conversation Management:
/admin_clear_conversation <conversation_id> - Clear a conversation
/admin_clear_user <user_id> - Clear all conversations for a user

System:
/admin_status - Check system status
/admin_help - Show this help message

Note: All admin actions are logged for audit purposes.
```

#### `/admin_block`

Block a user from using the bot.

**Usage:**
```
/admin_block <user_id> [reason]
```

**Example:**
```
/admin_block 123456789 Spam messages
```

**Response:**
```
✅ User Blocked

User ID: 123456789
Reason: Spam messages
Blocked by: 987654321
```

#### `/admin_unblock`

Unblock a previously blocked user.

**Usage:**
```
/admin_unblock <user_id>
```

**Example:**
```
/admin_unblock 123456789
```

**Response:**
```
✅ User Unblocked

User ID: 123456789
Unblocked by: 987654321
```

#### `/admin_list_blocked`

List all blocked users.

**Usage:**
```
/admin_list_blocked
```

**Response:**
```
🔒 Blocked Users:

• User ID: 123456789
  Blocked by: 987654321
  Reason: Spam messages
  Date: 2025-01-01 12:00:00

• User ID: 111222333
  Blocked by: 987654321
  Reason: Inappropriate content
  Date: 2025-01-02 10:00:00
```

#### `/admin_clear_conversation`

Clear a specific conversation.

**Usage:**
```
/admin_clear_conversation <conversation_id>
```

**Example:**
```
/admin_clear_conversation abc123-def456-...
```

**Response:**
```
✅ Conversation Cleared

Conversation ID: abc123-def456-...
Cleared by: 987654321
```

#### `/admin_clear_user`

Clear all conversations for a user.

**Usage:**
```
/admin_clear_user <user_id>
```

**Example:**
```
/admin_clear_user 123456789
```

**Response:**
```
✅ User Conversations Cleared

User ID: 123456789
Conversations cleared: 5
Cleared by: 987654321
```

#### `/admin_status`

Check system status including services and database statistics.

**Usage:**
```
/admin_status
```

**Response:**
```
🔍 System Status

📊 Services:
  STT: ✅ Online
  TTS: ✅ Online
  LLM: ✅ Online
  Database: ✅ Connected

📈 Statistics:
  Conversations: 150
  Messages: 1250
  Blocked users: 2
```

## Message Handling

### Voice Messages

The bot automatically processes voice messages:

1. **Receive**: Bot receives voice message from user
2. **Transcribe**: Voice is transcribed using STT service
3. **Process**: Transcript is processed by LLM
4. **Synthesize**: LLM response is converted to speech using TTS
5. **Respond**: Bot sends voice response back to user

**User Action:**
- Send a voice message (🎤) to the bot

**Bot Response:**
- Sends a voice message with the AI's response

### Text Messages

Text messages are also supported (processed as if transcribed):

1. **Receive**: Bot receives text message
2. **Process**: Text is processed by LLM
3. **Synthesize**: LLM response is converted to speech using TTS
4. **Respond**: Bot sends voice response back to user

**User Action:**
- Send a text message to the bot

**Bot Response:**
- Sends a voice message with the AI's response

## Webhook Setup

The Telegram Bot uses webhooks for receiving updates. Configure the webhook URL:

**Webhook URL Format:**
```
https://your-domain.com/telegram/webhook
```

**Set Webhook (using Telegram Bot API):**
```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-domain.com/telegram/webhook"}'
```

**Get Webhook Info:**
```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
```

**Delete Webhook:**
```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/deleteWebhook"
```

## Configuration

### Environment Variables

- `TELEGRAM_BOT_TOKEN`: Telegram Bot API token (required)
- `TELEGRAM_WEBHOOK_URL`: Webhook URL for receiving updates
- `TELEGRAM_WEBHOOK_SECRET`: Secret token for webhook verification
- `STT_SERVICE_URL`: STT service address (default: `stt:8080`)
- `TTS_SERVICE_URL`: TTS service address (default: `tts:8080`)
- `LLM_SERVICE_URL`: LLM service address (default: `tensorrt-llm:8000` for TensorRT-LLM, legacy: `inference-api:50051`)
- `MAX_FILE_SIZE`: Maximum voice file size in bytes (default: 20MB)
- `SUPPORTED_LANGUAGES`: Comma-separated list of supported language codes

### Bot Configuration

Bot configuration can be managed via the Gateway Admin API:

**Get Bot Config:**
```bash
curl -X GET "http://localhost:8000/admin/bot/config" \
  -H "Authorization: Bearer <admin_token>"
```

**Update Bot Config:**
```bash
curl -X PUT "http://localhost:8000/admin/bot/config" \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "max_file_size": 20971520,
      "supported_languages": ["en", "es", "fr"]
    }
  }'
```

## Limits

- **Maximum file size**: 20 MB (configurable)
- **Maximum duration**: ~1 minute
- **Supported formats**: OGG Opus (Telegram's default), MP3, WAV
- **Rate limiting**: Applied per user to prevent abuse

## Error Handling

### Common Errors

**File too large:**
```
❌ File size exceeds maximum allowed size (20 MB)
```

**Unsupported format:**
```
❌ Unsupported audio format. Please send a voice message.
```

**Service unavailable:**
```
❌ Service temporarily unavailable. Please try again later.
```

**User blocked:**
```
❌ Your account has been blocked. Contact support for assistance.
```

## Best Practices

1. **Use voice messages**: The bot is optimized for voice interaction
2. **Set language preference**: Use `/language` to set your preferred language
3. **Check status**: Use `/status` if experiencing issues
4. **Respect limits**: Keep voice messages under 1 minute for best results
5. **Clear audio**: Speak clearly for better transcription accuracy

## Integration Examples

### Python (python-telegram-bot)

```python
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

async def start(update: Update, context):
    await update.message.reply_text("Hello! Send me a voice message.")

async def handle_voice(update: Update, context):
    voice = update.message.voice
    # Process voice message...
    await update.message.reply_voice(voice=voice_file)

app = Application.builder().token("YOUR_BOT_TOKEN").build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.run_polling()
```

### Webhook Handler

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/telegram/webhook', methods=['POST'])
def webhook():
    update = request.json
    # Process update...
    return jsonify({"ok": True})
```

## Security

- **Admin commands**: Require admin privileges
- **User blocking**: Prevents abuse
- **Rate limiting**: Applied per user
- **Audit logging**: All admin actions are logged
- **Input validation**: All inputs are validated and sanitized

## Monitoring

Monitor bot health and performance:

- **Service status**: Use `/admin_status` command
- **Metrics**: Available via Gateway Admin API (`/admin/monitoring/metrics`)
- **Logs**: Check service logs for errors and issues

## Support

For issues or questions:
1. Check `/status` for service health
2. Review error messages for specific issues
3. Contact support with conversation ID if needed
