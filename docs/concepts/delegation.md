# One agent's ask of another

A delegation is work one agent hands to another and is owed an answer for. It is not a new kind of
turn: the receiving agent gets an ordinary message on an ordinary conversation and answers it the
way it answers a person. Everything below exists to make that true without a database either agent
shares.

The verbs are [`../api/conversations.md`](../api/conversations.md) — `ask` from inside a turn hands
work over, and `asked` is what the delegator does with it afterwards.

## The row belongs to the agent that made it

There is no cross-agent database, so the `delegations` row stands in the store of the agent that
**delegated**. *"I handed this out and I am owed an answer"* is a fact about the delegator; the
agent doing the work just has an inbound message.

One rule follows, and SQLite enforces it rather than anybody's discipline:

> A gateway writes only its own agent's store. It reads other agents' stores read-only.

`agents.records.reading` opens the file `mode=ro`, so a write down that path is refused by the
engine. There is no care to be taken and no reviewer who has to notice.

The conversation the work happens in is found by a key that is **constructed, never stored** —
`('agent', '<delegator>/<parent turn>/<delegation>')` in the answering agent's database. A stored id
would be a second source of truth, and it would point into a database this one may not follow it
into.

## Two sweeps that never touch the same row

A gateway hosts three things. Delegation is the third, beside channels and schedules.

| Sweep | This agent is | Reads | Does |
|---|---|---|---|
| **Answering** | doing somebody else's work | its own store, for a delegation conversation nobody has answered in | starts a turn on it |
| **Collecting** | owed an answer | *other* agents' stores, read-only, looking for its own name in `to_agent` | delivers the last thing that agent said into the conversation the work was asked in |

One reads other agents' tables, the other reads its own, so the two directions cannot collide. Each
pass starts at most **4** and collects at most **4**: a gateway that came up to find fifty waiting
must not spend its whole first pass on them and answer nobody. The rest are still there on the next
beat.

**The answer arrives as an ordinary `rundesk` message.** That is what makes the rest free — a
message nothing has answered yet is already how a person wakes an agent, and the provider layer
already starts a turn when the agent is idle, says it into the turn already running when it is busy,
and asks again on a short bound when the brain reads nothing mid-turn.

## The depth is one, so a cycle cannot be built

An agent answering a delegation is shown no team in its instructions, and is refused if it tries
anyway. `ava → bob → ava` has no path to exist, so there is no chain to walk and no path array to
carry. What is left is two checks that read only the turn in front of them: an agent may not
delegate to itself, and a turn that is itself answering a delegation may not delegate.

A turn woken to *review* an answer is an ordinary turn and may hand out new work, subject to the
reviewing agent's current scope.

**Who is asking is read from `RUNDESK_AGENT` and `RUNDESK_RUN`, and that is a correctness guard,
not a security boundary.** A brain determined to get around it can clear a variable. What it
prevents is an honest mistake, not an attack — an agent already has the owner's shell.

## Scope has three states, and the empty one is not the missing one

`rundesk agents configure <agent> --delegate-to …` writes `delegates_to`:

| Stored | Means | Shown as |
|---|---|---|
| `NULL` | every other agent — the compatible default | `any` |
| `[]` | nobody; the agent is inbound-only | `none` |
| a JSON array | exactly those agents, in that order | the names |

One module interprets this for both prompt composition and admission, because a list shown to a
brain and a command that accepts something different would be guidance rather than a boundary. A
value that cannot be parsed **fails closed**: it is refused, never read as unrestricted.

## Why a delegation is refused

Everything refusable is refused before anything durable is written, and the row is written last — a
half-admitted delegation is the shape that leaves an agent believing it handed work over when
nothing will ever answer.

| Refusal | Because |
|---|---|
| this is not a turn | only an agent's own turn can hand work over; a person uses `ask` directly |
| the target is the agent itself | that is a turn, not a delegation |
| this turn is answering a delegation | depth is one — finish it here, or report being blocked |
| there was nothing to hand over | an empty task |
| the task is over 16,384 characters | the bound is on the task itself |
| the target is outside this agent's scope | `delegates_to` does not allow it |
| the target has no gateway running | nothing would ever answer it |

**The last one refuses only on a definite `OFFLINE`.** A gateway nobody could ask about is not the
same as one that is down, and refusing on uncertainty is the worse of the two errors — so a delegation
goes out when the answer is unknown, and is refused only when the target is known to be stopped.

## The states one can get stuck in

There is no `state` column. The two terminal outcomes are explicit timestamps, and everything else is
inferred from their absence.

| State | On disk | Gets out by |
|---|---|---|
| working | `answered_at IS NULL AND stopped_at IS NULL` | the answering turn reaching a terminal status |
| stopping | `stop_asked_at` set, neither terminal timestamp yet | the next gateway beat on the answering side |
| answered | `answered_at` set | review, or `asked resume` — which clears `answered_at` **and** `stop_asked_at`, putting it back in front of the answering gateway |
| stopped | `stopped_at` set | nothing. **Stopped work cannot be resumed**, and is never reported as `answered` |

Both terminal writes are conditional `UPDATE`s guarded on the row still being open, so a stop and an
answer racing each other settle once and the loser is told.

**There is no attempt counter, and its absence is deliberate.** The turn row is written before the
work starts and settled in a `finally` that survives the process being taken down, so a provider
that could not start still leaves a turn that reached a terminal status. Work that was admitted and
then vanished is not a state this can be in.

## When a delegation is not moving

| What you see | Usually |
|---|---|
| it stays `working` and the target never starts | the target's gateway is not running — `rundesk gateways start <agent>` |
| `stopping` for longer than a beat | the answering gateway has not had its next pass yet, or the provider process group is still going down |
| a steer seems ignored | the turn had already finished; the guidance stays for the next turn on the same delegation |
| the target answered and the delegator did not notice | the *delegator's* gateway does the collecting, so that one must be running too |

`rundesk asked show <id>` is what distinguishes the requested provider and model, the effective ones
fixed at admission, and what the target's brain actually reported.
