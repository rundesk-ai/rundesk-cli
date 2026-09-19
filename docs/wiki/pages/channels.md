+++
title = "Channels"
subtitle = "the Discord and Slack adapters, who may reach an agent, and the credential each holds"
status = "draft"
intent = """
A channel exists so that a person reaches an agent from the place they already talk in, rather than from a
terminal. Who may be answered should be Rundesk CLI's decision and never the adapter's, and a bot token should
belong to one agent rather than to the install.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Adapters", value = "discord, slack", cite = "known" },
  { label = "Commands", value = "rundesk channels list, add, show, configure, test, remove, doctor", cite = "commands" },
  { label = "Credential name", value = "<ADAPTER TOKEN>__<AGENT>", cite = "credentials" },
]

[[infobox]]
group = "Values"
rows = [
  { label = "Message body limit", value = "64 kB", cite = "arriving" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "A refusal from an adapter", value = "printed as an answer, exit code 0", cite = "answered" },
]
+++

A channel adapter is a separate program that carries a conversation between a platform and an
[agent](agents.md).[^known] Who may reach an agent is described on
[authorization](channels/authorization.md), and what a person can type on
[gestures](channels/gestures.md). Rundesk CLI ships two.[^known] Seven verbs connect one, change it, test it and take it away.[^commands]

## Adapters

| Adapter | Platform gesture | Answers `search` | Uploads a file |
|---|---|---|---|
| `discord` | eleven application commands[^known] | yes[^known] | through `serve`[^known] |
| `slack` | one command named after the agent[^known] | yes[^known] | as a process of its own[^upload] |

## Invocations

An adapter answers five invocations: what it can do, a check of its settings, and `serve` for the owner
and the [gateway](gateways.md), plus `search` and `fetch` for the agent itself.[^known] The Slack adapter
answers a sixth that nothing else says: it runs itself as `upload`, because a file has a deadline and only
a separate process can be held to one.[^upload]

The printed object is the answer and the exit code is not: an adapter saying it is not ready still exits
0.[^answered]

## Bounds

Rundesk CLI puts a ceiling on every invocation it waits for.[^bounds]

| Invocation | Ceiling |
|---|---|
| what it can do | 60 seconds[^bounds] |
| a check of its settings | 5 minutes[^bounds] |
| `search` | 60 seconds[^bounds] |
| `fetch` | 5 minutes[^bounds] |

`serve` has no ceiling: the [gateway](gateways.md) holds it open for as long as the agent is up.[^hosting]

## Credentials

One bot belongs to one agent.[^credentials] The token is held under the adapter's own name joined to the agent's, such
as `DISCORD_BOT_TOKEN__ALAN`, and handed to the adapter under its plain name.[^credentials] A plain
unscoped token is never read, and an agent whose name cannot be part of a variable name holds no
credential.[^credentials]

## Hosting

The gateway starts each adapter, claims the channel's lock, and puts one thread on its output, because the
loop sleeps between beats and a pipe the gateway does not drain blocks the adapter.[^hosting] An adapter this gateway
is not reading is ended, whatever started it.[^hosting]

One exchange is one conversation, and a message body is held to 64 kB.[^arriving]

Messages are split to the platform's limit in one place rather than in each adapter, and a code fence cut
by a split is reopened.[^delivery] A file arriving must stand inside the channel's own directory, be an
ordinary file, and match the byte count declared for it.[^files]

[^known]: `src/rundesk/channels/adapters.py` — `known()` finds `discord` and `slack`, `capabilities()`
    asks one what it can do, `checked()` runs its check, `searched()` and `fetched()` ask it for the
    agent, and `talking_to()` starts `serve`.
[^commands]: `src/rundesk/commands/channels.py` — `register()` declares the seven verbs.
[^upload]: `src/channels/slack` — `main()` matches `upload` alongside the five, and its docstring states
    that a file has a deadline only a process can be held to.
[^answered]: `src/rundesk/channels/adapters.py` — `_answered()` reads the printed object, and the module
    docstring states that a refusal is an answer and exits 0.
[^credentials]: `src/rundesk/channels/credentials.py` — `handed()` reads the value under the adapter's
    declared name joined to the agent's, and refuses an agent name that cannot be part of one.
[^hosting]: `src/rundesk/channels/hosting.py` — `_started()` claims the lock and puts `_listened()` on a
    thread, whose module docstring gives the blocked-pipe reason, and
    `_ended_if_nobody_is_reading()` ends an adapter this gateway does not read.
[^delivery]: `src/rundesk/channels/delivery.py` — `carried()` splits to the platform's limit and reopens
    a cut code fence.
[^bounds]: `src/rundesk/channels/adapters.py` — `CAPABILITIES_WITHIN`, `CHECK_WITHIN`, `SEARCH_WITHIN`
    and `FETCH_WITHIN`.
[^files]: `src/rundesk/channels/files.py` — `landed()` checks the path, the file kind and the declared
    byte count.
[^arriving]: `src/rundesk/channels/arriving.py` — `BODY_AT_MOST` caps a message body, and `recorded()`
    resolves one conversation for one exchange.
