# What Python and its standard library actually do

Distilled 2026-08-04 out of the previous build's friction log and the docstrings in its source —
both gitignored, reference-only, and expected to be deleted. Every entry cost that build at least
one attempt, and most of them cost more: the shape they share is that the failure names something
other than its cause. Unless a line says otherwise these were established between 2026-07-24 and
2026-08-03, against CPython 3.9.6 (the floor) and 3.14 (whatever a developer's shell reached). Each
line says how it is known — **measured** means somebody ran it and kept the output, **read** means
it came from the language's own documentation.

The interpreter macOS ships, and what it does with bytecode, is in [`macos.md`](macos.md).

---

## asyncio, when the other end is a program

**`Process.wait()` resolves when every pipe closes, not when the process exits.** Measured, against
a reproduced hang. Anything the program left running inherited the far end of its pipes and holds
them open, so waiting on the exit lands hours late or never. Watch `proc.returncode` in short spells
instead — it is set promptly. This reads exactly like a deadlock in your own code.

**Giving a program `stderr=PIPE` with nothing reading it deadlocks the program.** Measured. It does
not present as a deadlock either: the child fills the pipe buffer and stops, and half an hour later
you have a perfectly healthy-looking process that has gone quiet. Anything that opens a second
stream must start a task that drains it to end-of-file for the program's whole life, whether or not
the caller wants what is on it.

**`StreamWriter.write()` never blocks and never raises.** Measured. On a program that has gone it
silently discards what it was given, and asyncio swallows the `BrokenPipeError` without it even
reaching the loop's exception handler. `await drain()` is the only place a failed write is reported,
so never write without it.

**`asyncio.wait({a, b})` returns instantly, forever, once one of them is already done.** A completed
future stays done, so the loop spins at full speed. Drop it from the set after it fires.

**`connect_read_pipe` hands the descriptor to a transport that closes the file object itself.**
Measured: wrapping the call in `with os.fdopen(fd, "rb")` closes it underneath the transport, and
asyncio logs `OSError: [Errno 9] Bad file descriptor` from `_read_ready` — in a test case that has
already passed. Wait for the transport to report itself closed instead of closing it yourself. It is
worst in the cancellation case, where the loop leaves before the transport has seen the end at all.

**A task `ensure_future`d and cancelled before the loop ever ran it never executes its `finally`.**
Measured, and it makes a test lie: a case that starts work and cancels it immediately finds the
bookkeeping the `finally` clears still populated, and reads as the cleanup being broken. One `await
asyncio.sleep(0)` between starting and cancelling makes the case about what it says it is about.

---

## Reading standard input

**`sys.stdin.readline()` on an open pipe with nothing in it blocks until the far end closes, which
may be never.** Measured: a suite ran for 12 seconds with `< /dev/null` and never finished without
it, and nothing in the output named the command that was reading. That exact shape — an open pipe
nobody will write to — is what a brain's tool shell hands its children, so it is the ordinary case
rather than an edge one.

The rule that follows is a design rule and this build already holds it: **reading standard input is
asked for and never inferred.** A command that decides to read stdin because it is "not a terminal"
hangs whatever is running it. And when a suite that used to pass suddenly never ends, run it with `<
/dev/null` before looking at anything else; finishing then is the whole diagnosis.

---

## Names, imports and definitions

**A default argument is bound once, when the file is read.** So a module-level constant used as a
default (`def __init__(self, held=HELD_BYTES)`) cannot be replaced by a test that rebinds the
constant, and the case passes against unbounded behaviour. Resolve it in the body. This build states
the same rule for network calls in `AGENTS.md`; the general form is the one to remember.

**Importing a module shadows a same-named function in the importing file, and nothing fails at
import.** Measured, expensively: `from rundesk import handoff` inside a module that defined its own
`handoff()` bound the module over the function at module level, and every later
`handoff.safe_label(...)` died with `AttributeError: 'function' object has no attribute
'safe_label'` — 117 errors, none of them near the import, in a module that still parsed. Grep the
file for `def <name>` before importing a module of that name, and alias when they collide.

**Moving a decorated function by its `def` line leaves the decorator behind, and it then wraps the
next function.** Measured: lifting one function out of a module left a `@contextlib.contextmanager`
above the one below it, which began returning a context manager instead of a path — and every
failure landed forty tests away, naming neither function. When you move a definition, take it from
the first line of its decorator list, and assert the moved text still starts with that decorator.

**A module-level constant that moves takes every test rebinding of it with it.** Measured. A suite
that turns a patience constant down so a waiter does not really wait reads it off the module global
at call time, so moving the constant to another module leaves the rebinding pointing at nothing —
and the suite still passes, just slowly. Never re-export a moved constant for convenience, and grep
the tests for `<module>.<CONST>` in the same commit that moves one.

**An import that looks dead can be the seam a collaborator arrives through.** Measured, and it beat
two reviewers and an AST pass: a module passed itself as a default collaborator, so a name reached
through that collaborator was never spelled anywhere in the file. Before deleting an import from a
module that is somebody's injected default, check what the callers reach for on the injected name.

---

## argparse

**A greedy positional and a subparser cannot share a slot.** An optional positional (`nargs="?"`)
followed by `add_subparsers()` makes argparse match the *value* against the subcommand choices, so
`foo bar` dies with `invalid choice: 'bar'`. The incident is in
[`the-old-build.md`](the-old-build.md); this build takes the verb-first spelling because of it.

**`nargs="*"` is the trap between `nargs="+"` and splitting the tail yourself.** Measured. argparse
carries a `--` tail into a *required* greedy positional on its own, which is why a verb with
`nargs="+"` worked for a year without anything special. Relax it to `"*"` so the verb can take an
option instead, and argparse binds zero eagerly and reports the program as `unrecognized arguments`
— and worse, an option *inside* the tail is read as the verb's own. A verb that grows options of its
own has to have its tail split off in front of the parser.

**argparse spends exit code `2` on a usage error.** Read. Anything else a command wants to say has
to use a different one, and the difference matters because "you typed it wrongly" and "this cannot
be done" want opposite things done about them.

---

## unittest, and how a test here is proved

Every one of these is measured, and every one of them makes a suite report a success it did not
earn.

**A class defined after the `if __name__ == "__main__"` guard never runs, and the suite still says
`OK`.** Python reaches the runner before the class is defined. The count silently stays where it was
— one suite reported the same 184 cases with a new four-case class in it. Keep that block last, and
check the count moved.

**A class inserted between two methods of an existing class adopts every method below it.**
Measured: four methods and a helper moved into the new class, ran against its `setUp`, and died on
errors nowhere near the edit. Anchor a new class on the *next* `class` line — and where the classes
carry decorators, anchor on the decorator line, because landing between a decorator and its class
produces an `IndentationError` pointing at the first method of the block you inserted. Check `grep
-n "^class \|^@"` before and after: the count moves by one and nothing else does.

**A helper called `_outcome` overwrites unittest's own.** `unittest` keeps the running case's
`_Outcome` object on `self._outcome`, so a helper of that name shadows it and every case using it
dies with `TypeError: '_Outcome' object is not callable`, pointing at the call site and saying
nothing about the collision. `_result`, `_subtest` and `_cleanups` are the same trap.

**`-k` takes a substring, not an expression.** `-k "a or b"` matches no test name at all, runs
nothing, and prints `NO TESTS RAN` — which in a probe reads exactly like "the test passed". Pass
`-k` twice.

**Read the `Ran N tests` line, not the word.** `OK (skipped=65)` and `OK` are the same word to
whoever reads a summary, and a suite that skipped everything is not a suite that passed. This
build's `AGENTS.md` already says so; the entry that earned it is worse than the rule sounds — one
suite skipped every case for months because a loader raised and a bare `except BaseException` set
the module to `None`, and the summary said `ok` throughout. The rule that came out of it: **a suite
may only skip for the reason skipping is for**, and whether the thing under test exists is asked
separately from whether its dependency is present.

**A probe that ran zero tests has proved nothing**, and a probe that broke the wrong thing has
proved nothing either. Measured: an attempt to prove that a migration runner kept both copies of a
file across a failed step broke the *cleanup* — but a step that dies never returns its list, so
there was nothing to clean up on the path the claim was about and every case still passed. What
actually held the claim was the `ROLLBACK`; turning that into a `COMMIT` failed the cases as it
should. Break the thing the guarantee rests on, not the thing nearest to it.

**Restore from a copy, never from git.** Measured, and it cost fifty uncommitted lines: `git
checkout <file>` after a teeth probe reverts the file holding everything you have written since the
last commit, prints nothing, and leaves `git diff --stat` empty — which reads exactly like a clean
restore. Take a `cp` copy *before* breaking anything and put it back from there. This build's
`AGENTS.md` states it as a rule; this is where it came from.

**A stand-in more generous than the real thing hides whole features.** Measured twice: a fake
turn-runner volunteered a capability the real one never passed on, so a whole feature was dead
behind a green suite; and a fake outcome object was missing an attribute the real one has, so a path
raised only in production. Give a stand-in exactly the surface of the thing it stands for, and no
more. The same trap through `getattr`: `getattr(vendor_object, "name", default)` on a library object
that never had that attribute hands back the default forever, and a stand-in built with the
attribute agrees with you. Ask the installed library whether the attribute exists.

**A guard written as a regex over source must be probed by *adding* the thing it forbids.**
Measured: a case holding "the product does not reach the new store yet" looked for two import
spellings, neither of which was the one this package actually uses — so it passed green through the
commit that broke it. Removing the forbidden thing proves nothing; only adding it does.

**Coverage without a dependency** is `trace.Trace(count=1)` over the suites **in one process**, then
grepping the written results for the miss marker. Running `python3 -m trace` once per test file
overwrites the previous file's output and reports nonsense.

---

## The 3.9 floor

**A parse check cannot catch a PEP 604 annotation.** Measured: `ast.parse` accepts `dict[str, bytes
| None]` happily, but `X | None` in a *signature* is evaluated at import on 3.9 and raises
`TypeError: unsupported operand type(s) for |`. So a gate running on one modern interpreter passes
while the floor CI pins fails. `from __future__ import annotations` in every file is the fix, and
the check before pushing is to run the suites under `/usr/bin/python3`.

---

## The `sqlite3` binding

The database's own behaviour is in
[`2026-07-26-sqlite-store-and-migrations.md`](2026-07-26-sqlite-store-and-migrations.md), and the
failures the previous build hit with it are in [`the-old-build.md`](the-old-build.md). Three things
belong to the *binding* rather than to SQLite, and all three are measured.

**`Connection` used as a context manager commits or rolls back and does not close.** Python's own
documentation says so and names the fix — `contextlib.closing`. It is worth stating because the
shape is plausible enough that one sibling project produced six separate issues of the same mistake,
and in WAL mode each surviving connection holds descriptors for three files, so a long-lived process
eventually fails with `[Errno 24] Too many open files` in components that have nothing to do with
the database.

**A leaked reader holds the WAL read lock on 3.11 and later, and does not on 3.9.** So the leak is
invisible on the floor CI pins and an error on whatever a developer is running. Measured, and it is
the worst way round: the version that finds the bug is not the version the check runs on.

**`timeout=` on `connect()` is a `busy_timeout`, and its default is five seconds.** SQLite's own
default is zero, so a Python connection is already waiting whether or not anybody decided it should.
Set it deliberately — a case proving an application-level retry works costs five seconds an attempt
otherwise, and reads as a hang.

**Splitting a script on `;` does not work**, because a trigger body contains semicolons.
`sqlite3.complete_statement` is the same test the `sqlite3` shell uses and is the thing to split on.
This matters wherever a schema must be executed statement by statement inside a transaction, which
is anywhere `executescript` cannot be used — and it cannot, because it commits first.

**`SUM` over no rows is `NULL`, not zero.** So a query totalling what an agent has spent reports
`None` for every summed column on an agent that has run nothing, while counted columns come back as
integers. That is correct and worth not "fixing": absent and zero are different claims, and a report
that turns one into the other is a report that cannot say "nothing was ever measured".
