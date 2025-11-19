"""NATS message queue for voice message processing.

Note: NATS is not available for MVP. This module is kept for optional queue processing
but will fail gracefully if NATS is not available. Set USE_VOICE_QUEUE=false to disable.
"""
import asyncio
import json
import logging
import os
from typing import Optional, Dict, Any
import base64

# NATS removed for MVP - import will fail if package not available
try:
    import nats
    from nats.js import api
    from nats.js.errors import NotFoundError

    NATS_AVAILABLE = True
except ImportError:
    NATS_AVAILABLE = False
    nats = None
    api = None
    NotFoundError = Exception

logger = logging.getLogger(__name__)


class VoiceMessageQueue:
    """NATS JetStream queue for voice message processing."""

    STREAM_NAME = "VOICE_MESSAGES"
    SUBJECT = "voice.message.process"
    CONSUMER_GROUP = "voice_workers"

    def __init__(self, nats_url: Optional[str] = None):
        """Initialize the voice message queue.

        Args:
            nats_url: NATS server URL (defaults to NATS_URL env var or nats://localhost:4222)
        """
        self.nats_url = nats_url or os.getenv("NATS_URL", "nats://localhost:4222")
        self.nc: Optional[nats.NATS] = None
        self.js: Optional[api.JetStreamContext] = None
        self._initialized = False

    async def connect(self):
        """Connect to NATS and initialize JetStream.

        Note: NATS is not available for MVP. This will raise RuntimeError if NATS is not available.
        """
        if self._initialized:
            return

        if not NATS_AVAILABLE:
            raise RuntimeError(
                "NATS is not available for MVP. Voice message queue requires NATS. "
                "Set USE_VOICE_QUEUE=false to disable queue processing and use direct processing instead."
            )

        try:
            self.nc = await nats.connect(self.nats_url)
            self.js = self.nc.jetstream()

            # Create stream if it doesn't exist
            try:
                await self.js.stream_info(self.STREAM_NAME)
            except NotFoundError:
                # Create stream with durability settings
                await self.js.add_stream(
                    name=self.STREAM_NAME,
                    subjects=[self.SUBJECT],
                    max_age=3600,  # 1 hour retention
                    storage=api.StorageType.FILE,
                    retention=api.RetentionPolicy.WORK_QUEUE,  # Work queue mode for load balancing
                    max_msgs=10000,  # Max 10k messages
                    max_bytes=10 * 1024 * 1024 * 1024,  # 10GB max
                )
                logger.info(f"Created NATS stream: {self.STREAM_NAME}")

            self._initialized = True
            logger.info(f"Connected to NATS at {self.nats_url}")
        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}", exc_info=True)
            raise RuntimeError(
                f"NATS connection failed: {e}. "
                "Set USE_VOICE_QUEUE=false to disable queue processing."
            ) from e

    async def disconnect(self):
        """Disconnect from NATS."""
        if self.nc:
            await self.nc.close()
            self.nc = None
            self.js = None
            self._initialized = False
            logger.info("Disconnected from NATS")

    async def publish_voice_message(
        self,
        voice_file_id: str,
        user_id: str,
        chat_id: str,
        audio_data: bytes,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Publish a voice message to the queue for processing.

        Args:
            voice_file_id: Telegram file ID
            user_id: Telegram user ID
            chat_id: Telegram chat ID
            audio_data: Raw audio data bytes
            metadata: Optional metadata dict

        Returns:
            Message sequence number (as string)
        """
        if not self._initialized:
            await self.connect()

        # Prepare message payload
        payload = {
            "voice_file_id": voice_file_id,
            "user_id": user_id,
            "chat_id": chat_id,
            "audio_data": base64.b64encode(audio_data).decode("utf-8"),
            "metadata": metadata or {},
        }

        message_json = json.dumps(payload)

        try:
            # Publish to JetStream with durability
            ack = await self.js.publish(
                self.SUBJECT,
                message_json.encode("utf-8"),
                headers={
                    "voice_file_id": voice_file_id,
                    "user_id": user_id,
                    "chat_id": chat_id,
                },
            )

            logger.info(
                f"Published voice message to queue: file_id={voice_file_id}, "
                f"user={user_id}, chat={chat_id}, seq={ack.seq}"
            )
            return str(ack.seq)
        except Exception as e:
            logger.error(f"Failed to publish voice message: {e}", exc_info=True)
            raise

    async def get_queue_status(self) -> Dict[str, Any]:
        """Get queue status and statistics.

        Returns:
            Dict with queue statistics
        """
        if not self._initialized:
            await self.connect()

        try:
            stream_info = await self.js.stream_info(self.STREAM_NAME)

            # Get consumer info if it exists
            consumer_info = None
            try:
                consumer_info = await self.js.consumer_info(
                    self.STREAM_NAME, self.CONSUMER_GROUP
                )
            except NotFoundError:
                pass

            return {
                "stream_name": self.STREAM_NAME,
                "subject": self.SUBJECT,
                "messages": stream_info.state.messages,
                "bytes": stream_info.state.bytes,
                "first_seq": stream_info.state.first_seq,
                "last_seq": stream_info.state.last_seq,
                "consumer_count": stream_info.state.consumer_count,
                "consumer": {
                    "pending": consumer_info.num_pending if consumer_info else 0,
                    "delivered": consumer_info.delivered.consumer_seq
                    if consumer_info
                    else 0,
                }
                if consumer_info
                else None,
            }
        except Exception as e:
            logger.error(f"Failed to get queue status: {e}", exc_info=True)
            return {
                "error": str(e),
                "stream_name": self.STREAM_NAME,
            }


async def create_worker_subscription(
    queue: VoiceMessageQueue, process_callback, worker_id: Optional[str] = None
):
    """Create a worker subscription to process voice messages.

    Args:
        queue: VoiceMessageQueue instance
        process_callback: Async function to process messages: async def callback(msg_data: dict)
        worker_id: Optional worker identifier for logging
    """
    if not queue._initialized:
        await queue.connect()

    worker_id = worker_id or f"worker-{os.getpid()}"
    logger.info(f"Starting voice message worker: {worker_id}")

    try:
        # Create durable consumer for load balancing
        consumer = await queue.js.pull_subscribe(
            queue.SUBJECT,
            queue.CONSUMER_GROUP,
            durable=queue.CONSUMER_GROUP,
            config=api.ConsumerConfig(
                durable_name=queue.CONSUMER_GROUP,
                ack_wait=300,  # 5 minutes ack wait
                max_deliver=3,  # Max 3 retries
                max_ack_pending=100,  # Max 100 pending acks
            ),
        )

        logger.info(f"Worker {worker_id} subscribed to queue")

        # Process messages in a loop
        while True:
            try:
                # Fetch messages (batch of 1)
                msgs = await consumer.fetch(1, timeout=30)

                for msg in msgs:
                    try:
                        # Parse message
                        payload = json.loads(msg.data.decode("utf-8"))

                        # Decode audio data
                        audio_data = base64.b64decode(payload["audio_data"])
                        payload["audio_data"] = audio_data

                        logger.info(
                            f"Worker {worker_id} processing message: "
                            f"file_id={payload['voice_file_id']}, user={payload['user_id']}"
                        )

                        # Process message
                        await process_callback(payload)

                        # Ack message on success
                        await msg.ack()
                        logger.info(
                            f"Worker {worker_id} completed message: "
                            f"file_id={payload['voice_file_id']}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Worker {worker_id} error processing message: {e}",
                            exc_info=True,
                        )
                        # NAK message to retry (will retry up to max_deliver times)
                        await msg.nak()
            except asyncio.TimeoutError:
                # No messages available, continue
                continue
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}", exc_info=True)
                await asyncio.sleep(1)  # Brief pause before retry
    except Exception as e:
        logger.error(f"Worker {worker_id} fatal error: {e}", exc_info=True)
        raise
