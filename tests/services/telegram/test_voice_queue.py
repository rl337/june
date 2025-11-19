"""Tests for voice message queue."""
import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from essence.services.telegram.voice_queue import (
    VoiceMessageQueue,
    create_worker_subscription,
)


@pytest.fixture
def mock_nats():
    """Mock NATS connection."""
    mock_nc = AsyncMock()
    mock_js = AsyncMock()
    mock_nc.jetstream.return_value = mock_js
    mock_nc.is_connected = True
    return mock_nc, mock_js


@pytest.mark.asyncio
async def test_voice_queue_connect(mock_nats):
    """Test queue connection."""
    mock_nc, mock_js = mock_nats

    with patch(
        "essence.services.telegram.voice_queue.nats.connect", return_value=mock_nc
    ):
        queue = VoiceMessageQueue(nats_url="nats://localhost:4222")

        # Mock stream_info to raise NotFoundError (stream doesn't exist)
        mock_js.stream_info = AsyncMock(side_effect=Exception("NotFound"))
        mock_js.add_stream = AsyncMock()

        await queue.connect()

        assert queue._initialized
        assert queue.nc == mock_nc
        assert queue.js == mock_js


@pytest.mark.asyncio
async def test_voice_queue_publish(mock_nats):
    """Test publishing voice message."""
    mock_nc, mock_js = mock_nats

    # Mock ack response
    mock_ack = MagicMock()
    mock_ack.seq = 123
    mock_js.publish = AsyncMock(return_value=mock_ack)

    with patch(
        "essence.services.telegram.voice_queue.nats.connect", return_value=mock_nc
    ):
        queue = VoiceMessageQueue(nats_url="nats://localhost:4222")
        queue.nc = mock_nc
        queue.js = mock_js
        queue._initialized = True

        audio_data = b"test audio data"
        seq = await queue.publish_voice_message(
            voice_file_id="file123",
            user_id="user1",
            chat_id="chat1",
            audio_data=audio_data,
            metadata={"test": "data"},
        )

        assert seq == "123"
        mock_js.publish.assert_called_once()

        # Verify message payload
        call_args = mock_js.publish.call_args
        assert call_args[0][0] == "voice.message.process"

        # Decode and verify payload
        payload = json.loads(call_args[0][1].decode("utf-8"))
        assert payload["voice_file_id"] == "file123"
        assert payload["user_id"] == "user1"
        assert payload["chat_id"] == "chat1"
        assert base64.b64decode(payload["audio_data"]) == audio_data


@pytest.mark.asyncio
async def test_voice_queue_status(mock_nats):
    """Test getting queue status."""
    mock_nc, mock_js = mock_nats

    # Mock stream info
    mock_stream_info = MagicMock()
    mock_stream_info.state = MagicMock()
    mock_stream_info.state.messages = 10
    mock_stream_info.state.bytes = 1024
    mock_stream_info.state.first_seq = 1
    mock_stream_info.state.last_seq = 10
    mock_stream_info.state.consumer_count = 2

    mock_js.stream_info = AsyncMock(return_value=mock_stream_info)
    mock_js.consumer_info = AsyncMock(side_effect=Exception("NotFound"))

    with patch(
        "essence.services.telegram.voice_queue.nats.connect", return_value=mock_nc
    ):
        queue = VoiceMessageQueue(nats_url="nats://localhost:4222")
        queue.nc = mock_nc
        queue.js = mock_js
        queue._initialized = True

        status = await queue.get_queue_status()

        assert status["stream_name"] == "VOICE_MESSAGES"
        assert status["messages"] == 10
        assert status["bytes"] == 1024
        assert status["first_seq"] == 1
        assert status["last_seq"] == 10


@pytest.mark.asyncio
async def test_worker_subscription(mock_nats):
    """Test worker subscription."""
    mock_nc, mock_js = mock_nats

    # Mock consumer
    mock_consumer = AsyncMock()
    mock_js.pull_subscribe = AsyncMock(return_value=mock_consumer)

    # Mock message
    mock_msg = MagicMock()
    mock_msg.data = json.dumps(
        {
            "voice_file_id": "file123",
            "user_id": "user1",
            "chat_id": "chat1",
            "audio_data": base64.b64encode(b"test audio").decode("utf-8"),
            "metadata": {},
        }
    ).encode("utf-8")
    mock_msg.ack = AsyncMock()
    mock_msg.nak = AsyncMock()

    # Mock fetch to return one message then timeout
    call_count = 0

    async def mock_fetch(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [mock_msg]
        else:
            raise asyncio.TimeoutError()

    mock_consumer.fetch = mock_fetch

    processed_messages = []

    async def process_callback(msg_data):
        processed_messages.append(msg_data)

    with patch(
        "essence.services.telegram.voice_queue.nats.connect", return_value=mock_nc
    ):
        queue = VoiceMessageQueue(nats_url="nats://localhost:4222")
        queue.nc = mock_nc
        queue.js = mock_js
        queue._initialized = True

        # Start subscription in background
        task = asyncio.create_task(
            create_worker_subscription(
                queue=queue, process_callback=process_callback, worker_id="test-worker"
            )
        )

        # Wait a bit for processing
        await asyncio.sleep(0.1)

        # Cancel task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify message was processed
        assert len(processed_messages) == 1
        assert processed_messages[0]["voice_file_id"] == "file123"
        assert processed_messages[0]["user_id"] == "user1"
        mock_msg.ack.assert_called_once()
