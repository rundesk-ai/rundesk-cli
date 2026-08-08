---
id: SLK
name: Slack, as an agent is reached on it
last_verified: 2026-08-02
---

## What this is

What a turn looks like on Slack, and how it is shown there. Being named in a channel makes the turn
happen in a thread rooted at that message, so one thread is one conversation and one session
(R-CH-3). The answer arrives as one message at the end, with what it cost above it, and what the
agent is doing is shown while it works only if the owner asked for it — a reply that rewrites itself
in place is unreadable, so only a running commentary may grow.

Everything about the platform lives in `src/channels/slack` and nowhere else (R-CAD-13). Adding it
required no change under `src/rundesk/`, which is what Phase 15 of the roadmap exists to establish:
a second real surface is a program written against the published channel contract, not an extension
of a core.

### What Slack cannot show, and what is done instead

Two rows of `channel-discord` have no counterpart here. They are recorded as absences with reasons
rather than left as gaps, because a surface renders what its own platform has and skips what it has
not (R-CAD-5), and the turn completes either way.

- **No typing indicator.** Slack has no generic typing indicator a bot may raise.
  `assistant.threads.setStatus` exists but requires the Agents & AI Apps feature, which forces a
  thread-only conversation UI on every exchange. So the 👀 mark and the running commentary are the
  whole of what says a turn is running, and R-SLK-5 carries the weight R-DIS-5 and R-DIS-6 shared.
- **No presence to set.** `users.setPresence` is a user-token method and cannot be called with a bot
  token. A bot installed with `always_online: false` in its manifest shows as active for exactly as
  long as its socket is open, which is this adapter's own lifetime — so presence is configured once,
  by the manifest in `docs/slack-app-manifest.yaml`, and never touched in code.

One shape differs rather than being absent. **Slack allows one app per slash command name in a
workspace**, and the last app to register a name wins it. So this surface offers *one* command whose
name the owner chooses — `/rundesk` by default, `--command` to change it — with the gesture as its
first word. Eleven names would take `/stop` from every other app in the workspace and make two
Rundesk agents in one workspace impossible.

## Why it exists

- The owner sees at a glance whether a message was seen, is being worked on, or is finished, and
  which question an answer belongs to.
- An agent in a shared workspace stays quiet until it is spoken to.
- Steering an agent uses Slack's own slash command, which is discoverable and described where it is
  offered, rather than words typed in chat.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-SLK-1 | Being named in a channel makes the turn happen in a thread rooted at that message | `being named in a channel puts the turn in a thread`, `a named message in a channel arrives keyed by its new thread`, `named inside a thread it answers there rather than starting another`, `a thread belongs to the channel it is in` |
