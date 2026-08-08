# The three clocks, and which one answers what

rundesk reads the time in three different ways, and they are not interchangeable. Each answers a
different question, and using one where another belongs is not a style choice — it produces a wrong
answer that looks entirely reasonable.

The rule is one sentence: **a record takes UTC, a line somebody reads takes the machine's own time,
and a duration takes neither.**

| The question | What is used | Where |
|---|---|---|
| When did this happen, for something to compare later? | UTC, `%Y-%m-%dT%H:%M:%SZ` | `core.config.MOMENT` — the install's own records, an agent's `migrations` rows |
| When did this happen, for somebody to read? | the machine's own time, with its offset | `utils.logs.stamp` — every log line, and every moment a command prints |
| How long since, or how long until? | `time.monotonic()` | every deadline, every retry ceiling, and a gateway's beat |

## Why a record is UTC

A stored moment is compared: to another record, by a later release, possibly on another machine. UTC
is the only reading that means the same thing in all three cases. A backup's name is UTC for a
further reason — `backups.WHEN` is `%Y-%m-%dT%H-%M-%SZ`, dashes because a colon is not a filename —
and sorting those names by string is the same as sorting them by age, which is what makes "newest
first" a fact rather than a guess.

## Why a line is local

A person reading a log is placing an event against their own day. A UTC line asks them to do
arithmetic to answer "was this before or after I left", and it is arithmetic they will get wrong the
week the clocks change.

Every line carries its **offset** — `[2026-08-05 08:54:33-04:00]` — and that is not decoration. On
the night the clocks go back, one wall-clock hour happens twice; without the offset the log has two
blocks of the same hour in it and no way to tell which came first. With it, the ordering is readable
from the line.

Day-stamped log files are named from the same local reading, so the file called `2026-08-05.log`
holds the day somebody had.

## Why a duration is neither

**The wall clock moves in both directions.** A laptop waking, an NTP correction, an owner fixing
their timezone — all of them can move it backwards. An age taken from it can come out negative, or
hours wrong, and nothing about the reading says so.

That matters most for a gateway's beat. A gateway writes a `time.monotonic()` reading every fifteen
seconds, and missing three beats is what marks it wedged. Taken from the wall clock instead, a
perfectly healthy gateway would be reported wedged because somebody's clock was adjusted — and the
resolution offered for a wedged gateway is a restart, so a clock correction would end a working
agent's process.

There is one thing to be careful of, and it is already handled where it arises: **a monotonic reading
only means anything within one boot.** The gateway's record persists, so a reading in it could in
principle be compared across a reboot and give nonsense. It cannot be, because staleness is only ever
asked about a gateway that is running *now*, and a lock cannot outlive the machine that granted it —
`gateways.standing._wedged` says so at the point it matters.

**On macOS `time.monotonic()` does not advance across system sleep** — measured on one machine as a
40.5-hour gap over 14.66 days of wall clock. That is the behaviour that is wanted, not a defect to
correct around: a sleeping laptop freezes the gateway too, so it misses no beat it was awake for. A
clock that went on counting through the sleep would have every single wake report a perfectly healthy
gateway as wedged, and then offer to restart it.
