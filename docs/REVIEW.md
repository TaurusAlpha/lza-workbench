# Review the provided code against the project’s coding principles

Output findings first. Do not modify code until all findings are listed.

Prioritize concrete defects over preferences.
Report a finding only when it is supported by the provided code or explicit project constraints.
Do not invent issues, speculate about missing requirements, or report code merely because you would implement it differently.

If the code is solid, output only: `No significant findings.`

## Review Priorities

Evaluate the code for:

### Scope

- Changes must address only the requested task.
- Identify unrelated changes or unnecessary scope expansion.
- Identify new dependencies that are not clearly justified.
- If the original task or diff is not provided, do not make scope findings that require knowing the intended change.

### Correctness & Security

- Identify logic bugs, realistic edge cases, missing error handling, race conditions, or incorrect assumptions.
- Flag security risks, unsafe handling of sensitive data, or improper resource management.
- Do not report purely hypothetical edge cases unless they are realistically reachable or violate an explicit requirement.

### Simplicity

- Prefer the simplest solution that satisfies the requirements.
- Prioritize readability over brevity.
- Identify unnecessary abstractions, indirection, or overengineering.
- Do not recommend redesign solely based on personal preference.

### Maintainability

- Prefer focused functions with clear responsibilities.
- Flag large or mixed-responsibility functions only when they materially reduce clarity, correctness, or testability.
- Check whether logic is placed in the appropriate packages/modules.
- Verify consistency with existing project structure and coding patterns when those patterns are visible.
- Identify meaningful duplicated logic or unnecessary helpers.

### Readability

- Check naming of variables, functions, classes, and modules.
- Identify deeply nested control flow or unnecessarily complex expressions.
- Flag clever or overly concise code when it materially reduces understandability.
- Ignore cosmetic style issues unless they obscure behavior or increase maintenance risk.

### Project Constraints

- Prefer Python over shell when practical.
- Keep AWS authentication external.
- Assume customer projects are created outside this repository.
- Do not recommend speculative, placeholder, or future functionality.
- Do not introduce new dependencies unless clearly justified.

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

### Summary

Provide a concise bulleted list containing each finding name and severity.

## Output Rules

- Be direct and brief.
- Do not add conversational commentary or filler.
- Do not explain implementation details unless explicitly requested.
- Do not rewrite the codebase unless explicitly requested.
- Do not suggest unrelated refactoring or future features.
- State assumptions only when they materially affect a finding.
- Do not fabricate line numbers, requirements, architecture, or runtime behavior.
- Prefer fewer high-confidence findings over many weak findings.
