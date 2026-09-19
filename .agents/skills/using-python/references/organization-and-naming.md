# Python organization and naming

Use these defaults when organizing Python code and the repository has no stronger local convention.
PEP 8 explicitly prioritizes consistency with surrounding code when an existing project uses a
different style.

## Choose boundaries by responsibility

Group related classes and top-level functions in a module named for the capability they implement.
Python does not require one class per file. Add a subpackage when a group has its own vocabulary,
public surface, or dependencies—not merely because a directory looks tidy.

```text
# Good: concrete modules own related behavior.
billing/
├── __init__.py
├── invoices.py       # Invoice, parse_invoice(), overdue_total()
└── payments.py       # Payment, capture_payment(), refund_payment()

# Bad as a default: generic buckets hide ownership.
billing/
├── models.py
├── services.py
├── helpers.py
└── utils.py
```

A specific `models.py` may be correct in a framework that defines that boundary. The problem is not
the word; it is a bucket whose contents have no stronger relationship than “used somewhere.” Follow
framework and repository conventions when they supply the architecture.

Keep the package as shallow as its domain permits. A dotted namespace earns another level when the
level communicates a real grouping. Avoid moving one small function through several packages solely
to satisfy an abstract layer diagram.

## Choose a project layout deliberately

Do not call one layout universally standard:

- A small application or internal script may keep its import package at the repository root.
- An installable distribution may use `src/<package>/` to prevent the working directory from
  accidentally making undeclared files importable and to exercise the installed package.
- A `src` layout requires an installation step for ordinary imports. Adopt it for that isolation,
  not as decoration.

Keep tests, tooling, documentation, and generated artifacts outside the import package unless they
are runtime resources deliberately shipped with it.

## Keep modules safe to import

Module top-level code executes during import. Keep it to definitions, immutable constants, and
deliberate lightweight registration. Put command behavior in a function and keep the entry block
minimal:

```python
"""Read and validate invoice files."""

from __future__ import annotations

__all__ = ["Invoice", "read_invoice"]

from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Invoice:
    number: str

def read_invoice(path: Path) -> Invoice:
    """Read one invoice from path."""
    ...
```

The normal top-level order is module docstring, future imports, module dunders such as `__all__`,
imports, constants, then related definitions. Keep executable entry behavior at the end.

```python
# Good
def main() -> int:
    args = parse_args()
    return run(args)

if __name__ == "__main__":
    raise SystemExit(main())

# Bad: importing this module parses another program's arguments and opens a connection.
args = parse_args()
client = connect(args.endpoint)
run(client)
```

## Make the public API deliberate

An undocumented imported name is an implementation detail; a documented name or deliberate
re-export is a compatibility commitment.

- Leave `__init__.py` empty when the package does not need a facade.
- Re-export only the small interface the package intentionally owns, and list it in `__all__`.
- Prefix internal packages, modules, classes, functions, methods, and attributes with one underscore.
- Use double-leading underscores only for the narrow name-mangling case in inheritance design.
- Never invent `__dunder__` names; Python reserves them for documented protocols.
- Do not use wildcard imports in production modules. They hide name origins and can overwrite names.

```python
# Good: an intentional package facade.
from .client import BillingClient
from .errors import BillingError

__all__ = ["BillingClient", "BillingError"]

# Bad: every imported implementation name leaks through the package.
from .client import *
from .errors import *
```

## Organize functions and classes

Prefer a module function when behavior needs only its arguments. Use an instance method when the
operation belongs to an object's state or invariant. Prefer a module function over a static-only
utility class; use `classmethod` primarily for named constructors or behavior that truly belongs to
the class.

Keep functions focused, but do not enforce a blind line limit. Split when one name cannot accurately
describe all branches, a section has a distinct contract, or nested control flow hides the main path.
Do not extract one-use fragments whose names add no meaning.

Python does not prescribe one class-member order. Follow the repository. With no local convention,
choose one consistent order that makes the public interface easy to scan, such as construction,
public properties and methods, then internal helpers. Do not randomly interleave public and internal
methods or reorder a mature class without a concrete readability gain.

Expose a simple public attribute directly. Use a property only for cheap, unsurprising logic; use a
method when access performs costly work, I/O, or a meaningful mutation.

## Name what the code means

| Construct | Default | Example |
|---|---|---|
| package | short lowercase; underscores sparingly | `billing` |
| module | short lowercase; underscores when clearer | `invoice_parser.py` |
| class | `CapWords` noun | `InvoiceParser` |
| error exception | `CapWords` ending in `Error` | `InvoiceParseError` |
| function or method | `lower_with_underscores`, usually a verb | `parse_invoice()` |
| variable or attribute | `lower_with_underscores` | `invoice_total` |
| constant | `UPPER_WITH_UNDERSCORES` | `MAX_RETRIES` |
| internal name | one leading underscore | `_parse_header()` |
| first instance/class argument | `self` / `cls` | `def create(cls, ...)` |
| keyword collision | one trailing underscore | `class_` |

Use names proportional to their scope. `i` is understandable in a tiny loop; it is not a useful
public parameter. Avoid unfamiliar abbreviations, types embedded in names (`name_string`), vague
verbs (`handle`, `process`) when a concrete one exists, and ambiguous single letters `l`, `O`, and
`I`.

```python
# Good
class InvoiceParseError(ValueError):
    pass

def parse_invoice(source: str) -> Invoice:
    ...

# Bad
class invoice_parser_exception(Exception):
    pass

def ParseInv(s):
    ...
```

## Keep imports explicit

Put imports at the top except for a documented cycle, optional dependency, or deferred-cost reason.
Group standard library, third-party, and local imports according to repository tooling. Import one
module per line; importing several names from one module is fine.

Prefer absolute imports for reusable package code because the source is obvious. Explicit relative
imports can be clearer inside a tightly coupled subpackage. A directly executed module has no package
context, so it cannot rely on relative imports; prefer `python -m package.module` or a real entry
point.

Do not expose a name merely because it was imported into another module. Import from the module that
owns the public contract unless a package facade deliberately re-exports it.

## Review organization failures

- A module name cannot summarize its contents without using “miscellaneous.”
- Importing a module performs I/O, parses arguments, starts threads, or mutates external state.
- Two packages import each other and local imports merely conceal the cycle.
- `__init__.py` re-exports most of the package without an intentional public facade.
- A class contains unrelated methods or only static methods and no class-owned contract.
- Public names expose storage, framework, or transient implementation details callers do not need.
- New files copy Java's one-class-per-file structure without improving Python's module API.
