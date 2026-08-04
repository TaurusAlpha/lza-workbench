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
- [ ] `lza profile check`
- [x] `lza installer download`
- [x] `lza installer plan`
- [ ] `lza installer deploy`
- [ ] `lza installer status`
- [ ] `lza installer update`
- [ ] `lza installer delete`
- [x] `lza config upload`
- [x] `lza config download`
- [ ] `lza pipeline start`
- [ ] `lza pipeline watch`
- [ ] `lza status`
- [ ] `lza doctor`

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
- [ ] Support selecting a packaged template when multiple templates exist.
- [x] Validate the copied template structure.
- [x] Generate initial `.lza/state.json`.
- [x] Store all selected initialization values in `lza-workspace.yaml`.
- [x] Validate the selected AWS profile unless skipped.
- [x] Print a concise initialization summary.
- [x] Print the next recommended commands.
- [x] Support non-interactive execution through CLI options.
- [x] Support `--dry-run`.
- [ ] Support `--force`.
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

- [ ] Repair missing or invalid workspace metadata.
- [ ] Support forced metadata replacement.
- [ ] Parse and validate imported YAML content.
- [ ] Integrate version-aware official LZA schema validation.
- [ ] Record or resolve remote/Git template provenance.
- [ ] Generate installer parameters as part of the installer workflow, not import.

### `lza profile check`

Validate AWS access for the profile configured in the current workspace or provided explicitly.
Implementation checklist:

- [ ] Read profile and region from `lza-workspace.yaml`.
- [ ] Support explicit `--profile`.
- [ ] Support explicit `--region`.
- [ ] Run `sts:GetCallerIdentity`.
- [ ] Show AWS account ID.
- [ ] Show caller ARN.
- [ ] Show detected user or role identity.
- [ ] Compare the detected account with the expected management account.
- [ ] Return a non-zero exit code when validation fails.
- [ ] Provide clear errors for expired SSO sessions or invalid credentials.

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
- [x] Prompt interactively for missing required values.
- [x] Reuse existing values without prompting.
- [x] Validate all collected values.
- [x] Show all missing values together in non-interactive mode.
- [x] Save accepted installer settings to `lza-workspace.yaml`.
- [x] Preserve unrelated YAML content and formatting.
- [x] Support `--no-save`.

#### Template resolution

- [x] Resolve the installer template for the configured LZA version.
- [x] Download the template when it is not available locally.
- [x] Reuse a compatible local template when available.
- [x] Validate that the template matches the configured LZA version.
- [x] Inspect template parameter definitions and defaults.

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

### `lza installer download`

Download the LZA installer CloudFormation template for the selected version into the customer workspace.

Implementation checklist:

- [x] Read selected LZA version from `lza-workspace.yaml`.
- [x] Resolve installer template URL for the selected version.
- [x] Download the installer template if missing.
- [x] Support re-download with `--force`.
- [x] Disable Anonymous Data Sharing by default.
- [x] Save the template under the workspace installer directory.
- [x] Record downloaded version in `.lza/state.json`.

Implementation notes:

- Template URL Latest: <https://s3.amazonaws.com/solutions-reference/landing-zone-accelerator-on-aws/latest/AWSAccelerator-InstallerStack.template>
- Template URL Versioned: <https://s3.amazonaws.com/solutions-reference/landing-zone-accelerator-on-aws/{LZA_VERSION}/AWSAccelerator-InstallerStack.template>
- LZA_VERSION format: `v1.0.0`, `v2.0.0`, etc.

### `lza installer deploy`

Deploy the LZA installer stack for the current workspace.
Implementation checklist:

- [ ] Execute the installer planning workflow.
- [ ] Prompt for missing required values.
- [ ] Prepare the configured installer source when required.
- [ ] Create or validate required AWS resources.
- [ ] Create the installer stack.
- [ ] Wait for stack completion.
- [ ] Display stack events when deployment fails.
- [ ] Record deployment metadata in `.lza/state.json`.
- [ ] Print deployment outputs and next recommended commands.
- [ ] Support `--dry-run`.
- [ ] Support `--force`.

### `lza installer update`

Update an existing LZA installer stack.

Implementation checklist:

