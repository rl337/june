"""Admin command handlers for Telegram bot."""
import os
import logging
from telegram import Update
from telegram.ext import ContextTypes
from typing import Optional
import httpx


from essence.services.telegram.admin_auth import require_admin, is_admin
from essence.services.telegram.admin_db import (
    block_user,
    unblock_user,
    get_blocked_users,
    clear_conversation,
    clear_user_conversations,
    log_audit_action,
    is_user_blocked,
)
from essence.chat.message_history import get_message_history

logger = logging.getLogger(__name__)


def get_user_ip(update: Update) -> Optional[str]:
    """Extract IP address from update if available."""
    # Telegram Bot API doesn't provide IP directly, but we can log None
    # In production, you might get this from webhook headers
    return None


async def block_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin_block command - Block a user."""
    user_id = str(update.effective_user.id)

    try:
        # Check admin permission
        require_admin(user_id)
    except PermissionError:
        await update.message.reply_text(
            "❌ **Access Denied**\n\n" "You are not authorized to use admin commands."
        )
        return

    # Get target user ID from command arguments
    args = context.args if context.args else []
    if not args:
        await update.message.reply_text(
            "❌ **Usage:** `/admin_block <user_id>`\n\n"
            "Example: `/admin_block 123456789`"
        )
        return

    target_user_id = args[0]
    reason = " ".join(args[1:]) if len(args) > 1 else None

    # Block the user
    if block_user(target_user_id, user_id, reason):
        # Log audit action
        log_audit_action(
            action="user_blocked",
            actor_user_id=user_id,
            target_user_id=target_user_id,
            details={"reason": reason},
            ip_address=get_user_ip(update),
        )

        await update.message.reply_text(
            f"✅ **User Blocked**\n\n"
            f"User ID: `{target_user_id}`\n"
            f"Reason: {reason or 'No reason provided'}\n"
            f"Blocked by: `{user_id}`"
        )
    else:
        await update.message.reply_text(f"❌ Failed to block user `{target_user_id}`")


async def unblock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin_unblock command - Unblock a user."""
    user_id = str(update.effective_user.id)

    try:
        # Check admin permission
        require_admin(user_id)
    except PermissionError:
        await update.message.reply_text(
            "❌ **Access Denied**\n\n" "You are not authorized to use admin commands."
        )
        return

    # Get target user ID from command arguments
    args = context.args if context.args else []
    if not args:
        await update.message.reply_text(
            "❌ **Usage:** `/admin_unblock <user_id>`\n\n"
            "Example: `/admin_unblock 123456789`"
        )
        return

    target_user_id = args[0]

    # Unblock the user
    if unblock_user(target_user_id):
        # Log audit action
        log_audit_action(
            action="user_unblocked",
            actor_user_id=user_id,
            target_user_id=target_user_id,
            ip_address=get_user_ip(update),
        )

        await update.message.reply_text(
            f"✅ **User Unblocked**\n\n"
            f"User ID: `{target_user_id}`\n"
            f"Unblocked by: `{user_id}`"
        )
    else:
        await update.message.reply_text(
            f"❌ User `{target_user_id}` is not blocked or failed to unblock"
        )


