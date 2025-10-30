from __future__ import annotations

import logging
from typing import Optional

from .strategies import InferenceStrategy, InferenceRequest, InferenceResponse


class InferenceApp:
    """Minimal runtime wrapper to host a Strategy.

    Each service binds its own transport (gRPC/FastAPI) and delegates
    request handling to the provided Strategy.
    """

    def __init__(self, strategy: InferenceStrategy, logger: Optional[logging.Logger] = None) -> None:
        self.strategy = strategy
        self.logger = logger or logging.getLogger("inference-core")

    def warmup(self) -> None:
        self.logger.info("warming up strategy %s", self.strategy.__class__.__name__)
        self.strategy.warmup()

    def handle(self, request: InferenceRequest) -> InferenceResponse:
        return self.strategy.infer(request)



