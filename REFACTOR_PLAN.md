# LZA Workbench Refactor Plan

## Purpose

This is the execution plan for the LZA Workbench refactor. It divides the work into small,
reviewable steps that leave the repository in a stable state after each step.

The plan is designed so that a completed step becomes an accepted contract for later work. A
later step should use the recorded checkpoint instead of reopening the entire architecture or
re-reviewing already accepted changes from scratch.

Supporting documents:

- [`docs/refactor.md`](docs/refactor.md) describes the intended architectural direction.
- [`docs/refactor_steps.md`](docs/refactor_steps.md) contains the detailed learning checklist.
- [`docs/REVIEW.md`](docs/REVIEW.md) defines the review standard.
- [`PROJECT.md`](PROJECT.md) defines durable project-wide constraints.

This file is the authoritative document for execution order, step status, and handoff records.
The supporting documents remain useful background and detailed checklists.

## Current Snapshot

Snapshot date: 2026-08-13

- Baseline commit: `c06af2b` (`main`)
- The working tree is not clean.
- Refactoring documentation and workspace-model extraction are already in progress.
- Existing uncommitted changes must be preserved and reviewed as the starting point for Steps 0
  and 1; they must not be discarded or silently rewritten.
- The current work mixes structural model movement with model/default/validation changes. Step 0
  must classify those changes before Step 1 is accepted so structural and behavioral changes can
  be reviewed separately.

Current uncommitted areas at the time of this snapshot:

- `TODO.md`
- `docs/refactor.md`
- `docs/refactor_steps.md`
- `src/lza_workbench/workspace/`
- `src/lza_workbench/core/workspace.py`
- `src/lza_workbench/commands/workspace_import.py`
- `src/lza_workbench/commands/__init__.py`
- Packaged configuration/template files

Update this snapshot or the step ledger after the current work is committed. Do not use the
snapshot as a permanent list of changed files.

## Refactoring Invariants

Every step must preserve these rules unless that step explicitly changes one and documents the
decision:

1. Existing CLI command names, options, exit behavior, and dry-run guarantees remain stable.
2. `lza-workspace.yaml` remains the declarative source of truth.
3. `.lza/state.json` contains runtime metadata and does not duplicate declarative configuration
   without an explicit reason.
4. Customer workspaces and customer-owned configuration remain outside this repository.
5. AWS authentication remains external to the application; secrets are not persisted in
   workspace configuration.
6. All boto3 sessions and clients are created through `AwsClientFactory`.
7. Core/domain/AWS modules do not prompt through Typer or render through Rich.
8. Commands coordinate workflows; reusable business rules live outside command handlers.
9. Application/domain failures use application-specific exceptions, not presentation-layer
   exceptions.
10. Refactoring does not add speculative features or dependencies.
11. Local or AWS mutation is never introduced into a read-only plan or status path.
12. Each accepted step leaves the package importable, lint-clean, tested for its scope, and
    releasable.

## Dependency Direction

The intended dependency direction is:

```text
cli.py and command rendering
    -> feature workflows
        -> workspace and feature-domain rules
        -> AWS service adapters
            -> AwsClientFactory
```

Imports must not point back toward presentation. In particular:

- `workspace/`, installer-domain modules, configuration-domain modules, and `aws/` must not
  import command modules.
- `workspace/`, installer-domain modules, configuration-domain modules, and `aws/` must not
  import Typer or Rich.
- One command module must not import underscore-prefixed helpers from another command module.
- AWS service adapters return structured data or raise application errors; they do not print.

## Working Agreement

### One active step

Only one numbered step is active at a time. Do not start the next step until the active step has:

- A reviewed diff with no unrelated changes.
- Required focused tests and Ruff passing.
- A completed checkpoint record in this file or the commit/PR description.
- An explicit decision to accept, revise, or revert the step.

### Structural and behavioral separation

A structural step moves ownership without intentionally changing behavior. A behavioral fix gets
its own step or clearly isolated commit with regression tests. If a move reveals a defect, record
the defect under `Deferred findings`; do not silently fix it during the move.

