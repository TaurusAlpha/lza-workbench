"""Tests for shared CLI output utilities."""

from __future__ import annotations

from lza_workbench.utils.output import (
    print_diff_summary,
    print_dry_run_header,
    print_info,
    print_kv,
    print_notice,
    print_section,
    print_success,
    print_warning,
)


def test_print_success(capsys) -> None:
    print_success("Operation completed")
    captured = capsys.readouterr().out
    assert "Operation completed" in captured


def test_print_dry_run_header(capsys) -> None:
    print_dry_run_header("lza init")
    captured = capsys.readouterr().out
    assert "Dry run: lza init" in captured


def test_print_warning(capsys) -> None:
    print_warning("Resource exists")
    captured = capsys.readouterr().out
    assert "Resource exists" in captured


def test_print_notice(capsys) -> None:
    print_notice("Downloading template...")
    captured = capsys.readouterr().out
    assert "Downloading template..." in captured


def test_print_info(capsys) -> None:
    print_info("Normal message")
    assert "Normal message" in capsys.readouterr().out

    print_info("Dimmed message", dim=True)
    assert "Dimmed message" in capsys.readouterr().out


def test_print_section(capsys) -> None:
    print_section(1, "CloudFormation Planning")
    captured = capsys.readouterr().out
    assert "1. CloudFormation Planning" in captured


def test_print_kv(capsys) -> None:
    print_kv("Workspace", "/tmp/workspace")
    captured = capsys.readouterr().out
    assert "Workspace: /tmp/workspace" in captured

    print_kv("Profile", "dev-root", bold_value=True)
    captured = capsys.readouterr().out
    assert "Profile: dev-root" in captured


def test_print_diff_summary_no_changes(capsys) -> None:
    print_diff_summary([], [], [])
    captured = capsys.readouterr().out
    assert "No file changes detected" in captured


def test_print_diff_summary_with_changes(capsys) -> None:
    print_diff_summary(["file1.yaml"], ["file2.yaml"], ["file3.yaml"])
    captured = capsys.readouterr().out
    assert "Changes: 1 added, 1 modified, 1 removed" in captured
    assert "+ file1.yaml" in captured
    assert "~ file2.yaml" in captured
    assert "- file3.yaml" in captured
