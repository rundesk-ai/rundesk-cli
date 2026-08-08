# The environment a skill's own commands are handed

Established 2026-08-05, while building the skill system. **Nothing in this release implements this**,
and that is why it is here rather than in `docs/`: no provider process is started yet, so there is no
turn to hand an environment to, and a page above claiming otherwise would be a page nobody could
check.

It is written down now because the shape was decided now — by what a skill is allowed to declare, and
by how profiles are found — and a contract recorded after the code that depends on it is a contract
that was never really agreed.

## What is already true

- A skill may declare what it needs, in `rundesk.json`, as a map of environment variable to why.
- An owner places values with `rundesk env set`, and `core.secrets` seals them on disk.
- A **profile** is a whole set of those values under a suffix: `JIRA_API_TOKEN__ACME`. The set of
  profiles is *found* from what is stored, never declared.
- `rundesk skills doctor` reports which values are missing, per profile, and exits non-zero.

None of that needs a provider. What needs one is getting the values into a program.

## The contract

**Plain environment variables, and nothing else.** No helper module, no socket, no `rundesk env get`.
A skill's script reads `os.environ` — or `$JIRA_API_TOKEN` in a shell — and that is the whole of it.

This works because of where the script runs: a provider CLI is started by rundesk with an environment
rundesk built, and the tool shell that CLI gives its model is a child of that process. So a script the
model invokes inherits everything, with nobody having exported anything.

### Every profile is handed over at once

An agent granted a profiled skill receives the plain names **and** every suffixed name it has. A
script that does not care about accounts reads `JIRA_API_TOKEN`; one that does reads
`JIRA_API_TOKEN__ACME`, and finds out which exist by running `rundesk skills profiles <catalog>/<skill>`
— one row per profile, name in the first column, which works today.

Nothing binds an agent to one profile. That was considered and rejected: an owner asked for an agent
to be able to reach several accounts, and a binding would need a record standing beside the grant,
which is otherwise the sole source of truth.

### What rundesk decides, a value cannot override

`RUNDESK_HOME`, and whatever else rundesk sets for its own purposes, are decided by rundesk. A stored
value whose name collides with one of those is **not** allowed to win. The build this replaces had the
same rule and said so in the same words: a credential store is not a way to reconfigure the product
that reads it.

### What is not handed over

The narrower alternative — hand a skill only the values it declared — was considered and **not**
adopted. A skill with no `rundesk.json` would then receive nothing, which breaks every skill written
before the file existed and every skill an owner wrote by hand in `local`. Worth revisiting once
declaring is the norm rather than the exception; it is a tightening, not a fix.

## Open questions

- **Whether a value placed mid-turn should reach that turn.** It cannot: a process's environment is
  fixed when it starts. The shipped `managing-rundesk` skill says so, and whether anything should
  *notice* and say it more loudly is unanswered.
- **What a skill should do when the same integration needs different treatment per provider.** The
  spec's `compatibility` field is advisory free text every loader ignores.
- **Whether a script should be able to ask rundesk for a value rather than read one.** It would let
  the store stay closed and a fetched credential be re-fetched per use, and it would mean rundesk
  answering a question from inside a turn — which is a much larger surface than an environment
  variable. Nothing needs it yet.

## Sources

- `src/rundesk/skills/needs.py` — what a skill declares, and how profiles are found (this build).
- `src/rundesk/core/secrets.py` — how a value is sealed, and the one function that reads one back.
- [`the-adapter-contracts.md`](the-adapter-contracts.md) — what the previous build handed a provider,
  and the environment it built rather than inherited.
- [`2026-07-27-skills-a-brain-discovers.md`](2026-07-27-skills-a-brain-discovers.md) — measured
  discovery, and why presentation is links rather than injection.
