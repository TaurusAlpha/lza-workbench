# AI Agent Instructions

## Context

- Read only the files required for the current task.
- Read `PROJECT.md` only for architecture or design decisions.
- Read `TODO.md` only if the task references it or requires feature planning.
- Ask before performing repository-wide investigation or reading many unrelated files.

## Rules

- Implement only the requested task.
- Do not change unrelated code or expand scope unless requested.
- Prefer modifying existing code over creating new modules.
- Keep solutions simple and modular.
- Do not create placeholder or speculative code.
- Prefer Python over shell when practical.
- Keep AWS authentication external.
- Customer projects are created outside this repository.

## Validation

Before finishing ask if you should validate the implementation:

- Run Ruff.
- Run pytest.
- Ensure new changes do not break the project.

## Responses

- Keep responses concise.
- Minimize token usage.
- Do not provide long explanations unless requested.
- Suggest follow-up work only when directly relevant.
