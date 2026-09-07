# Plan: Transition to Web GUI-First Architecture with Secondary CLI

Transition LZA Workbench from a CLI-heavy application into a Web GUI-first workbench with a streamlined, secondary CLI. The goal is to eliminate option sprawl, simplify internal patterns (OOP/Domain Workflows), and allow both interfaces to share the same underlying engine without duplication.

---

## User Review Required

> [!IMPORTANT]
> **Tech Stack Selection for Local Web GUI:**
> We recommend a lightweight Python backend running locally (`FastAPI` + `Uvicorn`) bundled into `lza ui`, paired with either:
> 1. **Single-Page Application (SPA):** React/Vite or Vue frontend embedded or served locally.
> 2. **Modern Server-Driven UI:** FastAPI + Jinja2 + HTMX + Tailwind (no separate Node/JS build toolchain, 100% Python-packaged).

---

## Key Refactoring & Architectural Shifts

1. **Declarative State over Command Options:**
   - Operational workflows (`deploy`, `push`, `pull`, `pipeline`) will read their domain settings strictly from `lza-workspace.yaml`.
   - Domain-specific CLI flags will be pruned; CLI commands retain only execution flags (`--dry-run`, `--force`, `--verbose`, `--workspace-dir`).
2. **Standardized Two-Phase Workflows (`plan` & `apply`):**
   - Eliminate terminal prompts (`typer.confirm`, `prompter` callbacks) from workflows.
   - Workflows expose `plan()` (pure inspection, diffs, schema validation) and `apply()` (mutation with event-streaming callback).
3. **Pydantic Request DTOs:**
   - Workflows take strongly typed Pydantic models for input instead of 10+ loose keyword arguments.

---

## Step-by-Step Implementation Plan

### Phase 1: Workflow Decoupling & Parameter Simplification
Refactor workflows so they no longer rely on CLI prompting or dozens of exploded parameters.

- **Step 1.1: Remove Prompter Callbacks from Workflows**
  - Refactor [`initialize_installer_workflow`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/installer_init.py) and related workflows to remove the `prompter: Callable` argument.
  - Separate missing parameter discovery from interactive prompt collection.
- **Step 1.2: Introduce Unified Request DTOs**
  - Define explicit Pydantic request models in `lza_workbench/workflows/schemas.py` (e.g. `WorkspaceInitRequest`, `InstallerInitRequest`).
  - Update workflow signatures to accept these DTOs and return structured result objects.
- **Step 1.3: Prune CLI Operational Options**
  - Refactor [`lza_workbench/cli/commands/`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/cli/commands/) and [`lza_workbench/cli/params.py`](file:///Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/cli/params.py).
  - Commands read target configuration from `lza-workspace.yaml`; CLI flags are limited to runtime execution modifiers.

### Phase 2: Standardize Two-Phase Workflow Pattern (Plan & Apply)
Ensure all mutating operations support inspection before execution, enabling both Rich CLI tables and Web UI modals/previews.

- **Step 2.1: Enforce Two-Phase Lifecycle across Workflows**
  - `installer_deploy`: Already has `prepare_installer_deployment` and `apply_installer_deployment`.
  - Standardize `config_deploy`, `config_push`, and `workspace_init` to follow the same pattern (`prepare_*` / `apply_*`).
- **Step 2.2: Standardize Event Streaming Callbacks**
  - Standardize progress events (CloudFormation resource events, CodePipeline execution stages, git push/pull output) via a unified event callback `Callable[[WorkflowEvent], None]`.
  - Enables CLI to print Rich spinners/tables and Web GUI to stream Server-Sent Events (SSE).

### Phase 3: Web GUI Backend & Server Command (`lza ui`)
Provide a lightweight local HTTP server exposing workspace management and workflow execution.

- **Step 3.1: Add Server Dependencies**
  - Add `fastapi` and `uvicorn` to `pyproject.toml`.
- **Step 3.2: Implement Local API Routes (`src/lza_workbench/server/`)**
  - `/api/workspaces`: List local workspaces, load `lza-workspace.yaml`, validate schema, and save modifications.
  - `/api/workflows/{name}/plan`: Run the `prepare_*` workflow phase and return JSON diff/status.
  - `/api/workflows/{name}/apply`: Run the `apply_*` workflow phase and stream real-time events via SSE.
  - `/api/status`: Overall workspace readiness and live AWS health.
- **Step 3.3: Add `lza ui` Command**
  - Add `lza ui [--port 8000] [--no-browser]` to launch the local server and open the browser.

### Phase 4: Web GUI Frontend Implementation
Deliver the primary visual interface for managing workspaces and operations.

- **Step 4.1: Workspace Dashboard & Health**
  - Visual summary of workspace identity, AWS account/profile, LZA version, and readiness level.
- **Step 4.2: Visual Configuration Editor**
  - Form-based editor for `lza-workspace.yaml` (backed by Pydantic JSON schema).
  - Eliminates the need to remember complex CLI parameters or manual YAML editing mistakes.
- **Step 4.3: Plan & Deploy Console**
  - Visual plan inspector showing parameter diffs and CloudFormation actions.
  - One-click deploy button with real-time streaming progress logs and stage progression.
- **Step 4.4: Configuration Diff & Pipeline Monitor**
  - Visual diff viewer (local `aws-accelerator-config` vs remote S3/CodeCommit/Git).
  - Real-time pipeline stage monitor for `lza pipeline watch`.

### Phase 5: Verification and Clean-up
- Run `uv run ruff check . --fix`.
- Run `uv run pytest tests/test_package.py` to ensure architectural boundaries remain clean (`server` and `cli` import `workflows`, but `workflows` never import `server` or `cli`).
- Test `lza ui` and verify CLI parity across core commands.

---

## Verification Plan

### Automated Tests
- `uv run pytest tests/test_package.py`: Verify layer boundaries (`server` and `cli` depend only on `workflows`).
- Run core unit tests on workflow request DTOs and schema validations.

### Manual Verification
1. Launch `lza ui` in a test workspace; verify browser opens and loads workspace state.
2. Edit configuration via GUI; verify `lza-workspace.yaml` updates cleanly.
3. Trigger a plan and deploy via GUI; verify SSE live stream renders progress.
4. Execute corresponding CLI command (e.g. `lza installer plan`) and verify identical planning outcome.
