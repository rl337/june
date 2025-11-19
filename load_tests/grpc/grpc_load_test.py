"""
gRPC load test for STT, TTS, and Inference API services.

This script uses the june-grpc-api package to test gRPC endpoints.
"""
import asyncio
import time
import random
import statistics
from typing import List, Dict, Any
import logging
from concurrent.futures import ThreadPoolExecutor
import grpc

# Try to import june-grpc-api
try:
    from june_grpc_api import asr as asr_shim, tts as tts_shim, llm as llm_shim

    GRPC_API_AVAILABLE = True
except ImportError:
    GRPC_API_AVAILABLE = False
    logging.warning(
        "june-grpc-api package not available. Install it to run gRPC load tests."
    )

logger = logging.getLogger(__name__)

SAMPLE_PROMPTS = [
    "Hello, how are you?",
    "What is the weather like today?",
    "Tell me a short story about a robot.",
    "Explain quantum computing in simple terms.",
    "What are the benefits of exercise?",
]

SAMPLE_TTS_TEXTS = [
    "Hello, this is a test message.",
    "The quick brown fox jumps over the lazy dog.",
    "Testing text to speech synthesis.",
    "This is a longer sentence to test TTS with more words and complexity.",
]


class GRPCLoadTest:
    """gRPC load test runner."""

    def __init__(
        self,
        inference_host: str = "localhost:50051",
        stt_host: str = "localhost:50052",
        tts_host: str = "localhost:50053",
        num_users: int = 10,
        duration: int = 60,
        spawn_rate: float = 1.0,
    ):
        self.inference_host = inference_host
        self.stt_host = stt_host
        self.tts_host = tts_host
        self.num_users = num_users
        self.duration = duration
        self.spawn_rate = spawn_rate

        self.results = {"inference": [], "stt": [], "tts": []}
        self.errors = {"inference": 0, "stt": 0, "tts": 0}

    async def test_inference_api(self, prompt: str) -> Dict[str, Any]:
        """Test Inference API gRPC endpoint."""
        start_time = time.time()
        error = None

        try:
            # Create gRPC channel
            channel = grpc.aio.insecure_channel(self.inference_host)
            client = llm_shim.LLMClient(channel)

            # Call generate
            result = await client.generate(prompt)

            response_time = (time.time() - start_time) * 1000  # Convert to ms

            await channel.close()

            return {
                "service": "inference",
                "success": True,
                "response_time": response_time,
                "error": None,
            }
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            error = str(e)
            self.errors["inference"] += 1
            logger.error(f"Inference API error: {e}")

            return {
                "service": "inference",
                "success": False,
                "response_time": response_time,
                "error": error,
            }

    async def test_stt_service(self, audio_data: bytes) -> Dict[str, Any]:
        """Test STT service gRPC endpoint."""
        start_time = time.time()
        error = None

        try:
            # Create gRPC channel
            channel = grpc.aio.insecure_channel(self.stt_host)
            client = asr_shim.SpeechToTextClient(channel)

            # Configure recognition
            config = asr_shim.RecognitionConfig(language="en", interim_results=False)

            # Call recognize
            result = await client.recognize(
                audio_data, sample_rate=16000, encoding="wav", config=config
            )

            response_time = (time.time() - start_time) * 1000

            await channel.close()

            return {
                "service": "stt",
                "success": True,
                "response_time": response_time,
                "error": None,
            }
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            error = str(e)
            self.errors["stt"] += 1
            logger.error(f"STT service error: {e}")

            return {
                "service": "stt",
                "success": False,
                "response_time": response_time,
                "error": error,
            }

    async def test_tts_service(self, text: str) -> Dict[str, Any]:
        """Test TTS service gRPC endpoint."""
        start_time = time.time()
        error = None

        try:
            # Create gRPC channel
            channel = grpc.aio.insecure_channel(self.tts_host)
            client = tts_shim.TextToSpeechClient(channel)

            # Configure synthesis
            config = tts_shim.SynthesisConfig(sample_rate=16000, speed=1.0, pitch=0.0)

            # Call synthesize
            result = await client.synthesize(
                text=text, voice_id="default", language="en", config=config
            )

            response_time = (time.time() - start_time) * 1000

            await channel.close()

            return {
                "service": "tts",
                "success": True,
                "response_time": response_time,
                "error": None,
            }
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            error = str(e)
            self.errors["tts"] += 1
            logger.error(f"TTS service error: {e}")

            return {
                "service": "tts",
                "success": False,
                "response_time": response_time,
                "error": error,
            }

    async def user_loop(self, user_id: int):
        """Simulate a single user's behavior."""
        end_time = time.time() + self.duration

        while time.time() < end_time:
            # Randomly choose a service to test
            service_choice = random.choices(
                ["inference", "stt", "tts"], weights=[30, 20, 20], k=1
            )[0]

            if service_choice == "inference":
                prompt = random.choice(SAMPLE_PROMPTS)
                result = await self.test_inference_api(prompt)
                self.results["inference"].append(result)

            elif service_choice == "stt":
                # For STT, we'd need actual audio data
                # For load testing, we can skip this or use a minimal test file
                # This is a placeholder
                pass

            elif service_choice == "tts":
                text = random.choice(SAMPLE_TTS_TEXTS)
                result = await self.test_tts_service(text)
                self.results["tts"].append(result)

            # Wait between requests
            await asyncio.sleep(random.uniform(1, 3))

    async def run(self):
        """Run the load test."""
        if not GRPC_API_AVAILABLE:
            logger.error(
                "june-grpc-api package not available. Cannot run gRPC load tests."
            )
            return

        logger.info(
            f"Starting gRPC load test with {self.num_users} users for {self.duration}s"
        )

        # Create tasks for all users
        tasks = []
        for i in range(self.num_users):
            # Stagger user start times
            await asyncio.sleep(1.0 / self.spawn_rate)
            tasks.append(self.user_loop(i))

        # Wait for all tasks to complete
        await asyncio.gather(*tasks)

        # Generate report
        self.generate_report()

    def generate_report(self):
        """Generate load test report."""
        print("\n" + "=" * 80)
        print("gRPC Load Test Results")
        print("=" * 80)

        for service in ["inference", "stt", "tts"]:
            results = self.results[service]
            if not results:
                continue

            successful = [r for r in results if r["success"]]
            failed = [r for r in results if not r["success"]]

            if successful:
                response_times = [r["response_time"] for r in successful]

                print(f"\n{service.upper()} Service:")
                print(f"  Total requests: {len(results)}")
                print(f"  Successful: {len(successful)}")
                print(f"  Failed: {len(failed)}")
                print(f"  Success rate: {len(successful)/len(results)*100:.2f}%")
                print(
                    f"  Average response time: {statistics.mean(response_times):.2f}ms"
                )
                print(
                    f"  Median response time: {statistics.median(response_times):.2f}ms"
                )
                if len(response_times) > 1:
                    print(
                        f"  P95 response time: {self.percentile(response_times, 95):.2f}ms"
                    )
                    print(
                        f"  P99 response time: {self.percentile(response_times, 99):.2f}ms"
                    )

        print("\n" + "=" * 80)

    @staticmethod
    def percentile(data: List[float], p: float) -> float:
        """Calculate percentile."""
        sorted_data = sorted(data)
        index = int(len(sorted_data) * p / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="gRPC load test for June services")
    parser.add_argument(
        "--inference-host", default="localhost:50051", help="Inference API host"
    )
    parser.add_argument(
        "--stt-host", default="localhost:50052", help="STT service host"
    )
    parser.add_argument(
        "--tts-host", default="localhost:50053", help="TTS service host"
    )
    parser.add_argument(
        "--users", type=int, default=10, help="Number of concurrent users"
    )
    parser.add_argument(
        "--duration", type=int, default=60, help="Test duration in seconds"
    )
    parser.add_argument(
        "--spawn-rate", type=float, default=1.0, help="User spawn rate per second"
    )

    args = parser.parse_args()

    test = GRPCLoadTest(
        inference_host=args.inference_host,
        stt_host=args.stt_host,
        tts_host=args.tts_host,
        num_users=args.users,
        duration=args.duration,
        spawn_rate=args.spawn_rate,
    )

    await test.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
