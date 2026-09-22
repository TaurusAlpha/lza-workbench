# File Architecture

This is a short human-facing map of where project files belong and what they own. The application
tree is generated from the filesystem and the first line of each module purpose docstring by
running `make file-architecture`.

## Repository Overview

```text
AGENTS.md                 # Rules for agents working in this repository
README.md                 # Operational setup, usage, and command reference
PROJECT.md                # Product scope, architecture, and durable project decisions
TODO.md                   # Command inventory and accepted technical implementation work
ROADMAP.md                # Product directions that require discussion before implementation
Makefile                  # Documentation generation entry points
pyproject.toml            # Python package, dependencies, tools, and command entry point
docs/                     # Human-facing architecture and manual review guidance
scripts/                  # Repository maintenance and documentation generators
src/lza_workbench/        # Application source and packaged resources
tests/                    # Automated behavior and architecture checks
```

## Application Source

Package and module descriptions below come from their purpose docstrings. `__init__.py` files and
individual static or packaged resource files are omitted to keep the map compact.

<!-- BEGIN GENERATED APPLICATION TREE -->
```text
src/lza_workbench/                                            # LZA Workbench package metadata.
├── configuration/                                            # Configuration feature package.
│   ├── inspection/                                           # Remote repository and pipeline inspection for LZA configuration.
│   │   ├── models.py                                         # Structured observation and status models for LZA configuration.
│   │   ├── pipeline.py                                       # Remote configuration CodePipeline inspection and failure diagnostics.
│   │   └── repository.py                                     # Remote configuration repository inspection (S3, CodeCommit, CodeConnections, Git).
│   ├── templates/                                            # Configuration template discovery, resolution, and rendering.
│   │   ├── discovery.py                                      # Resolve and validate LZA configuration templates.
│   │   └── rendering.py                                      # Resolve and render dynamic placeholders in LZA configuration templates.
│   ├── archive.py                                            # Zip archive operations for LZA configuration workspaces.
│   ├── deploy.py                                             # Workflow for deploying LZA configuration (push -> start pipeline -> watch).
│   ├── diff.py                                               # Application use case for showing configuration diffs.
│   ├── git.py                                                # Git integration utilities for LZA configuration repositories.
│   ├── initialize.py                                         # Workflow for initializing local LZA configuration from a template.
│   ├── pull.py                                               # Workflow for synchronizing remote LZA configuration to local workspace.
│   ├── push.py                                               # Workflow for synchronizing local LZA configuration to remote repositories.
│   ├── repository.py                                         # Resolved destinations and fixed conventions for LZA configuration repositories.
│   ├── runtime.py                                            # Runtime state owned by configuration synchronization actions.
│   ├── schema.py                                             # Configuration repository and packaging schema models.
│   ├── state.py                                              # Operational state updates for configuration archive transfers.
│   ├── status.py                                             # Configuration status interpretation, inspection, and reporting workflow.
│   ├── sync.py                                               # Configuration remote synchronization status evaluation and models.
│   ├── validation.py                                         # Validation utilities for LZA configuration files and schemas.
│   └── warnings.py                                           # Configuration warning compilers and diagnostic checks.
├── infrastructure/                                           # External infrastructure adapters and client session management.
│   ├── aws/                                                  # AWS infrastructure adapter package.
│   │   ├── cloudformation.py                                 # AWS CloudFormation service adapter for stack operations.
│   │   ├── codebuild.py                                      # AWS CodeBuild and CloudWatch Logs service adapter.
│   │   ├── codecommit.py                                     # Thin AWS CodeCommit service adapter.
│   │   ├── codeconnections.py                                # AWS CodeConnections integration utilities.
│   │   ├── codepipeline.py                                   # AWS CodePipeline integration utilities.
│   │   ├── dynamodb.py                                       # Thin AWS DynamoDB service adapter.
│   │   ├── ecr.py                                            # Thin AWS ECR service adapter.
│   │   ├── errors.py                                         # AWS error taxonomy and classification for adapters and workflows.
│   │   ├── iam.py                                            # Thin AWS IAM service adapter.
│   │   ├── kms.py                                            # Thin AWS KMS service adapter.
│   │   ├── logs.py                                           # Thin AWS CloudWatch Logs service adapter.
│   │   ├── organizations.py                                  # AWS Organizations service adapter for account discovery.
│   │   ├── s3.py                                             # AWS S3 service adapter for generic object and bucket operations.
│   │   ├── secrets_manager.py                                # Thin AWS Secrets Manager service adapter.
│   │   ├── session.py                                        # Centralized AWS session and execution context for LZA Workbench.
│   │   └── ssm.py                                            # Thin AWS Systems Manager Parameter Store adapter.
│   └── github.py                                             # External GitHub API validation and reachability checks.
├── installer/                                                # Installer feature package.
│   ├── source/                                               # Installer source preparation, repository inspection, and planning.
│   │   ├── inspection.py                                     # Installer source repository inspection and access verification.
│   │   └── planning.py                                       # Installer source precondition planning and CodeCommit plan results.
│   ├── templates/                                            # CloudFormation template handling and inspection for the LZA installer.
│   │   ├── digest.py                                         # Installer CloudFormation template digest and change detection.
│   │   └── retrieval.py                                      # Download, resolve, configure, and validate LZA installer CloudFormation templates.
│   ├── validation/                                           # Installer validation, preflight, and plan safety checks.
│   │   ├── config.py                                         # Installer configuration completeness validation.
│   │   └── preflight.py                                      # Installer deployment preflight and CloudFormation plan safety checks.
│   ├── versions/                                             # LZA release version normalization and deployed installer stack version detection.
│   │   ├── constants.py                                      # Normalize LZA release versions and installer repository branches.
│   │   └── detection.py                                      # Resolve the LZA version of a deployed installer stack.
│   ├── deploy.py                                             # Workflow and operations for deploying the LZA installer CloudFormation stack.
│   ├── drift.py                                              # Installer configuration drift and state alignment calculations.
│   ├── import_deployed.py                                    # Workflow for discovering and importing live AWS installer deployment parameters.
│   ├── initialize.py                                         # Interface-neutral installer settings preparation and application workflows.
│   ├── parameters.py                                         # CloudFormation parameter mapping, formatting, and template alignment for the LZA installer.
│   ├── plan.py                                               # Workflow and result models for planning LZA installer CloudFormation deployment.
│   ├── reset.py                                              # Reset installer settings to current deployed configuration.
│   ├── runtime.py                                            # Runtime state owned by installer actions.
│   ├── schema.py                                             # Installer schema and configuration models.
│   ├── state.py                                              # Operational state updates for installer deployments.
│   ├── status.py                                             # Installer stack status query, calculations, and reporting.
│   └── sync.py                                               # Synchronization helpers for reconciling workspace metadata with live AWS installer resources.
├── interfaces/                                               # User and machine interfaces for LZA Workbench.
│   ├── cli/                                                  # LZA Workbench Command Line Interface.
│   │   ├── __main__.py                                       # Module entry point for lza_workbench.interfaces.cli.
│   │   ├── configuration.py                                  # CLI commands and presentation for configuration lifecycle.
│   │   ├── input.py                                          # Interactive terminal prompt, choice selection, and input validation helpers.
│   │   ├── installer.py                                      # CLI commands and presentation for installer lifecycle.
│   │   ├── main.py                                           # LZA Workbench command-line interface.
│   │   ├── output.py                                         # Terminal rendering, formatted key-value presentation, and timestamp helpers.
│   │   ├── params.py                                         # Typer parameter declarations.
│   │   ├── pipeline.py                                       # CLI commands and presentation for pipeline execution and monitoring.
│   │   ├── status.py                                         # CLI commands and presentation for workspace status views.
│   │   ├── uninstall.py                                      # CLI command handler and rendering for lza uninstall.
│   │   └── workspace.py                                      # CLI commands and presentation for workspace lifecycle.
│   └── web/                                                  # Web interface for LZA Workbench workflows.
│       ├── static/                                           # Browser HTML, CSS, and JavaScript assets.
│       ├── app.py                                            # FastAPI application factory for the local Workbench interface.
│       ├── context.py                                        # Active workspace state for the local Web interface.
│       ├── main.py                                           # Local Uvicorn server entrypoint for the Web interface.
│       ├── serializers.py                                    # Response serialization helpers for the Web interface.
│       ├── status.py                                         # Status API adapter for the Web interface.
│       └── uninstall.py                                      # Web API router for LZA uninstallation operations.
├── pipeline/                                                 # Pipeline feature package.
│   ├── failures.py                                           # Pipeline failure interpretation shared by monitoring and status workflows.
│   ├── model.py                                              # Pipeline domain models.
│   ├── observation.py                                        # Single-pass pipeline execution observation.
│   ├── resolution.py                                         # Resolve configured LZA pipeline identities.
│   ├── runtime.py                                            # Runtime state owned by pipeline execution actions.
│   ├── start.py                                              # Workflow for starting AWS CodePipeline executions.
│   ├── state.py                                              # Operational state updates for pipeline executions.
│   ├── status.py                                             # Workflow for single-pass pipeline execution snapshots and diagnostics.
│   └── watcher.py                                            # Workflow for monitoring AWS CodePipeline executions.
├── resources/                                                # Bundled non-code assets used by LZA Workbench.
│   ├── configuration_templates/                              # Packaged configuration templates.
│   │   └── default/                                          # The default starter LZA customer configuration.
│   ├── installer_templates/                                  # Packaged installer templates.
│   │   └── v1.16.0/                                          # Packaged installer template v1.16.0.
│   └── workspace_examples/                                   # Reference workspace YAML configurations for development and documentation.
├── status/                                                   # Status and operational observation package.
│   ├── observer.py                                           # Workflow for gathering root workspace status data.
│   └── summary.py                                            # Summary presentation models for root status reporting.
├── workspace/                                                # Stable public API for loading and persisting LZA workspaces.
│   ├── layout/                                               # Workspace filesystem layout and scaffolding.
│   │   └── scaffolding.py                                    # Filesystem layout, directory scaffolding, and managed paths.
│   ├── uninstall/                                            # Workspace uninstallation feature package.
│   │   ├── executor.py                                       # Execution engine for LZA solution uninstallation.
│   │   ├── inventory.py                                      # Inventory discovery engine for LZA solution uninstallation.
│   │   ├── models.py                                         # Data models for LZA solution uninstallation.
│   │   ├── retained.py                                       # Retained resource state management and selective deletion.
│   │   └── state.py                                          # Runtime state schema for LZA uninstallation.
│   ├── validation/                                           # Workspace capability evaluation and readiness validation.
│   │   ├── capabilities.py                                   # Workspace capability enumeration and evaluation.
│   │   └── readiness.py                                      # Workspace readiness enforcement and directory structure validation.
│   ├── context.py                                            # Workspace execution context.
│   ├── import_workspace.py                                   # Workflow for importing and adopting an existing LZA workspace.
│   ├── initialize.py                                         # Workspace initialization workflow ('lza init').
│   ├── paths.py                                              # Pure workspace naming and path-discovery helpers.
│   ├── persistence.py                                        # Workspace persistence: YAML configuration and JSON state loading/saving.
│   └── schema.py                                             # Top-level workspace schema models for LZA Workbench.
└── errors.py                                                 # Common exception types for LZA Workbench.
```
<!-- END GENERATED APPLICATION TREE -->

## Core Persisted Models

Desired configuration and runtime state are stored separately:

```text
WorkspaceConfig (lza-workspace.yaml)
├── schema_version
├── customer
├── aws
├── assets_bucket
├── lza
├── installer
├── configuration
├── pipelines
└── cli_defaults

WorkspaceState (.lza/state.json)
├── timestamps and AWS identity metadata
├── import metadata
├── installer                 # InstallerRuntimeState
├── configuration             # ConfigurationRuntimeState
├── pipelines
│   ├── installer             # PipelineExecutionRuntimeState
│   └── configuration         # PipelineExecutionRuntimeState
└── uninstall                 # UninstallRuntimeState
```

## Unified Status Snapshot

Both interfaces consume the same observed workspace status while owning their own presentation:

```text
WorkspaceContext + AWS context
              │
              ▼
       WorkspaceObserver (status/observer.py)
              │
              ▼
       RootStatusResult (status/summary.py)
       ├── workspace assessment and AWS identity
       ├── installer stack and pipeline
       ├── configuration repository and pipeline
       └── overall health
              │
              ├── CLI renderer (interfaces/cli/status.py)
              └── Web response (interfaces/web/status.py)
```
