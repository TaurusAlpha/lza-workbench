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

- [] Review the current working tree and finish, commit, or deliberately preserve unrelated
      edits before starting the refactor.
- [] Run the existing Ruff check and record whether it passes before changing code.
- [] Run the full test suite once and record the baseline result.
- [] Draw the current call path for `lza init` from `cli.py` to its lowest-level file writes.
- [] Draw the current call path for `lza installer plan` from `cli.py` to AWS inspection.
- [] Draw the current call path for `lza installer deploy` from `cli.py` to state persistence.
- [] Write down which modules currently prompt, print, read files, write files, and call AWS.

Achievement: you have a verified starting point and can describe the current architecture before
changing it.

## Phase 1: Small Cleanup and Confidence Builders

- [x] In `commands/workspace_import.py`, move the misplaced workflow description to the actual
      `run_import` docstring position without changing behavior.
- [x] Inspect `commands/__init__.py` and confirm whether `DEFAULT_LZA_VERSION` and
      `DEFAULT_AWS_REGION` have callers.
- [x] Remove unused command defaults or migrate callers to one authoritative default location.
- [x] Resolve the `eu-west-1` versus `us-east-1` default-region inconsistency.
- [] In `commands/status/status_pipeline.py`, replace the nonexistent
      `pipeline_execution_id` lookup with the intended installer and/or configuration execution
      state fields.
- [] Add a focused status test proving the correct execution ID is displayed.
- [] Inspect unnecessary `hasattr` and `getattr` calls on known Pydantic fields and remove one
      only when the model guarantees the field exists.
- [] Rename the mocked AWS client factory test module if the team agrees that “integration” is
      misleading; do not change its behavior in the same task.

Achievement: you have completed several small, testable improvements and practiced making narrow
diffs.

## Phase 2: Separate Workspace Models

DONE

## Phase 3: Separate Workspace Persistence

DONE

Achievement: models no longer know how or where they are stored.

## Phase 4: Separate Workspace Paths and Readiness

- [x] List all workspace path-resolution functions and identify which ones are pure path logic
      and which ones prompt through Typer.
      - Pure: `workspace.paths.is_workspace_dir`, `resolve_workspace_dir`, and
        `resolve_init_workspace_dir`.
      - Prompting: `commands.workspace_common.value_or_prompt`, called only by init/import.
- [x] Move pure path-resolution functions to a workspace paths module.
- [x] Move prompting out of workspace/core code and into the init or import command boundary.
- [x] Run workspace path, init, and import tests.
- [x] Move `WorkspaceReadinessLevel` and `WorkspaceContext` to the context module.
- [x] Move readiness evaluation without changing its rules.
- [x] Move readiness error construction to the context module.
- [x] Add table-driven tests covering each readiness transition.
- [x] Update callers one workflow at a time.
- [x] Remove readiness re-exports after confirming all callers use the new module.

Achievement: workspace discovery, persistence, and readiness have separate responsibilities, and
the workspace domain no longer depends on Typer.

## Phase 5: Consolidate Installer Version Rules

- [] Inventory every function and inline expression that converts LZA versions, release refs,
      and branch names.
- [] Write tests describing expected handling of `latest`, `main`, `master`, `vX.Y.Z`, `X.Y.Z`,
      and `release/vX.Y.Z`.
- [] Choose one installer versions module as the owner of normalization rules.
- [] Move or implement one authoritative version-normalization function.
- [] Move or implement one authoritative version-to-branch conversion function.
- [] Move or implement branch-to-version extraction if status reporting needs the reverse
      conversion.
- [] Replace the CodeCommit implementation with calls to the shared functions.
- [] Replace inline conversion in CloudFormation parameter construction.
- [] Replace status-specific normalization functions.
- [] Remove duplicate version helpers after `rg` confirms they have no callers.

Achievement: version behavior is documented by tests and has one source of truth.

## Phase 6: Consolidate Installer Configuration Validation

- [] Compare `_has_required_installer_config` with `_gather_required_parameters` field by field.
- [] Write tests for required fields for GitHub, CodeCommit, S3, and CodeConnections sources.
- [] Choose one structured validation result that can describe every missing field.
- [] Move required-field validation into the installer configuration module.
- [] Make installer planning use the shared validator.
- [] Make installer deployment use the shared validator.
- [] Make workspace readiness derive its Boolean decision from the shared validation result.
- [] Remove the old duplicate validators.
- [x] Move CloudFormation installer parameter mapping from workspace code to installer
      configuration code.
- [] Add mapping tests for every supported repository source type.

Achievement: plan, deploy, and readiness cannot silently disagree about installer completeness.

## Phase 7: Correct AWS Authentication Ownership

This phase changes behavior and security assumptions. Keep its fixes separate from structural
moves and review operational impact carefully.

- [] Document the supported external authentication methods before editing models.
- [] Remove secret access keys from declarative workspace configuration and examples.
- [] Remove CLI options that would persist secret keys in workspace YAML.
- [] Add migration/error behavior for an existing workspace that contains secret-key fields.
- [] Add tests proving secrets are never serialized to `lza-workspace.yaml`.
- [] Define a small AWS execution-context result containing the resolved region, factory, and
      optional identity/error information.
- [] Implement one resolver for profile overrides, configured profile/role, region, and identity
      validation.
