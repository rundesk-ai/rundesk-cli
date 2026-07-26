# Memory — rundesk-cli

Always-loaded, read at the start of every task: the friction we've hit in **this codebase** and the
workaround for each — so you don't re-hit it. **A living list — delete an entry once it's genuinely solved;
a long MEMORY means something was solved and never pruned.** This codebase only.

## Friction / gotchas

*One bullet each: the trap, and the workaround. Delete when it's genuinely solved.*

- **`./install.sh --uninstall` removes the checkout's own `.venv`, whatever else you redirected.**
  Symmetric — the install put `discord.py` there — but it is where a *developer's* suite loads it from
  too, so the Discord cases silently start skipping, and a gateway you have running would fail on its
  next restart with no obvious cause. Run `./install.sh` again straight afterwards, and check
  `.venv/bin/python -c "import discord"` before believing a green suite.
- **A backticked anything in an Evidence cell is read as the name of a test.** That is the whole
  mechanism keeping a ✅ honest, and it does not care that the row is ❌ or that the backticks are around
  a filename, a path or a script. Write those plainly in a note — `check-evidence` fails the gate with
  "is ❌ but names a test", which reads like the row is wrong when the punctuation is.
- **Codex has two instruction fields and one of them is a trap.** `baseInstructions` on
  `thread/start` *replaces* what codex was built with, including the instructions telling it how to
  use its own tools — nothing reports this, the turn merely behaves strangely and the model gets the
  blame. `developerInstructions`, right beside it, *adds*. Probed: given one, codex obeyed it and its
  shell tool still worked. Neither is described in the schema, which types both as a nullable string.
- **`developerInstructions` binds where a thread is created and is ignored on resume.** Probed twice,
  once in a fresh process, which is the shape rundesk runs: the same rule was obeyed at `thread/start`
  and absent after `thread/resume`, while the resume itself reported success. So a reworded
  instruction reaches new conversations only. **Do not read a codex field's behaviour off its schema
  — both of these facts are invisible there**, and the probes are in `.knowledge/scripts/`.
- **Do not test a model instruction with a question the conversation can already answer.** A first
  attempt at the above asked for a codename the thread had been asked for before, so the model
  answered from its own earlier reply and the resume looked like it worked. Use a rule the history
  cannot supply, and run the control: prove the same rule *is* obeyed when given at the start.

- Installing dependencies leaves **caches outside rundesk's own directory** — pip and any build
  tooling it reaches for write under `~/.cache`, `~/Library/Caches`, even `~/.rustup`. Removing
  rundesk cannot take those and does not try. Do not word a requirement as "everything an install
  puts on a machine", because it is not true; ours is what rundesk *is made of*.
- A downloaded install is a directory of source with an `install.sh` in it, which is **exactly what a
  clone looks like** — so the guard protecting a developer's checkout refused to remove `~/.rundesk`
  and uninstalling silently left it. What tells them apart is whether the script sits in the
  directory the installer was told to create.
- A supposedly isolated install/uninstall gate with only `RUNDESK_INSTALL_DIR` and `RUNDESK_BIN_DIR`
  redirected still discovers and stops **live gateways** through the ambient state directories. Point
  `RUNDESK_RUN_DIR`, `RUNDESK_LOG_DIR`, `RUNDESK_SCHEDULES_DIR` and `RUNDESK_JOBS_DIR` at scratch too
  before running the destructive half of the gate.
- **A `Gateway` built without `root=` asks whether the *developer's checkout* fits**, so with anything in
  `requirements.txt` every case that claims a name refuses on a machine that has run the installer, and
  passes in CI, which has no `.venv`. Give any gateway a test builds a scratch `root`; only the fitness
  cases build an install. The suites are isolated now — the trap is writing the next one without it.
- **Never name a real process group in a test — `killpg` degenerates at `0` and at `1`.** It means "that
  group" only above one. Group `0` is the caller's own, and killed the test run and its shell. Group `1`
  looks safe and is worse: on Linux it is `kill(-1, …)`, *every process this user may signal*, so it took
  the CI runner's own agent with it — the step then hung forever with an empty log, no timeout applied and
  cancels did nothing, because nothing was left alive to answer. macOS returns an error instead, so it
  passed there every time. Replace `os.killpg` and assert on what was asked.
