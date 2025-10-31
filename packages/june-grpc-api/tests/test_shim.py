import grpc

from june_grpc_api import asr, tts, llm


def test_asr_shim_constructs():
    ch = grpc.insecure_channel("localhost:9")  # blackhole port; just construct stub
    client = asr.SpeechToTextClient(ch)
    assert client is not None


def test_tts_shim_constructs():
    ch = grpc.insecure_channel("localhost:9")
    client = tts.TextToSpeechClient(ch)
    assert client is not None


def test_llm_shim_constructs():
    ch = grpc.insecure_channel("localhost:9")
    client = llm.LLMClient(ch)
    assert client is not None




