+++
title = "Secrets"
subtitle = "the values an agent needs, how one is entered, and where they are sealed"
status = "draft"
intent = """
Secrets exist so that an agent can hold an API key or a token without the owner pasting it into a file, a
command line or a shell history. A value should never be printed back whole, and one agent's credential
should never be reachable as another's.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Commands", value = "rundesk env list, check, set, unset", cite = "commands" },
  { label = "Name form", value = "capitals, digits and underscores", cite = "named" },
  { label = "Location", value = "data/secrets, readable only by its owner", cite = "sealed" },
]

[[infobox]]
group = "Values"
rows = [
  { label = "Longest value", value = "4096 characters", cite = "typed" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "A value as a command argument", value = "not possible", cite = "typed" },
  { label = "A value printed back", value = "never whole, only a hint", cite = "hint" },
  { label = "Rundesk CLI's own stored document", value = "hidden, and refused to every verb", cite = "ours" },
]
+++

A secret is a value an [agent](agents.md) needs and the owner should not have to retype: an API key, a bot
token. Four verbs list them, check one, set one and empty one.[^commands] How a [channel](channels.md)
credential is scoped to a single agent is described there.

## Entering one

**There is no way to pass a value as an argument.**[^typed] `rundesk env set <key>` takes the name only and then
reads the value itself, so a secret never reaches a shell history, a process list or a log.[^typed] A
value is read without echo at a terminal, and runs to 4096 characters.[^typed]

A name is capitals, digits and underscores, which is what a program reads it as.[^named]

## Reading one back

**Nothing ever prints a whole value.**[^hint] `rundesk env list` shows each name with a hint of its value, and
`rundesk env check <key>` answers whether one is set without revealing it.[^hint]

Rundesk CLI's own stored document is hidden from the list and refused to `set`, `unset` and `check`, so
the owner cannot overwrite it by accident.[^ours]

## Storage

Values are sealed under a key beside them, in a directory only their owner can read.[^sealed] The key
lives on the same disk, which is weaker than a system keychain, and is the deliberate trade: a gateway
starting at boot cannot reach a key that needs a person present.[^why]

A value may be scoped to one profile, so two agents can hold the same named credential without either
reaching the other's.[^profile]

[^commands]: `src/rundesk/commands/env.py` — `register()` declares `list`, `check`, `set` and `unset`, and
    the module docstring states no verb takes a value.
[^typed]: `src/rundesk/commands/env.py` — `typed()` reads the value without echo at a terminal and from
    standard input otherwise, `MOST` caps its length, and the module docstring states there is no
    `env set KEY value` form.
[^named]: `src/rundesk/core/secrets.py` — `NAMED` accepts capitals, digits and underscores.
[^hint]: `src/rundesk/core/secrets.py` — `hinted()` renders a value as a hint, and the module docstring in
    `src/rundesk/commands/env.py` states nothing prints a whole value.
[^ours]: `src/rundesk/core/secrets.py` — `ours()`, which `src/rundesk/commands/env.py` uses to hide the
    document from `list` and refuse it to the other three verbs.
[^sealed]: `src/rundesk/core/paths.py` — `secrets()`; `src/rundesk/core/secrets.py` — `KEPT_IN` and
    `KEY_IN` name the two files, `ONLY_MINE` sets the directory mode, and `SEALED` names the sealed form.
[^why]: `src/rundesk/core/secrets.py` — the module docstring states the key is held beside the values
    because a gateway has to start at boot, names a system keychain as stronger, and says why the value or
    the key would have to stop living on this disk.
[^profile]: `src/rundesk/core/secrets.py` — `PROFILED_BY` separates a profile from a name.
