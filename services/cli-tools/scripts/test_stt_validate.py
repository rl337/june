import os
import sys
import grpc

from june_grpc_api import asr_pb2, asr_pb2_grpc

STT_ADDR = os.getenv("STT_ADDR", "stt:50052")


def main() -> None:
    channel = grpc.insecure_channel(STT_ADDR)
    stub = asr_pb2_grpc.SpeechToTextStub(channel)
    cfg = asr_pb2.RecognitionConfig(language="en", interim_results=False)
    with open("/app/scripts/samples/hello.wav", "rb") as f:
        data = f.read()
    req = asr_pb2.RecognitionRequest(audio_data=data, sample_rate=16000, encoding="wav", config=cfg)
    resp = stub.Recognize(req, timeout=30.0)
    print("Transcript:", resp.results[0].transcript if resp.results else "")


if __name__ == "__main__":
    main()


