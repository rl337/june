"""Template incubation — June-local workflows before MechaHarness promotion."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from june.persist import JsonStore


class TemplateStatus(str, Enum):
    INCUBATING = "incubating"
    CANDIDATE = "candidate"
    PROMOTED = "promoted"
    RETIRED = "retired"


@dataclass
class SoftPoint:
    name: str
    description: str
    june_owned: bool = True


@dataclass
class GraphTemplateSpec:
    """June-owned concrete or incubating workflow pattern."""

    name: str
    description: str
    id: str = field(default_factory=lambda: str(uuid4()))
    status: TemplateStatus = TemplateStatus.INCUBATING
    node_kinds: list[str] = field(default_factory=lambda: ["june.task"])
    soft_points: list[dict[str, Any]] = field(default_factory=list)
    usage_count: int = 0
    mechaharness_template: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphTemplateSpec:
        payload = dict(data)
        payload["status"] = TemplateStatus(payload.get("status", TemplateStatus.INCUBATING.value))
        return cls(**{k: v for k, v in payload.items() if k in cls.__dataclass_fields__})


class TemplateRegistry:
    """Evidence-driven incubation and promotion ledger."""

    def __init__(self, store: JsonStore | None = None) -> None:
        self._templates: dict[str, GraphTemplateSpec] = {}
        self._store = store
        self.register(
            GraphTemplateSpec(
                name="direct",
                description="Single-node direct task realization",
                status=TemplateStatus.INCUBATING,
                node_kinds=["june.task"],
                soft_points=[asdict(SoftPoint("bindings", "June task bindings"))],
            )
        )

    def register(self, spec: GraphTemplateSpec) -> GraphTemplateSpec:
        self._templates[spec.name] = spec
        if self._store is not None:
            self._store.put_item("templates", spec.name, spec.to_dict())
        return spec

    def get(self, name: str) -> GraphTemplateSpec | None:
        if name in self._templates:
            return self._templates[name]
        if self._store is None:
            return None
        raw = self._store.get_item("templates", name)
        if raw is None:
            return None
        spec = GraphTemplateSpec.from_dict(raw)
        self._templates[spec.name] = spec
        return spec

    def record_use(self, name: str) -> GraphTemplateSpec | None:
        spec = self.get(name)
        if spec is None:
            return None
        spec.usage_count += 1
        if spec.status is TemplateStatus.INCUBATING and spec.usage_count >= 3:
            spec.status = TemplateStatus.CANDIDATE
            spec.provenance["promotion_review"] = "usage_threshold"
        return self.register(spec)

    def mark_promoted(self, name: str, *, mechaharness_template: str) -> GraphTemplateSpec | None:
        spec = self.get(name)
        if spec is None:
            return None
        spec.status = TemplateStatus.PROMOTED
        spec.mechaharness_template = mechaharness_template
        spec.provenance["promoted_at"] = datetime.now(timezone.utc).isoformat()
        return self.register(spec)

    def demote_to_june(self, name: str, *, reason: str) -> GraphTemplateSpec | None:
        spec = self.get(name)
        if spec is None:
            return None
        spec.status = TemplateStatus.INCUBATING
        spec.mechaharness_template = None
        spec.provenance["demoted_reason"] = reason
        return self.register(spec)

    def list(self, *, status: TemplateStatus | None = None) -> list[GraphTemplateSpec]:
        if self._store is not None:
            for raw in self._store.list_items("templates"):
                spec = GraphTemplateSpec.from_dict(raw)
                self._templates.setdefault(spec.name, spec)
        specs = list(self._templates.values())
        if status is not None:
            specs = [s for s in specs if s.status is status]
        return specs

    def candidates_for_promotion(self) -> list[GraphTemplateSpec]:
        return self.list(status=TemplateStatus.CANDIDATE)
