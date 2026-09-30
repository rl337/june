"""Orchestration and autonomy policy owned by June."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Consequence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class PolicyDecision:
    allow: bool
    require_approval: bool
    consequence: Consequence
    reason: str
    restricted_capabilities: list[str] = field(default_factory=list)


@dataclass
class OrchestrationPolicy:
    """Versioned product policy; removable without changing MechaHarness primitives."""

    version: str = "0.1.0"
    rules: dict[str, Any] = field(default_factory=dict)

    def classify(self, action: str, *, user_intent: str = "") -> PolicyDecision:
        high_risk = {"external_side_effect", "goal_mutation", "delete", "deploy"}
        if action in high_risk:
            return PolicyDecision(
                allow=True,
                require_approval=True,
                consequence=Consequence.HIGH,
                reason=f"action '{action}' requires approval",
                restricted_capabilities=["network_write", "filesystem_write"],
            )
        return PolicyDecision(
            allow=True,
            require_approval=False,
            consequence=Consequence.LOW,
            reason=f"action '{action}' permitted under policy {self.version}",
        )
