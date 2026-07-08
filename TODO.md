# LZA Workbench TODO

## Project Setup

- [ ] Create Python project structure.
- [ ] Choose final package name.
- [ ] Add CLI entrypoint.
- [ ] Add basic `README.md`.
- [ ] Add `PROJECT.md`.
- [ ] Add `TODO.md`.
- [ ] Add `.gitignore`.
- [ ] Add formatter/linter configuration.
- [ ] Add basic test structure.
- [ ] Decide whether to use `uv`, Poetry, Hatch, or plain pip.

## init command

Features:

- [ ] Normalize customer name into slug.
  - Example: `Comm-IT` -> `comm-it`
- [ ] Create customer workspace folder.
- [ ] Create `lza-project.yaml`.
- [ ] Ask for AWS profile.
- [ ] Ask for AWS region.
- [ ] Ask for LZA version.
- [ ] Ask for template source.
- [ ] Ask for template name.
- [ ] Copy selected `aws-accelerator-config` template.
- [ ] Generate initial `.lza/state.json`.
- [ ] Generate installer folder.
- [ ] Generate initial installer parameter file.
- [ ] Generate helper scripts.
- [ ] Print next recommended commands.

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
