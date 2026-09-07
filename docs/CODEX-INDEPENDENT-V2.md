# Verdict

**Current architecture is sound but has several worthwhile structural refactors.**

The existing layering has successfully separated terminal presentation from most business logic, centralized AWS session creation, and protected declarative configuration from runtime metadata. However, previous reviews were somewhat conservative: the enforced package direction is clean at the import level, but it has also produced a large orchestration bucket, duplicated representations, callback-driven “interface-neutral” workflows, and several oversized procedural use cases.

No broad object-oriented rewrite is justified. The best refactors are concentrated around canonical state, capability modeling, status observations, provider behavior, and long-running operations.

## Area assessment

| Area | Assessment |
| --- | --- |
| Workspace | Configuration/state persistence is appropriately simple. The linear readiness model is misleading, and workspace import is substantially overburdened. |
| Installer | Plan/apply separation is good. Installer parameters have multiple competing representations and source-provider rules are scattered. |
| Configuration | Archive, rendering, and Git primitives are appropriately function-oriented. Push/pull/status orchestration is becoming provider-dependent and repetitive. |
| Pipeline | Central resolution and failure interpretation are valuable. Execution data is represented several times, and watching is too procedural for a second interface. |
| Status | The weakest structural area: duplicated AWS observation, large flat result models, and separate implementations of overlapping views. |
| AWS adapters | `AwsClientFactory` is a justified stateful class. Most service functions are reasonably simple, but results are inconsistently typed and CodeBuild contains non-adapter diagnostic policy. |
| CLI | Presentation separation is good. Registration, parameter aliases, forwarding handlers, and compatibility wrappers create avoidable navigation. |
| Workflows | Useful as an application-layer concept, but the global package has become a catch-all rather than a meaningful architectural boundary. |

## Significant potential refactors

### 1. Establish one canonical installer configuration

Priority: High.

1. **Current problem:** Known CloudFormation parameters can exist simultaneously in `lza`, `configuration.repository`, `installer.options`, `installer.source_code`, and `installer.template_parameters`.

2. **Evidence:** Configuration repository details are modeled in [configuration/schema.py:10](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/configuration/schema.py:10) and repeated as installer options in [installer/schema.py:124](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/installer/schema.py:124). `apply_installer_parameter()` updates multiple locations while also storing every value in `template_parameters` at [installer/parameters.py:134](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/installer/parameters.py:134). The final builder then permits `template_parameters` to overwrite known typed values at [installer/parameters.py:303](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/installer/parameters.py:303).

3. **Why insufficient:** Consistency depends on every mutation path knowing which mirrored fields to update and which representation wins. Pydantic validation cannot guarantee agreement between these stores. Importing deployed parameters is consequently a synchronization algorithm rather than a straightforward decode.

4. **Proposed alternative:** Make the workspace’s typed installer settings canonical. Derive CloudFormation parameters through a single `InstallerParameterCodec`. Preserve version-specific unknown parameters in `extra_parameters`, but prohibit them from shadowing known fields. Remove configuration repository mirrors from `InstallerOptionsConfig`; derive `ConfigurationRepositoryLocation` and related parameters directly from `configuration.repository`.

5. **Expected gain:** One source of truth, fewer update branches, simpler import/drift calculation, and a safer basis for future version-aware schemas and GUI editing.

6. **Cost/risk:** Requires a workspace schema migration and careful compatibility handling for existing YAML. Deployed-stack import and template-default behavior would need precise regression coverage.

7. **Recommend now?** Yes. This should precede GUI mutation flows and configuration generation.

---

### 2. Replace the ordinal readiness lifecycle with capability assessment

Priority: High.

1. **Current problem:** Workspace readiness is modeled as a single ordered enum even though installer, configuration, import, and deployment readiness are independent dimensions.

2. **Evidence:** [workspace/context.py:35](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workspace/context.py:35) assigns `CORE_CONFIGURED`, `IMPORTED`, `CONFIGURED`, or `DEPLOYED` by checking configuration-directory existence, installer completeness, and a recorded stack ID in a fixed sequence. “Imported” is inferred from an incomplete installer configuration, not from `state.imported`. Commands then compare enum ordering through `min_readiness`.

3. **Why insufficient:** A freshly initialized configuration with incomplete installer settings can be classified as `IMPORTED`; deployment readiness is inferred from cached state rather than live state; and commands express requirements indirectly as ordinal comparisons. The model will become harder to explain in a GUI where multiple component states must be displayed simultaneously.

