"""Serialize MechaHarness / console events for the event-log view."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def serialize_event(event: Any) -> dict[str, Any]:
    ts = getattr(event, "ts", None)
    if isinstance(ts, datetime):
        ts_str = ts.isoformat()
    else:
        ts_str = str(ts) if ts is not None else ""

    payload = getattr(event, "payload", None)
    payload_dict = dict(payload) if isinstance(payload, dict) else {}

    etype = str(getattr(event, "type", ""))
    summary = _summarize(etype, payload_dict)

    return {
        "ts": ts_str,
        "type": etype,
        "run_id": str(getattr(event, "run_id", "")),
        "agent_id": str(getattr(event, "agent_id", "")),
        "node_id": payload_dict.get("node_id"),
        "kind": payload_dict.get("kind"),
        "status": payload_dict.get("status"),
        "summary": summary,
        "payload": payload_dict,
    }


def serialize_journal_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "ts": entry.get("ts", ""),
        "type": entry.get("type", "june.console.log"),
        "run_id": entry.get("run_id", ""),
        "agent_id": entry.get("agent_id", "june"),
        "node_id": entry.get("node_id"),
        "kind": entry.get("kind", "june.event_log"),
        "status": entry.get("status"),
        "summary": entry.get("summary") or entry.get("message", ""),
        "payload": entry,
    }


def _summarize(etype: str, payload: dict[str, Any]) -> str:
    if etype == "core:graph_node_start":
        return f"start {payload.get('kind', '?')} node {payload.get('node_id', '?')}"
    if etype == "core:graph_node_end":
        return (
            f"end {payload.get('kind', '?')} node {payload.get('node_id', '?')} "
            f"→ {payload.get('status', '?')}"
        )
    if etype == "core:graph_start":
        return f"graph start ({payload.get('node_count', '?')} nodes)"
    if etype == "core:graph_end":
        return f"graph end → {payload.get('status', '?')}"
    if etype == "core:graph_node":
        return "graph checkpoint"
    if etype == "june.console.log":
        return str(payload.get("message", payload.get("summary", "log")))
    return etype
