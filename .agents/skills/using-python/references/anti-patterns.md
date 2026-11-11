# Python anti-patterns

Design choices that work today and cost later. Use this at review time.

**This page is not [documented-traps.md](documented-traps.md).** That page is *bugs* — code that
produces a wrong answer. This page is *design* — code that runs correctly and makes the next change
harder. Report them differently: a trap is a defect, an anti-pattern is a judgement, and saying which
is which is what makes a review credible.

Flag an anti-pattern only when you can name the concrete cost. `reviewing-code` puts it well: flag
complexity "only when it creates a concrete cost or defect risk."

## Structure and abstraction

| Don't | Do | Because |
|---|---|---|
| A class with an `__init__` and one other method | A function | Jack Diederich's *Stop Writing Classes* case: the class is a closure with ceremony. If it has no state between calls, it is not an object |
| Build the abstraction for the second caller you imagine | Wait for the second caller you have | Every speculative parameter is a branch nobody exercises and nobody can delete later |
| A module named `utils`, `helpers`, `common`, `misc` | Name it for the capability | Generic buckets have no owner, so everything lands there and nothing can be moved out |
| Deep inheritance to share code | Composition, or a module-level function | Hynek Schlawack: with inheritance a reader of `self.x` "won't know where `x` comes from." Composition "forces discipline on you, even if it results in clunkiness" |
| A `Repository`/`Manager` wrapping a library that is already the abstraction | Call the library | The wrapper re-exposes the same surface through a hand-written interface, and the swap it enables never happens |
| A metaclass, descriptor, or `__getattr__` to save repetition | Write it out | Each one makes the class unreadable to everyone who did not write it, and undebuggable in a stack trace |
| Build names dynamically — `globals()[f"handler_{x}"]` | A dict of callables | Nothing can grep for the definition, so nothing can safely rename or delete it |
| A package facade re-exporting everything | An explicit `__all__` | Everything imported becomes public API you cannot change |

The test for an abstraction, from the skill's own rule: add one when it "gives one name and one owner
to behavior already repeated or independently meaningful" — not to shorten a file.

## Interfaces and contracts

| Don't | Do | Because |
|---|---|---|
| Return `Result` or `None` or `False` from one function | One return type; raise on failure | Every caller writes a different guard, and one of them checks the wrong falsy value |
| `def render(data, True, False)` | Keyword-only flags, or separate functions | A boolean parameter at a call site says nothing; two of them say less |
| Take and mutate a caller's list | Return a new one, or document the mutation loudly | The caller's variable changes under them — the "mutable presto-chango" as an API design |
| Pass a dict of options through three layers | A dataclass, or explicit parameters | Nothing can tell you what keys exist, and a typo is a silent default |
| `str` for an id, a path, a currency, a state | `NewType`, `Path`, `Decimal`, `Enum` | Primitive obsession: the type system cannot stop you passing a user id where an order id goes |
| Accept `list[X]` when you only iterate | Accept `Iterable[X]` / `Sequence[X]` | Rejects a tuple or generator for no reason — see [typing.md](typing.md) |
| Leak an internal name through the public API | Underscore-prefix internals, curate exports | Anything importable becomes something somebody imports |

## Error handling as design

| Don't | Do | Because |
|---|---|---|
| `except Exception: return None` | Catch what this layer can resolve | The caller cannot distinguish "absent" from "broken", so the bug surfaces three layers away |
| Return an error code | Raise | Python's convention is exceptions; a returned code is a code somebody forgets to check |
| Exceptions for ordinary control flow | A conditional | An exception in the normal path hides the exceptional one |
| One `AppError` for everything | An exception per recoverable case | Callers cannot handle selectively, so they catch broadly, so they catch too much |
| Log **and** re-raise at every layer | Handle once, at the boundary that decides | The same failure appears five times and none of them is the cause |
| Swallow and substitute a default | Fail, or make the fallback explicit and logged | A silent default is a wrong answer that looks like a right one |

EAFP is idiomatic Python — `try/except` rather than a pre-check — but the `try` block stays narrow
enough that only the anticipated failure can occur inside it.

## Non-idiomatic Python

These are readability findings. They are real, and they are the lowest-priority thing in a review.

| Don't | Do |
|---|---|
| `if type(x) == Foo` | `isinstance(x, Foo)` |
| `if x == None`, `if x == True` | `if x is None`, `if x` |
| `for i in range(len(xs)): xs[i]` | `for x in xs`, or `enumerate(xs)` |
| `for i in range(len(a)): a[i], b[i]` | `zip(a, b)` |
| `if key in some_list` in a loop | A `set` — `in` on a list is O(n) |
| `d[k] = d.get(k, 0) + 1` scattered about | `collections.Counter` / `defaultdict` |
| Java-style `get_x()` / `set_x()` | An attribute, or `@property` when there is behaviour |
| `from module import *` | Explicit imports |
| `lambda` assigned to a name | `def` — it gets a real name in tracebacks |
| `os.path.join(...)` strings | `pathlib` (Ruff's `PTH` family) |
| Single-letter names outside a tight comprehension | Names that say what the value is |
| Type in the name — `user_list`, `str_name` | The annotation carries the type |

## State

| Don't | Do | Because |
|---|---|---|
| Module-level mutable state | Pass it, or own it in a class | Import order becomes load-bearing, and tests cannot isolate |
| `global` to write from a function | Return the new value | Hidden dependency: the caller cannot see what changed |
| Work at import time — I/O, network, config parsing, `argparse` | A `main()` guarded by `if __name__ == "__main__"` | Importing the module runs somebody else's program. See [organization-and-naming.md](organization-and-naming.md) |
| A singleton for convenience | An explicit dependency | Untestable, and in a server it is shared across requests |
| Cache with no invalidation story | Decide the story first | A wrong cached value outlives the bug that produced it |

## Testing

| Don't | Do | Because |
|---|---|---|
| Mock what you own | Use the real object; mock the boundary | A test of mocks asserts the mocks were configured |
| Assert on internal calls | Assert on the observable result | The test breaks on refactor and passes on regression |
| One test with fifteen assertions | One behaviour per test | A failure names the behaviour, not a line number |
| `assertTrue(x == y)` | `assertEqual(x, y)` | The failure message shows both values |
| Tests that share mutable state or depend on order | Isolate with fixtures and cleanup | Passes locally, fails in CI, passes on retry |
| Snapshot everything | Assert what matters | Reviewed by approving the diff, which is not review |

Depth in [testing.md](testing.md); choosing what deserves a test is a separate,
language-neutral concern.

## Performance

| Don't | Do | Because |
|---|---|---|
| Optimize before measuring | Profile first | "Measure before optimizing" — the hot path is rarely where it feels |
| Micro-optimize readable code | Fix the algorithm or the I/O | A comprehension rewrite does not repair an O(n²) loop or an N+1 query |
| Concatenate strings in a loop | `"".join(parts)` | Quadratic in total length, per CPython's own FAQ |
| Reach for concurrency to make it faster | Establish the workload is I/O-bound | CPU-bound threads add contention and no throughput |
| Load an entire file or query result to count it | Stream, or aggregate at the source | Memory scales with the input, and the input grows |

## How to report these

1. Name the concrete cost — the change this makes hard, the bug it invites.
2. Say it is a design finding, not a defect, and rank it below anything from
   [documented-traps.md](documented-traps.md) or [security.md](security.md).
3. Propose the smaller alternative, not a rewrite.
4. If the repository already does it this way consistently, say so and defer. PEP 8 is explicit that
   consistency with surrounding code can outweigh a general recommendation, and an isolated
   "improvement" is just a second convention.
