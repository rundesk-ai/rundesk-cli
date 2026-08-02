# Memory — rundesk-cli

Always-loaded, read at the start of every task: the friction we've hit in **this codebase** and the
workaround for each — so you don't re-hit it. **A living list — delete an entry once it's genuinely solved;
a long MEMORY means something was solved and never pruned.** This codebase only.

## Friction / gotchas

*One bullet each: the trap, and the workaround. Delete when it's genuinely solved.*

- **An import that looks dead can be the seam a collaborator arrives through.** `main` passes the
  gateway module itself as `gateways` when nothing is injected, so `gateways.remembered()` in
  `standing.every_name` needs `gateway.remembered` to exist — while every static check says the
  name is unused, because no line in the file spells `gateway.remembered`. Two reviewers and an
  AST pass all called it dead; `rundesk agents` then died with `AttributeError` inside a real
  subprocess. **Before deleting an import from `gateway.py`, `agent.py`, `supervisor.py`,
  `skill.py`, `script.py` or `catalog.py`, check what commands reach on the matching injected
  name** (`gateways.`, `agents.`, `machine.`, `skills.`, `scripts.`, `catalogs.`) — those modules
  are the defaults, so their public surface is an API even where nothing imports it by name.
- **Moving a decorated function and leaving its decorator behind silently rebinds the *next*
  function.** Lifting `changing()` out of `gateway.py` by its `def` line left the
  `@contextlib.contextmanager` above it, which then wrapped `logs_home()` — so `logs_home()`
  returned a context manager and every path that builds a log path died with `unsupported
  operand type(s) for /: '_GeneratorContextManager' and 'str'`, forty tests away from the
  edit and naming neither function. Nothing failed at import and the module still parsed.
  **When you move a definition, take it from `min(decorator_list, lineno)`, not from `def`**,
  and assert the moved text still starts with its decorator.
- **`test_install` fails three ways at once because of directories git never mentions, and none of
  them is your change.** A `ui/node_modules` (55 MB) and a built `site/` (47 MB) sitting beside `src/`
  are tracked by nothing and ignored by nothing, so **`git status` reports the tree clean** while
  `tests/test_install.py:38` and thirteen more `copytree` calls copy both fourteen times, and
  `OneInstructionTests._published()` walks straight into them. Measured on one commit: **82 cases,
  75 s, `OK`** against a lean `git archive` extraction, versus **187 s (past the gate's 180 s
  ceiling) plus two failures** in the checkout — `_published()` finding the install instruction in
  `site/dist/index.html`, `site/dist/llms-full.txt` and `site/dist/start/install/index.html` as well
  as in `install.sh`, and reporting `2 != 1` because the built site is older than the instruction it
  publishes. All three read exactly like a regression in whatever you just touched. **Before
  believing `FAIL test_install`, run `du -sh */ | sort -rh | head` and re-run the suite against
  `git archive HEAD | tar -x -C <scratch>`** — that separates the tree from the code in about a
  minute. The durable fix is `ui`, `site`, `node_modules` and `dist` in that file's
  `ignore_patterns`, plus a `.gitignore` line so the tree stops lying; both are changes nobody has
  been asked for yet.
- **A module-level constant that moves takes every `tests/` rebinding of it with it.** The suite
  turns `START_PATIENCE`/`CYCLE_PATIENCE`/`LOOK_AGAIN_SECONDS` *down* so waiters do not really wait,
  and `came_up`/`gone` read them off module globals at call time on purpose. Moving them from `cli`
  to `standing` while leaving `tests/test_cli.py` setting `cli.START_PATIENCE` would have left the
  rebinding pointing at nothing — the suite would still pass, just slowly enough to approach the
  gate's per-suite ceiling, which is the failure shape nobody attributes correctly. It failed loudly
  here only because nothing re-exported the old name. **Never re-export a moved constant for
  convenience**, and grep `tests/` for `<module>.<CONST>` in the same commit that moves one.
- **`_plain_name` in the Discord adapter does not drop a path — it rewrites one into a
  single long name, and every component of it stays readable.** It replaces each
  non-alphanumeric character with `-`, so `/Users/somebody/secret/exporter` comes out as
  `Users-somebody-secret-exporter` and passes an eyeball check for "no slashes in it"
  while publishing the whole path into a room (R-ROL-17). The guard that actually drops
  components is `_helper_name`, which takes the last one first and then calls
  `_plain_name`. Sanitise anything that might be a path with `_helper_name`, and assert
  the *middle* components are gone rather than only the separators. `_plain_name` also
  answers `attachment` when it is left with no characters at all — right for a file, and
  it will happily name something else after one.

- **Putting a file back after a teeth probe with `git checkout <file>` throws away the
  whole task's uncommitted work in it, not the probe's break.** A probe here is "break the
  fix, run the class, restore" — and the file being restored is the one holding everything
  you have written, none of which is committed yet. `git checkout src/rundesk/gateway.py`
  reverted fifty new lines to `HEAD`, printed nothing, and the `git diff --stat` after it
  answered empty, which reads exactly like a clean restore rather than like the work being
  gone. Recoverable only because the probe's own `cp … /tmp/<file>.keep` was still there.
  **Restore from that copy and never from git** until the work is committed — and take the
  copy *before* breaking anything, which is the same command either way.

- **Nothing correlated in the Discord adapter's `Live` survives the turn that put it
  there.** `_state`'s terminal branch ends with `self.live.pop(...)`, so a `finished`,
  `stopped` or `failed` state throws away the whole entry — `held.tools` with it. Anything
  that opens a mark in one record and closes it in another arriving after the turn ended
  therefore silently never closes: `_activity_line` falls through, `_as_a_line` returns
  `""` and `_doing` drops it, with nothing logged. This is what made a role run's return
  invisible for every run there had ever been (rol-1-964h, 2026-08-02), and it reads
  exactly like a feature nobody built. Anything outliving a turn must render from its own
  record; if you must correlate, prove it through the real `Agent.told` with a terminal
  `state` in between, and assert the entry really was popped — a case that only calls
  `_activity_line` twice in a row passes against this.

- **A test comparing two live readings of the same elapsed time passes locally and fails
  on a runner at a second boundary.** `role_run.shown` and anything calling it each read
  `time.time()` for themselves, so `AssertionError: 3000 != 3001` arrives from CI on a
  case that has run green a dozen times here. Agreeing to within a second proves nothing
  anyway — two separate computations would too. Replace the collaborator
  (`mock.patch.object(role_runs, "shown", return_value={"elapsed": 4242})`) and assert the
  value came through it.

- **Adding a field to `agent.Playing` fails `test_cli`, not the suite you are working
  in.** It is a frozen dataclass with every field required, and `tests/test_cli.py`'s
  fake agents build a real `Playing` by keyword — so a new field lands as
  `TypeError: __init__() missing 1 required positional argument` inside `cmd_serve`,
  in a suite with nothing to do with the change. Add it to that stand-in in the same
  commit; the same is true of the `Delegating`/`Shown` stand-ins in `tests/test_gateway.py`
  for anything new a gateway calls on it.

