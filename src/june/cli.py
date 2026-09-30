"""June CLI entrypoint."""

from __future__ import annotations

import argparse
import sys

from june import __version__


def app(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="june",
        description="June orchestrator — goals, scheduling, and MechaHarness-backed runs",
    )
    parser.add_argument("--version", action="version", version=f"june {__version__}")
    sub = parser.add_subparsers(dest="command")

    status = sub.add_parser("status", help="Show orchestrator status")
    status.set_defaults(func=_cmd_status)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        raise SystemExit(0)
    args.func(args)


def _cmd_status(_args: argparse.Namespace) -> None:
    print(f"june {__version__}")
    print("role: application orchestrator / MechaHarness client")
    print("state: scaffold — see docs/inspiration/dev-blog-inspiration.md")


if __name__ == "__main__":
    app(sys.argv[1:])
