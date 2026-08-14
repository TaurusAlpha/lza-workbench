# Refactoring Direction

## Purpose

This document describes how to simplify LZA Workbench without turning it into a single-file
application or changing its behavior unnecessarily.

The project is a good environment for learning refactoring by doing. Its core ideas are sound,
but responsibilities are spread across enough files and layers that following one workflow is
harder than the project size warrants. This is a maintainability issue, not merely a lack of
experience from the reader.

The companion [`refactor_steps.md`](refactor_steps.md) turns this direction into small,
independently achievable tasks.

## Overall Assessment

The project has a good foundation:

- Commands are named around LZA workflows.
- Workspace configuration uses typed Pydantic models.
- AWS client construction is centralized.
- Application-specific errors exist.
- `pathlib`, UTC-aware timestamps, dataclasses, enums, and type annotations are used.
- Tests are organized by feature.
- The dependency set is small.

The main problem is accidental complexity:

- `core/workspace.py` owns models, persistence, path handling, readiness, configuration diff
  types, and installer CloudFormation parameter mapping.
- Some command functions coordinate validation, prompting, AWS calls, mutation, state updates,
  and Rich output in one place.
- Command modules import private helpers from other command modules.
- Authentication, installer validation, defaults, and version conversion have multiple sources
  of truth.
- Core and AWS modules sometimes depend on Typer or presentation helpers.
- `config/`, `templates/`, and `core/templates.py` have overlapping names and responsibilities.

A mature codebase is not defined by the number of layers or files. A mature structure makes it
easy to answer:

1. Where does this business rule live?
2. Which function starts this workflow?
3. Which module performs the AWS operation?
4. Which module reads or writes workspace state?
5. Which layer prompts the user and renders output?

## Refactoring Goals

- Make a command workflow traceable through a short and predictable call path.
- Give each business rule one authoritative implementation.
- Keep Typer and Rich at the presentation boundary.
- Keep AWS modules focused on AWS requests and structured results.
- Separate workspace models from filesystem persistence and readiness evaluation.
- Keep command handlers small and focused on orchestration.
- Preserve existing CLI behavior while structure is moved.
- Make changes in small commits that are easy to understand and revert.

## Non-Goals

- Do not rewrite the entire project at once.
- Do not collapse the project into one or two large files.
- Do not introduce a framework, dependency-injection container, or speculative abstraction.
- Do not combine large file moves with unrelated feature development.
- Do not rename every class or module merely for stylistic consistency.
- Do not add future functionality as part of structural cleanup.

## Proposed Package Direction

The exact names can evolve, but the code should become organized around workspace,
installer, configuration, and AWS responsibilities:

```text
src/lza_workbench/
├── cli.py
├── cli_parameters.py
├── errors.py
├── workspace/
│   ├── models.py
│   ├── storage.py
│   ├── readiness.py
│   └── templates.py
├── installer/
│   ├── config.py
│   ├── versions.py
│   ├── planning.py
│   ├── deployment.py
│   └── status.py
├── configuration/
│   ├── archive.py
│   ├── upload.py
│   ├── download.py
│   └── status.py
├── aws/
│   ├── clients.py
│   ├── cloudformation.py
│   ├── codecommit.py
│   └── s3.py
└── resources/
    ├── installer/
    ├── examples/
    └── configuration_templates/
```

This is a direction, not a requirement to create every directory immediately. A directory
should be created only when code is ready to move into it.

## Dependency Direction

Dependencies should generally point in this direction:

```text
CLI and rendering
    -> feature workflows
        -> workspace/domain rules
        -> AWS service modules
            -> AwsClientFactory
```

Important boundaries:

- `cli.py` owns Typer registration and translates application failures into process results.
- Command or rendering code owns prompts, confirmations, Rich tables, and messages.
- Feature workflows coordinate domain rules, AWS operations, and state persistence.
- Workspace modules own models, readiness, paths, and local persistence.
- AWS modules accept a client or factory, call AWS, and return structured results.
- Core, workspace, installer-domain, and AWS modules should not print directly.
- Feature modules should not import private underscore-prefixed helpers from other command
  modules.

## Specific Areas to Simplify

### Workspace responsibilities

Split `core/workspace.py` gradually:

