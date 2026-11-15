+++
title = "Gateways"
subtitle = "the process that keeps an agent answering, how it is started, and what it refuses"
status = "draft"
intent = """
A gateway exists so that an agent answers when no terminal is open, and comes back after a crash, a reboot
or an update. It should never be left restarting in a loop, and a gateway whose state cannot be read
should never be reported as stopped.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Commands", value = "rundesk gateways list, start, stop, restart, logs, run", cite = "commands" },
  { label = "Job name", value = "ai.rundesk.<root>.gateway.<agent>", cite = "label" },
]

[[infobox]]
group = "Values"
rows = [
  { label = "Heartbeat", value = "every 15 seconds", cite = "beat" },
  { label = "Called wedged after", value = "45 seconds", cite = "beat" },
  { label = "Wait before a restart", value = "30 seconds", cite = "plist" },
  { label = "Log lines shown", value = "20", cite = "commands" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "A refusal to start", value = "reported as success, so macOS does not retry", cite = "refusal" },
  { label = "A state that cannot be read", value = "never reported as stopped", cite = "stands" },
]
+++

A gateway is one long-running process for one [agent](agents.md). macOS starts it, restarts it after a
crash and brings it back after a reboot, which is what lets an agent answer a
[channel](channels.md) or run a [schedule](schedules.md) with no terminal open.[^host]

## Job

Each agent's job is named after both the agent and the install it belongs to, so **two installs on one
machine never fight over the same agent's job**.[^label] The thing macOS launches is a small script inside
the agent's own directory, named after the agent, so the owner sees a recognizable row in Login Items
rather than an anonymous `python`.[^shim] It sits with the agent rather than with the program, because an
update replaces the program whole.[^shim]

Placing the job starts the gateway; there is no separate step.[^plist] A gateway that exits unexpectedly is
started again after 30 seconds.[^plist] The agent's search path is written out in full, because macOS
hands a background job almost none of it.[^plist]

## Liveness

A gateway claims its agent's name while it runs, and the claim is the check: whatever can take the claim
knows no gateway holds it.[^beat] It writes a heartbeat every 15 seconds and is called wedged after
45.[^beat]

## Refusals

**A gateway that declines to start reports success**, because macOS reads a failure as a request to try
again and would otherwise spin.[^refusal] Starting refuses an agent whose gateway is already up, and
refuses outright when the state cannot be read.[^start] If a job is placed and no gateway appears, the job
is taken away again, so no crash loop is left behind.[^start]

**A state that cannot be read is never reported as stopped.**[^stands] Two answers from macOS — no
graphical session, and the wrong domain for the request — mean the answer is unknown.[^stands] A gateway
the owner has denied in Login Items cannot be fixed from the command line, and the answer says to open
System Settings.[^stands]

## Reading one

`rundesk gateways logs <agent>` prints the last 20 lines the gateway wrote.[^commands]
`rundesk gateways run <agent>` is the same process in the terminal, with no macOS job behind
it.[^commands]

[^host]: `src/rundesk/gateways/host.py` — `run()` and `_serving()`, which host the channel, schedule and
    delegation work in one loop.
[^commands]: `src/rundesk/commands/gateways.py` — `register()` declares the six verbs and the 20-line
    default `LINES`; `cmd_gateways()` hands `run` to the host.
[^label]: `src/rundesk/gateways/job.py` — `label_for()` and `fingerprint()` build the name from the agent
    and the resolved root, and `_only_ours()` refuses a job belonging to another root.
[^shim]: `src/rundesk/gateways/job.py` — `shim_of()` puts the script in the agent's directory, and
    `_SHIM` records that Login Items names it.
[^plist]: `src/rundesk/gateways/job.py` — `document()` sets `KeepAlive`, `ThrottleInterval` and the full
    search path, and its docstring states that placing the job starts the gateway.
[^beat]: `src/rundesk/gateways/standing.py` — `holding()` makes the claim the check, `write_beat()` writes
    the heartbeat, and `BEAT_SECONDS`, `MISSED_BEATS` and `WEDGED_AFTER` set the figures.
[^refusal]: `src/rundesk/gateways/host.py` — `run()`, whose docstring states every refusal exits
    successfully because a failure asks macOS for a restart.
[^start]: `src/rundesk/commands/gateways.py` — `_started()` refuses a gateway already up and one whose
    state cannot be told, and `_resolved()` takes the job back when no gateway appeared.
[^stands]: `src/rundesk/gateways/job.py` — `stands()` reads four sources and treats `NO_GUI_SESSION` and
    `WRONG_DOMAIN_FOR_THE_VERB` as unknown, and names System Settings for a Login Items denial.
