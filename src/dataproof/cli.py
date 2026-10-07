"""Command line for DataProof."""

from __future__ import annotations

import argparse
from typing import Any

from .checks import dataproof
from .runner import Command, main_wrapper, run


def _check(args: argparse.Namespace, data: Any) -> dict[str, Any]:
    return dataproof(data, args.root)


COMMANDS = {
    "check": Command(
        _check,
        "Recalculate reported numbers from the data behind them",
        frozenset({"PASS"}),
        options=[(("--root",), {"default": ".", "help": "folder that CSV paths are under"})],
    ),
}


def main(argv: list[str] | None = None) -> int:
    return run("dataproof", "Recalculate reported numbers from their data.", COMMANDS, argv)


if __name__ == "__main__":
    main_wrapper(main)
