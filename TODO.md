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
- [ ] `lza profile check`
- [ ] `lza installer download`
- [ ] `lza installer deploy`
- [ ] `lza installer update`
- [ ] `lza config upload`
- [ ] `lza config download`
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
- [x] Ask for or accept template source.
- [x] Copy the selected `aws-accelerator-config` template.
- [x] Validate the copied template structure.
- [x] Generate initial `.lza/state.json`.
- [x] Store all selected initialization values in `lza-workspace.yaml`.
- [x] Validate the selected AWS profile unless skipped.
- [x] Print a concise initialization summary.
- [x] Print the next recommended commands.
- [x] Support non-interactive execution through CLI options.
- [x] Support `--dry-run`.
- [x] Support `--force`.
- [x] Support `--skip-aws-check`.
- [x] Detect a non-empty target workspace.
- [x] Offer to import the existing workspace instead of creating a new workspace.

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

### `lza installer download`

Download the LZA installer template for the selected version into the customer workspace.
Implementation checklist:

- [ ] Read selected LZA version from `lza-workspace.yaml`.
- [ ] Locate the downloaded installer template.
- [ ] Download it automatically if it is missing.
- [ ] Update the downloaded template structure with Anonymous Data Sharing disabled by default.
- Template URL Latest: <https://s3.amazonaws.com/solutions-reference/landing-zone-accelerator-on-aws/latest/AWSAccelerator-InstallerStack.template>
- Template URL Versioned: <https://s3.amazonaws.com/solutions-reference/landing-zone-accelerator-on-aws/{LZA_VERSION}/AWSAccelerator-InstallerStack.template>
- LZA_VERSION format: `v1.0.0`, `v2.0.0`, etc.

### `lza installer deploy`

Deploy the LZA installer stack for the current workspace.
Implementation checklist:

- [ ] Read installer settings from `lza-workspace.yaml`.
- [ ] Resolve the installer template for the selected LZA version.
- [ ] Render CloudFormation parameters from `lza-workspace.yaml`.
- [ ] Validate required installer settings before deployment.
- [ ] Show the planned stack name, account, and region.
- [ ] Support `--dry-run`.
- [ ] Create the installer stack.
- [ ] Wait for stack completion.
- [ ] Display stack events when deployment fails.
- [ ] Save deployment metadata to `.lza/state.json`.

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
- [ ] Read installer settings from `lza-workspace.yaml`.
- [ ] Render CloudFormation parameters from `lza-workspace.yaml`.

### `lza config upload`

Upload the customer `aws-accelerator-config` to the configured LZA configuration source.
Implementation checklist:

- [ ] Read configuration source settings from `lza-workspace.yaml`.
- [ ] Validate required configuration files.
- [ ] Detect unresolved replacement values.
- [ ] Package the configuration when required.
- [ ] Support S3 configuration repositories.
- [ ] Support additional repository types later.
- [ ] Show the target destination before upload.
- [ ] Support `--dry-run`.
- [ ] Save upload metadata to `.lza/state.json`.

### `lza config download`

Download the current aws-accelerator-config from the configured LZA configuration source into the customer workspace.
Implementation checklist:

- [ ] Read configuration source settings from `lza-workspace.yaml`.
- [ ] Detect the configured repository type.
- [ ] Support S3 configuration repositories.
- [ ] Support additional repository types later.
- [ ] Validate the destination workspace.
- [ ] Prevent accidental overwrite of local changes.
- [ ] Support `--force`.
- [ ] Support `--dry-run`.
- [ ] Download the complete aws-accelerator-config.
- [ ] Validate the downloaded template structure.
- [ ] Preserve file permissions where applicable.
- [ ] Update `.lza/state.json` with download metadata.
- [ ] Print a concise summary of downloaded files and source location.

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

## Authentication

Authentication ownership:

- [ ] Keep AWS authentication external to the tool.
- [ ] Document that AWS SSO/static keys/assume-role/proxy/bastion setup is user-managed.
- [ ] Centralize AWS session/profile resolution for reuse by all commands.
- [ ] Lowest priority future feature: helper for AWS profile creation or authentication onboarding.

## Installer Components

- [ ] Define installer settings schema in `lza-workspace.yaml`.
- [ ] Render CloudFormation parameters in memory for deploy/update.
- [ ] Support default values.
- [ ] Disable anonymous data sharing by default.
- [ ] Support approval stage email list.
- [ ] Support management account email.
- [ ] Support audit account email.
- [ ] Support log archive account email.
- [ ] Support repository source.
- [ ] Support repository owner/name/branch.
- [ ] Support config repository location.
- [ ] Support existing config repository options.
- [ ] Support S3 configuration location.

## Templates

- [x] Support local template source.
- [ ] Implement reusable template validation.
- [x] Copy template into customer workspace.
- [x] Avoid overwriting existing customer config unless explicitly approved.
- [x] Support `--force`.
- [ ] Support template list command.
- [ ] Support template validation command.

### Future

- [ ] Support Git template source.
- [ ] Support Bitbucket template source.
- [ ] Support template version/ref.
- [ ] Support cached templates.

## Validation

Shared validation components:

- [ ] Validate `lza-workspace.yaml`.
- [ ] Validate YAML formatting.
- [ ] Integrate LZA schema validation.
- [ ] Validate required installer settings.
- [ ] Validate selected template structure.
- [ ] Validate expected workspace files.
- [ ] Validate configuration upload target.
- [ ] Detect unresolved placeholders.
- [ ] Detect common LZA configuration mistakes.

## Reports

- [ ] Generate `reports/init-report.md`.
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
- [ ] Add example template.
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
