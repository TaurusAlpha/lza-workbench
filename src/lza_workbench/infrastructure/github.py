"""External GitHub API validation and reachability checks."""

from __future__ import annotations

from typing import Any


def validate_github_repository_access(
    *,
    owner: str = "awslabs",
    repository_name: str = "landing-zone-accelerator-on-aws",
    branch: str | None = None,
    token: str | None = None,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    """Validate that a GitHub repository (and optional branch) is accessible."""
    import urllib.error
    import urllib.request

    clean_owner = (owner or "awslabs").strip()
    clean_repo = (repository_name or "landing-zone-accelerator-on-aws").strip()
    repo_url = f"https://api.github.com/repos/{clean_owner}/{clean_repo}"

    headers = {
        "User-Agent": "LZA-Workbench",
        "Accept": "application/vnd.github+json",
    }
    if token and token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"

    req = urllib.request.Request(repo_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds):
            pass
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {
                "accessible": False,
                "error": (
                    f"Repository '{clean_owner}/{clean_repo}' not found or lacks access (HTTP 404)."
                ),
            }
        if exc.code == 401:
            return {
                "accessible": False,
                "error": (
                    "GitHub Personal Access Token is invalid or expired (HTTP 401 Unauthorized)."
                ),
            }
        if exc.code == 403:
            return {
                "accessible": False,
                "error": (
                    f"GitHub API access forbidden for '{clean_owner}/{clean_repo}' (HTTP 403)."
                ),
            }
        return {
            "accessible": False,
            "error": f"GitHub API returned HTTP {exc.code}: {exc.reason}",
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "accessible": False,
            "error": f"Could not connect to GitHub API: {exc}",
        }
    except Exception as exc:
        return {
            "accessible": False,
            "error": f"Unexpected error checking GitHub repository: {exc}",
        }

    if branch and branch.strip():
        clean_branch = branch.strip()
        branch_url = (
            f"https://api.github.com/repos/{clean_owner}/{clean_repo}/branches/{clean_branch}"
        )
        branch_req = urllib.request.Request(branch_url, headers=headers)
        try:
            with urllib.request.urlopen(branch_req, timeout=timeout_seconds):
                pass
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {
                    "accessible": False,
                    "error": (
                        f"Branch '{clean_branch}' not found in repository "
                        f"'{clean_owner}/{clean_repo}' (HTTP 404)."
                    ),
                }
            return {
                "accessible": False,
                "error": (
                    f"GitHub API returned HTTP {exc.code} for branch '{clean_branch}': {exc.reason}"
                ),
            }
        except Exception as exc:
            return {
                "accessible": False,
                "error": f"Could not verify branch '{clean_branch}' on GitHub: {exc}",
            }

    return {
        "accessible": True,
        "error": None,
    }


__all__ = ["validate_github_repository_access"]
