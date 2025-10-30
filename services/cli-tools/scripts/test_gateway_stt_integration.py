import os
import json
from pathlib import Path
import httpx


def load_pairs(index_path: Path):
    data = json.load(open(index_path, "r", encoding="utf-8"))
    return data.get("pairs", [])


def main() -> int:
    data_dir = Path(os.environ.get("JUNE_DATA_DIR", "/data"))
    index = data_dir / "datasets" / "librispeech_small" / "index.json"
    if not index.exists():
        print("Dataset not found. Run download_librispeech_small.py first.")
        return 1

    pairs = load_pairs(index)[:5]
    gw_url = os.environ.get("GATEWAY_URL", "http://gateway:8000")
    ok = 0
    with httpx.Client(timeout=30.0) as client:
        for i, item in enumerate(pairs, 1):
            audio_path = Path(item["audio"]).with_suffix(".wav")
            # If wav not present, skip (we used in-memory before; here just smoke test)
            if not audio_path.exists():
                # fallback: submit flac bytes
                audio_path = Path(item["audio"]) 
            files = {"audio": (audio_path.name, open(audio_path, "rb"), "audio/wav")}
            r = client.post(f"{gw_url}/api/v1/audio/transcribe", files=files)
            if r.status_code != 200:
                print(f"[{i}] HTTP {r.status_code}: {r.text}")
                continue
            resp = r.json()
            hyp = (resp.get("transcript") or "").lower().strip()
            ref = item["text"].lower().strip()
            print(f"[{i}] REF: {ref[:80]}\n      HYP: {hyp[:80]}\n")
            if hyp:
                ok += 1
    print(f"Gateway->STT non-empty transcripts: {ok}/{len(pairs)}")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())


