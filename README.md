# LZA Workbench

A local CLI toolkit for initializing and managing AWS Landing Zone Accelerator (LZA) projects.

The repository contains the application source code, reusable LZA templates, and development assets. It does not contain customer projects or deployment artifacts.

## Repository Layout

- `src/` — Application source code and all execution logic.
- `tests/` — Automated tests.
- `templates/` — Reusable starter LZA configuration templates.
- `PROJECT.md` — Long-term project vision, architecture, and design principles.
- `TODO.md` — Feature backlog and implementation ideas.

## Quick Start

Clone the repository, install the development dependencies, and run the quality checks:

```bash
uv sync --group dev
uv run ruff check .
uv run pytest
```

## Design Principles

- Keep business logic in Python.
- Customer workspaces live outside this repository.
- AWS authentication is managed externally.
- Prefer explicit, reviewable behavior over hidden automation.
- Keep the implementation modular and easy to extend.

## Development

Install dependencies:

```bash
uv sync --group dev
```

Run checks:

```bash
uv run ruff check .
uv run pytest
```

## Local CLI Installation

Install the project as a local CLI so it can be executed from any directory during development.

```bash
uv tool install .
```

Ensure your shell PATH includes uv's tool bin directory:

```bash
uv tool update-shell
```

Show where uv installs tool binaries:

```bash
uv tool dir --bin
```

Test from any directory:

```bash
lza
lza-workbench
```

Reinstall after code changes to test latest local version:

```bash
uv tool install --reinstall .
```

## Current Status

The project is currently in the active development stage. Feature implementation is tracked in TODO.md.
