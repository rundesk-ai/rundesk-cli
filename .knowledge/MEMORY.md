# Memory — rundesk-cli

Always-loaded, read at the start of every task: the friction we've hit in **this codebase** and the
workaround for each — so you don't re-hit it. **A living list — delete an entry once it's genuinely solved;
a long MEMORY means something was solved and never pruned.** This codebase only.

## Friction / gotchas

*One bullet each: the trap, and the workaround. Delete when it's genuinely solved.*

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
- A test class appended **after** the `if __name__ == "__main__": unittest.main()` block never runs —
  Python reaches the runner before the class is defined, and the count silently stays where it was.
  Keep that block last in every test file, and check the "Ran N tests" number moved.
- Parser-walking CLI tests dispatch the real **`uninstall`**, which now *removes rundesk* — so the case
  proving every verb is wired stopped the developer's gateways, deleted their launchd jobs and their run
  state, and **passed**, because a successful removal is what that command does. `tests/test_cli.py`
  replaces `cli._remove_this_install` for the whole module in `setUpModule`; never rely on individual
  cases remembering. Redirect every install, state and job directory too before a surface-wide case.
- Coverage without a dependency: `trace.Trace(count=1)` over both suites **in one process**
  (`t.results().write_results(show_missing=True, coverdir=…)`, then grep `>>>>>>`). Running
  `python3 -m trace` once per test file overwrites the previous file's `.cover` and reports nonsense.


---
*Editing this file? Follow the standard first: [`guides/docs-memory.md`](./guides/docs-memory.md).*
