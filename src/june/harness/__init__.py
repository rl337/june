"""MechaHarness client adapters owned by June.

June selects, binds, and composes reusable MechaHarness graph templates.
MechaHarness owns generic execution, linkage, envelopes, and checkpoints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BoundRun:
    """A June-owned concrete realization ready for MechaHarness execution."""

    template_name: str
    bindings: dict[str, Any] = field(default_factory=dict)
    goal_id: str | None = None
    issue_id: str | None = None
    policy_version: str | None = None


class MechaHarnessClient:
    """Thin June-side facade over MechaHarness execution APIs.

    Soft points (tools, providers, budgets, persistence, product policy) are
    filled here. Generic graph validation and execution stay in MechaHarness.
    """

    def __init__(self) -> None:
        self._mh: Any | None = None

    def connect(self) -> None:
        """Lazy-import MechaHarness so install/layout issues surface clearly."""
        try:
            import mechaharness  # noqa: F401
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "mechaharness is required. Install the local package or "
                "add it as a dependency (see pyproject.toml)."
            ) from exc
        self._mh = True

    def bind_template(
        self,
        template_name: str,
        *,
        bindings: dict[str, Any] | None = None,
        goal_id: str | None = None,
        issue_id: str | None = None,
        policy_version: str | None = None,
    ) -> BoundRun:
        """Create a June-owned concrete graph realization from a template name."""
        return BoundRun(
            template_name=template_name,
            bindings=dict(bindings or {}),
            goal_id=goal_id,
            issue_id=issue_id,
            policy_version=policy_version,
        )

    def execute(self, run: BoundRun) -> dict[str, Any]:
        """Execute a bound run through MechaHarness.

        Placeholder: returns a structured stub until GraphTemplate selection,
        linkage resolution, and checkpointed execution are wired. Connecting to
        MechaHarness is deferred until a real executor path exists.
        """
        return {
            "status": "not_implemented",
            "template_name": run.template_name,
            "goal_id": run.goal_id,
            "issue_id": run.issue_id,
            "bindings": run.bindings,
            "policy_version": run.policy_version,
            "harness_connected": self._mh is not None,
        }
