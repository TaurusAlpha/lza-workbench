Implement the approved pre-GUI architectural refactors described below.

Treat the supplied audit findings and implementation handoff as the scope of work.

Requirements:

- Implement only items classified as required before Web GUI work.
- Do not implement optional or “can wait” recommendations.
- Preserve existing user-facing behavior unless the handoff explicitly requires a change.
- Preserve the intended dependency direction:
  `cli -> workflows -> features/AWS`.
- Keep business logic in Python.
- Prefer modifying existing modules over creating new abstractions.
- Introduce classes, DTOs, protocols, or other design patterns only where the approved plan explicitly justifies them.
- Do not add GUI, FastAPI, frontend, server, or Web dependencies.
- Do not perform unrelated refactoring.
- Keep CLI behavior working.
- Update focused tests only where needed.
- Run `uv run ruff check . --fix`.
- Run focused tests for the affected areas.
- Review `pyproject.toml` and update it only if the implementation genuinely requires metadata changes.
- Update `PROJECT.md`, `AGENTS.md`, `TODO.md`, `README.md`, or `docs/DONE.md` only where the approved handoff says documentation must change.

At the end, report:

1. implemented changes;
2. files changed;
3. validation performed;
4. anything from the approved plan that could not be completed;
5. whether the code is now ready for the next GUI-readiness step.

Approved audit / implementation handoff:

## Required implementation scope

### 1. Make root status one coherent observation

- In `src/lza_workbench/workflows/status_root.py`, change `get_root_status_workflow` so one invocation loads one `WorkspaceContext`, resolves one `AwsExecutionContext`, and gathers each installer, pipeline, repository, and Git observation once.
- Remove the nested call to `get_config_status_workflow`; `lza status config` remains an independent detailed workflow and must not be invoked by root status.
- Remove the resulting `ConfigurationStatusResult`/`get_config_status_workflow` imports and `RootStatusResult.config_status`.
- Remove the unused compatibility fields from `RootStatusResult`: `stack_name`, `stack_status`, `stack_exists`, `repository_type`, `config_dir`, `config_dir_exists`, `installer_pipeline_name`, and `config_pipeline_name`. Their data already exists in `installer`, `configuration_repo`, and the two `PipelineSummary` values.
- Do not redesign `ConfigurationStatusResult` or `get_config_status_workflow`; no change is required in `src/lza_workbench/workflows/status_config.py` beyond any narrowly necessary caller/type adjustment discovered during implementation.

### 2. Make Git health structured and independent of AWS availability

- In `src/lza_workbench/workflows/status_root.py`, replace `ConfigurationRepoSummary.remote_sync_summary` with the existing `GitRemoteSyncStatus | None` model from `src/lza_workbench/configuration/git.py` (use a descriptive field such as `git_sync_status`). Do not add another sync DTO or enum.
- In `_derive_overall_health`, derive divergence from `GitRemoteSyncStatus.status == "Diverged"`; health must not inspect human-readable summary text.
- In `get_root_status_workflow`, evaluate local Git remote-tracking status whenever the configuration directory is a Git repository, regardless of whether AWS identity resolution succeeded. AWS liveness and local Git observability are separate facts.
- In `src/lza_workbench/cli/commands/status_root.py::render_root_status`, render the existing `GitRemoteSyncStatus.summary` so terminal wording remains presentation logic.
- Do not change `GitRemoteSyncStatus` or Git comparison behavior in `src/lza_workbench/configuration/git.py` unless a type-only adjustment is strictly necessary.

## Architectural constraints

- Preserve `cli -> workflows -> features/AWS`; lower layers must not import CLI or workflows.
- Keep Typer, Rich, terminal formatting, and user-facing summary wording in `src/lza_workbench/cli`.
- Workflows return structured, interface-neutral results and own orchestration; AWS modules remain thin boto3 adapters using `AwsClientFactory`.
- Preserve `lza-workspace.yaml` as desired configuration and `.lza/state.json` as runtime/execution state.
- Root status remains read-only. Do not add GUI, FastAPI, frontend, server, or Web dependencies.
- Do not introduce a service class, protocol, generic status framework, or new shared abstraction for this refactor.

## Behavior that must remain unchanged

- `lza status`, `lza status installer`, and `lza status config` remain available with their existing purposes.
- Preserve root-status sections, labels, ordering, pipeline diagnostics, configured pipeline names, AWS identity/error reporting, and recorded-state fallback behavior.
- Preserve the health vocabulary and precedence: `Healthy`, `Running`, `Attention Required`, `Incomplete`, and the existing AWS-unavailable recorded-state messages.
- Preserve `get_config_status_workflow(target_dir=...)` and its current detailed result contract for the configuration status command.
- Status commands must not write workspace files/state or mutate AWS resources.
- The only intentional output change is that root status may show an actual local Git remote-sync result while AWS is unavailable instead of `Not Checked (AWS Unavailable)`.

## Focused validation

- Update `tests/workflows/test_status.py` to verify:
  - root status no longer invokes the detailed configuration workflow or repeats AWS/configuration observations;
  - a structured `Diverged` Git status yields `Attention Required`;
  - health does not depend on the text in `GitRemoteSyncStatus.summary`;
  - local Git sync is evaluated when AWS is unavailable;
  - existing live healthy and offline recorded-state fallbacks remain unchanged.
- Run `uv run pytest tests/workflows/test_status.py`.
- Run `uv run pytest tests/test_package.py`.
- Run `uv run ruff check . --fix` and `git diff --check`.
- Exercise the real `lza status` command against a temporary workspace, including an AWS-unavailable path; verify output, exit code, and that no workspace files change. Do not run the full test suite unless focused failures show broader impact.

## Documentation after implementation

- Project direction and guidance are already updated in `PROJECT.md`, `AGENTS.md`, `TODO.md`, and `docs/CODEX-GUI-IMPLEMENTATION.md`; do not rewrite them as part of the code refactor.
- Update `TODO.md` to mark the approved root-status readiness refactors complete.
- Update `docs/CODEX-GUI-IMPLEMENTATION.md` to mark step 2 complete.
- Add a concise completed architectural-refactor entry to `docs/DONE.md` only after implementation and focused validation succeed.