- [ ] Detect the existing installer stack.
- [ ] Compare current and requested parameters.
- [ ] Show planned changes before execution.
- [ ] Support `--dry-run`.
- [ ] Update the stack.
- [ ] Handle no-change responses cleanly.
- [ ] Wait for update completion.
- [ ] Display stack events when the update fails.
- [ ] Update `.lza/state.json`.
- [ ] Detect parameter changes before update.

### `lza installer status`

Show the current installer deployment state.
Implementation checklist:

- [ ] Detect the installer stack.
- [ ] Show stack status.
- [ ] Show deployed LZA version.
- [ ] Show installer source type.
- [ ] Show source repository details.
- [ ] Show stack outputs.
- [ ] Compare deployed and configured versions.
- [ ] Detect configuration drift.
- [ ] Read deployment metadata from `.lza/state.json`.

### lza installer update

Update an existing installer deployment.
Implementation checklist:

- [ ] Detect the existing installer stack.
- [ ] Resolve the requested installer configuration.
- [ ] Compare deployed and requested parameters.
- [ ] Compare installer template versions.
- [ ] Compare installer source configuration.
- [ ] Show planned changes.
- [ ] Prepare updated installer source when required.
- [ ] Update the CloudFormation stack.
- [ ] Handle no-change updates cleanly.
- [ ] Wait for update completion.
- [ ] Display stack events when update fails.
- [ ] Update `.lza/state.json`.
- [ ] Support `--dry-run`.

### `lza installer delete`

Remove the installer deployment.
Implementation checklist:

- [ ] Detect the installer stack.
- [ ] Show the resources that will be removed.
- [ ] Require confirmation unless `--force` is specified.
- [ ] Delete the installer stack.
- [ ] Wait for stack deletion.
- [ ] Preserve installer source repositories by default.
- [ ] Optionally remove installer source resources.
- [ ] Remove installer deployment metadata from `.lza/state.json`.

### `lza config upload`

Upload the customer `aws-accelerator-config` to the configured LZA configuration source.
Implementation checklist:

- [x] Read configuration source settings from `lza-workspace.yaml`.
- [x] Validate required configuration files.
- [x] Detect unresolved replacement values.
- [x] Package the configuration when required.
- [x] Support S3 configuration repositories.
- [ ] Support additional repository types later.
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

- [ ] Support additional repository types:
  - Git repository
  - Bitbucket repository
  - Future custom repository providers
- [ ] Validate the downloaded configuration structure.
- [ ] Verify download integrity with checksums or signatures.
- [ ] Detect identical local and remote configurations and skip unnecessary downloads.

### `lza pipeline start`

Start the configured LZA pipeline.
Implementation checklist:

- [ ] Detect the pipeline name from workspace configuration or AWS.
- [ ] Show the target account, region, and pipeline.
- [ ] Start a new pipeline execution.
- [ ] Return the pipeline execution ID.
- [ ] Save execution metadata to `.lza/state.json`.
- [ ] Prevent accidental duplicate execution when appropriate.

### `lza pipeline watch`

Monitor an LZA pipeline execution.
Implementation checklist:

- [ ] Watch the latest execution by default.
- [ ] Support a specific execution ID.
- [ ] Show stage and action status.
- [ ] Refresh output without excessive API calls.
- [ ] Detect failed CodeBuild actions.
- [ ] Show relevant failure details.
- [ ] Exit successfully when the pipeline succeeds.
- [ ] Return a non-zero exit code when the pipeline fails.

### `lza status`

Show the current state of the customer LZA workspace.
Implementation checklist:

- [ ] Read `lza-workspace.yaml`.
- [ ] Read `.lza/state.json`.
- [ ] Show customer name and workspace path.
- [ ] Show configured AWS profile and region.
- [ ] Show selected LZA version.
- [ ] Show installer stack status.
- [ ] Show configuration source.
- [ ] Show latest pipeline execution status.
- [ ] Clearly distinguish configured, detected, and unknown values.

### `lza doctor`

Run local and AWS checks for the current workspace.
Implementation checklist:

