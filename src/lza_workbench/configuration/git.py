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


def stash_git_changes(repo_dir: Path, message: str = "lza-config-pull-stash") -> bool:
    """Stash uncommitted changes including untracked files.

    Returns True if changes were stashed, False if working tree was already clean.
    """
    if not has_uncommitted_changes(repo_dir):
        return False
    proc = _run_git_command(["stash", "push", "--include-untracked", "-m", message], cwd=repo_dir)
    if proc.returncode != 0:
        raise LzaError(f"Failed to stash local git changes: {proc.stderr.strip()}")
    return True


def fetch_git_remote(repo_dir: Path, remote: str = "origin") -> None:
    """Fetch branches/commits from specified git remote."""
    proc = _run_git_command(["fetch", remote], cwd=repo_dir)
    if proc.returncode != 0:
        raise LzaError(f"Failed to fetch from remote '{remote}': {proc.stderr.strip()}")


def pull_git_branch(repo_dir: Path, remote: str, branch: str) -> None:
    """Pull changes for the specified branch from remote repository."""
    proc = _run_git_command(["pull", remote, branch], cwd=repo_dir)
    if proc.returncode != 0:
        raise LzaError(
            f"Failed to pull git branch '{branch}' from remote '{remote}': {proc.stderr.strip()}"
        )


def configure_codecommit_credential_helper(
    repo_dir: Path,
    aws_profile: str,
) -> None:
    """Configure AWS CodeCommit credential helper in repository .git/config."""
    if not (repo_dir / ".git").exists() and not is_git_repository(repo_dir):
        return
    helper_cmd = f"!aws --profile {aws_profile} codecommit credential-helper $@"
    _run_git_command(["config", "credential.helper", helper_cmd], cwd=repo_dir)
    _run_git_command(["config", "credential.UseHttpPath", "true"], cwd=repo_dir)


def init_git_repository(
    repo_dir: Path,
    remote_name: str = "origin",
    remote_url: str | None = None,
    aws_profile: str | None = None,
) -> None:
    """Initialize a git repository in repo_dir and configure remote if provided."""
    repo_dir.mkdir(parents=True, exist_ok=True)
    proc = _run_git_command(["init"], cwd=repo_dir)
    if proc.returncode != 0:
        raise LzaError(
            f"Failed to initialize git repository at '{repo_dir}': {proc.stderr.strip()}"
        )
    if remote_url:
        set_git_remote_url(repo_dir, remote_name, remote_url)
    if aws_profile:
        configure_codecommit_credential_helper(repo_dir, aws_profile)


def clone_git_repository(
    repo_dir: Path,
    remote_url: str,
    branch: str | None = None,
    aws_profile: str | None = None,
) -> None:
    """Clone a remote repository into repo_dir and configure credential helper if profile given."""
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    args = ["clone"]
    if branch:
        args.extend(["--branch", branch])
    args.extend([remote_url, str(repo_dir)])
    proc = _run_git_command(args, cwd=repo_dir.parent)
    if proc.returncode != 0:
        raise LzaError(
            f"Failed to clone repository '{remote_url}' into '{repo_dir}': {proc.stderr.strip()}"
        )
    if aws_profile and "codecommit" in remote_url.lower():
        configure_codecommit_credential_helper(repo_dir, aws_profile)


