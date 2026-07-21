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

- [ ] `lza init`
- [ ] `lza profile check`
- [ ] `lza installer deploy`
- [ ] `lza installer update`
- [ ] `lza config upload`
- [ ] `lza config download`
- [ ] `lza pipeline start`
- [ ] `lza pipeline watch`
- [ ] `lza status`
- [ ] `lza doctor`

### `lza init`

Create a new customer-specific LZA project workspace.

Implementation checklist:

- [ ] Accept customer name as an argument.
- [ ] Normalize customer name into a filesystem-safe slug.
  - Example: `Comm-IT` -> `comm-it`
- [ ] Accept or ask for the target workspace directory.
- [ ] Prevent accidental overwrite of an existing project.
- [ ] Support explicit overwrite or reinitialization behavior.
- [ ] Create the customer workspace folder.
- [ ] Create `lza-project.yaml`.
- [ ] Ask for or accept AWS profile.
- [ ] Ask for or accept AWS region.
- [ ] Ask for or accept LZA version.
- [ ] Ask for or accept template source.
- [ ] Ask for or accept template name.
- [ ] Copy the selected `aws-accelerator-config` template.
- [ ] Validate the copied template structure.
- [ ] Generate initial `.lza/state.json`.
- [ ] Generate installer parameter files.
- [ ] Store all selected initialization values in `lza-project.yaml`.
- [ ] Validate the selected AWS profile unless skipped.
- [ ] Print a concise initialization summary.
- [ ] Print the next recommended commands.
- [ ] Support non-interactive execution through CLI options.
- [ ] Support `--dry-run`.
- [ ] Support `--force`.
- [ ] Support `--skip-aws-check`.

### `lza profile check`

Validate AWS access for the profile configured in the current project or provided explicitly.

Implementation checklist:

- [ ] Read profile and region from `lza-project.yaml`.
- [ ] Support explicit `--profile`.
- [ ] Support explicit `--region`.
- [ ] Run `sts:GetCallerIdentity`.
- [ ] Show AWS account ID.
- [ ] Show caller ARN.
- [ ] Show detected user or role identity.
- [ ] Compare the detected account with the expected management account.
- [ ] Return a non-zero exit code when validation fails.
- [ ] Provide clear errors for expired SSO sessions or invalid credentials.

### `lza installer deploy`

Deploy the LZA installer stack for the current project.

Implementation checklist:

- [ ] Read installer settings from `lza-project.yaml`.
- [ ] Resolve the installer template for the selected LZA version.
- [ ] Load installer parameters.
- [ ] Validate required parameters before deployment.
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

### `lza config upload`

Upload the customer `aws-accelerator-config` to the configured LZA configuration source.

Implementation checklist:

- [ ] Read configuration source settings from `lza-project.yaml`.
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

- [ ] Read configuration source settings from `lza-project.yaml`.
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

- [ ] Detect the pipeline name from project configuration or AWS.
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

Show the current state of the customer LZA project.

Implementation checklist:

- [ ] Read `lza-project.yaml`.
- [ ] Read `.lza/state.json`.
- [ ] Show customer name and workspace path.
- [ ] Show configured AWS profile and region.
- [ ] Show selected LZA version.
- [ ] Show installer stack status.
- [ ] Show configuration source.
- [ ] Show latest pipeline execution status.
- [ ] Clearly distinguish configured, detected, and unknown values.

### `lza doctor`

Run local and AWS checks for the current project.

Implementation checklist:

- [ ] Validate `lza-project.yaml`.
- [ ] Validate required project files and directories.
- [ ] Validate template structure.
- [ ] Validate AWS profile access.
- [ ] Validate expected AWS account.
- [ ] Validate installer parameter completeness.
- [ ] Validate configuration upload target.
- [ ] Detect unresolved placeholders.
- [ ] Produce a concise pass, warning, and failure summary.

## AWS Profile handling

- [ ] Run `sts:GetCallerIdentity` using selected profile.
- [ ] Show account ID, ARN, and user/role identity.
- [ ] Warn if profile does not work.
- [ ] Warn if actual account ID does not match expected management account ID.
- [ ] Support `--skip-aws-check`.
- [ ] Support `--profile`.
- [ ] Support `--region`.

Authentication ownership:

- [ ] Keep AWS authentication external to the tool.
- [ ] Document that AWS SSO/static keys/assume-role/proxy/bastion setup is user-managed.
- [ ] Lowest priority future feature: helper for AWS profile creation or authentication onboarding.

## Installer

### Parameters

- [ ] Define installer parameter schema.
- [ ] Render `installer/parameters.yaml`.
- [ ] Render `installer/parameters.json`.
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

### Operations

- [ ] `lza profile check`
- [ ] `lza installer deploy`
- [ ] `lza installer update`
- [ ] `lza config upload`
- [ ] `lza pipeline start`
- [ ] `lza pipeline watch`
- [ ] `lza status`

## Templates

- [ ] Support local template source.
- [ ] Validate that template contains `aws-accelerator-config`.
- [ ] Copy template into customer workspace.
- [ ] Avoid overwriting existing customer config unless explicitly approved.
- [ ] Support `--force`.
- [ ] Support template list command.
- [ ] Support template validation command.

### Future

- [ ] Support Git template source.
- [ ] Support Bitbucket template source.
- [ ] Support template version/ref.
- [ ] Support cached templates.

## Scripts

Generate simple reviewable scripts:

- [ ] `installer/deploy.sh`
- [ ] `installer/update.sh`
- [ ] `scripts/upload-config.sh`
- [ ] `scripts/start-pipeline.sh`
- [ ] `scripts/watch-pipeline.sh`

Rules:

- [ ] Scripts should use values from `lza-project.yaml`.
- [ ] Scripts should be simple and readable.
- [ ] Scripts should not hide dangerous AWS mutations.
- [ ] Scripts should include `set -euo pipefail`.

## Validation & Diagnostics

- [ ] Validate `lza-project.yaml`.
- [ ] Validate required installer parameters.
- [ ] Validate expected files exist.
- [ ] Validate selected template structure.
- [ ] Validate AWS profile identity.
- [ ] Validate config upload target.
- [ ] Add `lza doctor`.
- [ ] Integrate LZA schema validation.
- [ ] Validate YAML formatting.
- [ ] Validate replacement placeholders.
- [ ] Detect unresolved template values.
- [ ] Detect common LZA config mistakes.

## Reports

- [ ] Generate `reports/init-report.md`.
- [ ] Generate `reports/aws-profile-check.md`.
- [ ] Generate `reports/installer-params.md`.
- [ ] Generate `reports/status.md`.
- [ ] Generate pipeline execution reports.
- [ ] Generate CodeBuild failure summaries.
- [ ] Generate config diff reports.

## LZA Versions

- [ ] Store selected LZA version in `lza-project.yaml`.
- [ ] Support manual version input.
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
- [ ] Add local MCP server exposing project files, templates, validation, and pipeline status.
- [ ] Keep AI advisory first, execution second.

## Distribution

- [ ] Add installation instructions.
- [ ] Add example customer project.
- [ ] Add example template.
- [ ] Add safe defaults.
- [ ] Add dry-run mode.
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
