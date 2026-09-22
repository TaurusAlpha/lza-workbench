# LZA Workbench

## Purpose

LZA Workbench is a local, workspace-based application for AWS Landing Zone Accelerator engineers.

It assists with creating and managing customer-specific LZA workspaces and automates common LZA configuration, deployment, validation, and troubleshooting workflows.

The current implementation provides both a CLI and a local Web GUI. The Web GUI is becoming the
primary interactive interface, while the CLI remains supported for automation, debugging, SSH,
and advanced use.

The project is initially a personal engineering productivity tool, but its structure should remain suitable for wider use.

## Scope

LZA Workbench is strictly focused on AWS Landing Zone Accelerator workflows.

In scope:

- Customer workspace initialization and import.
- LZA installer lifecycle operations.
- Customer `aws-accelerator-config` management.
- Configuration synchronization.
- LZA pipeline execution and monitoring.
- Workspace and deployment status.
- LZA-specific validation and diagnostics.
- Support for multiple LZA versions and supported repository/source types.
- Future LZA-specific configuration generation and AI-assisted workflows.

Out of scope:

- Generic AWS infrastructure management.
- Generic DevOps automation.
- Autonomous AI modification of customer AWS environments.

## Workspace Model

The application is workspace-based.

Each customer has an independent local workspace outside this repository.

Example:

```text
customers/
  example/
    lza-workspace.yaml
    aws-accelerator-config/
    aws-accelerator-installer/
    .lza/
      logs/
      state.json
```

### Declarative Configuration

`lza-workspace.yaml` is the declarative source of truth for the workspace.

It contains configuration and user decisions required to reproduce or operate the workspace.

### Runtime State

`.lza/state.json` stores operational information discovered or produced during command execution.
Its installer, configuration, and pipeline sections are feature-owned runtime models; `workspace`
validates and persists the enclosing document. Persisted documents must match the current schema.

Runtime state must not duplicate declarative configuration already stored in `lza-workspace.yaml` unless specifically required for operational efficiency and state reconciliation.

During active development, backward compatibility across workspace schema changes is not
guaranteed and automatic schema migration is not supported. Re-import the workspace when metadata
must be regenerated for the current schema.

## Core Architecture

### AWS Client Management

AWS SDK initialization is centralized.
AWS authentication is external to LZA Workbench. Workspaces must not persist AWS credentials or secrets; profiles, assumed roles, environment credentials, and workload identity are supplied by the execution environment.

- `AwsClientFactory` is the single mechanism for creating boto3 sessions and service clients.
- Each AWS-backed action resolves and reuses one request-scoped AWS execution context.
- Interface handlers pass user intent into feature-owned actions rather than constructing AWS clients.
- AWS service modules receive clients rather than creating their own sessions.
- Authentication resolution, retry configuration, and shared AWS client behavior belong in the centralized factory.

### Application Boundaries

- Web and CLI handlers should coordinate feature-owned actions rather than contain substantial business logic.
- Business logic should live in appropriate Python modules outside the CLI layer.
- AWS-specific behavior should remain separated from workspace/configuration logic where practical.
- Customer-owned LZA configuration is independent from installer source-code management.

### Package Responsibilities

The application follows feature-owned actions with explicit interface and infrastructure
boundaries:

- `interfaces.cli` owns command registration, parameters, prompting, confirmation, terminal
  rendering, and translation of application errors into process results.
- `interfaces.web` owns HTTP routing, request/response translation, browser-facing presentation,
  and session concerns. It must not own LZA business policy.
- `workspace` is the workspace document and lifecycle boundary. It owns workspace schema
  composition, paths, readiness assessment, and persistence of `lza-workspace.yaml` and
  `.lza/state.json`. Other features load a validated `WorkspaceContext` and explicitly read or
  write those documents through its persistence API. Workspace owns local workspace lifecycle and
  persistence. AWS resources belong to the feature whose explicit deployment action requires and
  manages them.
- `configuration`, `installer`, and `pipeline` own their respective schemas, business rules,
  actions, and runtime-state transition rules. They must not delegate their policy to
  `workspace`; `workspace` persists the resulting validated state document.
- `status` owns unified operational observation and typed summaries shared by both interfaces.
- `infrastructure.aws` and `infrastructure.github` contain thin external-service adapters that
  accept resolved inputs, call external APIs, and return structured observations without deriving
  feature policy.
- `resources` contains packaged data only; customer-owned workspaces and configuration remain
  outside the package.

Dependencies point from interfaces to feature packages, from feature packages to infrastructure,
and from every feature to the workspace document boundary when it needs workspace data. Feature
packages may collaborate directly where an action genuinely spans features, but interfaces must
not duplicate that orchestration. Infrastructure adapters must not import workspace or feature
policy. Shared behavior belongs to the feature that owns the rule rather than generic `core`,
`utils`, or `helpers` modules.