4. **Proposed alternative:** Return a `WorkspaceAssessment` containing explicit capabilities such as `metadata_valid`, `configuration_present`, `installer_configured`, `installer_recorded_deployed`, and `imported`. Commands declare required capabilities rather than a minimum lifecycle number.

5. **Expected gain:** More accurate command guards, component-specific remediation, clearer GUI status, and easier addition of validation, doctor, and partial-workspace workflows.

6. **Cost/risk:** Moderate. Error messages and command prerequisites need migration. Care is needed not to turn capability checks into dozens of ad hoc booleans; the assessment should remain one structured domain object.

7. **Recommend now?** Yes, before the GUI’s workspace overview establishes the existing enum as an external contract.

---

### 3. Create one request-scoped operational snapshot for status

Priority: High.

1. **Current problem:** Root, installer, and configuration status independently assemble overlapping live AWS and local observations, then expose differently shaped results.

2. **Evidence:** The 50-plus-field `ConfigurationStatusResult` begins at [workflows/status_config.py:34](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/status_config.py:34), with provider inspection and pipeline interpretation continuing through [workflows/status_config.py:192](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/status_config.py:192). Root status separately inspects the installer, both pipelines, and local Git at [workflows/status_root.py:323](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/status_root.py:323). Installer status repeats stack, version, and pipeline discovery at [workflows/status_installer.py:100](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/status_installer.py:100).

3. **Why insufficient:** The views can disagree as their logic evolves. Adding a Web overview and detail routes would either repeat AWS calls or require the Web layer to understand which workflow results overlap. The flat configuration result also makes invalid combinations representable—for example, S3, CodeCommit, and CodeConnection fields can all be populated simultaneously.

4. **Proposed alternative:** Introduce a request-scoped `WorkspaceObserver` or equivalent service that loads one `WorkspaceContext`, resolves one AWS context, and memoizes observations for that request. It produces a nested `WorkspaceSnapshot`:

   - installer stack observation;
   - installer/configuration pipeline observations;
   - discriminated configuration-remote observation;
   - local configuration/Git observation;
   - recorded-state fallback;
   - derived health.

   Root and detail views become projections of the same snapshot.

5. **Expected gain:** One observation path, fewer AWS calls, consistent live/recorded semantics, smaller render-specific models, and a clean read API for CLI and Web.

6. **Cost/risk:** Medium. The snapshot must allow partial failures without making all status unavailable. Memoization must remain request-scoped so stale observations do not leak across Web requests.

7. **Recommend now?** Yes. This is the most valuable refactor before the first read-only GUI slice.

---

### 4. Split mixed workflows and remove interactive callbacks from the application layer

Priority: High.

1. **Current problem:** Several workflows combine discovery, policy, user-decision points, mutation, error suppression, and presentation-oriented recommendations.

2. **Evidence:** `import_workspace_workflow()` is a 327-line operation with fourteen parameters at [workflows/workspace_import.py:323](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/workspace_import.py:323). It validates local configuration, discovers Git, constructs metadata, performs best-effort AWS discovery, imports an installer template, updates config/state, and generates command recommendations. Bootstrap similarly has a 232-line plan builder at [workflows/workspace_bootstrap.py:160](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/workspace_bootstrap.py:160) and a 138-line apply operation at [workflows/workspace_bootstrap.py:467](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/workspace_bootstrap.py:467). Its supposedly presentation-independent plan even embeds Rich markup in action strings at [workflows/workspace_bootstrap.py:225](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/workspace_bootstrap.py:225). Configuration push/pull accept synchronous confirmation callbacks at [workflows/config_push.py:78](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/config_push.py:78) and [workflows/config_pull.py:84](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/config_pull.py:84); installer initialization accepts a prompting callback at [workflows/installer_init.py:42](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/installer_init.py:42).

3. **Why insufficient:** Avoiding imports from Typer is not enough to make a workflow interface-neutral. Prompt and confirmation callbacks still give the application layer control over an interface conversation and do not translate naturally to HTTP request/response flows.

