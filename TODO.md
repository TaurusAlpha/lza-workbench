# LZA Workbench TODO

## Project Setup

- [x] Create Python project structure.
- [x] Choose final package name.
- [x] Add CLI entrypoint.
- [x] Add basic `README.md`.
- [x] Add `PROJECT.md`.
- [x] Add `TODO.md`.
- [x] Add `.gitignore`.
- [x] Add formatter/linter configuration.
- [x] Add basic test structure.
- [x] Decide whether to use `uv`, Poetry, Hatch, or plain pip.

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
Implementation checklist:

- [x] Accept customer name as an argument.
- [x] Normalize customer name into a filesystem-safe slug.
  - Example: `Comm-IT` -> `comm-it`
- [x] Accept or ask for the target workspace directory.
- [x] Prevent accidental overwrite of an existing workspace.
- [x] Support explicit overwrite or reinitialization behavior.
- [x] Create the customer workspace folder.
- [x] Create `lza-workspace.yaml`.
- [x] Ask for or accept AWS profile.
- [x] Ask for or accept AWS region.
- [x] Ask for or accept LZA version.
- [x] Copy the packaged `aws-accelerator-config` template.
- [] Support selecting a packaged template when multiple templates exist.
- [x] Validate the copied template structure.
- [x] Generate initial `.lza/state.json`.
- [x] Store all selected initialization values in `lza-workspace.yaml`.
- [x] Validate the selected AWS profile unless skipped.
- [x] Print a concise initialization summary.
- [x] Print the next recommended commands.
- [x] Support non-interactive execution through CLI options.
- [x] Support `--dry-run`.
- [] Support `--force`.
- [x] Support `--skip-aws-check`.
- [x] Detect a non-empty target workspace.

Future enhancements:

- Init local git repository in LZA configuration directory and "init" commit.
  Check for correlation if configuration repo is already stored in Git or CodeCommit or other supported repository.

### `lza import`

Adopt an existing local LZA configuration without modifying customer-owned files.

- [x] Accept a workspace root or its direct `aws-accelerator-config` directory.
- [x] Default the workspace to the current directory.
- [x] Validate the existing `aws-accelerator-config` structure before import.
- [x] Reject nested, missing, or symlinked configuration layouts with a clear error.
- [x] Preserve all existing customer configuration files byte-for-byte.
- [x] Generate only `lza-workspace.yaml` and `.lza/state.json`.
- [x] Store imported configuration as a local workspace template source.
- [x] Support interactive prompts and non-interactive CLI options.
- [x] Support `--dry-run`.
- [x] Detect complete, partial, invalid, and inconsistent workspace metadata.
- [x] Update only selected metadata and preserve unknown or operational fields.
- [x] Preserve YAML comments and formatting where practical.
- [x] Treat unchanged repeat imports as a successful no-op.
- [x] Write changed metadata atomically.
- [x] Offer the import workflow from interactive `lza init`.
- [x] Keep `lza init --force` as the explicit reinitialization path.

Future import enhancements:

- [] Repair missing or invalid workspace metadata.
- [] Support forced metadata replacement.
- [] Parse and validate imported YAML content.
- [] Integrate version-aware official LZA schema validation.
- [] Record or resolve remote/Git template provenance.
- [] Generate installer parameters as part of the installer workflow, not import.

### `lza installer plan`

Resolve and persist installer configuration, then show the actions required to deploy the LZA installer without modifying AWS resources.

Implementation checklist:

#### Configuration ingestion

- [x] Load the current workspace from `lza-workspace.yaml`.
- [x] Read the configured LZA version.
- [x] Read existing installer configuration.
- [x] Resolve the configured installer source type.
- [x] Support `codecommit` as the initial installer source type.
- [x] Determine required common installer parameters.
- [x] Determine required CodeCommit-specific parameters.
- [] Collect every parameter exposed by the selected installer template.
- [] Apply documented template defaults and explicit workspace defaults where appropriate.
- [] Preserve a user's existing accepted values when defaults change.
- [x] Prompt interactively for missing required values.
- [x] Reuse existing values without prompting.
- [x] Validate all collected values.
- [x] Show all missing values together in non-interactive mode.
- [x] Save accepted installer settings to `lza-workspace.yaml`.
- [x] Preserve unrelated YAML content and formatting.
- [x] Support `--no-save`.

#### Template resolution

- [x] Resolve the installer template for the configured LZA version.
- [x] Download a local template internally when it is required and not available.
- [x] Reuse a compatible local template when available.
- [x] Validate that the template matches the configured LZA version.
- [x] Inspect template parameter definitions and defaults.
- [] Require a local template when the template must be modified, including when anonymous data sharing is disabled.
- [] Determine whether to support both the official remote template for unmodified deployments and a local template for modified deployments, or always standardize on a local template.

#### CodeCommit planning

