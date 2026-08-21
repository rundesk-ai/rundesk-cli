# Writing-skills live-agent verification

**Date:** 2026-08-21

**Candidate:** PR #435 at `880c16a`

**Provider:** Claude, reported model `claude-opus-5[1m]`

**Fixture:** Fresh provider conversations, temporary artifact roots, and a temporarily substituted
test-agent grant restored after the final run

## Purpose

Test whether the revised `writing-skills` guidance materially improves a real agent's reusable
script-backed skill, whether the required guidance loads before implementation, and whether the
result is well written as well as executable. The agent received the desired capability and raw
workspace boundary, not the expected interface or defects.

## Matrix

| Run | Candidate available | Task | Result | Evidence |
|---|---|---|---|---|
| A — matched baseline | No `writing-skills` grant | Build `summarizing-test-runs` with a reusable local script | Baseline pass, 19 artifact tests | Fresh turn; Python and testing guidance loaded; artifact and tests reviewed |
| B — matched candidate | Revised guidance before the final isolation correction | Same task and constraints as A | Partial improvement, 29 artifact tests | Loaded `writing-skills`, workflow-script, Python, and testing guidance before work; added unsupported-input, partial-input, large-output, duplicate-input, outside-directory, preservation, and mutation cases |
| C — exact-head isolation | PR head `880c16a` | Build `comparing-json-snapshots` in one named temporary workspace | Partial | Loaded `writing-skills`, then its workflow-script reference, then Python and testing guidance before implementation; produced a 98-line skill, executable standard-library script, and 39 passing tests |
| D — focused quality correction | Working candidate after C | Review and improve Run C without being told its defects | Partial improvement, 46 artifact tests | Fixed duplicate inputs, whole-report bounding, `--force` misuse, run-name ordering, and an invalid test command; retained one inaccurate prose claim |

Run B materially improved the executable contract over A, but inspected the live skill library even
though the task authorized only a temporary workspace. The candidate was corrected to forbid live
library inspection for drafts, reviews, repository work, and isolated tests.

Run C exercised that correction. Supported turn evidence showed no live-library, catalog, grant,
agent-file, repository, or network access by the test agent. The artifact stayed under its assigned
temporary directory. Its 39 tests passed on Python 3.9.6 with no skips, including direct entry-point,
outside-working-directory, malformed-input, filesystem-failure, repeat, bounded-path, and mutation
cases.

## Writing-quality review

The Run C `SKILL.md` had several strong properties:

- Its description routes direct and indirect repeated-JSON goals and excludes unrelated document
  diffs and schema validation.
- The body proceeds from capture, through invocation and interpretation, to a reusable gate.
- It keeps the deterministic mechanism in the script and gives the agent non-obvious judgment about
  stable, changing, intermittent, shape, and mixed findings.
- It is compact enough to scan, uses imperative guidance, contains no process diary or package
  README, and does not duplicate a reference.

It did not pass the whole writing contract. The capture guidance says sorting or re-indenting raw
JSON hides instability. Re-indenting and object-key sorting do not hide semantic changes from this
parser, while array sorting or filtering can; the broad claim is inaccurate. A green script suite
did not detect that prose defect.

## Interface defect outside the agent's reported suite

The skill promises bounded stdout through `--limit`, but the renderer lists every input snapshot
before applying that limit to field sections. An independent run with 100 input arguments and
`--limit 1` emitted 103 lines. The output contract is therefore not fully bounded, and the 39 tests
did not cover many-input header growth.

The artifact is a test fixture, not a shipped skill. Run D corrected a copy but nothing was installed
or published. The two Run C misses caused its exact-head result to remain `partial` and drove two
durable changes: the evergreen
[live-agent verification guide](../live-agent-verification.md) now grades writing separately and
requires large-output checks across the complete interface, and `writing-skills` now states that
green script tests do not prove writing quality.

## Focused correction result

Run D independently found the unbounded snapshot list and four additional contract failures. It
refused duplicate snapshot paths that could fake a stable result, made `--force` without `--out` a
usage error, zero-padded run names so lexical order remains chronological past nine runs, corrected
the documented test working directory, and expanded the suite from 39 to 46 passing tests. Direct
review confirmed those changes and the suite result.

Run D still called the prose sound and retained the sentence claiming that sorting or re-indenting
raw JSON hides instability. The whole-path verdict therefore remains partial. That miss drove the
final writing-quality rule: trace factual promises and examples to observed behavior or sources,
exercise executable claims directly, and narrow claims that are true only for some inputs or tools.

## Cleanup and restored state

- The temporary candidate catalog was previewed and removed.
- The test agent's original bundled `writing-skills` grant was restored.
- `skills doctor` reported all eight test-agent grants ready after restoration.
- Both temporary candidate catalogs were removed after previewing their exact effects.
- The test artifact remained only long enough for direct review and reproducible evidence capture;
  no catalog, repository, or agent home contains it.

## Limitations and untested cases

- Run C directly requested skill creation, so it proves body and reference loading but not an
  indirect routing trigger or close near-miss for the exact head.
- Runs A and B are the matched baseline comparison; Run C changed the task to exercise the corrected
  isolation boundary and writing quality.
- The artifact suite ran on macOS and Python 3.9.6. Platform-specific permission cases may skip when
  run as root.
- No external-service integration was generated; integration guidance still relies on static
  contracts and separate future live-agent cases.

## Verdict

The revised skill materially improves reusable-script engineering and the exact-head isolation rule
worked, but neither Run C nor its focused Run D correction earned a full quality pass. Future
acceptance requires both the executable contract and the writing-quality checklist to pass, with
every factual promise checked and every claimed output bound tested against the entire rendered
interface.
