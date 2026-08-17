# LZA Workbench

A local CLI toolkit for initializing and managing AWS Landing Zone Accelerator (LZA) workspaces.

The repository contains the application source code, bundled LZA templates, and development assets. It does not contain customer workspaces or deployment artifacts.

## Repository Layout

- `src/` — Application source code and all execution logic.
- `tests/` — Automated tests.
- `src/lza_workbench/resources/` — Bundled installer templates, starter customer configuration,
  and workspace examples shipped with the CLI.
- [`PROJECT.md`](PROJECT.md) — Durable project vision, architecture, and design principles.
- [`TODO.md`](TODO.md) — Active feature backlog and unresolved design work.
- [`docs/DONE.md`](docs/DONE.md) — Concise history of completed milestones.

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

Adopt an existing customer-owned LZA configuration by directory:

```bash
lza import /path/to/comm-it
```

From inside that directory, use `.`:

```bash
lza import .
```

Use `--lza-config-dir` when the configuration folder is not the default
`aws-accelerator-config`. Import reads valid existing metadata as the prompt defaults;
explicit options replace them:

```bash
lza import /path/to/comm-it \
  --customer-name Comm-IT \
  --aws-profile comm-it-root \
  --aws-region eu-west-1 \
  --lza-version v1.15.5
```

Import validates the existing configuration structure but never writes beneath
`aws-accelerator-config/`. It creates or updates only `lza-workspace.yaml` and
`.lza/state.json`. It validates the configured AWS profile unless `--skip-aws-check` is used.

Preview metadata changes without writing:

```bash
lza import /path/to/comm-it --dry-run
```

When `lza init` finds an existing directory, it stops and directs you to use `lza import`.
`lza init --force` overwrites generated metadata only and leaves the customer configuration
directory unchanged.

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

Defaults are defined by `WorkspaceConfig` in `src/lza_workbench/workspace/schema.py`; YAML supplies
explicit overrides. Unknown keys are rejected. See
`src/lza_workbench/resources/workspace_examples/` for minimal, full, configuration-only, and
installer-only examples.

### AWS authentication

LZA Workbench never stores AWS access keys or session tokens in `lza-workspace.yaml`.
Authentication is external to the tool: use an AWS profile backed by IAM Identity Center (SSO)
or shared credentials, or configure `aws.role_arn` to assume a role using external source
credentials (such as environment or instance/container credentials). The optional
`aws.account_id` is a safety guard: AWS-mutating commands stop if STS resolves a different
account.

Existing workspace YAML containing `access_key` or `secret_access_key` is rejected with a
migration error. Remove the secret fields and configure authentication outside the workspace.

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

The project is in active development. Feature work is tracked in [`TODO.md`](TODO.md).
