# Completed Work Log

Concise historical record of completed features, major architecture decisions, and refactors in LZA Workbench.

Work is moved here from `TODO.md` only after implementation, integration, code review, and validation/tests are complete.

## 2026-09

### Configuration Pull & Push Web Actions (v0.34.0)
- **Configuration Details Actions**: Added "Pull Configuration" and "Push Configuration" actions to the Configuration Details page (`#/configuration`).
- **Two-phase Prepare/Apply Pattern**: Non-mutating preparation step (`POST /api/config/pull/prepare`, `POST /api/config/push/prepare`) assesses remote target (S3 bucket or Git remote), tracked files count, branch, and detects overwrite/conflict risks before mutating anything.
- **Workflow-driven Confirmation UI**: Risky operations (e.g. uncommitted local changes, S3 overwrite) display structured warning reasons returned directly by backend workflows with an explicit confirmation checkbox; safe operations allow immediate execution.
- **Structured Apply & Refresh**: Applying operations (`POST /api/config/pull/apply`, `POST /api/config/push/apply`) passes explicit user intent, displays success message with file diff metrics, and automatically refreshes configuration status.
- **Layering & Testing**: Maintained strict architectural import boundaries (`web` -> `workflows` only) verified via `tests/test_package.py` and unit test coverage in `tests/web/test_status.py`.

### Web UI & Installer Settings Bugfixes (v0.33.1)
- **Bug 1 & 2 (Offline mode notices & recorded badge color)**: Fixed empty yellow notice box persisting after login/refresh/back when offline; displayed clear warning that statuses are not live but last recorded states; ensured recorded offline states are styled amber (warning) rather than misleading green (success).
- **Bug 3 (Card naming)**: Renamed "Canonical Settings" card on the Installer page to "Current Settings" for concise readability.
- **Bug 4 (Structured form layout)**: Refactored flat 2-column parameter inputs into 4 titled, structured card sections: "Source & Repository", "Mandatory Accounts", "Architecture & Environment", and "Pipeline & Operations".
- **Bug 5 (Reactive conditional fields)**: Added instantaneous client-side show/hide toggling for conditional inputs: toggling `EnableApprovalStage` shows/hides `ApprovalStageNotifyEmailList` and manages required status; toggling `RepositorySource` switches between GitHub, CodeCommit, and S3 parameters; hidden fields are omitted from client validation.
- **Bug 6 (Reset to written configuration)**: Implemented confirmation modal dialog before resetting installer settings; form fields revert directly to the written parameters from `lza-workspace.yaml` with reactive conditional updates and zero AWS calls; added `pending_installer_parameters` tracking in `WorkspaceState` to record changed parameters relative to deployed state until deployment.

### Installer Settings & Deployment Web Page (v0.33.0)
- Built the Installer Settings and Deployment page in the Web interface, accessible from the Overview Installer card (`#/installer`) with breadcrumb and hash-based navigation.
- Rendered canonical settings, deployed CloudFormation stack status, deployed version, state alignment, configuration drift warnings, and pipeline summary.
- Rendered dynamic settings form controls generated from the installer CloudFormation template schema (`InstallerForm`), with `<select>` dropdowns for allowed values, input patterns, and descriptions.
- Added client-side and server-side validation before saving installer settings to `lza-workspace.yaml`.
- Integrated read-only deployment preview action (`POST /api/installer/plan`) displaying CloudFormation operation, parameter diffs, CodeCommit source plan, and GitHub secret warnings without executing mutations.
- Enforced strict architectural layering (`web` -> `workflows` only) with tests in `test_package.py` and `test_status.py`.

### Configuration Details Web Page (v0.31.0)
- Built a dedicated read-only Configuration Details page in the Web interface, opened from the Overview Configuration card or direct link/hash navigation (`#/configuration`).
- Supported unified hash routing (`#/` and `#/overview` for Overview, `#/configuration` for Configuration Details) with back button and browser history support.
- Added `/api/status/config` endpoint serializing local config state, YAML file discovery, repository/provider inspection (S3, CodeCommit, CodeConnection, Git), Git working tree status, remote sync parity, configuration pipeline diagnostics, and synchronization history.
- Presented comprehensive diagnostic warnings and recommendations, file tags, pipeline execution stages, and provider-specific metadata.
- Preserved strict architectural layering with fast AST tests in `test_package.py` and endpoint coverage in `test_status.py`.