### Compatibility policy

Temporary re-exports are allowed to keep steps small. Every compatibility export must be listed
in the checkpoint record with its intended removal step. Do not create compatibility aliases
without a removal owner.

### Adjusting the plan

After any step, future steps may be reordered, split, renamed, or removed. When adjusting:

1. Preserve the accepted step's public contracts.
2. Update the ledger and dependencies of future steps.
3. Record the decision in the latest checkpoint.
4. Add an explicit migration step if an accepted contract must change.

This keeps adjustment local and avoids a repository-wide re-review.

## Step Ledger

| Step | Name | Status | Depends on |
|---:|---|---|---|
| 0 | Stabilize current work and record baseline | In progress | None |
| 1 | Complete workspace model extraction | In progress | Step 0 |
| 2 | Extract workspace storage | Not started | Step 1 |
| 3 | Extract workspace paths and readiness | Not started | Step 2 |
| 4 | Correct authentication ownership and add AWS execution context | Not started | Step 1 |
| 5 | Consolidate installer version rules | Not started | Step 1 |
| 6 | Consolidate installer validation and parameter mapping | Not started | Steps 3, 5 |
| 7 | Establish shared installer template and planning services | Not started | Steps 5, 6 |
| 8 | Decompose installer deployment orchestration | Not started | Steps 4, 7 |
| 9 | Correct installer source preparation behavior | Not started | Step 8 |
| 10 | Simplify configuration upload and download | Not started | Steps 2, 4 |
| 11 | Separate status data collection from rendering | Not started | Steps 3, 4, 6 |
| 12 | Clarify packaged resource layout | Not started | Steps 2, 7, 10 |
| 13 | Remove compatibility layers and normalize names | Not started | Steps 1-12 |
| 14 | Final integration and release review | Not started | Step 13 |

Steps with the same completed prerequisites may be reordered, but they should still be executed
one at a time. If a step's scope grows beyond the listed responsibility, split it before editing.

## Step 0: Stabilize Current Work and Record Baseline

### Goal

Turn the existing uncommitted work into a known, reviewable starting point without losing or
redoing it.

### In scope

- Inventory the existing changed and untracked files.
- Classify every current change as documentation, mechanical move, behavior/schema change, or
  unrelated work.
- Decide whether the current model extraction is kept as one patch or split into structural and
  behavioral commits.
- Run and record the initial Ruff and full-test baselines.
- Record any pre-existing failure instead of attributing it to a later step.

### Out of scope

- New module extraction.
- New validation rules or defaults.
- Fixing defects discovered during classification.
- AWS or customer-workspace mutation.

### Acceptance gate

- Every dirty file has an identified owner and purpose.
- Structural moves can be reviewed independently from behavior/schema changes.
- Baseline command results are recorded.
- The repository is committed at a known checkpoint, or the remaining dirty state is explicitly
  documented before Step 1 continues.

### Handoff contract

Later steps may assume that all pre-refactor edits are accounted for and that baseline failures
are known. They must not reclassify Step 0 changes unless new evidence is found.

## Step 1: Complete Workspace Model Extraction

### Goal

Make `lza_workbench.workspace` the single package owning workspace Pydantic models while
preserving existing serialized behavior. The accepted checkpoint will record whether the models
remain grouped or are split into focused configuration, installer, and state modules.

### In scope

- Complete the already-started `workspace/` package extraction using the chosen model-module
  boundaries.
- Move model definitions only.
- Keep temporary re-exports from `core.workspace` while callers are migrated.
- Update imports one caller group at a time.
- Add or retain model serialization and validation tests for existing behavior.

### Out of scope

- Storage and path functions.
- Readiness evaluation.
- Installer parameter mapping.
- New defaults, repository types, validation policies, model renames, or schema-version changes.
- Authentication redesign.

### Required review decision

The current in-progress workspace-model extraction contains validation/default changes as well
as moved models. Choose one before acceptance:

