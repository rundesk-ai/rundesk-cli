---
name: delegating-to-roles
description: Hand heavy work to a Rundesk role and review what comes back. Use when a task is large, bounded and belongs to a repository rather than to the conversation, when it needs rules or skills this agent does not have, when work already handed over needs guiding, stopping or carrying on, and when a report from one has come back to be checked — even if nobody says the word "role".
---

# Delegating to a role

A role runs outside your turn, under its own rules and its own skills, in a project you name.
You are woken later with one report. **It is not you** — no memory, no history, none of your
rules — and it cannot answer anybody, so everything it did reaches them through you.

## Which one

| | |
|---|---|
| Need it to write your next sentence | Subagent |
| Hours of work in somebody's repository | Role |
| Reading the output would cost you the conversation | Role |
| Needs rules or skills you do not have | Role |

`rundesk roles <you>` says what is installed. A role nobody knew about is the usual reason work
gets done the hard way.

## Handing one over

**Plan first.** Anything past one obvious change is yours to think through — it is what you will
review against. Write it with `writing-plans` and put its path in the brief.

```sh
printf '…brief…' | rundesk roles <you> run <role> --target <project> --label "<short name>"
```

The brief arrives on standard input and is all the role gets:

```text
Outcome                what must be true when this is done
Plan                   path to the plan, where the work needs one
Target                 the project, and anything to read first
Relevant facts         only what it needs
Authorization ceiling  what it may do, and what it may not
Acceptance checks      what will prove it worked
Expected handoff       what the report must contain
```

**Never paste this conversation in.** Quote one sentence where the exact words matter.

The command prints a run id and returns. Acknowledge briefly and carry on.

## While it runs

```sh
printf '…guidance…' | rundesk roles <you> say <run>       guide work happening now
rundesk roles <you> stop <run>                            end it early — it still reports back
printf '…more work…' | rundesk roles <you> resume <run>   carry a finished one on
rundesk roles <you> show <run>                            where it stands
```

`say` the moment it heads the wrong way; waiting spends the whole run first. `resume` rather
than starting fresh — it keeps its context.

## Reviewing

**The report is unchecked work.** Rundesk records what the role said and asserts nothing about
it. Before answering anybody: check the claims that matter against the work itself, say what you
checked, and `resume` it with a correction rather than passing a gap on.

## Gotchas

- **One level.** Neither a role nor the turn reviewing one may start another. Refused.
- **You must be in your own turn, on a surface you can be reached on** — from a terminal or a
  schedule it is refused, because there would be nowhere to report back to.
- **Some brains cannot be sent to mid-turn.** `say` refuses and names it; stop, or resume.
- **Not your own home** as a target — refused, because standing there hands it your identity.
- **A skill the machine has not got is simply not given.** The listing names it. The role still
  runs, with less than its description implies.
- **Resumable for a fortnight** after its last activity; `show` says the deadline.
