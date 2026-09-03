"""What this machine lets rundesk do, asked by doing it.

**This is not about a brain's tool permissions.** Every provider adapter already runs its CLI with
that system switched off — `--dangerously-skip-permissions`, `danger-full-access`,
`bypassPermissions` — and `docs/extending/providers.md` says so outright. What actually stops an agent taking
a screenshot, clicking a button or driving a browser is **macOS TCC**, and that is what this package
asks about.

| Module | Answers |
|---|---|
| `lineage` | whose grants an answer here would be a fact about, and how that was decided |
| `proving` | the one program each capability is settled by, what its answer means, and the one thing to type when it is a no |

May depend on `core` and `utils`. **It may not reach `agents`**, and that restriction is the
mechanical statement of the thing this package exists to say: *a grant belongs to a machine, not to
an install's agents.* Two gateway shims differing only in the agent they name were measured to be
one TCC client, so a module that had to be told which agent was asking would be a module answering a
question nobody can ask.

## Why this is its own package and not part of `skills.doctor`

`skills/doctor.py` opens with *"Nothing here reads a value and nothing here runs a program"*, and
gives the reason: a diagnosis that had to start somebody's program to find out is a diagnosis nobody
could run on a machine they were worried about.

**Everything here runs a program**, because there is no other way to find out. That is the opposite
paragraph, and two opposite rules do not belong in one package. What is borrowed is the shape — one
verdict per thing there is to do about it, a `fix` that is the exact line to type, and the answers
asked in an order that decides which of several true things gets said.

## The two rules that are not negotiable

**Nothing may prompt.** A consent dialog raised by a background gateway is a dialog on somebody's
desktop with no context, and the wrong button on it writes a **denial** that persists. Every query
here is a preflight or a read. Where no non-prompting query exists, the answer is `UNPROVEN` and the
probe is not shipped — an honest silence beats a guess that costs the owner a grant.

**Every answer says whose grants it is about.** Measured: the same probe run from a terminal and from
a launchd job gives opposite answers, because macOS makes the nearest application bundle the
responsible process and a terminal lends its own grants to everything started from it. A proof that
did not carry its lineage would be a claim about nobody, and the specific damage is a check run at a
terminal reporting `READY` for a gateway that cannot capture the screen.

Both are established in `docs/research/2026-08-08-what-this-mac-lets-a-process-do.md`, which is where
the measurements and the eleven questions still open are kept.
"""
