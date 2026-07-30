---
id: DIS
name: Discord, as an agent is reached on it
last_verified: 2026-07-30
---

## What this is

What a turn looks like on Discord, and how it is shown there. Being named in a server channel opens a
thread and the turn happens inside it, so one thread is one conversation and one session (R-CH-3). The answer
arrives as one message at the end, with what it cost above it, and what the agent is doing is shown
while it works only if the owner asked for it — a reply that rewrites itself in place is unreadable,
so only a running commentary may grow.

## Why it exists

- The owner sees at a glance whether a message was seen, is being worked on, or is finished, and
  which question an answer belongs to.
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
| ✅ | R-DIS-9 | A turn that failed says what failed | `stopping and failing are not the same mark`, `a tool that failed still says so`, `failed collaboration bookkeeping is not hidden` |
| ✅ | R-DIS-10 | Stopping and forgetting are offered as Discord's own commands, described where offered | `every command it offers is a gesture the seam defines`, `every command is described where it is offered`, `a new session and stopping a turn are different gestures` |
| ❌ | R-DIS-11 | A command is answered inside the time Discord allows before it reports an error | src/channels/discord:243 — the three seconds are Discord's, and only Discord can time them; .knowledge/scripts/probe-discord says what to do and what to look for |
| ❌ | R-DIS-12 | What a command did arrives as the turn's own outcome rather than as the command's answer | src/channels/discord:246 — the seam's half is proved offline; what a command shows is the platform's; .knowledge/scripts/probe-discord says what to do and what to look for |
| ✅ | R-DIS-13 | Output longer than a Discord message allows is split or attached rather than cut | `an answer that fits is one message`, `an answer too long is broken at a line where there is one`, `an answer with nowhere to break is cut rather than dropped`, `nothing is lost however many messages it takes`, `a long remark is split without losing any of it`, `the limit is under what discord allows` |
| ❌ | R-DIS-14 | Writes are paced so that Discord does not refuse them | src/channels/discord:69 — whether the pacing is enough is what a real server answers; .knowledge/scripts/probe-discord says what to do and what to look for |
| ❌ | R-DIS-15 | The owner is told when their agent comes up and when it goes down | src/channels/discord:279 — proved by hand, both coming up and going down; .knowledge/scripts/probe-discord says what to do and what to look for |
| ❌ | R-DIS-16 | An agent shows as online for as long as the gateway running it is up | src/channels/discord:271 — presence is a thing only the platform shows; .knowledge/scripts/probe-discord says what to do and what to look for |
| ✅ | R-DIS-17 | An answer arrives as one message, with what it cost above it | `what a turn cost is shown as one line`, `a turn that reported no cost says nothing about it`, `a tool that worked is not a message of its own`, `a small count is not rounded into a zero`, `a count in the millions is not shown in thousands`, `the footer shows the cache writes the seam hands over` |
| ❌ | R-DIS-18 | An answer too long to read as messages is attached as a file instead | src/channels/discord:447 — the splitting is proved offline; uploading is the platform's; .knowledge/scripts/probe-discord says what to do and what to look for |
| ❌ | R-DIS-19 | A file the agent made is uploaded rather than described | src/channels/discord:470 — the upload is the platform's, and proved by hand; .knowledge/scripts/probe-discord says what to do and what to look for |
| ✅ | R-DIS-20 | Discord shows broad activity compactly while work runs, and only when the owner asked | `showing the work is off unless the owner asks`, `consecutive activity is one line with a count`, `only consecutive activity is counted`, `a growing message counts across separate writes`, `activity arriving during an edit gets a successor write`, `an intervening message breaks a count that has not flushed yet`, `a subagent start and finish are two broad categories`, `a safe subagent name is shown without its provider path`, `named subagents still collapse as one broad category`, `finish waits for the child turn not the spawn call`, `thinking is a broad category and never the thought itself`, `an unknown tool uses thinking instead of a gear`, `a tool failure never publishes its private details` |
| ✅ | R-DIS-21 | Discord says which room and which person a message came from, in the words Discord shows | `discord says which room and which person a message came from`, `a direct message is named as one rather than as a channel`, `a thread is named under the channel it was opened in`, `a server with no name to show is not shown as blank`, `discord maps its places to the shared channel hierarchy`, `discord maps an ordinary room without inventing a thread`, `discord maps a direct message without platform containers`, `discords exact legacy defaults are replaced but owner edits are not` |
| ✅ | R-DIS-22 | Read-only gateway information is offered as Discord's own commands | `read only gateway information is offered as discord commands`, `a gateway answer completes the exact deferred interaction`, `a read only command is deferred and reported for authorization` |
| ✅ | R-DIS-23 | A Discord command is handled only by the channel whose configured place contains it | `one slash interaction belongs to exactly one configured surface` |
| ✅ | R-DIS-24 | A completed Discord answer shows compact elapsed time beside any reported token cost | `elapsed time is compact at seconds minutes and hours`, `elapsed time runs from taken until the answer is ready`, `repeated taken does not restart elapsed time`, `provider and elapsed time are shown when usage was not reported` |
| ✅ | R-DIS-25 | A single-user Discord channel offers a provider change and privately reports its result | `provider is deferred and reported for authorized configuration`, `provider result completes the exact private interaction`, `shared channel provider command is privately refused before reporting` |
| ✅ | R-DIS-26 | A gateway returning from update maintenance names the version now listening and links its release | `a gateway returning from an update links the version now listening`, `a gateway told only a version still names it` |
| ✅ | R-DIS-27 | An ordinary gateway startup adds no update wording and no release link | `an ordinary startup adds no update wording and no release link` |
| ✅ | R-DIS-28 | An answer is a reply to the message that asked, unless that message is not in the conversation the turn is in | `an answer in a direct message is a reply to the message that asked`, `an answer in a channel is a reply to the message that asked`, `an answer does not quote a message from somewhere else`, `only the first piece of a split answer carries the anchor`, `the anchor is read off the attribute a message actually has`, `an answer still arrives when the message it quotes is gone` |
| ✅ | R-DIS-29 | A completed Discord answer leads its cost line with how big the conversation is, where the provider said so | `the footer leads with how big the conversation is`, `the whole footer an owner reads is the size what was written and the clock`, `a brain that does not report a conversation size gets the footer it always got` |
| ✅ | R-DIS-30 | Discord holds the message it posted to say a scheduled run began, and posts that run's report as a reply to it | `a scheduled report is a reply to the message that said it started`, `a report for a schedule nobody announced quotes nothing`, `an ordinary remark still quotes nothing`, `a notice is answered once and never by the next firing`, `a notice that could not be posted is not held`, `an anchor is kept for the room being written in not the one named`, `a scheduled report still arrives when its notice is gone` |
| ✅ | R-DIS-31 | A completed answer mentions the person it is replying to, and nothing else Discord posts mentions anybody | `an answer in a direct message mentions the person who asked`, `only the first piece of a split answer mentions anybody`, `an answer attached as a file still mentions who asked`, `an answer with no message to reply to mentions nobody`, `an answer whose question is in another room mentions nobody`, `a remark said mid turn mentions nobody`, `a scheduled report mentions nobody though it is a reply`, `the commentary and the mark on a failure mention nobody`, `a quiet channel still posts one message and it is the mentioned answer`, `a mentioned answer that cannot be delivered is said and the turn goes on`, `a message nobody asked to mention does not` |
| ✅ | R-DIS-32 | A connected Discord bot keeps the username and profile identity its owner configured in Discord | `connecting never edits the bot profile` |
| ✅ | R-DIS-33 | A completed Discord answer begins its completion line with the provider that ran the turn | `the whole footer an owner reads is the size what was written and the clock`, `provider and elapsed time are shown when usage was not reported` |
| ✅ | R-DIS-34 | An inbound Discord reply carries its referenced message into Rundesk's shared reply context | `on message reports the reply on the arrived record`, `a resolved reply carries the parent identity author and body`, `a deleted or unfetched parent still carries its identity`, `a non reply reference is not presented as a reply`, `a message without a reference has no reply context` |

## Open questions

- Whether a mark between seen and finished is worth having for a turn that runs a long time.
- Whether a thread that has gone quiet is archived, and whether that is Rundesk's to do.
- Which of an agent's activity belongs in the thread and which belongs in a message to the owner alone.
- Whether more than one person in a thread may steer the same agent, or only the one who opened it.
- Whether a surface that cannot show presence should say it is up some other way, or stay quiet.
- Whether a scheduled report should mention the person the schedule reports to, having no asker of its own.