4. **Proposed alternative:** Use explicit two-stage operations:

   - `discover_import(request) -> ImportDiscovery`;
   - `plan_import(request, discovery) -> ImportPlan`;
   - `apply_import(plan) -> ImportResult`;
   - `prepare_installer_form() -> InstallerForm`;
   - `apply_installer_settings(InstallerSettingsRequest)`;
   - `plan_config_push(request) -> ConfigPushPlan`;
   - `apply_config_push(plan, confirmed=True)`.

   Bootstrap should return typed resource steps rather than formatted action strings. Optional live installer discovery should be a separate collaborator within import, with its own typed outcome.

5. **Expected gain:** Clear transaction boundaries, deterministic dry runs, Web-compatible APIs, easier partial-failure handling, and much smaller functions.

6. **Cost/risk:** Medium to high for import because its current best-effort behavior and repair semantics are intertwined. The split must preserve exactly when local metadata may be written after remote discovery fails.

7. **Recommend now?** Yes for callback removal and bootstrap result restructuring. Split workspace import before adding a Web import flow; it need not block the first read-only GUI page.

---

### 5. Introduce narrow provider abstractions where provider behavior is already repeated

Priority: Medium.

1. **Current problem:** Repository/source selection is implemented repeatedly with `if repo_type == ...` branches across push, pull, status, plan, deploy, and bootstrap.

2. **Evidence:** Configuration dispatch appears in [workflows/config_push.py:100](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/config_push.py:100), [workflows/config_pull.py:97](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/config_pull.py:97), and [workflows/status_config.py:192](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/status_config.py:192). Installer source behavior is separately selected during deployment at [installer/deployment.py:102](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/installer/deployment.py:102), plan at [workflows/installer_plan.py:76](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/installer_plan.py:76), and bootstrap at [workflows/workspace_bootstrap.py:199](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/workspace_bootstrap.py:199).

3. **Why insufficient:** Provider-specific defaults, accessibility rules, dry-run behavior, and observations can diverge depending on which workflow was updated. Planned diff support and installer source synchronization would add more branches to the same set of modules.

4. **Proposed alternative:** Introduce two separate, narrow provider families:

   - `ConfigurationRemote`: resolve destination, inspect, push, pull;
   - `InstallerSourceProvider`: inspect prerequisites, validate deployment readiness, plan, and eventually synchronize.

   Do not force S3 and Git into one large generic repository interface. Use capability-specific protocols or discriminated provider objects so unsupported operations remain explicit.

5. **Expected gain:** Provider rules become locally coherent; adding a provider no longer requires editing every workflow; status observations can use provider-specific typed results.

6. **Cost/risk:** The current configuration implementation has only two real transport families—S3 and Git—so an elaborate registry or dependency-injection framework would be worse. Provider construction also needs access to filesystem and AWS context without becoming a service locator.

7. **Recommend now?** Selectively. Extract configuration remotes before implementing `lza diff`; extract installer providers before implementing source synchronization. Do not introduce a general-purpose plugin framework now.

---

### 6. Replace duplicated pipeline representations with a lifecycle object or event stream

Priority: Medium to high before Web mutation.

1. **Current problem:** The same execution is represented as AWS adapter state, watch summaries, action failures, root summaries, and duplicated flat state fields. Watching is a blocking loop with internal timing state.

2. **Evidence:** Adapter models are defined in [aws/codepipeline.py:15](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/aws/codepipeline.py:15); near-parallel workflow models appear in [workflows/pipeline_watch.py:33](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/pipeline_watch.py:33); another summary exists in [workflows/status_root.py:30](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/status_root.py:30). The blocking polling lifecycle occupies [workflows/pipeline_watch.py:106](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/pipeline_watch.py:106). Runtime persistence duplicates installer/configuration branches throughout [pipeline/state.py:11](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/pipeline/state.py:11).

3. **Why insufficient:** Conversion and `getattr`-based structural handling weaken type safety. A two-hour synchronous callback workflow is suitable for a CLI but unsuitable as the primary abstraction for Web streaming, background execution, cancellation, or reconnection.

4. **Proposed alternative:** Define one domain `PipelineExecutionSnapshot` containing stages, actions, diagnostics, timestamps, and execution identity. Implement a `PipelineWatcher` with meaningful lifecycle state—or a generator/iterator yielding snapshots. CLI consumes it synchronously; Web can adapt it to streaming or background polling. Persist pipeline state as a nested record keyed by pipeline kind rather than two groups of parallel fields.

