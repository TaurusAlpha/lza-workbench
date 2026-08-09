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

Before finishing, ask whether validation should be performed.
Only If requested, run:

- Ruff
- pytest
- Verify new changes do not introduce regressions.

## Responses

- Keep responses concise.
- Minimize token usage.
- Do not provide long explanations unless requested.
- Suggest follow-up work only when directly relevant.
- State assumptions instead of silently making them.

## Code Quality & Readability

Before presenting code, review it against these principles.

### Release & Project Metadata

Every implementation must leave the project in a releasable state.

- Review `pyproject.toml` after every implementation.
- Update the project version according to the project's versioning scheme.
  - Feature → minor version bump.
  - Bug fix or improvement → patch version bump.
  - Breaking change → major version bump.
- Update dependencies, dependency constraints, optional dependencies, entry points, scripts, or other project metadata whenever required by the implementation.
- Remove obsolete dependencies and metadata introduced by previous implementations.
- Do not leave `pyproject.toml` inconsistent with the current codebase.

### Simplicity

- Prefer the simplest solution that satisfies the requirements.
- Prioritize readability over brevity.
- Avoid unnecessary abstractions or indirection.

### Maintainability

- Write small, focused functions with a single responsibility.
- Place new logic in the appropriate package (`core/`, `aws/`, `config/`, `utils/`) rather than in command handlers.
- Extend existing modules when appropriate; create new modules when they improve organization.
- Follow existing project structure and coding patterns.

### Readability

- Use descriptive names for variables, functions, and classes.
- Avoid deeply nested control flow.
- Keep comprehensions and generator expressions simple and readable.
- Avoid nested or difficult-to-read expressions within function calls.
