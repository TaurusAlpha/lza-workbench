# LZA Workbench TODO

Historical work is recorded in [`docs/DONE.md`](docs/DONE.md). This file tracks active features,
unresolved design decisions, and technical debt.

## Command Inventory

Keep this as the canonical inventory of implemented and planned command names. Checked commands
are registered in the current CLI; unchecked commands are planned.

### Workspace lifecycle

- `lza init`
- `lza import`
- `lza bootstrap`
- `lza validate`
- `lza diff`
- `lza doctor`
- `lza uninstall`

### Installer

- `lza installer init`
- `lza installer plan`
- `lza installer deploy`
- `lza installer status` (alias for `lza status installer`)
- `lza installer import`

### Configuration

- `lza config init`
- `lza config pull`
- `lza config push`
- `lza config download` (alias for `lza config pull`)
- `lza config upload` (alias for `lza config push`)
- `lza config deploy`
- `lza config status` (alias for `lza status config`)
- `lza config edit`

### Pipeline and status

- `lza pipeline start`
- `lza pipeline watch`
- `lza status`
- `lza status installer`
- `lza status config`

## Command Reference and Feature Work

Keep every inventory command in this section with a short description, even when it has no open
tasks. Add command-specific enhancements beneath the relevant command instead of removing an
implemented command's section.

### `lza init`

Create a new customer-specific LZA workspace and its local Workbench metadata.

### `lza import`

Adopt an existing local LZA configuration without modifying customer-owned configuration files.

### `lza bootstrap`

Create or validate AWS prerequisite resources required by LZA Workbench.

#### Future `lza bootstrap` enhancements

Bootstrap installer and configuration prerequisites based on the current installer configuration in `lza-workspace.yaml`.

The future implementation should preserve the following behavior:

#### Installer source

- [x] `RepositorySource=github`

- [ ] `RepositorySource=codecommit`
  - On init or changed configuration:
    - Create or validate the `lza-installer-source` CodeCommit repository in the management account.
  - On import:
    - Validate that the configured repository exists and is accessible.
    - Do not recreate missing imported resources automatically.

- [ ] `RepositorySource=s3`
  - On init or changed configuration:
    - Create or validate the versioned
      `s3-lza-installer-source-<account-id>-<region>` bucket.
  - On import:
    - Validate that the configured bucket exists and is accessible.
    - Do not recreate missing imported resources automatically.
  - Keep installer source packaging, upload, and S3-specific installer template synthesis outside bootstrap.

#### Configuration repository

- [ ] `ConfigurationRepositoryLocation=codeconnection`
  - On init, changed configuration, and import:
    - Require `ConfigCodeConnectionArn`.
    - Require the configured repository owner, name, and branch.
    - Validate that the CodeConnections connection exists and is accessible.
    - Validate repository accessibility where possible.
    - Do not create CodeConnections or external repository resources.

- [ ] `ConfigurationRepositoryLocation=s3`
  - Treat as a separate LZA-specific configuration workflow.
  - Do not create the LZA-managed `aws-accelerator-config-<account-id>-<region>` bucket during bootstrap.
  - When importing an existing deployment, validate the discovered bucket and access.
  - Revisit exact bootstrap behavior when S3 configuration deployment support is implemented.

### `lza validate`

Validate the current workspace and LZA configuration without modifying local files or AWS resources.

By default, validate all applicable workspace components.

Possible scoped usage:

```text
lza validate
lza validate workspace
lza validate config
lza validate installer
```

Implementation checklist:

- [ ] Validate `lza-workspace.yaml` schema and required workspace metadata.
- [ ] Validate workspace directory structure and configured paths.
- [ ] Validate LZA configuration YAML syntax.
- [ ] Validate the expected LZA configuration file structure.
- [ ] Reuse the existing official/version-aware LZA schema validation used by import and
  configuration synchronization workflows.
- [ ] Validate installer configuration and required parameters.
- [ ] Validate the configured upload target.
- [ ] Validate configuration replacement-variable consistency across configuration files and
  `replacements-config.yaml`.
- [ ] Detect inconsistent settings between workspace, installer, and configuration metadata.
- [ ] Detect common LZA configuration mistakes.
- [ ] Produce concise pass, warning, and failure results.
- [ ] Return a non-zero exit code when validation fails.
- [ ] Keep validation read-only.
- [ ] Reuse validation logic from other workflows rather than duplicating checks.

### `lza diff`

Show meaningful differences between the current local desired state and the corresponding remote or deployed LZA state without modifying anything.

Initial implementation should focus on configuration differences.

Possible usage:

```text
lza diff
lza diff config
```

Implementation checklist:

- [ ] Compare local `aws-accelerator-config` with the configured remote configuration source.
- [ ] Reuse provider-specific configuration source access from `lza config pull` without modifying the local workspace.
- [ ] Support Amazon S3, AWS CodeCommit, AWS CodeConnections, and Git configuration sources.
- [ ] Show added, removed, and modified configuration files.
- [ ] Show content differences for modified text/YAML files.
- [ ] Clearly identify the local and remote revisions or object metadata being compared when available.
- [ ] Avoid changing the Git working tree or local configuration directory.
- [ ] Support a concise summary and detailed diff output.
- [ ] Return successfully when no differences exist.
- [ ] Keep the design extensible for future installer/deployed-state diff support without implementing those scopes yet.