5. **Expected gain:** Fewer models and conversions, typed failure handling, reusable progress streaming, and elimination of repeated installer/configuration persistence branches.

6. **Cost/risk:** Runtime-state migration and careful preservation of eventual-consistency retries, timeout semantics, and final diagnostic enrichment.

7. **Recommend now?** Yes before implementing Web pipeline execution/watch. It does not need to block the first read-only Web view.

---

### 7. Move application use cases into bounded contexts and remove zero-value wrappers

Priority: Medium.

1. **Current problem:** The global `workflows` package separates use cases from the feature that owns them, while CLI registration adds another forwarding layer. Some modules exist only as aliases.

2. **Evidence:** Installer planning is divided between [installer/planning.py:13](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/installer/planning.py:13) and [workflows/installer_plan.py:38](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/workflows/installer_plan.py:38). `workflows/config_download.py` and `workflows/config_upload.py` are nineteen-line aliases, while [cli/commands/config_download.py:1](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/cli/commands/config_download.py:1) and [cli/commands/config_upload.py:1](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/cli/commands/config_upload.py:1) wrap sibling command handlers. [cli/main.py:13](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/cli/main.py:13) imports every handler and then defines forwarding Typer functions. Option declarations are separated again into the 281-line `cli/params.py`.

3. **Why insufficient:** The layer boundary improves import direction but increases the number of locations required to understand one feature. `workflows` answers “this is orchestration” but not “which domain owns it.” Alias modules preserve Python names that do not need to be public contracts.

4. **Proposed alternative:** Place application use cases under their owning bounded context, for example `installer/application/plan.py` and `configuration/application/sync.py`. Keep interface independence, but replace the rigid package formula with `interfaces -> feature application -> domain/ports`. Register command handlers directly from their CLI modules. Register `download` and `upload` as alternate command names for the same handler rather than maintaining wrapper modules and result aliases. Colocate one-off option definitions with their commands.

5. **Expected gain:** Less navigation, clearer ownership, fewer import-only modules, and a package structure that scales by feature rather than by horizontal layer.

6. **Cost/risk:** Mostly import churn with little immediate behavior gain. A big-bang move would create noisy history and conflict with concurrent GUI work.

7. **Recommend now?** Incrementally. Remove compatibility-only modules now when callers are verified; move workflows into features as those features undergo substantive refactors. Do not perform a repository-wide relocation by itself.

---

### 8. Tighten AWS adapter contracts and consolidate diagnostic parsing

Priority: Medium-low.

1. **Current problem:** AWS adapters alternate between typed dataclasses and untyped dictionaries, accept both factories and raw clients, and contain duplicated diagnostic cleanup.

2. **Evidence:** S3 observations return `dict[str, Any]` at [aws/s3.py:30](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/aws/s3.py:30) and [aws/s3.py:289](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/aws/s3.py:289). CodeCommit first returns a typed result and then converts it back to a dictionary at [aws/codecommit.py:107](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/aws/codecommit.py:107). Log cleanup in [aws/codebuild.py:13](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/aws/codebuild.py:13) overlaps substantially with [pipeline/failures.py:51](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/pipeline/failures.py:51).

3. **Why insufficient:** Callers depend on string keys and `Any`, while the alleged thin adapter layer owns heuristics for what constitutes an actionable LZA failure. The dual `factory`/`client` convention adds branches to nearly every service function without a clear runtime need.

4. **Proposed alternative:** Return typed observations consistently, including `AwsIdentity`, `S3BucketObservation`, and `S3ObjectObservation`. Keep AWS modules responsible for API calls and AWS error classification. Move all pure log extraction, recognition, deduplication, and root-cause selection into `pipeline.diagnostics`. Standardize adapters on either a resolved client or a small service object—not both per call.

5. **Expected gain:** Better type checking, smaller status builders, a genuinely thin AWS boundary, and one diagnostic normalization path.

6. **Cost/risk:** Low to medium, primarily caller migration. Overly detailed protocols for boto3 clients would add more ceremony than value.

7. **Recommend now?** Yes when touching the affected adapters, but it should not block GUI work. Do not build class wrappers for every AWS service solely for stylistic consistency.

## Patterns I would not introduce

