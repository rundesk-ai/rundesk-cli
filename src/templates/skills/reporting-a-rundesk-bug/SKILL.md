---
name: reporting-a-rundesk-bug
description: How to report a defect in rundesk itself to its GitHub issue tracker, including what counts as one, what evidence to gather, and what must never be pasted into a public issue. Use whenever a rundesk command behaves wrongly, crashes, reports something untrue, or does not do what its own help says — and whenever anyone says rundesk is broken, even if nobody asks for an issue to be filed.
---

# Reporting a bug in rundesk

*This skill ships with rundesk and is replaced whenever rundesk updates. To make a version of
your own, copy it under a different name — that copy is yours and is never touched.*

Rundesk is the thing running you, so you are better placed than anyone to notice when it
misbehaves. Issues go to **`rundesk-ai/rundesk-cli`**, which is a **public** repository.

## First, decide it is actually a rundesk bug

Most things that look like one are not. Check these before going further, because a wrong
report costs a maintainer more than a missing one:

- **Is it your own mistake?** A command you typed wrongly, a flag that does not exist, an agent
  name you got wrong. `rundesk <verb> --help` is generated from the command and cannot be stale.
- **Is it configuration?** Not signed in to a brain, no provider set, a missing credential.
  `rundesk doctor <agent>` names those, and none of them is a defect.
- **Is it already fixed?** `rundesk version` then `rundesk update --check`. A bug on an old
  version is often a bug somebody already reported.
- **Can you make it happen again?** One-off failures under load are worth mentioning to your
  owner; they are rarely worth an issue until they repeat.

A defect is: rundesk did something **untrue** (reported success it did not earn, said a thing
was there when it was not), **crashed**, **lost something**, or **disagreed with its own
documented behaviour**.

## Then check nobody has reported it

```sh
gh issue list --repo rundesk-ai/rundesk-cli --search "<a distinctive phrase from the error>" --state all
```

If one exists, **add a comment rather than a second issue** — say what your reproduction adds
that the original does not. Duplicate issues are the fastest way to make a tracker useless.

## Gather the evidence

```sh
rundesk version                    # which version this is
rundesk doctor <agent>             # what rundesk itself says is wrong
```

Then the reproduction: the exact command typed, what you expected, what happened instead.
Trim the output to the part that shows the failure.

## Never put these in a public issue

This is the part with real consequences, and it is on you rather than on any tool:

- **Anything anybody said to you.** Run transcripts, `rundesk messages` output, conversation
  content, channel history. That is your owner's private correspondence and it is not yours to
  publish. Describe the shape of the input, never the input.
- **Credentials of any kind** — tokens, keys, `auth.json`, anything from a provider's home.
- **Whole log files.** `rundesk logs` carries whatever the brain printed, which includes both
  of the above. Quote the handful of lines that show the failure and nothing else.
- **Absolute paths under a home directory**, which carry the owner's username. Write
  `<agent home>/skills` rather than the real path.
- **Your owner's name, email, or the names of people in their channels.**

When in doubt, leave it out and say what you left out. A maintainer can ask; an owner cannot
unpublish.

## File it

```sh
gh issue create --repo rundesk-ai/rundesk-cli \
  --title "<type>: <what is wrong, in one line>" \
  --body "<the body below>"
```

Title reads like a commit subject — `doctor: reports READY for an agent with no provider`, not
`bug` or `it broke`.

```md
## What happened
<One or two lines. What rundesk did that it should not have.>

## Reproduce
```sh
<the exact commands, in order>
```

**Expected:** <what should have happened>
**Actual:** <what happened, trimmed to the failure>

## Environment
- rundesk `<rundesk version>`
- <operating system and version>
- brain: `<which provider, and its version if relevant>`

## What `doctor` says
```
<rundesk doctor output, with any home paths redacted>
```
```

Add `--label bug` only if that label exists; a label that does not is an error, not a note.

## Gotchas

**A crash is a stack trace, and a stack trace is evidence — but read it first.** It names the
file and line, and often shows the bug is in a skill, a channel adapter, or a brain rather than
in rundesk. Report it where it lives.

**`rundesk doctor` output is the single most useful thing you can include**, and it is designed
to be safe to share — except that it prints paths. Redact the home portion.

**Say that you filed it.** Give your owner the issue URL in your reply. An agent that files
something on their behalf and does not mention it has done something surprising to them.

**If `gh` is not installed or not signed in, stop and tell your owner** with the body you would
have filed, so they can paste it. Do not try to reach GitHub another way.

**One issue per defect.** If you found three, file three — a single issue listing three bugs
gets closed when one of them is fixed.
