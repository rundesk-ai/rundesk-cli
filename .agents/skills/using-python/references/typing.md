# Typing

Annotations are static metadata. The `typing` docs are explicit: "the Python runtime does not enforce
function and variable type annotations." Nothing here changes behaviour at run time unless a library
such as Pydantic reads the annotations and validates deliberately.

## Match the runtime floor

Annotation syntax is version-gated, and this is the most common way typed code breaks a supported
runtime. Check `requires-python` before modernizing.

| Form | Needs | Older form |
|---|---|---|
| `list[int]`, `dict[str, int]` | 3.9 | `List[int]`, `Dict[str, int]` |
| `X \| None` | 3.10 | `Optional[X]` |
| `Self` | 3.11 | `TypeVar` bound to the class |
| `Required` / `NotRequired` | 3.11 | `total=False` on a second TypedDict |
| `type Alias = ...`, `def f[T](...)` | 3.12 | `TypeAlias`, explicit `TypeVar` |

`from __future__ import annotations` makes annotations strings, which lets newer *syntax* parse on an
older runtime — but it does not make `Self` exist for anything reading annotations at run time. Use it
for the syntax, not as a compatibility guarantee.

The `typing.List`/`Dict`/`Tuple` aliases are soft-deprecated since 3.9. Do not churn a working
codebase to remove them; do use builtin generics in new code.

## Annotate the boundary first

Annotate what other modules call: public functions, methods, and dataclass fields. Inside a short
function, an annotation on every local is noise the checker can infer.

Do annotate a local when the checker cannot infer it — an empty collection is the usual case:

```python
seen: set[str] = set()          # without this, the element type is unknown
results: list[Result] = []
```

## Be liberal in, specific out

Accept the widest type the function actually needs; return the narrowest one it actually produces.

```python
# Good: accepts a list, a tuple, a generator
def total(values: Iterable[int]) -> int: ...

# Worse: rejects a tuple for no reason
def total(values: list[int]) -> int: ...
```

Use `Iterable`, `Sequence`, `Mapping`, and `Collection` from `collections.abc` for parameters; use
concrete `list`/`dict` for returns. The reason is variance: `list` is invariant, so a `list[Dog]` is
not a `list[Animal]` and a function taking `list[Animal]` rejects it. `Sequence` is covariant and
accepts both.

Never mutate a parameter typed as `Sequence` or `Mapping` — the type is the promise that you will not.

## Use Protocol for structural typing

A `Protocol` types what an object *does*, not what it inherits from. It keeps a public API flexible
and avoids forcing callers to import your base class.

```python
class SupportsRead(Protocol):
    def read(self, size: int = -1, /) -> str: ...

def parse(source: SupportsRead) -> Config: ...
```

Two documented limits on `@runtime_checkable`:

- "`@runtime_checkable` will check only the presence of the required methods or attributes, not their
  type signatures or types" — so it is a shallower check than it looks.
- An `isinstance()` check against a runtime-checkable protocol "can be surprisingly slow"; prefer
  `hasattr()` in a hot path.

Use an ABC instead when you want shared implementation or a nominal relationship enforced.

## Constrain values, not just shapes

- **`Literal`** for a fixed set of accepted values — `Literal["r", "w", "a"]` catches a typo that
  `str` cannot.
- **`Enum`** when the set is a domain concept with behaviour or iteration.
- **`NewType`** to keep two `int`s apart: `UserId = NewType("UserId", int)`. At run time it returns its
  argument unchanged — it is purely a checker-level distinction, and arithmetic on it degrades back to
  the base type.
- **`Final`** for constants that must not be reassigned or overridden. "There is no runtime checking of
  these properties."
- **`TypedDict`** for a dict with a known shape — an API response, a config blob. Use `Required` /
  `NotRequired` per key rather than splitting into two classes.

Prefer a dataclass to a `TypedDict` when the thing has behaviour or invariants; `TypedDict` is for
data that genuinely stays a dict.

## Keep Any and ignores accountable

`Any` is not "unknown" — it is "stop checking." mypy's framing: `Any` types "let you lie to mypy, and
this could easily hide bugs." An `Any` in a return type silently disables checking in every caller.

- Use `object` when the value is genuinely unknown; it forces a narrowing check before use.
- Use `Any` at a boundary you cannot type — a dynamic plugin, an untyped dependency — and narrow it
  immediately.
- Every `# type: ignore` gets a specific code and a reason: `# type: ignore[arg-type]  # upstream stub
  is wrong, see #412`. Turn on `warn_unused_ignores` so they are removed when the cause is fixed.

Narrow with `isinstance`, an `assert`, or a guard clause — checkers understand all three. For an
exhaustive match, `assert_never` in the fallback turns a newly added enum member into a type error
rather than a silent fall-through.

## Avoid import cycles with TYPE_CHECKING

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myapp.orders import Order

def summarize(order: "Order") -> str: ...
```

The import happens only for the checker, so it cannot create a cycle or a startup cost. Ruff's `TC`
family flags imports that could move into this block. With `from __future__ import annotations` the
quotes are unnecessary.

## Configure the checker

Types that nothing checks are comments that drift.

- Run **mypy** or **pyright** in CI. Aim for `--strict`; mypy's own guidance is that "an excellent goal
  to aim for is to have your codebase pass when run against mypy `--strict`."
- Adopt it incrementally on an existing codebase: start with `warn_unused_configs`,
  `warn_redundant_casts`, `warn_unused_ignores`, `strict_equality`, then tighten per module.
- **An unannotated function body is not checked by default.** This is the biggest surprise when
  introducing mypy: adding annotations to a function's signature is what turns checking on inside it,
  so coverage grows in steps rather than smoothly.
- Keep the config in `pyproject.toml` beside the lint config, and pin the checker version — a checker
  upgrade is a code change.

## Typing traps

- **Annotations do not validate.** A function annotated `-> int` can return a string. Validate at the
  boundary if the data is external.
- **`Optional[X]` means the value can be `None`**, not that the parameter has a default. `def f(x:
  int | None)` still requires an argument.
- **Implicit `Optional` is gone.** `def f(x: int = None)` is an error in modern checkers; write
  `int | None = None`.
- **Mutable default plus annotation is still a mutable default.** The type checker will not save you
  from `B006`.
- **`list` is invariant.** `list[Dog]` is not a `list[Animal]`. Use `Sequence` for read-only parameters.
- **A bare `Callable` accepts anything.** Spell the signature: `Callable[[int, str], bool]`.
- **`cast()` does nothing at run time.** It is an assertion to the checker, and it is wrong as often as
  the annotation it overrides.
- **`@runtime_checkable` does not check signatures**, only attribute presence.
- **Deferred annotation evaluation changed in 3.14** (PEP 649). Code that reads `__annotations__`
  directly should go through `inspect.get_annotations()` or `typing.get_type_hints()`.
