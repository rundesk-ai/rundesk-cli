---
id: DIS
name: Discord, as an agent is reached on it
---

## What this is

What a turn looks like on Discord, and how it is shown there. Being named in a server channel opens a
thread and the turn happens inside it, so one thread is one conversation and one session (R-CH-3). A turn arrives as
one message, at the end, with what it cost above the answer — because a phone that buzzes eleven times
to say an agent read a file is worse than one that buzzes once with the reply.

## Why it exists

- The owner sees at a glance whether a message was seen, is being worked on, or is finished.
- An agent in a shared server stays quiet until it is spoken to.
- Steering an agent uses Discord's own commands, which are discoverable, rather than words typed in chat.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ❌ | R-DIS-1 | Being named in a server channel opens a thread, and the turn happens there | — |
| ❌ | R-DIS-2 | An agent stays silent in a shared channel until it is named | — |
| ❌ | R-DIS-3 | Inside a thread it opened, an agent answers without being named again | — |
| ❌ | R-DIS-4 | In a one-to-one conversation an agent answers where it was spoken to | — |
| ❌ | R-DIS-5 | A message that has been taken up is marked as seen | — |
| ❌ | R-DIS-6 | A turn shows the typing indicator for as long as it is still running | — |
| ❌ | R-DIS-7 | A turn that has ended is marked with how it ended | — |
| ❌ | R-DIS-8 | A turn carries one mark at a time, so how it ended replaces that it was seen | — |
| ❌ | R-DIS-9 | A turn that failed says what failed | — |
| ❌ | R-DIS-10 | Stopping and forgetting are offered as Discord's own commands, described where offered | — |
| ❌ | R-DIS-11 | A command is answered inside the time Discord allows before it reports an error | — |
| ❌ | R-DIS-12 | What a command did arrives as the turn's own outcome rather than as the command's answer | — |
| ❌ | R-DIS-13 | Output longer than a Discord message allows is split or attached rather than cut | — |
| ❌ | R-DIS-14 | Writes are paced so that Discord does not refuse them | — |
| ❌ | R-DIS-15 | The owner is told when their agent comes up and when it goes down | — |
| ❌ | R-DIS-16 | An agent shows as online for as long as the gateway running it is up | — |
| ❌ | R-DIS-17 | A turn arrives as one message, with what it cost above the answer | — |

## Open questions

- Whether a mark between seen and finished is worth having for a turn that runs a long time.
- Whether a thread that has gone quiet is archived, and whether that is Rundesk's to do.
- Which of an agent's activity belongs in the thread and which belongs in a message to the owner alone.
- Whether more than one person in a thread may steer the same agent, or only the one who opened it.
- Whether a surface that cannot show presence should say it is up some other way, or stay quiet.
