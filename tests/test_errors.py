"""Tests for application error types."""

from __future__ import annotations

import pytest

from lza_workbench.errors import LzaError


def test_errors_module_exports_lza_error() -> None:
    """Verify that LzaError is an Exception and is exported from errors module."""
    assert issubclass(LzaError, Exception)
    err = LzaError("test message")
    assert str(err) == "test message"


def test_lza_error_handling() -> None:
    """Verify standard exception handling behavior for LzaError."""
    with pytest.raises(LzaError, match="something went wrong"):
        raise LzaError("something went wrong")
