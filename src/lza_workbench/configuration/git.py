"""Git integration utilities for LZA configuration repositories."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from lza_workbench.errors import LzaError


def _run_git_command(
    args: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Execute a git command in the specified directory."""
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            env=run_env,
        )
    except FileNotFoundError as exc:
        raise LzaError("Git executable not found in PATH. Please ensure git is installed.") from exc


def is_git_repository(repo_dir: Path) -> bool:
    """Check if the directory is a valid git repository work tree."""
    if not repo_dir.exists() or not repo_dir.is_dir():
        return False
    proc = _run_git_command(["rev-parse", "--is-inside-work-tree"], cwd=repo_dir)
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def get_git_toplevel(repo_dir: Path) -> Path | None:
    """Get the top-level directory of the Git work tree, if inside one."""
    if not repo_dir.exists() or not repo_dir.is_dir():
        return None
    proc = _run_git_command(["rev-parse", "--show-toplevel"], cwd=repo_dir)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return Path(proc.stdout.strip()).resolve()


def is_git_root(repo_dir: Path) -> bool:
    """Check if the directory is the root of its own Git repository."""
    if (repo_dir / ".git").exists():
        return True
    toplevel = get_git_toplevel(repo_dir)
    return toplevel is not None and toplevel == repo_dir.resolve()


def is_inside_parent_git_repo(repo_dir: Path) -> bool:
    """Check if the directory is inside a parent Git repository work tree."""
    if (repo_dir / ".git").exists():
        return False
    toplevel = get_git_toplevel(repo_dir)
    return toplevel is not None and toplevel != repo_dir.resolve()


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


def create_initial_commit(
    repo_dir: Path,
    message: str = "Initial LZA configuration",
) -> str:
    """Stage all files in repo_dir and create an initial commit."""
    add_proc = _run_git_command(["add", "."], cwd=repo_dir)
    if add_proc.returncode != 0:
        raise LzaError(f"Failed to stage files in '{repo_dir}': {add_proc.stderr.strip()}")

    # Provide fallback author identity if not configured to prevent failures on clean systems
    check_user = _run_git_command(["config", "user.name"], cwd=repo_dir)
    env_override: dict[str, str] | None = None
    if check_user.returncode != 0 or not check_user.stdout.strip():
        check_global = _run_git_command(["config", "--global", "user.name"], cwd=repo_dir)
        if check_global.returncode != 0 or not check_global.stdout.strip():
            env_override = {
                "GIT_AUTHOR_NAME": "LZA Workbench",
                "GIT_AUTHOR_EMAIL": "workbench@local",
                "GIT_COMMITTER_NAME": "LZA Workbench",
                "GIT_COMMITTER_EMAIL": "workbench@local",
            }

    commit_proc = _run_git_command(
        ["commit", "-m", message],
        cwd=repo_dir,
        env=env_override,
    )
    if commit_proc.returncode != 0:
        raise LzaError(f"Failed to create initial git commit: {commit_proc.stderr.strip()}")

    return get_git_commit(repo_dir)


def get_git_branch(repo_dir: Path) -> str:
    """Return the current active git branch name, defaulting to 'main' on empty repositories."""
    proc = _run_git_command(["branch", "--show-current"], cwd=repo_dir)
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    proc = _run_git_command(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir)
    if proc.returncode == 0:
        branch = proc.stdout.strip()
        if branch and branch != "HEAD":
            return branch
    return "main"


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


def restore_git_stash(repo_dir: Path) -> None:
    """Restore the most recently created Git stash after a successful pull."""
    proc = _run_git_command(["stash", "pop"], cwd=repo_dir)
    if proc.returncode != 0:
        raise LzaError(
            "Configuration pull completed, but local changes could not be restored. "
            f"They remain in Git stash: {proc.stderr.strip()}"
        )


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
    proc1 = _run_git_command(["config", "credential.helper", helper_cmd], cwd=repo_dir)
    if proc1.returncode != 0:
        raise LzaError(
            f"Failed to configure git credential helper in '{repo_dir}': {proc1.stderr.strip()}"
        )
    proc2 = _run_git_command(["config", "credential.UseHttpPath", "true"], cwd=repo_dir)
    if proc2.returncode != 0:
        msg = proc2.stderr.strip()
        raise LzaError(f"Failed to configure git credential.UseHttpPath in '{repo_dir}': {msg}")


def init_git_repository(
    repo_dir: Path,
    remote_name: str = "origin",
    remote_url: str | None = None,
    aws_profile: str | None = None,
) -> None:
    """Initialize a git repository in repo_dir and configure remote and credential helper."""
    repo_dir.mkdir(parents=True, exist_ok=True)
    proc = _run_git_command(["init"], cwd=repo_dir)
    if proc.returncode != 0:
        msg = proc.stderr.strip()
        raise LzaError(f"Failed to initialize git repository in '{repo_dir}': {msg}")

    if remote_url:
        set_git_remote_url(repo_dir, remote_name=remote_name, remote_url=remote_url)

    if aws_profile and remote_url and "codecommit" in remote_url.lower():
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


def detect_git_repository_type(remote_url: str | None) -> str:
    """Classify the git repository type from its remote URL."""
    if not remote_url:
        return "local"
    url_lower = remote_url.lower()
    if "codecommit" in url_lower:
        return "codecommit"
    return "git"


def extract_codecommit_repo_name(remote_url: str) -> str | None:
    """Extract CodeCommit repository name from its HTTPS or SSH URL."""
    cleaned = remote_url.strip().rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    parts = cleaned.split("/")
    return parts[-1] if parts else None