| ✅ | R-SLK-2 | An agent stays silent in a shared channel until it is named | `an agent stays silent in a shared channel until it is named`, `an unnamed message in a channel arrives at nothing`, `it does not answer in somebody elses thread unless named`, `a message in a thread it has never answered in is ignored`, `an agent confined to a workspace answers anywhere in it`, `a direct message channel takes only direct messages`, `naming a channel still narrows it to that channel` |
| ✅ | R-SLK-3 | Inside a thread it has answered in, an agent answers without being named again | `inside a thread it has answered in it answers without being named`, `a message in a thread it has answered in needs no naming`, `a thread is asked about once and then remembered` |
| ✅ | R-SLK-4 | In a one-to-one conversation an agent answers where it was spoken to, and starts no thread | `in a one to one conversation it answers where it was spoken to`, `a direct message arrives keyed by its channel and is never threaded`, `an answer in a direct message starts no thread`, `a direct message is answered only when that is what was asked for` |
| ❌ | R-SLK-5 | A message that has been taken up is marked as seen | src/channels/slack — the mark itself is proved offline; that it appears on a real message is what a fake cannot show. .knowledge/scripts/probe-slack says what to do and what to look for |
| ✅ | R-SLK-6 | A turn that is still running remains visibly so, on a surface with no typing indicator to renew | `a running turn keeps its seen mark until it ends`, `a remark said mid turn does not unmark the turn`, `no typing indicator is attempted` |
| ✅ | R-SLK-7 | A turn that has ended is marked with how it ended | `every state the seam decides has something to show for it` |
| ✅ | R-SLK-8 | A turn carries one mark at a time, so how it ended replaces that it was seen | `how it ended replaces that it was seen` |
| ✅ | R-SLK-9 | A turn that failed says what failed, without publishing what was private | `stopping and failing are not the same mark`, `a turn that failed says what failed`, `a tool failure never publishes its private details` |
| ✅ | R-SLK-10 | Stopping, forgetting and restarting are offered as Slack's own command, described where offered | `every word it offers is a gesture the seam defines`, `every word is described where it is offered`, `it is one command and not one per gesture`, `a new session and stopping a turn are different gestures` |
| ❌ | R-SLK-11 | A command is answered inside the three seconds Slack allows before it reports a timeout | src/channels/slack — the ordering is proved offline; whether three seconds is enough on a real socket is what only Slack can answer. .knowledge/scripts/probe-slack says what to do and what to look for |
| ✅ | R-SLK-12 | What a command did arrives as the turn's own outcome rather than as the command's answer | `a control is acknowledged and never answered with the turn` |
| ✅ | R-SLK-13 | Output longer than a Slack message allows is split or attached rather than cut | `an answer that fits is one message`, `an answer too long is broken at a line where there is one`, `an answer with nowhere to break is cut rather than dropped`, `nothing is lost however many messages it takes`, `the limit is under what slack recommends`, `a notice too long for one message is split` |
| ❌ | R-SLK-14 | Writes are paced so that Slack does not refuse them | src/channels/slack — the pacing is set against Slack's documented one-message-per-second-per-channel tier; whether it is enough is what a real workspace answers. .knowledge/scripts/probe-slack says what to do and what to look for |
| ❌ | R-SLK-15 | The owner is told when their agent comes up and when it goes down | src/channels/slack — the once-per-gateway rule and the ordering are proved offline; that the message arrives is proved by hand, both coming up and going down. .knowledge/scripts/probe-slack says what to do and what to look for |
| ❌ | R-SLK-16 | An agent shows as active for as long as the gateway running it is up | src/channels/slack — presence is a thing only the platform shows, and here it follows the socket because the manifest says so rather than because any call sets it. .knowledge/scripts/probe-slack says what to do and what to look for |
| ✅ | R-SLK-17 | An answer arrives as one message, with what it cost above it | `what a turn cost is shown as one line above the answer`, `a turn that reported no cost still says how long it took`, `a small count is not rounded into a zero` |
| ❌ | R-SLK-18 | An answer too long to read as messages is attached as a file instead | src/channels/slack — the decision to attach is proved offline; the upload is the platform's. .knowledge/scripts/probe-slack says what to do and what to look for |
| ❌ | R-SLK-19 | A file the agent made is uploaded rather than described | src/channels/slack — the verification and the call are proved offline; that it renders in Slack is what a fake cannot show. .knowledge/scripts/probe-slack says what to do and what to look for |
| ✅ | R-SLK-20 | Slack shows broad activity compactly while work runs, and only when the owner asked | `showing the work is off when the owner turned it off`, `what a turn cost is kept even when the work is not shown`, `consecutive activity is one line with a count`, `only consecutive activity is counted`, `an intervening message breaks a count`, `a subagent start and finish are two broad categories`, `a safe subagent name is shown without its provider path`, `named subagents still collapse as one broad category`, `thinking is a broad category and never the thought itself`, `an unknown tool uses thinking instead of a vendors name`, `a tools own name is never shown`, `a long commentary keeps the newest and says it dropped the rest`, `every verb the seam defines has a mark and a word`, `the three continuity verbs are marked apart from editing` |
| ✅ | R-SLK-21 | Slack says which channel and which person a message came from, in the words Slack shows | `slack says which room and which person a message came from`, `a direct message is named as one rather than as a channel`, `slack maps its places to the shared channel hierarchy` |
| ✅ | R-SLK-22 | Read-only gateway information is offered through Slack's command and answered privately | `a read only question is reported for authorization and held`, `a gateway answer completes the exact command that asked`, `a question from somebody not allowed is refused before it is reported`, `an unknown word is answered with what it knows and reported as nothing` |
| ✅ | R-SLK-23 | A Slack command is handled only by the channel whose configured place contains it | `one command belongs to exactly one configured surface`, `a command named for another app is not ours` |
| ✅ | R-SLK-24 | A completed Slack answer shows compact elapsed time beside any reported token cost | `a turn that reported no cost still says how long it took`, `elapsed time runs from taken and a repeat does not restart it` |
| ✅ | R-SLK-25 | A single-user Slack channel offers a provider change and privately reports its result | `a provider change is offered only on a single user channel`, `a provider change is reported and never decided here`, `a provider change result completes the private command` |
| ✅ | R-SLK-26 | A gateway returning from update maintenance names the version now listening and links its release | `a gateway returning from an update links the version now listening`, `a gateway told only a version still names it` |
| ✅ | R-SLK-27 | An ordinary gateway startup adds no update wording and no release link | `an ordinary startup adds no update wording and no release link`, `the record goes out every time even when the message does not` |
| ✅ | R-SLK-28 | An answer is written into the thread the turn is in, and never into a thread somewhere else | `an answer is written into the thread the turn is in`, `an answer in a direct message starts no thread`, `a scheduled report is a reply to the message that said it started` |
| ✅ | R-SLK-29 | A completed Slack answer leads its cost line with how big the conversation is, where the provider said so | `the footer leads with how big the conversation is`, `a brain that reports no conversation size gets what it always got` |
| ✅ | R-SLK-30 | Slack holds the message it posted to say a scheduled run began, and posts that run's report as a reply to it | `a scheduled report is a reply to the message that said it started`, `a report for a schedule nobody announced quotes nothing`, `an ordinary remark quotes nothing`, `a notice that could not be posted is not held` |
| ✅ | R-SLK-31 | A completed Slack answer names its human recipient, and nothing else Slack posts names anybody | `an answer names who asked in a room and nobody in a direct message`, `only the first piece of a split answer names anybody`, `a remark said mid turn names nobody`, `an answer too long to read as messages is attached instead` |
| ✅ | R-SLK-32 | A connected Slack bot keeps the identity its owner configured in the app manifest | `presence is not something this file sets` |
| ✅ | R-SLK-33 | A completed Slack answer begins its completion line with the provider that ran the turn | `what a turn cost is shown as one line above the answer` |
| ✅ | R-SLK-34 | An inbound Slack threaded reply carries the message it is under into Rundesk's shared reply context | `a threaded reply carries the message it is under`, `a parent that cannot be fetched still reports the arrival` |
| ✅ | R-SLK-35 | A terminal Slack notice neither claims an idle turn is running nor erases a newer turn that is running | `a terminal notice does not erase a newer running turn` |
| ✅ | R-SLK-36 | Slack offers the current agent's granted skills as a read-only word of its command | `every word it offers is a gesture the seam defines` |
| ✅ | R-SLK-37 | Slack offers the schedules this agent can still run as a read-only word of its command | `every word it offers is a gesture the seam defines` |
| ✅ | R-SLK-38 | Slack sends a notice meant for the owner alone as a direct message to them | `a notice for the owner reaches them and starts no conversation`, `a notice too long for one message is split`, `a notice with nothing in it is not sent` |
| ✅ | R-SLK-39 | Slack sends a notice meant for one named allowed user to that user, and refuses one naming somebody the channel does not allow | `a notice naming somebody is carried to that person`, `a notice naming somebody this channel does not allow is refused` |
| ✅ | R-SLK-40 | An answer names its recipient outright only where the room holds more than that one person | `an answer names who asked in a room and nobody in a direct message` |
| ✅ | R-SLK-41 | A name written into an answer stands under its completion line rather than in front of it | `a name written into an answer stands under the completion line` |
| ✅ | R-SLK-42 | Ordinary Markdown written by a brain reaches Slack in the dialect Slack renders | `bold and italics are slacks and not markdowns`, `bold is not read back as italic`, `a link is written the way slack writes one`, `a heading becomes bold because slack has none`, `nothing inside a fenced code block is touched`, `nothing inside inline code is touched`, `arithmetic is not mistaken for emphasis`, `an answer reaches slack in slacks dialect` |
| ✅ | R-SLK-43 | A Socket Mode envelope is acknowledged before any work, and acted on exactly once | `an envelope is acknowledged before anything else happens`, `an envelope already handled is dropped`, `the same message is never reported twice`, `an app mention is not taken as well as the message`, `a message from this bot is never answered`, `an edit or a join notice is not somebody speaking` |
| ✅ | R-SLK-44 | Slack needs two credentials, and both are named rather than handed over | `both credentials are named and only named`, `both credentials have a file to be taken into`, `no credential is ever written into the settings`, `an option it does not understand is refused by name`, `a considered refusal still exits zero` |
| ✅ | R-SLK-45 | Characters Slack reserves are escaped in everything a brain wrote, so no answer can address the room | `slacks reserved characters are escaped wherever they appear`, `a broadcast an agent only mentioned does not notify the room`, `what the translation builds is not escaped a second time` |

## Open questions

- Whether a Slack thread that has gone quiet should be left alone, summarised, or closed, and whether
  that is Rundesk's to do.
- Whether one slash command per agent is right when an owner runs several in one workspace, or
  whether the agent's name should be the command by default.
- Whether the Agents & AI Apps feature — and the thread-only UI it forces — is worth having for the
  typing indicator it would bring back.
- Whether a Block Kit `markdown` block should replace the `mrkdwn` translation once its rendering in
  direct messages, and its handling of `<@U…>` mentions, has been watched on a real workspace.
- Whether a private channel the bot has been removed from should be noticed and said, rather than
  found out when a schedule fails to deliver.
