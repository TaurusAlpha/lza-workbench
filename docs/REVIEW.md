# Review the provided code

Output findings first. Do not modify code until all findings are listed.

Prioritize concrete defects over preferences.
Report a finding only when you can point to the specific lines or behavior that demonstrate it.
Do not invent issues, speculate about missing requirements, or report code merely because you would implement it differently.

If the code is solid, output only: `No significant findings.`

## Scope of Analysis

You will be given one specific target command/entry point. Trace its full implementation: follow its callees, and their callees, as needed to evaluate whether responsibilities are well-separated, logic lives in the right place, and data flows correctly. Do not limit yourself to the entry-point function/file in isolation — follow the call chain as far as necessary to evaluate it properly, within the code actually provided to you.

If a callee or caller is referenced but not available to you (out of context, external package, etc.), do not assume its behavior. Either state the assumption explicitly or mark the related finding as lower-confidence.

## Project Architecture Constraints

If a project architecture document is provided, treat its stated boundaries, ownership rules, and dependency directions as hard constraints — violations of them are findings, not lower-confidence observations, since they are explicit project requirements rather than general best-practice inference. Do not extend, generalize, or infer additional architectural rules beyond what the document states.

If no architecture document is provided, evaluate structure and placement using the general Maintainability lens below, at lower confidence, without asserting project-specific conventions you cannot verify.

## Review Lenses

Evaluate the code primarily through these lenses, but note anything else that looks like a real, concrete defect even if it doesn't fit neatly into one:

- **DRY** — meaningful duplicated logic (not superficially similar but semantically different code).
- **SOLID** — apply pragmatically. Flag a violation only when it currently causes a real problem (hard to test, hard to change safely, tangled responsibilities) — not because a pattern could theoretically be applied more purely.
- **Simplicity** — prefer the simplest solution that satisfies the requirements. Flag unnecessary abstraction, indirection, or overengineering, and equally flag under-engineering that causes real fragility.
- **Readability** — naming, nesting depth, overly clever or dense code, and structure that would be hard for a non-expert maintainer to follow.
- **Correctness & Security** — logic bugs, realistic edge cases, missing error handling, race conditions, unsafe handling of sensitive data, improper resource management. Do not report purely hypothetical edge cases unless realistically reachable.
- **Maintainability** — logic in the wrong module/package, consistency with existing visible patterns, large or mixed-responsibility functions when it materially reduces clarity or testability.

## Confidence Gating

This replaces topic restrictions as the main quality control — be broad in what you look for, strict in what you assert as a finding:

- **Finding**: you can cite the specific lines/behavior demonstrating a concrete problem.
- **Lower-confidence observation**: a principle feels violated (e.g. "this might be a SOLID smell") but you can't point to concrete resulting harm, or it depends on code you can't see. List these separately, clearly labeled, and do not count them toward severity.

## Project Constraints

- Prefer Python over shell when practical.
- Keep AWS authentication external.
- Assume customer projects are created outside this repository.
- Do not recommend speculative, placeholder, or future functionality.
- Do not add speculative unit tests alongside feature implementation unless explicitly requested.
- Do not introduce new dependencies unless clearly justified.
- Flag test shims, mock callbacks, or test-only parameters introduced into production code.
- Do not report purely cosmetic style issues unless they obscure behavior or increase maintenance risk.

## Severity Guidelines

Use severity conservatively.

- **Critical:** Likely security compromise, data loss, or production-wide outage.
- **High:** Likely functional failure, serious security issue, or major operational impact.
- **Medium:** Meaningful correctness, reliability, maintainability, or operational problem.
- **Low:** Minor but actionable issue with limited impact.

Do not report cosmetic or preference-only Low findings.

## Output Format

### Findings

List findings ordered from highest to lowest impact.

For each finding:

- **Severity:** Critical | High | Medium | Low
- **Location:** File and line number if reliably available; otherwise function, class, or symbol name.
- **Problem:** Brief description of the concrete issue.
- **Impact:** Why it matters in practice.
- **Recommendation:** Specific corrective action.

### Lower-Confidence Observations

List separately, same format as findings but no severity required — just problem, why it seemed worth flagging, and what would confirm or refute it.

### Summary

Concise bulleted list of each finding's name and severity, followed by a one-line count of lower-confidence observations.

## Output Rules

- Be direct and brief.
- Do not add conversational commentary or filler.
- Do not explain implementation details unless explicitly requested.
- Do not rewrite the codebase unless explicitly requested.
- Do not suggest unrelated refactoring or future features.
- State assumptions only when they materially affect a finding.
- Do not fabricate line numbers, requirements, architecture, or runtime behavior.
- Prefer fewer high-confidence findings over many weak findings.
