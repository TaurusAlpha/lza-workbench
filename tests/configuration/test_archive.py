"""Tests for configuration archive packaging and extraction rules."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest

from lza_workbench.configuration.archive import (
    count_config_files,
    create_zip_archive,
    extract_zip_to_workspace,
    is_path_excluded,
)


def test_upload_and_download_apply_the_same_exclusions(tmp_path: Path) -> None:
    """Excluded configuration content is neither packaged nor restored from an archive."""
    exclude_dirs = {".git", "backup"}
    exclude_files = {".DS_Store"}
    source_dir = tmp_path / "source"
    (source_dir / "backup").mkdir(parents=True)
    (source_dir / ".git").mkdir()
    (source_dir / "keep.yaml").write_text("keep", encoding="utf-8")
    (source_dir / "backup" / "ignored.yaml").write_text("ignored", encoding="utf-8")
    (source_dir / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    (source_dir / ".DS_Store").write_text("metadata", encoding="utf-8")

    zip_path = tmp_path / "archive.zip"
    _, manifest = create_zip_archive(
        config_dir=source_dir,
        zip_path=zip_path,
        exclude_dirs=exclude_dirs,
        exclude_files=exclude_files,
    )
    assert set(manifest) == {"keep.yaml"}

    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("aws-accelerator-config/keep.yaml", "new")
        archive.writestr("aws-accelerator-config/backup/incoming.yaml", "ignored")
        archive.writestr("aws-accelerator-config/.git/HEAD", "ignored")
        archive.writestr("aws-accelerator-config/.DS_Store", "ignored")

    target_dir = tmp_path / "aws-accelerator-config"
    (target_dir / ".git").mkdir(parents=True)
    (target_dir / ".git" / "HEAD").write_text("preserved", encoding="utf-8")
    (target_dir / ".DS_Store").write_text("preserved", encoding="utf-8")
    diff = extract_zip_to_workspace(
        zip_path=zip_path,
        config_dir=target_dir,
        exclude_dirs=exclude_dirs,
        exclude_files=exclude_files,
    )

    assert diff.added == ["keep.yaml"]
    assert (target_dir / "keep.yaml").read_text(encoding="utf-8") == "new"
    assert not (target_dir / "backup" / "incoming.yaml").exists()
    assert (target_dir / ".git" / "HEAD").read_text(encoding="utf-8") == "preserved"
    assert (target_dir / ".DS_Store").read_text(encoding="utf-8") == "preserved"


def test_extract_zip_invalid_archive_leaves_workspace_intact(tmp_path: Path) -> None:
    """An invalid/corrupt archive aborts before modifying the target directory."""
    target_dir = tmp_path / "aws-accelerator-config"
    target_dir.mkdir(parents=True)
    (target_dir / "existing.yaml").write_text("original", encoding="utf-8")

    corrupt_zip = tmp_path / "corrupt.zip"
    corrupt_zip.write_text("this is not a valid zip archive", encoding="utf-8")

    with pytest.raises(zipfile.BadZipFile):
        extract_zip_to_workspace(
            zip_path=corrupt_zip,
            config_dir=target_dir,
            exclude_dirs={".git"},
            exclude_files={".DS_Store"},
        )

    assert (target_dir / "existing.yaml").read_text(encoding="utf-8") == "original"


def test_extract_zip_failure_during_replacement_restores_original_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If an error occurs while copying incoming files, the original configuration is restored."""
    target_dir = tmp_path / "aws-accelerator-config"
    target_dir.mkdir(parents=True)
    (target_dir / "existing.yaml").write_text("original content", encoding="utf-8")
    (target_dir / "nested").mkdir()
    (target_dir / "nested" / "sub.yaml").write_text("nested original", encoding="utf-8")
    (target_dir / ".git").mkdir()
    (target_dir / ".git" / "config").write_text("git config", encoding="utf-8")

    valid_zip = tmp_path / "incoming.zip"
    with zipfile.ZipFile(valid_zip, "w") as archive:
        archive.writestr("aws-accelerator-config/incoming.yaml", "new content")
        archive.writestr("aws-accelerator-config/nested/sub.yaml", "new nested")

    original_copy2 = shutil.copy2
    failed_once = False

    # Simulate a crash/disk failure during the incoming copy phase
    def failing_copy2(src, dst, *args, **kwargs):
        nonlocal failed_once
        if "backup" in str(dst) or failed_once:
            return original_copy2(src, dst, *args, **kwargs)
        failed_once = True
        raise OSError("Simulated disk error during destination write")

    monkeypatch.setattr(shutil, "copy2", failing_copy2)

    with pytest.raises(OSError, match="Simulated disk error"):
        extract_zip_to_workspace(
            zip_path=valid_zip,
            config_dir=target_dir,
            exclude_dirs={".git"},
            exclude_files={".DS_Store"},
        )

    # Verify complete rollback of original workspace files
    assert (target_dir / "existing.yaml").read_text(encoding="utf-8") == "original content"
    assert (target_dir / "nested" / "sub.yaml").read_text(encoding="utf-8") == "nested original"
    assert (target_dir / ".git" / "config").read_text(encoding="utf-8") == "git config"
    assert not (target_dir / "incoming.yaml").exists()


def test_is_path_excluded_and_count_config_files(tmp_path: Path) -> None:
    assert is_path_excluded(Path(".git/config"), exclude_dirs={".git"})
    assert is_path_excluded(Path("sub/.git/HEAD"), exclude_dirs={".git"})
    assert not is_path_excluded(Path("accounts/accounts.yaml"), exclude_dirs={".git"})

    config_dir = tmp_path / "config"
    (config_dir / "dir1").mkdir(parents=True)
    (config_dir / ".git").mkdir(parents=True)

    (config_dir / "dir1" / "file1.txt").write_text("hello", encoding="utf-8")
    (config_dir / ".git" / "HEAD").write_text("ref", encoding="utf-8")

    assert count_config_files(config_dir, exclude_dirs={".git"}) == 1
