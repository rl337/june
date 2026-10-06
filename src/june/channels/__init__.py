"""Surface-agnostic chat intake shared by web (now) and TG/Discord (later)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


class Channel(str, Enum):
    WEBAPP = "webapp"
    TELEGRAM = "telegram"
    DISCORD = "discord"


class PartKind(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"


@dataclass
class ContentPart:
    kind: PartKind
    text: str | None = None
    url: str | None = None
    document_id: str | None = None
    media_type: str | None = None
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContentPart:
        payload = dict(data)
        payload["kind"] = PartKind(payload.get("kind", PartKind.TEXT.value))
        return cls(**{k: v for k, v in payload.items() if k in cls.__dataclass_fields__})

    @classmethod
    def text_part(cls, text: str) -> ContentPart:
        return cls(kind=PartKind.TEXT, text=text)


@dataclass
class ChannelMessage:
    channel: Channel
    session_id: str
    parts: list[ContentPart] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid4()))
    model: str | None = None
    user_ref: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def text(self) -> str:
        chunks = [p.text for p in self.parts if p.kind is PartKind.TEXT and p.text]
        return "\n".join(chunks).strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "channel": self.channel.value,
            "session_id": self.session_id,
            "parts": [p.to_dict() for p in self.parts],
            "model": self.model,
            "user_ref": self.user_ref,
            "history": self.history,
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChannelMessage:
        parts_raw = data.get("parts") or []
        if not parts_raw and data.get("text"):
            parts_raw = [{"kind": "text", "text": data["text"]}]
        return cls(
            id=str(data.get("id") or uuid4()),
            channel=Channel(data.get("channel", Channel.WEBAPP.value)),
            session_id=str(data.get("session_id") or "default"),
            parts=[ContentPart.from_dict(p) for p in parts_raw],
            model=data.get("model"),
            user_ref=data.get("user_ref"),
            history=list(data.get("history") or []),
            raw=dict(data.get("raw") or {}),
        )


@dataclass
class ChannelReply:
    parts: list[ContentPart] = field(default_factory=list)
    run_id: str | None = None
    model: str | None = None
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def text(self) -> str:
        chunks = [p.text for p in self.parts if p.kind is PartKind.TEXT and p.text]
        return "\n".join(chunks).strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "parts": [p.to_dict() for p in self.parts],
            "text": self.text(),
            "run_id": self.run_id,
            "model": self.model,
            "tool_trace": self.tool_trace,
            "notes": self.notes,
            "raw": self.raw,
        }


class ChatService:
    """Only conversational entrypoint for channel adapters."""

    def __init__(self, orchestrator: Any) -> None:
        self.orchestrator = orchestrator

    def handle(self, message: ChannelMessage) -> ChannelReply:
        reply = self.orchestrator.handle_chat(message)
        assert isinstance(reply, ChannelReply)
        return reply
