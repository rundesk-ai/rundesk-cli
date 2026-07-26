---
id: CH
name: A channel, and the work that arrives on it
last_verified: 2026-07-25
---

## What this is

A channel is a messaging surface an agent is reached on, and one agent may have several. It connects to
a platform, turns what arrives into work for that agent, and shows what it can of the turn that follows.
Platforms differ enormously in what they can show, so a channel renders what its own has and skips what
it has not — what never differs is that the work runs and is answered.

## Why it exists

- An owner reaches an agent from an app they already have open, and watches it work as it happens.
- A second platform is a file added beside the first, never a change to what already works.
- One conversation is one session, so two of them never answer into each other.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-CH-1 | A channel dispatches what arrives on it as work for the agent it belongs to | `a message from somebody allowed is carried through` |
| ❌ | R-CH-2 | A channel belongs to exactly one agent | src/rundesk_cli/channel.py:246 — the record is one agent's, so nothing can express a channel on two; no test proves what cannot be written |
| ✅ | R-CH-3 | Each conversation on a channel keeps a provider session of its own | `each conversation keeps a session of its own`, `a conversation is named so two channels cannot collide` |
| ✅ | R-CH-4 | A message from anyone the channel does not authorize is never dispatched | `a message from anyone the channel does not authorize is never dispatched`, `somebody the channel does not authorize is not dispatched`, `a gesture from somebody not allowed ends nothing`, `nobody in particular is not somebody` |
| ✅ | R-CH-5 | What a message says cannot change which agent, provider or model answers it | `a message naming a provider or model changes neither` |
| ✅ | R-CH-6 | A channel shows what an agent is doing while its turn is still running | `what the agent did is shown while the turn is still running`, `what the agent did is shown while it is happening` |
| ✅ | R-CH-7 | A channel shows only whole units of an agent's output, never a part-written one | `what a brain says is not something an adapter can be shown early`, `a control raised mid turn publishes no half written answer` |
| ✅ | R-CH-8 | A channel gives an agent's answer whole, once the turn has ended | `the answer arrives whole and once`, `an answer too long for any one message crosses whole`, `a turn that said nothing hands over no empty answer` |
| ✅ | R-CH-9 | A person can stop the turn running in their own conversation | `a stop ends the turn in that conversation and nothing else`, `a brain that can be steered is given the words now`, `a brain that cannot be steered answers the second message after`, `a burst arriving before the turn is admitted still steers it` |
| ✅ | R-CH-10 | A person can forget their conversation's session, so the next message starts a new one | `forgetting a conversation starts the next one fresh`, `forgetting while a turn runs is not undone when it ends` |
| ❌ | R-CH-11 | A channel leaves nothing running once the turn it belonged to has ended | src/rundesk_cli/gateway.py:1300 — inherited from what ends a program at all; no test of its own here |
| ✅ | R-CH-12 | A failure to deliver on a channel does not end the turn it was reporting | `a delivery that fails does not end the turn it was reporting`, `every delivery failing still leaves the turn finished` |
| ✅ | R-CH-13 | Raw tool arguments and results do not leave the machine unless a rule allows them | `raw tool arguments and results do not leave the machine`, `a field nobody here knows stays here`, `a summary too long to show is bounded rather than dropped` |
| ✅ | R-CH-14 | A conversation's session is found again after the gateway holding it restarted | `a conversations session is found again after a restart`, `reconnecting finds the conversation it already had` |
| ✅ | R-CH-15 | Work a channel dispatched is findable afterwards by the run it became | `work a channel dispatched is findable by the run it became`, `the run is named from the first mark rather than the last`, `a channel writes nothing of its own`, `where a turn came from is written into its account`, `a turn says which run it became before the brain is started` |
| ❌ | R-CH-16 | A person can restart the agent answering them, from the channel they are on | src/rundesk_cli/answering.py:166 — proved by hand against a real gateway; a case needs one the machine will bring back |
| ✅ | R-CH-17 | What a person attached reaches the agent as a file already on this machine | `a message with nothing but an attachment is still a message`, `a message with neither words nor anything attached is not one`, `something attached that is not on this machine is dropped` |
| ✅ | R-CH-18 | What the agent made is sent only from where that agent works | `what the agent made is sent from where it works`, `a file outside where the agent works is not sent`, `a file a brain never made is not invented` |
| ✅ | R-CH-19 | A finished thing an agent says mid-turn is shown then, and its last is the answer | `a finished thing said mid turn is shown when the next one arrives`, `only one finished thing said is all answer and no remark`, `a reply written a piece at a time is still held to the end` |
| ✅ | R-CH-21 | An agent is told which surface and which conversation it is answering in | `a brain is told which surface and conversation it is answering in`, `a surface that names neither is answered exactly as before`, `a surface that names neither says neither`, `a name somebody chose cannot write its own line in the prompt`, `a channel of an unnamed kind says nothing about where it is` |
| ✅ | R-CH-20 | Nothing an agent's surface does for somebody it may not answer is visible or costly | `nothing of this channels is still running afterwards`, `a turn waiting behind another never starts during a shutdown` |

## Open questions

- Whether a channel may carry a clarifying question before any provider work that raises one exists.
- Whether showing work as it happens is the same decision on every surface, or each one's to make.
- Where a channel's token is kept once it has been read, given it may never arrive as an argument.