- Move behavior changes into their later owning steps; or
- Keep a behavior change only if it has a focused test, migration impact is documented, and the
  checkpoint explicitly accepts it.

### Acceptance gate

- Models have one implementation, not copied implementations.
- YAML/JSON round trips remain compatible with the accepted schema.
- `core.workspace` compatibility exports are listed for removal in Step 13.
- Workspace configuration, readiness, init, import, installer, and configuration focused tests
  pass.

### Handoff contract

Later steps import models from the public modules recorded in this step's checkpoint. They may
rely on the accepted field names, defaults, validators, and schema version recorded there.

## Step 2: Extract Workspace Storage

### Goal

Give workspace YAML and state JSON persistence one clear owner without changing serialization.

### In scope

- Add `workspace/storage.py`.
- Move workspace config/state path constants.
- Move load/write functions for YAML and JSON.
- Preserve encoding, formatting, validation, missing-state behavior, and error semantics.
- Migrate callers by workflow group.
- Keep temporary re-exports if needed.

### Out of scope

- Atomic-write redesign.
- Schema migration.
- Readiness or path-discovery behavior.
- Installer/configuration artifact state policy.

### Acceptance gate

- Round-trip tests cover workspace configuration and state.
- Init/import and at least one state-writing workflow use the new public storage API.
- `workspace.models` contains no filesystem I/O.
- Temporary exports and their removal step are recorded.

### Handoff contract

All later steps use `workspace.storage` for workspace metadata persistence. Serialization changes
require a separate behavioral/migration step.

## Step 3: Extract Workspace Paths and Readiness

### Goal

Separate pure workspace discovery/path rules from readiness evaluation and remove Typer from the
workspace domain.

### In scope

- Add `workspace/paths.py` for pure path resolution and target validation.
- Keep prompts in init/import command boundaries.
- Add `workspace/readiness.py` for readiness levels, context loading, evaluation, and errors.
- Preserve readiness rules while moving them.
- Add table-driven readiness transition tests.

### Out of scope

- Changing which installer fields are required.
- Auto-repairing incomplete workspaces.
- AWS authentication/account health checks.
- Reorganizing installer-domain code.

### Acceptance gate

- Workspace modules do not import Typer or Rich.
- Pure path helpers do not prompt or print.
- Existing commands enforce the same minimum readiness levels.
- Path, init/import, and readiness tests pass.

### Handoff contract

Later features use `workspace.readiness.load_workspace_context` and public path APIs. Installer
validation may later replace the internals of one readiness rule without moving readiness again.

## Step 4: Correct Authentication Ownership and Add AWS Execution Context

### Goal

Keep authentication external and make every workflow resolve AWS configuration consistently and
safely.

### Behavior and security scope

This step intentionally changes authentication behavior and requires focused regression tests.

### In scope

- Remove persisted secret access keys from models, examples, and CLI inputs.
- Define explicit handling for existing workspace files containing obsolete secret fields.
- Support external profiles and optional role assumption without storing credentials.
- Add a small AWS execution-context result containing region, factory, and optional identity or
  validation error.
- Add one resolver for configured values and allowed CLI overrides.
- Migrate commands one at a time: plan, deploy, config upload/download, then status.
- Add an account mismatch guard before AWS mutation when `account_id` is configured.

### Out of scope

- Creating AWS profiles or performing SSO login.
- Changing service-specific AWS operations.
- Installer source preparation.
- Broad exception/error hierarchy redesign.

### Acceptance gate

- No secret is accepted for persistence or serialized to `lza-workspace.yaml`.
- Every AWS workflow uses the shared resolver and full configured authentication context.
- Read-only status can report unavailable authentication without pretending AWS state is absent.
- Mutating workflows fail before mutation on configured-account mismatch.
- Profile, role, missing-authentication, and account-mismatch tests pass.

### Handoff contract

Later workflows receive AWS access through the accepted execution-context API and must not
reimplement profile/region/identity resolution.