Future enhancements:

- [ ] `lza diff installer` for configured versus deployed installer state.
- [ ] Structured LZA-aware YAML differences rather than only textual differences.
- [ ] Export configuration diff reports.

### `lza config edit`

Future command for safely modifying selected parts of the local LZA configuration through structured Workbench workflows.

Do not implement until configuration schemas and generation/mutation behavior are sufficiently defined.

Potential future usage:

```text
lza config edit accounts
lza config edit organization
lza config edit regions
lza config edit network
```

Future design checklist:

- [ ] Decide which LZA configuration domains can be safely mutated by Workbench.
- [ ] Define version-aware configuration models before modifying customer YAML.
- [ ] Preserve unsupported and unknown configuration content.
- [ ] Validate proposed changes before writing files.
- [ ] Show planned changes and require confirmation before mutation.
- [ ] Support `--dry-run`.
- [ ] Keep modification local; do not implicitly push or deploy configuration.
- [ ] Ensure `lza config deploy` remains the explicit synchronization and execution workflow.
- [ ] Reuse configuration-generation functionality where appropriate.

### `lza installer init`

Collect and persist installer CloudFormation parameters and workspace settings.

### `lza installer plan`

Inspect AWS and show the CloudFormation actions required for the initialized installer
configuration without modifying AWS resources.

- [ ] Report validation-only readiness for the selected installer source, including its required
  GitHub secret/repository, CodeCommit repository and branch, or S3 source object. Keep source
  provisioning and synchronization in their dedicated future workflows.

### `lza installer deploy`

Deploy or update the LZA installer CloudFormation stack in the management account.

Future design decision:

- [ ] Prepare and synchronize installer source code across Amazon S3, AWS CodeCommit, and the official AWS GitHub repository when the configured LZA version or source settings require it.
- [ ] Follow the AWS source-location requirements for S3 packaging and synthesized installer parameters: <https://docs.aws.amazon.com/solutions/latest/landing-zone-accelerator-on-aws/source-code-location.html>.

### `lza installer status`

Show installer deployment status as an alias for `lza status installer`.

### `lza uninstall`

Uninstall the LZA solution rather than deleting only the installer stack.

Implementation checklist:

- [ ] Inventory the Installer and Core pipeline stacks and additional LZA stacks across managed accounts and Regions.
- [ ] Detect and explain termination protection before deletion.
- [ ] Show the resources that would be removed and those retained by AWS deletion policies.
- [ ] Offer explicit preservation modes for customer data and other retained resources.
- [ ] Require confirmation unless `--force` is specified.
- [ ] Delete stacks in dependency-safe reverse deployment order.
- [ ] Optionally remove retained S3 buckets and other explicitly selected resources.
- [ ] Preserve source repositories and customer configuration by default.
- [ ] Record progress so an interrupted uninstall can be inspected or resumed safely.
- [ ] Remove deployment metadata from `.lza/state.json` only after the corresponding resources are removed.
- [ ] Support `--dry-run`.

Implementation notes:

- Treat this as a destructive, solution-wide workflow, not a renamed installer stack deletion.
- AWS retains some data-bearing resources to avoid accidental data loss, so preservation and cleanup choices must be explicit.
- Reference: <https://docs.aws.amazon.com/solutions/latest/landing-zone-accelerator-on-aws/uninstall-the-solution.html>.

### `lza config init`

Initialize the local `aws-accelerator-config` in the current workspace from a packaged configuration template.

- [ ] Prompt for a packaged template when multiple templates exist and `--template` is omitted.
- [ ] When the configured remote source is S3, initialize a local Git repository and initial commit
  in the generated `aws-accelerator-config` directory.
- [ ] Avoid creating a nested or competing Git repository when the configuration directory is
  already tracked by Git, CodeCommit, or another supported repository.

### `lza config push`

Synchronize the local customer `aws-accelerator-config` to the configured remote configuration source without starting the LZA pipeline.

- [ ] Fix default packaging exclusions: remove `"backup"` from `PackagingExcludeConfig.directories` so customer AWS Backup definitions (e.g. `backup/backup-*.json`) are not omitted from configuration archives. Default exclusions should only target `.git`, `.DS_Store`, etc.
- [ ] Add support to parse and honor `.gitignore` / `.prettierignore` when packaging local configuration files for S3 upload.
- [ ] Fix zip diff calculation: filter out directory-level records (entries ending with `/`) in `read_zip_manifest` so directory records from existing zip archives are not incorrectly reported as removed files.
- [ ] Add safety check for S3-backed imported workspaces: if workspace was imported and has not yet synced/downloaded remote configuration from S3, warn the user that local configuration may overwrite unverified remote S3 state, requiring `--force` (or interactive confirmation) and recommending `lza config download` first.
- [ ] Persist the derived standard S3 configuration bucket name to `lza-workspace.yaml` during
  `config push` and `config pull`. Import and `status installer --sync-config` already derive and
  persist `aws-accelerator-config-<account-id>-<region>`.

