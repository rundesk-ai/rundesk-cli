# Memory — rundesk-cli

Always-loaded, read at the start of every task: the friction we've hit in **this codebase** and the
workaround for each — so you don't re-hit it. **A living list — delete an entry once it's genuinely solved;
a long MEMORY means something was solved and never pruned.** This codebase only.

## Friction / gotchas

*One bullet each: the trap, and the workaround. Delete when it's genuinely solved.*

- **`~/.rundesk` is the owner's live install. Never touch it.** It is a running product with
  real agents, real channels and real history in it — not a fixture. **Never install,
  uninstall, update, migrate, start, stop, add, remove or write anything there**, and never
  run a command that resolves there by default, which is most of them. This is not a thing to
  weigh against convenience: a scratch agent is free and a stopped gateway of theirs is not.
  Test installs somewhere else — `RUNDESK_INSTALL_DIR` and `RUNDESK_BIN_DIR` for the install
  itself, and **all four of** `RUNDESK_AGENTS_DIR`, `RUNDESK_RUN_DIR`, `RUNDESK_LOG_DIR` and
  `RUNDESK_JOBS_DIR` for what an agent keeps, or the command reaches the real one while
  reporting success. Check `find $SCRATCH` has something in it before believing a run was
  isolated, and check `ls ~/.rundesk` afterwards to be sure it did not.

- **`./install.sh --uninstall` removes the checkout's own `.venv`, whatever else you redirected.**
  Symmetric — the install put `discord.py` there — but it is where a *developer's* suite loads it from
  too, so the Discord cases silently start skipping, and a gateway you have running would fail on its
  next restart with no obvious cause. Run `./install.sh` again straight afterwards, and check
  `.venv/bin/python -c "import discord"` before believing a green suite.
- **The gate cannot tell you whether `test_discord` really ran, and CI is the machine where
  it matters.** CI runs with an *empty* `.venv` on purpose, so the Discord cases skip there
  legitimately — which means a suite that skips for the *wrong* reason skips there too, and
  nothing goes red. Whether the adapter file exists is the one thing that does not depend on
  the dependency, so it is checked first and raises on every machine. Anything else that
  fails to load is a skip only when `discord.py` is genuinely absent, asked of the import
  directly: the adapter catches its own missing import, prints a record and exits, so its
  exception can never be told apart from being broken. Reading it as one failed CI on the
  only machine the skip exists for.
- **The floor check `for f in tests/test_*.py; do /usr/bin/python3 "$f"; done` cannot include
  `test_discord`, and its failure looks like a real 3.9 break.** 3.9 finds the checkout's
  `.venv/lib/python3.14/site-packages`, so it imports a `discord` built for another Python;
  `yarl` falls back to its pure-Python quoter, whose signature is PEP 604, and 3.9 dies on
  `TypeError: unsupported operand type(s) for |`. Not a `ModuleNotFoundError`, so the suite's
  skip guard does not catch it — and nothing about the traceback says the cause is the
  interpreter reading somebody else's virtualenv. **CI never sees it**: it runs 3.9 with an
  empty `.venv`, which is the whole point. Run the other nineteen on `/usr/bin/python3` and
  `test_discord` on `.venv/bin/python`; confirmed present before any of this phase's work.
- **Run the gate with `.venv/bin/python`, not with a bare `python3`.** The gate is
  `PY = sys.executable`, so it runs every suite on whichever interpreter started it — and on
  a shell whose PATH does not reach Homebrew, `python3` is `/usr/bin/python3`, which is 3.9.
  It then finds the checkout's `.venv/lib/python3.14/site-packages`, imports a `discord`
  built for another Python, and dies in `yarl` on a PEP 604 signature: `TypeError:
  unsupported operand type(s) for |`. `FAIL test_discord` with a traceback naming nothing of
  ours, on a gate where the other nineteen suites are green, is this and not a real break.
  `.venv/bin/python .knowledge/scripts/gate` is the whole fix. It is the same fault the floor
  check below hits, arriving through the documented command rather than through a loop
  somebody wrote.
- **Regenerate `CLI.md` with that same interpreter, or the gate fails on a line you did not
  write.** `argparse` renders `BooleanOptionalAction` differently across versions — 3.9 adds
  `(default: True)` after the help text and 3.14 does not — so `cli-reference` run on the
  floor version rewrites the `--activity` line, and `--check` then reports that the reference
  no longer matches the command. The diff names an option nothing in the task touched, which
  reads like the generator being broken. `.venv/bin/python .knowledge/scripts/cli-reference`.
  **CI never catches this**: `build.yml` does not check the reference at all, so the local
  gate is the only thing that does.
