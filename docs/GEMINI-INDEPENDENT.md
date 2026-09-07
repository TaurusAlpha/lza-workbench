# Independent Architecture Review: LZA Workbench

## Executive Assessment

The current LZA Workbench architecture was designed with strong defensive instincts: strict directional dependency layering (`web/cli -> workflows -> features/AWS`), avoidance of heavy third-party frameworks, explicit isolation of AWS side-effects, and enforcement through static AST tests.

However, an independent evaluation reveals that **the architecture has become overly conservative and fragmented**. The strict adherence to a purely functional, "workflow-first" model—combined with a ban on domain services and OOP patterns—has created noticeable structural friction:

1. **Layer Proliferation & File Symmetry**: There is an artificial 1:1 mirroring across `cli/commands/` (19 files) and `workflows/` (19 files), backed by sub-feature modules (`installer/deployment.py`, `installer/planning.py`, `installer/status.py`, etc.). A single user action frequently traverses four layers of thin procedural delegation (`cli -> workflow -> feature module -> aws adapter`) with minimal added value per layer.
2. **Missing Polymorphism in Configuration Repositories**: LZA supports multiple configuration destinations (S3, CodeCommit, CodeConnections, generic Git). Rather than modeling a `ConfigurationRepository` provider/strategy, the codebase relies on sprawling `if/elif` statements across `config_push.py`, `config_pull.py`, and `status_config.py`. This forces monolithic result DTOs (e.g. `ConfigurationStatusResult` with 57 flat fields, `ConfigPushResult` with both S3 and Git fields where 70% are `None`).
3. **Procedural CLI Leakage Masquerading as Reusable Workflows**: Several workflows are not genuinely interface-neutral. They inject synchronous terminal callbacks (`prompter: Callable` in `installer_init`, `confirm_callback: Callable` in `config_push` and `config_pull`, blocking `while True: time.sleep()` loops in `pipeline_watch`). These abstractions do not map to the stateless request-response or asynchronous polling models required by a Web GUI.
4. **Anemic Domain State**: `WorkspaceContext` is a passive tuple of `(workspace_dir, config, state)`. Every workflow repeatedly resolves child paths, re-evaluates readiness, and manually triggers ad-hoc `record_*` persistence helpers.

---

## Area-by-Area Evaluation

### 1. Workspace