- No general conversion from functions to classes. `installer.versions`, archive scanning, template rendering, drift calculation, and diagnostic recognizers are naturally stateless transformations.
- No generic repository abstraction shared between installer sources and customer configuration remotes; their lifecycle and safety semantics differ.
- No repository/unit-of-work framework around YAML and JSON persistence.
- No class hierarchy for failure recognizers. The existing ordered sequence of small recognizer functions at [pipeline/failures.py:369](/Users/andreyv/Projects/personal/lza-workbench/src/lza_workbench/pipeline/failures.py:369) is already a lightweight strategy and is simpler than polymorphic classes.
- No protocol for every AWS call. Protocols are justified around application-level provider capabilities, not as handwritten substitutes for boto3 types.
- No generic orchestration engine. Plan/confirm/apply and progress events should have consistent shapes, but the actual use cases should remain explicit.

## Counterfactual Architecture

Starting today with the same requirements, I would use feature-owned application layers rather than a global workflow layer:

```text
lza_workbench/
  workspace/
    model.py                 # WorkspaceDocument, WorkspaceRuntime
    persistence.py           # YAML/JSON load, save, migration
    assessment.py            # WorkspaceAssessment/capabilities
    application/
      initialize.py
      import_workspace.py

  installer/
    model.py                 # Canonical installer desired state
    parameters.py            # CloudFormation parameter codec
    templates.py
    sources/
      protocol.py
      github.py
      codecommit.py
      s3.py
      codeconnection.py
    application/
      initialize.py
      plan.py
      deploy.py
      import_deployed.py
      status.py

  configuration/
    model.py
    templates.py
    archive.py
    git.py
    remotes/
      protocol.py
      s3.py
      git_remote.py
    application/
      initialize.py
      push.py
      pull.py
      deploy.py
      status.py
      diff.py

  pipeline/
    model.py                 # One execution/stage/action model
    diagnostics.py
    watcher.py               # Iterator/stateful lifecycle
    application/
      start.py
      status.py

  infrastructure/
    aws/
      session.py             # AwsClientFactory/AwsExecutionContext
      cloudformation.py
      codepipeline.py
      codebuild.py
      s3.py
      codecommit.py
      secrets_manager.py
    github.py

  interfaces/
    cli/
      workspace.py
      installer.py
      configuration.py
      pipeline.py
      status.py
    web/
      ...
```

The core persisted models would be nested:

```text
WorkspaceDocument
├── customer
├── aws_target
├── lza
├── installer        # canonical desired installer state
└── configuration    # canonical desired configuration state

WorkspaceRuntime
├── import_record
├── installer
├── configuration
└── pipelines
    ├── installer
    └── configuration
```

Status would be built once:

```text
WorkspaceContext + AWS context
              │
              ▼
       WorkspaceObserver
              │
              ▼
       WorkspaceSnapshot
       ├── installer
       ├── configuration remote/local
       ├── pipelines
       ├── recorded fallback
       └── health
          ├── CLI renderers
          └── Web response models
```

### Meaningful differences from the current implementation

- The desired/runtime split remains; it is a strong architectural choice. Runtime state becomes nested rather than a flat field collection.
- `AwsClientFactory` remains; it has real session lifecycle and state.
- Interface-independent application logic remains, but it is owned by the relevant feature rather than a global `workflows` package.
- Readiness becomes a capability report rather than a synthetic linear lifecycle.
- Installer CloudFormation parameters have one canonical typed representation plus an explicit codec.
- Configuration and installer providers encapsulate behavior that is currently repeated in conditionals.
- Status uses one operational snapshot rather than three overlapping observation workflows.
- Long-running pipeline watching becomes an execution stream/lifecycle object instead of a callback around a blocking loop.
- CLI aliases are registration aliases, not Python compatibility modules.
- Pure filesystem, transformation, parsing, and comparison work remains function-based.

## Final conclusion

The project does **not** need an object-oriented rewrite or a wholesale redesign before any GUI work. The current separation of interfaces, AWS session management, desired state, and runtime state is fundamentally sound.

However, the first read-only GUI slice should be preceded by the unified status snapshot and capability-readiness refactors. GUI mutation flows should additionally wait for canonical installer settings and callback-free plan/apply APIs. Otherwise, the Web layer will either inherit the current flat models and duplicated observations or grow compensating abstractions of its own.

**Current architecture is sound but has several worthwhile structural refactors.**

Validation was read-only source inspection; no tests or linters were run because no code changed. The pre-existing untracked independent-review documents were left untouched.
