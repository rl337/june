from __future__ import annotations

import logging
from typing import Dict, Any

from ..strategies import LlmStrategy, InferenceRequest, InferenceResponse

logger = logging.getLogger(__name__)


class PassthroughLlmStrategy(LlmStrategy):
    def warmup(self) -> None:
        logger.info("Passthrough LLM initialized")

    def infer(self, request: InferenceRequest | Dict[str, Any]) -> InferenceResponse:
        if isinstance(request, dict):
            prompt = request.get("prompt", "")
            params = request.get("params", {})
        else:
            payload = request.payload
            if isinstance(payload, dict):
                prompt = payload.get("prompt", "")
                params = payload.get("params", {})
            else:
                prompt = str(payload)
                params = {}
        
        text = f"[passthrough] {prompt}"
        return InferenceResponse(
            payload={"text": text, "tokens": None},
            metadata={}
        )