- **`gate > log; echo "GATE_EXIT=$?" >> log` reports the *echo's* status to whoever is
  watching the command, not the gate's.** A backgrounded compound command exits with its
  last member, so a harness or a `&&` chain reads `0` from a gate that failed — and the real
  code is only in the file, which nobody re-reads once they have been told it passed. Two
  runs were reported green this way while `test_transcript` was failing in both. **Run the
  gate as the only command in its shell** and read the exit the runner gives you, or grep the
  log for `^FAIL` before believing any summary — including your own.
- **Deriving a new directory from `agents_home().parent` isolates nothing — derive it
  *downwards*.** It reads like "beside where agents are kept", which for an owner is
  `~/.rundesk` and is right; for a suite it is whatever the scratch directory happens to sit
  in, which is the shared temp root. Every case then shared one directory, and one case's
  template turned up in another case's agent — passing or failing by test order. Anything
  hung *below* `agents_home()` cannot do that, because redirecting the root redirects it.
  Assert the shape (`self.assertEqual(self.where, made.parent.parent)`) rather than
  `startswith`, which a parent path satisfies trivially.
- **Anything a command locates from `cli.REPO_ROOT` writes into the developer's own checkout,
  whatever a suite redirected.** It is `Path(__file__).resolve().parent.parent.parent`, resolved
  at import and answering for the tree the test is *running from* — so a new update-time
  directory hung off it put a real copy of a fake agent's `state.db` into `rundesk-cli/` while
  every `RUNDESK_*` variable pointed at scratch. Found only because `git status` showed an
  untracked path. **Hang anything new off `agents_home()` instead**, which reads
  `RUNDESK_AGENTS_DIR` on every call, so whatever isolated the agents isolates it too — and
  check `git status --short` in the checkout after running a suite that drives a command.
- **`OK (skipped=65)` and `OK` are the same word to whoever reads the gate.** `test_discord`
  loaded the adapter from `src/rundesk/channels/discord`, which the src restructure had moved
  to `src/channels/discord`; the loader raised, a bare `except BaseException` set the module to
  `None`, and every case skipped for months while the gate said `ok`. **A suite may only skip
  for the reason skipping is for** — here, `discord.py` genuinely not installed — and anything
  else must raise. Check a suite that can skip with `.venv/bin/python tests/test_discord.py`
  and read the *count*, not the word: `python3` alone has no `discord` and skips honestly, so
  the two failures look identical from the wrong interpreter.
- **Waiting for the gate with `while pgrep -f "scripts/gate"` never ends, because the waiter
  matches itself.** The pattern is in the waiting shell's own command line, so `pgrep` finds it
  and every waiter keeps every other waiter alive — six of them were still spinning long after
  the runs they watched had finished, and one looked like a gate that would not end. Wait on
  the *output* instead: `until grep -q "GATE_EXIT=" "$log"; do sleep 20; done`. And do not
  trust the exit code of `gate > log; echo "GATE_EXIT=$?" >> log` either — what a caller sees
  is the `echo`'s, so a failed gate reports success. Read the line out of the log; a run that
  said `ok` against all 19 suites still exited 1 on a check above them.
- **A brain running `rundesk` picks a different `python3` than you did, and `fitness()` then
  refuses.** `rundesk` is `#!/usr/bin/env python3`, so what it resolves depends on the PATH of
  whoever ran it — a developer's shell finds Homebrew's 3.14, and a brain's tool shell finds
  `/usr/bin/python3`, which is 3.9.6. The `.venv` is built for whichever one ran `install.sh`,
  so the other reports `NOT READY — what rundesk needs was installed for python3.14, and this
  is python3.9` and the agent's records read as unavailable. Grok found this by being told to
  look something up and reporting what it actually got. Reproduce with
  `env PATH=/usr/bin:/bin ./rundesk doctor <agent>`; it is not a bug in the store.
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
- **Grok reads its other sessions, so a resume probe passes without resuming anything.** A
  control turn in a *fresh* session answered a question only the previous conversation could
  have set up, and said why: "No prior context in this session — checking recent sessions for
  what 'the second one' refers to." So the naive round-trip probe reports `CARRIES CONTEXT`
  when what carried it was cross-session recall, and an adapter would claim `resume` on it.
  Pass **`--no-memory`** on every turn of a probe *and* make the candidate words unguessable
  per run (a uuid suffix), or a re-run reads the previous run's sessions. The same finding is
  why the shipped adapter passes `--no-memory`: one agent's conversation is not another's.
