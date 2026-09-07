# AI Agent Instructions

## Context

- Read the minimum number of files required for the current task.
- Read `PROJECT.md` only when architectural decisions, repository conventions, or feature design are relevant.
- Read `TODO.md` only when implementing, planning, or discussing a feature described there.
- Ask before scanning large parts of the repository or reading unrelated files.

## Rules

- Implement only the requested task.
- Do not change unrelated code or expand scope unless requested.
- Prefer modifying existing code over creating new modules.
- Do not create placeholder or speculative code.
- Prefer Python over shell when practical.
- Customer projects are created outside this repository.
- Do not introduce new dependencies unless explicitly requested or clearly justified.

## Validation

Before finishing:

- Run `uv run ruff check . --fix`.
- Run `uv run pytest tests/test_package.py` to enforce static architectural import boundaries.
- Validate changed interface behavior through the real interface: exercise CLI changes against a
  temporary workspace or directory, and exercise Web changes through the real local application.
- Verify real outputs or responses, process/HTTP status, and file effects rather than relying on
  mocks or test suites.
- Do not run the full `pytest` suite unless explicitly requested.

## Testing Policy

Automated tests are secondary to real interface behavior and must not drive production-code design.

### Core Rules

- Do not create tests automatically when implementing features unless explicitly requested.
- Never alter production function signatures (e.g. injecting sleep/print callbacks or mock hooks), add production branches, or introduce indirection solely to make code testable.
- Requirements, command semantics, and real runtime behavior are the source of truth. Tests are supporting evidence only.
- When an intentional requirement or behavior change causes existing tests to fail, update or delete the obsolete tests immediately. Do not preserve obsolete behavior or write production shims to keep stale tests passing.
- Static architecture tests (`tests/test_package.py`) and pure schema/logic validations are always valid and run fast (<1s).
- When tests are explicitly requested, focus on pure domain logic, deterministic transformations, or defect reproduction. Avoid mocking external systems (`boto3`, AWS APIs, subprocess Git calls).

## Responses

- Keep responses concise.
- Minimize token usage.
- Do not provide long explanations.
- Suggest follow-up work only when directly relevant.
- State assumptions instead of silently making them.

## Code Quality & Readability

Before presenting code, review it against these principles.

### Release & Project Metadata

Every implementation must leave the project in a releasable state.

- Review `pyproject.toml` after every implementation.
- Update the project version according to the project's versioning scheme.
- Update dependencies, dependency constraints, optional dependencies, entry points, scripts, or other project metadata whenever required by the implementation.
- Remove obsolete dependencies and metadata introduced by previous implementations.
- Do not leave `pyproject.toml` inconsistent with the current codebase.
- If GIT working tree is clean always update pyproject.toml with the new project version according to the project's versioning scheme.

### Simplicity

- Prefer the simplest solution that satisfies the requirements.
- Prioritize readability over brevity.
- Avoid unnecessary abstractions or indirection.

### Maintainability

- Write small, focused functions with a single responsibility.
- Place new logic in the appropriate feature package rather than in command handlers or generic
  `core`/`utils` modules.
- Keep HTTP routing and browser-facing presentation in the Web layer; keep Typer, Rich, prompting,
  confirmation, and terminal rendering in the CLI layer.
- Implement reusable application use cases as workflows that return structured results.
- Keep workspace, installer, configuration, and pipeline rules in their owning feature packages.
- Keep AWS modules as thin boto3 adapters; pass resolved values into them instead of importing
  workspace or feature policy.
- Do not introduce generic `core`, `utils`, or `helpers` modules when a feature owner exists.
- Preserve the dependency direction `web/cli -> workflows -> features/AWS`; lower layers must not
  import interface or workflow modules.
- Extend existing modules when appropriate; create new modules when they improve organization.
- Follow existing project structure and coding patterns.

### Readability

- Use descriptive names for variables, functions, and classes.
- Avoid deeply nested control flow.
- Keep comprehensions and generator expressions simple and readable.
- Avoid nested or difficult-to-read expressions within function calls.

## Repository Specifics

- **Toolchain**: Uses `uv` for package management and execution.
- **CLI Entrypoints**: `lza` and `lza-workbench` (defined in `pyproject.toml`).
- **Workspace Model**: Each customer has an independent local workspace (e.g., `example/`).
- **Source of Truth**: `lza-workspace.yaml` is the declarative source of truth for a workspace. `.lza/state.json` stores runtime/execution metadata.
- **AWS Client Factory**: All `boto3` sessions and clients MUST be created via `AwsClientFactory`. Service modules should not create their own sessions.
- **Readiness:** Commands validate required workspace state before executing. The current representation is being migrated from an ordinal readiness level to explicit capability checks — see TODO.md for status before relying on either model.

## Documentation

Documentation files have separate responsibilities.

### PROJECT.md

Update only when a durable project-wide architectural decision or invariant changes.
Do not add detailed feature specifications or implementation status.

### TODO.md

Focuses exclusively on active, planned, unresolved, refactoring, and technical-debt work.

Update when:

- Work is planned, added, removed, or redesigned.
- A feature has unresolved design decisions.
- Technical debt or a meaningful refactor is identified.
- Work is completed and needs to be cleaned up / summarized into `docs/DONE.md`.

### docs/DONE.md

Maintain as a concise, high-level historical log of completed feature milestones and refactors.

Rules:

- Move work to `docs/DONE.md` only after implementation, integration, code review, and validation/tests are complete.
- Summarize delivered capabilities concisely; do not copy verbose micro-checklists, commit logs, or full specs.
- Retain remaining unfinished follow-up items in `TODO.md`.

### README.md

Update when current user-facing behavior, command usage, installation, or repository-development instructions change.
