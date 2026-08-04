# Working on a checkout

Nothing needs installing. `rundesk` is a plain script: it resolves its own location, puts `src/` on
the path and calls `cli.main`.

```sh
./rundesk status
```

That works — and it answers against **your live install**, because every location defaults downward
from your home. So do this instead:

```sh
./dev status
./dev version
./dev --home /tmp/somewhere status
```

`./dev` runs the same checkout against a scratch root. It prints the root it used on every run:

```console
$ ./dev status
dev: RUNDESK_HOME=/path/to/checkout/.scratch/rundesk-home
WHAT        IS
version     0.37.0
home        /path/to/checkout/.scratch/rundesk-home
program     /path/to/checkout
app         /path/to/checkout/.scratch/rundesk-home/app — not there yet
data        /path/to/checkout/.scratch/rundesk-home/data — not there yet
fit to run  yes
```

## The ordering that matters

`./dev` removes every `RUNDESK_*` variable from the environment **and then** sets the one rundesk
reads. That order is the whole point, and it is worth knowing if you ever write the equivalent by
hand.

Writing the override in front of a scrubbing prefix —

```sh
RUNDESK_HOME=/tmp/x env -u RUNDESK_HOME … ./rundesk env set SOME_KEY   # wrong
```

— sets the variable and then takes it away again, so the default under your home wins. The command
reports an ordinary success and nothing in its output says which directory it used. That has already
put a real credential into a live install once. Put the override *after* the scrubber, or use
`./dev`, which cannot get it backwards.

`XDG_CONFIG_HOME` is scrubbed too. It is not rundesk's variable, which is exactly what makes it
dangerous: any shell may carry one, and anything deriving a directory from it would quietly follow it
out of the scratch root.

## Tests

`unittest`, run directly. No runner to install, and nothing reaches the network.

```sh
python3 scripts/suites          # every suite
python3 tests/test_cli.py       # one of them
```

`scripts/suites` **finds** the suites rather than listing them, so a file added to `tests/` runs the
day it lands, and CI calls the same script — a list kept in two places is a list that disagrees with
itself. It **fails when it finds none**: the runner it replaces globbed a directory that had moved,
matched zero files and printed `parse OK`, and the project lost its only syntax check with nothing
going red.

Read the `Ran N tests` line rather than the word `OK`. `OK` and `OK (skipped=65)` are the same word
to whoever reads a summary, and a suite that skipped everything is not a suite that passed.

### Isolation is asserted, not assumed

Every case inherits `Isolated` from `tests/support.py`, which gives it a temporary root and then
**checks that rundesk resolved that root before the case runs**.

This is worth the code. A case that quietly ran against your live install passes exactly as green as
one that did not, and by the time anybody reads the result the damage is done. The build this
replaces had no shared harness at all: thirty-five suites each isolated a slightly different subset
of a dozen locations, and one of them created real agents on the owner's machine.

Write a new suite by importing `support` first:

```python
import support

class WhatItShouldDo(support.Isolated):
    def test_it_says_which_version_it_is(self):
        code, out, err = self.rundesk("version")
        self.assertEqual(0, code)
```

`self.home` is the scratch root; `self.rundesk(...)` drives the command and hands back
`(exit code, stdout, stderr)`.

## A test is unproven until you have watched it fail

Break the code, run the suite, see red, put the code back. A green test that would stay green with
the feature removed is worse than no test, because it is counted.

Restore from a copy, never from git — the file you are restoring holds everything you have written
and not yet committed:

```sh
cp src/rundesk/paths.py /tmp/paths.keep     # before breaking anything
# … break it, run the suite, read the failure …
cp /tmp/paths.keep src/rundesk/paths.py
```

## Python

The floor is **3.9** — the oldest a fresh macOS ships. A current one catches what only a newer
interpreter minds, so run both when you touch anything structural:

```sh
/usr/bin/python3 scripts/suites     # the floor
python3 scripts/suites              # whatever your shell finds
```

rundesk declares no dependencies. There is no virtualenv to build and nothing to install first.

## Never touch the live install

`~/.rundesk` is a running product with real agents in it, not a fixture. Never install, uninstall,
update, start, stop or write anything there.

Check it before and after anything that writes:

```sh
ls ~/.rundesk
```