- **`RUNDESK_HOME` does not redirect where agents live — `RUNDESK_AGENTS_DIR` does.** The name
  reads like the root of everything and is not: `agent.py` resolves the agents root from
  `RUNDESK_AGENTS_DIR` alone, falling back to `~/.rundesk/agents`. So a scratch run that sets
  `RUNDESK_HOME`, `RUNDESK_RUN_DIR`, `RUNDESK_LOG_DIR` and `RUNDESK_JOBS_DIR` — which looks
  exhaustive — still writes real agents into the owner's own
  `~/.rundesk/agents`, and `rundesk add` reports success while doing it. Three were created that
  way and had to be removed with `rundesk remove`. Set `RUNDESK_AGENTS_DIR` too, and check
  `find $SCRATCH` actually has something in it before believing a command was isolated.
- **Claude reports `loggedIn: false` on a signed-in machine when `USER` is unset.** Its
  sign-in is in the macOS login keychain (`Claude Code-credentials`, `acct=<username>`), and
  the lookup is keyed on the account name — so under the environment rundesk *builds*
  (`HOME`, `PATH`, `RUNDESK_*`, `TERM`, `LANG` and nothing else) it cannot find it, with no
  `CLAUDE_CONFIG_DIR` involved at all. Bisected: `USER` alone flips it; `LOGNAME`, `SHELL`,
  `TMPDIR`, `XPC_SERVICE_NAME` and `__CF_USER_TEXT_ENCODING` all leave it false. **Fix it in
  the adapter, not the core** — `getpass.getuser()` reads the password database and needs no
  environment. Ask `claude auth status` (offline, ~0.2s, answers `{"loggedIn": …}`) rather
  than guessing at a credential filename; there is no file to guess at.
- **`CLAUDE_CONFIG_DIR` does not redirect the Claude login — setting it *removes* one.**
  Separate from the above and it survives it: with `USER` present and the variable pointed at
  `~/.claude`, the very directory the CLI defaults to, `claude auth status` still answers
  `loggedIn: false`. Setting it at all stops the keychain being read. So isolating an agent
  into a private home is, on this brain, the same act as logging it out, and `--home
  ~/.claude` cannot give a real Claude a login. Either give the home its own
  (`CLAUDE_CONFIG_DIR=<dir> claude auth login`, needs a browser) or leave the variable unset
  and share the machine's — which is what the shipped codex adapter does unconditionally.
- **Claude says a lost conversation on stderr and `error_during_execution` on the stream.**
  Resuming a session id that no longer exists — which happens whenever a *failed* turn
  reported a handle — fails every turn after it, and the `result` line does not say why:
  `No conversation found with session ID: …` is on stderr only. So an adapter deciding
  whether to start again must read both streams, and must not report a handle for a turn
  that failed, or it poisons the conversation for good.
- **Codex asks nobody anything unless `approvalPolicy` is set, so a probe that leaves it out
  reports "no approval exists" about a policy nothing turned on.** The shipped adapter never
  sets it and its default does not ask; the first run of `probe-asking codex-approve` therefore
  said `NEVER FIRES` while `item/fileChange/requestApproval` was working perfectly. Pass
  `{"approvalPolicy": "untrusted", "approvalsReviewer": "user"}` on `thread/start`. And read
  the *item* type as `agentMessage`, not the `agent_message` the old `exec` stream used — the
  wrong spelling leaves every reply looking empty, which reads exactly like a turn that said
  nothing.
- **Codex's `outputSchema` needs `additionalProperties: false` on every object, and says so as a
  *failed turn*.** The same JSON Schema that claude's and grok's `--json-schema` accept unchanged
  is rejected by codex with a provider 400 — `invalid_json_schema`, "'additionalProperties' is
  required to be supplied and to be false" — delivered inside the turn error rather than as a
  refused request, so it costs a real turn and reads like the brain failing. Walk the schema and
  set it before sending. Related: ask a brain for options without giving it anything to enumerate
  and you get `options: []`, which is honest and looks exactly like a brain that cannot offer a
  multiple choice.
- **Allowlisting the very tool whose permission you are testing means nothing ever asks.**
  `--allowedTools Write` plus `--permission-prompt-tool` reported that Claude has no approval
  gate; a permitted tool never prompts, so the broker had nothing to be asked about. Grant
  nothing, and set `--permission-mode manual` — headless defaults to a mode Claude itself calls
  "don't ask". Always carry the canary: `system/init.mcp_servers` says whether the broker
  actually connected, and zero calls from a server that never started is not evidence.
