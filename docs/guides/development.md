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
version     <version>
home        /path/to/checkout/.scratch/rundesk-home
program     /path/to/checkout
app         /path/to/checkout/.scratch/rundesk-home/app — not there yet
data        /path/to/checkout/.scratch/rundesk-home/data — not there yet
fit to run  yes
```

### Testing an installed scratch root

When the test needs the installed launcher, make the root and command link disposable and remove
them through Rundesk when finished. The explicit root keeps this workflow away from the owner's
install, and `--purge` is safe here because the target is disposable:

```sh
scratch_root=$(mktemp -d /tmp/rundesk-scratch.XXXXXX)
RUNDESK_HOME="$scratch_root" ./rundesk install --source "$PWD" --bin-dir "$scratch_root/bin"
RUNDESK_HOME="$scratch_root" "$scratch_root/bin/rundesk" status

# run the installed-agent tests here
RUNDESK_HOME="$scratch_root" "$scratch_root/bin/rundesk" uninstall --confirm --purge \
  --root "$scratch_root"
```

Do not replace the explicit `RUNDESK_HOME` with a bare checkout command. A checkout has no
installed root to infer, while an installed `<root>/app/rundesk` launcher can safely select its own
root when the variable is absent. An explicit value always wins, keeping scratch and test installs
isolated.

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

**Run a suite with `-B` when you have been editing between runs.** `python3 -B tests/test_env.py`
writes no bytecode, and the reason is worth knowing: a suite that rewrites a source file and runs
again — a mutation check, proving a test fails before it passes — can be answered from a `.pyc`
compiled from the version before the edit. It has produced a green run against code that was
broken, and a red one against code that was fine, twice in one day. `scripts/suites` disables
bytecode in the environment it gives every suite, so installed copies and child interpreters inherit
the setting too; a hand-run loop does not.

`scripts/suites` **finds** the suites rather than listing them, so a file added to `tests/` runs the
day it lands, and CI calls the same script — a list kept in two places is a list that disagrees with
itself. It **fails when it finds none**: the runner it replaces globbed a directory that had moved,
matched zero files and printed `parse OK`, and the project lost its only syntax check with nothing
going red.

Read the `Ran N tests` line rather than the word `OK`. `OK` and `OK (skipped=65)` are the same word
to whoever reads a summary, and a suite that skipped everything is not a suite that passed.

### The longest suite is the run

Suites run eight at a time, each in an interpreter of its own, and **a whole file is the unit of
parallelism** — so no run finishes before its slowest suite does, however much idle machine is
sitting beside it. When one suite grows to several times its neighbours, the answer is to split it
rather than to add workers; `tests/test_gateway_host.py` and `tests/test_gateway_channels.py` are
one such split, sharing their harness through `tests/fixtures_gateways.py`.

The runner starts the slowest suites first, which it can only do because it writes down how long
each one took, in `.scratch/suite-seconds.json`:

- it is **learned, never written by hand** — a list of durations kept by hand disagrees with the
  suites within a month;
- it decides only what *starts* first. The report stays in the order suites were found in;
- a suite it has never heard of starts before every suite it has, on the grounds that an unmeasured
  suite may be the new slowest one; and
- missing, corrupt, or from an older set of suites, it is simply ignored. A cold checkout — CI, or
  your first run here — has none, and goes in the order the suites were found in.

So nothing about a run's *result* depends on that file, and there is never a reason to edit it.

`python3 scripts/suites -1` runs them one at a time, for a suite that only fails under load. It
deliberately records nothing: a suite timed with the machine to itself is a different measurement
from the one the ordering wants.

### A concrete `TestCase` is not a helper base

`unittest` inherits test methods, so subclassing a class that holds cases in order to reach its
`setUp` or its helpers **re-runs every one of those cases**. Put the helpers in a base that holds no
`test_` method of its own — `WithAChannel` and `RemovingAnInstall` are there for exactly this — and
let the cases live in a leaf. Three classes here had borrowed a concrete one, which ran sixty-eight
cases a second and third time and cost a hundred and five seconds of every run.

### The network is closed off, not merely avoided

Every case runs with the proxy variables pointed at a closed port, so **nothing a suite starts can
leave the machine** — not the command under test, and not a subprocess three levels below it.

That last part is why it is done in the harness rather than left to each case. A case can drive the
product with `asking=` and `fetching=` replaced and still reach GitHub, because `install` proves the
command it placed by *running* it, and what it runs is a whole rundesk with its own opinion about
what to look up. That is not hypothetical: `tests/test_install.py` spent half its wall clock on
GitHub round-trips while every case passed, and the only visible symptom was that running two
interpreters at once turned four suites red for reasons nobody could attribute to anything.

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
cp src/rundesk/core/paths.py /tmp/paths.keep     # before breaking anything
# … break it, run the suite, read the failure …
cp /tmp/paths.keep src/rundesk/core/paths.py
```

## Python

The floor is **3.9** — the oldest a fresh macOS ships. A current one catches what only a newer
interpreter minds, so run both when you touch anything structural:

```sh
/usr/bin/python3 scripts/suites     # the floor
python3 scripts/suites              # whatever your shell finds
```

**Nothing under `src/rundesk/` imports anything but the standard library**, so there is nothing to
install before running the suite or the command. What `requirements.txt` pins is for *adapters* —
separate programs on the far side of a pipe, which is the only reason reaching Discord is compatible
with a product whose own code imports nothing. `rundesk install` builds those into `app/.venv`; a
checkout has no such directory and needs none, because nothing you run here imports them.

## How the code is written

The conventions are ordinary and the code already keeps them; [`ruff.toml`](../../ruff.toml) is where a
machine can check that, and CI does on every pull request. It is **not** a dependency of the product
— it is fetched in CI and nothing a person installs ever sees it, which is why it is absent from
`requirements.txt` even though that file is no longer empty.

You do not need it to work here. If you want it:

```sh
python3 -m venv /tmp/lint && /tmp/lint/bin/pip install ruff==0.16.1
/tmp/lint/bin/ruff check src tests scripts/suites rundesk
```

What it enforces is the part that catches a mistake — an unused import, an import block in a
different order from every other file, a bare `except Exception` that nobody marked as deliberate, a
name that shadows a builtin. What it deliberately does not enforce is line width: this code is
written to a hundred columns and a handful of lines run over, all of them sentences in a docstring,
and having a linter rewrap somebody's prose costs more than the ragged edge does.

Two things it cannot check, and they matter more than anything it can:

- **Everything is annotated.** Every function in `src/` says what it takes and what it gives back.
  The ones worth being careful about are the collaborators — `release.Asking` and `update.Fetching`
  are the two things in this product that leave the machine, and they are named types so that
  "pass the network in" is a contract rather than a convention somebody has to be told about.
- **A docstring says why, not what.** The reasoning is the part that cannot be recovered from the
  code, and most of these modules exist because a previous version of them got something wrong. Say
  which thing.

## Never touch the live install

`~/.rundesk` is a running product with real agents in it, not a fixture. Never install, uninstall,
update, start, stop or write anything there.

Check it before and after anything that writes:

```sh
ls ~/.rundesk
```