- [ ] Validate `lza-workspace.yaml`.
- [ ] Validate required workspace files and directories.
- [ ] Validate template structure.
- [ ] Validate AWS profile access.
- [ ] Validate expected AWS account.
- [ ] Validate installer settings completeness.
- [ ] Validate configuration upload target.
- [ ] Detect unresolved placeholders.
- [ ] Produce a concise pass, warning, and failure summary.

## Workspace

- [ ] Define `lza-workspace.yaml` schema.
- [ ] Version the workspace schema.
- [ ] Support workspace schema migration.
- [ ] Validate workspace before every command.
- [ ] Keep `.lza/state.json` operational only.
- [ ] Generate JSON Schema for editor support.

## Authentication

Authentication ownership:

- [ ] Keep AWS authentication external to the tool.
- [ ] Document that AWS SSO/static keys/assume-role/proxy/bastion setup is user-managed.
- [ ] Centralize AWS session/profile resolution for reuse by all commands.
- [ ] Lowest priority future feature: helper for AWS profile creation or authentication onboarding.

## Configuration Templates

- [x] Support packaged template source.
- [x] Support local template source.
- [x] Copy template into customer workspace.
- [x] Avoid overwriting existing customer configuration.
- [x] Support `--force`.
- [ ] List available packaged templates.
- [ ] Validate template structure.
- [ ] Validate template compatibility with selected LZA version.

### Future

- [ ] Support Git template source.
- [ ] Support Bitbucket template source.
- [ ] Support template version/ref.
- [ ] Support cached templates.

## Validation

- [ ] Validate `lza-workspace.yaml`.
- [ ] Validate YAML formatting.
- [ ] Integrate official LZA schema validation.
- [ ] Validate workspace structure.
- [ ] Validate installer configuration.
- [ ] Validate upload target.
- [ ] Detect unresolved placeholders.
- [ ] Detect common LZA configuration mistakes.

## Reports

Maybe change entirely to 'lza report' command with subcommands for each report type?

- [ ] Generate `reports/aws-profile-check.md`.
- [ ] Generate `reports/status.md`.
- [ ] Generate pipeline execution reports.
- [ ] Generate CodeBuild failure summaries.
- [ ] Generate config diff reports.

## LZA Versions

- [x] Store selected LZA version in `lza-workspace.yaml`.
- [x] Support manual version input.
- [ ] Support version-specific installer template URL.
- [ ] Support version-specific default branch.
- [ ] Support blocked/unsupported versions list.
- [ ] Auto-discover latest LZA versions.
- [ ] Cache installer templates.
- [ ] Warn on unstable or very old versions.
- [ ] Support migration helper between LZA versions.
- [ ] Validate version compatibility with packaged templates.

## Configuration Generation

- [ ] Organization/OU generator.
- [ ] Account generator.
- [ ] Enabled regions generator.
- [ ] Basic naming replacement generator.
- [ ] Basic network pattern generator.
- [ ] SCP pack side-loading.
- [ ] RCP pack side-loading.
- [ ] Config rule pack side-loading.
- [ ] Security service defaults.
- [ ] Backup defaults.

## AI & MCP

- [ ] Use AI to suggest replacements.
- [ ] Use AI to explain LZA config files.
- [ ] Use AI to compare customer requirements with current config.
- [ ] Use AI to summarize CodeBuild failures.
- [ ] Use AI to troubleshoot failed CloudFormation stacks.
- [ ] Evaluate AWS-provided LZA MCP server.
- [ ] Add local MCP server exposing workspace files, templates, validation, and pipeline status.
- [ ] Keep AI advisory first, execution second.

## Distribution

- [ ] Add installation instructions.
- [ ] Add example customer workspace.
- [ ] Ship a default packaged template.
- [ ] Add safe defaults.
- [ ] Add clearer error messages.
- [ ] Add command examples.
- [ ] Add contribution guidelines.
- [ ] Remove personal/company-specific hardcoding.
- [ ] Add tests for core workflows.

## Backlog

- [ ] AWS profile creation helper.
- [ ] AWS SSO profile bootstrap.
- [ ] Static key profile bootstrap.
- [ ] AssumeRole profile helper.
- [ ] Bastion/proxy helper documentation.
- [ ] GUI or TUI.
- [ ] Web interface.
- [ ] Multi-user/server mode.
