# Building a provider adapter

Rundesk does not run a conversation. It runs **your program**, gives it somewhere to work,
reads what you report, and ends it. That program is an adapter.

It is a program and not a plugin on purpose: rundesk never loads your code, and you are not
obliged to write Python. **An adapter can be a shell script.**

**Read [`references/the-contract.md`](./references/the-contract.md) before writing the
code.** It is the whole contract and is authoritative where this page disagrees: every
record, every field, what is required and what is optional, and a working adapter in
twenty lines. This page is what you need to *start* and to avoid the expensive
mistakes — it is deliberately not the reference.

## Your adapter answers two questions

### One: what can you do?

Run with `--capabilities`, print one JSON object, exit `0`:

```json
{"tools": true, "resume": true, "usage": true, "model": false, "steer": false}
```

Every field is `false` when left out, so `{}` is a valid answer and a complete adapter. This
must need no account, no network and no login, and must be the same answer every time.

Only `steer` changes how a turn is *run*. The rest are claims about what to expect, recorded
with the run so a brain that reported nothing and a brain that has nothing can be told apart.

### Two: carry one turn

You are told everything through the environment:

| | |
|---|---|
| `RUNDESK_CWD` | the agent's own home — **stand here**, so what your brain loads is what the agent keeps |
| `RUNDESK_SKILLS` | the skills this agent was given; link them where your brain looks |
| `RUNDESK_CONTINUITY` | `NAME=verb,…` — the files the agent lives by, and what changing one is called |
| `RUNDESK_PROVIDER_HOME` | yours alone, and it lasts — for what you must remember between turns |
| `RUNDESK_RUN` | this run's id |
| `RUNDESK_POSTURE` | `read` or `work` — how much of the machine this turn may touch |
| `RUNDESK_MODEL` · `RUNDESK_RESUME` · `RUNDESK_SETTINGS` · `RUNDESK_PREFACE` · `RUNDESK_RAW` | absent rather than empty when there is nothing to say |

**The prompt arrives on stdin**, never as an argument — anything on a command line is readable
through the process list. You report on stdout, one JSON object per line, flushed as it happens:

```json
{"type": "text",   "text": "Looking at the logs now.", "whole": true}
{"type": "think",  "text": "The error is in the parser."}
{"type": "tool",   "id": "1", "name": "Bash", "did": "run"}
{"type": "result", "id": "1", "ok": true, "summary": "3 files changed"}
{"type": "usage",  "input": 1200, "output": 340, "cached": 8000, "model": "…"}
{"type": "file",   "at": "/…/workspace/chart.png", "name": "chart.png"}
{"type": "done",   "ok": true, "session": "019f954d-ad60"}
```

Only `done` is required. **stderr is yours** — say what went wrong there.

## The traps that actually cost something

**`did` is a closed list: `read`, `search`, `run`, `edit`, `list`, `make`, `delegate`, and the
three continuity verbs below.** If what your tool did is none of them, leave `did` out — `name`
still carries your own word. Do not stretch one to fit; say so instead and the list grows by a
release. A channel never sees your vendor's names, which is the whole point.

**An agent editing what it lives by is worth telling apart, and matching the name is the wrong
way to do it.** `RUNDESK_CONTINUITY` hands you `AGENTS.md=rules,MEMORY.md=memory,…`; when a
write lands on one of those *standing directly in `RUNDESK_CWD`*, report that verb instead of
`edit`. Resolve both sides before comparing, and never match on the file's name alone — every
checkout on the machine has an `AGENTS.md`, and reporting one of those as the agent rewriting
its own rules is worse than the plain `edit`, because it is untrue. Ignoring the variable
entirely is a whole adapter; you simply report `edit` as before.

**Never map `RUNDESK_PREFACE` onto anything that replaces the system prompt.** Use the *append*
form your brain offers. Sending an owner's paragraph to a replacing flag does not add a
paragraph — it deletes the brain and leaves the paragraph, and nothing reports it.

**Find out *when* your brain reads standing instructions.** Some take them every run; some bind
them when a conversation is created and silently ignore them after. An argument accepted and
then dropped is worse than one never sent, because it reads like it works.

**Report the turn's own tokens, not the conversation's.** If your brain hands you a running
total, subtract what you reported last time and keep the subtrahend in your own provider home.
Getting this wrong overstates every turn after the first.

**Keep cached tokens apart from fresh ones.** Folding them together reports a number that is
technically real and practically a lie.

**Never guess a vendor's field name.** Read a real item out of a run's raw output before writing
one down. A rundesk adapter once looked for `changes`, `files`, `artifacts` and `outputs` while
the brain emitted `savedPath` — nothing errored, and generated images were simply never
reported for months.

**Both your exit code and your `done` matter, and they mean different things.** `done.ok` is
what your *brain* made of the turn; the exit code is what became of *your program*. Exiting
without any `done` is a turn that never said it finished.

**Never a credential on a command line or in `RUNDESK_SETTINGS`** — settings are written into
the run's record, so a token there outlives the turn.

## Proving it

The same suite every shipped adapter passes:

```sh
python3 tests/test_provider.py --adapter /path/to/your-adapter
python3 tests/test_provider.py --adapter /path/to/your-adapter --home ~/.your-brain
```

Run bare it needs no account and no network. Pointed at yours it really runs your brain.
`--home` is only for a brain that must sign in.

**If your adapter follows the contract and the suite still fails it, the contract is what
moves** — report it rather than working around it.

Then point an agent at it:

```sh
rundesk add ava --provider /opt/my-brain
rundesk ask ava "what changed today?"
```

## Gotchas

**Never let your adapter find itself on its own PATH.** An adapter looks its brain up by name;
one named the same as the brain resolves to *itself*, runs itself, and that copy does the same.
This produced eight thousand processes and a load average of 641 before anyone noticed, because
every generation looks like a legitimate adapter run.

**An adapter that opens a second stream must drain it.** Giving a program `stderr=PIPE` with
nothing reading it deadlocks the program, and it presents half an hour later as a healthy brain
that has simply gone quiet.

**A stand-in that is more generous than the real thing hides whole features.** If you write a
fake brain to test against, give it exactly the surface of the real one — no more.
