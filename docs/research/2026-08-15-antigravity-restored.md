# Research: restoring the Antigravity adapter, and what is current about it

**Date:** 2026-08-15
**Question it answers:** which of
[the 1.1.8 findings](2026-07-28-antigravity-cli-as-a-brain.md) the restored
`src/providers/antigravity` was written against, which parts were re-checked at the version actually
on the machine, and which parts are still unproven.

This note exists because that one may not be edited: it was carried across intact and says so. What
follows is everything the restoration learned on top of it.

## Two strengths of evidence, and which is which

| | Measured 2026-07-28 | Re-checked 2026-08-15 |
|---|---|---|
| version | `agy 1.1.8` | `agy 1.1.13` |
| how | one real headless turn, captured | one fresh and one resumed checkout turn through a scratch Rundesk install |
| what it establishes | the original tool stream, usage arithmetic, and soft-denial defect | current stream shape, native-login execution, exact resume, cumulative terminal usage, per-turn step usage, and accepted flags |

The 1.1.13 turns were run from the checkout through `./dev` against a scratch `RUNDESK_HOME`. The
first stored a nonce without tools; the second process resumed the exact conversation and returned
that nonce. A separate fresh turn used `view_file` and returned the exact scratch-file contents.
One more isolated scratch turn used `write_to_file`: its active tool step named the exact absolute
destination as `TargetFile`, and the turn ended with exit zero and terminal status `SUCCESS`.
One more fresh turn, run against the adapter directly in an empty scratch directory under
`--mode plan`, read the current tool listing and confirmed `init` carries no model field; it ended
with one `done` and no `model_name`.
The checkout recorded zero unknown and zero lost records. The owner's live Rundesk install and
install-local adapter were not invoked or changed.

The 1.1.8 capture itself was carried over unchanged and renamed to
[`tests/samples/antigravity-1.1.8.jsonl`](../../tests/samples/antigravity-1.1.8.jsonl), so its name
says which version it is — the older note calls it `antigravity-stream.jsonl`. The sanitized
1.1.13 fresh and resumed streams stand beside it as `antigravity-1.1.13.jsonl` and
`antigravity-1.1.13-resumed.jsonl`.

## What `agy --help` says at 1.1.13

Every flag below was read off the installed binary. The adapter passes the first group and owns all
of them against `RUNDESK_SETTINGS` passthrough.

- `--output-format stream-json`, `--print-timeout`, `--log-file`
- `--conversation`, `--new-project`, `--model`, `--mode` (`accept-edits`, `plan`)
- `--dangerously-skip-permissions`
- offered and **not** passed: `--sandbox`, `-p` / `--print` / `--prompt`, `--json-schema`,
  `--continue`, `--project`, `--add-dir`, `--agent`, `--effort`, `--disable-slash-commands`

**`--print-timeout` defaults to `5m0s`.** That is new information against the 1.1.8 note, and it
matters: five minutes is shorter than rundesk's silence window and very much shorter than its
48-hour ceiling, so left alone it would cut short every long turn with two clocks disagreeing about
whose decision it was. The adapter sets it to `48h0m0s`, and both live 1.1.13 turns accepted that
value and completed normally.

**1.1.13 does not name the model that answered.** Its `init` object no longer carries the 1.1.8
`model` field — read off a fresh scratch turn whose `init` keys are exactly `cwd`,
`expanded_commands`, `permission_mode` and `tools`. The adapter can still pass an explicitly
selected slug, but that is not proof of backend routing, so its `model` capability is false and it
emits `model_name` on **neither** version. The 1.1.8 `init.model` is the slug that release was
configured with, and reporting it filled rundesk's *model that answered* column with the one thing
the capability had already said there was no evidence for.

**There is no `auth`, `login` or `logout` subcommand.** The subcommands are `agent`/`agents`,
`changelog`, `help`, `install`, `models`, `plugin`/`plugins`, `update`. That is why the adapter
declares no `account_aliases` and offers no account commands: the seam already refuses those verbs
for an adapter that does not declare the capability, with a message naming the adapter.

## What 1.1.13 offers as tools

One fresh turn — the adapter run directly, under `--mode plan`, standing in an empty scratch
directory outside any install — listed 56 names in `init.tools`. Twenty-five of them this adapter
has a word for; the names are all that is recorded here, and what each tool takes and answers with
is the vendor's.

- newly said in rundesk's words: `find_by_name` → `search`, `list_browser_pages` and
  `list_permissions` → `list`, `notebook_execution` and `execute_browser_javascript` → `run`
- already mapped and still offered: `view_file`, `sed_file`, `read_resource`, `read_url_content`,
  `read_browser_page`, `list_dir`, `list_resources`, `grep_search`, `search_web`, `run_command`,
  `command_status`, `send_command_input`, `replace_file_content`, `multi_replace_file_content`,
  `write_to_file`, `notebook_edit`, `generate_image`, `define_subagent`, `invoke_subagent`,
  `browser_subagent`
