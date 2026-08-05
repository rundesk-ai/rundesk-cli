"""Common functionality, with no opinion about rundesk.

The bottom of the tree. Everything here is a thing any program might need — keeping a small file
safely, replacing something on disk without a reader ever seeing it half-written, printing a table
that lines up — and **nothing here knows what an install, a release, an agent or a copy is.**

That is the whole membership rule, and it is worth stating as a test somebody can apply: *if this
function had to be told about rundesk to be written, it belongs a layer up.* `paths` reads
`RUNDESK_HOME` and `config` knows what an install may be configured with, so both stay in `core`
however reusable they look. `files` would work unchanged in somebody else's program, so it is
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
| `files` | putting bytes on disk without leaving a reader something half-written |
| `locking` | letting one process at a time change something, with a ceiling on the waiting |
| `programs` | running another program, whether it answers in a moment or runs for hours |
| `scripts` | a directory of numbered scripts, found in order and loaded to run |
| `terminal` | what a person sees: weight, colour, and columns that line up |

`tests/test_layers.py` checks this table against the directory rather than trusting it to be kept —
it had already fallen a module behind by the time anybody noticed, and it is what a reader trusts to
know what is here.

**Few and concrete, rather than many and abstract.** A module here is named for the thing you would
go looking for, and the test is whether somebody hunting "can this agent name be a directory?" would
guess the file. Nobody guesses `naming.py`; everybody guesses `files.py`. That is why these are four
modules rather than the seven thinner ones they started as — `jsonfile`, `staging` and a filename
check are one concern, because they fail together: a name with a separator lands the file somewhere
else, and a write that is not staged lands it half-written.

Never take a name the standard library already has — `logging`, `types`, `select`, `signal`,
`platform`. Anything inside this package would import yours in preference to the real one, and ruff
catches a shadowed builtin but not a shadowed module, so that one is checked in `test_layers.py`
too. Keep this flat until there are eight or ten, and then group by what a module touches rather
than into a drawer called `misc`.
"""
