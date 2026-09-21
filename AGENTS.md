# AI Agent Instructions

## Context

- Read only the files needed for the task.
- Read `PROJECT.md` when architecture or repository conventions are relevant.
- Read `TODO.md` only when the task depends on planned or unresolved work recorded there.
- Inspect broader repository context only when needed to understand ownership, dependencies, or existing patterns.

## Rules

- Implement only the requested task.
- Do not expand scope, refactor unrelated code, or add speculative functionality.
- Prefer Python over shell when practical.
- Customer projects live outside this repository.
- Do not introduce dependencies unless clearly required.
- Prefer existing project patterns, but do not preserve poor structure merely for consistency.

## Validation

- Do not run lint, complexity, architecture, or test tools unless explicitly requested.
- Treat findings from `ruff`, import-linter, complexipy, pytest, or other validation tools as diagnostic input.
- Fix findings only when they identify a real correctness, architecture, readability, or maintainability problem.
- Do not restructure coherent code solely to satisfy complexity metrics or static-analysis scores.

## Testing Policy

Tests support runtime behavior; they do not define it.

- Do not add tests automatically unless explicitly requested.
- Do not change production APIs, add branches, callbacks, hooks, or indirection solely for tests.
- Requirements and real runtime behavior are the source of truth.
- Update or remove tests that assert intentionally obsolete behavior.
- Prefer tests for deterministic domain logic, schemas, regressions, and architectural boundaries.
- Avoid extensive mocking of AWS APIs, boto3, Git subprocesses, or other external systems.

## Responses

- Be terse and information-dense.
- Prefer short bullets or fragments when full prose adds no value.
- Report only decisions, material findings, changes, and blockers.
- Do not restate the task or explain obvious implementation details.
- State material assumptions.

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

- Keep interface-specific presentation in `cli` and `web`.
- Keep reusable application orchestration in `workflows`.
- Keep workspace, installer, configuration, and pipeline rules in their owning feature packages.
- Keep `aws` focused on AWS integration rather than workspace or feature policy.
- Preserve the architecture enforced by the configured import-linter contracts.
- Do not create generic `core`, `utils`, or `helpers` modules when a clear owner exists.

## Repository Specifics

- Customer workspaces live outside this repository.
- `lza-workspace.yaml` is declarative configuration; `.lza/state.json` stores runtime/execution metadata.
- All boto3 sessions and clients are created through `AwsClientFactory`.
- Workspace readiness is enforced through `WorkspaceCapability` / `WorkspaceAssessment`.

## Documentation

- Update project documentation only when the requested change materially changes documented behavior or architecture.
- In-code docstrings follow the Code Clarity Convention below and should be maintained as part of normal source changes.

## Code Clarity Convention

- Every Python module must have a concise purpose docstring describing its responsibility. Prefer one line, but allow slightly more detail when strict brevity would remove information needed to distinguish the module's role.
- For functions and classes, prefer clear names, signatures, and types over explanatory docstrings.
- Use descriptive names and straightforward control flow.
- When renaming for clarity, make the new name more specific to the symbol's actual responsibility in this project, not more generic or textbook-like. Replacing a precise project-specific name with a broader technical term is a regression, even if the new name appears cleaner.
- Add a function or class docstring only when it communicates useful information that is not obvious from the name and signature, such as a non-obvious responsibility, side effect, precondition, invariant, or domain meaning.
- Visibility does not determine whether a function or class needs a docstring; usefulness does.
- Keep purpose docstrings brief. Do not document parameters, return values, or implementation details unless they add information needed to understand correct use.
- Do not add docstrings that merely restate the symbol name.
- If a concise purpose description exposes genuinely mixed or unrelated responsibilities, treat that as a code-structure concern rather than hiding it behind a longer docstring.
- Treat module purpose docstrings as the canonical descriptions used for generated repository indexes and maps. Do not maintain duplicate purpose descriptions in nearby comments solely for indexing.