- **`gateway.note()` makes no directory and swallows its `OSError`**, so arranging a log in a scratch
  directory that does not exist yet leaves you with silence and a `FileNotFoundError` two assertions
  later, in the reader. Make the log directory in `setUp`; do not assume the first write makes it.
- Running `tests/test_gateway.py` without `RUNDESK_SCHEDULES_DIR` redirected writes stray `<name>.seen.json`
  into the owner's real `~/.rundesk/schedules` — `RUNDESK_RUN_DIR` and `RUNDESK_LOG_DIR` alone are not
  enough, because the schedule checkpoint lives beside the schedules, not with the run state.

- **A capability gate and a caller-supplied-object gate look interchangeable right up until
  the caller has nothing to supply.** What a brain said it can do decided one half of how a
  turn was driven, and whether the caller passed a steering generator decided the other. They
  agree in every case except the ordinary one — `rundesk ask` with no `--steer` — where the
  record was skipped by the first gate and never written by the second, so a turn reached a
  brain with nothing in its account to show for it. One decision, asked once, threaded
  explicitly.
- **A turn that holds a brain's input open must close it on every path, including the ones
  where *we* went wrong.** A steerable brain reads until its input closes; leaving it open
  because the thing feeding it raised is a turn that never ends, waiting on somebody who has
  already stopped speaking. Close it in a `finally`, not at the end of the happy path.

- **A `pkill -f` pattern must match how a process really appears in `argv`, not how you think
  of it.** Suites are started as `python3 tests/test_turn.py` from the repo, so `argv` holds
  the *relative* path — `pkill -f "rundesk-cli/tests/"` matched nothing and reported success,
  and a suite kept running for another twenty minutes while the cleanup was believed done.
  Check with `pgrep -fl <pattern>` before trusting a kill, and remember that killing one
  command in a `&&` chain lets the shell move on to the next one.

- **An adapter that can find itself on its own PATH is a fork bomb.** An adapter looks its
  brain up by name; committing the stranger's adapter as `strangers/driftwood` and putting
  that directory on `PATH` meant it resolved `driftwood` to *itself*, ran itself, and that
  copy did the same — **eight thousand processes and a load average of 641** before anyone
  noticed, because each generation looks exactly like a legitimate adapter run. The brain is
  named what the adapter looks for and the adapter is named something else, and
  `_nothing_of_ours_is_on` in `test_provider.py` now fails the case rather than the machine.
- **Never leave overlapping runs of a suite in the background.** Repeatedly relaunching the
  gate and `test_provider.py` while earlier ones were still going left real gateways, real
  `codex app-server` processes and `sleep 300` stand-ins alive across a dozen generations —
  and made the fork bomb above take minutes to spot rather than seconds, because the process
  list was already full of things that belonged there. One run at a time; check the previous
  one is gone before starting another.

- **A test flag that points at a real directory points *every* case at it.** `test_provider.py
  --home ~/.codex` was meant for the adapter under test and reached the stand-ins too, so they
  wrote their own bookkeeping into the owner's real Codex home and read what an earlier run had
  left there — one case failed and the rest passed while quietly polluting it. Anything that
  redirects a case at something real must be scoped to the one class that needs it, and
  everything else left on scratch.
- **`codex exec` will not sign in from a home it was not given.** `CODEX_HOME` isolates
  credentials as well as configuration — the sign-in is `auth.json` inside it, a plain file
  rather than a keychain — so a scratch home means `401 Unauthorized` on every request and a
  conformance run against the real adapter that proves nothing. Point `--home` at a home that
  has one. A symlink to the owner's own works and stays a link; a copy works and goes stale on
  the next token refresh. Rundesk makes neither for them.

- `asyncio`'s `Process.wait()` resolves when **every pipe closes**, not when the process exits. Anything
  the program left running inherited the far end and holds it open, so waiting on the exit lands hours
  late or never. Watch `proc.returncode` in short spells instead — it is set promptly. This cost a
  reproduced hang and reads exactly like a deadlock in your own code.