- **The gate passes locally on a developer's machine for cases that fail on a runner, because
  the suite inherits `RUNDESK_DATA_DIR` too.** An agent's shell is a gateway's child, so a case
  that calls `agent.add` reads the *owner's* configured skill baseline through `config.skills()`
  and never notices it had no install of its own. Measured: three new cases in `test_answering`
  passed under `python3 .knowledge/scripts/gate` and errored on all three CI shards. Give every
  case that makes an agent its own `RUNDESK_DATA_DIR` and `config.ensure`, the way
  `CarriesAConversation.setUp` does — and run the gate at least once under
  `env -u RUNDESK_DATA_DIR -u RUNDESK_HOME -u RUNDESK_AGENTS_DIR … HOME=/tmp/somewhere` before
  believing it.

- **A teeth probe that runs its suite through a shell variable runs nothing, and prints
  nothing, which reads exactly like a probe that passed.** This shell is zsh, where
  `E="env -u RUNDESK_HOME … python3"; $E tests/test_role_run.py` does *not* word-split:
  zsh looks for one command whose name is the whole string, fails, and the `| grep -E
  "^(Ran|OK|FAILED)"` that was meant to read the result has nothing to match — so three
  probes in a row reported no failure while none of them had executed a case. The same
  trap as `unittest -k "a or b"`, arriving by a different route. Write the `env -u …`
  prefix out in full at each call, and **read the "Ran N tests" line before believing any
  probe**: no line at all is not a pass.

- **Adding a section to `config.json` fails `test_config` on a file in `docs/`, not on
  anything you wrote.** `test_the_documented_fresh_configuration_matches_the_install_seed`
  parses the JSON block out of `docs/configuration.md` and compares it with
  `config.INITIAL`, so a new section makes it fail with a dict diff naming the section and
  no hint that the fix is a documentation edit. That is the guard working — a copied
  example missing a default is one an update will never add to. Edit the example in the
  same change.

- **`changing(target, [], …)` cannot tell a file nobody has written from one holding an
  empty list, and for onboarding state those mean opposite things.** `_understood` returns
  the `empty` value for a missing file and refuses anything whose type differs, so `[]`
  collapses "this channel is new, greet everybody on it" into "this channel has greeted
  everybody already" — a feature that silently never fires, on exactly the installs that
  most need it. Measured while building `owed_a_welcome`: with `empty=[]` a channel added
  a minute ago and a channel from three releases back read back identically. Use a mapping
  (`empty={}`) and put the list under a key, so a *missing key* is the third answer;
  `gateway._NEVER_LOOKED` is that. The same trap is waiting for anything else where "never
  written" is not "written and empty".

- **The run directory's `*.json` entries *are* the list of gateways, so anything else you
  keep there under that suffix invents one.** `gateway.every` unions the stems of `*.lock`
  and `*.json`, and `sweep` walks the same glob. Measured: dropping `ava.skills.json` into a
  scratch run directory made `gateway.every` report a gateway called `ava.skills`. Runtime
  state of any other kind goes in as a dotfile keyed by the encoded name, the way
  `update_request.maintenance_path` and `gateway._skills_last_seen` do — never `<something>.json`.