## Step 5: Consolidate Installer Version Rules

### Goal

Give LZA version normalization and branch conversion one authoritative implementation.

### In scope

- Add `installer/versions.py` when the first implementation moves.
- Define tested behavior for `latest`, `main`, `master`, `vX.Y.Z`, `X.Y.Z`, and
  `release/vX.Y.Z`.
- Consolidate version normalization, version-to-branch conversion, and branch-to-version
  extraction.
- Migrate CodeCommit, installer parameter mapping, template resolution, and status callers.

### Out of scope

- Version discovery or network lookup.
- Supported/blocked version policy.
- Template download fallback behavior.
- Renaming unrelated installer models.

### Acceptance gate

- A table-driven test documents all accepted conversions.
- `rg` finds no duplicate version/branch conversion implementation.
- Existing configured branch overrides remain authoritative.

### Handoff contract

All later installer steps use `installer.versions`; no inline release-branch construction is
introduced elsewhere.

## Step 6: Consolidate Installer Validation and Parameter Mapping

### Goal

Make readiness, plan, deploy, and status agree on installer completeness and CloudFormation
parameter values.

### In scope

- Add `installer/config.py`.
- Define a structured missing/invalid-field result.
- Replace `_has_required_installer_config` and `_gather_required_parameters` with one validator.
- Make readiness derive its Boolean decision from that validator.
- Move installer CloudFormation parameter mapping out of workspace code.
- Test all supported source types and option combinations.

### Out of scope

- Template file resolution and parsing.
- AWS calls.
- Preparing source repositories.
- Changing CloudFormation itself.

### Acceptance gate

- Required-field rules have one implementation.
- Parameter mapping has tests for GitHub, CodeCommit, S3, and CodeConnections where supported.
- Readiness, plan, deploy, and drift status consume the same public APIs.
- No installer-specific parameter construction remains in workspace modules.

### Handoff contract

Later installer and status steps rely on the public validator and parameter mapper; they do not
repeat source-specific field rules.

## Step 7: Establish Shared Installer Template and Planning Services

### Goal

Remove shared installer business logic from command-private helpers and make planning reusable by
deployment.

### In scope

- Add installer template/planning modules only as functions are moved.
- Move template resolution, parsing, parameter-schema inspection, and parameter validation.
- Make requested-version/template mismatch fallback explicit and testable.
- Prepare structured repository and CloudFormation plan results before rendering.
- Update plan and deploy to use public installer APIs.

### Out of scope

- Deployment mutation.
- Source repository creation/synchronization.
- Rich output redesign beyond accepting prepared results.
- Resource file relocation.

### Acceptance gate

- Deploy imports no private helpers from the plan command.
- Planning services do not import Typer or Rich.
- Template fallback never silently substitutes a different version.
- Plan remains read-only and its focused tests pass.

### Handoff contract

Step 8 may treat template and deployment-plan preparation as stable services and focus only on
orchestration.

## Step 8: Decompose Installer Deployment Orchestration

### Goal

Turn `run_installer_deploy` into short, readable orchestration without intentionally changing AWS
behavior.

### In scope

- Document current stages, failure points, mutation boundaries, blast radius, and rollback path.
- Extract preflight, source inspection, CloudFormation planning, confirmation/rendering, event
  handling, and successful state update into focused functions/services.
- Use the shared AWS context, installer validation, and planning services.
- Reject unknown or unsafe CloudFormation states before mutation.

### Out of scope

- Fixing S3/CodeCommit source semantics; that belongs to Step 9.
- Adding pipeline execution.
- Changing confirmation defaults or output unless required for correctness.

### Acceptance gate

- The main deployment function reads as a sequence of named stages.
- Read-only preparation is visibly separated from AWS mutation.
- Create, update, no-change, inaccessible, success, and failure outcomes have focused tests.
- No AWS mutation occurs in dry-run tests.

### Handoff contract

Step 9 changes source preparation behind the accepted deployment-stage interface without
reworking the orchestration.

