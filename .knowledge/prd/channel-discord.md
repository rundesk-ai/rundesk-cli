---
id: DIS
name: Discord, as an agent is reached on it
last_verified: 2026-07-25
---

## What this is

What a turn looks like on Discord, and how it is shown there. Being named in a server channel opens a
thread and the turn happens inside it, so one thread is one conversation and one session (R-CH-3). The answer
arrives as one message at the end, with what it cost above it, and what the agent is doing is shown
while it works only if the owner asked for it — a reply that rewrites itself in place is unreadable,
so only a running commentary may grow.

## Why it exists

- The owner sees at a glance whether a message was seen, is being worked on, or is finished.
- An agent in a shared server stays quiet until it is spoken to.
- Steering an agent uses Discord's own commands, which are discoverable, rather than words typed in chat.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-DIS-1 | Being named in a server channel opens a thread, and the turn happens there | `being named in a server channel opens a thread`, `a thread is named for what was asked`, `a long question is clipped rather than refused`, `a question with nothing in it still gets a name`, `a thread belongs to the channel it was opened in` |
| ✅ | R-DIS-2 | An agent stays silent in a shared channel until it is named | `an agent stays silent in a shared channel until it is named`, `it does not answer in somebody elses thread unless named`, `an agent confined to a server and no further answers anywhere in it`, `an agent pointed at direct messages answers only those`, `one message in a room is taken by exactly one channel`, `a direct message is taken by the direct message channel only`, `a room channel still answers only in the room it names`, `a room channel given a server answers in every room of it` |
| ✅ | R-DIS-3 | Inside a thread it opened, an agent answers without being named again | `inside a thread it opened it answers without being named` |
| ✅ | R-DIS-4 | In a one-to-one conversation an agent answers where it was spoken to | `in a one to one conversation it answers where it was spoken to`, `a direct message is answered only when that is what was asked for` |
| ❌ | R-DIS-5 | A message that has been taken up is marked as seen | src/channels/discord:399 — proved by hand against a real server; a mark on a real message is what a fake cannot show; .knowledge/scripts/probe-discord says what to do and what to look for |
| ❌ | R-DIS-6 | A turn shows the typing indicator for as long as it is still running | src/channels/discord:414 — proved by hand; a typing indicator only exists on the platform; .knowledge/scripts/probe-discord says what to do and what to look for |
| ✅ | R-DIS-7 | A turn that has ended is marked with how it ended | `every state the seam decides has something to show for it` |
| ✅ | R-DIS-8 | A turn carries one mark at a time, so how it ended replaces that it was seen | `how it ended is told from that it was seen` |
| ✅ | R-DIS-9 | A turn that failed says what failed | `stopping and failing are not the same mark`, `a tool that failed still says so` |
| ✅ | R-DIS-10 | Stopping and forgetting are offered as Discord's own commands, described where offered | `every command it offers is a gesture the seam defines`, `every command is described where it is offered`, `a new session and stopping a turn are different gestures` |
| ❌ | R-DIS-11 | A command is answered inside the time Discord allows before it reports an error | src/channels/discord:243 — the three seconds are Discord's, and only Discord can time them; .knowledge/scripts/probe-discord says what to do and what to look for |
| ❌ | R-DIS-12 | What a command did arrives as the turn's own outcome rather than as the command's answer | src/channels/discord:246 — the seam's half is proved offline; what a command shows is the platform's; .knowledge/scripts/probe-discord says what to do and what to look for |
| ✅ | R-DIS-13 | Output longer than a Discord message allows is split or attached rather than cut | `an answer that fits is one message`, `an answer too long is broken at a line where there is one`, `an answer with nowhere to break is cut rather than dropped`, `nothing is lost however many messages it takes`, `the limit is under what discord allows` |
| ❌ | R-DIS-14 | Writes are paced so that Discord does not refuse them | src/channels/discord:69 — whether the pacing is enough is what a real server answers; .knowledge/scripts/probe-discord says what to do and what to look for |
| ❌ | R-DIS-15 | The owner is told when their agent comes up and when it goes down | src/channels/discord:279 — proved by hand, both coming up and going down; .knowledge/scripts/probe-discord says what to do and what to look for |
| ❌ | R-DIS-16 | An agent shows as online for as long as the gateway running it is up | src/channels/discord:271 — presence is a thing only the platform shows; .knowledge/scripts/probe-discord says what to do and what to look for |
| ✅ | R-DIS-17 | An answer arrives as one message, with what it cost above it | `what a turn cost is shown as one line`, `a turn that reported no cost says nothing about it`, `a tool that worked is not a message of its own`, `a small count is not rounded into a zero` |
| ❌ | R-DIS-18 | An answer too long to read as messages is attached as a file instead | src/channels/discord:447 — the splitting is proved offline; uploading is the platform's; .knowledge/scripts/probe-discord says what to do and what to look for |
| ❌ | R-DIS-19 | A file the agent made is uploaded rather than described | src/channels/discord:470 — the upload is the platform's, and proved by hand; .knowledge/scripts/probe-discord says what to do and what to look for |
| ✅ | R-DIS-20 | What an agent is doing is shown while it works only if the owner asked for it | `showing the work is off unless the owner asks`, `the commentary may grow but the answer may never`, `a long commentary is kept to what one message holds` |
| ✅ | R-DIS-21 | Discord says which room and which person a message came from, in the words Discord shows | `discord says which room and which person a message came from`, `a direct message is named as one rather than as a channel`, `a thread is named under the channel it was opened in`, `a server with no name to show is not shown as blank` |
| ✅ | R-DIS-22 | Read-only gateway information is offered as Discord's own commands | `read only gateway information is offered as discord commands`, `a gateway answer completes the exact deferred interaction`, `a read only command is deferred and reported for authorization` |
| ✅ | R-DIS-23 | A Discord command is handled only by the channel whose configured place contains it | `one slash interaction belongs to exactly one configured surface` |

## Open questions

- Whether a mark between seen and finished is worth having for a turn that runs a long time.
- Whether a thread that has gone quiet is archived, and whether that is Rundesk's to do.
- Which of an agent's activity belongs in the thread and which belongs in a message to the owner alone.
- Whether more than one person in a thread may steer the same agent, or only the one who opened it.
- Whether a surface that cannot show presence should say it is up some other way, or stay quiet.
