from inference_core import LlmGrpcApp
from inference_core.llm.passthrough_strategy import PassthroughLlmStrategy


def main() -> None:
    strategy = PassthroughLlmStrategy()
    app = LlmGrpcApp(strategy)
    app.initialize()
    app.run()


if __name__ == "__main__":
    main()
