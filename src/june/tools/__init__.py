"""Small June tool registry for the interactive chat subgraph."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from june.documents import DocumentStore
from june.knowledge import KnowledgeGraph


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    handler: Callable[[dict[str, Any]], str] | None = None

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
                or {"type": "object", "properties": {}, "additionalProperties": False},
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def specs(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def openai_tools(self) -> list[dict[str, Any]]:
        return [t.openai_schema() for t in self._tools.values()]

    def call(self, name: str, arguments: dict[str, Any] | str | None = None) -> str:
        spec = self._tools.get(name)
        if spec is None or spec.handler is None:
            return json.dumps({"error": f"unknown tool: {name}"})
        args: dict[str, Any]
        if arguments is None:
            args = {}
        elif isinstance(arguments, str):
            try:
                parsed = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                parsed = {"raw": arguments}
            args = parsed if isinstance(parsed, dict) else {"raw": parsed}
        else:
            args = arguments
        try:
            return spec.handler(args)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})


def build_default_tools(
    *,
    documents: DocumentStore | None = None,
    knowledge: KnowledgeGraph | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()

    def status(_args: dict[str, Any]) -> str:
        return json.dumps(
            {
                "ok": True,
                "utc": datetime.now(timezone.utc).isoformat(),
                "service": "june",
            }
        )

    registry.register(
        ToolSpec(
            name="june_status",
            description="Return June orchestrator status clock and health ping.",
            handler=status,
        )
    )

    if documents is not None:

        def doc_search(args: dict[str, Any]) -> str:
            query = str(args.get("query") or "")
            items = documents.as_context_items(query, limit=int(args.get("limit") or 5))
            return json.dumps({"documents": items})

        registry.register(
            ToolSpec(
                name="document_search",
                description="Search June document index by query string.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                },
                handler=doc_search,
            )
        )

    if knowledge is not None:

        def kg_lookup(args: dict[str, Any]) -> str:
            subject = args.get("subject")
            facts = knowledge.scoped_context(subject=str(subject) if subject else None)
            return json.dumps({"facts": facts[: int(args.get("limit") or 10)]})

        registry.register(
            ToolSpec(
                name="knowledge_lookup",
                description="Lookup scoped knowledge-graph facts for a subject.",
                parameters={
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                },
                handler=kg_lookup,
            )
        )

    return registry
