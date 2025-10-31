import argparse
import logging
from typing import List, Optional


class Command:
    name: str = ""
    help: str = ""

    def add_args(self, subparser: argparse.ArgumentParser) -> None:
        pass

    def initialize(self, args: argparse.Namespace) -> None:
        pass

    def run(self, args: argparse.Namespace) -> int:
        raise NotImplementedError


def _configure_logging(level: str) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=numeric, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")


def main(commands: Optional[List[Command]] = None) -> int:
    parser = argparse.ArgumentParser(prog="inference-core", description="June Inference Core CLI")
    parser.add_argument("--log-level", default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    cmds = commands or []
    for cmd in cmds:
        sp = subparsers.add_parser(cmd.name, help=cmd.help)
        cmd.add_args(sp)
        sp.set_defaults(_cmd=cmd)

    args = parser.parse_args()
    _configure_logging(args.log_level)

    cmd: Command = getattr(args, "_cmd")
    cmd.initialize(args)
    return int(cmd.run(args))