- **Verdict**: *Locally overcomplicated in persistence; missing an encapsulating domain abstraction.*
- **Analysis**:
  - `WorkspaceReadinessLevel` ([`workspace/context.py`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workspace/context.py#L15-L55)) and `WorkspaceConfig` ([`workspace/schema.py`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workspace/schema.py)) are clean, well-typed Pydantic models.
  - However, `WorkspaceContext` is anemic. It does not provide basic derived properties like `config_dir`, `installer_dir`, `state_path`, or `is_imported`. Instead, 19 workflow files independently reconstruct `workspace_dir / config.configuration.local_path` and `workspace_dir / CONFIG_ARCHIVE_FILENAME`.
  - State persistence is fragmented into disparate `record_*` functions (`configuration/state.py`, `installer/state.py`, `pipeline/state.py`). `.lza/state.json` is treated as a loose dictionary of 25 optional fields without lifecycle encapsulation.

### 2. Installer

- **Verdict**: *Too fragmented across feature and workflow layers; procedural prompt injection.*
- **Analysis**:
  - The installer capability is split across 12 files in `src/lza_workbench/installer/` and 4 files in `src/lza_workbench/workflows/` (`installer_init`, `installer_plan`, `installer_deploy`, `installer_import`).
  - `installer/deployment.py` and `workflows/installer_deploy.py` have blurred responsibilities: validation and template resolution are split arbitrarily between the two.
  - In [`workflows/installer_init.py:49`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/installer_init.py#L49), `prompter: Callable[[str, str | None], str] | None` is injected into the workflow to drive an interactive terminal loop. A workflow should accept resolved inputs; parameter collection belongs in the interface (CLI prompt loop or Web form).

### 3. Configuration

- **Verdict**: *Hiding a missing domain abstraction (Repository Provider).*
- **Analysis**:
  - Configuration sources (S3, CodeCommit, CodeConnections, Git) have completely different lifecycles, transport mechanisms, and verification rules.
  - Because OOP/strategy patterns were avoided, `config_push.py` ([`workflows/config_push.py:101-125`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/config_push.py#L101-L125)) and `config_pull.py` ([`workflows/config_pull.py:100-130`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/config_pull.py#L100-L130)) branch procedurally on `if repo_type == "s3"` vs `git`.
  - `ConfigPushResult` and `ConfigPullResult` combine unrelated S3 fields (`zip_path`, `s3_bucket`, `s3_key`, `etag`) and Git fields (`git_remote`, `git_branch`, `git_commit`, `files_count`, `stashed_changes`).
  - Empty alias modules (`workflows/config_download.py` and `workflows/config_upload.py`) exist solely to mirror CLI command names.

### 4. Pipeline

- **Verdict**: *Mixed-responsibility workflows; diagnostics module is strong, but execution monitoring is CLI-coupled.*
- **Analysis**:
  - [`pipeline/failures.py`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/pipeline/failures.py) is one of the strongest modules in the codebase: it has high-cohesion domain models (`FailureDiagnostic`, `FailureCategory`, `PipelineActionFailure`) and robust parsing logic.
  - However, `pipeline_watch_workflow` ([`workflows/pipeline_watch.py`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/pipeline_watch.py#L193-L293)) is a synchronous, blocking polling loop using `time.sleep()`. This design was built for terminal execution with a live Rich display. When accessed from a Web server, blocking the server worker for 15–30 minutes is untenable. The workflow needs to separate *single-pass snapshot polling* from *execution observation loops*.

### 5. Status

- **Verdict**: *Partially corrected; root status is now clean, but `status_config` remains a monolithic antipattern.*
- **Analysis**:
  - The recent refactor of `status_root.py` successfully unified root observation into a single coherent pass and decoupled Git health from AWS availability.
  - However, `status_config.py` ([`workflows/status_config.py`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/status_config.py#L35-L95)) remains a major bottleneck: `ConfigurationStatusResult` has 57 flat fields and [`compile_configuration_warnings`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/configuration/status.py#L8-L27) takes 17 keyword-only arguments.

### 6. AWS Adapters

- **Verdict**: *Already appropriately simple; minor signature inconsistencies.*
- **Analysis**:
  - [`aws/client_factory.py`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/aws/client_factory.py) and [`aws/context.py`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/aws/context.py) are clean, focused, and effective.
  - The individual adapters (`cloudformation.py`, `codepipeline.py`, `s3.py`, `codecommit.py`) remain thin boto3 adapters returning structured result models.
  - Minor blemish: some adapter functions accept dual signatures `(factory: AwsClientFactory | None = None, client: Any | None = None)`, while others take only `client`. Standardizing on passing the resolved boto3 client directly would simplify the adapters.

### 7. CLI Handlers

- **Verdict**: *Too procedural; redundant layer.*
- **Analysis**:
  - `src/lza_workbench/cli/commands/` contains 19 separate files whose functions largely do nothing more than unpack CLI arguments, call the corresponding workflow, and call a local `render_*` function.
  - Because Typer already maps functions to CLI commands, having `cli/main.py` -> `cli/commands/foo.py` -> `workflows/foo.py` creates excessive boilerplate without real encapsulation.

### 8. Workflows Layer

- **Verdict**: *Too fragmented; represents an artificial architectural division.*
- **Analysis**:
  - Having a top-level `workflows/` directory containing 19 one-off procedural files breaks feature cohesion.
  - For example, installer logic is split between `src/lza_workbench/installer/` and `src/lza_workbench/workflows/installer_*.py`. If a developer wants to understand installer deployment, they must jump between `installer/deployment.py`, `installer/parameters.py`, `installer/templates.py`, `installer/state.py`, `workflows/installer_deploy.py`, and `cli/commands/installer_deploy.py`.

---

## Detailed Evaluation of Significant Potential Refactors

### Refactor 1: Polymorphic `ConfigurationRepository` Strategy

1. **Concrete current problem**: Procedural branching across 4 repository types (S3, CodeCommit, CodeConnections, Git) resulting in bloated, unmaintainable DTOs and duplicate dispatch logic.
2. **Evidence from the code**:
   - `ConfigPushResult` ([`workflows/config_push.py:46-73`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/config_push.py#L46-L73)) defines fields for both S3 (`zip_path`, `s3_bucket`, `s3_key`, `diff_result`) and Git (`git_remote`, `git_branch`, `git_commit`), with most set to `None`.
   - `ConfigurationStatusResult` ([`workflows/status_config.py:35-95`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/status_config.py#L35-L95)) contains 57 flat fields spanning S3, CodeCommit, and CodeConnections.
   - `_handle_s3_push` vs `_handle_git_push` switch in `workflows/config_push.py:101-125`.
   - `_handle_s3_pull` vs `_handle_git_pull` switch in `workflows/config_pull.py:100-130`.
3. **Why the existing design is insufficient**: Adding a new source (e.g. OCI registry or Gitlab) requires adding fields to every status/push/pull DTO and adding branches across 4 different files.
4. **Proposed alternative**: Introduce a `ConfigRepository` protocol or abstract base class with concrete implementations:
   - `S3ConfigRepository`
   - `GitConfigRepository` (specialized by provider: CodeCommit, CodeConnection, standard Git)
   Each repository implements:
   - `inspect_status() -> RepoStatus`
   - `push(dry_run=False, force=False) -> RepoSyncResult`
   - `pull(dry_run=False, force=False) -> RepoSyncResult`
5. **Simplification / maintainability gain**: Eliminates ~400 lines of branchy glue; replaces 57-field DTO with focused, typed status objects (`S3RepoStatus`, `GitRepoStatus`); simplifies Web GUI rendering because the frontend inspects polymorphic repository objects rather than checking if 20 S3 fields are null.
6. **Cost / risk**: Medium. Touches `config_push`, `config_pull`, and `status_config`.
7. **Recommendation**: **Yes, highly recommended before Web GUI configuration work.**

---

### Refactor 2: Rich `Workspace` Domain Object

1. **Concrete current problem**: `WorkspaceContext` is an anemic data holder. Common path resolution, configuration lookup, and state mutations are duplicated across all workflows.
2. **Evidence from the code**:
   - Every workflow repeats: `config_dir = workspace_dir / config.configuration.local_path`.
   - Workflows duplicate: `zip_path = workspace_dir / CONFIG_ARCHIVE_FILENAME`.
   - State recording is scattered across 4 different modules calling `load_workspace_state` and `write_workspace_state`.
3. **Why the existing design is insufficient**: Callers must know internal path conventions and state serialization details, leading to inconsistency (e.g. hardcoding `"aws-accelerator-config"` vs reading `config.configuration.local_path`).
4. **Proposed alternative**: Upgrade `WorkspaceContext` to a `Workspace` domain model:

   ```python
   class Workspace:
       workspace_dir: Path
       config: WorkspaceConfig
       state: WorkspaceState
       readiness: WorkspaceReadinessLevel

       @property
       def config_dir(self) -> Path: ...
       @property
       def installer_template_dir(self) -> Path: ...
       def update_state(self, **mutations) -> None: ...
       def save_config(self) -> None: ...
   ```

5. **Simplification / maintainability gain**: Centralizes filesystem conventions, guarantees atomic state saves, and removes repetitive path arithmetic from 15+ workflow files.
6. **Cost / risk**: Low. It is additive and can be introduced incrementally without breaking functional boundaries.
7. **Recommendation**: **Yes, recommended immediately.**

---

### Refactor 3: Remove Workflow Procedural Callback Leaking (`prompter`, `confirm_callback`)

1. **Concrete current problem**: Workflows embed CLI-specific interaction patterns by requiring callers to pass interactive callback closures.
2. **Evidence from the code**:
   - `initialize_installer_workflow` ([`workflows/installer_init.py:49`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/installer_init.py#L49)) accepts `prompter: Callable[[str, str | None], str] | None`.
   - `push_configuration_workflow` ([`workflows/config_push.py:83`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/config_push.py#L83)) accepts `confirm_callback: Callable[[str], bool] | None`.
   - `pull_configuration_workflow` ([`workflows/config_pull.py:90`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/config_pull.py#L90)) accepts `confirm_callback: Callable[[str], bool] | None`.
3. **Why the existing design is insufficient**: In a Web API or GUI, interactions cannot pause in the middle of a workflow to ask a terminal question. Web workflows require explicit preview/plan phases followed by an execution phase.
4. **Proposed alternative**:
   - For `installer_init`: Split into `get_installer_parameters_schema(workspace)` (used by CLI prompter or Web form) and `save_installer_parameters(workspace, parameters)`.
   - For `config_push`/`config_pull`: Replace `confirm_callback` with a pre-flight inspection or explicit `require_force_reason` check. If safety checks fail without `--force`, raise a structured `UnsafeOperationError` detailing why confirmation is needed, allowing CLI or Web to handle confirmation *before* calling apply.
5. **Simplification / maintainability gain**: Pure, re-entrant workflows that are genuinely reusable across CLI, Web, and background workers.
6. **Cost / risk**: Low. Touches only 3 workflows.
7. **Recommendation**: **Yes, recommended before Web GUI integration.**

---

### Refactor 4: Disentangle `pipeline_watch` Polling Loop from Observation

1. **Concrete current problem**: `watch_pipeline_workflow` is a monolithic synchronous loop containing `time.sleep()`.
2. **Evidence from the code**:
   - [`workflows/pipeline_watch.py:193-293`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/pipeline_watch.py#L193-L293): `while True: ... time.sleep(interval)`.
3. **Why the existing design is insufficient**: A Web backend cannot run this workflow in an HTTP request thread without blocking workers or hitting gateway timeouts. A Web GUI needs to query pipeline status on-demand or stream updates via SSE/WebSockets.
4. **Proposed alternative**:
   - Extract `get_pipeline_execution_snapshot(client, pipeline_name, execution_id) -> PipelineExecutionSnapshot`.
   - Keep `watch_pipeline_workflow` (or a CLI watcher class) as a simple consumer that calls the snapshot in a loop.
   - The Web backend can directly expose the snapshot via `GET /api/pipeline/{name}/status`, letting frontend client polling or an async task runner own timing.
5. **Simplification / maintainability gain**: Eliminates thread blocking in headless environments and provides a clean building block for both CLI watch and Web dashboards.
6. **Cost / risk**: Low. Pure extraction of the loop body.
7. **Recommendation**: **Yes, recommended before Web GUI pipeline monitoring.**

---

### Refactor 5: Consolidate `workflows/` into Owning Feature Packages

1. **Concrete current problem**: Artificial split between feature modules (e.g. `src/lza_workbench/installer/`) and workflows (e.g. `src/lza_workbench/workflows/installer_*.py`).
2. **Evidence from the code**:
   - 19 files in `workflows/` mirroring 19 files in `cli/commands/` and 4 feature folders.
   - Arbitrary separation: why are `installer/planning.py` and `workflows/installer_plan.py` in separate top-level packages?
   - Forwarding alias files (`workflows/config_download.py`, `workflows/config_upload.py`).
3. **Why the existing design is insufficient**: It inflates the module count (95 Python files for a focused CLI utility) and forces artificial import rules rather than grouping related domain logic together.
4. **Proposed alternative**: Co-locate workflows inside feature packages:
   - `installer/` owns its models, adapters, and use cases (`init`, `plan`, `deploy`, `status`).
   - `configuration/` owns its models, repository providers, and use cases (`init`, `pull`, `push`, `status`).
   - `pipeline/` owns resolution, failure diagnostics, status snapshots, and execution monitoring.
   - Delete `workflows/config_download.py` and `workflows/config_upload.py` (aliases belong strictly in CLI registration).
5. **Simplification / maintainability gain**: Removes an entire artificial layer (19 files), reduces file count by ~25%, and makes features self-contained.
6. **Cost / risk**: Medium. Involves moving files and updating import paths across tests.
7. **Recommendation**: **Worthwhile, but can be done after or alongside Web GUI foundation.**

---

## Counterfactual Architecture

If designing LZA Workbench from scratch today with the same feature set and the planned Web GUI, the architecture would look like this:

```text
src/lza_workbench/
├── app.py                     # High-level application facade (or service registry)
├── errors.py                  # Domain error hierarchy
├── domain/                    # Pure domain models and policy (no AWS/CLI/Web dependencies)
│   ├── workspace.py           # Workspace, WorkspaceConfig, WorkspaceState, readiness
│   ├── pipeline.py            # PipelineStage, Action, FailureDiagnostic, root cause rules
│   └── repository.py          # ConfigRepository protocol, S3/Git repo strategies
├── services/                  # Reusable use cases / operations
│   ├── workspace_service.py   # Init, import, bootstrap
│   ├── installer_service.py   # Parameters resolution, plan, deploy, import
│   ├── config_service.py      # Sync (pull/push), template render, drift
│   └── pipeline_service.py    # Start, snapshot, diagnostics, watcher
├── infra/                     # External adapters
│   ├── aws/
│   │   ├── client_factory.py  # Centralized boto3 session/auth
│   │   ├── cloudformation.py  # CFN stack operations
│   │   ├── codepipeline.py    # Pipeline execution & state queries
│   │   ├── codebuild.py       # Build log fetching
│   │   └── s3.py              # Bucket and object operations
│   └── git/                   # Subprocess git wrapper
├── cli/                       # CLI presentation (Typer + Rich)
│   ├── main.py                # Command tree and routing
│   └── renderers/             # Tables, panels, formatters
└── web/                       # Web GUI (FastAPI)
    ├── api/                   # REST / JSON routes calling services
    └── server.py              # Server lifecycle and static assets
```

### Meaningful Differences from Current Implementation

| Dimension | Current Architecture | Counterfactual Architecture |
| :--- | :--- | :--- |
| **Use Case Organization** | 19 flat procedural workflow files in `src/lza_workbench/workflows/` | Cohesive service classes (`InstallerService`, `ConfigService`, etc.) in `services/` |
| **Repository Modeling** | Procedural branching (`if s3 / elif git`) with 57-field flat DTOs | Polymorphic `ConfigRepository` strategies (`S3Repository`, `GitRepository`) |
| **Workspace Handling** | Passive dataclass tuple `(workspace_dir, config, state)` | Active `Workspace` domain object managing paths, config, and state persistence |
| **Long-running Tasks** | Blocking `time.sleep()` loop inside workflow | Non-blocking snapshot query in service; loop owned by CLI monitor or Web async poller |
| **Interface Coupling** | Prompt and confirmation callbacks passed into workflows | Workflows take resolved inputs; interface owns prompts and confirmation |
| **File / Module Count** | ~95 Python files across 8 packages with 1:1 mirroring | ~40 Python files with clear domain/service/adapter boundaries |

---

## Conclusion

**Current architecture is sound but has several worthwhile structural refactors.**

The current architecture is not fundamentally broken:

- It correctly enforces external AWS authentication and local workspace isolation.
- It cleanly isolates AWS SDK initialization in `AwsClientFactory`.
- The recently refactored `status_root` workflow demonstrates that high-level observability can be unified without leaky dependencies.
- It avoids framework bloat and maintains high test performance.

However, prior reviews were **overly conservative** in preserving the procedural function-heavy convention and resisting object-oriented abstractions. Before building out the Web GUI, the following targeted refactors are strongly recommended to prevent technical debt from compounding:

1. **Adopt a polymorphic `ConfigRepository` provider abstraction** to eliminate procedural S3/Git branching and collapse the 57-field `ConfigurationStatusResult`.
2. **Promote `WorkspaceContext` to an active `Workspace` object** that encapsulates child paths and state persistence.
3. **Remove interactive `prompter` and `confirm_callback` closures from workflows**, replacing them with explicit preview/plan and apply phases.
4. **Decompose `pipeline_watch_workflow`** so that single-pass state inspection is separated from the blocking terminal sleep loop.