## Step 9: Correct Installer Source Preparation Behavior

### Goal

Fix provider-specific installer source behavior in isolated, operationally reviewable commits.

### In scope

- Make S3 preparation use configured bucket and key values.
- Verify the synthesized CloudFormation parameters match the prepared S3 source.
- Decide and implement one explicit CodeCommit contract:
  - Fully synchronize the requested LZA source/ref and verify the target branch; or
  - Treat population as an external prerequisite and stop before deployment when uninitialized.
- Add regression tests for both providers.
- Document AWS blast radius and rollback for bucket/repository mutations.

### Out of scope

- Configuration-repository upload/download behavior.
- Pipeline execution.
- Supporting additional providers.
- Restructuring deployment stages again.

### Acceptance gate

- Deployment never claims an empty CodeCommit repository is prepared.
- The S3 object described to CloudFormation is the object inspected/prepared by the workflow.
- Access-denied and inaccessible states fail safely rather than looking initialized.
- Provider-specific tests pass without live AWS mutation.

### Handoff contract

Installer deployment may rely on each source adapter's explicit inspect/prepare result and does
not contain provider field mapping.

## Step 10: Simplify Configuration Upload and Download

### Goal

Share real configuration-transfer rules while preserving clear upload and download workflows.

### In scope

- Add a configuration feature package only when code is moved into it.
- Share S3 archive-location resolution.
- Use the shared AWS execution context.
- Consolidate artifact metadata/state updates where semantics are identical.
- Keep upload packaging and download extraction separate.
- Ensure exclusion rules are applied consistently.

### Out of scope

- New repository providers.
- Starting or watching pipelines.
- Changing archive format.
- Moving packaged resources.

### Acceptance gate

- Upload/download do not duplicate AWS resolution or archive-location business rules.
- Exclusion, identical-content, force/overwrite, dry-run, and state-update behavior are tested.
- Download extraction remains safe and does not modify customer files before validation succeeds.

### Handoff contract

Later configuration features use the accepted transfer/location/state APIs and do not rebuild S3
paths or artifact metadata independently.

## Step 11: Separate Status Data Collection from Rendering

### Goal

Make status calculations independently testable and keep renderers presentation-only.

### In scope

- Fix pipeline status to use `installer_pipeline_execution_id` and
  `config_pipeline_execution_id` with a focused regression test.
- Prepare structured results for root, installer, configuration, and pipeline status.
- Extract pure drift and state-alignment calculations.
- Keep explicit synchronization actions outside read-only rendering.
- Split the long installer renderer into named rendering sections.

### Out of scope

- New status checks.
- Pipeline start/watch implementation.
- AWS authentication resolution changes.
- Model or resource renaming.

### Acceptance gate

- Renderers receive prepared result objects and do not call AWS or write files.
- Status calculations can be tested without capturing Rich output.
- Missing or inaccessible AWS state is distinguished from “not deployed.”
- Pipeline execution IDs display from real `WorkspaceState` fields.

### Handoff contract

Future status features extend result models/calculators first and render them second.

## Step 12: Clarify Packaged Resource Layout

### Goal

Make package paths clearly distinguish code, installer templates, workspace examples, starter
configuration, and runtime state.

### In scope

- Inventory `config/` and `templates/` resources and confirm package-build inclusion.
- Decide whether packaged `state.json` has a supported purpose.
- Create an agreed `resources/` hierarchy.
- Move one resource category at a time and update its resolver/tests/docs.
- Verify wheel and source-distribution contents.

### Out of scope

- Changing resource contents or defaults.
- Workspace schema migration.
- Adding new templates/examples.
- General Python module renames.

### Acceptance gate

- Resource paths reveal their purpose.
- Runtime-like state is not presented as a packaged default unless explicitly supported.
- Editable installs and built packages resolve the same resources.
- Package build-content tests pass.

### Handoff contract

Resource resolvers, not callers, own physical package paths. Later moves must preserve those public
resolver APIs.

