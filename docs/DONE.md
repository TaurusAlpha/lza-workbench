# Completed Work Log

Concise historical record of completed features, major architecture decisions, and refactors in LZA Workbench.

Work is moved here from `TODO.md` only after implementation, integration, code review, and validation/tests are complete.

---

## 2026-08

### Workspace & Project Setup
- Established Python project structure, package entrypoints (`lza`, `lza-workbench`), repository layout, `uv` configuration, and test suite.
- Defined core declarative architecture (`lza-workspace.yaml`), runtime execution state (`.lza/state.json`), and project documentation workflow.

### Core CLI Workflow Commands
- **`lza init`**: Customer workspace initialization with slug normalization, configuration copy, AWS profile validation, non-interactive execution, and dry-run support.
- **`lza import`**: Adopt existing local `aws-accelerator-config` without modifying customer files, validating layout and generating workspace metadata.
- **`lza installer init` and `lza installer plan`**: `installer init` collects and persists every parameter in the selected installer template; `installer plan` reuses that configuration to inspect AWS CodeCommit and CloudFormation without modifying AWS resources.
- **`lza installer deploy`**: Reconcile installer desired state with AWS CloudFormation, validate assets bucket configuration and existence, upload installer template to Workbench S3 assets bucket with integrity validation, execute deployments via S3 `TemplateURL` (bypassing CloudFormation 51,200-byte inline body limits), track events, and record deployment metadata in `.lza/state.json`.
- **`lza bootstrap`**: Create or validate AWS prerequisite resources required by LZA Workbench. Idempotently creates/validates the versioned, KMS-encrypted Workbench assets S3 bucket (`s3-lza-workbench-assets-<account-id>-<region>`), presenting planned actions and confirmation, updating `lza-workspace.yaml` and `.lza/state.json`.
- **`lza config push` & `lza config upload`**: Unified local-to-remote configuration synchronization workflow (`workflows/config_push.py`) supporting Amazon S3, AWS CodeCommit, AWS CodeConnections, and Git repositories. Validates local configuration templates and Git working tree state (clean working tree and commit verification), auto-derives CodeCommit remote URLs when unconfigured, pushes branches, and records operational synchronization state in `.lza/state.json`. `lza config upload` serves as a human-friendly alias routing directly through the canonical push workflow.
- **`lza status`**: Single read-only status dashboard for workspace state, installer details, configuration sources, and pipeline execution metadata.


### AWS Integration Architecture Refactoring
- Centralized boto3 session and client creation into `AwsClientFactory` across all service modules, eliminating direct `boto3` calls outside the factory.

### Modular Architecture Refactoring (v0.14.0)
- **Layering & Separation**: Established strict unidirectional architecture `cli -> workflows -> features/AWS`. Workflows and domain modules are completely decoupled from CLI presentation frameworks (`rich`, `typer`).
- **Workflows Extraction**: Extracted pure, typed workflows returning structured results for workspace initialization (`workflows/workspace_init.py`), workspace import (`workflows/workspace_import.py`), configuration operations (`workflows/config_download.py`, `workflows/config_upload.py`), installer operations (`workflows/installer_plan.py`, `workflows/installer_deploy.py`), and status queries (`workflows/status_*.py`).
- **CLI Presentation Separation**: Separated CLI presentation into `cli.output` (Rich console and table rendering) and `cli.input` (interactive prompting and option resolution).
- **Feature Packages**: Reorganized domain models, state management, and schemas into owning packages (`workspace`, `installer`, `configuration`, `aws`).
- **AWS Adapters Isolation**: Decoupled `aws` adapters to accept only primitive inputs (`version_ref`, strings) without importing workspace or feature policy.
- **Bounded Monitoring & Failure-Safe Archives**: Bounded CloudFormation event-stream error recovery and implemented failure-safe backup/rollback for archive extraction.
- **Architectural Tests**: Added AST-based test suite verifying strict layer boundaries, AWS adapter isolation, and CLI workflow delegation.
- **Removed Legacy Scaffolding**: Deleted deprecated `commands/`, `core/`, `utils/`, `workspace.models`, and root shim modules.