async def list_blocked_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin_list_blocked command - List all blocked users."""
    user_id = str(update.effective_user.id)

    try:
        # Check admin permission
        require_admin(user_id)
    except PermissionError:
        await update.message.reply_text(
            "❌ **Access Denied**\n\n" "You are not authorized to use admin commands."
        )
        return

    # Get blocked users
    blocked = get_blocked_users()

    if not blocked:
        await update.message.reply_text(
            "✅ **No Blocked Users**\n\n" "There are currently no blocked users."
        )
        return

    # Format blocked users list
    lines = ["🔒 **Blocked Users:**\n"]
    for user in blocked[:20]:  # Limit to 20 for message length
        reason = user.get("reason", "No reason provided")
        blocked_by = user.get("blocked_by", "Unknown")
        created_at = user.get("created_at", "Unknown")
        lines.append(
            f"• User ID: `{user['user_id']}`\n"
            f"  Blocked by: `{blocked_by}`\n"
            f"  Reason: {reason}\n"
            f"  Date: {created_at}\n"
        )

    if len(blocked) > 20:
        lines.append(f"\n... and {len(blocked) - 20} more")

    await update.message.reply_text("\n".join(lines))


async def clear_conversation_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handle /admin_clear_conversation command - Clear a conversation."""
    user_id = str(update.effective_user.id)

    try:
        # Check admin permission
        require_admin(user_id)
    except PermissionError:
        await update.message.reply_text(
            "❌ **Access Denied**\n\n" "You are not authorized to use admin commands."
        )
        return

    # Get conversation ID from command arguments
    args = context.args if context.args else []
    if not args:
        await update.message.reply_text(
            "❌ **Usage:** `/admin_clear_conversation <conversation_id>`\n\n"
            "Example: `/admin_clear_conversation abc123-def456-...`"
        )
        return

    conversation_id = args[0]

    # Clear the conversation
    if clear_conversation(conversation_id):
        # Log audit action
        log_audit_action(
            action="conversation_cleared",
            actor_user_id=user_id,
            target_conversation_id=conversation_id,
            ip_address=get_user_ip(update),
        )

        await update.message.reply_text(
            f"✅ **Conversation Cleared**\n\n"
            f"Conversation ID: `{conversation_id}`\n"
            f"Cleared by: `{user_id}`"
        )
    else:
        await update.message.reply_text(
            f"❌ Failed to clear conversation `{conversation_id}`"
        )


async def clear_user_conversations_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handle /admin_clear_user command - Clear all conversations for a user."""
    user_id = str(update.effective_user.id)

    try:
        # Check admin permission
        require_admin(user_id)
    except PermissionError:
        await update.message.reply_text(
            "❌ **Access Denied**\n\n" "You are not authorized to use admin commands."
        )
        return

    # Get target user ID from command arguments
    args = context.args if context.args else []
    if not args:
        await update.message.reply_text(
            "❌ **Usage:** `/admin_clear_user <user_id>`\n\n"
            "Example: `/admin_clear_user 123456789`"
        )
        return

    target_user_id = args[0]

    # Clear all conversations for the user
    count = clear_user_conversations(target_user_id)

    if count > 0:
        # Log audit action
        log_audit_action(
            action="user_conversations_cleared",
            actor_user_id=user_id,
            target_user_id=target_user_id,
            details={"conversations_cleared": count},
            ip_address=get_user_ip(update),
        )

        await update.message.reply_text(
            f"✅ **User Conversations Cleared**\n\n"
            f"User ID: `{target_user_id}`\n"
            f"Conversations cleared: {count}\n"
            f"Cleared by: `{user_id}`"
        )
    else:
        await update.message.reply_text(
            f"ℹ️ No conversations found for user `{target_user_id}`"
        )


async def system_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin_status command - Check system status."""
    user_id = str(update.effective_user.id)

    try:
        # Check admin permission
        require_admin(user_id)
    except PermissionError:
        await update.message.reply_text(
            "❌ **Access Denied**\n\n" "You are not authorized to use admin commands."
        )
        return

    # Check service statuses
    status_lines = ["🔍 **System Status**\n"]

    # Check STT service
    stt_address = os.getenv("STT_SERVICE_URL", "http://stt:8080")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{stt_address}/health")
            stt_status = "✅ Online" if response.status_code == 200 else "❌ Offline"
    except Exception:
        stt_status = "❌ Offline"

    # Check TTS service (if available)
    tts_address = os.getenv("TTS_SERVICE_URL", "http://tts:8080")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{tts_address}/health")
            tts_status = "✅ Online" if response.status_code == 200 else "❌ Offline"
    except Exception:
        tts_status = "❌ Offline"

    # Check LLM service (if available)
    llm_address = os.getenv("LLM_SERVICE_URL", "http://orchestrator:8080")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{llm_address}/health")
            llm_status = "✅ Online" if response.status_code == 200 else "❌ Offline"
    except Exception:
        llm_status = "❌ Offline"

    # Get database stats
    try:
        from essence.services.telegram.admin_db import get_db_connection

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM conversations")
            conversation_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM messages")
            message_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM blocked_users")
            blocked_count = cursor.fetchone()[0]
            db_status = "✅ Connected"
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error checking database: {e}", exc_info=True)
        db_status = "❌ Error"
        conversation_count = 0
        message_count = 0
        blocked_count = 0

    status_lines.extend(
        [
            f"📊 **Services:**",
            f"  STT: {stt_status}",
            f"  TTS: {tts_status}",
            f"  LLM: {llm_status}",
            f"  Database: {db_status}",
            f"",
            f"📈 **Statistics:**",
            f"  Conversations: {conversation_count}",
            f"  Messages: {message_count}",
            f"  Blocked users: {blocked_count}",
        ]
    )

    # Log audit action
    log_audit_action(
        action="system_status_checked",
        actor_user_id=user_id,
        details={
            "stt_status": stt_status,
            "tts_status": tts_status,
            "llm_status": llm_status,
            "db_status": db_status,
            "conversation_count": conversation_count,
            "message_count": message_count,
            "blocked_count": blocked_count,
        },
        ip_address=get_user_ip(update),
    )

    await update.message.reply_text("\n".join(status_lines))


