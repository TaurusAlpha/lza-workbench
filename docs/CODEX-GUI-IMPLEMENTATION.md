# LZA Workbench GUI-First Work Plan

Status: the architecture audit, project-direction update, and required pre-Web workflow refactors
are complete. Web stack selection and the first read-only vertical slice are next.

1. **Audit the current architecture — complete**
   - Review workflows, CLI handlers, feature packages, and AWS adapters.
   - Identify CLI leakage, duplicated orchestration, oversized responsibilities, inconsistent workflow inputs/results, and unnecessary abstractions.
   - Evaluate classes/OOP, DTOs, protocols, plan/apply patterns, and other design patterns only where they clearly simplify the code.
   - Preserve `web/cli -> workflows -> features/AWS`.

2. **Implement the required reusable workflow fixes — complete**
   - Complete only the approved pre-Web refactors in `GEMINI-PLAN.MD`.
   - Ensure important workflows can be called independently from CLI or Web.
   - Remove Typer, Rich, prompting, and terminal rendering from reusable logic.
   - Introduce structured request/result models only where current signatures are genuinely cumbersome.
   - Keep models close to the workflow or feature that owns them; avoid a generic DTO/schema dumping ground.

3. **Update project direction — complete**
   - Web GUI is the primary planned interactive interface; CLI remains supported for automation, debugging, SSH, and advanced use.
   - Web Interface work is active in `TODO.md`.
   - Keep multi-user/server mode out of scope for now.
   - Preserve external AWS authentication and local customer workspaces.

4. **Choose the minimal Web stack**
   - Prefer a local Python backend.
   - FastAPI is the leading candidate.
   - Choose SPA vs server-rendered/HTMX only after confirming actual UI complexity.
   - Do not introduce frontend or backend abstractions before they are needed.

5. **Implement the first read-only vertical slice**
   - Add a local Web server entrypoint, likely `lza ui`.
   - Open/select an existing workspace.
   - Reuse existing workspace loading and `lza status` workflows.
   - Build an Overview dashboard showing:
     - workspace identity;
     - AWS availability/account;
     - installer state;
     - configuration source/state;
     - installer/configuration pipeline state;
     - overall health.

6. **Add detailed read-only views**
   - Installer status/details.
   - Configuration status/details.
   - Pipeline executions and failure diagnostics.
   - Configuration diff when that workflow exists.
   - Consume structured workflow results directly; never parse CLI output.

7. **Add configuration mutation workflows**
   - `config push`
   - `config deploy`
   - pipeline monitoring after deployment
   - Use **plan/review/confirm/execute** where safety or useful preview justifies it.
   - Do not force every workflow into a universal plan/apply abstraction.

8. **Add pipeline operations**
   - pipeline start
   - pipeline watch
   - live execution progress
   - Reuse existing monitoring logic.
   - Introduce a shared event/progress abstraction only if multiple Web workflows demonstrate the same need.

9. **Add installer and bootstrap operations**
   - installer plan
   - installer deploy
   - bootstrap
   - Keep AWS mutation and business policy inside existing workflows/features.
   - Web handlers remain thin adapters.

10. **Add workspace setup UX**
   - `init`
   - `import`
   - `installer init`
   - `config init`
   - Convert CLI prompting into explicit Web forms backed by existing discovery/validation logic.

11. **Add structured configuration editing later**
   - Start with safe, explicitly supported workspace settings.
   - Do not automatically expose the entire Pydantic schema as a generated editor.
   - Add LZA configuration editing only after the relevant version-aware models and mutation rules are defined. 

12. **Simplify the CLI**
   - Keep persistent configuration in `lza-workspace.yaml`.
   - Keep CLI flags mainly for transient execution behavior such as `--dry-run`, `--force`, `--verbose`, workspace selection, and automation needs.
   - Remove obsolete CLI-specific abstractions when they no longer provide value.
   - Do not require every GUI action to have a dedicated CLI command.

13. **Continuously review and refactor**
   - Before exposing each major feature in Web, inspect its underlying implementation.
   - Refactor code that has become difficult to reuse, test, or understand.
   - Prefer simple functions/modules by default.
   - Introduce classes, protocols, DTOs, event models, or other patterns only when they reduce real complexity.
   - Since the project is still in development, do not preserve weak internal designs solely for compatibility.

14. **Validate each phase**
   - Run `uv run ruff check . --fix`.
   - Run focused tests for changed workflows/interfaces.
   - Periodically verify architecture boundaries:
     ```text
     web/cli -> workflows -> features/AWS
     ```
   - Keep `pyproject.toml`, `TODO.md`, `PROJECT.md`, `README.md`, and `docs/DONE.md` aligned with delivered behavior.
