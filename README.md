# LZA Workbench

A local CLI toolkit for initializing and managing AWS Landing Zone Accelerator (LZA) workspaces.

The repository contains the application source code, bundled LZA templates, and development assets. It does not contain customer workspaces or deployment artifacts.

## Repository Layout

- `src/` — Application source code and all execution logic.
- `tests/` — Automated tests.
- `src/lza_workbench/templates/` — Bundled templates shipped with the CLI.
- `src/lza_workbench/config/examples/` — Typed workspace configuration examples.
- `PROJECT.md` — Long-term project vision, architecture, and design principles.
- `TODO.md` — Feature backlog and implementation ideas.

## Quick Start

Clone the repository, install the development dependencies, and run the quality checks:

```bash
uv sync --group dev
uv run ruff check .
uv run pytest
```

Create a customer workspace from the packaged default template defined by `WorkspaceConfig`:

```bash
uv run lza init comm-it --skip-aws-check
```

The command prompts for missing customer/AWS values and writes:

```text
comm-it/
  lza-workspace.yaml
  aws-accelerator-config/
  aws-accelerator-installer/
  .lza/
    state.json
    logs/
```

Use `--dry-run` to preview the file operations without writing anything:

```bash
uv run lza init comm-it --dry-run --skip-aws-check
```

## Import an Existing Workspace

Adopt an existing customer-owned LZA configuration from the default workspace path,
derived from the customer name:

```bash
lza import comm-it
```

Override the default workspace path and, when needed, explicitly identify the existing configuration directory:

```bash
lza import comm-it \
  --workspace-dir /path/to/comm-it \
  --config-dir /path/to/comm-it/aws-accelerator-config
```

When `--workspace-dir` is omitted, import uses `<current-directory>/<customer-slug>`,
matching `lza init`. When `--config-dir` is omitted, import uses the configured local
path (`aws-accelerator-config`) inside the workspace. Missing metadata values are prompted
for in an interactive terminal and can be supplied explicitly for scripts:

```bash
lza import Comm-IT \
  --workspace-dir /path/to/comm-it \
  --aws-profile comm-it-root \
  --aws-region eu-west-1 \
  --lza-version v1.15.5
```

Import validates the existing configuration structure but never writes beneath
`aws-accelerator-config/`. It creates or updates only `lza-workspace.yaml` and
`.lza/state.json`. It validates the configured AWS profile unless `--skip-aws-check` is used.

Preview metadata changes without writing:

```bash
lza import comm-it --dry-run
```

When `lza init` finds an existing configuration directory, it stops and directs you to use
`lza import`. `lza init --force` retains its explicit reinitialization behavior.

## Workspace Configuration

`lza-workspace.yaml` is the declarative source of truth for a customer workspace. It is
loaded with `ruamel.yaml` and validated by nested Pydantic models. The top-level YAML keys
match `WorkspaceConfig`; nested sections match their corresponding model fields.

```yaml
customer:
  name: Example Customer
  slug: example-customer

aws:
  profile: example-root
  region: eu-west-1

lza:
  version: v1.15.5

configuration:
  local_path: aws-accelerator-config

pipelines:
  installer:
    name: AWSAccelerator-InstallerStack
  configuration:
    name: AWSAccelerator-Pipeline
```

Defaults are defined in `src/lza_workbench/core/workspace.py`; YAML supplies explicit
overrides. Unknown keys are rejected. See `src/lza_workbench/config/examples/` for minimal,
full, configuration-only, and installer-only examples.

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

Initialize a workspace after installing the CLI:

```bash
lza init comm-it --skip-aws-check
```

Reinstall after code changes to test latest local version:

```bash
uv tool install --reinstall .
```

## Current Status

The project is currently in the active development stage. Feature implementation is tracked in TODO.md.