- **Claude writes an auto-memory keyed by the working directory, and a `Read`-only allowlist
  does not stop it.** It lands in `~/.claude/projects/<resolved cwd slug>/memory/`, so a *fresh*
  session standing in the same directory answers another conversation's question — the grok
  cross-session trap, on a second brain, and rundesk stands every one of an agent's turns in
  one directory. A resume probe therefore needs its control in a **different** directory, or it
  reports `CARRIED-BY-SOMETHING-ELSE` forever. Build the slug from `os.path.realpath()`: on
  macOS `/var` resolves to `/private/var`, and the obvious spelling inspects a directory that
  never existed and reports nothing written.
- **A brain cannot be probed without writing into the owner's real brain home.** Isolating
  `CLAUDE_CONFIG_DIR`, `CODEX_HOME` or `GROK_HOME` logs that brain out, so every probe run
  leaves session and memory directories under `~/.claude/projects/`, `~/.grok/sessions/` and
  `~/.codex/sessions/`. Name every scratch working directory `probe-…` so the litter is
  identifiable afterwards, and tell the owner what to remove rather than removing it yourself.
- **`claude --help` does not list every flag `claude` accepts, so absence from it proves nothing.**
  `--permission-prompt-tool` — the flag a whole documented approval route rests on — is missing
  from 2.1.220's help output and is still accepted by the parser. The free way to tell is the
  control: a genuinely unknown flag dies with `error: unknown option '…'` **before a turn
  starts**, so passing the flag under test costs nothing when it is gone and one live turn when
  it is not. Run the bogus-flag control first, and never conclude a vendor dropped something
  from `--help` alone.
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
  `RUNDESK_RUN_DIR`, `RUNDESK_LOG_DIR`, `RUNDESK_AGENTS_DIR` and `RUNDESK_JOBS_DIR` at scratch too
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

- **A `--` tail needs `nargs="+"` or `_handed_on`, and `nargs="*"` is the trap between them.**
  argparse carries a tail into a *required* greedy positional on its own, which is why
  `schedules add` worked for a year without being in `_carries_a_tail`. Relax it to `"*"` so
  the verb can take `--ask` instead, and argparse binds zero eagerly and reports the program as
  `unrecognized arguments` — and worse, an option *inside* the tail (`-- rundesk ask ava "…"
  --instructions "…"`) is read as the verb's own, which is finding 31 all over again. A verb
  that grows options of its own must name its tail `CARRIED` so `_handed_on` splits it off in
  front of the parser.
- **`agents <agent>` and subcommands under `agents` cannot both exist.** An optional positional
  (`nargs="?"`) followed by `add_subparsers()` makes argparse match the *agent's name* against
  the subcommand choices: `rundesk agents ava` dies with `invalid choice: 'ava'`. That is why
  what an agent is told is written by `add --instructions` rather than by `agents ava
  instructions …`, and why any new per-agent action has to go somewhere else.
- **`store` runs with `PRAGMA foreign_keys=ON`, so a test writing a row that references another
  must write that one first.** A schedule with `channel="ops"` on an agent with no such channel
  is `sqlite3.IntegrityError: FOREIGN KEY constraint failed`, from the writer and not from
  anything that reads it back. And the stand-in `Brain` in `test_answering.py` never calls
  `store.opened`, so nothing that reads `conversations()` after driving a fake turn finds one —
  open it yourself when what is under test is where something goes rather than how it got there.
- **`Gateway._started` is an attribute, not a name going spare.** `_record` sets it lazily
  (`if not hasattr(self, "_started")`) and writes it into the gateway's record as the moment
  it came up, so adding a *method* called `_started` makes `hasattr` true, puts a bound method
  where a float goes, and the whole claim dies on `Object of type method is not JSON
  serializable` — from `claim()`, nowhere near what you wrote. Grep `self\._<name>` before
  naming a private method on `Gateway`: several of its attributes are set outside `__init__`.
