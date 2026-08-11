# LZA Workbench

## Purpose

LZA Workbench is a local, workspace-based CLI toolkit for AWS Landing Zone Accelerator engineers.

It assists with creating and managing customer-specific LZA workspaces and automates common LZA bootstrap, configuration, deployment, validation, and troubleshooting workflows.

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

Runtime state must not duplicate declarative configuration already stored in `lza-workspace.yaml` unless specifically required for operational efficiency and state reconciliation.

## Core Architecture

### AWS Client Management

AWS SDK initialization is centralized.

- `AwsClientFactory` is the single mechanism for creating boto3 sessions and service clients.
- Commands create and reuse a factory for their execution context.
- AWS service modules receive clients rather than creating their own sessions.
- Authentication resolution, retry configuration, and shared AWS client behavior belong in the centralized factory.

### Application Boundaries

- CLI command handlers should coordinate workflows rather than contain substantial business logic.
- Business logic should live in appropriate Python modules outside the CLI layer.
- AWS-specific behavior should remain separated from workspace/configuration logic where practical.
- Customer-owned LZA configuration is independent from installer source-code management.

### Workspace Readiness

Commands operate against explicit workspace readiness rather than independently repairing missing workspace configuration.

`lza init` and `lza import` establish or complete the workspace.

Other commands should validate the minimum workspace state they require and fail clearly when it is incomplete.

AWS authentication validity and deployed-resource health are separate from workspace readiness.

## CLI Design Principles

The CLI should follow LZA workflow domains rather than expose low-level AWS resource operations directly.

General principles:

- Prefer commands that represent meaningful LZA workflows.
- Keep planning/read-only behavior separate from mutation where practical.
- AWS-mutating operations must have clear command intent.
- Prefer reconciliation semantics when initial deployment and later updates represent the same operation.
- Avoid duplicate commands that provide overlapping workflow semantics.
- Keep explicit control available for operations such as synchronization, execution, and monitoring.

The current command set, detailed command behavior, unresolved command-design decisions, and implementation status are maintained in `TODO.md`.

## Development Model

The project evolves rapidly.

Documentation therefore has intentionally separate responsibilities:

- `PROJECT.md` defines durable project identity and architectural invariants.
- `TODO.md` contains active feature design, backlog, technical debt, refactoring tasks, and unresolved decisions.
- `AGENTS.md` defines the current implementation and coding baseline for AI-assisted development.
- `README.md` documents current user-facing and development usage.

Detailed feature specifications should not be duplicated in `PROJECT.md`.

## Architectural Change Rule

Update this document only when a change affects a durable project-wide assumption or architectural boundary.

Examples include:

- changing ownership of AWS authentication;
- changing the workspace/source-of-truth model;
- changing AWS client construction;
- changing major application-layer responsibilities;
- changing fundamental CLI design principles.

Feature behavior, individual commands, implementation details, repository refactors, and temporary design decisions belong elsewhere.

## Technical Direction

The current implementation uses:

- Python
- Typer
- Pydantic
- boto3
- ruamel.yaml
- Rich
- pytest
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
- optional LZA-focused MCP/AI assistance.
- Server-side or multi-user operation.

Detailed planning and prioritization belong in `TODO.md`.

AI should assist with analysis, generation, validation, and troubleshooting. It should not become the primary autonomous execution mechanism for customer environments.
