+++
title = "Schedules"
subtitle = "recurring and one-time work, the local clock it reads, and running a due moment once"
status = "draft"
intent = """
A schedule exists so that an agent starts work without being asked, at a time written in local time. A due moment should run exactly once, and a moment the machine slept through should not run
late.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Commands", value = "rundesk schedules list, add, update, show, run, remove", cite = "commands" },
  { label = "Moment format", value = "YYYY-MM-DDTHH:MM", cite = "shape" },
]

[[infobox]]
group = "Values"
rows = [
  { label = "Cron fields", value = "5", cite = "shape" },
  { label = "Outcomes", value = "done, failed, stopped", cite = "outcomes" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "Times written by the owner", value = "read in local time", cite = "clock" },
  { label = "A moment the machine slept through", value = "skipped, never run late", cite = "due" },
  { label = "A run still going", value = "not started a second time", cite = "claim" },
]
+++

A schedule starts work for one [agent](agents.md) with no person at the keyboard.[^commands] Each one either
repeats on a cron line or fires at a single moment, and either runs a program or puts a question to the
agent; a schedule that says both, or neither, is refused.[^shape]

## Clock

**Times written into a schedule are local**: the cron line, the one-time moment and the expiry.[^clock] Times
Rundesk CLI records are UTC, so a run's history reads the same in every time zone.[^clock]
A repeating schedule stops only when its expiry passes.[^shape]

## Due work

**A moment is due in its own minute and no other.**[^due] A machine asleep at that minute does not fire
the schedule an hour later when it wakes; the moment has passed.[^due]

The check against the last minute fired asks whether this minute is *later*, never whether it is
*different*, because a wall clock goes backward in autumn and after a correction, and "different" would
run the same work twice.[^due] Looking ahead runs past nine years, so the twenty-ninth of February is
still found.[^due]

## Running once

The minute is written down before the work starts rather than after, so a crash mid-run cannot let the
same moment fire again.[^claim] The [gateway](gateways.md) also takes a claim on the schedule itself, so a
run that is still going is passed over instead of started twice.[^claim]

The set of minutes already fired is read back from the records on every pass rather than remembered, so a
gateway that restarted does not repeat a morning's work.[^fired]

**Nothing a schedule does can bring the gateway down.**[^fired] A schedule whose settings cannot be read is
reported and passed over, and every firing runs inside a guard.[^fired]

## Outcomes

A run ends as done, failed or stopped, where stopped means the outcome cannot be told.[^outcomes] A
finished run is deliberately not announced on a channel, so a nightly job does not wake the
room.[^outcomes] Work an agent is asked to do runs as a process of its own, so it outlives a gateway
restart.[^ownprocess]

An agent that improves itself gets one protected weekly schedule, once it has been used on seven separate
days.[^upkeep]

[^commands]: `src/rundesk/commands/schedules.py` — `register()` declares the six verbs and the shared
    flags.
[^shape]: `src/rundesk/schedules/due.py` — `Schedule` and `understood()` hold one of a cron line and a
    moment, and one of a program and a prompt; `FIELDS` names the five cron fields; `A_MOMENT` and
    `SAID_AS` give the moment's shape; `expired()` is derived from the expiry.
[^clock]: `src/rundesk/schedules/due.py` — the module docstring separates the local fields from the UTC
    ones.
[^due]: `src/rundesk/schedules/due.py` — `due_at()` makes a moment due in its own minute alone,
    `_not_yet()` compares strictly later and its comment gives the wall-clock reason, and `LOOK_AHEAD`
    runs past nine years.
[^claim]: `src/rundesk/schedules/kept.py` — `claimed()` writes the minute before the work starts and
    raises rather than returning a value a caller could ignore; `src/rundesk/schedules/firing.py` —
    `claiming()` takes the exclusive claim and `Occupied` is the answer for a run still going.
[^fired]: `src/rundesk/schedules/firing.py` — `looked()` rebuilds the fired minutes from the records,
    reports a row it cannot read, and runs each firing inside a guard.
[^outcomes]: `src/rundesk/schedules/kept.py` — `OUTCOMES` names the three, and the module docstring
    states a finished run is not announced on a channel.
[^ownprocess]: `src/rundesk/providers/answering.py` — `OnASchedule` spawns `THE_RUNNER` as a process of
    its own.
[^upkeep]: `src/rundesk/schedules/upkeep.py` — `UPKEEP`, `DATES_REQUIRED` and `activity()`.
