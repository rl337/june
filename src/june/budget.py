"""June-owned budget selection for MechaHarness subgraph executions.

The control graph is the base operating layer and is not budget-capped.
Spawned MechaHarness runs MUST receive a ``BudgetPolicy`` that the harness
enforces (soft wind-down / hard fail). June chooses the policy; MechaHarness
owns the ledger and enforcement.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from june.policy import Consequence, PolicyDecision


@dataclass(frozen=True)
class SubgraphBudget:
    """Mirror of mechaharness.budget.BudgetPolicy for June-side selection."""

    soft_limit: float | None = None
    hard_limit: float | None = 64.0
    unit: Literal["units", "usd", "tokens"] = "units"

    @classmethod
    def unlimited(cls) -> SubgraphBudget:
        """Only for the control graph / explicit unlimited child runs."""
        return cls(soft_limit=None, hard_limit=None)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_mechaharness(self) -> Any:
        """Build the real MechaHarness BudgetPolicy when the package is installed."""
        from mechaharness.budget import BudgetPolicy

        return BudgetPolicy(
            soft_limit=self.soft_limit,
            hard_limit=self.hard_limit,
            unit=self.unit,
        )


# Consequence → default subgraph spend ceilings (abstract MH cost units).
_DEFAULT_BY_CONSEQUENCE: dict[Consequence, SubgraphBudget] = {
    Consequence.LOW: SubgraphBudget(soft_limit=16.0, hard_limit=32.0),
    Consequence.MEDIUM: SubgraphBudget(soft_limit=32.0, hard_limit=64.0),
    Consequence.HIGH: SubgraphBudget(soft_limit=64.0, hard_limit=128.0),
    Consequence.CRITICAL: SubgraphBudget(soft_limit=8.0, hard_limit=16.0),
}


def budget_for_decision(
    decision: PolicyDecision,
    *,
    override: SubgraphBudget | None = None,
) -> SubgraphBudget:
    """Select the MechaHarness budget policy for a child graph run."""
    if override is not None:
        return override
    return _DEFAULT_BY_CONSEQUENCE.get(decision.consequence, SubgraphBudget())


def budget_from_payload(payload: dict[str, Any] | None) -> SubgraphBudget | None:
    """Optional explicit budget on execute_work / wake payloads."""
    if not payload:
        return None
    raw = payload.get("budget_policy") or payload.get("budget")
    if not isinstance(raw, dict):
        return None
    unit = raw.get("unit", "units")
    if unit not in ("units", "usd", "tokens"):
        unit = "units"
    return SubgraphBudget(
        soft_limit=raw.get("soft_limit"),
        hard_limit=raw.get("hard_limit", 64.0),
        unit=unit,  # type: ignore[arg-type]
    )
