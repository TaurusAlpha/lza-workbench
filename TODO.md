# LZA Workbench TODO

Historical record of completed features is recorded in [`docs/DONE.md`](file:///Users/andreyv/Projects/personal/lza-workbench/docs/DONE.md).
This file tracks active, planned, unresolved, refactoring, and technical-debt work.

## Refactoring

- [] Follow the architectural direction in [`docs/refactor.md`](docs/refactor.md).
- [] Work through the incremental learning checklist in
  [`docs/refactor_steps.md`](docs/refactor_steps.md).

## CLI Commands

- [x] `lza init`
- [x] `lza import`
- [x] `lza installer plan`
- [x] `lza installer deploy`
- [] `lza uninstall`
- [x] `lza config upload`
- [x] `lza config download`
- [] `lza config deploy`
- [] `lza pipeline start`
- [] `lza pipeline watch`
- [x] `lza status`
- [] `lza doctor`

### `lza init`

Create a new customer-specific LZA workspace.

- [] Support selecting a packaged template when multiple templates exist.
- [] Init local git repository in LZA configuration directory and "init" commit.
  Check for correlation if configuration repo is already stored in Git or CodeCommit or other supported repository.

### `lza import`

Adopt an existing local LZA configuration without modifying customer-owned files.

- [] Repair missing or invalid workspace metadata.
- [x] Support forced metadata replacement.
- [] Parse and validate imported YAML content.
- [] Integrate version-aware official LZA schema validation.
- [] Record or resolve remote/Git template provenance.

### `lza installer plan`

Resolve and persist installer configuration, then show the actions required to deploy the LZA installer without modifying AWS resources.

- [] Collect every parameter exposed by the selected installer template.
- [] Apply documented template defaults and explicit workspace defaults where appropriate.
- [] Preserve a user's existing accepted values when defaults change.
- [] Require a local template when the template must be modified, including when anonymous data sharing is disabled.
- [] Determine whether to support both the official remote template for unmodified deployments and a local template for modified deployments, or always standardize on a local template.

### `lza installer deploy`

Reconcile the locally configured installer desired state with AWS for both initial deployment and later updates.

- [] Ask for confirmation before applying changes unless confirmation is explicitly bypassed.
- [] Prepare and synchronize installer source code across Amazon S3, AWS CodeCommit, and the official AWS GitHub repository when the configured LZA version or source settings require it.
- [] Define provider-specific prerequisites, version/ref resolution, packaging, upload, and drift detection.
- [] Keep source preparation separate from customer `aws-accelerator-config` management.
- [] Follow the AWS source-location requirements for S3 packaging and synthesized installer parameters: <https://docs.aws.amazon.com/solutions/latest/landing-zone-accelerator-on-aws/source-code-location.html>.

### `lza uninstall`

Uninstall the LZA solution rather than deleting only the installer stack.

Implementation checklist:

- [] Inventory the Installer and Core pipeline stacks and additional LZA stacks across managed accounts and Regions.
- [] Detect and explain termination protection before deletion.
- [] Show the resources that would be removed and those retained by AWS deletion policies.
- [] Offer explicit preservation modes for customer data and other retained resources.
- [] Require confirmation unless `--force` is specified.
- [] Delete stacks in dependency-safe reverse deployment order.
- [] Optionally remove retained S3 buckets and other explicitly selected resources.
- [] Preserve source repositories and customer configuration by default.
- [] Record progress so an interrupted uninstall can be inspected or resumed safely.
- [] Remove deployment metadata from `.lza/state.json` only after the corresponding resources are removed.
- [] Support `--dry-run`.

Implementation notes:

- Treat this as a destructive, solution-wide workflow, not a renamed installer stack deletion.
- AWS retains some data-bearing resources to avoid accidental data loss, so preservation and cleanup choices must be explicit.
- Reference: <https://docs.aws.amazon.com/solutions/latest/landing-zone-accelerator-on-aws/uninstall-the-solution.html>.

### `lza config upload`

Upload the customer `aws-accelerator-config` to an S3-backed LZA configuration source without starting the LZA pipeline.

This command is the explicit S3 transfer utility. Other configuration repository types require their own synchronization behavior and are future work.

- [] Keep non-S3 repository synchronization out of this command unless its semantics are explicitly redesigned.

### `lza config download`

Download the current `aws-accelerator-config` from the configured LZA configuration source into the customer workspace.

- [] Support additional repository types:
  - Git repository
  - Bitbucket repository
  - Future custom repository providers
- [] Validate the downloaded configuration structure.
- [] Verify download integrity with checksums or signatures.
- [] Detect identical local and remote configurations and skip unnecessary downloads.

### `lza config deploy`

Synchronize the local customer configuration to its configured deployment destination.

By default, the command uploads or synchronizes configuration and then stops. It does not implicitly start or watch the LZA pipeline.

Implementation checklist:

- [] Validate the local configuration and configured destination.
- [] Show the target and planned synchronization changes.
- [] Upload or synchronize the configuration using provider-specific behavior.
- [] Stop after synchronization when no execution flags are supplied.
- [] Support `--execute` to start the relevant configuration pipeline after successful synchronization.
- [] Support `--watch` to watch the started execution; imply `--execute` when necessary.
- [] Record the upload/synchronization result and started pipeline execution ID in `.lza/state.json`.
- [] Reuse the same start/watch services as the separate pipeline commands.
- [] Support `--dry-run`.

### `lza pipeline start`

Start the configured LZA pipeline.
Implementation checklist:

- [] Detect the pipeline name from workspace configuration or AWS.
- [] Show the target account, region, and pipeline.
- [] Start a new pipeline execution.
- [] Return the pipeline execution ID.
- [] Save execution metadata to `.lza/state.json`.
- [] Prevent accidental duplicate execution when appropriate.

### `lza pipeline watch`

Monitor an LZA pipeline execution. This remains available independently of `lza config deploy --watch`.
Implementation checklist:

- [] Use the latest execution ID recorded in `.lza/state.json` by default when available.
- [] Fall back to discovering the latest execution when no recorded execution ID is available.
- [] Support a specific execution ID.
- [] Show stage and action status.
- [] Refresh output without excessive API calls.
- [] Detect failed CodeBuild actions.
- [] Show relevant failure details.
- [] Exit successfully when the pipeline succeeds.
- [] Return a non-zero exit code when the pipeline fails.

### `lza status`

Provide the single status entry point for the customer LZA workspace.

`lza status` shows the overall summary. Filtered views or subcommands such as `lza status installer`, `lza status config`, and `lza status pipeline` show component detail without separate top-level status commands.

### `lza doctor`

Run advisory local and AWS checks for the current workspace. The command reports problems and suggested remediation without modifying local files or AWS resources.

Implementation checklist:

- [] Validate `lza-workspace.yaml`.
- [] Validate required workspace files and directories.
- [] Validate template structure.
- [] Validate AWS profile access.
- [] Validate expected AWS account.
- [] Validate installer settings completeness.
- [] Validate configuration upload target.
- [] Detect unresolved placeholders.
- [] Produce a concise pass, warning, and failure summary.
- [] Suggest a remediation plan for failed or incomplete checks.

Future design decision:

- [] Decide whether to add an explicit `--fix` mode. Do not implement mutation as part of the current diagnostic command.

## Workspace

- [] Define `lza-workspace.yaml` schema.
- [] Version the workspace schema.
- [] Support workspace schema migration.
- [] Validate workspace before every command.
- [] Keep `.lza/state.json` operational only.
- [] Generate JSON Schema for editor support.
- [] Introduce centralized workspace readiness validation.
- [] Define core workspace configuration requirements.
- [] Allow `lza init` and `lza import` to establish missing core configuration.
- [] Require other commands to validate their minimum workspace readiness before execution.
- [] Fail early with clear errors when required workspace configuration is missing.
- [] Add target AWS account ID to workspace configuration.
- [] Resolve account ID from authenticated AWS identity when available.
- [] Allow account ID to be derived from AWS profile configuration when reliably possible.
- [] Persist the accepted account ID in `lza-workspace.yaml`.
- [] Validate authenticated AWS account against the configured workspace account where appropriate.

## Authentication

Authentication ownership:

- [] Keep AWS authentication external to the tool.
- [] Document that AWS SSO/static keys/assume-role/proxy/bastion setup is user-managed.
- [] Centralize AWS session/profile resolution for reuse by all commands.
- [] Lowest priority future feature: helper for AWS profile creation or authentication onboarding.

## Configuration Templates

- [] List available packaged templates.
- [] Validate template structure.
- [] Validate template compatibility with selected LZA version.

### Future

- [] Support Git template source.
- [] Support Bitbucket template source.
- [] Support template version/ref.
- [] Support cached templates.

## Validation

- [] Validate `lza-workspace.yaml`.
- [] Validate YAML formatting.
- [] Integrate official LZA schema validation.
- [] Validate workspace structure.
- [] Validate installer configuration.
- [] Validate upload target.
- [] Detect unresolved placeholders.
- [] Detect common LZA configuration mistakes.

## Reports

Maybe change entirely to 'lza report' command with subcommands for each report type?

- [] Generate `reports/aws-profile-check.md`.
- [] Generate `reports/status.md`.
- [] Generate pipeline execution reports.
- [] Generate CodeBuild failure summaries.
- [] Generate config diff reports.

## LZA Versions

- [] Support version-specific installer template URL.
- [] Support version-specific default branch.
- [] Support blocked/unsupported versions list.
- [] Auto-discover latest LZA versions.
- [] Cache installer templates.
- [] Warn on unstable or very old versions.
- [] Support migration helper between LZA versions.
- [] Validate version compatibility with packaged templates.

## Configuration Generation

- [] Organization/OU generator.
- [] Account generator.
- [] Enabled regions generator.
- [] Basic naming replacement generator.
- [] Basic network pattern generator.
- [] SCP pack side-loading.
- [] RCP pack side-loading.
- [] Config rule pack side-loading.
- [] Security service defaults.
- [] Backup defaults.

## AI & MCP

- [] Use AI to suggest replacements.
- [] Use AI to explain LZA config files.
- [] Use AI to compare customer requirements with current config.
- [] Use AI to summarize CodeBuild failures.
- [] Use AI to troubleshoot failed CloudFormation stacks.
- [] Evaluate AWS-provided LZA MCP server.
- [] Add local MCP server exposing workspace files, templates, validation, and pipeline status.
- [] Keep AI advisory first, execution second.

## Distribution

- [] Add installation instructions.
- [] Add example customer workspace.
- [] Ship a default packaged template.
- [] Add safe defaults.
- [] Add clearer error messages.
- [] Add command examples.
- [] Add contribution guidelines.
- [] Remove personal/company-specific hardcoding.
- [] Add tests for core workflows.

## Backlog

- [] AWS profile creation helper.
- [] AWS SSO profile bootstrap.
- [] Static key profile bootstrap.
- [] AssumeRole profile helper.
- [] Bastion/proxy helper documentation.
- [] GUI or TUI.
- [] Web interface.
- [] Multi-user/server mode.
