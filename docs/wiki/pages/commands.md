+++
title = "Commands"
subtitle = "the twenty-two command groups, their exit codes and the hidden token bridge"
status = "draft"
intent = """
The command reference exists so that a person can find the command for a job, and how to type it, without
reading the code or the help. Every group Rundesk CLI offers should be here, and nothing it does not offer.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Program", value = "rundesk", cite = "parser" },
  { label = "Public groups", value = "22", cite = "parser" },
  { label = "Hidden group", value = "_oauth", cite = "hidden" },
]

[[infobox]]
group = "Exit codes"
rows = [
  { label = "Done", value = "0", cite = "exits" },
  { label = "Failed", value = "1", cite = "exits" },
  { label = "Misused", value = "2", cite = "exits" },
]
+++

`rundesk` takes one command, and each command group answers for one part of an install.[^parser] Typing
`rundesk` with no command prints the help.[^bare] Each group that has a `list` verb also lists when it is
called with no verb, except [permissions](#permissions), which reports instead.[^bare]

## Groups

In the order the help prints them.[^parser]

| Group | Job |
|---|---|
| `status` | the version, where the install is, and every configured value[^status] |
| `version` | the version, and whether a newer release is published[^version] |
| `configure` | the install-wide settings, one flag for each[^configure] |
| `agents` | make an agent, change it, list them, take one away[^agents] |
| `gateways` | start, stop, restart and read the process behind an agent[^gateways] |
| `backups` | copy what Rundesk CLI holds, put a copy back, move where copies live[^backups] |
| `env` | the values an agent needs, typed rather than passed as arguments[^env] |
| `login` | connect a verified account in the browser[^login] |
| `ask` | ask an agent, and watch the answer arrive[^ask] |
| `asked` | the work this agent handed to other agents[^asked] |
| `messages` | what was said in an agent's conversations[^messages] |
| `search` | ask the platforms an agent is connected to[^search] |
| `providers` | the provider commands, account aliases, and one agent's instructions[^providers] |
| `permissions` | what macOS lets this process do[^permissions] |
| `turns` | what one turn did[^turns] |
| `schedules` | recurring and one-time work for an agent[^schedules] |
| `channels` | connect an agent to Discord or Slack, and say who may reach it[^channels] |
| `skills` | catalogs, grants and profiles[^skills] |
| `teams` | install and update a team of agents from a catalog[^teams] |
| `install` | place the program and put `rundesk` on a path[^install] |
| `update` | fetch a newer release and carry the install forward[^update] |
| `uninstall` | take the program away[^uninstall] |

`_oauth` is a twenty-third group the help does not print, because it is a token bridge between processes
rather than something a person types.[^hidden]

## Options

There is no option on the program itself; every option belongs to a group.[^parser] `--json` prints a
machine-readable answer, and exists on `status`, `agents` and `skills` alone.[^json] `--root` exists only
on `uninstall`, where it is the explicit target a confirmed purge must name.[^root]

## Exit codes

Rundesk CLI has three, and no code for a verb it cannot perform.[^exits]

| Code | Condition |
|---|---|
| `0` | it was done[^exits] |
| `1` | it was attempted and did not work[^exits] |
| `2` | the command line itself was wrong[^exits] |

`exits.py` says code `2` is never returned by hand, and five groups return it by hand anyway, for a
command line their own verb found wrong: `gateways`, `schedules`, `search`, `messages` and
`turns`.[^byhand]

[^parser]: `src/rundesk/cli.py` — `build_parser()` builds the `rundesk` parser, registers every group in
    the order above, and declares no option on the program itself; `offered()` leaves out a name
    beginning with an underscore.
[^bare]: `src/rundesk/cli.py` — `_the_verb()` prints the help when no command is given;
    `src/rundesk/commands/agents.py` — `cmd_agents()` treats no verb as `list`;
    `src/rundesk/commands/permissions.py` — `cmd_permissions()` reports instead.
[^status]: `src/rundesk/commands/status.py` — `cmd_status()`.
[^version]: `src/rundesk/commands/version.py` — `cmd_version()`.
[^configure]: `src/rundesk/commands/configure.py` — `register()` generates one flag per settable value.
[^agents]: `src/rundesk/commands/agents.py` — `register()`.
[^gateways]: `src/rundesk/commands/gateways.py` — `register()`.
[^backups]: `src/rundesk/commands/backups.py` — `register()`.
[^env]: `src/rundesk/commands/env.py` — `register()`.
[^login]: `src/rundesk/commands/login.py` — `register()`.
[^ask]: `src/rundesk/commands/ask.py` — `register()`.
[^asked]: `src/rundesk/commands/asked.py` — `register()`.
[^messages]: `src/rundesk/commands/messages.py` — `register()`.
[^search]: `src/rundesk/commands/search.py` — `register()`.
[^providers]: `src/rundesk/commands/providers.py` — `register()`.
[^permissions]: `src/rundesk/commands/permissions.py` — `register()`.
[^turns]: `src/rundesk/commands/turns.py` — `register()`.
[^schedules]: `src/rundesk/commands/schedules.py` — `register()`.
[^channels]: `src/rundesk/commands/channels.py` — `register()`.
[^skills]: `src/rundesk/commands/skills.py` — `register()`.
[^teams]: `src/rundesk/commands/teams.py` — `register()`.
[^install]: `src/rundesk/cli.py` — `_register_install()`.
[^update]: `src/rundesk/cli.py` — `_register_update()`.
[^uninstall]: `src/rundesk/cli.py` — `_register_uninstall()`.
[^hidden]: `src/rundesk/commands/oauth.py` — `register()` gives the group `help=argparse.SUPPRESS`.
[^json]: `src/rundesk/commands/__init__.py` — `print_json()` writes the envelope;
    `src/rundesk/cli.py` — `_register_status()`, and `register()` in `src/rundesk/commands/agents.py`
    and `src/rundesk/commands/skills.py`, are the three that declare `--json`.
[^root]: `src/rundesk/commands/uninstall.py` — `cmd_uninstall()` checks `--root` against the resolved
    install root before a purge.
[^exits]: `src/rundesk/exits.py` — `OK`, `FAILED` and `USAGE`, and the note that a verb Rundesk CLI cannot
    perform is a verb it does not have.
[^byhand]: `src/rundesk/commands/gateways.py`, `src/rundesk/commands/schedules.py` and
    `src/rundesk/commands/search.py` — `_mistyped()` in each returns `USAGE`;
    `src/rundesk/commands/messages.py` — `_mistyped()`; `src/rundesk/commands/turns.py` — `cmd_turns()`
    returns `USAGE` for a limit below 1.
