---
name: delegating-to-roles
description: Hand heavy work to a Rundesk role and review what comes back. Use when a task is large, bounded and belongs to a repository rather than to the conversation, when it needs rules or skills this agent does not have, when work already handed over needs guiding, stopping or carrying on, and when a report from one has come back to be checked — even if nobody says the word "role".
---

# Delegating to a role

A role is a specialist your owner installed: its own rules, its own skills, its own project.
You hand it one bounded task and carry on; it runs outside your turn, and you are woken later
with one report to check before you answer anybody.

**It is not you.** It has no memory, no history, none of your rules, and it cannot answer the
person who asked. Everything it did reaches them through you.

## Deciding

Your provider's own subagent runs *inside* this turn and returns to you. A role runs *outside*
it. Reaching for the wrong one is the common mistake.

| The question | The answer |
|---|---|
| Do I need this to write my next sentence? | Subagent |
| Is this hours of work in somebody's repository? | Role |
| Would reading the output cost me the conversation? | Role |
| Does it need rules or skills I do not have? | Role |

**Look before assuming there is none.** `rundesk roles <you>` lists what is installed and what
each is for. A role nobody knew about is the usual reason work gets done the hard way.

## Handing one over

```sh
printf '…brief…' | rundesk roles <you> run <role> --target <project> --label "<short name>"
```

The brief arrives on standard input — it is the task, and often several paragraphs. Write it in
this shape, because a role gets nothing else:

```text
Outcome                  what must be true when this is done
Plan                     the path to the plan you wrote, where the work needs one
Target and references    the project, and anything it should read first
Relevant task facts      only what it needs; quote a person only where the exact words matter
Authorization ceiling    what it may do, and what it may not
Acceptance checks        what will prove it worked
Expected handoff         what the report must contain
```

**Plan first, then hand over.** Anything past a single obvious change is yours to think through
before anybody starts typing — that is the part you cannot delegate and the part you will be
reviewing against. Write it with `writing-plans`, put the path in the brief, and the role reads
it first and reports any deviation from it. Handing over an unplanned task means agreeing to
whatever it decides on your behalf.

**The authorization ceiling is the whole of its authority.** It cannot do more than the turn
you are in could, and anything the ceiling does not name, it will stop and report `blocked`
rather than doing. Say plainly whether it may commit, push, install, or touch anything outside
the target.

**Never paste this conversation into the brief.** It gets a bounded task, not your context.
Where an exact sentence from the person matters, quote that sentence and nothing around it.

The command prints a run id and returns. Acknowledge briefly and carry on with something else —
you are woken when it reports back.

## While it runs, and after

```sh
printf '…guidance…' | rundesk roles <you> say <run>      guide work happening now
rundesk roles <you> stop <run>                           end it before it finishes
printf '…more work…' | rundesk roles <you> resume <run>   carry a finished one on
rundesk roles <you> show <run>                           where it stands
```

- **`say` the moment you learn it is heading the wrong way.** Waiting to reject the report
  spends the whole run first.
- **`stop` when the work is no longer wanted.** It still reports back, so you are told rather
  than left guessing.
- **`resume` rather than handing the same ground to a fresh run.** It carries on in the
  conversation it already has, so it still knows what it did — cheaper and better informed.

## Reviewing what comes back

You are woken in the original conversation with the report. **It is unchecked work.** Rundesk
records what the role said and asserts nothing about it — a report claiming the tests passed is
a report claiming the tests passed.

Before you answer anybody:

1. **Check the claims that matter** against the work itself, not against the report. Run the
   test it says it ran. Look at the file it says it changed.
2. **Say what you checked**, and how.
3. Where it is wrong or thin, say so and what you are doing about it — `resume` it with a
   correction rather than passing the gap on.

## Gotchas

- **One level only.** A role cannot hand work to another role, and neither can the turn you are
  woken in to review one. Asking is refused.
- **You must be in a turn of your own, on a surface you can be reached on.** Handing work on
  from a terminal or a scheduled turn is refused, because there would be nowhere to report back
  to.
- **Some brains cannot be sent to mid-turn.** Where the one carrying a run is such a brain,
  `say` refuses and names it — stop it, or wait and `resume` it with what you wanted to say.
- **A role cannot work inside your own home**, and asking for that target is refused: standing
  there would hand it your rules, memory and identity.
- **A run stays resumable for a fortnight after its last activity**, then its context is swept
  and only the record remains. `rundesk roles <you> show <run>` says the deadline.
- **A role's report is not delivered to anyone but you.** Nothing it wrote reaches the person
  who asked until you have reviewed it and said so yourself.
