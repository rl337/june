"""
Locust load test for Gateway REST API endpoints.

Tests:
- Health checks
- LLM generation
- TTS synthesis
- STT transcription
- Chat endpoints
"""
import json
import logging
import random
import time

from locust import HttpUser, between, events, task
from locust.contrib.fasthttp import FastHttpUser

logger = logging.getLogger(__name__)

# Sample test data
SAMPLE_PROMPTS = [
    "Hello, how are you?",
    "What is the weather like today?",
    "Tell me a short story about a robot.",
    "Explain quantum computing in simple terms.",
    "What are the benefits of exercise?",
    "Write a haiku about technology.",
    "Describe the process of photosynthesis.",
    "What is machine learning?",
    "Tell me about the history of computers.",
    "What are the main causes of climate change?",
]

SAMPLE_TTS_TEXTS = [
    "Hello, this is a test message.",
    "The quick brown fox jumps over the lazy dog.",
    "Testing text to speech synthesis.",
    "This is a longer sentence to test TTS with more words and complexity.",
    "Short test.",
]

# Authentication tokens cache
auth_tokens = {}


def get_auth_token(client, user_id):
    """Get or create authentication token for a user."""
    if user_id not in auth_tokens:
        try:
            response = client.post(
                "/auth/token",
                params={"user_id": user_id},
                name="/auth/token",
                catch_response=True,
            )
            if response.status_code == 200:
                token_data = response.json()
                auth_tokens[user_id] = token_data.get("access_token")
                response.success()
            else:
                response.failure(f"Failed to get token: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error getting auth token: {e}")
            return None
    return auth_tokens.get(user_id)


class GatewayRESTUser(FastHttpUser):
    """Load test user for Gateway REST API endpoints."""

    wait_time = between(1, 3)  # Wait 1-3 seconds between requests

    def on_start(self):
        """Setup user session."""
        self.user_id = f"load_test_user_{random.randint(1000, 9999)}"
        self.token = get_auth_token(self.client, self.user_id)
        if not self.token:
            logger.warning(f"Failed to get auth token for {self.user_id}")

    @task(10)
    def health_check(self):
        """Health check endpoint - lightweight, high frequency."""
        with self.client.get(
            "/health", name="/health", catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")

    @task(30)
    def llm_generate(self):
        """LLM generation endpoint - high weight, core functionality."""
        if not self.token:
            return

        prompt = random.choice(SAMPLE_PROMPTS)
        headers = {"Authorization": f"Bearer {self.token}"}

        with self.client.post(
            "/api/v1/llm/generate",
            json={"prompt": prompt},
            headers=headers,
            name="/api/v1/llm/generate",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if "text" in data:
                    response.success()
                else:
                    response.failure("Missing 'text' in response")
            elif response.status_code == 429:
                response.failure("Rate limited")
            else:
                response.failure(f"Request failed: {response.status_code}")

    @task(20)
    def tts_speak(self):
        """TTS synthesis endpoint."""
        if not self.token:
            return

        text = random.choice(SAMPLE_TTS_TEXTS)
        headers = {"Authorization": f"Bearer {self.token}"}

        with self.client.post(
            "/api/v1/tts/speak",
            json={"text": text, "language": "en", "voice_id": "default"},
            headers=headers,
            name="/api/v1/tts/speak",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if "audio_b64" in data:
                    response.success()
                else:
                    response.failure("Missing 'audio_b64' in response")
            elif response.status_code == 429:
                response.failure("Rate limited")
            else:
                response.failure(f"Request failed: {response.status_code}")

    @task(20)
    def audio_transcribe(self):
        """STT transcription endpoint - requires audio file."""
        if not self.token:
            return

        # For load testing, we'll use a small test audio file
        # In production, this would be a real audio file
        # For now, we'll skip this or use a minimal test file
        # This is a placeholder - actual implementation would need audio file handling
        pass

    @task(40)
    def chat(self):
        """Chat endpoint - most common operation."""
        if not self.token:
            return

        message = random.choice(SAMPLE_PROMPTS)
        headers = {"Authorization": f"Bearer {self.token}"}

        with self.client.post(
            "/chat",
            json={"type": "text", "text": message},
            headers=headers,
            name="/chat",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if "text" in data or "response" in data:
                    response.success()
                else:
                    response.failure("Invalid response format")
            elif response.status_code == 429:
                response.failure("Rate limited")
            else:
                response.failure(f"Request failed: {response.status_code}")

    @task(5)
    def get_status(self):
        """Status endpoint."""
        with self.client.get(
            "/status", name="/status", catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status check failed: {response.status_code}")


# Custom event handlers for metrics collection
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when the test starts."""
    logger.info("Load test started")
    # Clear auth tokens cache
    auth_tokens.clear()


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when the test stops."""
    logger.info("Load test stopped")
    # Generate custom metrics report
    stats = environment.stats
    logger.info(f"Total requests: {stats.total.num_requests}")
    logger.info(f"Total failures: {stats.total.num_failures}")
    logger.info(f"Average response time: {stats.total.avg_response_time:.2f}ms")