- mapped and **not** in the 1.1.13 listing: `code_search`. Kept. A name missing from one release's
  listing is not evidence the older stream stopped naming it, and removing it would silently stop
  reporting a search that happened.
- the remaining names are left wordless deliberately. `did` is ten closed words, and a browser
  keypress, a permission request, an inbox or a scheduled thing is not one of them — a reader shown
  nothing is better off than one taught a word that means something else here.

## Decisions the restoration made, and why

**`--sandbox` is not passed.** It is the vendor's OS containment. Its effect on a turn that must run
this install's own `rundesk` command and write the files the agent lives by is unprobed at 1.1.13,
and passing it would imply a boundary rundesk does not enforce and could not honour. The other three
shipped adapters run with the whole machine available; this one does too, and `docs/providers.md`
says so.

**`--dangerously-skip-permissions` is passed, on both access modes.** Print mode has no channel an
approval could be asked or given through, so withholding it does not make a turn safer — it makes it
the soft denial that exits zero claiming success, which is the defect the adapter then has to correct
after the fact. This is the explicit decision the flag's name asks for.

**`RUNDESK_ACCESS_MODE` is mapped rather than ignored.** `read` becomes `--mode plan` and `work`
becomes `--mode accept-edits`. A request in the brain's own vocabulary, and not containment: `plan`
is a workflow.

**The adapter presents no skills.** `.agents/skills` is one of the four roots rundesk itself links
into an agent's home, so an adapter doing it again during a turn would race the thing that owns it,
and its pruning would take links rundesk had just made. The 1.1.8 build did this because rundesk did
not yet. A case proves the adapter leaves both a rundesk link and a hand-placed directory alone.

**The version probe is started the way a turn is.** `--capabilities` runs `agy --version`, and that
is the one place an answer meant to be offline, quick and the same every time starts the vendor. It
is now handed `the_environment()` — the adapter's own environment, plus the account name the keyring
lookup needs and `AGY_CLI_DISABLE_AUTO_UPDATE=true`. Without the last of those a brain asked its
version may fetch a release, and it would land in the middle of the turn admitted moments later.
Nothing wider than the adapter's own environment is handed over.

**One terminal record, and the first one wins.** Rundesk reads the *last* `done` in a turn, so a
brain that ended a turn and then went on talking could take back a status, a failure message, a
session handle and a bill the owner already had. Nothing crosses the seam after the adapter has
ended a turn; the trailing lines are still written to `RUNDESK_RAW` and one bounded line says on
stderr that they arrived. No `agy` release has been seen to do this — it is written down because the
failure is silent and would be read as the truth.

**A line too long to hold says so.** A vendor line over a megabyte is read to its end and discarded
whole, because half a record is not a smaller record. That loss is invisible to rundesk's own drift
counters — nothing ever reaches the seam to be counted — and it is not written to `RUNDESK_RAW`
either, since keeping the megabyte is the bound in another place. So the adapter writes one bounded
line to the conversation's own `stderr.log` naming the bound and which gap of the turn it was. The
next valid record is read normally. The seam's eight record kinds have no loss kind and none was
invented.

**Nothing is renamed in the environment.** The 1.1.8 build read a `RUNDESK_ANTIGRAVITY_BIN` of its
own invention and a `RUNDESK_POSTURE` that no longer exists. A `RUNDESK_` name is one rundesk decides
and an owner's value may never take, so the restored adapter finds `agy` by name on `PATH` like every
other shipped adapter, and reads only the names `docs/providers.md` documents. A case walks the file
and fails on any other.

## Still unproven

- A `--print-timeout 48h0m0s` turn running past the vendor's five-minute default. The value parses
  and short turns complete, but the long duration itself was not exercised.
- Whether a write tool other than the measured `write_to_file` uses a path spelling besides the
  documented `TargetFile`. Historical `AbsolutePath` remains understood; an unseen spelling makes an
  edit to a file the agent lives by report as a plain `edit`, which is the safe direction.
- Whether `generate_image` produces a file worth reporting to a channel, and under which key. Until
  that is known the adapter emits no `file` records at all.
- Whether any terminal `status` other than `SUCCESS` exists and whether one classifies a failure.
  Until then the adapter writes a `failure_code` only where *it* is what went wrong.
- Whether this brain ever really says anything after its own terminal line, or ever writes a line
  over a megabyte. Neither has been seen; both are held to constructed streams in the scratch root,
  which is where a stream nobody captured belongs.
- What the other 31 tools 1.1.13 lists actually do. They are named in the stream and reported with
  no `did`, which is the safe direction.