The package-level direction is `interfaces -> status/features -> infrastructure`, with
`workspace`, `configuration`, `installer`, and `pipeline` forming the collaborating feature layer.
CLI, Web, worker, and MCP interfaces should reuse the same feature-owned actions rather than
duplicating business logic.

### Error Handling

Application errors must remain independent of presentation and execution interfaces.

- Business logic should raise application-specific exceptions rather than Typer, Rich, HTTP, or other interface-specific errors.
- CLI handlers translate application errors into user-facing output and exit codes.
- Web handlers translate the same errors into HTTP responses and browser-facing messages.
- Headless-service interfaces may translate the same errors into structured results, logs, or worker status.
- Typer/Click usage exceptions should be reserved for invalid command-line arguments or invocation syntax.
- Unexpected programming errors should remain distinguishable from expected application failures.
- Expected user-facing errors should identify the failed operation and provide actionable
  remediation when it is known.

### Workspace Readiness

Commands operate against explicit workspace readiness rather than independently repairing missing workspace configuration.

`lza init` and `lza import` establish or complete the workspace.

Other commands should validate the minimum workspace state they require and fail clearly when it is incomplete.

AWS authentication validity and deployed-resource health are separate from workspace readiness.

## Interface Design Principles

The Web GUI is the primary planned interactive interface. The CLI remains a supported interface
for automation, debugging, SSH, and advanced use. Both should expose meaningful LZA actions rather
than low-level AWS resource operations directly.

General principles:

- Prefer interface actions that represent meaningful LZA operations.
- Keep Web routes and CLI command handlers thin; neither interface should duplicate orchestration.
- Keep planning/read-only behavior separate from mutation where practical.
- AWS-mutating operations must have clear command intent.
- Destructive operations must require an explicit confirmation or override and should provide a
  non-mutating preview when practical.
- Prefer reconciliation semantics when initial deployment and later updates represent the same operation.
- Avoid duplicate commands that provide overlapping workflow semantics.
- Keep explicit control available for operations such as synchronization, execution, and monitoring.

The current command set, detailed command behavior, unresolved command-design decisions, and implementation status are maintained in `TODO.md`.

## Development Model

The project evolves rapidly.

Documentation therefore has intentionally separate responsibilities:

- `PROJECT.md` defines durable project identity and architectural invariants.
- `TODO.md` maintains the command inventory, planned feature work, improvements, and unresolved
  decisions. Completed items may remain checked until they are manually verified and removed.
- `ROADMAP.md` records possible product directions that require discussion before becoming
  implementation work in `TODO.md`.
- `AGENTS.md` defines the current implementation and coding baseline for AI-assisted development.
- `README.md` documents current user-facing and development usage.
- `docs/REVIEW.md` is an optional review-specific instruction set used when explicitly requested.

Detailed feature specifications should not be duplicated in `PROJECT.md`.

### Testing and Verification Philosophy

- Real execution through the affected interface and declarative workspace outcomes are the primary sources of truth for behavior.
- Automated tests are supporting regression tools, not feature design drivers.
- Production code must never be compromised or complicated (e.g. via mock hooks, test callbacks, or artificial indirection) solely to satisfy tests.
- Static architectural tests (`tests/test_package.py`) enforce layer boundaries and import rules without mocking.
- Heavy unit testing of external integrations (AWS, Git subprocesses) is discouraged in favor of focused contract checks and manual/smoke execution through the affected interface.

## Architectural Change Rule

Update this document only when a change affects a durable project-wide assumption or architectural boundary.

Examples include:

- changing ownership of AWS authentication;
- changing the workspace/source-of-truth model;
- changing AWS client construction;
- changing major application-layer responsibilities;
- changing fundamental interface design principles.

Feature behavior, individual commands, implementation details, repository refactors, and temporary design decisions belong elsewhere.

## Technical Direction

The current implementation uses:

- Python
- Typer
- Pydantic
- boto3
- FastAPI
- ruamel.yaml
- Rich
- pytest
- Uvicorn
- uv

These are implementation choices rather than permanent architectural requirements unless explicitly promoted to an architectural constraint.

## Future Direction

Natural areas of future development include:

- LZA configuration validation;
- version-aware schemas;
- pipeline monitoring and diagnostics;
- config diff/reporting;
- configuration generators;
- security and policy pack integration;
- optional LZA-focused MCP/AI assistance;
- authenticated server-side and multi-user operation.

Product directions belong in `ROADMAP.md`; concrete implementation work belongs in `TODO.md`.

AI should assist with analysis, generation, validation, and troubleshooting. It should not become the primary autonomous execution mechanism for customer environments.
