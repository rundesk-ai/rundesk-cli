+++
title = "Gestures"
subtitle = "the eleven commands a person types on a platform, and the words behind them"
status = "draft"
intent = """
Gestures exist so that a person can steer an agent from the room they are already in, without a terminal.
The same words should mean the same thing on every platform, and a gesture a person is not allowed to make
should be decided by Rundesk CLI rather than by the platform.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Controls", value = "stop, new, restart, shutdown", cite = "controls" },
  { label = "Questions", value = "status, version, agents, skills, schedules, delegations", cite = "queries" },
  { label = "Setting", value = "provider", cite = "configure" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "Discord", value = "eleven application commands", cite = "discord" },
  { label = "Slack", value = "one command named after the agent", cite = "slack" },
  { label = "A Slack answer", value = "ephemeral, to whoever typed it", cite = "slack" },
]
+++

A gesture is a command a person types on a platform to steer an agent, rather than a message for the agent
to answer.[^controls] Who may make one is described on [authorization](authorization.md).

## Vocabulary

Rundesk CLI owns eleven words behind every platform, so the same gesture means the same thing on each
one.[^controls]

| Kind | Words |
|---|---|
| Controls | `stop`, `forget`, `restart`, `shutdown`[^controls] |
| Questions | `status`, `version`, `agents`, `skills`, `schedules`, `delegations`[^queries] |
| Setting | `provider`[^configure] |

## Discord

Discord registers each of the eleven as its own application command.[^discord] The command a person types
for a fresh session is `new`, which is Rundesk CLI's `forget`.[^discord]

## Slack

Slack offers one command named after the agent, with the same words as its subcommands, because a slash
command must be unique across a workspace.[^slack] Every answer goes back through Slack's own response
address as an ephemeral reply, so a command typed in a room is answered to whoever typed it and never into
the room.[^slack]

[^controls]: `src/rundesk/channels/hosting.py` — `CONTROLS` names `stop`, `forget`, `restart` and
    `shutdown`.
[^queries]: `src/rundesk/channels/hosting.py` — `QUERIES` names the six questions.
[^configure]: `src/channels/discord` — `CONFIGURE`; `src/channels/slack` — `CONFIGURE`.
[^discord]: `src/channels/discord` — `CONTROLS`, `QUERIES` and `CONFIGURE`, registered as application
    commands in its client setup; `CONTROLS` maps the typed `new` to `forget`.
[^slack]: `src/channels/slack` — the module docstring states the command is named after the agent because
    a slash command is unique across a workspace, and that every answer goes back through the response
    address as an ephemeral reply.
