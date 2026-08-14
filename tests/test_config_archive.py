"""Tests for configuration archive packaging and extraction rules."""

from __future__ import annotations

import zipfile
from pathlib import Path

from lza_workbench.config.archive import create_zip_archive, extract_zip_to_workspace


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
