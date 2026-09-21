# LZA Workbench

LZA Workbench is a local Web and CLI application for initializing and operating customer-specific
AWS Landing Zone Accelerator (LZA) workspaces.

Customer workspaces and deployment artifacts live outside this repository. The repository contains
the application, tests, bundled installer templates, starter LZA configuration, and workspace
examples.

## Development Setup

Install the project and development dependencies:

```bash
uv sync --group dev
```

Run the CLI directly from the checkout:

```bash
uv run lza --help
```

Install the current checkout as a local command for use from customer workspace directories:

```bash
uv tool install --reinstall .
```

If `lza` is not found, add the uv tool directory to the shell path:

```bash
uv tool update-shell
```

Reinstall the tool after source changes when testing the latest checkout.

Useful development checks:

```bash
uv run ruff check .
uv run pytest tests/test_package.py
# uv run pytest  # Full suite when needed
```

## Start a New Workspace

Create a workspace outside this repository:

```bash
lza init example \
  --workspace-dir /path/to/customers/example \
  --aws-profile example-root \
  --aws-region eu-west-1
```

Use `--dry-run` to preview the generated files. Use `--skip-aws-check` only when the configured AWS
identity cannot or should not be validated during initialization.

Continue from the new workspace directory:

```bash
cd /path/to/customers/example
lza installer init
lza config init
lza installer plan
```

When the plan is correct, deploy the installer and then synchronize and deploy the customer
configuration:

```bash
lza installer deploy
lza config deploy
lza status
```

`lza installer plan` is non-mutating. Use `--dry-run` on mutating commands when available to inspect
their planned actions.

## Import an Existing Workspace

Adopt an existing customer-owned LZA configuration:

```bash
lza import /path/to/customers/example
```

Use `.` for the current directory or `--lza-config-dir` when the configuration directory is not
`aws-accelerator-config`:

```bash
cd /path/to/customers/example
lza import . --lza-config-dir ./configuration
```

Import validates the existing configuration but does not modify files inside the customer-owned
configuration directory. Use `--dry-run` to preview metadata changes and `--repair` when existing
Workbench metadata is incomplete or corrupted.

## Local Web Interface

Start the Web interface for the current workspace:

```bash
lza ui
```

Or select a workspace explicitly:

```bash
lza ui --workspace-dir /path/to/customers/example
lza ui --no-browser --port 8080
```

The server listens on `127.0.0.1:8000` by default and is intended for local, single-user operation.
The Web interface supports workspace setup, operational status, installer settings and planning,
configuration pull/push/deploy, pipeline inspection, and LZA uninstallation. Installer deployment
itself remains a CLI operation.

## CLI Command Reference

The table lists the flags most useful to remember, not every available option. Run
`lza <command> --help` for the authoritative argument and flag list.

| Command | Purpose | Useful flags |
| --- | --- | --- |
| `lza init <customer-name>` | Create a new workspace and Workbench metadata. | `--workspace-dir`, `--aws-profile`, `--aws-role-arn`, `--aws-region`, `--lza-version`, `--dry-run`, `--force`, `--skip-aws-check` |
| `lza import [workspace-dir]` | Adopt an existing LZA configuration and create or repair Workbench metadata. | `--lza-config-dir`, `--customer-name`, `--aws-profile`, `--aws-region`, `--lza-version`, `--installer-stack-name`, `--dry-run`, `--force`, `--repair` |
| `lza ui` | Start the local Web interface. | `--workspace-dir`, `--host`, `--port`, `--no-browser` |
| `lza status` | Show the overall workspace and deployment status. | — |
| `lza status installer` | Show detailed installer status. Alias: `lza installer status`. | — |
| `lza status config` | Show local/remote configuration and pipeline status. Alias: `lza config status`. | — |
| `lza installer init` | Collect and save installer parameters. | `--management-account-email`, `--log-archive-account-email`, `--audit-account-email`, `--accelerator-prefix`, `--dry-run`, `--no-save` |
| `lza installer plan` | Inspect the installer changes required in AWS. | `--dry-run` |
| `lza installer deploy` | Create or update the installer CloudFormation stack. | `--dry-run`, `--force` |
| `lza installer import` | Reconcile deployed installer parameters and template data into the workspace. | `--installer-stack-name`, `--dry-run` |
| `lza config init` | Create local LZA configuration from a bundled template. | `--template`, `--dry-run`, `--force` |
| `lza config pull` | Synchronize remote configuration into the local workspace. Alias: `download`. | `--dry-run`, `--force`, `--extract` / `--no-extract` |
| `lza config push` | Synchronize local configuration to the configured remote repository. Alias: `upload`. | `--dry-run`, `--force` |
| `lza config deploy` | Push configuration, start its pipeline, and optionally watch it. | `--dry-run`, `--no-watch`, `--verbose` |
| `lza pipeline start` | Start a configured LZA pipeline without synchronizing configuration. | `--pipeline-name`, `--dry-run`, `--allow-concurrent` |
| `lza pipeline watch` | Monitor an existing pipeline execution. | `--pipeline-name`, `--execution-id`, `--poll-interval`, `--verbose` |
| `lza uninstall` | Plan or remove the LZA solution across accounts and regions. | `--regions`, `--all-regions`, `--accounts`, `--dry-run`, `--delete-s3-buckets`, `--delete-retained-resources`, `--skip-installer`, `--skip-pipeline` |

## Workspace Files

`lza-workspace.yaml` is the declarative source of truth for a customer workspace. It stores customer
identity, AWS context, LZA version, installer settings, configuration-repository settings, and
pipeline preferences.

`.lza/state.json` stores operational information observed or produced while commands run. It is not
a replacement for declarative workspace configuration.

A typical initialized workspace starts with:

```text
example/
  lza-workspace.yaml
  aws-accelerator-installer/
  .lza/
    state.json
    logs/
```

`lza config init` creates the customer `aws-accelerator-config/` directory from the selected bundled
template.

## Configuration Synchronization

Use `lza config pull` to bring the configured remote source into the workspace and `lza config push`
to publish local configuration without starting the pipeline. `lza config deploy` performs the push
and starts the configuration pipeline.

For S3-backed configuration, archive exclusions come from `configuration.packaging.exclude` in
`lza-workspace.yaml` and the workspace root `.gitignore`. Use `--dry-run` to inspect synchronization
before changing local or remote content.

## AWS Authentication

LZA Workbench does not store AWS access keys or session tokens in `lza-workspace.yaml`. Use an AWS
profile, IAM Identity Center configuration, environment or workload credentials, or an external
credential source with `aws.role_arn`.

The optional `aws.account_id` acts as a safety guard: AWS-mutating operations stop when STS resolves
a different account.

## Uninstallation Safety

Always run an uninstallation preview first:

```bash
lza uninstall --dry-run
```

Deleting S3 buckets or resources retained by CloudFormation requires explicit flags. Review the
planned accounts, regions, stacks, buckets, and retained resources before applying the operation.