async def admin_message_history_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handle /admin_message_history command - View message history for debugging."""
    user_id = str(update.effective_user.id)

    try:
        # Check admin permission
        require_admin(user_id)
    except PermissionError:
        await update.message.reply_text(
            "❌ **Access Denied**\n\n" "You are not authorized to use admin commands."
        )
        return

    # Parse command arguments
    args = context.args if context.args else []

    # Parse filters
    filters_dict = {}
    limit = 10  # Default limit

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--user-id" and i + 1 < len(args):
            filters_dict["user_id"] = args[i + 1]
            i += 2
        elif arg == "--chat-id" and i + 1 < len(args):
            filters_dict["chat_id"] = args[i + 1]
            i += 2
        elif arg == "--platform" and i + 1 < len(args):
            platform = args[i + 1].lower()
            if platform in ["telegram", "discord"]:
                filters_dict["platform"] = platform
            i += 2
        elif arg == "--type" and i + 1 < len(args):
            msg_type = args[i + 1].lower()
            if msg_type in ["text", "voice", "error", "status"]:
                filters_dict["message_type"] = msg_type
            i += 2
        elif arg == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
                limit = max(1, min(limit, 50))  # Clamp between 1 and 50
            except ValueError:
                pass
            i += 2
        elif arg == "--stats":
            # Show statistics instead of messages
            history = get_message_history()
            stats = history.get_stats()

            stats_text = (
                "📊 **Message History Statistics**\n\n"
                f"**Total Messages:** {stats['total_messages']}\n"
                f"**Max Entries:** {stats['max_entries']}\n"
                f"**Unique Users:** {stats['unique_users']}\n"
                f"**Unique Chats:** {stats['unique_chats']}\n\n"
                "**By Platform:**\n"
            )

            for platform, count in stats["by_platform"].items():
                stats_text += f"  • {platform.capitalize()}: {count}\n"

            stats_text += "\n**By Type:**\n"
            for msg_type, count in stats["by_type"].items():
                if count > 0:
                    stats_text += f"  • {msg_type.capitalize()}: {count}\n"

            await update.message.reply_text(stats_text, parse_mode="HTML")
            return
        else:
            i += 1

    # Get messages
    history = get_message_history()
    messages = history.get_messages(
        user_id=filters_dict.get("user_id"),
        chat_id=filters_dict.get("chat_id"),
        platform=filters_dict.get("platform"),
        message_type=filters_dict.get("message_type"),
        limit=limit,
    )

    if not messages:
        filter_desc = "matching criteria" if filters_dict else ""
        await update.message.reply_text(
            f"📭 **No Messages Found**\n\n" f"No messages {filter_desc} in history.",
            parse_mode="HTML",
        )
        return

    # Format messages for Telegram (HTML)
    # Telegram has a 4096 character limit, so we'll send multiple messages if needed
    message_parts = []
    current_part = f"📜 **Message History** ({len(messages)} message{'s' if len(messages) != 1 else ''})\n\n"

    for i, msg in enumerate(messages, 1):
        msg_entry = (
            f"<b>Message {i}</b>\n"
            f"Time: {msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Platform: {msg.platform}\n"
            f"User: <code>{msg.user_id}</code>\n"
            f"Chat: <code>{msg.chat_id}</code>\n"
            f"Type: {msg.message_type}\n"
        )

        if msg.message_id:
            msg_entry += f"ID: <code>{msg.message_id}</code>\n"

        # Truncate content if too long (leave room for formatting)
        content_preview = msg.message_content[:300] + (
            "..." if len(msg.message_content) > 300 else ""
        )
        msg_entry += f"\nContent:\n<pre>{content_preview}</pre>\n"

        if msg.rendering_metadata:
            metadata_str = ", ".join(
                f"{k}={v}" for k, v in list(msg.rendering_metadata.items())[:3]
            )
            if len(msg.rendering_metadata) > 3:
                metadata_str += "..."
            msg_entry += f"\nMetadata: {metadata_str}\n"

        msg_entry += "\n"

        # Check if adding this entry would exceed Telegram's limit
        if len(current_part) + len(msg_entry) > 4000:  # Leave some margin
            message_parts.append(current_part)
            current_part = msg_entry
        else:
            current_part += msg_entry

    if current_part:
        message_parts.append(current_part)

    # Send messages
    for part in message_parts:
        await update.message.reply_text(part, parse_mode="HTML")

    # Log audit action
    log_audit_action(
        action="message_history_viewed",
        actor_user_id=user_id,
        target_user_id=filters_dict.get("user_id"),
        details={
            "filters": filters_dict,
            "limit": limit,
            "results_count": len(messages),
        },
        ip_address=get_user_ip(update),
    )


async def admin_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin_help command - Show admin command help."""
    user_id = str(update.effective_user.id)

    if not is_admin(user_id):
        await update.message.reply_text(
            "❌ **Access Denied**\n\n" "You are not authorized to use admin commands."
        )
        return

    help_text = """
🔐 **Admin Commands**

**User Management:**
`/admin_block <user_id> [reason]` - Block a user
`/admin_unblock <user_id>` - Unblock a user
`/admin_list_blocked` - List all blocked users

**Conversation Management:**
`/admin_clear_conversation <conversation_id>` - Clear a conversation
`/admin_clear_user <user_id>` - Clear all conversations for a user

**Debugging:**
`/admin_message_history [options]` - View message history
  Options:
    `--user-id <id>` - Filter by user ID
    `--chat-id <id>` - Filter by chat/channel ID
    `--platform <telegram|discord>` - Filter by platform
    `--type <text|voice|error|status>` - Filter by message type
    `--limit <n>` - Limit results (1-50, default: 10)
    `--stats` - Show statistics instead of messages
  Examples:
    `/admin_message_history --user-id 12345 --limit 5`
    `/admin_message_history --platform telegram --type error`
    `/admin_message_history --stats`

**System:**
`/admin_status` - Check system status
`/admin_help` - Show this help message

**Note:** All admin actions are logged for audit purposes.
    """

    await update.message.reply_text(help_text)
