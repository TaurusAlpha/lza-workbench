## Counterfactual Architecture

The LZA Workbench is structured around feature-owned domain modules and thin infrastructure adapters without artificial subpackage nesting or shadow application layers:

```text
src/lza_workbench/
├── constants.py                     # Global constants, default timeouts, and formatting symbols
├── errors.py                        # Base exception hierarchy (LzaError, LzaConfigurationError, etc.)
│
├── workspace/                       # Workspace lifecycle, configuration, state, and workflows
│   ├── schema.py                    # Pydantic schemas for lza-workspace.yaml and .lza/state.json
│   ├── persistence.py               # Low-level YAML/JSON loaders, dumpers, and atomic write operations
│   ├── assessment.py                # WorkspaceCapability and WorkspaceAssessment readiness evaluations
│   ├── context.py                   # WorkspaceContext resolution and environment management
│   ├── paths.py                     # Filesystem path resolvers for workspace directories and artifacts
│   ├── initialize.py                # Workflow and helpers for initializing a new customer workspace
│   ├── import_workspace.py          # Workflow for adopting and importing existing LZA deployments
│   └── bootstrap.py                 # Workflow for validating and provisioning AWS prerequisite resources
│
├── installer/                       # LZA Installer CloudFormation stack management and workflows
│   ├── schema.py                    # Pydantic schemas for installer options, templates, and parameters
│   ├── parameters.py                # CloudFormation parameter codec, validation, and overrides
│   ├── templates.py                 # Installer CloudFormation template retrieval, caching, and hashing
│   ├── deploy.py                    # Preflight checks, plan validation, stack deployment, and monitoring
│   ├── plan.py                      # Stack change calculations, parameter planning, and plan workflow
│   ├── initialize.py                # Workflow to initialize and collect installer settings
│   ├── import_deployed.py           # Workflow to discover and adopt an already deployed installer stack
│   ├── deployed_version.py          # Live CloudFormation stack inspection and version detection
│   ├── state.py                     # Operational state transitions for installer deployments
│   ├── status.py                    # Calculations, warnings, and status query workflow
│   ├── sync.py                      # Source repository synchronization and branch validation
│   ├── source.py                    # Source prerequisite validation and planning (CodeCommit, S3, GitHub)
│   └── versions.py                  # Packaged LZA installer version constants and version checks
│
├── configuration/                   # LZA configuration repository, packaging, and workflows
│   ├── schema.py                    # Pydantic schemas for repositories, templates, and packaging exclusions
│   ├── archive.py                   # Zip packaging, checksum hashing, and file diffing
│   ├── git.py                       # Git CLI subprocess operations (branch, commit, diff, push, pull)
│   ├── state.py                     # Operational state transitions for configuration archive transfers
│   ├── status.py                    # Status evaluation, warning compilers, and status query workflow
│   ├── sync.py                      # Synchronization coordinator between local files and remote targets
│   ├── templates.py                 # Starter configuration template extractors and loaders
│   ├── rendering.py                 # Template rendering and variable replacement
│   ├── repository.py                # Repository destination and naming helpers
│   ├── validation.py                # Local configuration structure validation
│   ├── initialize.py                # Workflow to initialize customer configuration repository and templates
│   ├── push.py                      # Workflow to push local configuration to remote destination
│   ├── pull.py                      # Workflow to pull remote configuration into local workspace
│   ├── deploy.py                    # Workflow to push configuration and immediately start the pipeline
│   └── diff.py                      # Workflow to compute differences between local config and remote package
│
├── pipeline/                        # CodePipeline execution tracking, diagnostics, and workflows
│   ├── model.py                     # Domain pipeline models (PipelineExecutionSnapshot, stage/action states)
│   ├── failures.py                  # Pattern recognizers and diagnostics for CodePipeline and CodeBuild errors
│   ├── watcher.py                   # Reusable lifecycle watcher and update generator for pipeline runs
│   ├── observation.py               # CodePipeline polling, stage details, and snapshot aggregators
│   ├── resolution.py                # Pipeline name resolution for installer and configuration workflows
│   ├── state.py                     # Operational state transitions for recorded pipeline runs
│   ├── start.py                     # Workflow to trigger a pipeline execution
│   └── status.py                    # Workflow to fetch execution snapshots and stage diagnostics
│
├── status/                          # Unified status aggregation and health reporting
│   └── observer.py                  # Observer workflows and status models (get_root_status_workflow)
│
├── infrastructure/                  # Thin external service adapters
│   ├── aws/
│   │   ├── session.py               # AwsClientFactory, AwsExecutionContext, and session credential priming
│   │   ├── cloudformation.py        # CloudFormation client operations (stacks, events, changesets)
│   │   ├── codepipeline.py          # CodePipeline client operations (executions, stages, actions)
│   │   ├── codebuild.py             # CodeBuild client operations (build logs, execution phases)
│   │   ├── s3.py                    # S3 client operations (bucket checks, encryption, uploads/downloads)
│   │   ├── codecommit.py            # CodeCommit client operations (repository and branch queries)
│   │   ├── codeconnections.py       # CodeConnections client operations (connection status queries)
│   │   ├── secrets_manager.py       # Secrets Manager client operations (secret existence and metadata)
│   │   ├── ssm.py                   # SSM parameter client operations (parameter store lookups)
│   │   └── errors.py                # Unified AWS error classification (classify_aws_error, AwsErrorInfo)
│   └── github.py                    # GitHub API operations (repository accessibility validation)
│
├── interfaces/                      # Presentation layers (CLI and Web)
│   ├── cli/
│   │   ├── main.py                  # Typer CLI application root, version command, and command groups
│   │   ├── __main__.py              # Executable entry point (python -m lza_workbench.interfaces.cli)
│   │   ├── params.py                # Shared CLI option definitions (workspace-dir, profile, dry-run)
│   │   ├── input.py                 # Interactive terminal prompts, confirmations, and value fallbacks
│   │   ├── output.py                # Rich formatting, tables, panels, and status tag renderers
│   │   ├── workspace.py             # CLI command handlers for `workspace init`, `import`, and `bootstrap`
│   │   ├── installer.py             # CLI command handlers for `installer init`, `plan`, `deploy`, and `import`
│   │   ├── configuration.py         # CLI command handlers for `config init`, `push`, `pull`, and `deploy`
│   │   ├── pipeline.py              # CLI command handlers for `pipeline start` and `pipeline watch`
│   │   └── status.py                # CLI command handlers for `status` (root, installer, configuration)
│   └── web/
│       ├── app.py                   # FastAPI web application factory, route configuration, and CORS setup
│       ├── main.py                  # Web server runner (Uvicorn launcher for `lza ui`)
│       ├── status.py                # REST API endpoints serving workspace snapshots and component status
│       └── static/                  # HTML, CSS, and frontend JavaScript assets for the read-only UI
│
└── resources/                       # Packaged static assets
    ├── configuration_templates/     # Default starter configuration templates for landing zones
    ├── installer_templates/         # Packaged CloudFormation templates for installer stacks
    └── workspace_examples/          # Reference lza-workspace.yaml examples (minimal, full, installer-only)
```

### Core Persisted Models

The declarative configuration and runtime execution states are split into explicit documents:

```text
WorkspaceConfig (lza-workspace.yaml)
├── customer
├── aws
├── lza
├── installer        # canonical desired installer state
└── configuration    # canonical desired configuration state

WorkspaceState (.lza/state.json)
├── imported
├── installer
├── configuration
└── pipelines
    ├── installer
    └── configuration
```

### Unified Status Snapshot

Status observation is centralized through a single observer pipeline producing a typed snapshot consumed by both CLI renderers and Web API endpoints:

```text
WorkspaceContext + AWS context
              │
              ▼
       WorkspaceObserver (status/observer.py)
              │
              ▼
       RootStatusResult (status/observer.py)
       ├── installer
       ├── configuration remote/local
       ├── pipelines
       ├── recorded fallback
       └── health
          ├── CLI renderers (interfaces/cli/status.py)
          └── Web response models (interfaces/web/status.py)
```
