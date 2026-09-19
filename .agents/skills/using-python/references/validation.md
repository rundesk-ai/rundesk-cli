# Using Python Validation

This is the current validation record for `using-python`; the repository-wide method is in
[Validating Skills](../../../docs/guides/validation.md).

## Boundary under test

The skill should activate for Python language and project practice — module and package boundaries,
public APIs, naming, docstrings, typing, error handling, resource lifetimes, concurrency, measured
performance, runtime compatibility, security-sensitive operations, and standard-library `unittest`.
It should not activate for a non-Python codebase or for database-engine work that never touches
Python.

## Trigger and exclusion cases

| ID | Request shape | Expected behavior |
|---|---|---|
| PYT-T01 | Review a Python module's public API and docstrings | Load |
| PYT-T02 | "This script silently swallows errors and I can't tell what failed" | Load |
| PYT-T03 | Write a shell script that happens to call a Python program | Do not load |
| PYT-T04 | Tune a Postgres index used by a Python service, with no Python change | Do not load; `using-postgres` owns it |
| PYT-T05 | Add typing to a mixed repository's TypeScript files | Do not load |
| PYT-T06 | Add `unittest` cases with isolation and cleanup | Load |
| PYT-T07 | Python service storing state in SQLite | Compose with `using-sqlite`; each owns its half |

## Workflow and authority cases

| ID | Request shape | Expected behavior |
|---|---|---|
| PYT-W01 | `T \| None` proposed in a project whose floor is Python 3.9 | Use `Optional[T]`; do not modernize past the declared runtime floor |
| PYT-W02 | A refactor that also reformats unrelated code | Keep the change bounded; local formatting comes last and does not repair a contract |
| PYT-W03 | SQL built by string formatting from user input | Name it as injection, parameterize, and allowlist identifiers rather than interpolating them |
| PYT-W04 | `pickle` used on data from a cache another process can write | Treat it as untrusted deserialization and replace it, not merely warn |
| PYT-W05 | A repository convention conflicts with this package's default | Follow the repository, and call out any deviation made for correctness or security |
| PYT-W06 | "I cleaned it up and the tests pass" | Reject fluent assurance; require the observed run and the tool findings before added judgement |
| PYT-W07 | Supported Python versions cannot be determined | Inspect `pyproject.toml` and the CI matrix, or stop and name the unknown |
| PYT-W08 | A performance claim with no measurement | Require a measured baseline before accepting the optimization |

## Provider evidence

Last verification: not yet run against a live provider matrix.

- Claude Code: pending. Cases marked for the sampled run are PYT-T01, PYT-T04, PYT-W06, and PYT-T07.
- Codex: not run.

No case below is marked passed. Record client versions, model identifiers, isolation constraints,
and per-case results here before claiming provider compatibility.

## Limits

PYT-T07 requires `using-sqlite` in the same workspace. No case executes a Python program; workflow
cases are graded on the decision, the rule cited, and the proof demanded.
