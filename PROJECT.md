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
- Copy or resolve the LZA installer stack template.
- Generate helper scripts or commands for LZA bootstrap workflows.
- Validate that the selected AWS profile can access the target account.
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

## Workspace Model

The tool is workspace-based.

Each customer gets an independent local workspace.

Example:

```text
customers/
  comm-it/
    lza-workbench.yaml
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

This file stores the key decisions used during initialization and later operations.

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

## Workspace Model

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

State should only contain operational metadata. The main declarative source of truth should remain `lza-workbench.yaml`.

## Current Technical Direction

The current implementation is expected to use the following technologies. These are implementation preferences rather than permanent architectural decisions:

- Python
- Typer for CLI
- Pydantic for config/schema validation
- boto3 for AWS API calls
- ruamel.yaml for YAML read/write while preserving formatting
- Jinja2 for templates
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
