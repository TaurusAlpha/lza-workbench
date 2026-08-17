"""CLI error translation and presentation."""

from __future__ import annotations

import sys

from lza_workbench.cli.output import print_error
from lza_workbench.errors import LzaError


def handle_cli_error(exc: Exception) -> int:
    """Translate an exception into a user-facing CLI error message and exit code."""
    if isinstance(exc, LzaError):
        print_error(str(exc))
        return 1

    print_error(f"Unexpected error: {exc}")
    return 1


def handle_main_execution(func) -> None:
    """Execute the CLI application, catching expected and unexpected failures."""
    try:
        func()
    except Exception as exc:
        code = handle_cli_error(exc)
        sys.exit(code)