### S3 Configuration Remote Synchronization & Status Workflow (v0.30.8)
- Added S3 remote sync parity tracking comparing local configuration against canonical remote S3 archives without downloading objects into memory.
- Tracked transfer state in `.lza/state.json` (`config_artifact_etag`, `config_sync_digest`, `config_artifact_version_id`) across `lza config push` and `lza config pull`.
- Attached `x-amz-meta-lza-content-digest` user metadata on S3 uploads for stateless parity checks across workstations.
- Unified `RemoteSyncStatus` model across Git and S3 repositories for CLI (`lza status`, `lza status config`) and Web UI (`overview.js` green status pill).
- Simplified sync evaluation to fast AWS S3 header checks (`head_object`) and state comparison; untracked remote archives cleanly report `Unknown` ("Never synced with workspace").

### Local Web Overview Skeleton
- Added `lza ui`, an on-demand loopback FastAPI/Uvicorn server for one launch-selected workspace.
- Added a framework-free static Overview page backed by `GET /api/status`, reusing the root-status workflow and presenting workspace, AWS, installer, configuration, pipeline, and health summaries.
- Preserved read-only behavior and translated expected workspace failures into browser-safe API responses; AWS-offline responses continue to show recorded status where available.

### Root Status Workflow Coherence & Git Health Independence
- Unified `get_root_status_workflow` into a single coherent observation pass, loading one `WorkspaceContext` and resolving one `AwsExecutionContext` without nesting `get_config_status_workflow`.
- Removed redundant compatibility fields and `config_status` from `RootStatusResult`, preserving structured summaries (`installer`, `installer_pipeline`, `configuration_repo`, `configuration_pipeline`, `health`).
- Replaced string `remote_sync_summary` in `ConfigurationRepoSummary` with structured `GitRemoteSyncStatus | None` model (`git_sync_status`), decoupling divergence health logic from human-readable summary text (`status == "Diverged"`).
- Decoupled local Git sync evaluation from AWS availability, allowing local tracking branch status to be observed even when AWS credentials or sessions are expired/unavailable.
- Preserved CLI presentation logic in `render_root_status`, reading `git_sync_status.summary` directly.

### Testing Strategy Overhaul & Production Shim Removal (v0.30.1)
- Removed production test shims (`sleeper` and `time_provider` parameters) from `pipeline_watch_workflow` and `deploy_configuration_workflow`, restoring clean production signatures and direct `time.sleep`/`time.time` calls.
- Deleted `tests/aws/` suite (8 files) and 11 mock-heavy `tests/cli/` test files that asserted internal `unittest.mock` dictionaries against external AWS services.
- Migrated the critical `boto3` centralization invariant check into `tests/test_package.py` as a fast AST architectural test.
- Preserved real CLI and domain tests (`test_output.py`, `test_workspace_init.py`, `test_workspace_import.py`, `test_config_init.py`, `test_package.py`, schemas, and templates), cutting test suite execution to ~6 seconds (279 passed, 0 failures).
- Updated `AGENTS.md`, `PROJECT.md`, `README.md`, `TODO.md`, and `docs/REVIEW.md` to codify the CLI-first validation policy and zero test pollution rules.

### S3 Configuration Synchronization Safeguards (v0.30.0)
- Included customer AWS Backup configuration by default and added root `.gitignore` packaging rules, preserving explicit workspace YAML exclusions. `.prettierignore` does not affect archive contents.
- Corrected archive diffs to compare files only, ignoring explicit ZIP directory records.
- Protected imported S3 workspaces without a synchronization baseline through confirmation or `--force`, with warnings during read-only previews.
- Persisted missing standard S3 bucket names in workspace YAML during push and pull; dry runs remain non-mutating.
- Validated packaging, CLI aliases, synchronization state, workspace persistence, and affected deployment/template behavior with focused regression tests.

### Pipeline Watch Initial Delay & Propagation Tolerance (v0.29.3)
- Added `initial_delay_seconds` (default 3.0s) in `watch_pipeline_workflow` and `deploy_configuration_workflow` before querying AWS CodePipeline for initial status, preventing race conditions immediately after pipeline start.
- Added graceful retry tolerance for `NOT_FOUND` execution responses during early polling to accommodate AWS eventual consistency.

