from inference_core import SttGrpcApp
from inference_core.stt.whisper_strategy import WhisperSttStrategy


def main() -> None:
    strategy = WhisperSttStrategy(
        model_name=os.getenv("STT_MODEL_NAME", "base.en"),  # Upgraded from tiny.en for better accuracy
        device=os.getenv("STT_DEVICE", "cpu"),
    )
    app = SttGrpcApp(strategy)
    app.initialize()
    app.run()


if __name__ == "__main__":
    import os
    main()


