"""Task runner — June orchestration around MechaHarness execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from june.harness import BoundRun, MechaHarnessClient
from june.scheduler import RunnableWork, WakeReason


@dataclass
class TaskOutcome:
    work_id: str
    status: str
    result: dict[str, Any]


class TaskRunner:
    """Load state → select/bind template → execute via MechaHarness → write back."""

    def __init__(self, client: MechaHarnessClient | None = None) -> None:
        self.client = client or MechaHarnessClient()

    def run(self, work: RunnableWork, *, template_name: str = "direct") -> TaskOutcome:
        bound = self.client.bind_template(
            template_name,
            bindings={"wake_reason": work.reason.value, **work.payload},
            goal_id=work.goal_id,
            issue_id=work.issue_id,
        )
        result = self.client.execute(bound)
        status = "completed" if result.get("status") != "not_implemented" else "pending"
        if work.reason is WakeReason.MANUAL and result.get("status") == "not_implemented":
            status = "scaffolded"
        return TaskOutcome(work_id=work.id, status=status, result=result)

    def realize(self, run: BoundRun) -> dict[str, Any]:
        return self.client.execute(run)
