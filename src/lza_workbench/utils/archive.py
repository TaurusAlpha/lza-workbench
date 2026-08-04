"""Zip archive creation, extraction, and manifest utilities for LZA configuration."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import zipfile
from pathlib import Path

from lza_workbench.core.workspace import ConfigDiffResult, is_path_excluded


def create_zip_archive(
    *,
    config_dir: Path,
    zip_path: Path,
    exclude_dirs: set[str],
    exclude_files: set[str],
) -> tuple[ConfigDiffResult, dict[str, tuple[int, int]]]:
    """Create a zip archive from config_dir and compute diff against previous zip manifest."""
    old_manifest = read_zip_manifest(zip_path)

    new_manifest: dict[str, tuple[int, int]] = {}
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for path in sorted(config_dir.rglob("*")):
            if not path.is_file():
                continue

            rel_path = path.relative_to(config_dir)
            if is_path_excluded(rel_path, exclude_dirs, exclude_files):
                continue

            arcname = str(rel_path)
            zipf.write(path, arcname)
            info = zipf.getinfo(arcname)
            new_manifest[arcname] = (info.file_size, info.CRC)

    old_keys = set(old_manifest.keys())
    new_keys = set(new_manifest.keys())

    added = sorted(list(new_keys - old_keys))
    removed = sorted(list(old_keys - new_keys))
    modified = [
        k for k in sorted(old_keys & new_keys)
        if old_manifest[k] != new_manifest[k]
    ]

    diff_result = ConfigDiffResult(added=added, modified=modified, removed=removed)
    return diff_result, new_manifest


def extract_zip_to_workspace(
    *,
    zip_path: Path,
    workspace_dir: Path,
    config_dir: Path,
    exclude_dirs: set[str],
) -> ConfigDiffResult:
    """Extract zip into workspace root, computing added/modified/removed file diffs."""
    with tempfile.TemporaryDirectory() as tmp_str:
        staging_dir = Path(tmp_str)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(staging_dir)

        top_level_folder = staging_dir / config_dir.name
        if top_level_folder.is_dir():
            source_content_dir = top_level_folder
        else:
            source_content_dir = staging_dir

        before_files = scan_directory_files(config_dir, exclude_dirs)
        incoming_files = scan_directory_files(source_content_dir, exclude_dirs)

        before_keys = set(before_files.keys())
        incoming_keys = set(incoming_files.keys())

        added = sorted(list(incoming_keys - before_keys))
        removed = sorted(list(before_keys - incoming_keys))
        modified = [
            k for k in sorted(before_keys & incoming_keys)
            if before_files[k] != incoming_files[k]
        ]

        config_dir.mkdir(parents=True, exist_ok=True)

        for item in config_dir.iterdir():
            if item.name in exclude_dirs:
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        for item in source_content_dir.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(source_content_dir)
                dest = config_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)

        return ConfigDiffResult(added=added, modified=modified, removed=removed)


def read_zip_manifest(path: Path) -> dict[str, tuple[int, int]]:
    """Read file size and CRC manifest of an existing zip file."""
    manifest: dict[str, tuple[int, int]] = {}
    if not path.is_file():
        return manifest

    try:
        with zipfile.ZipFile(path, "r") as z:
            for info in z.infolist():
                manifest[info.filename] = (info.file_size, info.CRC)
    except zipfile.BadZipFile:
        pass

    return manifest


def scan_directory_files(directory: Path, exclude_dirs: set[str]) -> dict[str, str]:
    """Scan directory files and return relative path to sha256 checksum map."""
    files_map: dict[str, str] = {}
    if not directory.is_dir():
        return files_map

    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(directory)
        if is_path_excluded(rel, exclude_dirs):
            continue
        files_map[str(rel)] = hashlib.sha256(path.read_bytes()).hexdigest()

    return files_map
