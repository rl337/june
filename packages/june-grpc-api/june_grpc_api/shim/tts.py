from typing import Optional

import grpc

from ..generated import tts_pb2, tts_pb2_grpc


class SynthesisConfig:
    def __init__(
        self, sample_rate: int = 16000, speed: float = 1.0, pitch: float = 0.0
    ):
        # Note: sample_rate is not in proto, but kept for API compatibility
        # Actual proto fields: speed, pitch, energy, prosody, enable_ssml
        self.sample_rate = sample_rate  # Stored but not sent to proto
        self.speed = speed
        self.pitch = pitch

    def to_proto(self) -> tts_pb2.SynthesisConfig:
        # Proto only has: speed, pitch, energy, prosody, enable_ssml
        return tts_pb2.SynthesisConfig(speed=self.speed, pitch=self.pitch)


class TextToSpeechClient:
    def __init__(self, channel: grpc.Channel):
        self._stub = tts_pb2_grpc.TextToSpeechStub(channel)

    async def synthesize(
        self,
        text: str,
        voice_id: str = "default",
        language: str = "en",
        config: Optional[SynthesisConfig] = None,
        timeout: Optional[float] = 30.0,
    ) -> bytes:
        cfg = (config or SynthesisConfig()).to_proto()
        request = tts_pb2.SynthesisRequest(
            text=text, config=cfg, voice_id=voice_id, language=language
        )
        response = await self._stub.Synthesize(request, timeout=timeout)
        return response.audio_data
