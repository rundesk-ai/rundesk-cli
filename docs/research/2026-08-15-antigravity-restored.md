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
`model` field. The adapter can still pass an explicitly selected slug, but that is not proof of
backend routing, so its `model` capability is false and current turns omit `model_name`.

**There is no `auth`, `login` or `logout` subcommand.** The subcommands are `agent`/`agents`,
`changelog`, `help`, `install`, `models`, `plugin`/`plugins`, `update`. That is why the adapter
declares no `account_aliases` and offers no account commands: the seam already refuses those verbs
for an adapter that does not declare the capability, with a message naming the adapter.

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