- **A fake brain written into a test as a plain triple-quoted string needs `\\n`, not `\n`.**
  The brain is source code *written to a file*, so a real newline lands inside its string
  literal and the adapter dies with `SyntaxError: EOL while scanning string literal` — exit 1,
  nothing on stdout, and the turn recorded as `failed` with no clue why. Nothing points at the
  test: the reason is in `logs/runs/<run>.err`, which is the first place to look when a
  stand-in brain "runs" and says nothing. `r"""…"""` is the fix, and `tests/test_turn.py`
  escapes it the other way.
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
- **`pkill -f "tests/test_*.py"` in this checkout kills whatever *another agent* is running,
  and their gate then reports a failure that never happened.** More than one agent works in
  this worktree at once, so a suite you did not start is the ordinary case rather than a
  stray: a leftover-looking `test_gateway.py` was a step inside somebody else's gate, killed
  by a cleanup that had every reason to look safe. Before killing anything, read the parent —
  `ps -o ppid= -p <pid>` up to the `scripts/gate` that owns it, and look at the log path in
  its command line: it names the **session** that started it, and one that is not yours is
  not yours to end. A suite left running past a few minutes is far cheaper than a green gate
  somebody has to re-run without knowing why it went red.
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
- **Another agent moves the checkout out from under a long task, and the first sign is a
  file "modified on disk".** A review that named `37d0753` on `phase-8-…` as its baseline
  finished on `main` at `66387d7`, with that branch merged and the working tree emptied of
  the other agent's files. **Do not assume the work is void and do not re-do it**: ask
  `git merge-base --is-ancestor <baseline> HEAD` and `git diff <baseline> HEAD -- <the files
  you reviewed>`, and if the scope is byte-identical the baseline still holds — say so
  rather than silently restating it. Re-check `git rev-parse --abbrev-ref HEAD` immediately
  before every commit; a commit meant for a feature branch lands on `main` otherwise, and
  switching back in a shared worktree would disrupt whoever is working in it.
- **`SUGGESTIONS.md` finding numbers are taken while you are writing.** Numbers are never
  reused, so two agents filing at once both reach for the next one — 41 and 42 were claimed
  by another round mid-review. Re-read the file's tail immediately before you number
  anything, and append rather than editing near somebody else's section.
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

- **A guard written as a regex over source must be written against how this package
  actually imports.** `test_the_product_does_not_reach_the_new_store_yet` looked for
  `from store import` and for a line starting `import …store…`. Every module here writes
  `from rundesk import gateway, store`, which is neither — so the case that was supposed to
  hold the whole "deleting the store leaves the product as it was" safety passed green
  through the commit that broke it. Any case that greps `src/` for an import must be probed
  by *adding* the thing it forbids, not only by removing it.
- **Changing a `store.py` signature means running `test_migration.py`, not only `test_store.py`.**
  `test_migration`'s fixtures build a furnished agent through the real store, so a new required
  argument on `schedule_fired` broke it while every suite anyone thought to re-run stayed green —
  and the gate caught it, which is the one place it is expensive to find. The suites that drive
  the store are `test_store`, `test_migration`, `test_turn`, `test_transcript`, `test_answering`,
  `test_channel`, `test_agent` and `test_cli`; run all eight.
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
- **`DROP TABLE` fires the foreign-key actions pointing *at* it, so rebuilding `schedule`
  silently empties `run.schedule_id`.** With `PRAGMA foreign_keys=ON` — which is how the
  runner opens every step's connection — `DROP TABLE` performs an implicit `DELETE FROM`
  first, and that fires `ON DELETE SET NULL` on every run a schedule ever started. The
  rebuild then looks perfect: the table is right, the schedules are all there, and the one
  thing `001.py` added that clause *to preserve* is gone, with nothing raised. A step that
  rebuilds a referenced table must read the links out first (`SELECT n, schedule_id FROM run
  WHERE schedule_id IS NOT NULL`), do the rebuild, put them back, and end on
  `PRAGMA foreign_key_check` — which returns rows rather than raising, so it has to be read
  and raised on by hand.
- **`PRAGMA foreign_keys=OFF` is a no-op inside a transaction, and answers `1` when you ask
  it back.** So SQLite's documented twelve-step procedure for changing a table's shape —
  which *begins* by turning foreign keys off — cannot be followed by a migration step at all:
  the runner hands the step a live `BEGIN IMMEDIATE`, and a step may not commit. Neither
  `PRAGMA legacy_alter_table=ON` nor `defer_foreign_keys` rescues it; the first still rewrites
  the reference and the second defers violations while the actions still run. What does work,
  probed on both `legacy_alter_table` settings: create the new table, copy, `DROP TABLE` the
  old, `ALTER TABLE … RENAME TO` the old name — after which the referencing table's clause
  names the rebuilt one — then restore the links by hand. Restore `sqlite_sequence` too: the
  drop takes the old table's row with it, and an `AUTOINCREMENT` id that goes backwards can
  be re-issued.
- **Breaking `migration.py` to remove a step's spare files *before* the version commits proves
  nothing** — a probe that looks decisive and fails silently. A step that dies never returns its
  list, so the runner has nothing to remove on the path the claim is about, and every case still
  passes. What actually holds "both copies survive a failed step" is the `ROLLBACK` in `_one`;
  probe *that* (turn it into a `COMMIT`) and the copying cases fail as they should.

---
*Editing this file? Follow the standard first: [`guides/docs-memory.md`](./guides/docs-memory.md).*
