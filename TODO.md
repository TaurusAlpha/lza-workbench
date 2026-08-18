# LZA Workbench TODO

Historical work is recorded in [`docs/DONE.md`](docs/DONE.md). This file tracks active features,
unresolved design decisions, and technical debt.

## CLI Commands

- [ ] `lza uninstall`
- [ ] `lza config deploy`
- [ ] `lza pipeline start`
- [ ] `lza pipeline watch`
- [ ] `lza doctor`
- [ ] `lza installer init`
- [x] `lza bootstrap`

### `lza bootstrap`

Create or validate AWS prerequisite resources required by LZA Workbench.
The command can be run at any time after workspace creation and is idempotent.
Bootstrap is create/validate only. It must never delete resources.

Implementation checklist:

---

Implementation notes:

- The Workbench assets bucket is owned by LZA Workbench.
- It may be created for both newly initialized and imported workspaces.
- The bucket may later store installer templates, state, workspace configuration, and other Workbench-managed assets.
- Bootstrap never deletes or cleans up AWS resources.

### Future `lza bootstrap` enhancements

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

- [] `ConfigurationRepositoryLocation=codecommit`
  - On init or changed configuration:
    - Default `UseExistingConfigRepo=true`.
    - Create or validate the `lza-config-source` CodeCommit repository in the management account.
    - Default `ExistingConfigRepositoryBranchName` to `main`.
    - The installer workflow may then push the initial/basic LZA configuration before installer deployment.
  - On import:
    - Validate that the configured repository and branch exist and are accessible.
    - Do not recreate missing imported resources automatically.

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

- [ ] Repair missing or invalid workspace metadata.
- [ ] Parse and validate imported YAML content.
- [ ] Integrate version-aware official LZA schema validation.
- [ ] Record or resolve remote/Git template provenance.

### `lza installer init`

- [ ] Add support for different parameters according to chosen options

### `lza installer deploy`

Reconcile the locally configured installer desired state with AWS for both initial deployment and later updates.

- [ ] Prepare and synchronize installer source code across Amazon S3, AWS CodeCommit, and the official AWS GitHub repository when the configured LZA version or source settings require it.
- [ ] Define provider-specific prerequisites, version/ref resolution, packaging, upload, and drift detection.
- [ ] Keep source preparation separate from customer `aws-accelerator-config` management.
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

### `lza config upload`

Upload the customer `aws-accelerator-config` to an S3-backed LZA configuration source without starting the LZA pipeline.

This command is the explicit S3 transfer utility. Other configuration repository types require their own synchronization behavior and are future work.

- [ ] Keep non-S3 repository synchronization out of this command unless its semantics are explicitly redesigned.

### `lza config download`

Download the current `aws-accelerator-config` from the configured LZA configuration source into the customer workspace.

- [ ] Support additional repository types:
  - Git repository
  - Bitbucket repository
  - Future custom repository providers
- [ ] Validate the downloaded configuration structure.
- [ ] Verify download integrity with checksums or signatures.
- [ ] Detect identical local and remote configurations and skip unnecessary downloads.

### `lza config deploy`

Synchronize the local customer configuration to its configured deployment destination.

By default, the command uploads or synchronizes configuration and then stops. It does not implicitly start or watch the LZA pipeline.

Implementation checklist:

- [ ] Validate the local configuration and configured destination.
- [ ] Show the target and planned synchronization changes.
- [ ] Upload or synchronize the configuration using provider-specific behavior.
- [ ] Stop after synchronization when no execution flags are supplied.
- [ ] Support `--execute` to start the relevant configuration pipeline after successful synchronization.
- [ ] Support `--watch` to watch the started execution; imply `--execute` when necessary.
- [ ] Record the upload/synchronization result and started pipeline execution ID in `.lza/state.json`.
- [ ] Reuse the same start/watch services as the separate pipeline commands.
- [ ] Support `--dry-run`.

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

Monitor an LZA pipeline execution. This remains available independently of `lza config deploy --watch`.
Implementation checklist:

- [ ] Use the latest execution ID recorded in `.lza/state.json` by default when available.
- [ ] Fall back to discovering the latest execution when no recorded execution ID is available.
- [ ] Support a specific execution ID.
- [ ] Show stage and action status.
- [ ] Refresh output without excessive API calls.
- [ ] Detect failed CodeBuild actions.
- [ ] Show relevant failure details.
- [ ] Exit successfully when the pipeline succeeds.
- [ ] Return a non-zero exit code when the pipeline fails.

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
