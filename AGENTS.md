# AI Agent Instructions

## Context

- Read only the files needed for the task.
- Read `PROJECT.md` for architecture, repository conventions, or feature design.
- Read `TODO.md` for planned, unresolved, or requested feature work.
- Inspect broader repository context when required to understand ownership, dependencies, or existing patterns; avoid unrelated scanning.

## Rules

- Implement only the requested task.
- Do not expand scope, refactor unrelated code, or add speculative functionality.
- Prefer Python over shell when practical.
- Customer projects live outside this repository.
- Do not introduce dependencies unless clearly required.
- Prefer existing project patterns, but do not preserve a poor structure merely for consistency.

## Validation

Before finishing:

- Run `uv run ruff check . --fix`.
- Run `uv run pytest tests/test_package.py` to validate architectural boundaries.
- Validate changed user-facing behavior through the real interface when practical:
  - CLI changes through the CLI against a temporary workspace.
  - Web changes through the running local application.
- Verify actual output/status and relevant file effects rather than relying only on mocks.
- Do not run the full pytest suite unless explicitly requested or clearly necessary.

## Testing Policy

Tests support runtime behavior; they do not define it.

- Do not add tests automatically unless explicitly requested.
- Do not change production APIs, add branches, callbacks, hooks, or indirection solely for tests.
- Requirements and real runtime behavior are the source of truth.
- Update or remove tests that assert intentionally obsolete behavior.
- Prefer tests for deterministic domain logic, schemas, regressions, and architectural boundaries.
- Avoid extensive mocking of AWS APIs, boto3, Git subprocesses, or other external systems.

## Responses

- Keep responses very short, straight to the point,concise and focused.
- State material assumptions only if relevant.
- Suggest follow-up work only when directly relevant.

## Code Quality

Optimize for code that is easy for a human to read, change, and debug.

- Prefer simple, explicit, DRY code with clear ownership.
- Keep functions and modules focused on a coherent responsibility.
- Modify an existing module when the logic belongs there; create a focused module when it improves cohesion, reuse, or readability.
- Do not optimize for minimum file count or minimum line count.
- Avoid duplicated logic, large mixed-responsibility modules, deep nesting, clever expressions, and unnecessary indirection.
- Introduce abstractions only when they remove meaningful duplication or establish a clear architectural boundary.
- Use descriptive names and straightforward control flow.

### Architecture

- Keep HTTP routing and browser-facing presentation in the Web layer.
- Keep Typer, Rich, prompting, confirmation, and terminal rendering in the CLI layer.
- Implement reusable application use cases as workflows returning structured results.
- Keep workspace, installer, configuration, and pipeline rules in their owning feature packages.
- Keep AWS modules as thin boto3 adapters; pass resolved inputs into them instead of importing workspace or feature policy.
- Do not create generic `core`, `utils`, or `helpers` modules when a clear owner exists.
- Preserve dependency direction:

  `web/cli -> workflows -> features/AWS`

- Lower layers must not import interface or workflow modules.

## Release & Project Metadata

Keep project metadata consistent with the implementation.

- Review `pyproject.toml` only when the change affects versioning, dependencies, entry points, scripts, packaging, or other project metadata.
- Update the project version when the implementation represents a release according to the project's versioning scheme.
- Remove obsolete dependency or packaging metadata when encountered as part of the requested change.

## Repository Specifics

- **Toolchain:** `uv`.
- **CLI entrypoints:** `lza` and `lza-workbench`.
- **Workspace model:** each customer has an independent workspace outside this repository.
- **Source of truth:** `lza-workspace.yaml` is declarative configuration; `.lza/state.json` stores runtime/execution metadata.
- **AWS clients:** all boto3 sessions and clients are created through `AwsClientFactory`.
- **Readiness:** commands declare required `WorkspaceCapability` values and are gated through `load_workspace_context()` / `require_capabilities()` against `WorkspaceAssessment`.

## Documentation

Documentation files have distinct responsibilities.

### `PROJECT.md`

Durable project-wide architecture, invariants, and design decisions only.

Do not add detailed feature specifications or implementation status.

### `TODO.md`

Active, planned, unresolved, refactoring, and technical-debt work.

Update when work is added, removed, redesigned, or remains unresolved.

### `docs/DONE.md`

Concise history of completed features and meaningful refactors.

Move work here only after implementation, integration, review, and required validation are complete. Summarize outcomes rather than copying implementation checklists.

### `README.md`

Update when current user-facing behavior, usage, installation, or development instructions change.