### `lza config pull`

Synchronize the configured remote customer configuration source into the local
`aws-accelerator-config` directory.

### `lza config download`

Download configuration from the configured remote source as an alias for `lza config pull`.

### `lza config upload`

Upload configuration to the configured remote source as an alias for `lza config push`.

### `lza config deploy`

Push the local configuration, start the configuration pipeline, and optionally watch the pipeline
execution to completion.

### `lza pipeline start`

Start the configured LZA pipeline without synchronizing local configuration first.

### `lza pipeline watch`

Monitor an existing pipeline execution without starting a new execution or synchronizing
configuration.

### `lza status`

Show the read-only overall operational status of the current LZA workspace and deployment.

Provides a consolidated high-level summary of workspace identity, installer CloudFormation stack and CodePipeline status, configuration repository and CodePipeline status, and overall deployment health with graceful offline fallback when AWS access is unavailable. Detailed diagnostics remain in `lza status installer` and `lza status config`.

### `lza status installer`

Show detailed installer stack status, deployed configuration drift, and optional explicit state or
configuration synchronization.

### `lza status config`

Show detailed configuration repository status, remote source existence/accessibility, local Git working-tree status and remote revision comparison, configuration pipeline status, and operational metadata.

### `lza doctor`

Run advisory local and AWS checks for the current workspace. The command reports problems and suggested remediation without modifying local files or AWS resources.

Implementation checklist:

- [ ] Run the shared local checks defined for [`lza validate`](#lza-validate).
- [ ] Validate AWS profile access.
- [ ] Validate expected AWS account.
- [ ] Produce a concise pass, warning, and failure summary.
- [ ] Suggest a remediation plan for failed or incomplete checks.

Future design decision:

- [ ] Decide whether to add an explicit `--fix` mode. Do not implement mutation as part of the current diagnostic command.

## Workspace

- [ ] Support workspace schema migration.
- [ ] Generate JSON Schema for editor support.
- [ ] Resolve the account ID from authenticated AWS identity, including profile-based
  authentication, and persist the accepted value in `lza-workspace.yaml`.

## Authentication

- [ ] Reassess and likely remove application-managed source credential priming after selecting the
  preferred external AWS authentication approach. Keep priming opt-in in the meantime.
- [ ] Add an AWS profile creation or authentication-onboarding helper.
- [ ] Support AWS IAM Identity Center (SSO) profile bootstrap.
- [ ] Support static-key profile bootstrap without storing credentials in workspace metadata.
- [ ] Support AssumeRole profile configuration.
- [ ] Document bastion and proxy setup where required.

## Configuration Templates

- [ ] Validate template compatibility with selected LZA version.
- [ ] Support Git template source.
- [ ] Support Bitbucket template source.
- [ ] Support template version/ref.
- [ ] Support cached templates.

## Testing & Quality Assurance

- [ ] Add unified End-to-End Workspace Lifecycle integration test (`tests/cli/test_lifecycle_e2e.py`) covering sequential execution: `lza init` -> `lza config init` -> `lza bootstrap` -> `lza installer init` -> `lza installer plan` -> `lza installer deploy` -> `lza config push` -> `lza status`.
- [ ] Add error resilience tests for corrupted/partial `.lza/state.json` and malformed `lza-workspace.yaml` files to verify clean recovery guidance.
- [ ] Add error reporting tests for Git merge conflicts and remote authentication failures during `lza config pull`.
- [ ] Add CloudFormation template size limit boundary test verifying S3 `TemplateURL` is always used when templates exceed 51.2 KB.
- [ ] Streamline `test_config_download.py` and `test_config_upload.py` to focus on alias routing while retaining the full synchronization matrix in `test_config_pull.py` and `test_config_push.py`.
- [ ] Configure Pytest markers (`unit`, `cli`, `e2e`, `arch`) in `pyproject.toml` for targeted test runs.

## Reports

- [ ] Decide whether reports use `lza report` with one subcommand per report type.
- [ ] Generate `reports/aws-profile-check.md`.
- [ ] Generate `reports/status.md`.
- [ ] Generate pipeline execution reports.
- [ ] Generate CodeBuild failure summaries.

## LZA Versions

- [ ] Support blocked/unsupported versions list.
- [ ] Auto-discover latest LZA versions.
- [ ] Cache installer templates.
- [ ] Warn on unstable or very old versions.
- [ ] Support migration helper between LZA versions.
- [ ] Validate installer template compatibility with the selected LZA version.

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

AI features remain advisory by default; execution must be a separate explicit action.

## Distribution

- [ ] Audit CLI defaults for safe, non-destructive behavior.
- [ ] Standardize actionable error messages and remediation guidance.
- [ ] Add command examples.
- [ ] Add contribution guidelines.
- [ ] Remove personal/company-specific hardcoding.

## Backlog

- [ ] GUI or TUI.
- [ ] Web interface.
- [ ] Multi-user/server mode.