- [] Migrate installer planning to the resolver.
- [] Migrate installer deployment to the resolver.
- [] Migrate configuration upload and download to the resolver.
- [] Migrate root, installer, and pipeline status to the resolver one command at a time.
- [] Add tests proving every workflow uses the selected profile or role.
- [] Add an account-safety check before mutating AWS when the configured account ID is available.
- [] Remove repeated profile/region/factory/identity blocks after confirming no callers remain.

Achievement: authentication is external, consistent, and safe across every command.

## Phase 8: Establish Installer Feature Modules

- [x] Create the installer feature package only when the first shared function is ready to move.
- [] Move template resolution from `commands/installer_plan.py` into the installer feature.
- [] Move template parameter inspection into the installer feature.
- [] Move template parameter validation into the installer feature.
- [] Give these functions public names and update installer plan to use them.
- [] Update installer deploy to use the same public functions.
- [] Remove imports of underscore-prefixed helpers from one command module into another.
- [] Move planning result preparation out of Rich rendering code.
- [] Make the plan renderer accept prepared results and only render them.
- [] Run plan tests after each moved responsibility.

Achievement: installer plan and deploy share public domain logic instead of command internals.

## Phase 9: Decompose Installer Deployment

This is intentionally late because it requires understanding all preceding boundaries.

- [] Write a one-page sequence of the current deployment stages and their failure points.
- [] Identify which stages are read-only and which mutate local files or AWS.
- [] Extract preflight validation from `run_installer_deploy` into a focused function.
- [] Extract source repository inspection from deployment orchestration.
- [] Fix S3 source preparation to use configured bucket and key values in a separate behavioral
      commit.
- [] Decide whether CodeCommit synchronization is implemented or explicitly required as a
      manual prerequisite.
- [] Add a regression test for the chosen CodeCommit behavior.
- [] Extract CloudFormation plan preparation from deployment orchestration.
- [] Reject unsafe or unknown CloudFormation states before mutation.
- [] Extract confirmation and Rich tables into presentation helpers.
- [] Extract state update after successful deployment.
- [] Reduce `run_installer_deploy` to readable orchestration of named stages.
- [] Add tests for create, update, no-change, inaccessible, and failure outcomes.

Achievement: deployment reads as a short workflow, and each risky stage can be tested separately.

## Phase 10: Simplify Configuration Upload and Download

- [] Compare `config_upload.py` and `config_download.py` and list duplicated business rules.
- [] Extract one shared resolver for the configured S3 archive location.
- [] Reuse the shared AWS execution context rather than constructing a factory locally.
- [] Extract configuration artifact metadata updates into a focused state helper.
- [] Keep upload-specific packaging and download-specific extraction separate.
- [] Add tests proving excluded files and directories behave consistently in both directions.
- [] Check extraction behavior for archives containing excluded directories.
- [] Move archive operations into the configuration feature package when their callers are
      ready.

Achievement: upload and download share only real domain rules while retaining clear individual
workflows.

## Phase 11: Separate Status Data from Rendering

- [] For root status, create a structured result before rendering any Rich output.
- [] For installer status, separate AWS/config/state comparison from report rendering.
- [] Move configuration drift calculation into a pure function and add focused tests.
- [] Move state-alignment calculation into a pure function and add focused tests.
- [] For pipeline status, prepare pipeline names and execution metadata before rendering.
- [] Make status renderers consume results without calling AWS or writing files.
- [] Keep explicit synchronization actions outside read-only report rendering.
- [] Shorten the 200-line installer status renderer by rendering small, named report sections.

Achievement: status calculations can be tested without capturing terminal output.

## Phase 12: Clarify Files and Resource Names

- [] Inventory which files under `src/lza_workbench/config/` are packaged resources, examples,
      or obsolete runtime-like files.
- [] Confirm whether packaged `state.json` has a supported purpose; remove or relocate it if not.
- [] Create a resources hierarchy only after agreeing on its categories.
- [] Move the packaged installer CloudFormation template and update its resolver.
- [] Move workspace examples and update documentation references.
- [] Move the default customer configuration template and update template discovery.
- [] Rename status modules from redundant names only after functional refactors are complete.
- [] Rename configuration model classes only when the value outweighs compatibility churn.
- [] Verify package build contents after resource moves.

Achievement: directory and file names reveal whether content is code, a packaged template, an
example, or runtime workspace data.

## Phase 13: Remove Compatibility Layers and Review the Result

- [] Search for temporary re-exports and compatibility imports created during the refactor.
- [] Remove one compatibility layer at a time and run focused tests.
- [] Confirm no command module imports private helpers from another command module.
- [] Confirm core, workspace, installer-domain, and AWS modules do not import Typer or Rich.
- [] Confirm authentication resolution has one source of truth.
- [] Confirm installer validation has one source of truth.
- [] Confirm version conversion has one source of truth.
- [] Run Ruff, the full test suite, and package build validation.
- [] Review `pyproject.toml`, README usage, TODO items, and package version for release readiness.
- [] Update `docs/DONE.md` only after the refactor is implemented, reviewed, and validated.

Achievement: temporary migration scaffolding is gone and the final structure matches the intended
dependency direction.

## Definition of Done for Each Checkbox

A task is complete only when:

- Its scope can be explained in one or two sentences.
- The diff contains no unrelated change.
- Relevant tests pass.
- Ruff passes.
- Imports and public names are understandable.
- Any behavior change is documented and tested.
- You can explain every changed line before committing it.