from dataclasses import dataclass  # noqa: E402


@dataclass(frozen=True)
class GitProvenance:
    """Resolved Git repository metadata and provenance."""

    remote_url: str | None
    branch: str
    commit: str
    files_count: int
    repo_type: str
    repo_name: str | None


@dataclass(frozen=True)
class GitWorkingTreeStatus:
    """Local Git working tree state and branch/commit information."""

    is_git: bool
    branch: str
    commit: str
    commit_subject: str | None
    has_uncommitted: bool
    uncommitted_count: int
    remote_url: str | None
    files_count: int


@dataclass(frozen=True)
class GitRemoteSyncStatus:
    """Comparison between local HEAD and remote tracking branch."""

    status: str  # Synchronized, Ahead, Behind, Diverged, No Upstream, Not Git, Unknown
    ahead: int
    behind: int
    summary: str


def get_git_working_tree_status(repo_dir: Path) -> GitWorkingTreeStatus | None:
    """Get local Git repository and working tree status."""
    if not is_git_repository(repo_dir):
        return None

    branch = get_git_branch(repo_dir)
    commit = get_git_commit(repo_dir)
    commit_subject = None
    if has_commits(repo_dir):
        proc = _run_git_command(["log", "-1", "--format=%s"], cwd=repo_dir)
        if proc.returncode == 0:
            commit_subject = proc.stdout.strip() or None

    status_proc = _run_git_command(["status", "--porcelain"], cwd=repo_dir)
    uncommitted_lines = (
        [line for line in status_proc.stdout.splitlines() if line.strip()]
        if status_proc.returncode == 0
        else []
    )
    has_uncommitted = bool(uncommitted_lines)
    files_count = count_git_files(repo_dir)
    remote_url = get_git_remote_url(repo_dir)

    return GitWorkingTreeStatus(
        is_git=True,
        branch=branch,
        commit=commit,
        commit_subject=commit_subject,
        has_uncommitted=has_uncommitted,
        uncommitted_count=len(uncommitted_lines),
        remote_url=remote_url,
        files_count=files_count,
    )


def get_git_remote_sync_status(
    repo_dir: Path,
    remote_name: str = "origin",
    branch: str | None = None,
) -> GitRemoteSyncStatus:
    """Compare local branch HEAD against remote tracking branch."""
    if not is_git_repository(repo_dir) or not has_commits(repo_dir):
        return GitRemoteSyncStatus(
            status="Not Git",
            ahead=0,
            behind=0,
            summary="Not a Git repository or has no commits",
        )

    resolved_branch = branch or get_git_branch(repo_dir)
    upstream_ref = f"{remote_name}/{resolved_branch}"
    check_ref = _run_git_command(["rev-parse", "--verify", upstream_ref], cwd=repo_dir)

    if check_ref.returncode != 0:
        check_u = _run_git_command(["rev-parse", "--verify", "@{u}"], cwd=repo_dir)
        if check_u.returncode == 0:
            target_ref = "@{u}"
        else:
            return GitRemoteSyncStatus(
                status="No Upstream",
                ahead=0,
                behind=0,
                summary="No remote tracking branch",
            )
    else:
        target_ref = upstream_ref

    proc = _run_git_command(
        ["rev-list", "--left-right", "--count", f"HEAD...{target_ref}"], cwd=repo_dir
    )
    if proc.returncode != 0:
        return GitRemoteSyncStatus(
            status="Unknown",
            ahead=0,
            behind=0,
            summary="Cannot compare with remote",
        )

    parts = proc.stdout.strip().split()
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        ahead = int(parts[0])
        behind = int(parts[1])
        if ahead == 0 and behind == 0:
            return GitRemoteSyncStatus(status="Synchronized", ahead=0, behind=0, summary="In Sync")
        if ahead > 0 and behind == 0:
            suffix = "s" if ahead != 1 else ""
            return GitRemoteSyncStatus(
                status="Ahead",
                ahead=ahead,
                behind=0,
                summary=f"Ahead by {ahead} commit{suffix}",
            )
        if ahead == 0 and behind > 0:
            suffix = "s" if behind != 1 else ""
            return GitRemoteSyncStatus(
                status="Behind",
                ahead=0,
                behind=behind,
                summary=f"Behind by {behind} commit{suffix}",
            )
        return GitRemoteSyncStatus(
            status="Diverged",
            ahead=ahead,
            behind=behind,
            summary=f"Diverged ({ahead} ahead, {behind} behind)",
        )

    return GitRemoteSyncStatus(
        status="Unknown",
        ahead=0,
        behind=0,
        summary="Unknown sync state",
    )


def resolve_git_provenance(repo_dir: Path) -> GitProvenance | None:
    """Detect and resolve Git provenance for a given directory if it is a Git repository."""
    if not is_git_repository(repo_dir):
        return None

    remote_url = get_git_remote_url(repo_dir)
    branch = get_git_branch(repo_dir)
    commit = get_git_commit(repo_dir)
    files_count = count_git_files(repo_dir)
    repo_type = detect_git_repository_type(remote_url)
    repo_name = (
        extract_codecommit_repo_name(remote_url)
        if (remote_url and repo_type == "codecommit")
        else None
    )

    return GitProvenance(
        remote_url=remote_url,
        branch=branch,
        commit=commit,
        files_count=files_count,
        repo_type=repo_type,
        repo_name=repo_name,
    )

