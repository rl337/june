"""June CLI entrypoint."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from pathlib import Path

from june import __version__
from june.config import JuneSettings, load_settings
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
        help="Durable state directory (JSON store); overrides config data_dir",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config.yaml (default: $JUNE_CONFIG or ./config.yaml)",
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

    tick = sub.add_parser("tick", help="One control-graph step (cron/polls/due work)")
    tick.set_defaults(func=_cmd_tick)

    run = sub.add_parser(
        "run",
        help="Single entrypoint: run the June control graph (cron + polling loop)",
    )
    run.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Stop after N control steps (default: run until interrupted)",
    )
    run.set_defaults(func=_cmd_run)

    dream = sub.add_parser("dream", help="Mine durable traces for improvement proposals")
    dream.set_defaults(func=_cmd_dream)

    graph_viz = sub.add_parser(
        "graph-viz",
        help="Execute a sample MechaHarness graph with live ASCII visualization",
    )
    graph_viz.add_argument(
        "--nodes",
        type=int,
        default=3,
        help="Number of sequential june.task nodes (default: 3)",
    )
    graph_viz.add_argument(
        "--format",
        choices=("ascii", "mermaid", "json"),
        default="ascii",
        help="Final snapshot format (live updates are always ASCII)",
    )
    graph_viz.set_defaults(func=_cmd_graph_viz)

    serve = sub.add_parser(
        "serve",
        help="Run the web graph console (chat + live graph; container entrypoint)",
    )
    serve.add_argument(
        "--host",
        default=None,
        help="Bind host (default: console.host from config, else 0.0.0.0)",
    )
    serve.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port (default: console.port from config, else 8080)",
    )
    serve.add_argument(
        "--demo-graph",
        action="store_true",
        help="Run a sample MechaHarness graph on startup (also via JUNE_CONSOLE_DEMO=1)",
    )
    serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        raise SystemExit(0)
    args.func(args)


def _settings(args: argparse.Namespace) -> JuneSettings:
    settings = load_settings(getattr(args, "config", None))
    if args.data_dir:
        settings = settings.model_copy(update={"data_dir": args.data_dir})
    return settings


def _orch(args: argparse.Namespace) -> Orchestrator:
    from june.bootstrap import build_app

    settings = _settings(args)
    built = build_app(settings)
    return built[Orchestrator]


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


def _cmd_run(args: argparse.Namespace) -> None:
    orch = _orch(args)
    stop = {"flag": False}

    def _stop(signum: int, frame: object) -> None:
        del signum, frame
        stop["flag"] = True
        print("stopping control graph…", file=sys.stderr)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    print(
        json.dumps(
            {
                "event": "control_graph_start",
                "graph": orch.control.describe(),
            },
            indent=2,
        ),
        file=sys.stderr,
    )
    results = orch.run(max_steps=args.max_steps, should_stop=lambda: stop["flag"])
    print(
        json.dumps(
            {
                "event": "control_graph_stop",
                "steps": len(results),
                "last": None
                if not results
                else {
                    "slept_seconds": results[-1].slept_seconds,
                    "jobs_run": results[-1].jobs_run,
                    "events": len(results[-1].events),
                    "work_outcomes": len(results[-1].work_outcomes),
                },
            },
            indent=2,
        )
    )


def _cmd_dream(args: argparse.Namespace) -> None:
    proposals = _orch(args).dream()
    print(json.dumps([p.to_dict() for p in proposals], indent=2))


def _cmd_serve(args: argparse.Namespace) -> None:
    import asyncio
    import os
    import threading

    from june.bootstrap import build_app
    from june.channels import ChatService
    from june.console.hub import ConsoleHub
    from june.console.runtime import ConsoleRuntime
    from june.console.server import serve_console
    from june.console.spool import ConsoleSpool
    from june.providers.junespark import JunesparkProvider

    settings = _settings(args)
    host = args.host or settings.console.host or "0.0.0.0"
    port = args.port if args.port is not None else (settings.console.port or 8080)
    settings = settings.model_copy(
        update={"console": settings.console.model_copy(update={"host": host, "port": port})}
    )
    built = build_app(settings)
    orch = built[Orchestrator]
    # Console observability spool: hourly JSONL events + instance checkpoints.
    # Prefer settings.data_dir, then JUNE_DATA_DIR, then .env/data.
    data_root = (
        Path(settings.data_dir)
        if settings.data_dir
        else Path(os.environ.get("JUNE_DATA_DIR", ".env/data"))
    )
    hub = ConsoleHub(spool=ConsoleSpool(data_root / "console" / "spool"))
    runtime = ConsoleRuntime(orch, hub)
    runtime.refresh_status()
    runtime.start_control_loop()
    runtime.start_cron_graph()

    demo = args.demo_graph or os.environ.get("JUNE_CONSOLE_DEMO", "").lower() in {
        "1",
        "true",
        "yes",
    }

    def run_demo() -> None:
        if not orch.client.connect():
            return
        run = orch.client.bind_template(
            "console-demo",
            bindings={"task": "console demo", "query": ""},
            node_kinds=["june.task", "june.task", "june.task"],
        )
        orch.client.execute(run, driver="run")

    if demo:
        threading.Thread(target=run_demo, name="june-console-demo", daemon=True).start()

    try:
        asyncio.run(
            serve_console(
                hub,
                host=settings.console.host,
                port=settings.console.port,
                orchestrator=orch,
                provider=built[JunesparkProvider],
                chat_service=built[ChatService],
                settings=settings,
            )
        )
    finally:
        runtime.stop()


def _cmd_graph_viz(args: argparse.Namespace) -> None:
    from june.harness import MechaHarnessClient
    from june.harness.visualization import GRAPH_NODE_START

    probe = MechaHarnessClient()
    if not probe.connect():
        print(
            json.dumps(
                {
                    "error": "mechaharness_not_installed",
                    "hint": "pip install 'june[harness]'",
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)

    run_holder: dict[str, object] = {}

    def on_event(event: object) -> None:
        etype = str(getattr(event, "type", ""))
        if etype != GRAPH_NODE_START:
            return
        bound = run_holder.get("run")
        if bound is None:
            return
        print(client.render_execution_focus(bound, style="ascii"), file=sys.stderr)
        print(f"--- {etype} ---", file=sys.stderr)

    client = MechaHarnessClient(on_graph_event=on_event)
    if not client.connect():
        raise SystemExit(1)
    run = client.bind_template(
        "graph-viz-demo",
        bindings={"task": "visualize execution"},
        node_kinds=["june.task"] * max(1, args.nodes),
    )
    run_holder["run"] = run
    result = client.execute(run, driver="run")
    if args.format == "json":
        print(json.dumps(result.raw.get("execution_focus"), indent=2))
    elif args.format == "mermaid":
        print(
            client.render_execution_focus(
                run, checkpoint=result.graph_checkpoint, style="mermaid"
            )
        )
    else:
        print(
            client.render_execution_focus(
                run, checkpoint=result.graph_checkpoint, style="ascii"
            )
        )
    print(json.dumps({"status": result.status, "run_id": result.run_id}, indent=2), file=sys.stderr)


if __name__ == "__main__":
    app(sys.argv[1:])
