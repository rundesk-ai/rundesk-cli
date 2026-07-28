---
name: example
description: Read and act on Example service data through the local example CLI. Use when a task mentions Example, its records, or data this plugin owns — even if nobody says "example".
---

# Example

A plugin ships its own skills, and this is one. Rundesk links it into the skill library on
install, so it appears in `rundesk skills` beside the built-ins with `example` in its FROM
column. Grant it with `rundesk plugins grant <agent> example`.

The directory name, the `name:` above, and the manifest's `provides.skills` entry must all be
the same word. A brain indexes by one and looks up by another when they differ, and the skill
is then silently absent rather than broken — which is far harder to notice.

## When to use this

- The situations that should reach for the command, in the words a task would actually use.
- Not "when the user says example" — the point is catching the ones where they do not.

## The commands

```sh
example status          # whether it can work, and which credentials are missing by name
example list --limit 20 # recent items, newest first, bounded
```

Bounded by default. Raise `--limit` only when the smaller answer was genuinely not enough.

## Boundaries

- Mutations are dry-run until `--confirm` names the exact action.
- Never paste a token, an authorization header, or raw configuration into a reply.
- `status` exits non-zero when credentials are missing. That is an answer, not a failure to
  work around — say what is missing and stop.

## What does not belong here

Setup, credential paths, implementation detail, and copied `--help` output. This file is for
what an agent could not infer: when to reach for it, which defaults are safe, and the
service-specific traps.
