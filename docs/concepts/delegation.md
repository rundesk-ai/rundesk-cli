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

A third pass stands on the collecting side: an answer already recorded that no turn has read is
offered for review again. It settles nothing — see
[the states one can get stuck in](#the-states-one-can-get-stuck-in) for why an answer is durable
before it is read — and it is bounded twice, because the two costs are different:

| Bound | What it holds |
|---|---|
| **32** read | the rows one pass reads to find candidates, as one indexed seek |
| **2** taken | the candidates it hands to the sweep, and so the delegation rows it reads |
| **2** tried | the answers it then acts on — another store read, a turn, a log line — spent by an attempt whether or not it succeeds |

**The walk moves by what it handed over.** Work carried on, stopped or forgotten keeps its recorded
result for as long as the history does; so does one whose target cannot be read, and one whose
review will not start. The oldest end is where all of those collect, so the position has to leave
them behind whatever became of them — read, passed over as busy, refused. It follows the last
candidate a pass was given, or the end of what that pass read when it was given none.

**A pass that reads nothing after the position is the only thing that begins it again.** A look with
room to spare is not the end of anything: it can still have rows behind the two it handed over, and
starting again at the head there is how two answers nothing can use hold everything behind them for
ever — which is what this arrangement is for.

An answer behind *n* unusable candidates therefore waits ⌈n/2⌉ beats rather than never. That
position is the gateway process's and is not written down — a replacement starts at the oldest end,
which costs a walk and loses nothing.

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

**A result is settled once it is durably the asking agent's, and not once a turn has read it.** The
two are the same moment whenever that agent is free. They are not when it is already running a turn
nothing can speak to — a scheduled run is a process of its own, so the registry a steer needs is not
the gateway's — and waiting for the review before settling left the delegation `working` for as long
as that turn ran, which never ended when the turn was itself waiting on this delegation. What is
still owed is the review, and the third pass is what offers it again: it takes each delegation's
**newest** recorded result that no turn has claimed — an earlier phase's is what the agent has
already been told — passes over a conversation with a turn in it, passes over stopped, carried-on
and forgotten work, and offers each the same message until one turn takes it.

A result a turn has already claimed stays that turn's. The claim is written just before the provider
accepts it, so a gateway can end between those writes. While the claiming turn remains `working`,
collection leaves the claim alone because that turn may still admit it. Once the claiming turn is
terminal without the admission record, the next collection pass releases that exact claim and starts
the ordinary fallback review turn. The result's stable external id reuses the same message rather
than delivering another copy, and the claim on that one row is what makes however many offers one
review.

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
| the result was claimed just before the delegator's turn ended | the next collecting pass releases the terminal unadmitted claim and starts one fallback review turn |
| it says `answered` and no review turn has run | the delegator is busy with a turn nothing can speak to; the answer is recorded and readable, and the next free pass reviews it |

`rundesk asked show <id>` is what distinguishes the requested provider and model, the effective ones
fixed at admission, and what the target's brain actually reported.
