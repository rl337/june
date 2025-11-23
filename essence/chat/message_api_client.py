"""
Message API Client

HTTP client for interacting with the Message API service.
Provides a clean interface for sending messages, editing messages, and querying message history.
"""
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Default API base URL
# Note: Message API is mapped as 8083:8082 in docker-compose.yml (host:container)
# For host access, use port 8083. For container access, use port 8082.
DEFAULT_API_URL = os.getenv("MESSAGE_API_URL", "http://localhost:8083")


class MessageAPIClient:
    """
    Client for interacting with the Message API service.

    Provides methods for:
    - Listing message history (GET /messages)
    - Getting specific messages (GET /messages/{message_id})
    - Sending messages (POST /messages)
    - Editing messages (PUT /messages/{message_id})
    - Appending to messages (PATCH /messages/{message_id})
    """

    def __init__(self, base_url: str = DEFAULT_API_URL, timeout: float = 10.0):
        """
        Initialize the Message API client.

        Args:
            base_url: Base URL for the Message API service (default: http://localhost:8082)
            timeout: Request timeout in seconds (default: 10.0)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(
        self,
        method: str,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the API.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH)
            endpoint: API endpoint (e.g., "/messages")
            json: JSON body for POST/PUT/PATCH requests
            params: Query parameters for GET requests

        Returns:
            Response JSON as dictionary

        Raises:
            httpx.HTTPError: If the request fails
        """
        url = f"{self.base_url}{endpoint}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(
                    method=method, url=url, json=json, params=params
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Message API request failed: {method} {url} - {e}")
            raise

    def list_messages(
        self,
        platform: Optional[str] = None,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        message_type: Optional[str] = None,
        limit: Optional[int] = 50,
        offset: Optional[int] = 0,
    ) -> Dict[str, Any]:
        """
        List message history with optional filters.

        Args:
            platform: Filter by platform ("telegram" or "discord")
            user_id: Filter by user ID
            chat_id: Filter by chat/channel ID
            message_type: Filter by message type
            limit: Maximum number of results (default: 50)
            offset: Offset for pagination (default: 0)

        Returns:
            Dictionary with "messages" list and "total" count
        """
        params = {}
        if platform:
            params["platform"] = platform
        if user_id:
            params["user_id"] = user_id
        if chat_id:
            params["chat_id"] = chat_id
        if message_type:
            params["message_type"] = message_type
        if limit:
            params["limit"] = limit
        if offset:
            params["offset"] = offset

        return self._request("GET", "/messages", params=params)

    def get_message(
        self, message_id: str, platform: Optional[str] = None, user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get a specific message by ID.

        Args:
            message_id: Message ID to retrieve
            platform: Optional platform filter
            user_id: Optional user ID filter

        Returns:
            Message data as dictionary
        """
        params = {}
        if platform:
            params["platform"] = platform
        if user_id:
            params["user_id"] = user_id

        return self._request("GET", f"/messages/{message_id}", params=params)

    def send_message(
        self,
        user_id: str,
        chat_id: str,
        message: str,
        platform: str = "auto",
        message_type: str = "text",
    ) -> Dict[str, Any]:
        """
        Send a new message to a user.

        Args:
            user_id: User ID to send message to
            chat_id: Chat/channel ID
            message: Message content
            platform: Platform ("telegram", "discord", or "auto")
            message_type: Message type ("text", "error", "status", etc.)

        Returns:
            Response dictionary with success status, message_id, platform, error
        """
        payload = {
            "user_id": user_id,
            "chat_id": chat_id,
            "message": message,
            "platform": platform,
            "message_type": message_type,
        }
        return self._request("POST", "/messages", json=payload)

    def edit_message(
        self,
        message_id: str,
        new_message: str,
        message_type: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Edit/replace an existing message.

        Args:
            message_id: ID of message to edit
            new_message: New message content
            message_type: Optional new message type
            platform: Optional platform filter

        Returns:
            Response dictionary with success status
        """
        payload = {"new_message": new_message}
        if message_type:
            payload["message_type"] = message_type

        params = {}
        if platform:
            params["platform"] = platform

        return self._request("PUT", f"/messages/{message_id}", json=payload, params=params)

    def append_to_message(
        self,
        message_id: str,
        new_content: str,
        message_type: Optional[str] = None,
        platform: Optional[str] = None,
        prepend: bool = False,
        replace: bool = False,
    ) -> Dict[str, Any]:
        """
        Append to or partially update a message.

        Args:
            message_id: ID of message to update
            new_content: Content to append (or prepend/replace if flags set)
            message_type: Optional new message type
            platform: Optional platform filter
            prepend: If True, prepend content instead of appending
            replace: If True, replace entire message (same as edit_message)

        Returns:
            Response dictionary with success status
        """
        # Add prefix based on mode
        if replace:
            content = f"REPLACE:{new_content}"
        elif prepend:
            content = f"PREPEND:{new_content}"
        else:
            content = new_content

        payload = {"new_message": content}
        if message_type:
            payload["message_type"] = message_type

        params = {}
        if platform:
            params["platform"] = platform

        return self._request("PATCH", f"/messages/{message_id}", json=payload, params=params)

    def health_check(self) -> Dict[str, Any]:
        """
        Check API service health.

        Returns:
            Health status dictionary
        """
        return self._request("GET", "/health")


# Convenience functions for backward compatibility
def send_message_via_api(
    user_id: str,
    chat_id: str,
    message: str,
    platform: str = "auto",
    message_type: str = "text",
    api_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send a message via the Message API (convenience function).

    This is a drop-in replacement for `essence.chat.agent_communication.send_message_to_user()`.

    Args:
        user_id: User ID to send message to
        chat_id: Chat/channel ID
        message: Message content
        platform: Platform ("telegram", "discord", or "auto")
        message_type: Message type
        api_url: Optional API base URL (defaults to MESSAGE_API_URL env var or http://localhost:8082)

    Returns:
        Response dictionary with success status, message_id, platform, error
    """
    base_url = api_url or DEFAULT_API_URL
    client = MessageAPIClient(base_url=base_url)
    return client.send_message(
        user_id=user_id,
        chat_id=chat_id,
        message=message,
        platform=platform,
        message_type=message_type,
    )


def edit_message_via_api(
    message_id: str,
    new_message: str,
    message_type: Optional[str] = None,
    platform: Optional[str] = None,
    api_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Edit a message via the Message API (convenience function).

    This is a drop-in replacement for `essence.chat.agent_communication.edit_message_to_user()`.

    Args:
        message_id: ID of message to edit
        new_message: New message content
        message_type: Optional new message type
        platform: Optional platform filter
        api_url: Optional API base URL

    Returns:
        Response dictionary with success status
    """
    base_url = api_url or DEFAULT_API_URL
    client = MessageAPIClient(base_url=base_url)
    return client.edit_message(
        message_id=message_id,
        new_message=new_message,
        message_type=message_type,
        platform=platform,
    )