### LZA Configuration Initialization Enhancements (v0.29.0)
- **Interactive Template Selection**: In `lza config init`, prompts user interactively when multiple packaged templates exist and `--template` is omitted, while automatically selecting the single template when only one exists. Keeps terminal prompting decoupled within the CLI layer.
- **S3-Backed Local Git Repository Initialization**: Automatically initializes a local Git repository and creates an initial commit containing generated configuration files when the remote repository type is Amazon S3.
- **Worktree Detection & Repository Protection**: Inspects Git worktree top-level to detect whether `aws-accelerator-config` already has `.git`, is tracked inside an existing parent Git worktree, or uses a Git-backed remote provider (CodeCommit, CodeConnections, Git), skipping Git initialization with structured feedback to prevent nested or competing repositories. Preserves `.git` and Git configuration on `--force` re-runs.

### Root Status Dashboard & Deprecation Cleanup (v0.28.0)
- **Enhanced `lza status`**: Promoted `lza status` to the primary high-level operational overview across workspace identity, installer stack & pipeline, configuration repository & pipeline, and overall deployment health.
  - Queries CloudFormation for installer stack status and deployed LZA version.
  - Queries CodePipeline for both installer and configuration pipeline existence, latest execution status, execution ID, start time, duration, active stage/action (when in progress), and failed stage/action with normalized root cause diagnostics (when failed).
  - Integrates configuration repository destination, local Git working tree state, and remote synchronization status.
  - Derives concise overall deployment health (`Healthy`, `Running`, `Attention Required`, `Incomplete`).
  - Provides graceful offline fallback when AWS authentication or live queries are unavailable, preserving existing AWS access warning notices, leveraging `.lza/state.json` runtime metadata with explicit `(Recorded)` labels, and reporting degraded visibility (`AWS Unavailable - Showing Last Known State`) without asserting health from cached data.
- **Removed Deprecated `lza status pipeline`**: Completely eliminated `lza status pipeline` CLI registration, command handlers, dedicated workflow, and tests without deprecation aliases, shims, or hidden commands.

---

## 2026-08

### Workspace & Project Setup
- Established Python project structure, package entrypoints (`lza`, `lza-workbench`), repository layout, `uv` configuration, and test suite.
- Defined core declarative architecture (`lza-workspace.yaml`), runtime execution state (`.lza/state.json`), and project documentation workflow.

