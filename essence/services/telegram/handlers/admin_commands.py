"""Admin command handlers for Telegram bot."""
import os
import logging
from telegram import Update
from telegram.ext import ContextTypes
from typing import Optional
import httpx


from essence.services.telegram.admin_auth import require_admin, is_admin
from essence.services.telegram.admin_db import (
    block_user, unblock_user, get_blocked_users,
    clear_conversation, clear_user_conversations,
    log_audit_action, is_user_blocked
)

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
            "❌ **Access Denied**\n\n"
            "You are not authorized to use admin commands."
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
            ip_address=get_user_ip(update)
        )
        
        await update.message.reply_text(
            f"✅ **User Blocked**\n\n"
            f"User ID: `{target_user_id}`\n"
            f"Reason: {reason or 'No reason provided'}\n"
            f"Blocked by: `{user_id}`"
        )
    else:
        await update.message.reply_text(
            f"❌ Failed to block user `{target_user_id}`"
        )


async def unblock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin_unblock command - Unblock a user."""
    user_id = str(update.effective_user.id)
    
    try:
        # Check admin permission
        require_admin(user_id)
    except PermissionError:
        await update.message.reply_text(
            "❌ **Access Denied**\n\n"
            "You are not authorized to use admin commands."
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
            ip_address=get_user_ip(update)
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
            "❌ **Access Denied**\n\n"
            "You are not authorized to use admin commands."
        )
        return
    
    # Get blocked users
    blocked = get_blocked_users()
    
    if not blocked:
        await update.message.reply_text(
            "✅ **No Blocked Users**\n\n"
            "There are currently no blocked users."
        )
        return
    
    # Format blocked users list
    lines = ["🔒 **Blocked Users:**\n"]
    for user in blocked[:20]:  # Limit to 20 for message length
        reason = user.get('reason', 'No reason provided')
        blocked_by = user.get('blocked_by', 'Unknown')
        created_at = user.get('created_at', 'Unknown')
        lines.append(
            f"• User ID: `{user['user_id']}`\n"
            f"  Blocked by: `{blocked_by}`\n"
            f"  Reason: {reason}\n"
            f"  Date: {created_at}\n"
        )
    
    if len(blocked) > 20:
        lines.append(f"\n... and {len(blocked) - 20} more")
    
    await update.message.reply_text("\n".join(lines))


async def clear_conversation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin_clear_conversation command - Clear a conversation."""
    user_id = str(update.effective_user.id)
    
    try:
        # Check admin permission
        require_admin(user_id)
    except PermissionError:
        await update.message.reply_text(
            "❌ **Access Denied**\n\n"
            "You are not authorized to use admin commands."
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
            ip_address=get_user_ip(update)
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


async def clear_user_conversations_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin_clear_user command - Clear all conversations for a user."""
    user_id = str(update.effective_user.id)
    
    try:
        # Check admin permission
        require_admin(user_id)
    except PermissionError:
        await update.message.reply_text(
            "❌ **Access Denied**\n\n"
            "You are not authorized to use admin commands."
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
            ip_address=get_user_ip(update)
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
            "❌ **Access Denied**\n\n"
            "You are not authorized to use admin commands."
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
    
    status_lines.extend([
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
    ])
    
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
            "blocked_count": blocked_count
        },
        ip_address=get_user_ip(update)
    )
    
    await update.message.reply_text("\n".join(status_lines))


async def admin_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin_help command - Show admin command help."""
    user_id = str(update.effective_user.id)
    
    if not is_admin(user_id):
        await update.message.reply_text(
            "❌ **Access Denied**\n\n"
            "You are not authorized to use admin commands."
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

**System:**
`/admin_status` - Check system status
`/admin_help` - Show this help message

**Note:** All admin actions are logged for audit purposes.
    """
    
    await update.message.reply_text(help_text)
