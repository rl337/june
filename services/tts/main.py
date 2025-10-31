from inference_core import TtsGrpcApp
from inference_core.tts.espeak_strategy import EspeakTtsStrategy


def main() -> None:
    import os
    strategy = EspeakTtsStrategy(
        sample_rate=int(os.getenv("TTS_SAMPLE_RATE", "16000"))
    )
    app = TtsGrpcApp(strategy)
    app.initialize()
    app.run()


if __name__ == "__main__":
    main()
