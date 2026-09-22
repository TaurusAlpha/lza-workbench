# LZA Workbench TODO

This file maintains the command inventory, planned features, improvements, unresolved design
decisions, and technical debt. Completed items may remain checked until they are manually verified
and removed.

## Command Inventory

Keep this as the canonical inventory of implemented and planned command names. Planned commands
are identified explicitly in their reference sections.

### Workspace lifecycle

- `lza init`
- `lza import`
- `lza uninstall`
- `lza ui`

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

### `lza ui`

Start the local Web interface for workspace setup, status, configuration synchronization, pipeline
inspection, and supported deployment lifecycle operations.

### Workspace AWS ownership

Workspace owns local lifecycle and persistence. Feature deployment actions own the AWS resources
they explicitly require. `lza installer deploy` owns installer prerequisites; configuration
synchronization never provisions missing remotes.

#### Installer prerequisite ownership

- [ ] If retained, define its contract as preparation of shared workspace operational substrate:
  workspace-owned paths/metadata, the Workbench assets bucket, and cross-feature prerequisite
  coordination. It must not become the owner of installer source policy or configuration
  repository policy.

#### Future installer prerequisite enhancements

Installer prerequisites are reconciled from the current installer configuration in `lza-workspace.yaml`.

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
  - Keep installer source packaging, upload, and S3-specific installer template synthesis under installer deployment.

#### Configuration repository

- [x] `ConfigurationRepositoryLocation=codecommit`

- [ ] `ConfigurationRepositoryLocation=codeconnection`
  - On init, changed configuration, and import:
    - Require `ConfigCodeConnectionArn`.
    - Require the configured repository owner, name, and branch.
    - Validate that the CodeConnections connection exists and is accessible.
    - Validate repository accessibility where possible.
    - Do not create CodeConnections or external repository resources.

- [ ] `ConfigurationRepositoryLocation=s3`
  - Treat as a separate LZA-specific configuration workflow.
  - Do not create the LZA-managed `aws-accelerator-config-<account-id>-<region>` bucket during configuration synchronization.
  - When importing an existing deployment, validate the discovered bucket and access.
  - Revisit exact configuration deployment behavior when S3 configuration deployment support is implemented.

### `lza config init`

Initialize local LZA configuration in the current workspace from a packaged configuration template.

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

### `lza installer import`

Discover a deployed installer stack and reconcile its CloudFormation parameters and template data
with the current workspace.

### `lza uninstall`

Uninstall the LZA solution rather than deleting only the installer stack across managed accounts and regions.

Implementation notes:

- AWS retains some data-bearing resources to avoid accidental data loss, so preservation and cleanup choices must be explicit.
- Reference: <https://docs.aws.amazon.com/solutions/latest/landing-zone-accelerator-on-aws/uninstall-the-solution.html>.

### `lza config push` and `lza config upload`

Synchronize the local customer `aws-accelerator-config` to the configured remote configuration source without starting the LZA pipeline.

### `lza config pull` and `lza config download`

Synchronize the configured remote customer configuration source into the local
`aws-accelerator-config` directory.

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

### `lza status installer` and `lza installer status`

Show detailed installer stack status, deployed configuration drift, and optional explicit state or
configuration synchronization.

### `lza status config` and `lza config status`

Show detailed configuration repository status, remote source existence/accessibility, local Git working-tree status and remote revision comparison, configuration pipeline status, and operational metadata.

## Web Interface

The local Web GUI is the primary planned interactive interface.

- [ ] Add installer deployment mutation flow.
- [ ] Keep multi-user/server operation out of the current scope.

## Workspace

- [ ] Support workspace schema migration.

## Package Boundaries

- [ ] Keep one-file support modules as modules unless a subpackage has multiple cohesive internal
  modules or establishes a real boundary. Reassess new directories against this rule during future
  refactors.

## Authentication

- [ ] Reassess and likely remove application-managed source credential priming after selecting the
  preferred external AWS authentication approach. Keep priming opt-in in the meantime.
- [ ] Support AWS IAM Identity Center (SSO) profile discovery.
- [ ] Document bastion and proxy setup where required.

## Configuration Templates

- [ ] Validate template compatibility with selected LZA version.
- [ ] Support Git template source.
- [ ] Support template version/ref.
- [ ] Support cached templates.

## Reports

- [ ] Decide whether reports use `lza report` with one subcommand per report type.
- [ ] Generate `reports/aws-profile-check.md`.
- [ ] Generate `reports/status.md`.
- [ ] Generate pipeline execution reports.
- [ ] Generate CodeBuild failure summaries.

## LZA Versions

- [ ] Auto-discover latest LZA versions.
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

AI features remain advisory by default; execution must be a separate explicit action.

## Distribution

- [ ] Audit CLI defaults for safe, non-destructive behavior.
- [ ] Standardize actionable error messages and remediation guidance.

## Backlog

- [ ] Expand "Environment Context" into a dedicated workspace details page showing AWS Organization context (Control Tower, accounts, OUs) and workspace lifecycle actions.
- [ ] Generate JSON Schema for editor support.
