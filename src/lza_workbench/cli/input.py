import re
from collections.abc import Callable

import typer

from lza_workbench.errors import LzaError

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def validate_email(value: str) -> str:
    """Validate and strip an email address parameter."""
    cleaned = (value or "").strip()
    if not EMAIL_PATTERN.match(cleaned):
        raise ValueError("Must be a valid email address (e.g. user@example.com).")
    return cleaned


def value_or_prompt(
    label: str,
    value: str | None,
    default: str | None = None,
    interactive: bool = True,
    validator: Callable[[str], str] | None = None,
) -> str:
    """Use an explicit value, prompt with a default, or use that default."""
    if value and value.strip():
        cleaned = value.strip()
        if validator:
            return validator(cleaned)
        return cleaned

    if interactive:
        def value_proc(val: str) -> str:
            cleaned = (val or "").strip()
            if not cleaned and default is None:
                raise typer.BadParameter("Value cannot be empty.")
            if validator and cleaned:
                try:
                    return validator(cleaned)
                except ValueError as err:
                    raise typer.BadParameter(str(err)) from err
            return cleaned

        if default is not None:
            return typer.prompt(label, default=default, value_proc=value_proc)
        return typer.prompt(label, value_proc=value_proc)

    if default is not None and default.strip():
        return default.strip()

    raise LzaError(f"{label} is required.")


__all__ = ["validate_email", "value_or_prompt"]