- `asyncio.wait({a, b})` returns **instantly, forever** once one of them is already done — a completed
  future stays done. Drop it from the set after it fires, or the loop spins at full speed.
- Giving a program `stderr=PIPE` **without something reading it deadlocks the program**, and it presents
  half an hour later as a perfectly healthy one having gone quiet (`SILENT`), which sends you looking
  anywhere but here. Anything that opens a second stream must start a task that drains it to EOF for the
  program's whole life, whether or not the caller wants what is on it.
- `StreamWriter.write()` **never blocks and never raises** — on a program that has gone it silently
  discards what it was given, and asyncio swallows the `BrokenPipeError` without even reaching the loop's
  exception handler. `await drain()` is the *only* place a failed write is reported. Never write without it.
- A module-level constant used as a **default argument** (`def __init__(self, held=HELD_BYTES)`) is bound
  once, when the file is read, so a test that monkeypatches the constant changes nothing and the case
  passes against unbounded behaviour. Resolve it in the body: `held = HELD_BYTES if held is None else held`.
- A test that builds a `Gateway` without `RUNDESK_RUN_DIR` **and** `RUNDESK_LOG_DIR` pointed at scratch
  writes into the real `~/.rundesk`. The suite did, and left nine log files in the owner's home. Point
  logs somewhere **outside** the run directory too, or the "leaves nothing behind" cases trip over them.
- **The gate cannot catch a 3.9 break, and CI can.** It runs on one Python — whatever `sys.executable`
  is — and its parse check is `ast.parse`, which accepts `dict[str, bytes | None]` happily. A PEP 604
  `X | None` in a *signature* is evaluated at import on 3.9 and raises `TypeError: unsupported operand
  type(s) for |`, so a suite that passes the whole gate dies on the floor version CI pins. Every file
  needs `from __future__ import annotations`, and the check before pushing is
  `for f in tests/test_*.py; do /usr/bin/python3 "$f"; done` — macOS ships 3.9.6 at that path, which is
  exactly the floor. `.knowledge/tmp/like-ci` exists for this.
- A test class appended **after** the `if __name__ == "__main__": unittest.main()` block never runs —
  Python reaches the runner before the class is defined, and the count silently stays where it was.
  Keep that block last in every test file, and check the "Ran N tests" number moved.
- Coverage without a dependency: `trace.Trace(count=1)` over both suites **in one process**
  (`t.results().write_results(show_missing=True, coverdir=…)`, then grep `>>>>>>`). Running
  `python3 -m trace` once per test file overwrites the previous file's `.cover` and reports nonsense.


- **`./install.sh --uninstall` deletes the *checkout's* `.venv`**, which is the one a
  developer's own `./rundesk` uses. Run the uninstall half of the gate while a gateway is
  serving a channel and the next restart of that channel cannot import `discord` — the
  running process survives, because it imported it already, so this shows up minutes later
  as a channel that will not come back. Rebuild it (`python3 -m venv .venv && .venv/bin/python
  -m pip install -r requirements.txt`) before carrying on.
- **A gateway holds the `channel.py` it imported when it started.** Editing a module and
  restarting *the adapter* is not enough: the adapter is a fresh process each time and the
  gateway is not. An attachment was downloaded correctly by a new adapter and dropped by an
  old seam, which reads exactly like the adapter being broken. Restart the gateway after
  touching anything under `src/`, and check the file's mtime against the gateway's start
  line in its log before believing what you are seeing.
- **A second connection with the same bot token silently wins.** Running the Discord
  adapter by hand to diagnose it, while a gateway is already serving that channel, makes
  one of the two stop receiving — with no error on either. Stop the gateway first, or
  accept that what you are watching is not what the gateway sees.
- **A stand-in that is more generous than the real thing hides whole features.** Twice
  here: a fake `turn.carry` volunteered what the brain could do, which the real one never
  passed on, so steering was dead behind a green suite; and a fake `Outcome` was missing an
  attribute the real one has, so a code path raised only in production. Give a stand-in
  exactly the surface of the thing it stands for — no more.