- [x] Validate AWS access using the configured profile and region.
- [x] Inspect whether the configured CodeCommit repository exists.
- [x] Detect missing, empty, initialized, outdated, and inaccessible repositories.
- [x] Determine whether repository creation is required.
- [x] Determine whether source synchronization is required.
- [x] Resolve the official AWS source repository and version ref.
- [x] Produce source preparation actions without modifying the repository.

#### Deployment planning

- [x] Map workspace installer settings to CloudFormation parameters.
- [x] Validate resolved parameters against the installer template.
- [x] Detect whether the installer stack exists.
- [x] Determine whether the deployment operation would be create, update, or no change.
- [x] Show the resolved installer configuration.
- [x] Show CodeCommit preparation actions.
- [x] Show the CloudFormation deployment operation.
- [x] Show parameter provenance when useful.
- [x] Guarantee that the command does not mutate AWS resources.

### `lza installer deploy`

Reconcile the locally configured installer desired state with AWS for both initial deployment and later updates.

Implementation checklist:

- [x] Check for missing required values, stop if missing, and suggest running `lza installer plan`.
- [x] Resolve the requested installer configuration from `lza-workspace.yaml`.
- [x] Resolve or download the configured installer template version when required.
- [x] Detect the existing installer stack and determine whether the operation is create, update, or no change.
- [x] Compare deployed and requested parameters.
- [x] Compare installer template versions.
- [x] Compare installer source configuration.
- [x] Show planned changes before execution.
- [] Ask for confirmation before applying changes unless confirmation is explicitly bypassed.
- [x] Prepare the configured installer source when supported and required.
- [x] Create or validate required AWS resources.
- [x] Create or update the CloudFormation stack.
- [x] Handle no-change deployments cleanly.
- [x] Wait for stack completion.
- [x] Display stack events when deployment fails.
- [x] Record deployment metadata in `.lza/state.json`.
- [x] Print deployment outputs and next recommended commands.
- [x] Support `--dry-run`.
- [x] Support `--force`.

Future enhancements:

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

Implementation checklist:

- [x] Read configuration source settings from `lza-workspace.yaml`.
- [x] Validate required configuration files.
- [x] Detect unresolved replacement values.
- [x] Package the configuration when required.
- [x] Support S3 configuration repositories.
- [] Keep non-S3 repository synchronization out of this command unless its semantics are explicitly redesigned.
- [x] Show the target destination before upload.
- [x] Support `--dry-run`.
- [x] Save upload metadata to `.lza/state.json`.

### `lza config download`

Download the current `aws-accelerator-config` from the configured LZA configuration source into the customer workspace.

Implementation checklist:

- [x] Read configuration source settings from `lza-workspace.yaml`.
- [x] Prompt for missing settings interactively.
- [x] Detect the configured repository type.
- [x] Support S3 configuration repositories.
- [x] Prevent accidental overwrite of local changes.
      Overwrite local changes by default.
      If overwrite is disabled, ask for confirmation when local changes are detected.
- [x] Support `--force`.
      Ignore overwrite protection and replace local changes without confirmation.
- [x] Support `--dry-run`.
      Verify remote access and print the files that would be downloaded without changing the workspace.
- [x] Verify required S3 list and object-read permissions.
- [x] Download the remote configuration.
- [x] Add `--extract` for archive-based sources.
      Extract the archive into the workspace and print updated file paths.
- [x] Replace the local configuration atomically.
- [x] Preserve excluded local directories such as `.git`.
- [x] Record download metadata in `.lza/state.json`.
- [x] Print a concise summary of the source and downloaded files.

Future download enhancements:

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

Implementation checklist:

- [x] Read `lza-workspace.yaml`.
- [x] Read `.lza/state.json`.
- [x] Show customer name and workspace path.
- [x] Show configured AWS profile and region.
- [x] Show selected LZA version.
- [x] Show an overall installer, configuration, and pipeline summary.
- [x] Support an installer view with stack status, deployed version, source details, outputs, drift, and configured-versus-deployed differences.
- [x] Support a configuration view with local and remote source status and last upload/download metadata.
- [x] Support a pipeline view with the latest known execution and its status.
- [x] Allow synchronizing local operational state only through an explicit option; status remains read-only by default.
- [x] Clearly distinguish configured, detected, and unknown values.

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

## Authentication

Authentication ownership:

- [] Keep AWS authentication external to the tool.
- [] Document that AWS SSO/static keys/assume-role/proxy/bastion setup is user-managed.
- [] Centralize AWS session/profile resolution for reuse by all commands.
- [] Lowest priority future feature: helper for AWS profile creation or authentication onboarding.

## Configuration Templates

- [x] Support packaged template source.
- [x] Support local template source.
- [x] Copy template into customer workspace.
- [x] Avoid overwriting existing customer configuration.
- [x] Support `--force`.
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

- [x] Store selected LZA version in `lza-workspace.yaml`.
- [x] Support manual version input.
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
