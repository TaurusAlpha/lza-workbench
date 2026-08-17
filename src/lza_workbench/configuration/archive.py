"""Zip archive operations for LZA configuration workspaces."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConfigDiffResult:
    """Summary of changes between existing and new configuration files."""

    added: list[str]
    modified: list[str]
    removed: list[str]

    @property
    def has_changes(self) -> bool:
        """Return whether the comparison found at least one change."""
        return bool(self.added or self.modified or self.removed)


def create_zip_archive(
    *,
    config_dir: Path,
    zip_path: Path,
    exclude_dirs: set[str],
    exclude_files: set[str],
) -> tuple[ConfigDiffResult, dict[str, tuple[int, int]]]:
    """Create a zip archive from config_dir and compute its diff from the previous archive."""
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

    old_keys = set(old_manifest)
    new_keys = set(new_manifest)
    return (
        ConfigDiffResult(
            added=sorted(new_keys - old_keys),
            modified=sorted(
                key for key in old_keys & new_keys if old_manifest[key] != new_manifest[key]
            ),
            removed=sorted(old_keys - new_keys),
        ),
        new_manifest,
    )


def extract_zip_to_workspace(
    *,
    zip_path: Path,
    config_dir: Path,
    exclude_dirs: set[str],
    exclude_files: set[str],
) -> ConfigDiffResult:
    """Extract included archive files into the workspace configuration directory safely."""
    if not zip_path.is_file():
        raise FileNotFoundError(f"Archive file not found: {zip_path}")

    with tempfile.TemporaryDirectory() as tmp_str:
        temp_root = Path(tmp_str)
        staging_dir = temp_root / "staging"
        backup_dir = temp_root / "backup"
        staging_dir.mkdir(parents=True, exist_ok=True)
        backup_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(staging_dir)

        top_level_folder = staging_dir / config_dir.name
        source_content_dir = top_level_folder if top_level_folder.is_dir() else staging_dir

        before_files = scan_directory_files(config_dir, exclude_dirs, exclude_files)
        incoming_files = scan_directory_files(source_content_dir, exclude_dirs, exclude_files)
        before_keys = set(before_files)
        incoming_keys = set(incoming_files)
        diff_result = ConfigDiffResult(
            added=sorted(incoming_keys - before_keys),
            modified=sorted(
                key
                for key in before_keys & incoming_keys
                if before_files[key] != incoming_files[key]
            ),
            removed=sorted(before_keys - incoming_keys),
        )

        if config_dir.is_dir():
            for item in config_dir.iterdir():
                if item.name in exclude_dirs or (item.is_file() and item.name in exclude_files):
                    continue
                if item.is_dir():
                    shutil.copytree(item, backup_dir / item.name)
                else:
                    shutil.copy2(item, backup_dir / item.name)

        config_dir.mkdir(parents=True, exist_ok=True)

        try:
            for item in list(config_dir.iterdir()):
                if item.name in exclude_dirs or (item.is_file() and item.name in exclude_files):
                    continue
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

            for item in source_content_dir.rglob("*"):
                if not item.is_file():
                    continue
                rel_path = item.relative_to(source_content_dir)
                if is_path_excluded(rel_path, exclude_dirs, exclude_files):
                    continue
                dest = config_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)

            return diff_result

        except Exception:
            for item in list(config_dir.iterdir()):
                if item.name in exclude_dirs or (item.is_file() and item.name in exclude_files):
                    continue
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

            for item in backup_dir.iterdir():
                if item.is_dir():
                    shutil.copytree(item, config_dir / item.name)
                else:
                    shutil.copy2(item, config_dir / item.name)
            raise


def read_zip_manifest(path: Path) -> dict[str, tuple[int, int]]:
    """Read file size and CRC manifest of an existing zip file."""
    manifest: dict[str, tuple[int, int]] = {}
    if not path.is_file():
        return manifest

    try:
        with zipfile.ZipFile(path, "r") as archive:
            for info in archive.infolist():
                manifest[info.filename] = (info.file_size, info.CRC)
    except zipfile.BadZipFile:
        pass
    return manifest


def scan_directory_files(
    directory: Path, exclude_dirs: set[str], exclude_files: set[str] | None = None
) -> dict[str, str]:
    """Return included relative paths mapped to their SHA-256 checksum."""
    files_map: dict[str, str] = {}
    if not directory.is_dir():
        return files_map

    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        rel_path = path.relative_to(directory)
        if not is_path_excluded(rel_path, exclude_dirs, exclude_files):
            files_map[str(rel_path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files_map


def is_path_excluded(
    rel_path: Path,
    exclude_dirs: set[str],
    exclude_files: set[str] | None = None,
) -> bool:
    """Check whether a relative path matches excluded directory or file rules."""
    return any(part in exclude_dirs for part in rel_path.parts[:-1]) or bool(
        exclude_files and rel_path.name in exclude_files
    )


def count_config_files(
    config_dir: Path, exclude_dirs: set[str], exclude_files: set[str] | None = None
) -> int:
    """Count included configuration files."""
    return len(scan_directory_files(config_dir, exclude_dirs, exclude_files))