## Step 13: Remove Compatibility Layers and Normalize Names

### Goal

Remove temporary migration scaffolding and apply only naming changes that improve ownership.

### In scope

- Remove recorded `core.workspace` re-exports one group at a time.
- Remove obsolete modules/constants/helpers after `rg` confirms no callers.
- Rename redundant status modules if still valuable.
- Rename models only with explicit compatibility/migration consideration.
- Confirm dependency direction with import searches and architecture tests.

### Out of scope

- New business behavior.
- Broad cosmetic renaming.
- Feature development.
- Resource reorganization.

### Acceptance gate

- No temporary compatibility item remains unaccounted for.
- Commands do not import private helpers from other commands.
- Domain/AWS modules do not import Typer or Rich.
- Authentication, installer validation, and version conversion each have one source of truth.
- No known dead compatibility module or constant remains.

### Handoff contract

The refactored public package structure is final for the release review. Step 14 should validate,
document, and release it rather than redesign it.

## Step 14: Final Integration and Release Review

### Goal

Validate the complete refactor and leave the project releasable.

### In scope

- Run Ruff and the full test suite.
- Build the wheel/source distribution and inspect included resources.
- Run CLI smoke tests for init, import, plan, deploy dry-run, config upload/download dry-run, and
  status.
- Review `pyproject.toml`, dependency metadata, entry points, and version.
- Update README only for current user-visible changes.
- Reconcile `TODO.md`, `docs/refactor_steps.md`, and this ledger.
- Add a concise milestone to `docs/DONE.md` only after implementation, review, and validation are
  complete.

### Out of scope

- New features.
- Opportunistic cleanup.
- Live AWS mutation unless separately authorized and planned.
- Reopening accepted module boundaries without a newly documented defect.

### Acceptance gate

- All automated validation passes or accepted baseline exceptions are documented.
- Package contents and entry points are correct.
- Documentation matches current behavior and structure.
- No compatibility removal or deferred correctness item required for this refactor remains open.
- The final version follows the project's versioning scheme.

## Per-Step Checkpoint Template

Append or link one checkpoint when a step is ready for review:

```markdown
### Step N checkpoint — YYYY-MM-DD

- Status: Ready for review | Accepted | Needs revision | Reverted
- Commit/PR:
- Responsibility completed:
- Files intentionally changed:
- Public APIs/contracts added or changed:
- Behavior changes: None | List with tests
- Compatibility exports introduced:
- Compatibility exports removed:
- Focused validation:
- Ruff result:
- Full test result: Not required | Result
- Deferred findings:
- Decisions made:
- Assumptions available to the next step:
- Requested plan adjustments:
```

The `Assumptions available to the next step` field is the compact handoff. It should be sufficient
for continuing work without a fresh whole-project review.

## Review Checklist for Every Step

Before accepting a step, verify:

- The diff implements only the named responsibility.
- Structural moves and behavioral changes are separated or explicitly justified.
- No unrelated user changes were overwritten.
- New public names describe ownership clearly.
- No circular or presentation-to-domain dependency was introduced.
- Exceptions are not silently swallowed.
- Dry-run and read-only guarantees remain true.
- AWS blast radius and rollback are documented for any mutating workflow change.
- Focused tests cover the moved rule or fixed defect.
- Ruff passes.
- `pyproject.toml` remains consistent; version/dependency changes are made only when required.
- The checkpoint records enough context for the next step.

## Completion Criteria

The refactor is complete when:

- Each workflow has a short, predictable call path.
- Workspace models, storage, paths, and readiness have distinct owners.
- Installer version, validation, template, planning, and deployment rules have distinct owners.
- AWS context resolution has one implementation and persists no secrets.
- Commands orchestrate public services rather than sharing private helpers.
- Status data preparation is separate from Rich rendering.
- Packaged resources have unambiguous locations and build coverage.
- Temporary compatibility layers are removed.
- Known correctness/security findings have regression tests.
- The final package passes validation and is documented as delivered.
