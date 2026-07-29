---
name: writing-issues
description: How to file an issue that makes the case for work being real before anyone builds it — choosing the right type, gathering evidence, labelling it, and keeping a tracker worth reading. Use whenever opening, drafting, rewriting or reviewing anything on an issue tracker — a bug report, a feature request, a ticket for work already agreed — even when nobody says the words "GitHub issue".
---

# Writing an issue

*This skill ships with rundesk and is replaced whenever rundesk updates. To make a version of
your own, copy it under a different name — that copy is yours and is never touched.*

An issue is **the durable statement that a piece of work is real**. It exists before anybody has
decided how to do it, it outlives every conversation about it, and it is what somebody reads
months later when the person who noticed the problem is gone. A pull request argues for one
change; an issue argues that something needs changing at all.

This is the craft of it, for any tracker. Where the project has a skill of its own naming the
repository, its conventions and what must never be published, that one wins on the particulars.

## First, check nobody already said it

```sh
gh issue list --repo <owner>/<repo> --search "<a distinctive phrase>" --state all
```

Search closed as well as open. A thing that was filed and rejected is an answer; a thing that was
filed and fixed is a version number.

**If one exists, comment on it rather than opening a second.** Say what your evidence adds that
the original does not. Duplicates are the fastest way to make a tracker useless — not because
they waste space, but because the discussion splits and neither half has all of it.

**And if an existing issue is wrong, say so on it.** A report nobody corrected is one somebody
eventually builds against: a wrong root cause sends the fix at the wrong code, and a false claim
in a title outlives every comment under it. Correcting a report — your own or anybody's — is
worth as much as filing a good one.

## Then decide what kind of work it is

Most trackers now carry a **type** as a field of its own, separate from labels. Where they do,
setting it is not optional decoration: it is the classification, and an untyped issue is an
incomplete one.

- **Bug** — it does not do what it says it does. Documented behaviour and actual behaviour
  disagree, or it crashed, or it lost something, or it reported a success it did not earn.
- **Feature** — it does not do this at all, and should. New capability, new surface, new option.
- **Task** — it exists and works, and the work is on it: a refactor, a migration, revising
  content that ships, docs, maintenance somebody has agreed is worth doing.

**The borderline cases are the ones worth thinking about**, and there are three that recur:

- *Deliberate behaviour somebody dislikes* is not a Bug. If the documentation says it works this
  way and it works that way, you are asking for a change — Feature, or Task if the thing already
  exists and is merely wrong-shaped.
- *A missing guard* reads like a Bug and often is not. Nothing broke; something was never built.
- *Shipped content that gives bad guidance* — a template, a document, a prompt — is a Task, not a
  Bug, unless it states something factually untrue about how the software behaves.

**Say why you chose it when the call is genuinely close.** One sentence in the body. The default
failure is reaching for Bug because the issue describes something unwelcome, and it distorts
every count anybody takes off the tracker afterwards.

## Labels are facets, never the classification

Once a type exists, a `bug` or `enhancement` label says the same thing twice and the two drift
apart the first time somebody sets one and not the other. Labels answer the other questions:

- **Area** — where the work lands, so the person who owns that part can find it.
- **Priority** — by impact and urgency. **Never by your confidence or by how much work it is.**
  A small fix to a data-loss bug is not low priority because it is small.

Read the repository's actual label set before filing — `gh label list --repo <owner>/<repo>` —
and use what is there. A label that does not exist is an error, not a note, and inventing one
because it seemed useful leaves a taxonomy nobody agreed to.

## Write the body

Lead with what is true, then what you think, then what you propose — in that order and visibly
separated. A reader has to be able to tell which of your claims rests on what.

**Bug:**

```md
## What happens
<One or two lines. What it did that it should not have.>

## Reproduce
<the exact commands or steps, in order>

**Expected:** <what should have happened>
**Actual:** <what happened, trimmed to the failure>

## Evidence
<version, environment, the handful of output lines that show it>

## Where it comes from
<Only if you proved it. A traced mechanism is a hypothesis — say which it is.>
```

**Feature:**

```md
## What is missing
<The need, from the point of view of whoever has it. Not the implementation.>

## Why it matters
<What is impossible or expensive today. Concrete, ideally with an instance of it.>

## Proposed scope
<What would be built. Bounded.>

## Non-goals
<What this deliberately does not cover, so it cannot quietly grow.>
```

**Task:**

```md
## How it is now
<The current state, named precisely — file, command, behaviour.>

## What should change
<And why this is work rather than a defect.>

## Scope
<What is touched and what is not.>
```

Every one of them ends with **acceptance criteria that can be checked** — a condition somebody
can test, not "works properly". If you cannot write one, the issue is not yet understood well
enough to file.

## Never publish these

A public tracker is published, indexed and cached. Deleting a comment does not unpublish it.

- **Anything anybody said to you** — conversation content, transcripts, message history. Describe
  the shape of the input; never the input.
- **Credentials of any kind**, and whole log files, which carry them.
- **Absolute paths under a home directory**, which carry a username.
- **The names, emails or handles of real people.**
- **Anything naming what wrote the issue** — no tool or model branding, in the body or a trailer.

When in doubt, leave it out and say what you left out. A maintainer can ask; you cannot unpublish.

## Gotchas

**One issue per thing.** Three problems in one issue gets closed when the first is fixed, and the
other two are lost inside a thread nobody reopens.

**A title reads like a commit subject** — `doctor: reports READY for an agent with no provider`,
not `bug` and not `it broke`. Somebody scanning fifty of these should need only the title.

**Proposing the implementation is how an issue goes stale.** State the problem so precisely that
several solutions are visible; the one you had in mind belongs in a comment, where being wrong
about it costs nothing.

**Say that you filed it**, and give the URL to whoever raised it. Filing something on somebody's
behalf without telling them is a surprise, not a service.

**If `gh` is missing or not signed in, stop and hand over the body you would have filed** so a
person can paste it. Do not reach the tracker another way.

**Link the work back.** When a change fixes an issue, its pull request carries `Closes #<n>` —
one keyword per issue, and the issue closes itself on merge. A bare `#<n>` links and closes
nothing, and a fix that ships with its issue still open reads to everybody as work never done.
`writing-pull-requests` covers the rest of that side.
