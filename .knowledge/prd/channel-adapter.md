---
id: CAD
name: The seam a surface is reached through
last_verified: 2026-07-25
---

## What this is

A channel adapter is a program that speaks one messaging platform and reports what arrives in words no
platform owns. Rundesk holds it open inside the agent's gateway, hands it what a turn is doing, and ends
it — it never loads an adapter's code, and it never lets a platform's vocabulary past the seam. Discord
is the first one and is first-class; a second is one more program rather than a change here.

## Why it exists

- An owner can reach an agent from whatever they already use, including something nobody here wrote.
- A surface with almost nothing — no reactions, no typing, no edits — still carries a whole turn.
- What a turn is doing is decided once, so two surfaces can never disagree about it.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-CAD-1 | A channel adapter is a program Rundesk runs, never code it loads | `a channel this rundesk has never heard of is the ordinary case`, `a shipped channel is found by looking rather than by being listed`, `a channel that is not there is the only way resolving fails`, `a record of a kind nobody knows breaks nothing`, `an adapter is a program this machine can run` |
| ✅ | R-CAD-2 | A channel adapter Rundesk has never heard of carries a whole conversation | `a channel adapter this code has never seen carries a whole conversation` |
| ✅ | R-CAD-3 | Rundesk decides whether a turn is taken up, running, finished, stopped or failed | `every state a turn can be in is named here`, `a stopped turn is marked as stopped rather than failed`, `a turn that went wrong is reported rather than lost` |
| ✅ | R-CAD-4 | An adapter is told how a turn stands, and decides only how its platform shows it | `an adapter is told how a turn stands rather than asked`, `what a brain can do reaches the surface that would offer it`, `every state the seam decides has something to show for it` |
| ✅ | R-CAD-5 | A surface that cannot show something still carries the turn through to an answer | `a surface with nothing at all still carries a turn` |
| ❌ | R-CAD-6 | An agent's channels are held open by the gateway that runs it | src/rundesk/gateway.py:1276 — proved by hand against a real Discord gateway, not by a test: the case needs a gateway serving a channel for real |
| ❌ | R-CAD-7 | A channel that drops its connection returns without a turn noticing | src/rundesk/gateway.py:1300 — a turn surviving a drop is proved, the adapter coming back on its own is not |
| ✅ | R-CAD-8 | An agent that is not running is reported as out of reach rather than silently missing what arrives | `an agent that is not running is reported as out of reach` |
| ✅ | R-CAD-9 | Adding a channel proves it can connect before anything about it is written down | `an adapter says whether it can reach what it was pointed at`, `an adapter that cannot reach its platform says why`, `an adapter that answers with nonsense has proved nothing`, `an adapter that says nothing is reported by what it said went wrong`, `adding a channel that cannot connect writes nothing and says why`, `adding a channel that works writes what the adapter asked to keep`, `taking one channel off leaves every other one on` |
| ✅ | R-CAD-10 | A channel that nobody is allowed to use is refused rather than defaulted | `a channel nobody may use is never written down`, `adding a channel with nobody allowed is refused`, `allowing nobody in particular is refused too`, `a record allowing nobody authorizes nobody` |
| ✅ | R-CAD-11 | A credential a channel needs is never an argument, and is taken and kept for an owner who has not placed it | `an adapter names a credential rather than giving one`, `the one credential an adapter named is the only one it gets`, `a credential that is not set is not invented`, `the credential is read from the environment and never an argument`, `a supervised gateway finds its token without a shell`, `a credential is taken from a pipe and never from an argument`, `a credential nobody can supply is a refusal rather than a wait`, `no option on the command takes a credential as its value` |
| ✅ | R-CAD-12 | What shows a channel says a credential is present rather than what it is | `what is kept is the name of a credential and never one`, `a credential is named as present rather than shown`, `no option takes a secret as a value` |
| ✅ | R-CAD-13 | No word belonging to one platform appears outside the adapter that speaks it | `an adapter is told which channel and whose it is`, `what a platform needs is handed back unread`, `what the owner typed reaches the adapter exactly as typed`, `what a platform needs is never read by the command`, `a platforms options survive looking like rundesks own` |
| ✅ | R-CAD-14 | An adapter decides the shape of what Rundesk keeps for it, and Rundesk reads none of it | `an adapter decides the shape of what is kept for it`, `what an adapter keeps for itself is its own business`, `a platforms own words are kept exactly as it gave them` |
| ✅ | R-CAD-15 | An adapter says which kinds of place it reached, and each becomes a channel of its own | `a surface reports the kinds of place it comes in`, `a surface that reports no kinds of place is a whole adapter`, `a kind of place that could not be a channel is dropped`, `a starting wording that names something unfillable is not kept`, `one add makes a channel for each kind of place`, `a kind of place whose name is already taken adds none of them`, `each kind of place is given a home under its own name`, `the checks own directory is not left behind when it is empty`, `a check directory with something in it is kept and said`, `naming no place at all takes both kinds`, `naming only direct messages leaves the rooms out`, `naming only a room leaves direct messages out`, `naming both takes both` |
| ✅ | R-CAD-16 | An adapter is told which place to say something in, and resolves that word itself | `a name with its hash and without are one room`, `a room is found however it was capitalised`, `a different room is not this one`, `what an owner typed is taken as they typed it` |
| ✅ | R-CAD-17 | A channel adapter can ask Rundesk a closed set of read-only questions | `a gateway query is closed and read only`, `status names the agent and its gateway state`, `version tells installed code from the running gateway`, `agents lists every configured agent in name order`, `help names read only conversation and agent commands` |
| ✅ | R-CAD-18 | A channel adapter can request an authorized provider change and receive its result | `provider is deferred and reported for authorized configuration`, `an authorized provider command changes the default and starts fresh`, `provider configuration requires a correlated whole record`, `a provider configuration result is a record a surface may receive` |

## Open questions

- Whether an adapter is told which of its abilities Rundesk will use, the way a brain is asked.
- Whether one agent may be reached on two surfaces at once, and what that does to a conversation.
- Whether a surface may refuse a turn outright, and what an owner sees when it does.
- Where an adapter that is not on the machine is reported — by `doctor`, at setup, or both.
