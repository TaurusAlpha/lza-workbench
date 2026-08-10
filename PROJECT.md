# LZA Workbench

## Purpose

LZA Workbench is a local, workspace-based helper tool for AWS Landing Zone Accelerator engineers.

Its initial goal is to automate the customer onboarding/init phase for AWS Landing Zone Accelerator by creating a clean customer workspace, copying selected LZA configuration templates, generating workspace metadata, and providing helper commands for common LZA bootstrap operations.

The tool starts as a personal productivity helper but should be structured cleanly enough to become usable by coworkers or the wider community later.

## Scope

This project is strictly focused on AWS Landing Zone Accelerator related workflows.

In scope:

- Create customer-specific LZA workspace folders.
- Copy or initialize `aws-accelerator-config`.
- Use local or Git-based LZA configuration templates.
- Generate and store workspace metadata.
- Resolve the LZA installer stack template from the official remote template or a local workspace copy, as required.
- Plan installer configuration and reconcile the deployed installer with that desired state.
- Generate helper scripts or commands for LZA bootstrap workflows.
- Validate that the selected AWS profile can access the target account as shared command preflight behavior and through diagnostics.
- Support multiple LZA versions.
- Support different configuration repository locations such as S3, CodeCommit, or GitHub where applicable.
- Keep the code expandable for future config generation, validation, and AI/MCP assistance.

## Non-Goals

The following are intentionally outside the scope of this project unless explicitly revisited in the future:

- Managing general AWS infrastructure unrelated to AWS Landing Zone Accelerator.
- Acting as a generic DevOps platform.
- Replacing AWS authentication tooling.
- Automatically designing complex customer network or security architectures.
- Becoming a server-side, multi-user application.
- Allowing AI to autonomously modify customer environments.

## Core Principle

The tool should not own AWS authentication.

If the following command works, the tool should be able to use that profile:

```bash
aws sts get-caller-identity --profile <profile-name>
```

Authentication methods such as AWS SSO, static access keys, AssumeRole chains, bastion-based access, or proxy-based access are the user's responsibility.

AWS authentication management may be considered later as a low-priority feature.

### AWS Client Management

The application should have a single, centralized mechanism for creating AWS sessions and service clients.

- All boto3 `Session` and service client creation must go through `AwsClientFactory`.
- Commands should create one factory instance per execution and reuse it for all AWS interactions.
- AWS service modules (CloudFormation, S3, CodeCommit, STS, etc.) should not create their own sessions or clients.
- Service modules should operate on injected boto3 clients rather than managing authentication themselves.
- Authentication, credential resolution, retry behavior, and future client configuration should be implemented only in `AwsClientFactory`.

## Workspace Model

The tool is workspace-based.

Each customer gets an independent local workspace.

Example:

```text
customers/
  comm-it/
    lza-workspace.yaml
    aws-accelerator-config/
    aws-accelerator-installer/
    scripts/
    .lza/
```

The tool should be able to manage one customer or many customers without requiring a central server or shared database.

## Source of Truth

Each customer workspace should contain a workspace metadata file.

Recommended name:

```text
lza-workspace.yaml
```

This file stores the key decisions used during initialization and later operations. `lza-workspace.yaml` is the declarative source of truth. Runtime and execution metadata is stored separately in `.lza/state.json`.

Example:

```yaml
customer:
  name: Example Customer
  slug: example-customer

aws:
  profile: example-root
  region: eu-west-1

configuration:
  local_path: customer-accelerator-config
  template:
    source: git
    repository: https://github.com/example/lza-config-templates.git
    ref: main
    path: templates/default
  repository:
    type: git
    repository: git@github.com:example/customer-lza-config.git
    branch: main
```

The CLI may collect these values interactively, but it should persist them into this file so the workspace remains repeatable.

## Template Model

Templates may come from:

- bundled templates
- local folder
- Git repository
- Bitbucket repository
- future custom template providers

Initial version supports the bundled default template and local template folders. Git and Bitbucket template sources are future work.

Example:

```yaml
lza:
  template_source_type: local
  template_source: ~/templates/lza/default
```

After a template is copied into a customer workspace, it becomes customer-owned configuration.

The copied `aws-accelerator-config` should be treated as the customer's working LZA configuration.

## First Supported Workflow

The first supported workflow is customer initialization. The primary entry point is:

```bash
lza init comm-it
```

This workflow creates a new customer workspace, collects the minimum required workspace metadata, copies the selected LZA configuration template, creates local state, validates the selected AWS profile unless skipped, and leaves the workspace ready for the next deployment steps. The exact implementation of this workflow is intentionally maintained in TODO.md rather than this document.

## Workspace Layout

```text
comm-it/
  lza-workspace.yaml

  aws-accelerator-config/
    global-config.yaml
    organization-config.yaml
    accounts-config.yaml
    network-config.yaml
    security-config.yaml
    replacements-config.yaml

  aws-accelerator-installer/
    AWSAccelerator-InstallerStack.template.json

  .lza/
    state.json
    logs/
```

## State Model

No database is required initially.

Local state may be stored under:

```text
.lza/state.json
```

Example state:

```json
{
  "initialized_at": null,
  "updated_at": null,
  "management_account_id": null,
  "caller_arn": null,
  "installer_stack_id": null
}
```

State should never duplicate configuration already present in `lza-workspace.yaml`.
It exists only to store information discovered or produced during command execution.

## Installer Model

The installer consists of two independent components:

- The CloudFormation installer stack template.
- The Landing Zone Accelerator source code consumed by the installer.