- Move Pydantic configuration and state classes to a models module.
- Move YAML and JSON load/write operations to a storage module.
- Move readiness evaluation and readiness errors to a readiness module.
- Move installer-specific CloudFormation parameter mapping to the installer feature.
- Leave temporary re-exports in `core/workspace.py` while callers are migrated.

Temporary re-exports allow small commits and prevent a single repository-wide import rewrite.
They should be removed after all callers use the new locations.

### Installer responsibilities

Installer planning and deployment currently share logic through private command helpers. Shared
logic should live in public installer modules:

- Required configuration validation
- Template resolution and inspection
- CloudFormation parameter validation
- LZA version and branch normalization
- Deployment planning

The plan and deploy commands should consume the same public functions.

### AWS execution context

Commands should not independently resolve profile, region, role, credentials, factory, identity,
and authentication errors. One focused resolver should produce the AWS execution context used by
all workflows.

AWS authentication itself must remain external to the tool. Workspace configuration may refer to
an external profile or role, but it should not persist secret access keys.

### Presentation

Long Rich report functions are not automatically wrong, but they should receive prepared result
objects rather than calculate domain state while rendering. This keeps reports readable without
making AWS or workspace logic depend on Rich.

### Defaults and normalization

Each default or conversion rule should have one owner:

- Default AWS region
- Default LZA version
- LZA version normalization
- Version-to-branch conversion
- Installer-required configuration fields
- Pipeline names derived from the accelerator prefix

Avoid extracting tiny helpers only to remove two repeated lines. Apply DRY to business rules that
can drift, not to every similar-looking expression.

### Packaged resources

The current `config/` and `templates/` names are ambiguous. Packaged CloudFormation templates,
workspace examples, and starter customer configuration should eventually live under a clearly
named resources hierarchy. Runtime `.lza/state.json` remains customer-workspace data and should
not be confused with packaged example state.

## Correctness and Security Work to Keep Separate

The following known problems should be fixed in focused behavioral commits rather than hidden
inside file moves:

- Remove plaintext AWS secret keys from workspace configuration.
- Make every operational command use the complete configured AWS authentication context.
- Use configured S3 installer source bucket and key values.
- Either implement CodeCommit repository synchronization or stop claiming that an empty
  repository was prepared.
- Read the actual installer/configuration pipeline execution fields from `WorkspaceState`.
- Make installer-template fallback explicit when the packaged template version differs from the
  requested version.

Keeping these fixes separate makes their tests and operational impact reviewable.

## Naming Guidance

Names are already mostly understandable. Improve names only where they clarify ownership:

- Prefer `InstallerConfig` over `LzaInstaller` when that model is moved.
- Prefer `InstallerPipelineConfig` over `PipelineInstaller` when that model is moved.
- Inside a `status/` package, use concise module names such as `installer.py`.
- Prefer public domain names such as `find_missing_installer_parameters` over importing private
  helpers from command modules.
- Keep domain-standard abbreviations such as AWS, LZA, ARN, S3, and CloudFormation.

## Learning and LLM Collaboration

The learner should own:

- The order of changes
- Module boundaries
- Names
- Expected behavior
- Acceptance of each patch

An LLM is useful for:

- Explaining the current call path
- Finding imports and references
- Identifying possible circular imports
- Comparing two module-boundary options
- Performing mechanical moves after the destination is agreed
- Creating focused test scaffolding
- Reviewing a small patch

Do not accept a refactoring patch that cannot be explained during a code review. For each change,
be able to explain why the destination module owns the responsibility, which callers changed, and
how behavior was verified.

## Working Method

For every task:

1. State the responsibility being moved or consolidated.
2. Identify current callers with `rg`.
3. Add or identify a focused behavioral test.
4. Make one small structural or behavioral change.
5. Run Ruff and the relevant tests.
6. Review the diff for accidental behavior changes.
7. Commit before starting the next concern.

Use separate commits for structural moves and behavior changes whenever practical.

## Completion Criteria

The refactor is successful when:

- A new contributor can follow each CLI command through a short call path.
- `core/workspace.py` is removed or reduced to a temporary compatibility module.
- Commands do not import private helpers from other command modules.
- Installer validation and version conversion each have one source of truth.
- All workflows use the same AWS context resolver.
- Core/domain/AWS modules do not prompt or render output.
- Packaged resources have unambiguous locations.
- Existing CLI behavior remains covered by tests.
- The known correctness and security findings have focused regression tests.
