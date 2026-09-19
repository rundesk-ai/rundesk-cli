# Diagnosing a flaky test

`SKILL.md` lists the traps and their replacements; this page is the procedure for finding which
one you have, in the order that finds it fastest.

## Start from what the evidence says is likely

The largest published study of flaky-test fixes — 201 commits across 51 Apache projects — classified
root causes into ten categories. Three dominate, and they are worth checking in this order because
the distribution is that lopsided:

| Category | Share of classified commits | What it looks like |
|---|---|---|
| Async wait | 74 of 201 | The test asserts before the work it triggered has finished |
| Concurrency | 32 of 201 | Two threads race on shared memory |
| Test order dependency | 19 of 201 | The test passes alone and fails after another test |
| Resource leak, network, time, randomness, I/O, floating point, unordered collections | 11, 10, 5, 4, 4, 3, 1 | Long tail, each with its own tell |

Two findings from that study should change how you treat the failure before you start:

- **78% of flaky tests were flaky the first time they were written.** Flakiness is usually introduced
  with the test, not acquired later. Reach for the test's own history before assuming the system
  changed.
- **24% of flaky-test fixes changed the code under test, and 94% of those fixed a real bug in it.**
  A flake is not automatically a test defect. Roughly one in four is the system telling you
  something true.

That second number is the reason a retry-until-green policy is dangerous: it is a filter that
discards real defect reports at a known rate.

## Reproduce the flake before diagnosing it

You cannot bisect a failure you cannot summon. Get a reproduction rate first — a test that fails
1-in-50 needs a different technique from one that fails 1-in-2.

```sh
# Establish the rate. Keep the count; "it failed sometimes" is not a measurement.
fails=0
for i in $(seq 1 50); do
  <run the single test> >/dev/null 2>&1 || fails=$((fails + 1))
done
echo "$fails/50"
```

Preserve everything from a failing run before touching anything: seed, order, timing, logs,
artifacts, environment, and the full failure output. A flake destroys its own evidence on the next
run, and re-running is the first thing everyone does.

If the rate is zero in isolation, that is itself a result — go straight to order dependency below.

## Isolate the axis

Vary exactly one thing at a time. Each result eliminates a category.

| Run | If it now fails | If it still passes |
|---|---|---|
| The test alone, repeatedly | Not order-dependent — look at async, concurrency, or time | Order dependency; find the polluting test |
| The suite in a fixed order, repeatedly | Non-determinism inside the test | Order or shared state |
| The suite in a randomized order | Order dependency confirmed | Order is not the axis |
| Single-threaded / parallelism disabled | Concurrency or shared resource contention | Not parallelism |
| With the clock frozen | Time dependence — boundaries, timezones, month ends | Not time |
| With a fixed seed | Randomness in data or iteration order | Not seeded randomness |
| On a loaded machine, or with a slower dependency | Async wait — the test's timing assumption is thin | Not timing-sensitive |

Most runners can randomize order and pin a seed; use the runner's own facility rather than
hand-rolling one, and record the seed with the result so the run is repeatable.

For order dependency, bisect the suite rather than reading it: run the failing test after the first
half of the suite, then after the quarter that reproduced it, until one polluting test remains. That
converges in a handful of runs where reading can take an afternoon.

## Fix the cause the category implies

The same study recorded how these were actually fixed, which is a better guide than intuition:

**Async wait.** 54% were fixed by waiting for the condition rather than for a duration, and that fix
usually removed the flakiness rather than reducing it. A third of these tests used a plain sleep to
enforce ordering.

```js
// Bad: too short on a loaded machine, wasted time on a fast one, and silent either way.
await sleep(200);
expect(await readStatus()).toBe('done');

// Good: waits for the event, and fails with a diagnostic when it never arrives.
await waitFor(() => expect(readStatus()).resolves.toBe('done'), { timeout: 5000 });
```

Give every wait a timeout that fails loudly. A wait with no bound converts a flake into a hang, which
is worse because CI reports it as an infrastructure problem.

**Concurrency.** No single strategy dominated: 31% were fixed by adding locks, 25% by making the code
deterministic, 9% by changing a condition. Almost all involved only two threads and memory-object
access, so the reproduction is usually smaller than it first appears — reduce to two threads before
theorizing.

**Test order dependency.** 74% were fixed by cleaning shared state between runs. Prefer creating
unique state per test over cleaning up after it, and register cleanup at the moment you acquire the
resource rather than in a teardown that a failure can skip. Nearly half of these depended on an
external resource, so check files, ports, databases, and caches before internal statics.

## Quarantine deliberately, and briefly

Quarantine protects the signal for everyone else while one test is being fixed. It is a holding
pattern, not a resolution.

Bound it when you use it: a hard cap on how many tests may sit in quarantine, or a fixed expiry per
test. Without a bound, quarantine becomes the place tests go to be forgotten, and the coverage they
represented is gone while the suite still reports green.

A quarantined test keeps an owner and a deadline. Deleting it is a decision to be made explicitly,
not the passive outcome of nobody looking.

## Do not

- Do not add a retry to make a failure disappear. Given that roughly a quarter of flake fixes turn
  out to be production bugs, a retry policy silently discards real findings.
- Do not lengthen a sleep. It changes the failure rate and the run time, not the cause.
- Do not conclude "environment" without evidence — 96% of the studied flaky tests were independent
  of platform.
- Do not fix a flake you never reproduced. Confirm the rate returns to zero under the conditions
  that produced it, not just once.
- Do not close it as flaky before checking whether the test is right and the system is wrong.
