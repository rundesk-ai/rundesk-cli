+++
title = "Authorization"
subtitle = "the list of who may reach an agent, and the channel that carries its notices"
status = "draft"
intent = """
Authorization exists so that the owner decides which people on a platform may reach an agent, and so that
a stranger who finds the bot gets nothing. The decision belongs to Rundesk CLI rather than to the adapter,
and an agent whose list is empty should admit no sender at all.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Commands", value = "rundesk channels add --allow, configure --allow, --deny", cite = "commands" },
  { label = "Entry forms", value = "a bare sender, sender:<id>, place:<id>", cite = "entries" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "An unnamed sender", value = "never admitted", cite = "admits" },
  { label = "A place entry alone", value = "admits no sender until one is named", cite = "admits" },
  { label = "Notified channels", value = "at most one an agent", cite = "notified" },
  { label = "The decision", value = "never moves to the adapter", cite = "admits" },
]
+++

Whether a person may be answered is Rundesk CLI's decision.[^admits] An adapter narrows who it listens to
only to avoid working for nothing, and the answer is decided again here.[^admits] What a person can type
once admitted is described on [gestures](gestures.md).

## Entries

Each [channel](../channels.md) holds a list of who may reach it, and an entry takes one of three
forms.[^entries]

| Entry | Admits |
|---|---|
| `alice#1234` | that one sender, named bare[^entries] |
| `sender:<id>` | that one sender, named explicitly[^entries] |
| `place:<id>` | the people the platform reports in that room[^entries] |

`rundesk channels add` requires at least one entry, and `configure` adds and removes them one at a time
rather than replacing the list.[^commands]

## Refusals

A sender the platform does not name is never admitted.[^admits] A place entry admits the people in that
room **only when the platform also names the sender**, so a room whose members arrive unnamed admits
no sender.[^admits]

## Notices

One channel an agent holds carries its notices, and no agent can end up with two.[^notified]

[^commands]: `src/rundesk/commands/channels.py` — `register()` declares `--allow` on `add` and `--allow`
    and `--deny` on `configure`, and `cmd_channels()` refuses an `add` naming none.
[^entries]: `src/rundesk/channels/kept.py` — `SENDER`, `PLACE`, `TYPED` and `AS` give the three forms, and
    `allowing()` adds and removes entries inside one transaction rather than writing the list whole.
[^admits]: `src/rundesk/channels/kept.py` — `Admitting.admits()` refuses an unnamed sender and admits a
    place only alongside one, `admitting()` and `admitted_by()` build it, and the module docstring states
    the decision never moves to the adapter.
[^notified]: `src/rundesk/channels/kept.py` — `telling()` moves the notified channel, which a partial
    unique index holds to one an agent.
