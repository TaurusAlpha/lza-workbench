## Counterfactual Architecture

The LZA Workbench is structured around feature-owned application layers, domain models, provider abstractions, and thin infrastructure adapters rather than a monolithic global workflow layer:

```text
src/lza_workbench/
├── constants.py                     # Global constants, default timeouts, and formatting symbols
├── errors.py                        # Base exception hierarchy (LzaError, LzaConfigurationError, etc.)
│
├── workspace/                       # Workspace lifecycle, configuration, and state
│   ├── model.py                     # Canonical workspace models (WorkspaceDocument, WorkspaceRuntime)
│   ├── schema.py                    # Pydantic schemas for lza-workspace.yaml and .lza/state.json
│   ├── persistence.py               # Low-level YAML/JSON loaders, dumpers, and atomic write operations
│   ├── assessment.py                # WorkspaceCapability and WorkspaceAssessment readiness evaluations
│   ├── context.py                   # WorkspaceContext resolution and environment management
│   ├── config.py                    # Workspace YAML declarative config helpers and loaders
│   ├── state.py                     # Workspace JSON runtime execution state helpers
│   ├── paths.py                     # Filesystem path resolvers for workspace directories and artifacts
│   ├── setup.py                     # Filesystem scaffolding, gitignore generation, and workspace bootstrap
│   └── application/
│       ├── initialize.py            # Workflow for initializing a new customer workspace
│       ├── import_workspace.py      # Workflow for adopting and importing existing LZA deployments
│       └── bootstrap.py             # Workflow for validating and provisioning AWS prerequisite resources
│
├── installer/                       # LZA Installer CloudFormation stack management
│   ├── model.py                     # Canonical installer domain models (InstallerDocument, LzaInstaller)
│   ├── schema.py                    # Pydantic schemas for installer options, templates, and parameters
│   ├── parameters.py                # CloudFormation parameter codec, validation, and overrides
│   ├── templates.py                 # Installer CloudFormation template retrieval, caching, and hashing
│   ├── deployment.py                # CloudFormation stack creation, updates, changesets, and polling
│   ├── planning.py                  # Stack change calculations and parameter planning
│   ├── deployed_version.py          # Live CloudFormation stack inspection and version detection
│   ├── state.py                     # Operational state transitions for installer deployments
│   ├── status.py                    # Installer component status evaluation and observation builders
│   ├── sync.py                      # Source repository synchronization and branch validation
│   ├── versions.py                  # Packaged LZA installer version constants and version checks
│   ├── sources/                     # Installer source provider abstractions
│   │   ├── protocol.py              # InstallerSourceProvider protocol definition
│   │   ├── github.py                # GitHub source provider (secret inspection and repo accessibility)
│   │   ├── codecommit.py            # AWS CodeCommit source provider (repo existence and branch checks)
│   │   ├── s3.py                    # AWS S3 source provider (bucket/key object inspection)
│   │   └── codeconnection.py        # AWS CodeConnections provider (connection ARN status checks)
│   └── application/
│       ├── initialize.py            # Workflow to initialize installer settings
│       ├── plan.py                  # Workflow to calculate changes and validate installer stack parameters
│       ├── deploy.py                # Workflow to deploy or update the CloudFormation installer stack
│       ├── import_deployed.py       # Workflow to adopt an already deployed installer stack
│       └── status.py                # Workflow to inspect and report live installer stack status
│
├── configuration/                   # LZA configuration repository and packaging management
│   ├── model.py                     # Canonical configuration domain models and schemas
│   ├── schema.py                    # Pydantic schemas for repositories, templates, and packaging exclusions
│   ├── archive.py                   # Zip packaging, checksum hashing, and file diffing
│   ├── git.py                       # Git CLI subprocess operations (branch, commit, diff, push, pull)
│   ├── state.py                     # Operational state transitions for configuration archive transfers
│   ├── status.py                    # Configuration component status evaluation and observation builders
│   ├── sync.py                      # Synchronization coordinator between local files and remote targets
│   ├── templates.py                 # Starter configuration template extractors and loaders
│   ├── remotes/                     # Configuration remote provider abstractions
│   │   ├── protocol.py              # ConfigurationRemote protocol definition
│   │   ├── s3.py                    # S3 configuration remote provider (direct archive push/pull/inspect)
│   │   └── git_remote.py            # Git configuration remote provider (CodeCommit/Git push/pull/inspect)
│   └── application/
│       ├── initialize.py            # Workflow to initialize customer configuration repository and templates
│       ├── push.py                  # Workflow to push local configuration to remote destination
│       ├── pull.py                  # Workflow to pull remote configuration into local workspace
│       ├── deploy.py                # Workflow to push configuration and immediately start the pipeline
│       ├── status.py                # Workflow to inspect configuration status against remote
│       └── diff.py                  # Workflow to compute differences between local config and remote package
│
├── pipeline/                        # CodePipeline execution tracking and diagnostics
│   ├── model.py                     # Domain pipeline models (PipelineExecutionSnapshot, stage/action states)
│   ├── models.py                    # Legacy pipeline state models and status representations
│   ├── diagnostics.py               # Pipeline failure diagnosis and root-cause classification
│   ├── failures.py                  # Pattern recognizers for known CodePipeline and CodeBuild errors
│   ├── watcher.py                   # Reusable lifecycle watcher and update generator for pipeline runs
│   ├── observation.py               # CodePipeline polling, stage details, and snapshot aggregators
│   ├── resolution.py                # Pipeline name resolution for installer and configuration workflows
│   ├── starter.py                   # Pipeline execution triggering and execution ID tracking
│   ├── state.py                     # Operational state transitions for recorded pipeline runs
│   └── application/
│       ├── start.py                 # Workflow to trigger a pipeline execution
│       └── status.py                # Workflow to fetch execution snapshots and stage breakdown
│
├── status/                          # Unified status aggregation and health reporting
│   ├── model.py                     # Aggregated WorkspaceSnapshot and component health models
│   └── observer.py                  # Observer workflows (get_root_status_workflow, status_root_workflow)
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
WorkspaceDocument (lza-workspace.yaml)
├── customer
├── aws_target
├── lza
├── installer        # canonical desired installer state
└── configuration    # canonical desired configuration state

WorkspaceRuntime (.lza/state.json)
├── import_record
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
       WorkspaceObserver (observer.py)
              │
              ▼
       WorkspaceSnapshot (status/model.py)
       ├── installer
       ├── configuration remote/local
       ├── pipelines
       ├── recorded fallback
       └── health
          ├── CLI renderers (interfaces/cli/status.py)
          └── Web response models (interfaces/web/status.py)
```
