# LZA Workbench TODO

Historical work is recorded in [`docs/DONE.md`](docs/DONE.md). This file tracks active features,
unresolved design decisions, and technical debt.

## CLI Commands

Keep for reference. Do not delete commands from this list even if they are implemented.

- [ ] `lza init`
- [ ] `lza import`
- [ ] `lza bootstrap`
- [ ] `lza uninstall`
- [ ] `lza validate`
- [ ] `lza diff`
- [ ] `lza installer init`
- [ ] `lza installer plan`
- [ ] `lza installer deploy`
- [ ] `lza installer status`
- [ ] `lza status`
- [ ] `lza config init`
- [ ] `lza config download`
- [ ] `lza config upload`
- [ ] `lza config push`
- [ ] `lza config pull`
- [ ] `lza config deploy`
- [ ] `lza config status`
- [ ] `lza pipeline start`
- [ ] `lza pipeline watch`
- [ ] `lza doctor`

### `lza bootstrap`

Create or validate AWS prerequisite resources required by LZA Workbench.

#### Future `lza bootstrap` enhancements

Bootstrap installer and configuration prerequisites based on the current installer configuration in `lza-workspace.yaml`.

The future implementation should preserve the following behavior:

#### Installer source

- [] `RepositorySource=github`
  - On init or changed configuration:
    - Do not create repository resources.
    - Validate the `accelerator/github-token` secret.
    - Validate that the configured repository is accessible using the token.
  - On import:
    - Validate the retrieved installer parameters.
    - Validate the secret and repository accessibility.
    - Do not create resources.

- [] `RepositorySource=codecommit`
  - On init or changed configuration:
    - Create or validate the `lza-installer-source` CodeCommit repository in the management account.
  - On import:
    - Validate that the configured repository exists and is accessible.
    - Do not recreate missing imported resources automatically.

- [] `RepositorySource=s3`
  - On init or changed configuration:
    - Create or validate the versioned
      `s3-lza-installer-source-<account-id>-<region>` bucket.
  - On import:
    - Validate that the configured bucket exists and is accessible.
    - Do not recreate missing imported resources automatically.
  - Keep installer source packaging, upload, and S3-specific installer template synthesis outside bootstrap.

#### Configuration repository

- [x] `ConfigurationRepositoryLocation=codecommit`
  - On init or changed configuration:
    - [x] Default `UseExistingConfigRepo=true`.
    - [x] Create or validate the `lza-config-source` CodeCommit repository in the management account.
    - [x] Default `ExistingConfigRepositoryBranchName` to `main`.
    - [x] The installer workflow may then push the initial/basic LZA configuration before installer deployment.
  - On import:
    - [x] Validate that the configured repository and branch exist and are accessible.
    - [x] Do not recreate missing imported resources automatically.

- [] `ConfigurationRepositoryLocation=codeconnection`
  - On init, changed configuration, and import:
    - Require `ConfigCodeConnectionArn`.
    - Require the configured repository owner, name, and branch.
    - Validate that the CodeConnections connection exists and is accessible.
    - Validate repository accessibility where possible.
    - Do not create CodeConnections or external repository resources.

- [] `ConfigurationRepositoryLocation=s3`
  - Treat as a separate LZA-specific configuration workflow.
  - Do not currently create the LZA-managed
    `aws-accelerator-config-<account-id>-<region>` bucket during bootstrap.
  - When importing an existing deployment, validate the discovered bucket and access.
  - Revisit exact bootstrap behavior when S3 configuration deployment support is implemented.

#### Import and change semantics

- [] Treat resources discovered through `lza installer import` as existing deployment resources.
- [] Imported resources are validation-only; bootstrap must not recreate or replace them automatically.
- [] If the user later explicitly changes installer or configuration source settings, treat the new desired resources as newly configured resources and apply the corresponding init/create behavior.
- [] Bootstrap must never delete old repositories, buckets, branches, connections, or other resources after configuration changes.

### `lza init`

Create a new customer-specific LZA workspace.

- [ ] Support selecting a packaged template when multiple templates exist.
- [ ] Init local git repository in LZA configuration directory and "init" commit.
  Check for correlation if configuration repo is already stored in Git or CodeCommit or other supported repository.

### `lza import`

Adopt an existing local LZA configuration without modifying customer-owned files.

- [x] Repair missing or invalid workspace metadata.
- [x] Parse and validate imported YAML content.
- [x] Integrate version-aware official LZA schema validation.
- [x] Record or resolve remote/Git template provenance.
- [ ] Add live AWS discovery during import: query CloudFormation for `AWSAccelerator-InstallerStack` and `AWSAccelerator-PipelineStack` to automatically extract and populate deployed parameters (`ConfigurationRepositoryLocation`, account emails, `EnableApprovalStage`, LZA version, etc.) into `lza-workspace.yaml` and `.lza/state.json`.
- [ ] Add graceful error handling and guidance if AWS authentication fails or `--skip-aws-check` is used: explain that live stack introspection was skipped, and suggest verifying AWS credentials and running `lza import` or running `lza installer status --sync-config` / `lza installer plan --sync-config`.
- [ ] Add context-aware next-step recommendations after import (e.g., recommend `lza config download` if configuration is S3-backed and unverified, or `lza validate` / `lza config push`).
- [ ] Track imported workspace state flag in `.lza/state.json` (e.g. `imported: true` or `config_synced: false`) until installer/config is downloaded, pulled, or deployed at least once using the tool.

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
- [ ] Integrate official/version-aware LZA schema validation.
- [ ] Validate installer configuration and required parameters.
- [ ] Detect inconsistent settings between workspace, installer, and configuration metadata.
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

