---
name: testing-code
description: Use when designing, adding, repairing, assessing, or speeding up automated tests and their local or CI feedback loop, including choosing a boundary, finding untested behavior, reproducing a defect, or diagnosing flaky, brittle, slow, or falsely green results. It supplies a runner-neutral workflow for deterministic cases, trustworthy assertions, measured performance changes, and auditable evidence. Do not use it for a framework's test syntax alone, to review a completed change, or to diagnose a failure whose cause is unknown.
---

# Test code

Prove the smallest meaningful contract, then prove the test can detect its violation.

## Define the proof

1. Read repository rules, test commands, nearby tests, and the authoritative requirement.
2. State the observable behavior, required side effects, and risk if it breaks.
3. Search existing tests by behavior; add only missing proof.
4. For a defect, isolate the smallest reproducing input and environment.

```text
Good: assert the public result and required state change.
Bad:  assert a private collaborator was called before another, although users cannot observe it.
```

Assert an interaction only when it is required behavior, such as emitting an event or avoiding an
expensive boundary.

## Load the stack's own mechanics

This skill supplies the method — the boundary, the assertion, and the proof. A runner's fixtures,
doubles, isolation, cleanup, and the idioms a reviewer of that stack expects belong to the package
that owns it: `using-laravel`, `using-inertia`, `using-vuejs`, `using-reactjs`, `using-python`,
`using-cpp`, `using-axmol`, `using-postgres`, `using-mysql`, `using-sqlite`, and their neighbours.

Read the package for every language, framework, and data store the code under test uses, as soon as
you know what they are. A framework and the database under it are two packages, not one. None of them
needs to be installed for the method here to work.

## Choose the boundary that contains the risk

| Boundary | Prove |
|---|---|
| Unit | Decision, transformation, invariant, or error path without infrastructure. |
| Integration | Wiring to a real local boundary such as persistence, filesystem, queue, network, process, or serializer. |
| Contract | Producer and consumer agree on the messages and formats each uses. |
| End to end | A few critical journeys or wiring decisions narrower tests cannot establish. |

Prefer the narrowest boundary containing the risk. Add a wider case only when it answers another
question; do not replay every edge case through the full system. Report what ran and which
dependencies were real because labels vary.

The risk is not always where the code changed. When a local result is stored, or decides an action
somewhere else, the narrowest boundary containing it reaches that consumer: prove the transformation
in a unit and the consequence where it lands. A unit case alone reports a transformation as correct
while the state or action it drives is wrong.

```text
Good: use the real serializer to prove its stored format.
Bad:  mock the serializer and call the result an integration test.
```

## Make one case trustworthy

- Arrange only relevant state, perform one action, and assert the contract.
- Name the condition and behavior; make failures print useful expected and actual values.
- Cover only material partitions such as normal, empty, invalid, maximum, repeated, unauthorized,
  partial, or concurrent behavior. Take the values from what real producers emit and existing
  consumers accept — alternate representations, missing and malformed among them — not from the
  one example the assignment happened to give.
- Keep causal values visible. Helpers hide noise, not why the case passes.
- Use an independent expected value or oracle. Duplicating production logic can make both wrong.

Never weaken an assertion merely to get green. When behavior changes intentionally, update it from
the requirement—not current output. Never write a case for behavior nobody specified: an assertion
whose only source is the implementation records a guess as a requirement, and every later reader
takes it for a decision someone made.

## Replace known traps

| Avoid | Do instead | Prove the replacement |
|---|---|---|
| Ambient time, locale, randomness, environment, identifiers, or scheduling | Inject or freeze inputs; record seeds | Re-run the seed and boundaries |
| Shared state or order-dependent cleanup | Use unique state; register cleanup on acquisition | Run alone, reordered, and in parallel |
| Production services or data | Use a real local dependency, hermetic service, contract, or maintained fake | Name the real boundary; test drift separately |
| Mock choreography for computation | Stub inputs; mock only an observable interaction against its real interface | Refactor internals; behavior tests stay green |
| Fixed sleep before an async assertion | Wait for the event or condition with a diagnostic timeout | Delay the operation; completion follows the event |
| Retry that converts intermittent failure to green | Preserve seed, order, timing, logs, and artifacts; fix the cause | Repeat the failing conditions; report retries |

A flaky result is a defect in the test, system, runner, or environment. Quarantine may protect the
main signal temporarily; keep the failure visible and owned.

## Prove the test and the run

1. For a regression, observe failure for the reported reason before the correction. If that is unsafe
   or impractical, state the limitation instead of claiming the defect was reproduced.
2. Run the changed case, containing suite, then required broader checks.
3. Read exit status, discovery/execution counts, skips, expected failures, retries, and warnings. A
   check that builds its cases from fixtures, generation, or discovery reports how many it exercised;
   one that found none did not run, whatever it returned.

```text
Good: exit 0; 37 discovered, 37 executed, 0 skipped; new regression passed.
Bad:  "green"; 0 discovered, or the relevant case skipped because its dependency was absent.
```

Coverage locates unexercised code; it does not prove assertions or justify an invented target.

For performance work, keep local duration, hosted CI latency, time to first failure, and runner
consumption as separate claims. Name only the metric observed: a local benchmark cannot prove hosted
CI latency, and removing parallel duplicate work reduces cost rather than the critical path unless
queue or resource contention was measured.

Report the behavior, boundary, command, result, counts, real dependencies, and unresolved paths. Do
not claim more than the evidence covers.

## Load the depth the task needs

- [boundaries-and-doubles.md](references/boundaries-and-doubles.md) — the double vocabulary, stub
  versus mock, and which dependencies to keep real.
- [flaky-diagnosis.md](references/flaky-diagnosis.md) — reproducing a flake, isolating which axis
  causes it, and fixing by category.
- [proving-teeth.md](references/proving-teeth.md) — breaking the code to prove the test detects it,
  safely, and what a false pass looks like.
- [assessing-a-suite.md](references/assessing-a-suite.md) — judging what an existing suite protects
  and what it leaves unguarded, when the task is to assess coverage rather than to add a case.
- [performance.md](references/performance.md) — measuring and reducing local test and CI feedback
  time without weakening coverage, isolation, or failure evidence.

Read [the source map](references/sources.md) when auditing, changing, or extending these rules.
