# LZA Workbench TODO

Historical work is recorded in [`docs/DONE.md`](docs/DONE.md). This file tracks active features,
unresolved design decisions, and technical debt.

## CLI Commands

Keep for reference. Do not delete commands from this list even if they are implemented.

- [ ] `lza init`
- [ ] `lza import`
- [ ] `lza bootstrap`
- [ ] `lza uninstall`
- [ ] `lza installer init`
- [ ] `lza installer plan`
- [ ] `lza installer deploy`
- [ ] `lza status`
- [ ] `lza config init`
- [ ] `lza config download`
- [ ] `lza config upload`
- [ ] `lza config push`
- [ ] `lza config pull`
- [ ] `lza config deploy`
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

Collect and persist installer CloudFormation parameters and workspace settings.

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

### `lza config pull`

Synchronize the configured remote customer configuration source into the local `aws-accelerator-config`.

### `lza config deploy`

Synchronize the local customer configuration to its configured deployment destination and execute the LZA pipeline.

By default, the command synchronizes configuration and then starts and watches the LZA pipeline.

Implementation checklist:

- [ ] Reuse the same local-to-remote synchronization workflow as `lza config push`.
- [ ] Validate the local configuration and configured destination.
- [ ] Show the target and planned synchronization changes.
- [ ] Synchronize configuration using provider-specific behavior.
- [ ] Start the configured LZA pipeline after successful synchronization.
- [ ] Support `--watch` to watch the started execution; imply `--execute` when necessary.
- [ ] Record the synchronization result and started pipeline execution ID in `.lza/state.json`.
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

- [ ] Validate template compatibility with selected LZA version.
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
