---
id: CH
name: A channel, and the work that arrives on it
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
| ❌ | R-CH-1 | A channel dispatches what arrives on it as work for the agent it belongs to | — |
| ❌ | R-CH-2 | A channel belongs to exactly one agent | — |
| ❌ | R-CH-3 | Each conversation on a channel keeps a provider session of its own | — |
| ❌ | R-CH-4 | A message from anyone the channel does not authorize is never dispatched | — |
| ❌ | R-CH-5 | What a message says cannot change which agent, provider or model answers it | — |
| ❌ | R-CH-6 | A channel shows what an agent is doing while its turn is still running | — |
| ❌ | R-CH-7 | A channel shows only whole units of an agent's output, never a part-written one | — |
| ❌ | R-CH-8 | A channel gives an agent's answer whole, once the turn has ended | — |
| ❌ | R-CH-9 | A person can stop the turn running in their own conversation | — |
| ❌ | R-CH-10 | A person can forget their conversation's session, so the next message starts a new one | — |
| ❌ | R-CH-11 | A channel leaves nothing running once the turn it belonged to has ended | — |
| ❌ | R-CH-12 | A failure to deliver on a channel does not end the turn it was reporting | — |
| ❌ | R-CH-13 | Raw tool arguments and results do not leave the machine unless a rule allows them | — |
| ❌ | R-CH-14 | A conversation's session is found again after the gateway holding it restarted | — |
| ❌ | R-CH-15 | Work a channel dispatched is findable afterwards by the run it became | — |
| ❌ | R-CH-16 | A person can restart the agent answering them, from the channel they are on | — |
| ❌ | R-CH-17 | What a person attached reaches the agent as a file already on this machine | — |

## Open questions

- Whether a channel may carry a clarifying question before any provider work that raises one exists.
- Whether showing work as it happens is the same decision on every surface, or each one's to make.
- Where a channel's token is kept once it has been read, given it may never arrive as an argument.
