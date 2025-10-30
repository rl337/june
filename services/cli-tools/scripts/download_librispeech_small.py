import os
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlretrieve
import json

DATA_DIR = Path(os.environ.get("JUNE_DATA_DIR", "/data")) / "datasets" / "librispeech_small"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Use a small sample archive (dev-clean subset with few files). If not available, point to test-clean and limit.
URL = os.environ.get(
    "LIBRISPEECH_URL",
    "https://www.openslr.org/resources/12/test-clean.tar.gz",
)


def main() -> None:
    archive_path = DATA_DIR / "test-clean.tar.gz"
    if not archive_path.exists():
        print(f"Downloading {URL} -> {archive_path}")
        urlretrieve(URL, archive_path)

    print("Extracting archive (subset)...")
    with tarfile.open(archive_path, "r:gz") as tf:
        members = [m for m in tf.getmembers() if m.isfile() and (m.name.endswith(".flac") or m.name.endswith(".txt"))]
        # Limit extraction for speed
        limited = members[:200]
        tf.extractall(DATA_DIR, limited)

    # Build an index of audio->text pairs (limit ~20 samples)
    pairs = []
    for txt in DATA_DIR.rglob("*.txt"):
        # Each txt contains multiple utterances mapping
        with open(txt, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                utt_id, *words = line.split(" ")
                transcript = " ".join(words)
                # audio path has same prefix with .flac extension
                audio = None
                for cand in txt.parent.glob(f"{utt_id}.flac"):
                    audio = cand
                    break
                if audio and audio.exists():
                    pairs.append({"id": utt_id, "audio": str(audio), "text": transcript})
                if len(pairs) >= 20:
                    break
        if len(pairs) >= 20:
            break

    index_file = DATA_DIR / "index.json"
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump({"pairs": pairs}, f, indent=2)

    print(f"Wrote {len(pairs)} pairs to {index_file}")


if __name__ == "__main__":
    main()