### Core CLI Workflow Commands
- **`lza init`**: Customer workspace initialization with slug normalization, configuration copy, AWS profile validation, non-interactive execution, and dry-run support.
- **`lza import` & `lza import installer` / `lza installer import`**: Adopt existing local `aws-accelerator-config` without modifying customer files, validating layout and generating workspace metadata. Features full YAML syntax parsing with line/column diagnostics, version-aware official LZA schema validation, template provenance detection, interactive prompt for installer stack name (default: `"AWSAccelerator-InstallerStack"`), and live AWS CloudFormation stack parameter synchronization. Introduced dedicated `lza import installer` / `lza installer import` commands and workflow (`workflows/installer_import.py`) with domain sync functions centralized in `installer/sync.py` (`sync_installer_config`, `sync_installer_state`), while maintaining strict read-only status reporting across `lza status` commands.
- **`lza installer init` and `lza installer plan`**: `installer init` collects and persists CloudFormation parameters and workspace settings from the selected installer template, featuring automatic version normalization in official template download URLs to prevent 404s, conditional prompt filtering that only asks for parameters applicable to the selected installer and configuration sources, source-aware branch defaults, and version-aware packaged fallback diagnostics; `installer plan` reuses that configuration to inspect AWS CodeCommit and CloudFormation without modifying AWS resources.
- **`lza installer deploy`**: Reconcile installer desired state with AWS CloudFormation, validate assets bucket configuration and existence, upload installer template to Workbench S3 assets bucket with integrity validation, execute deployments via S3 `TemplateURL` (bypassing CloudFormation 51,200-byte inline body limits), track events, and record deployment metadata in `.lza/state.json`.
- **`lza bootstrap`**: Create or validate AWS prerequisite resources required by LZA Workbench. Idempotently creates/validates the versioned, KMS-encrypted Workbench assets S3 bucket (`s3-lza-workbench-assets-<account-id>-<region>`), the `lza-config-source` CodeCommit configuration repository (when `ConfigurationRepositoryLocation=codecommit`), and the AWS Secrets Manager secret (`accelerator/github-token`) with repository accessibility validation (when `RepositorySource=github`). Features interactive prompting for missing GitHub Personal Access Tokens with direct secret creation, non-fatal warnings with `--allow-missing-github-secret`, strict validation-only semantics on imported workspaces, planned action preview with confirmation, and state tracking in `lza-workspace.yaml` and `.lza/state.json`.
- **`lza config push` & `lza config upload`**: Unified local-to-remote configuration synchronization workflow (`workflows/config_push.py`) supporting Amazon S3, AWS CodeCommit, AWS CodeConnections, and Git repositories. Validates local configuration templates, the configured deployable branch, and Git remote against `lza-workspace.yaml`; dry runs do not mutate Git configuration. S3 synchronization uses the fixed LZA archive name and object key. Successful pushes record operational synchronization state in `.lza/state.json`. `lza config upload` serves as a human-friendly alias routing directly through the canonical push workflow.
- **`lza config pull` & `lza config download`**: Unified remote-to-local configuration synchronization workflow (`workflows/config_pull.py`) supporting Amazon S3, AWS CodeCommit, AWS CodeConnections, and Git repositories. Validates remote source, protects uncommitted local changes (stashing with `--force`), clones/fetches/pulls configured branches or downloads/extracts S3 archives, validates post-synchronization template structure, and records operational state in `.lza/state.json`. `lza config download` serves as a human-friendly alias routing directly through the canonical pull workflow.
- **`lza config deploy`**: Complete end-to-end customer configuration deployment workflow orchestrating `config push -> pipeline start -> pipeline watch`. Synchronizes local configuration to configured remote destination (S3, CodeCommit, CodeConnections, Git), triggers CodePipeline execution, records execution ID in `.lza/state.json`, and monitors stage/action status until completion with live updates, failure diagnostics, and `--no-watch` / `--dry-run` support.
- **`lza pipeline start` & `lza pipeline watch`**: Reusable standalone CLI commands and workflows (`workflows/pipeline_start.py`, `workflows/pipeline_watch.py`) for triggering pipeline executions without config re-synchronization and monitoring active/historical executions. Features live updating polling progress (`PipelineWatchMonitor`), accurate true execution duration calculation from CodePipeline metadata (omitting duration when unknown), concise breakdown table with short action status details (`CodeBuild BUILD phase failed (exit status 1)`) suppressing raw buildspec/shell script dumps, omission of pending/unexecuted stages in failure mode, a single deduplicated `2. Failure` section attributing `Stage`, `Action`, `Resource` (e.g. `AWSAccelerator-PrepareStack-...`), and normalized root cause `Error` (with wrapper prefixes and presentation emojis stripped), build console links, `--verbose` support for full breakdown and raw diagnostic context, and shared presentation across `lza pipeline watch` and `lza config deploy`.
- **`lza status`**: Strictly read-only status dashboard with overall, installer, configuration, and pipeline views; `lza installer status` remains an installer-view alias. Recommends `lza installer import` upon detecting configuration drift.
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

### CLI Presentation Standardization
- **Unified Presentation Primitives (`cli/output.py`)**: Centralized `format_timestamp` (normalizing all datetime representations to `YYYY-MM-DD HH:MM:SS UTC`), `format_status` (humanizing raw AWS status enums e.g. `UPDATE_COMPLETE` -> `Update Complete` with standardized Rich color styles), `render_workspace_header` (standardizing top-level workspace banners), and `render_failure_section` (standardizing pipeline root cause failures).
- **Normalized Command Renderers**: Standardized section titles, numbering, labels, and formatting across `status`, `status installer` (`installer status`), `status config` (`config status`), `status pipeline`, `pipeline watch`, and `config deploy`.
- **Cleaned Storage Leaks & Unnecessary IDs**: Suppressed internal `.lza/state.json` file paths in section headings in favor of domain terms (`Synchronization History`, `Execution History`), and omitted full caller/stack ARNs from default views while retaining vital account/region/profile context.
- **Multi-line Diagnostic Extraction & Custom Resource Error Resolution (`aws/codebuild.py`)**: Enhanced CloudWatch / CodeBuild diagnostic parsing with multi-line error block aggregation and lookahead. Accurately extracts root cause messages from CDK `DeploymentError: Resource updates failed:`, Custom Resource failures (`Received response status [FAILED] from custom resource. Message returned: ...`), and CloudFormation resource creation errors across multiple lines.

