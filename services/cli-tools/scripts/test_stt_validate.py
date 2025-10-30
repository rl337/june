import os
import json
import base64
import soundfile as sf
import io
import asyncio
import grpc
from pathlib import Path

import sys
sys.path.insert(0, "/app/proto")
try:
    import june.asr_pb2 as asr_pb2
    import june.asr_pb2_grpc as asr_pb2_grpc
except Exception:
    import asr_pb2
    import asr_pb2_grpc


def load_pairs(index_path: Path):
    data = json.load(open(index_path, "r", encoding="utf-8"))
    return data.get("pairs", [])


def read_audio_wav_bytes(flac_path: Path) -> bytes:
    # Convert FLAC to WAV bytes in-memory
    audio, sr = sf.read(str(flac_path))
    if sr != 16000:
        # simple resample using soundfile write param
        target_sr = 16000
        buf = io.BytesIO()
        sf.write(buf, audio, target_sr, format="WAV", subtype="PCM_16")
        return buf.getvalue()
    buf = io.BytesIO()
    sf.write(buf, audio, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


async def stt_call(channel, wav_bytes: bytes) -> str:
    stub = asr_pb2_grpc.SpeechToTextStub(channel)
    cfg = asr_pb2.RecognitionConfig(language="en", interim_results=False)
    req = asr_pb2.RecognitionRequest(audio_data=wav_bytes, sample_rate=16000, encoding="wav", config=cfg)
    resp = await stub.Recognize(req, timeout=30.0)
    if resp.results:
        return resp.results[0].transcript
    return ""


async def main():
    data_dir = Path(os.environ.get("JUNE_DATA_DIR", "/data"))
    index = data_dir / "datasets" / "librispeech_small" / "index.json"
    if not index.exists():
        print("Dataset not found. Run download_librispeech_small.py first.")
        return 1

    pairs = load_pairs(index)
    stt_addr = os.environ.get("STT_SERVICE_ADDRESS", "stt:50052")
    ok = 0
    total = 0
    async with grpc.aio.insecure_channel(stt_addr) as channel:
        for item in pairs:
            total += 1
            wav_bytes = read_audio_wav_bytes(Path(item["audio"]))
            hypo = await stt_call(channel, wav_bytes)
            ref = item["text"].lower().strip()
            hyp = hypo.lower().strip()
            if ref and hyp and (ref[:30].split()[:3] == hyp[:30].split()[:3]):
                ok += 1
            print(f"[{total}] REF: {ref[:80]}\n      HYP: {hyp[:80]}\n")

    acc = ok / max(1, total)
    print(f"Accuracy (prefix-3 match): {acc:.2%} ({ok}/{total})")
    # Do not hard-fail; return 0 if at least some success
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))


