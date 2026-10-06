"""Incubating interactive ``june.chat`` subgraph (June-owned concrete topology)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from june.channels import ChannelMessage, ChannelReply, ContentPart, PartKind
from june.config import ChatSettings, JuneSettings
from june.documents import DocumentStore
from june.knowledge import KnowledgeGraph
from june.providers.junespark import JunesparkProvider, ModelCapabilities
from june.tools import ToolRegistry

CHAT_TEMPLATE = "june.chat"
CHAT_NODE_KINDS = [
    "june.chat.refine_input",
    "june.chat.context_optimize",
    "june.chat.tool_loop",
    "june.chat.render_reply",
]


@dataclass
class ChatGraphState:
    message: ChannelMessage
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    model: str | None = None
    notes: list[str] = field(default_factory=list)
    context_refs: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    assistant_text: str = ""
    reply_parts: list[ContentPart] = field(default_factory=list)
    run_id: str = field(default_factory=lambda: str(uuid4()))


class ChatGraphRunner:
    """Execute refine → context → tool_loop → render for one conversational turn."""

    def __init__(
        self,
        *,
        provider: JunesparkProvider,
        tools: ToolRegistry,
        settings: JuneSettings | None = None,
        documents: DocumentStore | None = None,
        knowledge: KnowledgeGraph | None = None,
    ) -> None:
        self.provider = provider
        self.tools = tools
        self.settings = settings or JuneSettings()
        self.chat: ChatSettings = self.settings.chat
        self.documents = documents
        self.knowledge = knowledge

    def run(
        self,
        message: ChannelMessage,
        *,
        on_phase: Any | None = None,
    ) -> ChannelReply:
        state = ChatGraphState(message=message)
        phases = (
            ("refine", self.refine_input),
            ("context", self.context_optimize),
            ("tools", self.tool_loop),
            ("render", self.render_reply),
        )
        for phase, fn in phases:
            if on_phase is not None:
                on_phase(phase, state)
            fn(state)
        return ChannelReply(
            parts=state.reply_parts,
            run_id=state.run_id,
            model=state.model,
            tool_trace=state.tool_trace,
            notes=state.notes,
            raw={"template": CHAT_TEMPLATE, "node_kinds": list(CHAT_NODE_KINDS)},
        )

    def refine_input(self, state: ChatGraphState) -> None:
        preferred = state.message.model or self.provider.default_model
        try:
            selected = self.provider.select_model(preferred)
            if selected is not None:
                state.model = selected.id
                state.capabilities = selected.capabilities
            else:
                state.model = preferred
                state.capabilities = self.provider.probe_capabilities(preferred)
        except Exception as exc:  # noqa: BLE001
            state.notes.append(f"model discovery failed: {exc}")
            state.model = preferred
            state.capabilities = ModelCapabilities(tools=False, vision=False)

        refined_parts: list[ContentPart] = []
        max_bytes = self.chat.max_part_bytes
        for part in state.message.parts:
            if part.kind is PartKind.TEXT:
                text = (part.text or "").strip()
                if text:
                    refined_parts.append(ContentPart.text_part(text))
                continue
            if part.kind is PartKind.IMAGE and not state.capabilities.vision:
                label = part.name or part.document_id or part.url or "image"
                state.notes.append(
                    f"model lacks vision; image omitted ({label}). "
                    "Describe the image in text or load a vision-capable model."
                )
                refined_parts.append(
                    ContentPart.text_part(f"[user attached image: {label}]")
                )
                continue
            # Size guard for inline/data URLs
            blob = part.url or ""
            if len(blob.encode("utf-8", errors="ignore")) > max_bytes:
                state.notes.append(f"oversized {part.kind.value} part stripped")
                continue
            refined_parts.append(part)

        if not refined_parts:
            refined_parts = [ContentPart.text_part(state.message.text() or "")]
        state.message.parts = refined_parts

    def context_optimize(self, state: ChatGraphState) -> None:
        query = state.message.text()
        refs: list[dict[str, Any]] = []
        if self.documents is not None:
            refs.extend(self.documents.as_context_items(query, limit=3))
        if self.knowledge is not None:
            refs.extend(self.knowledge.scoped_context())
        state.context_refs = refs

        # Approximate token budget by character budget (~4 chars/token).
        char_budget = max(500, self.chat.context_token_budget * 4)
        system_bits = [self.chat.system_prompt]
        if refs:
            compact = json.dumps(refs)[: char_budget // 4]
            system_bits.append(f"Retrieved context (truncated if needed):\n{compact}")
        if state.notes:
            system_bits.append("Notes:\n" + "\n".join(state.notes))

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "\n\n".join(system_bits)}
        ]

        # Prior history (already channel-normalized dict messages).
        used = sum(len(json.dumps(m)) for m in messages)
        for item in state.message.history:
            encoded = json.dumps(item)
            if used + len(encoded) > char_budget:
                state.notes.append("older history truncated for context budget")
                break
            messages.append(item)
            used += len(encoded)

        messages.append({"role": "user", "content": self._user_content(state)})
        state.messages = messages

    def tool_loop(self, state: ChatGraphState) -> None:
        if not state.model:
            state.assistant_text = "No model available on junespark."
            return

        use_tools = state.capabilities.tools and bool(self.tools.specs())
        tool_schemas = self.tools.openai_tools() if use_tools else None
        if not use_tools:
            state.notes.append("tool loop disabled (no tools or model lacks tools)")

        messages = list(state.messages)
        max_turns = max(1, self.chat.max_tool_turns)
        assistant_text = ""

        for _ in range(max_turns):
            try:
                response = self.provider.complete(
                    messages,
                    model=state.model,
                    tools=tool_schemas,
                )
            except Exception as exc:  # noqa: BLE001
                state.notes.append(f"inference failed: {exc}")
                assistant_text = f"Inference error: {exc}"
                break

            message = self.provider.extract_assistant(response)
            messages.append(message)
            tool_calls = message.get("tool_calls") or []
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                assistant_text = content
            elif isinstance(content, list):
                texts = [
                    str(p.get("text"))
                    for p in content
                    if isinstance(p, dict) and p.get("type") == "text" and p.get("text")
                ]
                if texts:
                    assistant_text = "\n".join(texts)

            if not tool_calls or not use_tools:
                break

            for call in tool_calls:
                fn = call.get("function") or {}
                name = str(fn.get("name") or "")
                args = fn.get("arguments")
                result = self.tools.call(name, args)
                state.tool_trace.append(
                    {"id": call.get("id"), "name": name, "arguments": args, "result": result}
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "content": result,
                    }
                )

        state.messages = messages
        state.assistant_text = assistant_text or "(empty model response)"

    def render_reply(self, state: ChatGraphState) -> None:
        parts: list[ContentPart] = [ContentPart.text_part(state.assistant_text)]
        # Future media tools can append image/audio/video parts here.
        for entry in state.tool_trace:
            result = entry.get("result")
            if not isinstance(result, str):
                continue
            try:
                payload = json.loads(result)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            media = payload.get("media")
            if isinstance(media, dict):
                kind = PartKind(media.get("kind", PartKind.FILE.value))
                parts.append(
                    ContentPart(
                        kind=kind,
                        url=media.get("url"),
                        document_id=media.get("document_id"),
                        media_type=media.get("media_type"),
                        name=media.get("name"),
                    )
                )
        state.reply_parts = parts

    def _user_content(self, state: ChatGraphState) -> str | list[dict[str, Any]]:
        parts = state.message.parts
        text_only = all(p.kind is PartKind.TEXT for p in parts)
        if text_only:
            return state.message.text()

        content: list[dict[str, Any]] = []
        for part in parts:
            if part.kind is PartKind.TEXT and part.text:
                content.append({"type": "text", "text": part.text})
            elif part.kind is PartKind.IMAGE:
                url = part.url
                if not url and part.document_id and self.documents is not None:
                    loaded = self.documents.load(part.document_id)
                    if loaded is not None:
                        _ref, payload = loaded
                        # Stored as data URL or raw base64.
                        if payload.startswith("data:"):
                            url = payload
                        else:
                            media = part.media_type or "image/png"
                            url = f"data:{media};base64,{payload}"
                if url:
                    content.append({"type": "image_url", "image_url": {"url": url}})
                elif part.text:
                    content.append({"type": "text", "text": part.text})
            else:
                label = part.name or part.document_id or part.kind.value
                content.append({"type": "text", "text": f"[attached {part.kind.value}: {label}]"})
        return content or state.message.text()


def execute_chat_graph(
    message: ChannelMessage,
    *,
    provider: JunesparkProvider,
    tools: ToolRegistry,
    settings: JuneSettings | None = None,
    documents: DocumentStore | None = None,
    knowledge: KnowledgeGraph | None = None,
) -> ChannelReply:
    return ChatGraphRunner(
        provider=provider,
        tools=tools,
        settings=settings,
        documents=documents,
        knowledge=knowledge,
    ).run(message)
