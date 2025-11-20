"""
Message API Service

REST API for programmatic access to message histories and sending/editing messages.
Replaces the direct function call approach with a proper API interface.

Endpoints:
- GET /messages - List message history
- GET /messages/{message_id} - Get specific message
- POST /messages - Send a new message
- PUT /messages/{message_id} - Edit/update a message
- PATCH /messages/{message_id} - Partial update (append/edit)
"""
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from essence.chat.agent_communication import (
    CommunicationChannel,
    edit_message_to_user,
    send_message_to_user,
)
from essence.chat.message_history import get_message_history

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Message API",
    description="REST API for message histories and agent-user communication",
    version="1.0.0",
)

# Service name for metrics
SERVICE_NAME = "message-api"


# Pydantic models for request/response
class MessageRequest(BaseModel):
    """Request model for sending a message."""

    user_id: str = Field(..., description="User ID to send message to")
    chat_id: str = Field(..., description="Chat/channel ID")
    message: str = Field(..., description="Message content")
    platform: str = Field(
        default="auto", description="Platform: 'telegram', 'discord', or 'auto'"
    )
    message_type: str = Field(
        default="text",
        description="Message type: 'text', 'error', 'status', 'clarification', 'help_request', 'progress'",
    )


class MessageEditRequest(BaseModel):
    """Request model for editing a message."""

    new_message: str = Field(..., description="New message content")
    message_type: Optional[str] = Field(
        default=None, description="Optional new message type"
    )


class MessageResponse(BaseModel):
    """Response model for message operations."""

    success: bool
    platform: Optional[str] = None
    message_id: Optional[str] = None
    error: Optional[str] = None


class MessageHistoryItem(BaseModel):
    """Model for a message history item."""

    platform: str
    user_id: str
    chat_id: str
    message_content: str
    message_type: str
    message_id: Optional[str] = None
    timestamp: Optional[str] = None
    raw_text: Optional[str] = None
    formatted_text: Optional[str] = None
    rendering_metadata: Optional[Dict[str, Any]] = None


class MessageHistoryResponse(BaseModel):
    """Response model for message history list."""

    messages: List[MessageHistoryItem]
    total: int
    limit: Optional[int] = None
    offset: Optional[int] = None


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": SERVICE_NAME}


