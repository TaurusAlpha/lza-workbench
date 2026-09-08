# LZA Workbench — Pre-GUI Architecture Action Plan

**Purpose of this document.** This is a single, consolidated action plan synthesized from five prior review documents:

- `CODEX-INDEPENDENT.md` (Codex, run inside an existing/"dirty" conversation)
- `CODEX-INDEPENDENT-V2.md` (Codex, fresh conversation, second pass)
- `GEMINI-INDEPENDENT.md` (Gemini, fresh conversation)
- `CODEX-VERDICT.md` (Codex's cross-review of both Codex passes and Gemini)
- `GEMINI-VERDICT.md` (Gemini's cross-review of both Codex passes and its own review)

It is meant to be handed to any coding model (or engineer) as the single source of truth for what to build, in what order, and — just as importantly — what **not** to build. Where the two verdicts disagreed, this document states both positions and gives an explicit resolution so an implementer doesn't have to adjudicate.

**Headline conclusion (unanimous across all five documents):** The architecture is fundamentally sound. `interfaces -> workflows -> feature policy/AWS adapters` is the right shape and should be kept. This is **not** a rewrite. It is a set of targeted, sequenced refactors, each timed to land just before the GUI feature that would otherwise expose or duplicate the weak contract it fixes.

---

## 0. Non-negotiable ground rules (things NOT to do)

Every reviewer, on every pass, converged on rejecting these patterns. If any implementation of an item below drifts toward one of these, stop and reconsider:

1. **No general procedural→OOP conversion.** Do not turn workflows into `WorkspaceService`, `InstallerService`, `ConfigService` classes. Pure transformations (template rendering, archive diffing, parameter encoding, diagnostic recognition, version mapping) stay as functions.
2. **No generic `ConfigRepository` hierarchy preemptively.** This is a threshold rule, not a permanent ban: start with discriminated data models and explicit S3/Git behavior (there are really only **two** transport families today — S3 archive sync, and Git sync, which already covers CodeCommit, CodeConnections, and plain Git through one branch). Introduce a narrow provider abstraction later only when repeated behavior across real use cases (push/pull/status/diff all needing the same operations) demonstrates that an abstraction would actually simplify the implementation — not because "providers" sounds like the right shape in the abstract.
3. **No ActiveRecord-style `Workspace` domain object** that owns both the in-memory model and disk persistence (e.g. `workspace.save_config()`, `workspace.update_state(**mutations)`). This would blur the (good, deliberate) separation between declarative `lza-workspace.yaml` config and operational `.lza/state.json` runtime state, and would hide I/O behind method calls.
4. **No monolithic `WorkspaceObserver` / global `WorkspaceSnapshot`** that eagerly loads installer + both pipelines + all configuration remotes for every status request. Build small, reusable, typed observation functions instead. Only introduce a shared/memoized observer later, and only if a specific Web route is demonstrably making the same AWS calls more than once in one request.
5. **No repository-wide package reshuffle right now** (e.g. moving all of `workflows/` into `services/` or into per-feature `application/` subpackages in one pass). This is pure churn with no behavior change and will conflict with concurrent GUI work. Do it feature-by-feature, later, opportunistically.
6. **No generic approval/confirmation engine or universal workflow/orchestration framework.** Each mutating flow (config sync, installer init, workspace import) gets its own explicit prepare/confirm/apply shape — not a shared "approval" abstraction.
7. **No class wrappers around every boto3 service "for consistency."** AWS adapters stay thin, function-based, and become more consistent only in their **return types** (typed results instead of `dict[str, Any]`), not in becoming classes.

---

## 1. Where the two verdicts disagreed, and how to resolve it

Both cross-reviews (Codex-Verdict, Gemini-Verdict) independently arrived at almost the same list of confirmed findings. There are exactly two real disagreements:

### Disagreement A — Is `WorkspaceReadinessLevel → WorkspaceAssessment` a hard prerequisite for the *first* GUI slice, or just for later workspace/setup features?

- **Gemini-Verdict:** Treat it as a Phase-1 prerequisite, before any GUI work starts, because a GUI needs to show independent facet health (Configuration: Valid / Installer: Incomplete / AWS Stack: Active) and a single ordinal enum can't express that.
- **Codex-Verdict:** The first read-only overview will be built on `RootStatusResult`, which already reports component status separately and doesn't expose the ordinal enum. So this can wait until it's about to become a *visible contract* — i.e. before a setup/import wizard, a command-availability system, a doctor/remediation view, or any screen that would literally print "IMPORTED / CONFIGURED / DEPLOYED" as one label.

**Resolution used in this plan:** Do the capability-assessment refactor early (Phase 1, alongside/just after the first read-only slice, not strictly blocking it) — it's low-risk, self-contained, and every reviewer agrees the current ordinal model is actively wrong (an imported workspace with incomplete installer settings gets ranked *below* "configured," and "deployed" is inferred from stale cached state rather than live AWS). Getting it right before more code depends on the old enum avoids rework. If timeline pressure exists, it is acceptable to build the first read-only slice against `RootStatusResult` in parallel and land the capability assessment before the *second* GUI slice — but no later than that.

### Disagreement B — Should a shared "status observation" layer be built at all before GUI status work?

- **Codex-Verdict (Codex V2 original position):** A request-scoped `WorkspaceObserver` producing one `WorkspaceSnapshot` is potentially useful; introduce it once multiple Web routes demonstrably need the same live observations.
- **Gemini-Verdict:** Reject the observer outright — forcing all status views through one monolithic snapshot would make cheap, targeted CLI checks (e.g. "is local config drifted?") pay for unrelated AWS calls, or require a memoization/caching layer that doesn't currently exist.

**Resolution used in this plan:** Follow Ground Rule 4 above — **do not build a shared observer now.** Extract reusable, narrow, typed observation functions per concern (installer stack observation, pipeline observation, configuration-remote observation) as part of the status refactor in Phase 2. Revisit a shared observer only if, once the Web routes exist, profiling or code review shows the same live AWS calls being duplicated across routes in a single request.

Everything else below reflects genuine consensus.

---

## 2. Sequenced action items

Each item lists: the concrete problem, the target design, why it must land before a specific GUI step, and what must be preserved (regression risk).

**On ordering:** the only hard rule is that each refactor must precede the GUI feature that depends on the weak contract it fixes — these are feature-gated, not globally sequenced. Phase 1 comes first (it's a foundational, cross-cutting model). Within Phase 2, the item order below follows the currently-planned GUI build order (Configuration Status → Installer Settings → Config Sync → Pipeline Monitoring → Bootstrap → Workspace Import) and is a *default*, not a dependency chain. If GUI priorities change — e.g. Pipeline Monitoring gets built before Installer Settings — reorder items 2.1–2.6 to match; there is no architectural reason 2.2 must land before 2.4. Do not treat this list as a linear migration program.

### Phase 0 — Do this anytime, no GUI dependency, near-zero risk - **COMPLETE**

**0.1 Delete zero-value alias modules.**

- Problem: `workflows/config_download.py` and `workflows/config_upload.py` exist purely as compatibility re-exports; `cli/commands/config_download.py` / `config_upload.py` similarly just forward to sibling command handlers.
- Action: Remove these alias/wrapper modules. Register `download`/`upload` as alternate command names pointing at the same handler directly in CLI registration, instead of maintaining separate wrapper files and result-type aliases.
- Risk: Negligible — pure deletion once call sites are confirmed migrated. No behavior change.

---

### Phase 1 — Before / alongside the first read-only GUI overview - **COMPLETE**

**1.1 Replace ordinal `WorkspaceReadinessLevel` with a multi-dimensional `WorkspaceAssessment`.**

- Problem: `evaluate_workspace_readiness()` assigns a single ordinal enum (`UNINITIALIZED → CORE_CONFIGURED → IMPORTED → CONFIGURED → DEPLOYED`) by checking things in a fixed sequence. Concretely: an imported workspace with incomplete installer settings is ranked *below* `CONFIGURED`; "imported" is inferred from config-directory presence rather than from `state.imported`; "deployed" is inferred from a cached installer stack ID rather than live AWS state. Commands then gate on `readiness >= X`, an ordinal comparison over what are actually independent facts.
- Target design: A `WorkspaceAssessment` value object exposing explicit boolean/structured capabilities, e.g. `metadata_valid`, `configuration_present`, `installer_configured`, `installer_recorded_deployed`, `imported` (read from `state.imported`, not inferred). Commands declare which capabilities they require instead of comparing an ordinal minimum. Keep this as one structured object — do not degrade into a scatter of ad hoc booleans checked independently across the codebase.
- **Guard migration is part of this item, not an afterthought.** Today's command guards are ordinal comparisons (`context.readiness >= WorkspaceReadinessLevel.CONFIGURED`) scattered across ~19 CLI entry points. Swapping the enum for capability flags without a central mechanism invites silent regressions — a command that previously required `readiness >= CONFIGURED` might get migrated to check only `installer_configured` when it actually also depended on `configuration_present`. Before removing the enum:
  1. Introduce a single `require_capabilities(*capabilities)` guard (helper or decorator) that all command entry points call.
  2. Build an explicit old-enum → new-capability mapping table for every existing gate, and verify each mapped guard against the command's current behavior before cutting over.
  3. Only delete `WorkspaceReadinessLevel` once every call site has migrated through the mapping table, not ad hoc.
- Preserve: existing CLI error messages / exit behavior for commands that currently gate on readiness.
- Blocks: nothing about the very first read-only overview (which uses `RootStatusResult`, not the enum) — but see Disagreement A above. Must land before any setup/import wizard, "doctor"/remediation view, or any UI element that would otherwise expose the old enum as a single status label.
- Risk: **Moderate** (raised from an initial "low–moderate" data-model framing — the real risk is in the guard migration across many call sites, not the new type itself).

---

### Phase 2 — Before each specific GUI feature, in this order

**2.1 Before "Configuration Status & Details" — replace the flat `ConfigurationStatusResult`.**

- Problem: `ConfigurationStatusResult` is a ~57-field flat model mixing workspace identity, local filesystem/Git state, S3 details, CodeCommit details, CodeConnections details, pipeline status, persisted runtime metadata, and warnings — most fields are `None`/invalid for any given repository type. `compile_configuration_warnings` takes 17 keyword-only arguments.
- Target design: Keep one `ConfigurationStatusResult`, but compose it from focused sections:
  - workspace/local configuration summary;
  - local Git summary;
  - **one discriminated repository observation** — `S3ConfigurationRepositoryStatus`, `CodeCommitConfigurationRepositoryStatus`, `CodeConnectionConfigurationRepositoryStatus`, `GitConfigurationRepositoryStatus` — as ordinary frozen dataclasses, not a class hierarchy or protocol;
  - configuration-pipeline summary;
  - persisted synchronization metadata and warnings.
- Do **not** build a generic `ConfigRepository` OOP strategy interface here (see Ground Rule 2). This is a data-shape fix, not a polymorphism exercise.
- Also fold in: remove the untyped dictionary-conversion wrapper in the CodeCommit adapter (`inspect_codecommit_config_repository()` currently converts a typed `CodeCommitRepositoryStatus` into a dict for callers) — call the typed inspector directly and consume the typed result in status/bootstrap.
- Preserve: all currently user-visible fields, and the existing fallback-to-recorded-state behavior when live AWS data is unavailable.
- Migrate together: the status CLI renderer and its targeted tests.

**2.2 Before "Installer Settings & Deployment" — canonical installer configuration, parameter codec, and callback removal (one combined refactor).**

*This item absorbs the installer half of what an earlier draft listed as a separate "2.3" callback-removal task. `initialize_installer_workflow` derives and writes parameter defaults directly inside its `prompter` loop, so the codec and the callback removal are the same piece of logic viewed from two angles — splitting them into separate changes means deriving parameter values once inline in the old prompt path and again in the new codec, then reconciling the two. Land them together.*

- Problem (data model): CloudFormation parameters can currently be represented simultaneously in `lza`, `configuration.repository`, `installer.options`, `installer.source_code`, and `installer.template_parameters`. `apply_installer_parameter()` writes to multiple locations for one logical value, and the final parameter builder lets raw `template_parameters` silently overwrite already-derived typed values. This is not cosmetic: it means a GUI edit can appear accepted while a stale shadow value wins at deploy time.
- Problem (interface leakage): `initialize_installer_workflow` accepts `prompter: Callable[[str, str | None], str] | None` and drives an interactive terminal loop, interleaving parameter derivation with prompting. A workflow doesn't become interface-neutral just because its callback type doesn't literally mention Typer — an HTTP request can't pause mid-call to await a terminal prompt, and building the codec without also removing the prompter guarantees the derivation logic gets written twice.
- Target design:
  - Typed workspace installer/configuration settings become the single canonical source.
  - Repository destination values are derived from `configuration.repository`; do not mirror them again inside `InstallerOptionsConfig`.
  - A single stateless `InstallerParameterCodec` (a module of functions, not a stateful class unless it ends up holding a resolved template schema/version) converts canonical typed desired state to/from CloudFormation parameters. All parameter derivation — whether triggered by a CLI prompt loop or a Web form submission — goes through this codec; there is no separate derivation path.
  - Version-specific unknown parameters live in `extra_parameters` and are **not allowed to shadow** known typed parameters.
  - `initialize_installer_workflow` splits into `get_installer_parameters_schema(workspace) -> InstallerForm` (consumable by a CLI prompt loop or a Web form — describes what's needed, using the codec's typed model) and `apply_installer_settings(request) -> ...` (accepts already-resolved values built via the codec, no prompting inside the workflow).
- Preserve: exact deployed-stack import behavior and template-default resolution; add regression coverage before changing the shadowing behavior, since this is the most safety-relevant item in the plan (a wrong parameter value ships to a real CloudFormation deploy).
- This was independently identified as the single most important issue missed by the first review pass — treat it as high priority, and treat it as one atomic change, not two.

**2.3 Before "Configuration Sync & Deployment Actions" — remove interactive callbacks from config push/pull.**

- Problem: `push_configuration_workflow` and `pull_configuration_workflow` accept a synchronous `confirm_callback: Callable[[str], bool] | None` used for destructive-overwrite safety checks (e.g. confirming before overwriting imported S3 content or changed local configuration). Same interface-neutrality problem as 2.2's installer prompter, but this is separate application logic (config sync, not installer settings) and does not share derivation code with the codec — it should stay its own item.
- Target design: replace `confirm_callback` with a prepare/plan step that returns a typed result describing overwrite risk and the affected target (a structured "confirmation required" outcome, not a boolean callback), and an apply step that only proceeds given explicit confirmation or `--force`/confirmed intent. Keep existing `--force` semantics and existing safety messages exactly as they are today.
- Do not build one generic "approval" abstraction shared with 2.2's installer form or with pipeline watch's progress notification (Ground Rule 6) — each gets its own small, explicit typed request/response, because the safety semantics differ.
- Preserve: dry-run purity, imported-workspace S3 overwrite protection, current CLI exit behavior on declined confirmation.
- Note: the pipeline watch progress-notification callback is handled separately under 2.4, as part of decoupling the polling loop from single-pass observation — it is not part of this item.

**2.4 Before "Pipeline Monitoring & Logs" — canonical pipeline models + decouple the watch loop from observation.**

- Problem: The same operational concept (a pipeline execution's stage/action state) has multiple overlapping representations: the AWS adapter's `ActionStateResult`/`StageStateResult`, a near-duplicate `PipelineActionSummary`/`PipelineStageSummary` defined again inside the watch workflow, and callers elsewhere (`failures.py`, `pipeline/state.py`, root status) that fall back to `Iterable[Any]` and `getattr()` because both shapes circulate. Separately, `watch_pipeline_workflow` is a blocking `while True: time.sleep(interval)` loop that also owns retry tolerance, timeout handling, diagnostic enrichment, callbacks, and state persistence all in one place — untenable for a Web server thread over a 15–30 minute pipeline run.
- Target design:
  1. Define one canonical, provider-neutral snapshot in the `pipeline` package: `PipelineActionState`, `PipelineStageState`, and a `PipelineExecutionSnapshot` (or equivalent) wrapper.
  2. The CodePipeline adapter parses boto3 responses directly into these canonical models — no separate near-duplicate models in the watch workflow.
  3. Extract a single-pass `observe_pipeline_execution(...) -> PipelineExecutionSnapshot` function. The CLI watch loop becomes a thin consumer that calls this repeatedly and renders updates; a Web endpoint can call it once per request and let the browser/poller own timing (a background/streaming `PipelineWatcher` object is only justified later, if cancellation/reconnection/SSE become real requirements — don't build it speculatively now).
  4. Keep failure enrichment (`PipelineFailureReport` / `PipelineActionFailure`) as a separate, explicitly-invoked diagnostic step — don't make every snapshot query also fetch CodeBuild logs.
  5. Update `collect_pipeline_action_failures`, root status, watch, and state persistence to consume the canonical typed models instead of `Any`/`getattr`.
- Preserve: execution-identity filtering, `NOT_FOUND` propagation tolerance, timeout semantics, terminal diagnostic enrichment, and exactly what gets persisted to runtime state. This is a medium-risk refactor — treat retry/timeout/diagnostic behavior as must-preserve, not incidental.

**2.5 Before "Bootstrap Resources" — structured bootstrap actions instead of terminal-styled strings.**

- Problem: `BootstrapPlanResult` exposes `actions: list[str]` and `warnings: list[str]`, and the workflow embeds Rich terminal markup directly in those strings (e.g. `"[bold red]MISSING[/bold red]"`). A browser would have to parse or strip terminal markup, and the actual action severity/resource identity is trapped inside prose.
- Target design: A small typed `BootstrapAction` record containing at least: subject/resource, operation or status (`CREATE`, `UPDATE`, `NO_CHANGE`, `MISSING`, `WARNING`), a plain message, and optional severity. Keep `warnings` as plain domain messages. The CLI renderer becomes solely responsible for turning status/severity into Rich styling; the Web layer maps the same status/severity to its own styling.
- Preserve: current action ordering, existing warnings, validation outcomes, and no-recreate behavior for imported resources.

**2.6 Before "Workspace Setup & Import" — split workspace import into request/prepare/apply.**

- Problem: `import_workspace_workflow()` is a large, mixed-responsibility function (~300+ lines, ~14–16 parameters) that validates local configuration, discovers Git provenance, reconstructs metadata, resolves defaults, performs best-effort remote AWS discovery, imports/synchronizes an installer template, validates GitHub access, builds desired configuration/runtime state, generates recommendations, and writes several files — all in one call. A CLI can collect inputs then call it once; a Web setup flow needs to discover inputs, show findings and intended file changes, collect user decisions, and only then mutate — without re-running the whole (expensive, remote-calling) import just to render a review screen.
- Target design:
  - A frozen `ImportWorkspaceRequest` for the current keyword inputs.
  - `prepare_workspace_import(request) -> ImportWorkspacePreparation`: resolved discovery, derived desired config/state, remote observations, affected file paths, and recommendations — no writes.
  - `apply_workspace_import(preparation)`: performs the actual template/config/state writes and installer metadata synchronization.
  - Keep `import_workspace_workflow()` around as a convenience composition of the two, for existing CLI call sites, until they're migrated.
  - Remote installer inspection can stay a private helper inside this workflow for now; only promote it into the installer feature package if/when a second caller genuinely needs the same observation.
- Preserve: exact template/config/state write ordering, and exactly when local metadata is allowed to be written after a remote discovery failure (the current best-effort/repair semantics). This is the highest-risk item in the plan — cover it with real (not mocked-everything) CLI import regression tests before and after.

---

### Phase 3 — Later / opportunistic, not gating any specific GUI step

**3.1 AWS adapter contract cleanup.**

- Standardize on typed observation results instead of raw dictionaries where adapters still return `dict[str, Any]` (e.g. some S3 inspection calls).
- Standardize each adapter function on accepting either a resolved client or a small service object — not both `factory: AwsClientFactory | None` and `client: Any | None` on the same call.
- Consolidate log-cleaning/diagnostic-normalization logic that currently overlaps between the CodeBuild adapter and `pipeline/failures.py` into one place owned by `pipeline` (adapters should stay a thin AWS boundary; diagnostic heuristics belong in `pipeline`).
- Do this as each adapter is touched by the phase-2 work above, not as a standalone project, and definitely not by wrapping every boto3 service in a class (Ground Rule 7).

**3.2 Incremental package relocation — kept separate from behavioral refactors.**

- The global `workflows/` package does weaken feature locality (installer logic is split between `installer/` and `workflows/installer_*.py`, for example), and moving toward `interfaces -> feature application -> domain/ports` is the right long-term direction.
- But do not do this as a repository-wide move, and **do not bundle a file relocation into the same change as a Phase-2 behavioral refactor.** A substantial behavior change (2.2, 2.4, 2.6 especially) plus a package move in one diff stacks four kinds of noise on top of each other — behavior changes, type/model changes, import/package relocation, and test relocation — at exactly the moment you most need a clean diff to verify behavior was preserved.
- Instead: land the Phase-2 refactor inside the existing `workflows/` module first, get it merged with its tests green. Only then, **as a separate, later change**, reconsider whether moving that use case into its owning feature package (e.g. `installer/application/plan.py`) materially improves locality. Perform the move on its own unless relocation is actually necessary to make the refactor itself coherent (rare — most of the items in this plan aren't). If it doesn't clearly pay for itself, it's fine to leave the file where it is.
- Also fold in here: simplify the CLI's forwarding command functions and any workflow-result aliases kept only for command-name synonyms — but only as those specific commands are touched, not as a standalone cleanup pass.

**3.3 Minor `WorkspaceContext` ergonomics (optional, low-risk, additive).**

- If genuinely useful, add a small number of **read-only derived path properties** (e.g. `.config_dir`, `.installer_dir`) to the existing immutable `WorkspaceContext`, or a small immutable `WorkspacePaths` value object.
- Do **not** turn this into a persistence-owning object (Ground Rule 3). State mutation stays in the existing explicit, feature-owned functions (`configuration/state.py`, `installer/state.py`, `pipeline/state.py`) that name exactly which transition occurred — this explicitness is a deliberate strength of the current design, not a gap.

---

## 3. Summary table (for quick reference)

| # | Item | Gate: before... | Risk | Notes |
| --- | ------ | ------------------ | ------ | ------- |
| 0.1 | Delete `config_download`/`config_upload` alias modules | anytime | Trivial | Register aliases directly in CLI |
| 1.1 | Ordinal readiness → `WorkspaceAssessment` capabilities + `require_capabilities()` guard migration | first GUI slice (early, not strictly blocking) | Moderate | See Disagreement A; risk is in the ~19-call-site guard migration, not the new type |
| 2.1 | Discriminated `ConfigurationStatusResult` | Configuration Status & Details view | Moderate | Frozen dataclasses, no strategy interface |
| 2.2 | Canonical installer config + `InstallerParameterCodec` + installer `prompter` removal (one combined refactor) | Installer Settings & Deployment | High | Most safety-relevant item; codec and callback removal must land together |
| 2.3 | Remove `confirm_callback` from config push/pull | Configuration Sync & Deployment Actions | Moderate | Explicit prepare/apply, no shared approval engine; independent of 2.2 |
| 2.4 | Canonical pipeline snapshot + decouple watch loop | Pipeline Monitoring & Logs | Moderate–high | Preserve retry/timeout/diagnostic semantics |
| 2.5 | Typed `BootstrapAction` (no Rich markup) | Bootstrap Resources | Low–moderate | Pure data-shape fix |
| 2.6 | `ImportWorkspaceRequest` + prepare/apply split | Workspace Setup & Import | High | Highest-risk item; needs real regression coverage |
| 3.1 | AWS adapter typed-result cleanup | as adapters are touched | Low–moderate | No adapter classes |
| 3.2 | Move a use case into its feature package | only after its refactor above is merged and green, as its own change | Medium | Never bundled with the behavioral refactor; skip if it doesn't clearly pay for itself |
| 3.3 | Optional read-only path properties on `WorkspaceContext` | opportunistic | Low | Not a persistence-owning object |

**On sequencing (reiterated from §2):** the "Gate" column above states each item's dependency, not a fixed calendar order. Reorder Phase-2 rows (2.1–2.6) freely if actual GUI build priority changes — the only constraint is refactor-before-its-own-feature.

---

## 4. How to use this document

1. Work Phase 0 → Phase 1 → Phase 2 → Phase 3 in that order. Within Phase 2, follow the listed order by default (it mirrors the currently-planned GUI build order), but reorder freely if actual GUI priorities change — the binding rule is always "refactor before its own feature," not "refactor in list order."
2. Before starting any item, re-read its "Preserve" bullet — that's the regression contract, and for 2.2 and 2.6 in particular it's more important than the refactor itself.
3. Don't reach for anything listed under Ground Rules (§0) even if it seems like a natural extension of an item below — those were explicitly evaluated and rejected across all five source reviews.
4. If a future reviewer proposes deviating from this plan, check first whether the proposal falls into one of the rejected patterns in §0 before adopting it.
