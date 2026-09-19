# Assessing what a suite protects

Assessing coverage is a different task from adding a case, and it fails in a particular way: the
assessor reads the tests, finds them plausible, and reports that the area is covered. Test names
describe what somebody once wrote. They are not an inventory of what the system does, and the gap is
always in the difference between the two.

Work in the other direction. Establish what the code promises, then ask what would catch each promise
breaking.

## Build the behavior inventory from the code

List what this surface decides, transforms, stores, refuses, and emits — from the code and its
callers, not from the test directory. For each entry note who depends on it and what a defect there
would cost. That cost is what ranks the result later; nothing else does.

Include the promises that are easy to miss because no single function states them:

- what the surface refuses, and what the caller sees when it does;
- what it writes that something else later reads;
- what it does the second time it is called with the same input; and
- what happens when a dependency it needs is unavailable.

## Map each behavior to the case that would catch its regression

For every entry, name the specific case that fails if that behavior breaks. Three outcomes, and they
are not the same finding:

| Outcome | What it means |
|---|---|
| A case names it and asserts it | Mapped. Move on unless it is load-bearing enough to probe |
| A case touches the code but asserts something else | The line executes and nothing checks it; this reads as covered and is not |
| No case reaches it | Unmapped |

The second row is the one that makes coverage reports misleading, and it is invisible from a
percentage. It is also the common case around error paths: the test exercises the failure to reach
the success assertion after it.

## Probe the mapping where it matters

A mapped case is a claim, not a guarantee. For the behaviors whose failure would cost the most,
verify the claim rather than accepting it — break the behavior, watch that case fail for that reason,
and restore. [proving-teeth.md](proving-teeth.md) is the procedure and the false-pass signals.

Sample deliberately: the authorization rule, the money calculation, the migration path. A suite that
passes with the module deleted is worse than no suite, because it is what convinced everyone to stop
looking.

Also read the run itself, not the word green: a suite that discovers zero cases exits successfully,
and a case skipped for an absent dependency counts as coverage in every report that counts files.

## Rank by consequence and stop

Order the unmapped and mis-mapped behaviors by what a defect costs, and cut the list where the cost
stops justifying the work. A ranked list of five gaps that matter is actionable; a complete list of
sixty is a document nobody opens.

Leave these out — reporting them spends the credibility the real findings need:

- A helper already exercised through the behavior that uses it.
- Code with no decision in it.
- Generated or framework-supplied code the repository does not customize.
- An input no producer in the system can emit.
- A case that would repeat what an existing case already asserts.

## Report a work list, not a verdict on quantity

For each gap: the behavior, what breaks undetected, the boundary the case belongs at, and the
smallest case that would catch it. Name what you probed and what you took on trust, because those are
different claims and the reader cannot tell them apart otherwise.

```text
Good: `refund()` leaves the ledger row committed when the gateway returns non-2xx. Nothing asserts
      the rollback; the two refund cases both stub a success. One integration case against the real
      store, asserting no row after a failed response.
Bad:  refund handling needs more test coverage.
```

Say what a percentage cannot: whether the cases that exist would actually notice.
