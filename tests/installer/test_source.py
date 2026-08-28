"""Tests for installer source rules and GitHub validation."""

from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

from lza_workbench.installer.source import (
    github_secret_warning,
    validate_github_repository_access,
)


def test_github_secret_warning() -> None:
    assert github_secret_warning("accelerator/github-token", exists=True) is None
    warn = github_secret_warning("accelerator/github-token", exists=False)
    assert warn is not None and "was not found" in warn
    warn_err = github_secret_warning(
        "accelerator/github-token", exists=False, error="access denied"
    )
    assert warn_err is not None and "failed: access denied" in warn_err


def test_validate_github_repository_access_success() -> None:
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = validate_github_repository_access(
            owner="awslabs",
            repository_name="landing-zone-accelerator-on-aws",
            branch="release/v1.16.0",
            token="ghp_test123",
        )
        assert res["accessible"] is True
        assert res["error"] is None


def test_validate_github_repository_access_404() -> None:
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.github.com/repos/awslabs/nonexistent",
            code=404,
            msg="Not Found",
            hdrs={},  # type: ignore[arg-type]
            fp=None,
        )

        res = validate_github_repository_access(
            owner="awslabs",
            repository_name="nonexistent",
            token="ghp_test123",
        )
        assert res["accessible"] is False
        assert "not found" in res["error"].lower()


def test_validate_github_repository_access_401() -> None:
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.github.com/repos/awslabs/landing-zone-accelerator-on-aws",
            code=401,
            msg="Unauthorized",
            hdrs={},  # type: ignore[arg-type]
            fp=None,
        )

        res = validate_github_repository_access(
            owner="awslabs",
            repository_name="landing-zone-accelerator-on-aws",
            token="invalid_token",
        )
        assert res["accessible"] is False
        assert "unauthorized" in res["error"].lower() or "invalid" in res["error"].lower()
