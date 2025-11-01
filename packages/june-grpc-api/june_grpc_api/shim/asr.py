import grpc
from typing import Optional

from ..generated import asr_pb2, asr_pb2_grpc


class RecognitionResult:
    def __init__(self, transcript: str, confidence: float):
        self.transcript = transcript
        self.confidence = confidence


class RecognitionConfig:
    def __init__(self, language: str = "en", interim_results: bool = False):
        self.language = language
        self.interim_results = interim_results

    def to_proto(self) -> asr_pb2.RecognitionConfig:
        return asr_pb2.RecognitionConfig(language=self.language, interim_results=self.interim_results)


class SpeechToTextClient:
    def __init__(self, channel: grpc.Channel):
        self._stub = asr_pb2_grpc.SpeechToTextStub(channel)

    async def recognize(self, audio_data: bytes, sample_rate: int = 16000, encoding: str = "wav", config: Optional[RecognitionConfig] = None, timeout: Optional[float] = 30.0) -> RecognitionResult:
        cfg = (config or RecognitionConfig()).to_proto()
        request = asr_pb2.RecognitionRequest(audio_data=audio_data, sample_rate=sample_rate, encoding=encoding, config=cfg)
        response = await self._stub.Recognize(request, timeout=timeout)
        if response.results:
            r = response.results[0]
            return RecognitionResult(transcript=r.transcript, confidence=r.confidence)
        return RecognitionResult(transcript="", confidence=0.0)