- **Running `./rundesk` from a checkout tests new code against the live install's data, and
  nothing warns you.** An agent's shell is a gateway's child, so it already carries
  `RUNDESK_AGENTS_DIR`, `RUNDESK_HOME`, `RUNDESK_SCRIPTS` and `RUNDESK_RUN` — the *owner's*.
  Measured: `./rundesk agents` from a checkout listed the machine's real agents and their PIDs;
  the same command with those variables unset and pointed at a scratch root listed none.
  `env | grep RUNDESK` before believing otherwise. The launchd half is worse, because a
  directory cannot move it: a label belongs to the person, so a second install's `--uninstall`
  boots out `ai.rundesk-automatic-update` — the live one — and leaves the other install's plist
  on disk looking well (#146). Set `RUNDESK_JOB_PREFIX` for anything that touches a job, and
  check `launchctl list | grep rundesk` before and after. The whole recipe is
  [`guides/testing-against-a-station.md`](./guides/testing-against-a-station.md).

- **Codex's output markup is not in the codex binary — it is in the skills it downloads, so
  grepping the executable for it finds nothing and looks like proof it does not exist.**
  `:codex-file-citation{path="…" purpose="output"}` is instructed by the bundled document
  skills, not the CLI: `LC_ALL=C grep -ao 'codex-file-citation.\{0,400\}'` over the 271 MB
  binary at `~/.codex/packages/standalone/releases/<version>/bin/codex` returns nothing, while
  `grep -rl` over `~/.codex/plugins/cache/openai-primary-runtime/*/<version>/skills/*/SKILL.md`
  gives the whole grammar with examples. Grep the plugin cache *and* the binary before deciding
  this vendor never emits something; `~/.codex/sessions/**/rollout-*.jsonl` holds real captures
  of what it actually wrote.

- **A run's account holds no record of what its brain *said*, so "the account keeps every
  raw event" is false for text.** `store.RECORD_KINDS` has no `text` member and
  `turn._Account.add` returns before writing one — including its `raw` — because what was
  said is a message and only what *happened* is a record. So the only place a brain's
  individual thoughts survive is `logs/runs/<run>.jsonl`, which R-STO-5 and R-RUN-23
  explicitly allow to be destroyed and swept — **and which R-RUN-22's `transcript.trim`
  bounds on every single turn, in `carry`'s own `finally`, keeping the tail and discarding
  the head.** That is the near one, not the seven-day sweep: measured runs on this machine
  reach 3.7 MB against a 4 MB `CEILING_BYTES`, and a scheduled turn is `fresh=True`
  (R-SCH-29), so those are that turn's own records. Anything narrowing what the message row
  holds is narrowing the durable account, whatever the record table appears to promise —
  and the early thoughts it drops are the ones the trim takes the minute the turn ends,
  not in a week. Check with
  `sqlite3 <agent>/state.db "select kind, count(*) from record where run_id=? group by kind"`
  on a real run before believing otherwise — a 3.7 MB transcript beside a run with no text
  record in it is what this looks like.
- **`getattr(vendor_object, "name", default)` is a silent feature-killer, and a stand-in
  carrying an attribute the real class does not have will agree with you for ever.**
  `_post`'s anchor guard asked a `discord.Message` for `channel_id`, which discord.py has
  never had, so `getattr` handed back `""`, `"" != conversation` was true of every message
  ever posted, and no answer rundesk sent to Discord was a reply for months (#151). Nothing
  raised, nothing logged, and the case covering it passed — it grepped the source for the
  guard and built its message from a `class Message: channel_id`, a shape the platform does
  not have. **Before trusting a defaulted `getattr` on somebody else's object, ask the
  installed library whether the attribute exists** — `.venv/bin/python -c "import discord;
  print(hasattr(discord.Message, 'channel_id'))"` — and build a stand-in only out of
  attributes that answered yes. A guard whose wrong reading fails *open* takes the whole
  feature with it and looks exactly like a feature nobody built.
- **A rundesk agent running the gate fails four suites on its own environment, not on the
  code.** A turn is handed `RUNDESK_AGENTS_DIR`, `RUNDESK_SKILL_LIBRARY`, `RUNDESK_SCRIPTS`
  and friends, the suites inherit them, and `test_agent`, `test_skill`, `test_transcript`
  and `test_process` then resolve to the owner's real data home — so their isolation cases
  fail with paths under `~/.rundesk` where a scratch root was expected. Identical on a clean
  `main`, and green on CI, which has none of them set. Prefix the gate with
  `env -u RUNDESK_AGENTS_DIR -u RUNDESK_SKILL_LIBRARY -u RUNDESK_SCRIPTS -u RUNDESK_HOME
  -u RUNDESK_SKILLS -u RUNDESK_PROVIDER_HOME -u RUNDESK_RUN -u RUNDESK_POSTURE
  -u RUNDESK_RESUME -u RUNDESK_PREFACE -u RUNDESK_RAW -u RUNDESK_CWD` and it is green.
  Do not spend an hour hunting a regression in these four first.
- **A new field on a provider record reaches no surface until it is named in
  `_Shown.AS_IT_HAPPENS`.** It is an allowlist of exactly which of each record's fields
  cross the channel seam (R-CH-13), so an adapter can report a quantity, a channel can
  render it, both suites can be green, and a chat footer still shows nothing — nothing
  errors and nothing is logged. `written` cost the project two releases of exactly this:
  it sat in the Discord footer's slot list from v0.17.0 and never once arrived, because
  that list did not name it (#155). Add the field there in the same change, and prove it
  end to end (`test_answering.py` drives the seam and never skips; a case that only calls
  an adapter proves half, and skips wherever the dependency is absent).
- **Antigravity's `-p` flag consumes its next argument; it is not the switch for a piped
  prompt.** `agy -p --output-format stream-json` asks the model about `--output-format`, and
  `agy ... -p ""` rejects an empty prompt. For the private stdin transport Rundesk requires,
  pipe the prompt to `agy --output-format stream-json` with no `-p`; non-TTY stdin selects
  print mode and keeps the prompt out of the process list.
- **Ignored live-probe trees inside a worktree can make `test_cli.py` look hung.** A 620 KB
  `.knowledge/tmp` probe tree containing a nested Git repository, vendor logs and captured
  output left the suite traversing directories for more than fourteen minutes; moving the
  exact probe tree to `/tmp` returned the suite to 27 seconds. Keep live captures outside
  the checkout and commit only small sanitized fixtures.
- **Fake command collaborators do not isolate direct global resolvers.** `test_cli` walks
  every operation with fake gateways, agents, skills and a machine, but bare `backups`
  calls `backups_home()` directly; the aggregate gate left it reading the owner's backup
  directory until the new ceiling captured a 180-second `pathlib.iterdir` stack. Whenever
  a command reaches a directory outside an injected collaborator, redirect that resolver
  for the whole surface suite and assert the scratch boundary before walking every verb.
- **A shell does not move into a worktree it just created.** A command such as
  `git worktree add <path> <branch> && sed …` runs the read in the original checkout, so
  release preparation can inspect or edit a stale version while the new worktree is correct.
  Start the next command with the new worktree as its working directory, then verify its
  branch before editing.
- **A station wrapper that consumes every leading `--*` option cannot forward
  `install.sh --uninstall`, and its install mode resolves the canonical checkout rather
  than the worktree it was invoked from.** Run both installer directions from the target
  worktree directly with the same fully redirected station environment and job prefix;
  otherwise the wrong source is tested or the temporary automatic-update job stays loaded.
- **A scratch data root that no install has ever run against has no `config.json`, so the
  first `add` fails with `NOT MADE — <data>/config.json: 'skills' is missing` and names
  nothing you did.** `install.sh` is what seeds it, and in a disposable station installing
  is exactly what is blocked, because the shared launchd labels are per user. Seed it
  instead: with the station's environment exported, `python3 -c "import sys;
  sys.path.insert(0, 'src'); from rundesk import config; config.ensure()"` answers
  `['backups', 'updates', 'roles', 'skills']` once and the same `add` then succeeds.
- **A fresh worktree has no `.venv`, so its Discord regression test skips and looks green.**
  Run the worktree's test path with the main checkout's `.venv/bin/python`; the interpreter
  supplies `discord.py` while the working directory and imported adapter remain the worktree's.
- **A test class appended to the end of a suite file lands *after* the `__main__` guard and
  never runs — and the suite still says `OK`.** `tests/test_gateway.py` reported the same 184
  cases with a new four-case class in it, which reads exactly like a class that passed. Insert
  a new class before the guard, and check the count moved before believing a green run.
- **An agent running the gate on its own repository fails three cases that have nothing to
  do with its change.** A rundesk turn's environment already carries `RUNDESK_HOME`,
  `RUNDESK_AGENTS_DIR`, `RUNDESK_SCRIPTS` and nine more, and `test_process` and `test_cli`
  read them straight through their fixtures — so `PATH` comes out as the *live* install's
  scripts directory and the assertion points at product code that is fine. Unset every
  `RUNDESK_*` variable for the gate command itself (`env -u RUNDESK_HOME -u … python3
  .knowledge/scripts/gate`), not only for scratch installs. Costs a full 80-second run and
  reads exactly like a real regression.
- **`~/.rundesk` is the owner's live install. Never touch it.** It is a running product with
  real agents, real channels and real history in it — not a fixture. **Never install,
  uninstall, update, migrate, start, stop, add, remove or write anything there**, and never
  run a command that resolves there by default, which is most of them. This is not a thing to
  weigh against convenience: a scratch agent is free and a stopped gateway of theirs is not.
  Test installs somewhere else by **clearing every inherited `RUNDESK_*` variable first**,
  then setting `RUNDESK_INSTALL_DIR`, `RUNDESK_BIN_DIR`, `RUNDESK_DATA_DIR`,
  `RUNDESK_BACKUP_DIR`, `RUNDESK_AGENTS_DIR`, `RUNDESK_RUN_DIR`, `RUNDESK_LOG_DIR` and
  `RUNDESK_JOBS_DIR` under scratch. Omitting `RUNDESK_DATA_DIR` while the rest were pointed
  away let a scratch uninstall remove the live built-in skills; omitting the jobs boundary
  let the gate boot out a waiting live update worker. Check `find $SCRATCH` has something in
  it before believing a run was isolated, and check `ls ~/.rundesk` afterwards to be sure it
  did not.

- **`./install.sh --uninstall` deletes the *checkout's* `.venv`, whatever else you redirected.**
  `install.sh` removes `${SCRIPT_DIR}/.venv` along with the install's own, which is symmetric — the
  install put `discord.py` there — but it is also where a *developer's* suite and a developer's
  `./rundesk` load it from. Two consequences, both delayed: the Discord cases silently start
  skipping, and a gateway already serving a channel survives (it imported `discord` already) but
  cannot come back on its next restart, so it presents minutes later as a channel that will not
  return. Rebuild straight afterwards — `./install.sh`, or `python3 -m venv .venv &&
  .venv/bin/python -m pip install -r requirements.txt` — and check
  `.venv/bin/python -c "import discord"` before believing a green suite.
- **The command sandbox rejects an isolated install check when its chain ends in `rm -rf`,
  even for a validated `mktemp -d` directory.** The command never starts, so it proves
  nothing about the installer. Leave the scratch directory in place for that run and report
  its path, or remove it later through an approved recoverable cleanup.
- **`OK (skipped=65)` and `OK` are the same word to whoever reads the gate, and CI is the
  machine where it matters.** `test_discord` loaded the adapter from `src/rundesk/channels/discord`,
  which the src restructure had moved to `src/channels/discord`; the loader raised, a bare
  `except BaseException` set the module to `None`, and every case skipped for months while the gate
  said `ok`. CI runs with an *empty* `.venv` on purpose, so the Discord cases skip there
  legitimately — which means a suite skipping for the *wrong* reason skips there too and nothing
  goes red. **A suite may only skip for the reason skipping is for.** Whether the adapter file
  exists does not depend on the dependency, so it is asked first and raises on every machine;
  anything else is a skip only when `discord.py` is genuinely absent, asked of the import directly
  — never inferred from how the adapter failed, since it catches its own missing import, prints a
  record and exits, so its exception cannot be told apart from being broken. **The guard is
  partial by design**: a load breaking for a third reason still degrades to a skip wherever
  `discord.py` is absent, which is CI. Check with `.venv/bin/python tests/test_discord.py` and read
  the *count*, not the word — `python3` alone has no `discord` and skips honestly, so the two
  failures look identical from the wrong interpreter.
- **A 3.9 interpreter that can see the checkout's `.venv` dies in `yarl`, and it looks like a real
  break.** 3.9 finds `.venv/lib/python3.14/site-packages`, imports a `discord` built for another
  Python, and `yarl` falls back to its pure-Python quoter, whose signature is PEP 604: `TypeError:
  unsupported operand type(s) for |`. Not a `ModuleNotFoundError`, so the skip guard does not catch
  it, and nothing in the traceback says the cause is one interpreter reading another's virtualenv.
  **CI never sees it** — it runs 3.9 with an empty `.venv`, which is the whole point. It arrives two
  ways. Through the gate: `PY = sys.executable`, so a shell whose PATH does not reach Homebrew runs
  every suite on `/usr/bin/python3`; `FAIL test_discord` naming nothing of ours while the other
  nineteen suites are green is this. Use **`.venv/bin/python .knowledge/scripts/gate`**. Through the
  floor check `for f in tests/test_*.py; do /usr/bin/python3 "$f"; done`: run the others on
  `/usr/bin/python3` and **`test_discord` on `.venv/bin/python`**.
- **`gate > log; echo "GATE_EXIT=$?" >> log` reports the *echo's* status, not the gate's.** A
  compound command exits with its last member, so a harness or a `&&` chain reads `0` from a gate
  that failed — and the real code is only in the file, which nobody re-reads once they have been
  told it passed. Two runs were reported green this way while `test_transcript` was failing in
  both. **Run the gate as the only command in its shell** and read the exit the runner gives you,
  or grep the log for `^FAIL` before believing any summary, including your own: a run that printed
  `ok` against all 19 suites still exited 1 on a check above them.
- **The gate inherits agent-turn variables that break its isolation, plus Apple's system Python
  writes bytecode outside the checkout.** `RUNDESK_AGENTS_DIR`, `RUNDESK_SCRIPTS`,
  `RUNDESK_SKILLS` and `RUNDESK_SKILL_LIBRARY` point isolation suites back at the live install,
  producing failures in agent, skill, install, process and provider tests; Python can also create
  `Library/Caches/com.apple.python` under the install suite's scratch `HOME`. Unset every ambient
  `RUNDESK_*` turn variable and point `PYTHONPYCACHEPREFIX` at a fresh temporary directory before
  running the gate; neither changes product behavior, and the failures otherwise look like real
  regressions.
- **Validate install and uninstall only with every install, data, bin, jobs and backup path
  redirected into one scratch root.** The installer acts on the machine it is run from, and
  `tests/test_install.py` drives a *copy* of the checkout for exactly that reason: run against the
  checkout itself it deletes the `.venv` a live install is made of. (`--help` no longer installs —
  R-INS-17 — but every other invocation still does.)
- **A scratch root is not enough on a machine with a live install: the uninstall still takes the
  live `ai.rundesk-automatic-update` job away.** launchd labels are per *user* and job files are
  per *install*, so `remove_automatic_update` checks ownership of the scratch plist, passes, and
  boots out the only registration the shared label can have. The live plist stays on disk, so
  nothing looks wrong and the machine has silently stopped updating itself (#146). Check
  `launchctl list | grep rundesk` before and after every install/uninstall verification, and put
  back whatever went with
  `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.rundesk-automatic-update.plist`.
- **Waiting for the gate with `while pgrep -f "scripts/gate"` never ends, because the waiter
  matches itself.** The pattern is in the waiting shell's own command line, so `pgrep` finds it
  and every waiter keeps every other waiter alive — six were still spinning long after the runs
  they watched had finished, and one looked like a gate that would not end. Wait on the *output*
  instead: `until grep -q "GATE_EXIT=" "$log"; do sleep 20; done`.
- **Deriving a new directory from `agents_home().parent` isolates nothing — derive it
  *downwards*.** It reads like "beside where agents are kept", which for an owner is
  `~/.rundesk` and is right; for a suite it is whatever the scratch directory happens to sit
  in, which is the shared temp root. Every case then shared one directory, and one case's
  template turned up in another case's agent — passing or failing by test order. Anything
  hung *below* `agents_home()` cannot do that, because redirecting the root redirects it
  (`templates_home()` is `agents_home().joinpath(*OVERRIDES)` for exactly this reason).
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
- **`RUNDESK_HOME` does not redirect where agents live — `RUNDESK_AGENTS_DIR` does.** The name
  reads like the root of everything and is not: `agent.py` resolves the agents root from
  `RUNDESK_AGENTS_DIR` alone, falling back to `~/.rundesk/agents`. So a scratch run that sets
  `RUNDESK_HOME`, `RUNDESK_RUN_DIR`, `RUNDESK_LOG_DIR` and `RUNDESK_JOBS_DIR` — which looks
  exhaustive — still writes real agents into the owner's own `~/.rundesk/agents`, and
  `rundesk add` reports success while doing it. Three were created that way and had to be
  removed with `rundesk remove`. Set `RUNDESK_AGENTS_DIR` too, and check `find $SCRATCH`
  actually has something in it before believing a command was isolated.
- **A gateway or an install redirected only part-way still reaches the real one.** Two shapes of
  the same mistake. A test that builds a `Gateway` without **both** `RUNDESK_RUN_DIR` and
  `RUNDESK_LOG_DIR` at scratch writes into `~/.rundesk`; the suite did, and left nine log files in
  the owner's home — point logs somewhere *outside* the run directory too, or the "leaves nothing
  behind" cases trip over them. And an install/uninstall gate with only `RUNDESK_INSTALL_DIR` and
  `RUNDESK_BIN_DIR` redirected still discovers and stops **live gateways** through the ambient
  state directories: point `RUNDESK_RUN_DIR`, `RUNDESK_LOG_DIR`, `RUNDESK_AGENTS_DIR` and
  `RUNDESK_JOBS_DIR` at scratch as well before running the destructive half.
- **A brain running `rundesk` picks a different `python3` than you did, and `fitness()` then
  refuses.** `rundesk` is `#!/usr/bin/env python3`, so what it resolves depends on the PATH of
  whoever ran it — a developer's shell finds Homebrew's 3.14, and a brain's tool shell finds
  `/usr/bin/python3`, which is 3.9.6. The `.venv` is built for whichever one ran `install.sh`,
  so the other reports `what rundesk needs was installed for python3.14, and this is python3.9`
  and the agent's records read as unavailable. Grok found this by being told to look something
  up and reporting what it actually got. Reproduce with
  `env PATH=/usr/bin:/bin ./rundesk doctor <agent>`; it is not a bug in the store.
- **A provider adapter probed directly from inside another provider's turn inherits that
  turn's `RUNDESK_RESUME`.** The adapter then tries to load an opaque session belonging to
  the wrong brain and fails with `session/load: Path not found`; unset `RUNDESK_RESUME` for
  a fresh direct probe, or set it only to a handle that adapter reported.
- **`until gh run view …; do :; done` spends five thousand API calls in a couple of minutes
  and locks you out of GitHub for the rest of the hour.** The loop body is empty, so it asks
  as fast as the network answers — four of those while watching a release exhausted the
  authenticated quota (5,000/hr, shared by every tool and agent on the account), and then
  *nothing* could read a run, a release or an issue until the top of the hour. Watching a
  workflow is the obvious thing to do and this is the obvious way to write it. Use
  `gh run watch <id> --exit-status --interval 20`, which GitHub paces for you, or put a
  `sleep 20` in the loop. Check what is left with
  `gh api rate_limit --jq .resources.core` before starting anything that polls.
- **Backticks inside a double-quoted zsh search pattern are command substitutions.** A pattern
  such as one containing `` `rundesk-attach:` `` fails before `rg` runs when its Markdown backticks
  are unmatched. Use single quotes around literal Markdown search patterns.
- **`gh release view --json isLatest` fails because this `gh` does not expose that field.**
  The command prints its supported release fields and exits before anything chained after it
  runs. Use `tagName,name,publishedAt,url` and compare `tagName` with
  `gh release list --limit 1` when whether it is latest matters.
- **`gh issue list --json type` fails even though `gh issue create --type` is valid.**
  The issue classification field is named `issueType` in JSON output; use that when checking
  existing issues before filing one.
- **This installed `gh` does not accept `--repo` on `gh repo view`.** Pass the repository as
  the positional argument (`gh repo view owner/repo --json ...`); the documented-looking flag
  fails before any repository information is read.
- **zsh expands an unquoted `?ref=main` in a `gh api` endpoint as a filename glob.** The
  request never reaches GitHub and fails with `no matches found`; quote the whole endpoint.
- **In zsh, `path` is a special array tied to `PATH`.** Assigning a file path to a shell
  variable named `path` replaces the command search path, so the next `gh`, `base64` or other
  executable reports `command not found`. Use a task-specific name such as `skill_file`.
- **The system skill creator's `quick_validate.py` is not zero-dependency.** It imports
  PyYAML and fails with `ModuleNotFoundError: No module named 'yaml'` on the repository's
  standard-library Python. Do not install around the repository contract; validate shipped
  skill frontmatter with `tests/test_skill.py` and the full gate.
- **GitHub's repository issue-types endpoint requires its current API version header.** A bare
  `gh api repos/<owner>/<repo>/issue-types` used gh's older default and returned HTTP 404 even
  though the types exist. Pass `-H 'X-GitHub-Api-Version: 2026-03-10'`; `gh issue view --json`
  names the returned field `issueType`, not `type`.
- **`gh pr list --head` does not accept the `owner:branch` syntax that `gh pr create --head`
  accepts.** It returns no matches rather than flagging the qualifier. Search with the bare
  branch, request `headRepositoryOwner`, and compare that field before treating a PR as the
  same head.
- **macOS `tar` has no GNU `--wildcards` option.** Extracting one member from a generated
  archive fails before reading it; list the archive, select the exact member name, then pass
  that name back to `tar -x`.
- **`unittest -k "a or b"` runs nothing and says `NO TESTS RAN`, which in a teeth probe reads
  exactly like "the test passed".** `-k` takes a substring, not an expression — an `or` matches
  no test name at all. Two probes in a run of six reported the code was fine when neither had
  executed a single case. Pass `-k` twice for two patterns, and **read the "Ran N tests" count
  before believing any probe**: a probe that ran zero tests has proved nothing in the direction
  that matters. The same run also showed that a probe naming *one* test can pass while a
  sibling catches the break, so a green probe means "this case has no teeth", never "the code
  is unprotected" — narrow to the case, then widen to its class before concluding either.
- **Adding any `RUNDESK_*_DIR` resolver fails `test_supervisor` until the launchd job carries
  it.** `test_the_job_carries_every_place_rundesk_can_be_pointed_at` scrapes
  `environ.get("RUNDESK_..._DIR")` out of the *source* of `gateway`, `agent` and the package
  `__init__`, then asserts `supervisor.describe()` names every one it found. So a new directory
  variable is caught the moment it is written, in a suite that looks unrelated to the feature
  adding it — which is the guard working, not a broken test. Add the variable to `describe()`'s
  `EnvironmentVariables` in the same change; a supervised gateway resolving a different place
  from the command that wrote its job is the failure it exists to prevent.
- **A requirement row is capped at 25 words and `doc-lint` counts them, drafts included.** The
  message is exact — `R-ROL-38 requirement is 28 words (max 25)` — but nothing says so while you
  are writing the row, and a requirement written to be unambiguous lands at about thirty. Say the
  guarantee and drop the justification; the reasoning belongs in the rules or the test docstring,
  not in the row.
- **A Markdown link out of `.knowledge` passes `doc-lint` and fails the gate.** `doc-lint
  .knowledge` resolves a catalog link against the real checkout, so
  `[docs/extending/](../../docs/extending/)` in `guides/README.md` is fine — and then
  `test_doc_lint.py`, which is the gate's *teeth* check, copies `.knowledge` into a scratch
  tree **on its own**, with no sibling `docs/`, `src/` or `tests/`. The link is now missing,
  doc-lint reports a problem it is supposed to report nothing for, and the failure reads
  `[FAIL] an internal source needs no link (exit=1, wanted_ok=True)` — which names a rule
  about *sources* and says nothing about your catalog link, in a check whose other 43 cases
  pass. Name a path outside `.knowledge` in backticks; never link it. Standalone doc-lint
  cannot catch this, so run `.knowledge/scripts/test_doc_lint.py` before believing a green
  linter.
- **`skill.home()` resolves to the owner's live library when *every* `RUNDESK_*` variable is
  unset — unsetting them is the opposite of isolation here.** It is
  `RUNDESK_SKILL_LIBRARY or skills_home()`, and the fallback is `~/.rundesk/data/skills`,
  which is the live install. So a scratch script that carefully scrubs the environment and
  then calls any `skill` function without an explicit `where=` is pointed straight at the
  owner's eighteen built-ins, and `retire`/`take_back` delete them. Scrub the inherited
  variables and then **set `RUNDESK_DATA_DIR`, `RUNDESK_SKILL_LIBRARY` and
  `RUNDESK_AGENTS_DIR` under a scratch root before importing the module**, and assert
  `str(scratch) in str(skill.home())` as the first line that runs. Checking `env | grep
  RUNDESK` is empty proves the danger, not the safety.
- **A backticked anything in an Evidence cell is read as the name of a test.** That is the whole
  mechanism keeping a ✅ honest, and it does not care that the row is ❌ or that the backticks are
  around a filename, a path or a script. Write those plainly in a note — `check-evidence` fails the
  gate with "is ❌ but names a test", which reads like the row is wrong when the punctuation is.
  Renaming that test without updating every PRD citation fails the same gate; search Evidence for
  the old humanized test name in the same change.
- **`instructions.render()` preserves a template's trailing whitespace; `instructions.build()`
  strips every rendered layer before joining it.** A test comparing a raw rendered layer with a
  built preface differs only by the final newline and produces a page-long assertion diff; strip the
  rendered layer when proving exact composition, or assert against the final built string.
- **Schedule-trigger wording is asserted at both the builder seam and the gateway account seam.**
  Changing `SCHEDULE_INSTRUCTIONS` can leave targeted instruction tests green while `test_gateway`
  still expects a retired phrase; search the old distinctive wording across `tests/` before the
  full gate.

*The entries below are traps in a **vendor's CLI**. We cannot fix them, only re-verify — and a version
bump can invalidate one in either direction. Each was probed when it was written; none has been
re-checked since, so treat these as true-when-found rather than as current.*

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
- **Grok ACP ignores root `--rules`; append standing instructions through `_meta.rules` on
  `session/new`.** The root flag works in one-shot mode and is silently accepted by `agent stdio`,
  but a live ACP marker disappeared there. The session metadata field returned the exact marker
  and the indirect attachment protocol on 0.2.112. Do not send it on `session/load`: rules bind
  when the conversation is created. Root `--tools` is also ignored by ACP and remains tracked in
  issue #250 rather than being mistaken for a working read boundary.
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
- **`codex exec` will not sign in from a home it was not given.** `CODEX_HOME` isolates
  credentials as well as configuration — the sign-in is `auth.json` inside it, a plain file
  rather than a keychain — so a scratch home means `401 Unauthorized` on every request and a
  conformance run against the real adapter that proves nothing. Point `--home` at a home that
  has one. A symlink to the owner's own works and stays a link; a copy works and goes stale on
  the next token refresh. Rundesk makes neither for them.
- **`claude --help` does not list every flag `claude` accepts, so absence from it proves nothing.**
  `--permission-prompt-tool` — the flag a whole documented approval route rests on — is missing
  from 2.1.220's help output and is still accepted by the parser. The free way to tell is the
  control: a genuinely unknown flag dies with `error: unknown option '…'` **before a turn
  starts**, so passing the flag under test costs nothing when it is gone and one live turn when
  it is not. Run the bogus-flag control first, and never conclude a vendor dropped something
  from `--help` alone.
- **A second connection with the same bot token silently wins.** Running the Discord
  adapter by hand to diagnose it, while a gateway is already serving that channel, makes
  one of the two stop receiving — with no error on either. Stop the gateway first, or
  accept that what you are watching is not what the gateway sees.
- **Guessing a vendor's field names costs a whole feature, silently.** The Codex adapter
  looked for `changes`, `files`, `artifacts` and `outputs`; Codex emits `savedPath`. Nothing
  errored — a generated image was simply never reported. Read a real item out of a run's
  `.brain` file before writing the name of a field.
- **Codex raw response usage has two separate opt-ins.** `initialize` must enable
  `capabilities.experimentalApi`, and a new `thread/start` must also set
  `experimentalRawEvents`; the first only makes the second legal and emits nothing alone.
  The thread keeps that setting when resumed, where the start-only field must not be sent.

- **Do not test a model instruction with a question the conversation can already answer.** A first
  attempt asked for a codename the thread had been asked for before, so the model answered from its
  own earlier reply and the resume looked like it worked. Use a rule the history cannot supply, and
  run the control: prove the same rule *is* obeyed when given at the start.
- Installing dependencies leaves **caches outside rundesk's own directory** — pip and any build
  tooling it reaches for write under `~/.cache`, `~/Library/Caches`, even `~/.rustup`. Removing
  rundesk cannot take those and does not try. Do not word a requirement as "everything an install
  puts on a machine", because it is not true; ours is what rundesk *is made of*.
- **A scratch install still inherits `RUNDESK_SKILL_LIBRARY` and `RUNDESK_SKILLS`.** Redirecting
  only install, data, agent, run, log and job directories let the scratch uninstall remove the
  live built-in skill copies. Unset every ambient `RUNDESK_*` variable first, then set each
  scratch path explicitly; restore with the live `rundesk skills --lay-down` if this already
  happened.
- A downloaded install is a directory of source with an `install.sh` in it, which is **exactly what a
  clone looks like** — so the guard protecting a developer's checkout refused to remove `~/.rundesk`
  and uninstalling silently left it. What tells them apart is whether the script sits in the
  directory the installer was told to create.
- **A `Gateway` built without `root=` asks whether the *developer's checkout* fits**, so with anything in
  `requirements.txt` every case that claims a name refuses on a machine that has run the installer, and
  passes in CI, which has no `.venv`. Give any gateway a test builds a scratch `root`; only the fitness
  cases build an install. The suites are isolated now — the trap is writing the next one without it.
- **Never name a real process group in a test — `killpg` degenerates at `0` and at `1`.** It means "that
  group" only above one. Group `0` is the caller's own, and killed the test run and its shell. Group `1`
  looks safe and is worse: on Linux it is `kill(-1, …)`, *every process this user may signal*, so it took
  the CI runner's own agent with it — the step then hung forever with an empty log, no timeout applied and
  cancels did nothing, because nothing was left alive to answer. macOS returns an error instead, so it
  passed there every time. Replace `os.killpg` and assert on what was asked. The convention is held by
  hand in `test_gateway.py` and `test_process.py`; nothing mechanical stops the *next* test naming one.

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
  anything that reads it back.
- **The stand-in `Brain` in `test_answering.py` never calls `store.opened`.** So nothing that reads
  `conversations()` after driving a fake turn finds one — open it yourself when what is under test
  is where something goes rather than how it got there.
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
- **`pkill -f "tests/test_*.py"` in this checkout kills whatever *another agent* is running,
  and their gate then reports a failure that never happened.** More than one agent works in
  this worktree at once, so a suite you did not start is the ordinary case rather than a
  stray: a leftover-looking `test_gateway.py` was a step inside somebody else's gate, killed
  by a cleanup that had every reason to look safe. Before killing anything, read the parent —
  `ps -o ppid= -p <pid>` up to the `scripts/gate` that owns it, and look at the log path in
  its command line: it names the **session** that started it, and one that is not yours is
  not yours to end. A suite left running past a few minutes is far cheaper than a green gate
  somebody has to re-run without knowing why it went red.
- **An adapter that can find itself on its own PATH is a fork bomb.** An adapter looks its
  brain up by name; committing the stranger's adapter under the brain's own name and putting
  that directory on `PATH` meant it resolved the brain to *itself*, ran itself, and that
  copy did the same — **eight thousand processes and a load average of 641** before anyone
  noticed, because each generation looks exactly like a legitimate adapter run. The brain is
  named what the adapter looks for and the adapter is named something else (`driftwood` and
  `driftwood-adapter`), and `_nothing_of_ours_is_on` in `test_provider.py` now fails the case
  rather than the machine. That guard covers that one case; putting an adapter directory on a
  `PATH` by hand is still a fork bomb.
- **Never leave overlapping runs of a suite in the background, and never edit `src/` while one
  is going.** Repeatedly relaunching the gate and `test_provider.py` while earlier ones were
  still running left real gateways, real `codex app-server` processes and `sleep 300` stand-ins
  alive across a dozen generations — and made the fork bomb above take minutes to spot rather
  than seconds. The same rule covers a *teeth probe*: breaking a module to prove a case has
  teeth while a background gate is part-way through that suite fails it against code you had
  already restored, and the failure names the module, so it reads as a real break in your own
  work. One run at a time; check the previous one is gone before starting another, and hold
  every `src/` edit until it is.
- **A test flag that points at a real directory points *every* case at it.** `test_provider.py
  --home ~/.codex` was meant for the adapter under test and reached the stand-ins too, so they
  wrote their own bookkeeping into the owner's real Codex home and read what an earlier run had
  left there — one case failed and the rest passed while quietly polluting it. Anything that
  redirects a case at something real must be scoped to the one class that needs it, and
  everything else left on scratch.

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
- **The gate cannot catch a 3.9 break, and CI can.** It runs on one Python — whatever `sys.executable`
  is — and its parse check is `ast.parse`, which accepts `dict[str, bytes | None]` happily. A PEP 604
  `X | None` in a *signature* is evaluated at import on 3.9 and raises `TypeError: unsupported operand
  type(s) for |: 'type' and 'NoneType'`, so a suite that passes the whole gate dies on the floor version
  CI pins. Every file needs `from __future__ import annotations` — five still lack it
  (`src/rundesk/__init__.py`, `tests/test_gateway.py`, `test_process.py`, `test_schedule.py`,
  `test_supervisor.py`) — and the check before pushing is
  `for f in tests/test_*.py; do /usr/bin/python3 "$f"; done` — macOS ships 3.9.6 at that path, which is
  exactly the floor. `.knowledge/tmp/like-ci` exists for this.
- **An agent-run gate inherits `RUNDESK_AGENTS_DIR`, and `test_provider` treats it as leaked provider
  state.** Remove that one variable for the gate:
  `env -u RUNDESK_AGENTS_DIR python3 .knowledge/scripts/gate`.
- **macOS's system Python may make `Library/Caches/com.apple.python` under `test_install`'s fake HOME.**
  That correctly fails the test for undeclared install output even though the installer did not write it;
  run the gate with `PYTHONDONTWRITEBYTECODE=1` so the interpreter makes no bytecode cache there.
- A test class appended **after** the `if __name__ == "__main__": unittest.main()` block never runs —
  Python reaches the runner before the class is defined, and the count silently stays where it was.
  Keep that block last in every test file, and check the "Ran N tests" number moved.
- Coverage without a dependency: `trace.Trace(count=1)` over both suites **in one process**
  (`t.results().write_results(show_missing=True, coverdir=…)`, then grep `>>>>>>`). Running
  `python3 -m trace` once per test file overwrites the previous file's `.cover` and reports nonsense.

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
  switching back in a shared worktree would disrupt whoever is working in it. A red suite can
  be theirs and not yours — prove it in a scratch **copy** of the checkout rather than by
  changing anything in the tree they are working in.
- **`SUGGESTIONS.md` finding numbers are taken while you are writing.** Numbers are never
  reused, so two agents filing at once both reach for the next one — 41 and 42 were claimed
  by another round mid-review. Re-read the file's tail immediately before you number
  anything, and append rather than editing near somebody else's section.
- **A stand-in that is more generous than the real thing hides whole features.** Twice
  here: a fake `turn.carry` volunteered what the brain could do, which the real one never
  passed on, so steering was dead behind a green suite; and a fake `Outcome` was missing an
  attribute the real one has, so a code path raised only in production. Give a stand-in
  exactly the surface of the thing it stands for — no more.

- **A guard written as a regex over source must be written against how this package actually
  imports, and must be probed by *adding* the thing it forbids.** A case holding "the product does
  not reach the new store yet" looked for `from store import` and for a line starting
  `import …store…`. Every module here writes `from rundesk import gateway, store`, which is
  neither — so the case that was supposed to hold the whole safety passed green through the commit
  that broke it. Removing the forbidden thing proves nothing; only adding it does.
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
  fits and `20260726120000` does not. `migration.found()` refuses anything above `CEILING`, and
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
- **`store.usage()` on an agent that has run nothing reports `None` for `input`, `output` and
  `cached`**, not `0` — `SUM` over no rows is NULL. `runs`, `reported` and `unreported` are counted
  and come back as integers, so only three of the six are absent. This is deliberate, not a defect:
  `test_what_an_agent_cost_counts_a_run_it_cannot_account_for_apart` pins it, because absent and
  zero are different claims. A case asserting zeros on a fresh database fails; do not "fix" it.
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

- **`test_process` fails three cases when the gate is run by an agent rundesk is running.**
  A gateway exports a dozen `RUNDESK_*` variables into the turn's environment — `RUNDESK_HOME`,
  `RUNDESK_AGENTS_DIR`, `RUNDESK_CWD` and the rest — and those cases assert on a environment
  built from a fixture's own paths, so they read the live install's instead and the diff looks
  like a real defect in what a program is handed. It is not: clear the `RUNDESK_*` names and
  all 101 pass. CI never sees it, because CI is not an agent. Check `env | grep RUNDESK`
  before spending a diagnosis on it.

- **`RUNDESK_DATA_DIR` does not isolate a scratch install when an agent is running the work.**
  `agents_home()` is `RUNDESK_AGENTS_DIR or data_home()/agents`, and its own variable wins — so
  a gateway, which exports `RUNDESK_AGENTS_DIR` into every turn, silently overrides the data
  directory a scratch station just set. `rundesk add probe` then makes a **real agent in the
  live install**, and `rundesk agents probe` is what says so, several commands too late. Set
  both, or scrub every `RUNDESK_*` name:
  `env $(env | grep -o '^RUNDESK_[A-Z_]*' | sed 's/^/-u /' | tr '\n' ' ') ./rundesk …` —
  which is also what makes the gate pass under an agent (the note above).

- **A `TestCase` helper called `_outcome` overwrites unittest's own, and the failure names
  neither.** `unittest` keeps the running case's `_Outcome` object on `self._outcome`, so a
  helper of that name shadows it and every case using it dies with `TypeError: '_Outcome'
  object is not callable` — pointing at the call site, saying nothing about the collision.
  Our own domain word for what a run came to makes this an easy name to reach for; `_became`
  is free. The same trap is set for `_result`, `_subtest` and `_cleanups`.

- **A schedule's `last_outcome` says `started` before the work begins, so polling it for
  "an outcome" returns instantly and reads the wrong one.** `_remember_firing` writes it
  ahead of the run on purpose (R-SCH-9). A test that fires the clock and waits for a final
  outcome has to wait for something *other* than `started` — and then wait again, because
  what is said on a surface is said after that write, so a case about delivery otherwise
  reads the surface before anything could have reached it. `tests/test_gateway.py::_became`
  does both; `_fired` waits for a run row, which a program schedule never writes at all.

- **An `R-<AREA>-<n>` on an open branch is not reserved, and the branch finds out at rebase.**
  Ids are permanent once merged, so whatever lands first takes the number and every other
  branch holding it has to move — and doc-lint's contiguity rule means moving to the next
  free one, never to a gap. Renumbering is a whole-tree edit with a trap in it: main is
  already citing your old id for its own row, so a blind replace across the files you touch
  renames somebody else's citations too. Replace only on lines that are not in
  `git show origin/main:<file>`, then check what is left with
  `grep -rn 'R-XXX-n' src tests .knowledge` — what remains should be exactly main's.

- **A multi-line `from rundesk import (...)` in `agent.py` fails `test_store`.** The guard
  `TheOnlyWayIn.test_the_product_reaches_what_an_agent_keeps` matches
  `^\s*from\s+rundesk\s+import\s+[^\n]*\bstore\b` on one line, so wrapping the import puts
  `store` on a continuation line and the case reads it as an agent with nowhere to keep
  anything. Add a second `from rundesk import <name>` line instead of wrapping — which is
  what `cli.py` does anyway.

- **A full-gate command with an `rm -rf` cleanup trap is rejected before the gate starts.**
  The shell safety layer rejects the command even when the target came from `mktemp -d`.
  Point `PYTHONPYCACHEPREFIX` at a task-specific path under `/tmp` and leave cleanup outside
  the gate invocation.

- **`gh pr checks --required` exits nonzero when a branch has no required-check rules,
  even when every reported CI check passed.** Inspect `statusCheckRollup` and reject any
  conclusion other than `SUCCESS` or `SKIPPED` before merging; do not chain the
  `--required` command ahead of the merge.

- **A checkout path containing `bo` fails `test_cli` even when status lists no agent
  names.** Its R-CMD-5 case asserts that fixture agent `bo` appears nowhere in the whole
  status output, which includes the install path; use a worktree path without `bo`.

- **GitHub issue JSON calls expose the type as `issueType`, not `type`.** `gh issue list
  --json type` exits before listing anything and prints the valid fields; request
  `--json issueType` and read `.issueType.name`.

- **The system skill creator's `quick_validate.py` imports PyYAML, which this repository does
  not install.** Do not add or install that dependency for a built-in skill; use
  `tests/test_skill.py` and its `skill.valid()` coverage, then run the repository gate.

- **Parallel pushes from linked worktrees contend on the repository's shared config lock.** The
  remote push can succeed while `git push -u` fails to save local upstream metadata; push linked
  worktrees sequentially, or run `git branch --set-upstream-to=origin/<branch>` afterward.

- **`gh repo view` takes the repository positionally and rejects `--repo`.** Use
  `gh repo view owner/repository --json ...`; unlike issue and PR commands, this verb has no
  repository flag.

- **The disposable station defaults to the canonical checkout, not the shell's current
  worktree.** Running `station.sh --install` from a feature worktree can therefore validate
  and install a different revision while appearing isolated. Pass
  `--checkout /absolute/path/to/the/worktree` on every station install or command.

- **`status` is a read-only parameter in zsh.** A verification command that assigns
  `status=$?` aborts before its later checks. Use a task-specific name such as
  `launchd_exit=$?` for captured exit codes.

- **The test counts in `CODEMAP.md` can be stale before a change starts.** Do not increment the
  recorded number by the cases just added; run the suite and copy the actual `Ran N tests` count.

- **The system Ruby's Psych has `safe_load` but not `safe_load_file`.** A YAML verification
  using `YAML.safe_load_file(path)` fails before parsing; use
  `YAML.safe_load(File.read(path), aliases: false, filename: path)` instead.

- **A command runner resolves `workdir` before the command can create it.** A chained copy
  followed by an install fails before the copy starts when `workdir` names the future copy;
  create the directory in one invocation, then run from it in the next.

- **The release guide names a Workspace `scripts/issues-closed-by.py` that is no longer
  present.** Verify issue linkage directly with
  `gh pr view <n> --json closingIssuesReferences` and `gh issue view <n> --json state`; do
  not treat the missing helper as proof that a release issue closed.

- **This installed `gh release view --json` has no `isLatest` field.** Asking for it fails
  before returning any release data; verify tag, publication, draft and prerelease state with
  supported `release view` fields, and use `gh release list` when latest ordering matters.

- **An apostrophe inside a heredoc inside `$( ... )` breaks `bash -n` on bash 3.2**, which is
  what macOS ships and what the gate's shell check runs. `install.sh` embeds Python through
  `took="$(python3 - ... <<'SKILLS' ... SKILLS)"`, and a Python comment reading `the owner's`
  in there is reported as a syntax error dozens of lines later, at whatever line happens to
  hold an unbalanced parenthesis. Write those comments without an apostrophe.

- **`run.provider` is `NOT NULL`, so a turn with no brain cannot be written.** A case
  exercising "nothing said which brain, so the agent's own default answered" naturally reaches
  for `kept.began("channel", None, ...)` and gets `IntegrityError: NOT NULL constraint failed:
  run.provider` from inside the store rather than a refusal saying what a run needs. The empty
  string is what a run with no brain looks like in these records, and `or` chains treat it the
  same way — write `kept.began("channel", "", ...)`.
- **A station install stops before it ever lays down skills or roles**, so `./install.sh` under a
  redirected root is not evidence that either landed. The launchd bootstrap fails in that
  environment (`Bootstrap failed: 5: Input/output error`) and line 678's `die` ends the script —
  the skills step is line 682 and the roles step line 694, both after it. Prove those two by
  running what the installer runs: `rundesk skills --lay-down` from the station's `bin`, and
  `role.lay_down(<data>/agents)` / `role.take_back(<data>/agents)` in `python3` with the
  checkout's `src` on the path, all under the station environment.

---
*Editing this file? Follow the standard first: [`guides/docs-memory.md`](./guides/docs-memory.md).*
