from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class InferenceRequest:
    payload: Any
    metadata: Dict[str, Any]


@dataclass
class InferenceResponse:
    payload: Any
    metadata: Dict[str, Any]


class InferenceStrategy(ABC):
    @abstractmethod
    def warmup(self) -> None:
        ...

    @abstractmethod
    def infer(self, request: InferenceRequest) -> InferenceResponse:
        ...


class SttStrategy(InferenceStrategy, ABC):
    """Speech-to-Text contract.

    Input payload: bytes (PCM/encoded audio)
    Output payload: str (transcript)
    """


class TtsStrategy(InferenceStrategy, ABC):
    """Text-to-Speech contract.

    Input payload: str (text)
    Output payload: bytes (PCM WAV data)
    """


class LlmStrategy(InferenceStrategy, ABC):
    """LLM contract.

    Input payload: dict {prompt: str, params: dict}
    Output payload: dict {text: str, tokens: Optional[int]}
    """


