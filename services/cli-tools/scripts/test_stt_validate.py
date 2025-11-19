import os
import sys

import grpc
from june_grpc_api import asr as asr_shim

STT_ADDR = os.getenv("STT_ADDR", "stt:50052")


def main() -> None:
    channel = grpc.insecure_channel(STT_ADDR)
    client = asr_shim.SpeechToTextClient(channel)
    cfg = asr_shim.RecognitionConfig(language="en", interim_results=False)
    try:
        with open("/app/scripts/samples/hello.wav", "rb") as f:
            data = f.read()
    except FileNotFoundError:
        # Fallback: generate a 1s 440Hz tone at 16kHz
        import io
        import struct

        import numpy as np

        sr = 16000
        t = np.linspace(0, 1.0, int(sr), endpoint=False)
        tone = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        # Convert float32 [-1,1] to 16-bit PCM
        pcm = (np.clip(tone, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
        buf = io.BytesIO()
        # Write WAV header
        buf.write(b"RIFF")
        buf.write(struct.pack("<I", len(pcm) + 36))
        buf.write(b"WAVE")
        buf.write(b"fmt ")
        buf.write(struct.pack("<I", 16))
        buf.write(struct.pack("<HHIIHH", 1, 1, sr, sr * 2, 2, 16))
        buf.write(b"data")
        buf.write(struct.pack("<I", len(pcm)))
        buf.write(pcm)
        data = buf.getvalue()
    result = (
        client.recognize.__wrapped__(
            client,
            audio_data=data,
            sample_rate=16000,
            encoding="wav",
            config=cfg,
            timeout=30.0,
        )
        if hasattr(client.recognize, "__wrapped__")
        else None
    )
    if result is None:
        # If async, fallback to a simple print note (tool run context). Real validation uses validate_stt.sh with asyncio
        print("Shim constructed; async recognize to be exercised in integration tests.")
    else:
        print("Transcript:", result.transcript)


if __name__ == "__main__":
    main()
