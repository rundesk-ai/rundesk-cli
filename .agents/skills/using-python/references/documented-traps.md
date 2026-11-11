# Documented Python traps

Traps that CPython's own FAQ, the linters the ecosystem runs, and Python maintainers have already
written down. Each entry names the trap, what actually happens, and the fix. Rule codes are given so
a finding can be checked against the tool that reports it.

The two catalogs worth knowing exist: **flake8-bugbear** (`B0xx`, also Ruff's `B`) is a list of real
Python traps, and **flake8-bandit** (`S`) is the security equivalent — see
[security.md](security.md). A rule exists in either because enough people hit the trap.

## Names, values, and mutation

**Assignment never copies.** `y = x` binds a second name to the same object. CPython's FAQ: "doing
`y = x` doesn't create a copy of the list – it creates a new variable `y` that refers to the same
object." Ned Batchelder calls the consequence the *mutable presto-chango*: "changes in a value are
visible through all of its names." Three conditions are needed — a mutable value, more than one name,
and a mutation through one of them.

```python
nums = [1, 2, 3]
tri = nums
nums.append(4)      # tri is now [1, 2, 3, 4]
```

Copy deliberately: `list(x)` or `x[:]` for a shallow copy, `copy.deepcopy(x)` when the nesting matters.

**`[[0] * 3] * 3` makes three references to one inner list.** Writing to `grid[0][0]` writes to all
three rows. Build it with a comprehension: `[[0] * 3 for _ in range(3)]`.

**Augmented assignment on a mutable inside a tuple both fails and succeeds.**
`a_tuple[0] += ['x']` raises `TypeError` *and* leaves the list mutated, because `+=` on a list
extends in place and then attempts the rejected item assignment.

**`is` is not `==`.** Use `is` only for `None`, singletons, and after `new = old`. The FAQ:
"identity tests should not be used to check constants such as `int` and `str` which aren't guaranteed
to be singletons." Small-integer and string interning make `is` appear to work until the value grows.

**Assigning anywhere in a function makes the name local everywhere in it**, so a read before the
assignment raises `UnboundLocalError` rather than reading the global. Declare `global` or `nonlocal`,
or better, pass the value in and return the new one.

## Definition time versus call time

**Mutable default arguments** (`B006`). The FAQ: "default values are created exactly once, when the
function is defined. If that object is changed… subsequent calls to the function will refer to this
changed object." Default to `None` and build inside.

**Function calls in defaults** (`B008`) have the same shape and are easier to miss:

```python
def f(when=datetime.now()):     # evaluated once, at import
def f(when=None): when = when or datetime.now(tz=UTC)
```

**`ContextVar` with a mutable or computed default** (`B039`) — evaluated once, so every `.get()`
returns the same instance.

**A mutable class attribute is shared by every instance.** Same trap, different scope; assign in
`__init__` or use a dataclass `field(default_factory=...)`.

## Loops and closures

**Late binding** (`B023`). A function defined in a loop reads the loop variable when it is *called*,
not when it is defined. The FAQ: "`x` is not local to the lambdas, but is defined in the outer scope,
and it is accessed when the lambda is called — not when it is defined." Every closure sees the final
value. Bind it as a default (`lambda n=x: ...`) or use `functools.partial`.

**A loop variable that shadows the iterable** (`B020`) — `for items in items:` — silently changes what
is being iterated.

**Mutating a list while iterating it** skips elements. Iterate over a copy, or build a new list.

**`itertools.groupby()` groups are consumed once** (`B031`). Using a group a second time yields
nothing. Materialize with `list()` if you need it twice.

## Exceptions

**Bare `except:`** (`B001`) catches `KeyboardInterrupt`, `SystemExit`, and `MemoryError`. So does
`except BaseException:` without a re-raise (`B036`). Catch `Exception` at most, and only where the
layer can act.

**`return`, `break`, or `continue` inside `finally`** (`B012`) swallows the in-flight exception or
discards the return value from the `try`. It is a silent correctness bug.

**`try/except/pass`** (`S110`) and `try/except/continue` (`S112`) discard the failure with no record.
If the failure is genuinely expected, `contextlib.suppress(SpecificError)` says so; otherwise log it.

**`assertRaises(Exception)` / `pytest.raises(Exception)`** (`B017`) passes when the code under test
raises for an unrelated reason — including a typo in the test. Assert the specific exception.

**`assert` disappears under `-O`** (`B011`, `S101`). Never use it to validate input, enforce
invariants in production, or check permissions. Raise explicitly. It remains the right tool inside
tests.

**Duplicate exception types across `except` clauses** (`B025`) — only the first is reachable. And
`except (X,):` (`B013`) is a redundant one-tuple.

**A custom exception whose `__init__` does not pass its arguments to `super().__init__()`** (`B042`)
breaks pickling and copying — which surfaces when the exception crosses a process boundary.

**`add_note()` without a re-raise** (`B040`) annotates an exception nobody sees.

## Classes, objects, and decorators

**`functools.lru_cache` or `@cache` on a method leaks memory** (`B019`). `self` is part of the cache
key, so every instance is retained for the lifetime of the process. Cache a module-level function, or
use a per-instance cache such as `functools.cached_property`.

**An ABC with no `@abstractmethod`** (`B024`), or an empty method in an ABC that is missing the
decorator (`B027`) — the subclass that forgets to implement it instantiates fine and fails later.

**`hasattr()` runs the attribute lookup and discards the result.** Hynek Schlawack's argument: it is
"a dangerous misnomer" because a property that raises is reported as a missing attribute. Prefer
`getattr(x, "y", None)` or a narrow `try/except AttributeError`. For callables, `callable(x)` rather
than `hasattr(x, "__call__")` (`B004`).

**Most decorators break the signature.** `functools.wraps` copies the name and docstring but the
wrapper's signature replaces the real one, so introspection, debuggers, autocomplete, and frameworks
that dispatch on argument count all see the wrong thing. Keep decorators few and simple, accept
`*args, **kwargs` honestly, and reach for a signature-preserving helper when the wrapped callable's
signature actually matters.

**Prefer composition to subclassing.** Schlawack's case: with inheritance a reader of `self.x` "won't
know where `x` comes from and it takes research and mental energy to find out." Composition "forces
discipline on you, even if it results in clunkiness." This is why `attrs` and `dataclasses` are
decorators rather than base classes.

**`getattr`/`setattr`/`delattr` with a literal name** (`B009`, `B010`, `B043`) — write `x.attr`.

**`warnings.warn()` defaults to `stacklevel=1`** (`B028`), which points at your own module instead of
the caller. Pass `stacklevel=2`.

## Dataclasses

**A mutable default raises at class creation** — the one trap Python turned into an error. Since 3.11
"unhashable objects are now not allowed as default values." Use `field(default_factory=list)`.

**A field without a default cannot follow one with a default.** `TypeError`, "whether this occurs in a
single class, or as a result of class inheritance" — which is how it appears in a base class you did
not write. `kw_only=True` removes the ordering constraint.

**`eq` and `frozen` decide hashability.** With `eq=True, frozen=False` (the default) `__hash__` is set
to `None` and instances are unhashable. `frozen=True` makes them hashable. `order=True` with
`eq=False` raises `ValueError`.

**The generated `__init__` does not call the base class `__init__`.** Call it from `__post_init__` if
the base needs it.

**`slots=True`** conflicts with parameterized `__init_subclass__` (`TypeError`), and the docs warn:
"do not use `__slots__` to retrieve the field names of a dataclass. Use `fields()` instead."

**`replace()` and `init=False` fields**: they are "not copied from the source object" but
re-initialized in `__post_init__`.

## Dates and times

The `DTZ` family exists because naive datetimes are a durable source of production bugs.

| Trap | Rule | Fix |
|---|---|---|
| `datetime.now()` with no tz | `DTZ005` | `datetime.now(tz=UTC)` |
| `datetime.utcnow()` | `DTZ003` | `datetime.now(tz=UTC)` — **deprecated, removed in 3.15** |
| `datetime.utcfromtimestamp()` | `DTZ004` | `datetime.fromtimestamp(t, tz=UTC)` — same removal |
| `datetime.today()` | `DTZ002` | `datetime.now(tz=UTC)` |
| `datetime.fromtimestamp()` with no tz | `DTZ006` | pass `tz=` |
| `strptime()` without `%z` | `DTZ007` | parse the offset, or attach one explicitly |
| `date.today()` | `DTZ011` | derive from an aware datetime |

`utcnow()` is the sharpest: it returns a **naive** datetime holding UTC, so comparing it with an aware
one raises, and comparing it with local time is silently wrong.

Store and compute in UTC; convert at the presentation boundary only.

## Logging

**Never format the message yourself** (`G001`–`G004`). Pass the format string and the arguments:
`logger.info("processed %s in %s", name, elapsed)`. Formatting eagerly does the work even when the
level is disabled, and it destroys the grouping key that log aggregators use.

**`logger.exception(...)` inside the handler**, not `logger.error(..., exc_info=True)` (`G201`), and
never `.exception()` outside an exception handler (`LOG004`).

**`logging.getLogger(__name__)`** (`LOG002`), not a bare root logger (`LOG015`) and not a directly
constructed `Logger` (`LOG001`).

**A library configures no handlers.** Add a `NullHandler` and let the application decide; calling
`logging.basicConfig()` from a library hijacks the host application's logging.

## Strings and collections

**Building a string in a loop is quadratic.** The FAQ: "each concatenation creates a new object… the
total runtime cost is quadratic in the total string length." Collect into a list and `"".join(...)`.

**`.strip("abc")` removes characters, not a substring** (`B005`) — a permanent source of surprise. Use
`removeprefix()` / `removesuffix()`.

**Duplicate items in a set literal** (`B033`) and repeated keys in a dict literal (`B041`) collapse
silently.

**A dict comprehension with a constant key** (`B035`) produces a one-entry dict.

**`re.sub`/`re.split` take `count`/`flags` positionally** (`B034`) — pass them by keyword, because the
positional order is not what most people assume.

## Command-line input

**An open pipe is not permission to read stdin.** Symptom: an unattended command hangs only under a
runner or pipeline. Cause: `not sys.stdin.isatty()` can mean a pipe whose writer is still open but has
sent neither data nor EOF, so `read()` waits indefinitely. Require an explicit flag or subcommand:

```python
# Good: the caller opted into consuming stdin.
if args.stdin:
    payload = sys.stdin.read()

# Bad: non-interactive input is treated as an instruction to wait.
if not sys.stdin.isatty():
    payload = sys.stdin.read()
```

Prove both paths: redirect stdin from the platform null device (`/dev/null` on POSIX, `NUL` on
Windows) for the no-input case, then hold a pipe's writer open without writing. Only the explicit
stdin mode should wait for the second case.

## Async

**A fire-and-forget task can be garbage collected mid-flight.** The event loop keeps only weak
references, so a task nothing holds "may get garbage collected at any time, even before it's done."
Hold a reference:

```python
background = set()
task = asyncio.create_task(work())
background.add(task)
task.add_done_callback(background.discard)
```

`asyncio.TaskGroup` is the modern answer — it owns the tasks and will not exit until they finish.

**Blocking calls stall everything.** A one-second CPU-bound call inside a coroutine delays every other
task by a second. Move it to `asyncio.to_thread()` or an executor. The `ASYNC` rule family finds
blocking calls inside `async def`.

**An un-awaited coroutine never runs** and warns only at garbage-collection time. An exception set on
a future nobody awaits is likewise only reported when it is collected.

See [advanced-patterns.md](advanced-patterns.md) for task ownership, cancellation, and shutdown.

## Deprecations that bite

Check the runtime floor before modernizing, and check these before assuming existing code still works:

| Removed / removing | Version | Replacement |
|---|---|---|
| `datetime.utcnow()`, `utcfromtimestamp()` | 3.15 | `datetime.now(tz=UTC)`, `fromtimestamp(t, tz=UTC)` |
| `asyncio` event-loop policy API | 3.16 | `asyncio.run(main(), loop_factory=...)` |
| `asyncio.iscoroutinefunction()` | 3.16 | `inspect.iscoroutinefunction()` |
| `typing.ByteString`, `collections.abc.ByteString` | 3.17 | `bytes \| bytearray \| memoryview` |
| `cgi`, `telnetlib`, `crypt`, `imghdr`, `pipes`, `nntplib`, and 13 more | **removed in 3.13** (PEP 594) | PyPI backports such as `standard-cgi` exist |
| `lib2to3` / `2to3` | removed in 3.13 | — |
| `logging.warn()` | pending | `logging.warning()` |
| `typing.List`, `Dict`, `Tuple`, … | soft-deprecated since 3.9 | builtin generics |

Python 3.9 reached end of life on **31 October 2025**, and 3.10 reaches it on **31 October 2026**. A
repository still pinned to either is worth flagging — but do not raise its floor without being asked.

## Review order for these

1. Anything that silently produces a wrong value — shared mutable state, late binding, naive datetimes.
2. Anything that hides a failure — bare `except`, `try/except/pass`, `finally` returns.
3. Anything that leaks — `lru_cache` on methods, unowned tasks, unclosed resources.
4. Anything that will stop working — deprecations against the declared floor.
5. Style and simplification last.
