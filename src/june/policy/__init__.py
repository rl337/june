"""Orchestration and autonomy policy owned by June."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from june.persist import JsonStore


class Consequence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class PolicyRule:
    name: str
    failure_mode: str
    actions: list[str]
    consequence: Consequence = Consequence.MEDIUM
    require_approval: bool = False
    restricted_capabilities: list[str] = field(default_factory=list)
    enabled: bool = True


@dataclass
class PolicyDecision:
    allow: bool
    require_approval: bool
    consequence: Consequence
    reason: str
    restricted_capabilities: list[str] = field(default_factory=list)
    grants: list[str] = field(default_factory=list)
    postponed: bool = False


@dataclass
class AutonomyMetric:
    kind: str
    at: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestrationPolicy:
    """Versioned product policy; removable without changing MechaHarness primitives."""

    version: str = "0.1.0"
    id: str = field(default_factory=lambda: str(uuid4()))
    rules: list[PolicyRule] = field(default_factory=list)
    metrics: list[AutonomyMetric] = field(default_factory=list)
    retired_rules: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.rules:
            self.rules = [
                PolicyRule(
                    name="external_side_effect",
                    failure_mode="unapproved irreversible external action",
                    actions=["external_side_effect", "deploy", "delete"],
                    consequence=Consequence.HIGH,
                    require_approval=True,
                    restricted_capabilities=["network_write", "filesystem_write"],
                ),
                PolicyRule(
                    name="goal_mutation",
                    failure_mode="untracked consequential goal change",
                    actions=["goal_mutation"],
                    consequence=Consequence.HIGH,
                    require_approval=True,
                ),
                PolicyRule(
                    name="default_allow",
                    failure_mode="over-interruption of low-risk work",
                    actions=["*"],
                    consequence=Consequence.LOW,
                    require_approval=False,
                    restricted_capabilities=[],
                ),
            ]

    def classify(self, action: str, *, user_intent: str = "") -> PolicyDecision:
        del user_intent
        for rule in self.rules:
            if not rule.enabled:
                continue
            if action in rule.actions or "*" in rule.actions:
                grants = ["core:graph.execute"]
                if not rule.require_approval:
                    grants.extend(rule.restricted_capabilities)
                return PolicyDecision(
                    allow=True,
                    require_approval=rule.require_approval,
                    consequence=rule.consequence,
                    reason=f"rule '{rule.name}' ({rule.failure_mode}) policy={self.version}",
                    restricted_capabilities=list(rule.restricted_capabilities),
                    grants=grants,
                )
        return PolicyDecision(
            allow=False,
            require_approval=True,
            consequence=Consequence.CRITICAL,
            reason=f"no matching rule for '{action}'",
            postponed=True,
        )

    def record_metric(self, kind: str, **detail: Any) -> None:
        self.metrics.append(
            AutonomyMetric(
                kind=kind,
                at=datetime.now(timezone.utc).isoformat(),
                detail=detail,
            )
        )

    def retire_rule(self, name: str) -> bool:
        for rule in self.rules:
            if rule.name == name:
                rule.enabled = False
                self.retired_rules.append(name)
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "rules": [asdict(r) | {"consequence": r.consequence.value} for r in self.rules],
            "metrics": [asdict(m) for m in self.metrics],
            "retired_rules": self.retired_rules,
        }


class PolicyStore:
    def __init__(self, store: JsonStore | None = None) -> None:
        self._store = store
        self._policies: dict[str, OrchestrationPolicy] = {}
        self.active = OrchestrationPolicy()

    def save_active(self) -> OrchestrationPolicy:
        self._policies[self.active.version] = self.active
        if self._store is not None:
            self._store.put_item("policies", self.active.version, self.active.to_dict())
        return self.active

    def compare(self, left_version: str, right_version: str) -> dict[str, Any]:
        left = self._policies.get(left_version)
        right = self._policies.get(right_version)
        return {
            "left": None if left is None else left.to_dict(),
            "right": None if right is None else right.to_dict(),
            "retired_delta": list(
                set(right.retired_rules if right else [])
                - set(left.retired_rules if left else [])
            ),
        }