- **Guessing a vendor's field names costs a whole feature, silently.** The Codex adapter
  looked for `changes`, `files`, `artifacts` and `outputs`; Codex emits `savedPath`. Nothing
  errored — a generated image was simply never reported. Read a real item out of a run's
  `.brain` file before writing the name of a field.

- **Never assert that `state.db-wal` and `state.db-shm` exist.** They are there only while a
  connection is open or after one closed badly — a clean close checkpoints and removes them. A case
  asserting all three files are present passed on `/usr/bin/python3` and failed the gate on 3.14,
  which is the worst way round to find it. Assert that nothing *other* than the three is left.
- **`Connection.executescript()` issues an implicit COMMIT before it runs**, so a `BEGIN IMMEDIATE`
  opened just above it is silently ended and everything the script does happens in the open. The
  build of a fresh `state.db` looked atomic and was not, and the failure surfaced two steps later
  as `cannot commit - no transaction is active` rather than anywhere near the cause. Execute
  statements one at a time inside the transaction. Splitting a script on `;` does **not** work —
  a trigger body contains semicolons — so use `sqlite3.complete_statement`, which is the same test
  the shell uses; `store._statements()` is that, and `migrations/001.py` keeps its own copy on
  purpose so a step never changes meaning when today's code does.
- **A migration whose number is a date with a time on it silently destroys the version.**
  `PRAGMA user_version` is a signed 32-bit integer: past `2147483647` it does not raise, it wraps
  to `0` — which is exactly the value meaning "written partway and cannot be read". `20260726`
  fits and `20260726120000` does not. `migration.found()` refuses anything above the ceiling, and
  that guard is the only thing between a plausible-looking filename and unreadable records.
- **`BEGIN IMMEDIATE` on a read-only SQLite connection succeeds.** SQLite defers taking the write
  lock until something actually writes, so a case proving `store`'s reader "cannot begin a write
  transaction" by asserting the `BEGIN` raises is asserting on nothing — and fails. The refusal
  lands on the first write, as `OperationalError: attempt to write a readonly database`. Assert
  there.
- **A case about `store`'s boundary retry must shorten `store.BUSY_SECONDS` first.** SQLite's own
  busy handler waits the connection timeout — five seconds — before `BEGIN IMMEDIATE` ever raises,
  so holding a write lock from a second connection and expecting the retry costs five seconds an
  attempt and reads as a hang. It is looked up in the body of `_open`, so setting it to `0.05`
  (and restoring it in `addCleanup`) reaches it; the fake `wait=` can then release the held lock
  and the retry resolves at once.
- **`store.usage()` on an agent that has run nothing reports `None` for the four token totals**, not
  `0` — `SUM` over no rows is NULL, and only `runs`, `reported` and `unreported` are counted. A case
  asserting zeros on a fresh database fails.
- **`/usr/bin/python3` caches bytecode outside the checkout, and a restored file can keep
  running the break.** macOS's system Python writes to `~/Library/Caches/com.apple.python/…`
  rather than to `src/rundesk/__pycache__`, so clearing the repo's `__pycache__` does
  nothing. A `.pyc` is reused when the source's *mtime and size* match what it recorded — and
  breaking a module for a teeth probe, then restoring it seconds later with a same-length edit
  (`step.version` → `step.at.name` is character-for-character the same size) matches both. The
  suite then keeps failing against code that is byte-for-byte correct, and `diff` says nothing
  is wrong. `touch src/rundesk/<module>.py` after restoring invalidates it.
- **Breaking `migration.py` to remove a step's spare files *before* the version commits proves
  nothing** — a probe that looks decisive and fails silently. A step that dies never returns its
  list, so the runner has nothing to remove on the path the claim is about, and every case still
  passes. What actually holds "both copies survive a failed step" is the `ROLLBACK` in `_one`;
  probe *that* (turn it into a `COMMIT`) and the copying cases fail as they should.

---
*Editing this file? Follow the standard first: [`guides/docs-memory.md`](./guides/docs-memory.md).*
