"""Common functionality, with no opinion about rundesk.

The bottom of the tree. Everything here is a thing any program might need — keeping a small file
safely, replacing something on disk without a reader ever seeing it half-written, printing a table
that lines up — and **nothing here knows what an install, a release, an agent or a copy is.**

That is the whole membership rule, and it is worth stating as a test somebody can apply: *if this
function had to be told about rundesk to be written, it belongs a layer up.* `paths` reads
`RUNDESK_HOME` and `config` knows what an install may be configured with, so both stay in `core`
however reusable they look. `jsonfile` would work unchanged in somebody else's program, so it is
here.

**May import the standard library and nothing else in this product** — not `core`, and certainly not
`lifecycle` or `commands`. That is what makes the direction of the whole tree checkable at a glance:

    commands → lifecycle → core → utils

A module here that reached upward would make the layer above it impossible to test on its own, and
would turn the shared thing into the place domain logic accumulates because it is the file everybody
already imports. Keeping the rule mechanical — *no rundesk imports* — is what stops that happening
gradually.

| Module | Answers |
|---|---|
| `jsonfile` | reading and writing a small JSON file safely |
| `staging` | building something beside what it replaces, and renaming it into place |
| `table` | printing a table whose columns line up |
"""
