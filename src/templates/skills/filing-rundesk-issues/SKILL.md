---
name: filing-rundesk-issues
description: How to take something to rundesk's own issue tracker — a defect, a feature it should have, or scoped work on what is already there — including what counts as each, what evidence rundesk itself can give you, and what must never be pasted into a public issue. Use whenever a rundesk command behaves wrongly, crashes, reports something untrue, or does not do what its own help says; whenever anyone says rundesk is broken or should do something it does not; and even if nobody asks for an issue to be filed.
---

# Filing an issue against rundesk

*This skill ships with rundesk and is replaced whenever rundesk updates. To make a version of
your own, copy it under a different name — that copy is yours and is never touched.*

Rundesk is the thing running you, so you are better placed than anyone to notice when it
misbehaves or falls short. Issues go to **`rundesk-ai/rundesk-cli`**, which is a **public**
repository.

**`writing-issues` is how to write one** — duplicate search, the body, evidence, acceptance
criteria, one issue per thing. This skill is only what is true of rundesk in particular, and it
does not repeat any of that.

## First, decide it is rundesk's to fix

Most things that look like a defect are not, and a wrong report costs a maintainer more than a
missing one:

- **Is it your own mistake?** A command typed wrongly, a flag that does not exist, an agent name
  you got wrong. `rundesk <verb> --help` is generated from the command and cannot be stale.
- **Is it configuration?** Not signed in to a brain, no provider set, a missing credential.
  `rundesk doctor <agent>` names those, and none of them is a defect.
- **Is it already fixed?** `rundesk version`, then `rundesk update --check`. A bug on an old
  version is often one somebody already reported.
- **Can you make it happen again?** One-off failures under load are worth mentioning to your
  owner; they are rarely worth an issue until they repeat.
- **Is it rundesk at all?** A stack trace often shows the fault is in a skill, a channel adapter
  or a brain. Report it where it lives.

## Then decide which of the three it is

Set the type on every issue — `--type Bug`, `--type Feature` or `--type Task`. An untyped issue is
an incomplete one, and this repository has all three enabled.

- **Bug** — rundesk did something **untrue** (reported a success it did not earn, said a thing was
  there when it was not), **crashed**, **lost something**, or **disagreed with its own documented
  behaviour**. That last one is the test that matters: `CLI.md` and the `--help` output are what it
  promised.
- **Feature** — rundesk has no way to do this and should. A verb, an option, a surface, a provider
  or a channel adapter it does not ship.
- **Task** — it works as documented and the work is on it: a refactor, revising a skill or a
  document that ships, maintenance already agreed. **Guidance that ships and is merely wrong-shaped
  is a Task**, not a Bug — unless it states something untrue about how rundesk behaves.

Behaviour a `prd/` requirement guarantees is not a defect for disagreeing with what you expected.
If you want it changed, that is a Feature, and the requirement is what it has to argue with.

## The evidence only you can gather

```sh
rundesk version                    # which version this is
rundesk doctor <agent>             # what rundesk itself says is wrong
```

`doctor` is the single most useful thing you can include, and it is designed to be safe to share —
except that it prints paths, so redact the home portion.

**Did you *run* it, or only read it?** Tracing a defect in the source is a **hypothesis**, not a
finding — and it is the most convincing kind of wrong report, because a `file:line` and a traced
mechanism look exactly like proof. Run it first: a probe, a case against the repository's own test
harness, a real reproduction. Where it genuinely cannot be run — it is destructive, it needs a real
outage, it needs hardware you do not have — file it anyway and **say in the body that it was not
executed**, so a reader can weigh it.

## Never put these in a public issue

`writing-issues` has the general rule. These are the rundesk-shaped ways to break it:

- **`rundesk messages` output, run transcripts, channel history.** That is your owner's private
  correspondence and it is not yours to publish. Describe the shape of the input, never the input.
- **Whole log files.** `rundesk logs` carries whatever the brain printed, which includes both
  credentials and conversation. Quote the handful of lines that show the failure and nothing else.
- **Absolute paths under an agent's home**, which carry the owner's username. Write
  `<agent home>/skills` rather than the real path.
- **Your owner's name, email, or the names of people in their channels.**

## File it

```sh
gh issue create --repo rundesk-ai/rundesk-cli \
  --type Bug \
  --label "priority: high" \
  --title "<area>: <what is wrong, in one line>" \
  --body "<the body>"
```

`<area>` is the part of rundesk it belongs to — `doctor:`, `schedules:`, `discord:`, `skills:` —
and it is not the type. Those were the same word before types existed; they are not now.

**The labels this repository has**, none of which classifies:

- `documentation` — what a person reads: the README, the guides, `CLI.md`.
- `skills` — what an agent is taught: anything under `src/templates/skills/`. Not documentation —
  a different audience, and a different blast radius when it is wrong.
- `epic` — work that has to be decomposed before anybody implements it.
- `priority: critical` / `high` / `medium` / `low` — by impact and urgency.

There is deliberately no `bug` or `enhancement` label. The type carries that, and a second copy of
it would drift.

## Gotchas

**A traced mechanism is not an observed failure, and it is the most convincing way to be wrong.**
A `file:line` says where to look; it never says the thing happens. Keep the two apart in the body
— what you read, and what you saw — so a reader can tell which claim rests on which.

**A crash is a stack trace, and a stack trace is evidence — but read it first.** It names the file
and line, and often shows the fault belongs to somebody else's code.

**Say that you filed it.** Give your owner the issue URL in your reply. An agent that files
something on their behalf and does not mention it has done something surprising to them.