The customer configuration (`aws-accelerator-config`) is managed independently and should not be coupled to installer source management.

Installer deployment capabilities are being introduced incrementally based on practical customer workflows rather than a predefined end-state.

The workspace model should describe the desired installer source independently of its implementation so source preparation and synchronization can be added for Amazon S3, AWS CodeCommit, and the official AWS GitHub repository without changing the overall configuration model. Provider-specific source preparation is future work.

`lza installer plan` is the configuration collection step. It should collect every available installer template parameter, apply explicit defaults where appropriate, validate the result, and persist the accepted desired state in `lza-workspace.yaml`. Later installer commands should rely on that persisted state rather than recollecting configuration.

`lza installer deploy` reconciles the locally configured desired state with AWS for both initial installation and later updates. It should preview create, update, or no-change behavior and ask for confirmation before applying changes unless explicitly bypassed. A separate `lza installer update` command is not part of the command model.

Installer template handling depends on whether the template must be modified. A local template is required when a change such as disabling anonymous data sharing must be applied. When no template modification is needed, the official remote template may be usable. Whether to retain both paths or standardize on local templates remains a design decision.

AWS context:

- [Installer pipeline](https://docs.aws.amazon.com/solutions/latest/landing-zone-accelerator-on-aws/awsaccelerator-installer.html)
- [Source code location](https://docs.aws.amazon.com/solutions/latest/landing-zone-accelerator-on-aws/source-code-location.html)

Detailed command behavior, implementation phases, and provider-specific functionality are intentionally maintained in `TODO.md` rather than this document.

## Command Model

- `lza installer plan` resolves and persists installer configuration without changing AWS.
- `lza installer deploy` handles both initial deployment and updates by reconciling local desired state with AWS.
- Installer template download is internal to planning and deployment rather than a standalone command.
- `lza config upload` transfers configuration to an S3-backed configuration source without starting the pipeline.
- `lza config deploy` synchronizes configuration and stops by default; optional flags may start and/or watch the configuration pipeline.
- `lza pipeline start` and `lza pipeline watch` remain separate commands for explicit pipeline control.
- `lza status` is the single status entry point, with an overall summary and installer, configuration, and pipeline filtered views.
- `lza doctor` runs diagnostic checks and reports advice without modifying local files or AWS resources. A future `--fix` mode is an undecided enhancement, not current behavior.
- `lza uninstall` is a top-level, destructive solution lifecycle command rather than an installer-stack delete command. It must make preservation choices explicit because a complete LZA uninstall spans the Installer and Core pipelines, retained data, and additional regional/account stacks.

The standalone commands `lza profile check`, `lza installer download`, `lza installer update`, `lza installer status`, and `lza installer delete` are not part of the command model.

## Workspace Configuration Model

`lza-workspace.yaml` is represented internally by strongly typed Pydantic models.
The workspace configuration is loaded, validated, and exposed through typed objects rather than untyped dictionaries.
Derived values should be calculated at runtime instead of persisted whenever practical.

### Workspace Readiness

Workspace commands operate against explicit readiness levels rather than independently checking individual configuration values.

#### Core Workspace Configuration

A workspace is core-configured when the minimum values required for normal command execution are present.

Core values currently include:

- AWS profile
- AWS region

`lza init` and `lza import` are responsible for establishing or completing core workspace configuration. They may accept these values through CLI options or interactive prompts.

Commands other than `lza init` and `lza import` must not interactively collect or repair missing core workspace configuration.

If a required core value is missing, the command must fail before command-specific logic or AWS operations and clearly report the missing values.

#### Workspace Readiness Levels

The workspace progresses through increasingly complete states:

- **Uninitialized** — no valid LZA Workbench workspace exists.
- **Core configured** — required core workspace configuration is present.
- **Imported** — a valid customer `aws-accelerator-config` and required LZA Workbench metadata are present.
- **Configured** — command-specific configuration required for installer planning or deployment is present.
- **Deployed** — the installer has been deployed and deployment state has been recorded.

Commands should validate the minimum readiness level they require before executing command-specific logic.

Readiness levels describe workspace state, not AWS authentication validity or deployed-resource health. Those should be validated separately by commands that require them.

Command-specific optional values may still be accepted through CLI options when appropriate.

## Current Technical Direction

The current implementation is expected to use the following technologies. These are implementation preferences rather than permanent architectural decisions:

- Python
- Typer for CLI
- Pydantic for config/schema validation
- boto3 for AWS API calls
- ruamel.yaml for YAML read/write while preserving formatting
- Rich for CLI output
- pytest for tests

The tech stack is not final and may be changed later.

## Design Guidelines

- Keep the first version simple.
- Prefer explicit local files over hidden logic.
- Avoid hardcoded company-specific values.
- Make every generated file reviewable.
- Prefer dry-run behavior where possible.
- Do not mutate AWS resources without clear command intent.
- Keep complex LZA config generation out of the MVP.
- Structure code so modules can be extended later.
- Centralize AWS SDK initialization and authentication logic in a single component.

## Future Direction

The following capabilities are considered natural evolution of the project. Their prioritization and implementation details are intentionally maintained in TODO.md.

- config validation
- schema-aware editing
- LZA version discovery
- pipeline monitoring
- CodeBuild log summarization
- config diff reports
- account/OU generators
- network pattern generators
- security pack side-loading
- SCP/RCP/config-rule packs
- optional MCP/AI assistant integration

AI should assist, suggest, validate, and troubleshoot. It should not become the primary execution engine in the early versions.
