# Refactoring Learning Steps

## How to Use This Checklist

This checklist is ordered from smaller, faster achievements to changes requiring more design
judgment. Complete one checkbox at a time. Do not treat a phase as one large patch.

For each task:

- Inspect the relevant file and its callers before editing.
- Predict what imports and tests will change.
- Keep behavior unchanged unless the task is explicitly marked as a fix.
- Run Ruff and focused tests.
- Read the complete diff.
- Commit the completed task separately.

When asking an LLM for help, first ask for an explanation or a list of affected references. Ask
for a patch only after choosing the intended boundary yourself.

## Phase 0: Establish a Safe Baseline

DONE

Achievement: you have a verified starting point and can describe the current architecture before
changing it.

## Phase 1: Small Cleanup and Confidence Builders

DONE

Achievement: you have completed several small, testable improvements and practiced making narrow
diffs.

## Phase 2: Separate Workspace Models

DONE

## Phase 3: Separate Workspace Persistence

DONE

Achievement: models no longer know how or where they are stored.

## Phase 4: Separate Workspace Paths and Readiness

DONE

Achievement: workspace discovery, persistence, and readiness have separate responsibilities, and
the workspace domain no longer depends on Typer.

## Phase 5: Consolidate Installer Version Rules

DONE

Achievement: version behavior is documented by tests and has one source of truth.

## Phase 6: Consolidate Installer Configuration Validation

DONE

Achievement: plan, deploy, and readiness cannot silently disagree about installer completeness.

## Phase 7: Correct AWS Authentication Ownership

This phase changes behavior and security assumptions. Keep its fixes separate from structural
moves and review operational impact carefully.

DONE

Achievement: authentication is external, consistent, and safe across every command.

## Phase 8: Establish Installer Feature Modules

DONE

Achievement: installer plan and deploy share public domain logic instead of command internals.

## Phase 9: Decompose Installer Deployment

This is intentionally late because it requires understanding all preceding boundaries.

DONE

Achievement: deployment reads as a short workflow, and each risky stage can be tested separately.

## Phase 10: Simplify Configuration Upload and Download

DONE

Achievement: upload and download share only real domain rules while retaining clear individual
workflows.

## Phase 11: Separate Status Data from Rendering

DONE

Achievement: status calculations can be tested without capturing terminal output.

## Phase 12: Clarify Files and Resource Names

DOME

Achievement: directory and file names reveal whether content is code, a packaged template, an
example, or runtime workspace data.

## Phase 13: Remove Compatibility Layers and Review the Result

DONE

Achievement: temporary migration scaffolding is gone and the final structure matches the intended
dependency direction.

DONE

## Definition of Done for Each Checkbox

A task is complete only when:

- Its scope can be explained in one or two sentences.
- The diff contains no unrelated change.
- Relevant tests pass.
- Ruff passes.
- Imports and public names are understandable.
- Any behavior change is documented and tested.
- You can explain every changed line before committing it.
