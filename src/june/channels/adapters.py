"""Thin channel adapters: transport ↔ ChannelMessage / ChannelReply."""

from __future__ import annotations

from typing import Any, Protocol

from june.channels import Channel, ChannelMessage, ChannelReply, ContentPart, PartKind


class ChannelAdapter(Protocol):
    channel: Channel

    def to_message(self, raw: dict[str, Any]) -> ChannelMessage: ...

    def from_reply(self, reply: ChannelReply) -> dict[str, Any]: ...


class WebappAdapter:
    """Console / webapp JSON body shape (also used by REST)."""

    channel = Channel.WEBAPP

    def to_message(self, raw: dict[str, Any]) -> ChannelMessage:
        parts_raw = list(raw.get("parts") or [])
        text = raw.get("text")
        parts = [ContentPart.from_dict(p) for p in parts_raw]
        if text and not any(p.kind is PartKind.TEXT and p.text == text for p in parts):
            parts.insert(0, ContentPart.text_part(str(text)))
        if not parts:
            raise ValueError("empty chat message")
        return ChannelMessage(
            channel=self.channel,
            session_id=str(raw.get("session_id") or "default"),
            parts=parts,
            model=raw.get("model"),
            user_ref=raw.get("user_ref"),
            history=list(raw.get("history") or []),
            raw=dict(raw.get("raw") or {}),
        )

    def from_reply(self, reply: ChannelReply) -> dict[str, Any]:
        return reply.to_dict()


class RestChatAdapter(WebappAdapter):
    """REST front: same DTO as webapp; marks channel as WEBAPP (API surface)."""

    # Reuse WEBAPP until a dedicated Channel.API is needed by product policy.


class TelegramAdapter:
    """Stub — poller/intake not implemented (no voice / Switchboard)."""

    channel = Channel.TELEGRAM

    def to_message(self, raw: dict[str, Any]) -> ChannelMessage:
        raise NotImplementedError("Telegram adapter not implemented")

    def from_reply(self, reply: ChannelReply) -> dict[str, Any]:
        raise NotImplementedError("Telegram adapter not implemented")


class DiscordAdapter:
    """Stub — poller/intake not implemented (no voice / Switchboard)."""

    channel = Channel.DISCORD

    def to_message(self, raw: dict[str, Any]) -> ChannelMessage:
        raise NotImplementedError("Discord adapter not implemented")

    def from_reply(self, reply: ChannelReply) -> dict[str, Any]:
        raise NotImplementedError("Discord adapter not implemented")


def adapter_for(channel: Channel | str) -> ChannelAdapter:
    key = Channel(channel) if not isinstance(channel, Channel) else channel
    mapping: dict[Channel, ChannelAdapter] = {
        Channel.WEBAPP: WebappAdapter(),
        Channel.TELEGRAM: TelegramAdapter(),
        Channel.DISCORD: DiscordAdapter(),
    }
    return mapping[key]
