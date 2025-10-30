import os
import sys
import asyncio
import logging
from concurrent import futures

import grpc
import numpy as np

from june_grpc_api.asr_pb2 import RecognitionRequest, RecognitionResponse, RecognitionResult, HealthRequest, HealthResponse
import june_grpc_api.asr_pb2_grpc as asr_pb2_grpc


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("stt-whisper")


class WhisperSTTService(asr_pb2_grpc.SpeechToTextServicer):
    def __init__(self) -> None:
        self.model_name = os.getenv("STT_MODEL_NAME", "tiny.en")
        self.device = os.getenv("STT_DEVICE", "cpu")
        self._load_model()

    def _load_model(self) -> None:
        import whisper  # lazy import to ensure dependencies are present

        logger.info(f"Loading Whisper model: {self.model_name} on {self.device}")
        self.whisper = whisper.load_model(self.model_name, device=self.device)
        logger.info("Whisper model loaded")

    def Recognize(self, request: RecognitionRequest, context) -> RecognitionResponse:
        try:
            if not request.audio_data:
                return RecognitionResponse(results=[])

            # Save to a temp wav that ffmpeg can parse
            import tempfile
            import soundfile as sf

            # The client is assumed to send 16kHz 16-bit PCM mono raw wav bytes (with header)
            # Use a temp file for whisper convenience via ffmpeg
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(request.audio_data)
                temp_path = f.name

            lang = "en"
            try:
                if request.config and request.config.language:
                    lang = request.config.language
            except Exception:
                pass
            result = self.whisper.transcribe(temp_path, language=lang)
            text = (result or {}).get("text", "").strip()
            logger.info(f"Transcription: {text[:100]}")

            os.unlink(temp_path)

            rec_result = RecognitionResult(transcript=text, confidence=0.0)
            return RecognitionResponse(results=[rec_result])

        except Exception as e:
            logger.exception("STT recognition failed")
            return RecognitionResponse(results=[])

    def HealthCheck(self, request: HealthRequest, context) -> HealthResponse:
        return HealthResponse(healthy=True)


def serve() -> None:
    port = int(os.getenv("STT_PORT", "50052"))
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    asr_pb2_grpc.add_SpeechToTextServicer_to_server(WhisperSTTService(), server)
    server.add_insecure_port(f"[::]:{port}")
    logger.info(f"Starting Whisper STT server on port {port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()


