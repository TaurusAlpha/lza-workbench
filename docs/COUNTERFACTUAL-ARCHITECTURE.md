## Counterfactual Architecture

The LZA Workbench is structured around feature-owned domain packages with explicit separation between **Supported Actions** (primary public orchestrations) and **Dedicated Support Modules** (single-purpose domain helpers, diagnostics, models, and low-level adapters):

```text
src/lza_workbench/
├── constants.py                     # Global constants, default timeouts, and formatting symbols
├── errors.py                        # Base exception hierarchy (LzaError, LzaConfigurationError, etc.)
│
├── workspace/                       # Workspace lifecycle, configuration, and state
│   ├── # Actions (CLI / Web operations)
│   ├── initialize.py                # Action: initialize new customer workspace ('lza init')
│   ├── import_workspace.py          # Action: adopt and import existing LZA deployment ('lza import')
│   ├── bootstrap.py                 # Action: validate/provision AWS prerequisite resources ('lza bootstrap')
│   │
│   ├── # Support Subdirectories
│   ├── layout/                      # Filesystem layout, directory scaffolding, and managed paths
│   │   └── scaffolding.py
│   ├── validation/                  # Capability assessment, readiness rules, and structure validation
│   │   ├── capabilities.py
│   │   └── readiness.py
│   │
│   ├── # Package Support Modules
│   ├── context.py                   # Request-scoped WorkspaceContext loader and environment manager
│   ├── persistence.py               # YAML/JSON loaders, dumpers, and atomic file operations
│   ├── paths.py                     # Path resolvers and directory normalization
│   └── schema.py                    # Pydantic schemas for WorkspaceConfig and WorkspaceState
│
├── installer/                       # LZA Installer CloudFormation stack management
│   ├── # Actions (CLI / Web operations)
│   ├── initialize.py                # Action: collect/configure installer settings ('lza installer init')
│   ├── plan.py                      # Action: calculate stack changes and parameter plan ('lza installer plan')
│   ├── deploy.py                    # Action: deploy CloudFormation installer stack ('lza installer deploy')
│   ├── import_deployed.py           # Action: discover and adopt deployed stack ('lza installer import')
│   ├── status.py                    # Action: query live/recorded installer status ('lza installer status')
│   │
│   ├── # Support Subdirectories
│   ├── validation/                  # Configuration completeness, preflight checks, and CFN plan safety
│   │   ├── config.py
│   │   └── preflight.py
│   ├── drift/                       # Configuration drift and state alignment calculations
│   │   └── alignment.py
│   ├── templates/                   # CloudFormation template retrieval, caching, schemas, and hashing
│   │   ├── retrieval.py
│   │   └── digest.py
│   ├── source/                      # Source prerequisite validation and planning (CodeCommit, S3, GitHub)
│   │   ├── inspection.py
│   │   └── planning.py
│   ├── parameters/                  # CloudFormation parameter codecs, resolution, and overrides
│   │   └── codec.py
│   ├── versions/                    # LZA version constants, normalization, and deployed version detection
│   │   ├── constants.py
│   │   └── detection.py
│   │
│   ├── # Package Support Modules
│   ├── state.py                     # Operational state transitions for installer deployments
│   ├── schema.py                    # Pydantic schemas for installer configuration and options
│   └── sync.py                      # Source repository synchronization rules
│
├── configuration/                   # LZA customer configuration repository & packaging
│   ├── # Actions (CLI / Web operations)
│   ├── initialize.py                # Action: initialize local config with template ('lza config init')
│   ├── pull.py                      # Action: pull remote configuration into workspace ('lza config pull')
│   ├── push.py                      # Action: push local configuration to remote destination ('lza config push')
│   ├── deploy.py                    # Action: push configuration and trigger pipeline ('lza config deploy')
│   ├── diff.py                      # Action: compute differences against remote package ('lza config diff')
│   ├── status.py                    # Action: query configuration and remote sync status ('lza config status')
│   │
│   ├── # Support Subdirectories
│   ├── warnings/                    # Actionable warning compilers for workspace, git, repo, and pipeline
│   │   └── compiler.py
│   ├── inspection/                  # Remote repository (S3, CodeCommit, CodeConnection) and pipeline inspection
│   │   ├── models.py
│   │   ├── pipeline.py
│   │   └── repository.py
│   ├── validation/                  # Local configuration directory structure and YAML syntax validation
│   │   └── structure.py
│   ├── archive/                     # Zip packaging, checksum hashing, and archive diffing
│   │   └── packaging.py
│   ├── git/                         # Local Git subprocess operations (commit, push, pull, branch status)
│   │   └── operations.py
│   ├── templates/                   # Starter configuration template extractors and loaders
│   │   ├── discovery.py
│   │   └── rendering.py
│   │
│   ├── # Package Support Modules
│   ├── sync.py                      # Remote sync evaluation and digest comparisons
│   ├── repository.py                # Repository destination and naming helpers
│   ├── state.py                     # Operational state transitions for configuration archive transfers
│   └── schema.py                    # Pydantic schemas for repositories, packaging, and exclude rules
│
├── pipeline/                        # CodePipeline execution tracking and diagnostics
│   ├── # Actions (CLI / Web operations)
│   ├── start.py                     # Action: trigger CodePipeline execution ('lza pipeline start')
│   ├── watcher.py                   # Action: stream pipeline execution lifecycle events ('lza pipeline watch')
│   ├── status.py                    # Action: fetch execution snapshot and diagnostics ('lza pipeline status')
│   │
│   ├── # Support Subdirectories
│   ├── failures/                    # CodeBuild log analyzers, failure classification, and diagnostics
│   │   └── diagnostics.py
│   ├── observation/                 # CodePipeline polling and stage state extraction
│   │   └── polling.py
│   │
│   ├── # Package Support Modules
│   ├── resolution.py                # Pipeline name resolution from workspace configuration
│   ├── state.py                     # Operational state transitions for recorded pipeline runs
│   └── model.py                     # Domain dataclasses (PipelineExecutionSnapshot, stage/action states)
│
├── status/                          # Unified status aggregation and health reporting
│   ├── observer.py                  # Root observer workflow ('lza status' / GET /api/status)
│   └── summary.py                   # Typed summary models (HealthSummary, InstallerSummary, ConfigSummary)

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
       RootStatusResult (status/summary.py)
       ├── installer
       ├── configuration remote/local
       ├── pipelines
       ├── recorded fallback
       └── health
          ├── CLI renderers (interfaces/cli/status.py)
          └── Web response models (interfaces/web/status.py)
```
