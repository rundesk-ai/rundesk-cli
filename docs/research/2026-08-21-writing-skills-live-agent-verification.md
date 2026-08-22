# Writing-skills live-agent verification

**Date:** 2026-08-21

**Candidate:** PR #435, final exact head `2f25532` (Run E used earlier candidate `03251b0`)

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
| E — integration and publication draft | Earlier candidate `03251b0` | Build an offline-testable external-service skill and catalog | Partial, corrected fixture at 137 tests | Produced a valid catalog and strong pagination, profile, mutation, and offline proof; direct review found a type-label collision, unsafe incomplete-read recovery, and an order-dependent test module |
| F — existing-owner reuse | Exact head `2f25532` | Add semantic release-evidence comparison to a catalog where `release-audits` already owns it | Placement pass; whole-path partial | Inspected both skills and extended `release-audits` without adding a package; direct review found path-alias, input-bound, and rendered-identity defects, and the original tests wrote under system temp |
| G — distinct-authority control | Exact head `2f25532` | Add release-policy exception decisions where existing audit and notes skills explicitly exclude authority | Placement pass; whole-path partial | Added sibling `release-exceptions` inside the existing catalog package; direct review found hard-link, input-bound, special-file, and nested-authority validation gaps |
| H — non-authoring near-miss | Exact head `2f25532` | Apply the generated exception workflow to one existing record | Pass | Correctly reported the bounded active window, loaded no skill-authoring guidance, and wrote nothing |
| I — clean-boundary reuse repetition | Exact head `2f25532` | Add incident action-item comparison where `incident-reviews` already owns it | Boundary and placement pass; whole-path partial | Loaded authoring, script, Python, and test guidance before implementation; all transient work stayed under and was removed from `tests/.scratch`; direct review found report-over-input and rendered-label defects |

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

## External-integration result

Run E produced a structurally valid `pulsefeed-skills` catalog, an executable Python 3.9 standard-
library client, 134 passing tests on Python 3.9 and 3.11, seven caught mutations, an offline run, and
a supported Rundesk install preview that changed nothing. The command handled empty intermediate
pages, cross-page repeats, explicit profile selection, bounded sampling, safe output replacement,
and incomplete reads.

Direct review still found three material defects. Two distinct long event types could collapse into
one displayed key; the incomplete-read message advised timestamp-only resumption even though an
empty intermediate page or more same-timestamp events than the cap could make that loop or lose
meaning; and one CLI test module passed only after another module had modified import state. Watched-
fail corrections made labels collision-safe, required rerunning the same full window with higher
limits, and made every suite independently runnable. The corrected fixture passed 137 tests on both
runtimes, the offline run, all seven mutations, the demo, and Rundesk's preview. Run E remains
partial because the delegated artifact itself needed those corrections.

## Existing-owner and distinct-owner decisions

Run F is the direct test of `LIVE-SK11`. The seed catalog contained `release-audits`, whose
description and body already owned semantic validation-report comparison, and `release-notes`,
which explicitly excluded audits. The agent inspected both and added the command, reference, and
tests to `release-audits`; the package set remained exactly those two skills. That placement is a
pass: a new routing surface would have duplicated the existing owner.

Its overall execution is partial. The original 46 tests passed on Python 3.9 and 3.11, but used
default system-temporary directories outside the fixture boundary. Direct adversarial tests then
caught hard-linked inputs bypassing same-file refusal, long identities with the same prefix
rendering indistinguishably, control characters injecting report lines, and whole-file or special-
file reads bypassing the claimed input bound. Watched-fail corrections pass 52 tests on both
runtimes, each suite independently, with all scratch inside the catalog; Rundesk's install preview
accepts the corrected catalog without installing it.

Run G checked the inverse decision. `release-audits` explicitly excluded waiving policy and naming
an approver, while `release-notes` excluded approval decisions. The requested approval, expiry,
revocation, and supersession authority was therefore materially distinct. The agent correctly
created sibling `release-exceptions` inside the existing catalog package and added only a handoff to
`release-audits`; it did not force the workflow into the close-but-wrong owner or create a separate
catalog package. The original 35 tests passed on both runtimes and kept scratch under the catalog.
Direct review found hard-link aliases, unbounded or blocking input reads, and an ignored nested
authority typo. Watched-fail corrections pass 39 tests on both runtimes and Rundesk's preview accepts
the corrected three-skill catalog. Placement passes; the whole implementation path remains partial.

Run H was deliberately not a skill-authoring task. The agent read and applied the existing
`release-exceptions` workflow to its worked record, correctly reported the exception active at the
named instant and expiring 21 hours later, invoked no skill-authoring guidance, and wrote nothing.
This is the expected near-miss behavior.

Run I repeated the existing-owner decision with a strict local scratch contract. The agent loaded
the applicable authoring and implementation guidance before writing, inspected `incident-reviews`
and the explicitly excluded `incident-comms`, and extended `incident-reviews`. Its 46 original tests,
mutation copies, and demo files all stayed under the catalog; `tests/.scratch` was absent at handoff.
That is a clean placement and write-boundary pass. Direct review still caught an optional report
replacing a compared export, same-prefix long values rendering identically, and control characters
injecting report lines. Watched-fail corrections pass 49 tests on Python 3.9 and 3.11 with both
suites independently runnable, and Rundesk's preview accepts the corrected catalog without
installing it. The implementation path remains partial.

## Cleanup and restored state

- The temporary candidate catalog was previewed and removed.
- The test agent's original bundled `writing-skills` grant was restored.
- `skills doctor` reported all eight test-agent grants ready after restoration.
- Every draft catalog was previewed without installation and retained only through direct review.
- The five temporary artifact roots were moved to Trash after evidence capture; no installed
  catalog, repository, or agent home contains them.

## Limitations and untested cases

- Run C directly requested skill creation. Run H covers the final-head non-authoring near-miss, but
  no matched indirect-trigger pair was rerun at the final head.
- Runs A and B are the matched baseline comparison; Run C changed the task to exercise the corrected
  isolation boundary and writing quality.
- The artifact suite ran on macOS and Python 3.9.6. Platform-specific permission cases may skip when
  run as root.
- Run E used a synthetic service contract and injected transports. No real-service smoke test was
  authorized, so the concrete HTTP transport remains unproven against a live endpoint.

## Verdict

The revised skill materially improves reusable-script engineering, and the final candidate makes
the correct `LIVE-SK11` decisions in both directions: reuse the current owner when it owns the
workflow, and create a sibling skill when routing and authority are distinct. The near-miss also
stayed out of authoring guidance. The implementation paths remain partial because green delegated
suites repeatedly missed path aliases, complete input bounds, and rendered-output collisions.
Acceptance therefore requires parent adversarial review as well as the executable and writing-
quality checklists; every factual promise and every input/output bound must be exercised across the
complete interface.
