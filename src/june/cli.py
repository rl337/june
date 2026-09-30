"""June CLI entrypoint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from june import __version__
from june.orchestrator import Orchestrator
from june.scheduler import WakeReason


def app(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="june",
        description="June orchestrator — goals, scheduling, and MechaHarness-backed runs",
    )
    parser.add_argument("--version", action="version", version=f"june {__version__}")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Durable state directory (JSON store)",
    )
    sub = parser.add_subparsers(dest="command")

    status = sub.add_parser("status", help="Show orchestrator status")
    status.set_defaults(func=_cmd_status)

    goal = sub.add_parser("goal-create", help="Create a persistent goal")
    goal.add_argument("title")
    goal.add_argument("--criteria", default="manual completion")
    goal.add_argument("--priority", type=int, default=0)
    goal.set_defaults(func=_cmd_goal_create)

    wake = sub.add_parser("wake", help="Wake a goal into the task runner")
    wake.add_argument("goal_id")
    wake.add_argument("--task", default="")
    wake.add_argument("--complete", action="store_true")
    wake.set_defaults(func=_cmd_wake)

    tick = sub.add_parser("tick", help="Materialize schedules and drain runnable work")
    tick.set_defaults(func=_cmd_tick)

    dream = sub.add_parser("dream", help="Mine durable traces for improvement proposals")
    dream.set_defaults(func=_cmd_dream)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        raise SystemExit(0)
    args.func(args)


def _orch(args: argparse.Namespace) -> Orchestrator:
    data_dir = Path(args.data_dir) if args.data_dir else None
    return Orchestrator(data_dir)


def _cmd_status(args: argparse.Namespace) -> None:
    print(json.dumps(_orch(args).status(), indent=2))


def _cmd_goal_create(args: argparse.Namespace) -> None:
    goal = _orch(args).create_goal(args.title, args.criteria, priority=args.priority)
    print(json.dumps(goal.to_dict(), indent=2))


def _cmd_wake(args: argparse.Namespace) -> None:
    payload = {"task": args.task or args.goal_id}
    if args.complete:
        payload["mark_goal_complete"] = True
    outcome = _orch(args).wake_goal(args.goal_id, reason=WakeReason.MANUAL, payload=payload)
    print(
        json.dumps(
            {
                "work_id": outcome.work_id,
                "status": outcome.status,
                "decision": outcome.decision,
                "run_id": outcome.run_id,
                "result": outcome.result,
                "policy": outcome.policy,
            },
            indent=2,
        )
    )


def _cmd_tick(args: argparse.Namespace) -> None:
    outcomes = _orch(args).tick()
    payload = [
        {"work_id": o.work_id, "status": o.status, "decision": o.decision}
        for o in outcomes
    ]
    print(json.dumps(payload, indent=2))


def _cmd_dream(args: argparse.Namespace) -> None:
    proposals = _orch(args).dream()
    print(json.dumps([p.to_dict() for p in proposals], indent=2))


if __name__ == "__main__":
    app(sys.argv[1:])
