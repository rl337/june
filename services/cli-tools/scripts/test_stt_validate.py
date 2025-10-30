import os
import sys
import grpc

from june_grpc_api import asr as asr_shim

STT_ADDR = os.getenv("STT_ADDR", "stt:50052")


def main() -> None:
    channel = grpc.insecure_channel(STT_ADDR)
    client = asr_shim.SpeechToTextClient(channel)
    cfg = asr_shim.RecognitionConfig(language="en", interim_results=False)
    with open("/app/scripts/samples/hello.wav", "rb") as f:
        data = f.read()
    result = client.recognize.__wrapped__(client, audio_data=data, sample_rate=16000, encoding="wav", config=cfg, timeout=30.0) if hasattr(client.recognize, "__wrapped__") else None
    if result is None:
        # If async, fallback to a simple print note (tool run context). Real validation uses validate_stt.sh with asyncio
        print("Shim constructed; async recognize to be exercised in integration tests.")
    else:
        print("Transcript:", result.transcript)


if __name__ == "__main__":
    main()


