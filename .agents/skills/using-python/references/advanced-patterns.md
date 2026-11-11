# Advanced Python concurrency and performance

Load this reference only when the task actually involves concurrency, cancellation, shared state,
memory pressure, or measured performance. Follow the repository's supported versions and configured
tools; do not install a preferred toolchain merely because it appears in an example elsewhere.

## Choose concurrency from the workload

| Work | Default starting point | Main constraint |
|---|---|---|
| Existing async application with concurrent I/O | `asyncio` | Every blocking call can stall the event loop |
| Blocking I/O with synchronous libraries | Bounded threads | Cancellation cannot forcibly stop arbitrary thread work |
| CPU-bound independent work | Processes | Inputs and results must cross process boundaries |
| Small sequential workload | No concurrency | Coordination may cost more than the work |

Do not mix models without naming the boundary. Calling blocking I/O directly from an async function
is not asynchronous; on an ordinary GIL-enabled CPython build, creating more threads does not make
CPU-bound Python bytecode scale reliably.

```python
# Good: the caller owns the executor and its shutdown.
with ThreadPoolExecutor(max_workers=8) as executor:
    results = list(executor.map(fetch_one, urls))

# Bad: work outlives the function and shutdown is unspecified.
executor = ThreadPoolExecutor()
for url in urls:
    executor.submit(fetch_one, url)
```

## Own tasks and shutdown

Every task needs an owner that observes its result, handles failure, and completes or cancels it
during shutdown. Do not create fire-and-forget tasks whose references and exceptions disappear.

Use the structured primitive available at the runtime floor. `asyncio.TaskGroup` requires Python
3.11; on older versions, retain task references and define explicit collection and cancellation.
Treat version-specific concurrency syntax as a compatibility decision, not a cosmetic rewrite.

Make cancellation part of the contract:

- propagate `CancelledError` unless the current boundary is responsible for cleanup;
- put cleanup in `finally` or an async context manager;
- bound waits with a timeout chosen from product requirements;
- decide whether one child failure cancels siblings or permits partial results;
- do not retry cancellation, validation failures, or permanent errors as transient work.

## Own subprocess streams

**A child can block before it exits when a captured pipe fills.** Symptom: `await process.wait()` never
returns for a verbose child. Cause: the child is blocked writing to an unread `PIPE`, so it cannot
terminate. Use `communicate()` when output is bounded; for unbounded output, start concurrent drains
for every captured stream before waiting. If stdin is a pipe, write or close it on every path.

```python
# Good: communicate drains both captured streams and waits for exit.
stdout, stderr = await process.communicate()

# Bad: nobody drains the captured output while the child is running.
await process.wait()
stdout = await process.stdout.read()
```

Prove the lifecycle with a child that writes more than the pipe capacity before exiting. The
draining implementation completes; the wait-first implementation stalls.

**`StreamWriter.write()` may only buffer bytes.** Symptom: a slow or closed peer is noticed late while
memory grows. Cause: `write()` does not provide flow control; failure can surface when the buffer is
drained or closed. Pair writes with `await drain()`, then close and await closure:

```python
# Good
writer.write(payload)
await writer.drain()
writer.close()
await writer.wait_closed()

# Bad: no backpressure or observed shutdown.
writer.write(payload)
```

Prove it with a slow reader and a peer that closes early; the producer must stay bounded and observe
the broken connection.

**Reuse only the pending set from `asyncio.wait()`.** Symptom: a `FIRST_COMPLETED` loop consumes a CPU
without new work finishing. Cause: a completed future remains immediately ready when passed to the
next wait. Carry `pending`, not the original set:

```python
pending = set(tasks)
while pending:
    done, pending = await asyncio.wait(
        pending, return_when=asyncio.FIRST_COMPLETED
    )
    consume(done)
```

Prove it with one fast and one blocked task: each completion is consumed once, and the loop waits for
the blocked task instead of repeatedly returning the first.

## Protect shared state

Do not rely on the apparent atomicity of a built-in operation. Interpreter details change, and a
multi-step invariant is never protected by one atomic-looking mutation.

Prefer passing immutable messages through a queue. When state must be shared, give it one owner or
protect the whole invariant with the appropriate lock:

```python
# Good: the read-modify-write decision is one locked operation.
with self._lock:
    if key not in self._values:
        self._values[key] = build_value(key)
    return self._values[key]

# Bad: two threads can both observe a miss and create competing values.
if key not in self._values:
    self._values[key] = build_value(key)
return self._values[key]
```

Create process-owned clients and connections inside the worker unless the resource explicitly
documents inheritance across the selected process start method.

## Measure before optimizing

First preserve a representative input and observable result. Then profile the relevant path and
measure wall time, CPU, allocations, or I/O according to the suspected limit. Optimize the measured
hotspot and repeat the same measurement.

Prefer algorithm and I/O improvements over local tricks. Removing repeated work or an unnecessary
round trip usually matters more than replacing clear syntax with a micro-optimization.

```python
# Good when all pieces are already available.
text = "".join(pieces)

# Good for incremental writes from branches or callbacks.
buffer = io.StringIO()
for item in items:
    buffer.write(render(item))
text = buffer.getvalue()
```

Do not claim a complexity or speed improvement without evidence from the supported interpreter and
representative data. CPython may optimize operations differently from another Python runtime.

## Use memory techniques deliberately

- Use a generator when consumers can process values once and incrementally. Keep a collection when
  callers need length, indexing, repeated traversal, or a stable snapshot.
- Use `__slots__` only after measuring many long-lived instances. It changes attribute behavior,
  inheritance, weak references, and serialization expectations.
- Stream files and network bodies when the interface permits partial processing. Do not turn a
  small, simple read into a state machine without measured need.
- Bound queues, caches, result sets, and concurrency. An unbounded optimization is an eventual
  memory policy whether or not it was named as one.

## Avoid advanced-pattern traps

- Do not add concurrency to hide slow I/O that should be batched, cached, or removed.
- Do not swallow worker exceptions to keep a batch green; return or record an explicit per-item
  result when partial failure is allowed.
- Do not hold a lock across network I/O, user input, or an unbounded callback.
- Do not share an async client, task, event loop, or synchronization primitive across unrelated
  loop lifetimes unless its documentation permits it.
- Do not add `__slots__`, caching, multiprocessing, or native extensions based on intuition alone.
- Do not replace repository tooling with a generic formatter, linter, type checker, profiler, or
  test runner. Use what the project configures and propose a tooling change separately.
