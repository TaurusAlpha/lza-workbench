# Review the provided code against the project’s coding principles

Output findings first. Do not modify code until all findings are listed.

Review priorities

Evaluate the code for:

Scope

* Changes must address only the requested task.
* Identify unrelated changes or unnecessary scope expansion.
* Identify new dependencies that are not clearly justified.

Simplicity

* Prefer the simplest solution that satisfies the requirements.
* Prioritize readability over brevity.
* Identify unnecessary abstractions, indirection, or overengineering.

Maintainability

* Prefer small, focused functions with a clear responsibility.
* Check whether logic is placed in the appropriate package, such as core/, aws/, config/, or utils/, instead of being embedded in command handlers.
* Check whether existing modules should be extended or whether a new module genuinely improves organization.
* Verify consistency with existing project structure and coding patterns.
* Identify duplicated logic or helpers.

Readability

* Check naming of variables, functions, and classes.
* Identify deeply nested control flow.
* Identify comprehensions or generator expressions that are difficult to read.
* Identify nested or complex expressions inside function calls.
* Flag code that is concise but harder to understand.

Project constraints

* Prefer Python over shell when practical.
* Keep AWS authentication external.
* Assume customer projects are created outside this repository.
* Do not recommend speculative or placeholder functionality.

Output format

Findings

List findings from highest to lowest impact.

For each finding include:

* Severity: critical, high, medium, or low
* File and line, when available
* Problem
* Why it matters
* Specific recommended change

Do not include style-only findings unless they improve correctness, readability, consistency, or maintainability.

If no meaningful issues are found, state:

No significant findings.

Suggested changes

After all findings, provide a concise list of findings and severity.
Do not explain the implementation unless explicitly asked.

Do not rewrite the code unless explicitly asked.
Do not suggest unrelated refactoring or future features.
State any assumptions clearly.
