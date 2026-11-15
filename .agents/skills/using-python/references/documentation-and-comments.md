# Python documentation and comments

Document the contract a caller cannot infer from the signature, and comment on implementation
reasoning the code cannot express. Follow the repository's existing docstring dialect and prose
style before applying any fallback here.

## Choose docstring, comment, or neither

| Need | Put it in | Do not put it in |
|---|---|---|
| How a caller uses a public object | Docstring or generated API docs | An implementation comment callers never see |
| Argument meaning, return semantics, side effects, raised errors, restrictions | Function or method docstring | Types repeated from annotations with no added meaning |
| Why an algorithm, workaround, lock, or unusual branch exists | Block or inline comment beside the code | A public docstring unless callers depend on it |
| Obvious mechanics already expressed by clear code | Neither | A comment narrating the next statement |
| Work that must happen later | Tracked issue plus a narrow TODO if local context helps | “TODO: fix this” with no trigger or owner |

Public modules, classes, functions, and methods need usable documentation. A small private helper with
an exact name and obvious behavior does not earn a boilerplate docstring. Non-obvious private logic
still needs its contract or reasoning documented.

## Write useful docstrings

Use triple double quotes. Start with a concise, punctuated summary. PEP 257 prefers an imperative
verb for a function or method; if the repository consistently uses descriptive voice, preserve it.
For multiline text, put a blank line after the summary and keep the remaining indentation uniform.

Do not repeat the signature:

```python
# Good
def load_invoice(path: Path) -> Invoice:
    """Load an invoice and reject unsupported schema versions."""
    ...

# Bad: introspection and annotations already say all of this.
def load_invoice(path: Path) -> Invoice:
    """load_invoice(path: Path) -> Invoice"""
    ...
```

Describe caller-visible behavior: argument meaning, return semantics, mutations, relevant
exceptions, preconditions, ordering, units, external effects, and restrictions. Omit sections that
add nothing. A one-line docstring is enough when the name and signature carry the rest.

PEP 257 does not prescribe Google, NumPy, Sphinx/reStructuredText, or another section dialect. Detect
the repository's format and use it consistently; do not mix `Args:` with `:param:` or NumPy section
underlines in one package.

## Document each object at its boundary

### Modules and packages

State purpose, important usage constraints, import-time behavior, and the intended public surface.
Do not repeat the filename or write a generic label:

```python
# Good
"""Parse vendor invoices without performing network access at import time."""

# Bad
"""invoice_parser module."""
```

A test module needs a docstring only when it explains unusual setup, environment requirements,
fixtures, or a non-obvious way to run it. `"""Tests for invoices."""` adds no information.

### Classes

Describe what an instance represents, its important invariants, lifecycle, and public attributes not
already documented as properties. Do not say merely that it is a class:

```python
# Good
class RetryPolicy:
    """Backoff limits applied to one retryable operation."""

# Bad
class RetryPolicy:
    """Class for retry policy."""
```

For an exception, describe the error condition or state it represents. Avoid `"""Raised when ..."""`
when a direct description is clearer.

### Functions and methods

Write enough for a caller to use the function without reading its body. Document side effects and
failure semantics that annotations cannot express:

```python
def reserve(invoice: Invoice, *, ttl_seconds: int) -> Reservation:
    """Reserve an invoice for exclusive processing.

    The reservation expires after ``ttl_seconds`` and replaces any expired reservation.
    Raise ``InvoiceBusyError`` while another live reservation owns the invoice.
    """
    ...
```

Do not copy a base method's docstring into an override. Inherit it when the contract is unchanged;
document only material differences in side effects, restrictions, or results.

## Keep types and behavior separate

Annotations describe types for tools and readers; Python does not enforce them at runtime. Validate
untrusted data at the boundary even when the signature is annotated.

Use `Any` only where the boundary is genuinely dynamic. Prefer a protocol, union, or concrete
interface when callers depend on behavior.

When annotations already state a type, use prose for meaning:

```python
# Good: the docstring supplies semantics absent from ``int``.
def retry(delay_seconds: int) -> None:
    """Retry after a non-negative delay measured from the last failure."""

# Bad: the prose only repeats the annotation.
def retry(delay_seconds: int) -> None:
    """Args: delay_seconds (int): An integer."""
```

If the project's documentation generator requires types in a structured section, follow that
toolchain. Do not remove required markup in the name of avoiding repetition.

## Write comments for reasoning

Keep comments synchronized with the code. A wrong comment is more damaging than no comment because
it looks authoritative.

Use comments for design reasons, invariants, units, source references, compatibility workarounds,
non-obvious edge cases, or why a simpler-looking alternative is unsafe:

```python
# Good: explains the constraint that makes the branch necessary.
# Keep the previous token until the replacement is durable so a crash cannot revoke both.
write_replacement(token)
delete_previous_token()

# Bad: narrates Python syntax.
# Write the replacement token.
write_replacement(token)
```

Put a block comment immediately before the code it explains and indent it with that code. Use inline
comments sparingly, separated from code by at least two spaces. Prefer clearer names or extracted
logic when a comment is compensating for dense code.

Do not keep commented-out code; version control already does that. Do not explain a workaround
without its removal condition or source issue, because the comment cannot tell a future maintainer
whether the constraint still exists.

## Make TODOs actionable

Prefer an issue for work that needs priority, ownership, discussion, or multiple changes. Keep a
TODO beside code only when the location itself matters, and state the tracked issue or exact event
that makes removal possible:

```python
# Good
# TODO(issue-418): Remove the fallback after the oldest supported server emits v2 records.

# Bad
# TODO: clean this up later
```

Do not use a person's name as the only ownership or context; people and teams change. A stable issue
or technical condition survives them.

## Review documentation failures

- A public caller must inspect implementation code to learn exceptions, mutations, units, or order.
- The docstring repeats the signature, object name, or type annotations without adding semantics.
- One package mixes multiple docstring section formats.
- A comment narrates the next line instead of explaining why it exists.
- Code changed but nearby comments still describe the previous behavior.
- A long docstring teaches a shared concept that belongs in package documentation and is duplicated
  across several APIs.
- An annotation is treated as validation, or a docstring promises types the runtime accepts but the
  implementation does not check.
- A TODO has no issue, removal condition, or concrete next action.
