"""Git integration utilities for LZA configuration repositories."""

from __future__ import annotations

import subprocess
from pathlib import Path

from lza_workbench.errors import LzaError


def _run_git_command(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Execute a git command in the specified directory."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise LzaError("Git executable not found in PATH. Please ensure git is installed.") from exc


def is_git_repository(repo_dir: Path) -> bool:
    """Check if the directory is a valid git repository work tree."""
    if not repo_dir.exists() or not repo_dir.is_dir():
        return False
    proc = _run_git_command(["rev-parse", "--is-inside-work-tree"], cwd=repo_dir)
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def has_commits(repo_dir: Path) -> bool:
    """Check if the git repository has at least one commit."""
    proc = _run_git_command(["rev-parse", "--verify", "HEAD"], cwd=repo_dir)
    return proc.returncode == 0


def has_uncommitted_changes(repo_dir: Path) -> bool:
    """Check if there are any uncommitted changes or untracked files."""
    proc = _run_git_command(["status", "--porcelain"], cwd=repo_dir)
    if proc.returncode != 0:
        raise LzaError(f"Failed to check git status: {proc.stderr.strip()}")
    return bool(proc.stdout.strip())


def get_git_branch(repo_dir: Path) -> str:
    """Return the current active git branch name."""
    proc = _run_git_command(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir)
    if proc.returncode != 0:
        raise LzaError(f"Failed to get current git branch: {proc.stderr.strip()}")
    branch = proc.stdout.strip()
    return branch if branch != "HEAD" else "main"


def get_git_commit(repo_dir: Path) -> str:
    """Return the current HEAD commit hash (abbreviated)."""
    proc = _run_git_command(["rev-parse", "--short", "HEAD"], cwd=repo_dir)
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def get_git_remote_url(repo_dir: Path, remote_name: str = "origin") -> str | None:
    """Get the URL for the specified git remote."""
    proc = _run_git_command(["remote", "get-url", remote_name], cwd=repo_dir)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def set_git_remote_url(repo_dir: Path, remote_name: str, remote_url: str) -> None:
    """Set or add a git remote URL."""
    existing = get_git_remote_url(repo_dir, remote_name)
    if existing:
        proc = _run_git_command(["remote", "set-url", remote_name, remote_url], cwd=repo_dir)
    else:
        proc = _run_git_command(["remote", "add", remote_name, remote_url], cwd=repo_dir)
    if proc.returncode != 0:
        raise LzaError(f"Failed to configure git remote '{remote_name}': {proc.stderr.strip()}")


def count_git_files(repo_dir: Path) -> int:
    """Return the number of tracked files in the git repository."""
    proc = _run_git_command(["ls-files"], cwd=repo_dir)
    if proc.returncode != 0:
        return 0
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    return len(lines)


def push_git_branch(repo_dir: Path, remote: str, branch: str, dry_run: bool = False) -> None:
    """Push local branch to remote repository."""
    args = ["push", remote, branch]
    if dry_run:
        args.append("--dry-run")
    proc = _run_git_command(args, cwd=repo_dir)
    if proc.returncode != 0:
        raise LzaError(
            f"Failed to push git branch '{branch}' to remote '{remote}': {proc.stderr.strip()}"
        )