- [ ] Normalize LZA version strings (e.g. prefixing `v` for `vX.Y.Z`) when constructing the official AWS solutions-reference installer template download URL (`https://s3.amazonaws.com/solutions-reference/landing-zone-accelerator-on-aws/v{version}/AWSAccelerator-InstallerStack.template`) to prevent 404 download failures for un-prefixed version inputs (such as `1.15.5`).
- [ ] Provide better error diagnostics and fallback resolution when downloading non-packaged installer template versions from the public S3 URL.
- [ ] Add support to ask for different parameters according to chosen options. For example don't ask for codeconnection arn if github was chosen as source. Don't ask for github token if codeconnection was chosen as source.

### `lza installer plan`

Inspect AWS and display the CloudFormation actions and changes required to deploy the installer stack.

### `lza installer deploy`

Deploy or update the LZA installer CloudFormation stack in the management account.

Future design decision:

- [ ] Prepare and synchronize installer source code across Amazon S3, AWS CodeCommit, and the official AWS GitHub repository when the configured LZA version or source settings require it.
- [ ] Follow the AWS source-location requirements for S3 packaging and synthesized installer parameters: <https://docs.aws.amazon.com/solutions/latest/landing-zone-accelerator-on-aws/source-code-location.html>.

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

- [ ] Check configuration source that will be used in installer. If S3 then with template initialize local git repo in the `aws-accelerator-config` folder.

### `lza config download`

Download LZA configuration from the configured remote source into the local workspace (alias for `lza config pull`).

### `lza config upload`

Upload local LZA configuration to the configured remote repository or S3 bucket (alias for `lza config push`).

### `lza config push`

Synchronize the local customer `aws-accelerator-config` to the configured remote configuration source without starting the LZA pipeline.

- [ ] Fix default packaging exclusions: remove `"backup"` from `PackagingExcludeConfig.directories` so customer AWS Backup definitions (e.g. `backup/backup-*.json`) are not omitted from configuration archives. Default exclusions should only target `.git`, `.DS_Store`, etc.
- [ ] Add support to parse and honor `.gitignore` / `.prettierignore` when packaging local configuration files for S3 upload.
- [ ] Fix zip diff calculation: filter out directory-level records (entries ending with `/`) in `read_zip_manifest` so directory records from existing zip archives are not incorrectly reported as removed files.
- [ ] Add safety check for S3-backed imported workspaces: if workspace was imported and has not yet synced/downloaded remote configuration from S3, warn the user that local configuration may overwrite unverified remote S3 state, requiring `--force` (or interactive confirmation) and recommending `lza config download` first.
- [ ] Auto-derive standard S3 configuration bucket name: when `ConfigurationRepositoryLocation=s3`, automatically derive the deterministic bucket name (`aws-accelerator-config-<account-id>-<region>` or `<prefix>-config-<account-id>-<region>`) and persist it into `lza-workspace.yaml` during import / `status --sync-config` / `config push` / `config pull` without prompting the user.

### `lza config pull`

Synchronize the configured remote customer configuration source into the local `aws-accelerator-config`.

### `lza config deploy`

Synchronize the local customer configuration to its configured deployment destination, start the LZA pipeline, and optionally wait for the execution to complete.

By default, the command performs the full deployment workflow:

```text
config push -> pipeline start -> pipeline watch
```

### `lza pipeline start`

Start the configured LZA pipeline without synchronizing configuration.

This command remains available independently for cases where the existing remote configuration should be executed again without another `lza config push`.

### `lza pipeline watch`

Monitor an existing LZA pipeline execution without starting or synchronizing anything.

This command remains available independently for reconnecting to or inspecting an execution started previously by `lza pipeline start`, `lza config deploy`, or another mechanism.

### `lza status`

Provide the single status entry point for the customer LZA workspace.

`lza status` shows the overall summary. Filtered views or subcommands such as `lza status installer`, `lza status config`, and `lza status pipeline` show component detail without separate top-level status commands.

### `lza doctor`

Run advisory local and AWS checks for the current workspace. The command reports problems and suggested remediation without modifying local files or AWS resources.

Implementation checklist:

- [ ] Run the shared local checks defined under [Validation](#validation).
- [ ] Validate AWS profile access.
- [ ] Validate expected AWS account.
- [ ] Produce a concise pass, warning, and failure summary.
- [ ] Suggest a remediation plan for failed or incomplete checks.

Future design decision:

- [ ] Decide whether to add an explicit `--fix` mode. Do not implement mutation as part of the current diagnostic command.

## Workspace

- [ ] Support workspace schema migration.
- [ ] Generate JSON Schema for editor support.
- [ ] Resolve account ID from authenticated AWS identity when available.
- [ ] Allow account ID to be derived from AWS profile configuration when reliably possible.
- [ ] Persist the accepted account ID in `lza-workspace.yaml`.

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

## Validation

- [ ] Validate `lza-workspace.yaml`.
- [ ] Validate YAML formatting.
- [ ] Integrate official LZA schema validation.
- [ ] Validate configuration replacement variables consistency (cross-validate placeholders in configuration files with variables defined in replacements-config.yaml or installer options).
- [ ] Validate workspace structure.
- [ ] Validate installer configuration.
- [ ] Validate upload target.
- [ ] Detect common LZA configuration mistakes.

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
- [ ] Generate config diff reports.

## LZA Versions

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

- [ ] Audit CLI defaults for safe, non-destructive behavior.
- [ ] Standardize actionable error messages and remediation guidance.
- [ ] Add command examples.
- [ ] Add contribution guidelines.
- [ ] Remove personal/company-specific hardcoding.
- [ ] Add end-to-end CLI tests for core workflows.

## Backlog

- [ ] GUI or TUI.
- [ ] Web interface.
- [ ] Multi-user/server mode.
