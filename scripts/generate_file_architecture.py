"""Generate the human-facing application file tree from module purpose docstrings."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src" / "lza_workbench"
DOCUMENT_PATH = PROJECT_ROOT / "docs" / "FILE-ARCHITECTURE.md"
BEGIN_MARKER = "<!-- BEGIN GENERATED APPLICATION TREE -->"
END_MARKER = "<!-- END GENERATED APPLICATION TREE -->"
EXTRA_DIRECTORIES = {
    SOURCE_ROOT / "interfaces" / "web" / "static": (
        "Browser HTML, CSS, and JavaScript assets."
    ),
}


def purpose(path: Path) -> str:
    """Return the first line of a Python module's purpose docstring."""
    document = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstring = ast.get_docstring(document, clean=True)
    if not docstring:
        relative_path = path.relative_to(PROJECT_ROOT)
        raise ValueError(f"Missing module purpose docstring: {relative_path}")
    return docstring.splitlines()[0]


def directory_purpose(path: Path) -> str:
    """Return the package purpose or an explicit purpose for a non-Python asset directory."""
    if path in EXTRA_DIRECTORIES:
        return EXTRA_DIRECTORIES[path]
    return purpose(path / "__init__.py")


def included_directories(path: Path) -> list[Path]:
    """Return child package and explicitly documented asset directories."""
    directories = []
    for child in path.iterdir():
        if not child.is_dir() or child.name == "__pycache__":
            continue
        if (child / "__init__.py").is_file() or child in EXTRA_DIRECTORIES:
            directories.append(child)
    return sorted(directories, key=lambda item: item.name)


def included_modules(path: Path) -> list[Path]:
    """Return Python modules that should appear as individual files in the map."""
    return sorted(child for child in path.glob("*.py") if child.name != "__init__.py")


def format_entry(label: str, description: str) -> str:
    """Align a tree label and its concise purpose comment."""
    padding = " " * max(1, 62 - len(label))
    return f"{label}{padding}# {description}"


def render_children(path: Path, prefix: str = "") -> list[str]:
    """Render package directories followed by modules at the current tree level."""
    directories = included_directories(path)
    modules = included_modules(path)
    entries: list[tuple[Path, bool]] = [(item, True) for item in directories]
    entries.extend((item, False) for item in modules)

    lines: list[str] = []
    for index, (entry, is_directory) in enumerate(entries):
        is_last = index == len(entries) - 1
        connector = "└── " if is_last else "├── "
        name = f"{entry.name}/" if is_directory else entry.name
        label = f"{prefix}{connector}{name}"
        description = directory_purpose(entry) if is_directory else purpose(entry)
        lines.append(format_entry(label, description))
        if is_directory:
            child_prefix = f"{prefix}{'    ' if is_last else '│   '}"
            lines.extend(render_children(entry, child_prefix))
    return lines


def generated_block() -> str:
    """Build the marked Markdown block replaced on every generation."""
    root_line = format_entry("src/lza_workbench/", directory_purpose(SOURCE_ROOT))
    tree = "\n".join([root_line, *render_children(SOURCE_ROOT)])
    return f"{BEGIN_MARKER}\n```text\n{tree}\n```\n{END_MARKER}"


def main() -> None:
    """Replace only the generated application-tree region in the architecture document."""
    document = DOCUMENT_PATH.read_text(encoding="utf-8")
    before, separator, remainder = document.partition(BEGIN_MARKER)
    if not separator:
        raise ValueError(f"Missing marker in {DOCUMENT_PATH}: {BEGIN_MARKER}")
    _, separator, after = remainder.partition(END_MARKER)
    if not separator:
        raise ValueError(f"Missing marker in {DOCUMENT_PATH}: {END_MARKER}")
    DOCUMENT_PATH.write_text(f"{before}{generated_block()}{after}", encoding="utf-8")


if __name__ == "__main__":
    main()
