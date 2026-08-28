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
- **`lza import`**: Adopt existing local `aws-accelerator-config` without modifying customer files, validating layout and generating workspace metadata. Features full YAML syntax parsing with line/column diagnostics, version-aware official LZA schema validation (`global-config`, `organization-config`, `accounts-config` with mandatory accounts, `network-config`, `security-config`, `iam-config`), remote/Git repository template provenance auto-detection (AWS CodeCommit, Git remotes, commits, branch, and tracked file counts), automatic/`--repair` metadata restoration for partial or corrupted metadata, live AWS CloudFormation stack introspection (extracting deployed parameters and synchronizing `lza-workspace.yaml` and `.lza/state.json`), imported workspace operational state tracking (`imported: true`), and context-aware next-step recommendations.
- **`lza installer init` and `lza installer plan`**: `installer init` collects and persists every parameter in the selected installer template, with source-aware branch defaults and version-aware packaged fallback diagnostics; `installer plan` reuses that configuration to inspect AWS CodeCommit and CloudFormation without modifying AWS resources.
- **`lza installer deploy`**: Reconcile installer desired state with AWS CloudFormation, validate assets bucket configuration and existence, upload installer template to Workbench S3 assets bucket with integrity validation, execute deployments via S3 `TemplateURL` (bypassing CloudFormation 51,200-byte inline body limits), track events, and record deployment metadata in `.lza/state.json`.
- **`lza bootstrap`**: Create or validate AWS prerequisite resources required by LZA Workbench. Idempotently creates/validates the versioned, KMS-encrypted Workbench assets S3 bucket (`s3-lza-workbench-assets-<account-id>-<region>`), the `lza-config-source` CodeCommit configuration repository (when `ConfigurationRepositoryLocation=codecommit`), and the AWS Secrets Manager secret (`accelerator/github-token`) with repository accessibility validation (when `RepositorySource=github`). Features interactive prompting for missing GitHub Personal Access Tokens with direct secret creation, non-fatal warnings with `--allow-missing-github-secret`, strict validation-only semantics on imported workspaces, planned action preview with confirmation, and state tracking in `lza-workspace.yaml` and `.lza/state.json`.
- **`lza config push` & `lza config upload`**: Unified local-to-remote configuration synchronization workflow (`workflows/config_push.py`) supporting Amazon S3, AWS CodeCommit, AWS CodeConnections, and Git repositories. Validates local configuration templates, the configured deployable branch, and Git remote against `lza-workspace.yaml`; dry runs do not mutate Git configuration. S3 synchronization uses the fixed LZA archive name and object key. Successful pushes record operational synchronization state in `.lza/state.json`. `lza config upload` serves as a human-friendly alias routing directly through the canonical push workflow.
- **`lza config pull` & `lza config download`**: Unified remote-to-local configuration synchronization workflow (`workflows/config_pull.py`) supporting Amazon S3, AWS CodeCommit, AWS CodeConnections, and Git repositories. Validates remote source, protects uncommitted local changes (stashing with `--force`), clones/fetches/pulls configured branches or downloads/extracts S3 archives, validates post-synchronization template structure, and records operational state in `.lza/state.json`. `lza config download` serves as a human-friendly alias routing directly through the canonical pull workflow.
- **`lza config deploy`**: Complete end-to-end customer configuration deployment workflow orchestrating `config push -> pipeline start -> pipeline watch`. Synchronizes local configuration to configured remote destination (S3, CodeCommit, CodeConnections, Git), triggers CodePipeline execution, records execution ID in `.lza/state.json`, and monitors stage/action status until completion with live updates, failure diagnostics, and `--no-watch` / `--dry-run` support.
- **`lza pipeline start` & `lza pipeline watch`**: Reusable standalone CLI commands and workflows (`workflows/pipeline_start.py`, `workflows/pipeline_watch.py`) for triggering pipeline executions without config re-synchronization and monitoring active/historical executions. Features live updating polling progress (`PipelineWatchMonitor`), concise failure summaries omitting unreached/pending stages, prioritized failed stage and action reporting (`Stage: <Stage> > Action: <Action>`), automated extraction of high-signal root causes from CloudWatch Logs and CodeBuild phases, suppression of raw buildspec commands and wrapper boilerplate from normal output, deduplication of repeated AWS/CloudFormation error messages, `--verbose` support for full breakdown and raw diagnostic context, and shared presentation across `lza pipeline watch` and `lza config deploy`.

- **`lza status`**: Read-only status dashboard with overall, installer, configuration, and pipeline views; `lza installer status` remains an installer-view alias.
- **`lza status config` & `lza config status`**: Comprehensive configuration repository status workflow (`workflows/status_config.py`) and CLI presentation reporting provider configuration (Amazon S3, AWS CodeCommit, AWS CodeConnections, Git), remote source existence and accessibility checks (S3 bucket and archive inspection, CodeCommit repository and branch verification, CodeConnections status validation), local Git working tree status (branch, commit, uncommitted changes count) and remote revision synchronization comparison (in-sync, ahead, behind, diverged), live CodePipeline configuration execution status integration, and automated diagnostic warnings. `lza config status` operates as a direct alias for `lza status config`, and the configuration summary is reused in `lza status`.



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

### Test Suite Modernization & Architectural Alignment
- **Mirrored Test Hierarchy**: Reorganized flat test directory into package-aligned test packages matching source structure (`tests/aws/`, `tests/workspace/`, `tests/configuration/`, `tests/installer/`, `tests/workflows/`, `tests/cli/`).
- **Centralized Test Fixtures (`conftest.py`)**: Consolidated duplicate setup logic and created reusable test fixtures for AWS caller identity, execution context, workspace configurations, and temporary initialized/configured workspaces.
- **Deduplication & Layer Purity**: Eliminated redundant and duplicate tests across bootstrap, deploy, and S3 modules. Decoupled CLI tests from internal domain algorithm testing and isolated workflow orchestration tests.
