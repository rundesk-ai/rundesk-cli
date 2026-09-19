---
name: debugging-code
description: Use when software crashes, hangs, regresses, behaves inconsistently, returns wrong results, or fails a test, build, or runtime check and the cause is not yet proved. It supplies a language-agnostic workflow to reproduce the failure, preserve evidence, isolate the responsible boundary, test one hypothesis at a time, and prove the smallest safe correction, plus stack mechanics for Laravel and Herd, Vue and Nuxt, React, Python, and C++. Do not use it to judge a completed change, to explain a cause that is already proved, or to write tests as the main task.
---

# Debug code

Find the cause before choosing the correction. Keep observations, inferences, and hypotheses
separate throughout the investigation.

## Load the framework's mechanics

The workflow below is language-agnostic. Read the reference for the stack in front of you as soon as
you know what it is — each one says where the evidence is already recorded, how to bisect that
stack's request or render path, which symptom points at which layer, and the traps that send a
diagnosis the wrong way.

- [references/laravel.md](references/laravel.md) — Laravel and its queue, Eloquent, and cache layers.
- [references/herd.md](references/herd.md) — Laravel Herd site mapping, PHP identity, services, TLS,
  and local runtime logs. Load it only when Herd serves the failing application.
- [references/vue.md](references/vue.md) — Vue and Nuxt: reactivity, render triggers, hydration.
- [references/react.md](references/react.md) — React: DevTools evidence, Strict Mode double
  invocation, stale closures, render loops, hydration, and errors that never surface.
- [references/python.md](references/python.md) — tracebacks, `pdb`, development mode, hangs, leaks.
- [references/cpp.md](references/cpp.md) — build identity, GDB/LLDB, sanitizers, cores, optimized code.
- [references/sources.md](references/sources.md) — the citation basis for the above.

These supply mechanics only: where a stack records evidence and how to get more. The rule a symptom
violates belongs to that stack's own package — `using-laravel`, `using-vuejs`, `using-reactjs`,
`using-python`, `using-cpp` — and none of them needs to be installed for the mechanics here to work.

## Establish the failure

1. Read the applicable repository rules and the system's intended contract.
2. Record the expected behavior, actual behavior, impact, affected scope, last known success, and
   earliest known failure.
3. Preserve the exact error, stack, logs, command, inputs, versions, environment, and timestamps.
   Summaries can erase the clue that distinguishes one failure from another.
4. Reproduce with the smallest safe case that still fails. Run the exact case more than once when
   intermittency is possible.
5. Confirm the signal is valid: the command exercised the intended code, instrumentation is current,
   and the observed failure is not a stale artifact or an unrelated setup error.

If the failure cannot be reproduced, state what was attempted and what evidence is missing. Do not
turn a plausible explanation into a proven cause.

For a live or production failure, stabilize user impact before extended diagnosis when authorized.
Do not experiment on production data, permissions, availability, or irreversible state without
explicit authority and a recovery path.

## Model the failing path

- Trace the request, event, or input from its entry point to the first incorrect state, not merely
  the final error.
- Mark component boundaries, state transitions, external dependencies, retries, and asynchronous
  handoffs where evidence can be compared.
- Compare a working and failing case across one dimension at a time: input, version, configuration,
  data, environment, timing, or dependency response.
- Inspect recent code, dependency, configuration, schema, and infrastructure changes, but do not
  assume correlation proves cause.
- Distinguish the visible symptom, the immediate mechanism, and the root condition that made the
  mechanism possible.

## Run a hypothesis loop

1. State one falsifiable cause and the evidence it predicts.
2. Choose the cheapest safe observation or experiment that distinguishes it from the alternatives.
3. Change one variable. Capture the command, input, and result.
4. Reject, refine, or confirm the hypothesis from that result.
5. Repeat until the evidence explains the complete failing path.

Rank hypotheses by fit with the evidence, likelihood, and cost to test. Use boundary probes, binary
search through the call path or change history, targeted logging, a debugger, or a minimal fixture
to shrink the search space.

Avoid shotgun edits, broad dependency upgrades, blind restarts, and several speculative fixes at
once. They destroy causal evidence. A restart that clears a symptom may reveal state involvement,
but it does not establish root cause.

## Handle intermittent failures

Hold code and inputs constant while controlling sources of nondeterminism:

- time, timezone, locale, randomness, and generated identifiers;
- execution order, shared mutable state, cleanup, and parallel workers;
- scheduling, races, timeouts, retries, and eventual consistency;
- network, filesystem, resource pressure, and external-service behavior.

Capture the seed, order, timing, environment, and artifacts for every failure. Do not treat retries,
longer sleeps, or wider timeouts as fixes unless the contract itself requires that behavior.

## Correct the proven cause

If the request is diagnosis-only, stop after establishing the cause and correction direction. When
a fix is authorized:

1. Add or identify the smallest proof that fails for the defect and expresses the intended contract.
2. Change the narrowest responsible code or configuration. Do not bundle unrelated cleanup.
3. Re-run the original reproduction, the focused proof, and the relevant surrounding checks.
4. Exercise nearby boundary and failure cases that share the corrected path.
5. Remove temporary instrumentation and confirm the fix did not conceal the signal.

Use the framework reference above for the mechanics of proving the fix on that stack, and the
applicable language or testing skill for the rules the defect violated.

## Report what is known

Report the original failure, reproduction, evidence trail, root cause, correction, and verification.
Name residual risk and anything not exercised. If causality remains incomplete, label the result as
a leading hypothesis and state the next discriminating check; never report a symptom disappearing
as proof that the defect is resolved.