@app.get("/messages", response_model=MessageHistoryResponse)
async def list_messages(
    platform: Optional[str] = Query(None, description="Filter by platform"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    chat_id: Optional[str] = Query(None, description="Filter by chat ID"),
    message_type: Optional[str] = Query(None, description="Filter by message type"),
    limit: Optional[int] = Query(50, ge=1, le=1000, description="Maximum number of results"),
    offset: Optional[int] = Query(0, ge=0, description="Offset for pagination"),
):
    """
    List message history with optional filters.

    Supports filtering by platform, user_id, chat_id, and message_type.
    Results are paginated using limit and offset.
    """
    try:
        history = get_message_history()

        # Get messages with filters
        messages = history.get_messages(
            platform=platform,
            user_id=user_id,
            chat_id=chat_id,
            message_type=message_type,
            limit=limit + offset if limit else None,  # Get more to handle offset
        )

        # Apply offset
        if offset:
            messages = messages[offset:]

        # Apply limit
        if limit:
            messages = messages[:limit]

        # Convert to response format
        history_items = [
            MessageHistoryItem(
                platform=msg.get("platform", ""),
                user_id=msg.get("user_id", ""),
                chat_id=msg.get("chat_id", ""),
                message_content=msg.get("message_content", ""),
                message_type=msg.get("message_type", "text"),
                message_id=msg.get("message_id"),
                timestamp=msg.get("timestamp"),
                raw_text=msg.get("raw_text"),
                formatted_text=msg.get("formatted_text"),
                rendering_metadata=msg.get("rendering_metadata"),
            )
            for msg in messages
        ]

        # Get total count (approximate, may be limited by history size)
        total_messages = history.get_messages(
            platform=platform,
            user_id=user_id,
            chat_id=chat_id,
            message_type=message_type,
            limit=None,  # Get all for count
        )
        total = len(total_messages)

        return MessageHistoryResponse(
            messages=history_items,
            total=total,
            limit=limit,
            offset=offset,
        )

    except Exception as e:
        logger.error(f"Error listing messages: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing messages: {str(e)}")


@app.get("/messages/{message_id}")
async def get_message(
    message_id: str,
    platform: Optional[str] = Query(None, description="Platform filter"),
    user_id: Optional[str] = Query(None, description="User ID filter"),
):
    """
    Get a specific message by ID.

    Requires message_id. Optionally filter by platform and user_id to narrow search.
    """
    try:
        history = get_message_history()

        # Get messages with filters (get_messages doesn't support message_id directly)
        messages = history.get_messages(
            platform=platform,
            user_id=user_id,
            limit=None,  # Get all matching, then filter by message_id
        )

        # Find message with matching ID
        msg = None
        for entry in messages:
            if str(entry.message_id) == str(message_id):
                msg = entry
                break

        if not msg:
            raise HTTPException(
                status_code=404, detail=f"Message {message_id} not found"
            )

        return MessageHistoryItem(
            platform=msg.platform,
            user_id=msg.user_id,
            chat_id=msg.chat_id,
            message_content=msg.message_content,
            message_type=msg.message_type,
            message_id=msg.message_id,
            timestamp=msg.timestamp,
            raw_text=msg.raw_text,
            formatted_text=msg.formatted_text,
            rendering_metadata=msg.rendering_metadata,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting message: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error getting message: {str(e)}"
        )


@app.post("/messages", response_model=MessageResponse)
async def send_message(request: MessageRequest):
    """
    Send a new message to a user.

    Creates a new message and sends it via Telegram or Discord.
    """
    try:
        # Convert platform string to CommunicationChannel enum
        platform_map = {
            "telegram": CommunicationChannel.TELEGRAM,
            "discord": CommunicationChannel.DISCORD,
            "auto": CommunicationChannel.AUTO,
        }
        platform_enum = platform_map.get(
            request.platform.lower(), CommunicationChannel.AUTO
        )

        result = send_message_to_user(
            user_id=request.user_id,
            chat_id=request.chat_id,
            message=request.message,
            platform=platform_enum,
            message_type=request.message_type,
            require_service_stopped=True,
        )

        if result.get("success"):
            return MessageResponse(
                success=True,
                platform=result.get("platform"),
                message_id=result.get("message_id"),
                error=None,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Failed to send message"),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error sending message: {str(e)}"
        )


@app.put("/messages/{message_id}", response_model=MessageResponse)
async def edit_message(
    message_id: str, request: MessageEditRequest, platform: Optional[str] = Query(None)
):
    """
    Edit/update an existing message.

    Replaces the entire message content. Requires message_id and platform.
    """
    try:
        # We need user_id and chat_id to edit - get from message history
        history = get_message_history()

        # Get messages with filters (get_messages doesn't support message_id directly)
        messages = history.get_messages(
            platform=platform,
            limit=None,  # Get all matching, then filter by message_id
        )

        # Find message with matching ID
        msg = None
        for entry in messages:
            if str(entry.message_id) == str(message_id):
                msg = entry
                break

        if not msg:
            raise HTTPException(
                status_code=404, detail=f"Message {message_id} not found"
            )

        user_id = msg.user_id
        chat_id = msg.chat_id
        msg_platform = msg.platform or platform or "auto"

        # Convert platform string to CommunicationChannel enum
        platform_map = {
            "telegram": CommunicationChannel.TELEGRAM,
            "discord": CommunicationChannel.DISCORD,
            "auto": CommunicationChannel.AUTO,
        }
        platform_enum = platform_map.get(
            msg_platform.lower(), CommunicationChannel.AUTO
        )

        message_type = request.message_type or msg.message_type or "text"

        result = edit_message_to_user(
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
            new_message=request.new_message,
            platform=platform_enum,
            message_type=message_type,
            require_service_stopped=True,
        )

        if result.get("success"):
            return MessageResponse(
                success=True,
                platform=result.get("platform"),
                message_id=message_id,
                error=None,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Failed to edit message"),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error editing message: {str(e)}"
        )


@app.patch("/messages/{message_id}", response_model=MessageResponse)
async def append_to_message(
    message_id: str,
    request: MessageEditRequest,
    platform: Optional[str] = Query(None),
):
    """
    Append to or partially update a message.

    Appends new content to existing message. If new_message starts with special markers,
    it can replace or prepend instead.
    """
    try:
        # Get existing message
        history = get_message_history()

        # Get messages with filters (get_messages doesn't support message_id directly)
        messages = history.get_messages(
            platform=platform,
            limit=None,  # Get all matching, then filter by message_id
        )

        # Find message with matching ID
        msg = None
        for entry in messages:
            if str(entry.message_id) == str(message_id):
                msg = entry
                break

        if not msg:
            raise HTTPException(
                status_code=404, detail=f"Message {message_id} not found"
            )

        existing_content = msg.message_content
        user_id = msg.user_id
        chat_id = msg.chat_id
        msg_platform = msg.platform or platform or "auto"

        # Determine if we should append, prepend, or replace
        new_content = request.new_message
        if new_content.startswith("PREPEND:"):
            # Prepend mode
            new_content = new_content[8:].strip()
            combined = f"{new_content}\n\n{existing_content}"
        elif new_content.startswith("REPLACE:"):
            # Replace mode (same as PUT)
            combined = new_content[8:].strip()
        else:
            # Default: append
            combined = f"{existing_content}\n\n{new_content}"

        # Convert platform string to CommunicationChannel enum
        platform_map = {
            "telegram": CommunicationChannel.TELEGRAM,
            "discord": CommunicationChannel.DISCORD,
            "auto": CommunicationChannel.AUTO,
        }
        platform_enum = platform_map.get(
            msg_platform.lower(), CommunicationChannel.AUTO
        )

        message_type = request.message_type or msg.message_type or "text"

        result = edit_message_to_user(
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
            new_message=combined,
            platform=platform_enum,
            message_type=message_type,
            require_service_stopped=True,
        )

        if result.get("success"):
            return MessageResponse(
                success=True,
                platform=result.get("platform"),
                message_id=message_id,
                error=None,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Failed to update message"),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating message: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error updating message: {str(e)}"
        )


def main():
    """Run the message API service."""
    port = int(os.getenv("MESSAGE_API_PORT", "8082"))
    host = os.getenv("MESSAGE_API_HOST", "0.0.0.0")

    logger.info(f"Starting Message API service on {host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
