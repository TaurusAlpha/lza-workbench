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
- **`lza installer plan`**: Read installer parameters from `lza-workspace.yaml`, resolve templates, inspect AWS CodeCommit and deployment status, and generate non-mutating action plans.
- **`lza installer deploy`**: Reconcile installer desired state with AWS CloudFormation, execute deployments, track events, and record deployment metadata in `.lza/state.json`.
- **`lza config upload`**: Validate configuration placeholders, package customer `aws-accelerator-config`, upload to S3 configuration sources, and log upload state.
- **`lza config download`**: Download customer configuration from S3 configuration sources with
  `--dry-run`, optional archive extraction, and operational state updates.
- **`lza status`**: Single read-only status dashboard for workspace state, installer details, configuration sources, and pipeline execution metadata.

### AWS Integration Architecture Refactoring
- Centralized boto3 session and client creation into `AwsClientFactory` across all service modules, eliminating direct `boto3` calls outside the factory.

### Modular Architecture Refactoring (v0.14.0)
- **Layering & Separation**: Established strict unidirectional architecture `cli -> workflows -> features/AWS`. Workflows and domain modules are completely decoupled from CLI/presentation frameworks (`rich`, `typer`).
- **Workflows Extraction**: Extracted pure, typed workflows returning structured results for workspace initialization (`workflows/workspace_init.py`), workspace import (`workflows/workspace_import.py`), configuration operations (`workflows/config_download.py`, `workflows/config_upload.py`), installer operations (`workflows/installer_plan.py`, `workflows/installer_deploy.py`), and status queries (`workflows/status_*.py`).
- **CLI Package**: Consolidated interactive prompting, confirmation handlers, Rich panel/table rendering, and CLI command definitions under `lza_workbench.cli`.
- **Durable Error Ownership**: Consolidated application error definitions in `errors.py`.
- **Feature Packages**: Reorganized domain models and schemas into owning packages (`workspace`, `installer`, `config`, `aws`).
- **Safe Defaults & Fixes**: Restored safe config download archive defaults, honored exact configuration archive keys, ensured proper installer-plan readiness, restricted installer template fallback by version, failed closed on unexpected CodeCommit errors, and primed source credentials before role assumption.
- **Architectural Tests**: Added AST-based test suite verifying strict layer boundaries and preventing domain/workflow modules from importing presentation frameworks or higher layers.
- **Removed Legacy Layers**: Deleted deprecated `commands/`, `core/`, `utils/`, and root shim modules.


