---
id: DEL
name: One agent's ask of another, and the answer it returns
---

## What this is

A delegation is one bounded task a named agent hands to another named agent on this
install. The agent it is handed to answers it once as itself — its own home, memory,
skills and brain — and that single answer is delivered back into the asking agent's own
conversation for review. The asking agent reviews it and answers the person who asked.

## Why it exists

- An agent can hand work to a colleague that genuinely knows something it does not.
- Neither agent loses what it is: the one answering is itself, not an execution of a role.
- No unreviewed work reaches the person who asked for it.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-DEL-1 | A delegation is one bounded task one named agent hands another on this install, answered once | `an ask is written whole and read back`, `a claim moves one ask and leaves the rest`, `an agent with no brain is refused at admission`, `a gateway is handed everything it does about delegations`, `an ask is waiting for the agent it was handed to and for nobody else`, `a gateway carries every ask addressed to it that it finds`, `a backup holds a delegation that has not been collected` |
| ✅ | R-DEL-2 | An answering agent keeps its whole identity: its home, its memory, its skills, its brain | `carrying an ask asks the answering agents own brain`, `the preface is rundesks standing rules and the delegation layer`, `a delegation run still receives rundesks own standing rules first`, `a turn carrying a delegation names it in the environment the adapter is given` |
| ✅ | R-DEL-3 | A delegation is admitted only by a turn belonging to the agent asking, still in flight | `a turn that has already ended is not a turn that can delegate`, `a role execution cannot hand work to an agent`, `a delegation is asked for by this agents own turn`, `a delegation needs a turn of this agents own`, `a role execution cannot hand work to a named agent` |
| ✅ | R-DEL-4 | A turn on no surface the asking agent is reachable on cannot delegate | `a turn on no surface the agent is reachable on cannot delegate`, `a conversation on a channel this agent has is one it can be reached on`, `a conversation on a surface that joins no channel is not reachable` |
| ✅ | R-DEL-5 | A delegation turn happens in a conversation of its own, never one a person is typing into | `the answer is asked in a conversation keyed by the caller and the calling run`, `the ways work is admitted are exactly these five in this order`, `two asks in one conversation are carried one at a time` |
| ✅ | R-DEL-6 | A delegation turn is told the requester is an agent, nobody is present, and to report blocked | `a delegation run is told the agent that handed the work over`, `a delegation run is told nobody is present and never to ask`, `a delegation run is told its answer goes to no channel`, `delegation instructions apply only to delegation triggers` |
| ✅ | R-DEL-7 | A delegation never widens the authority the asking turn had, and may narrow it | `an ask never widens the authority its parent turn had`, `an ask may still narrow it`, `work admitted by a turn that may only look may only look`, `work asking only to look looks however much its parent could do`, `work admitted by a working turn that wants to work may work` |
| ✅ | R-DEL-8 | An agent already in the delegation chain is refused, and an agent reached by delegation cannot delegate | `an agent already in the chain is refused`, `an agent reached by delegation may not delegate onward`, `an agent cannot hand work to itself`, `an agent reached by delegation cannot hand work on` |
| ✅ | R-DEL-9 | An agent answering a delegation cannot start a role run from that turn | `work handed over by another agent cannot be handed on to a role`, `a delegation run is told it may not hand the work on`, `a delegation turn is offered no roles`, `a delegation run offered no roles is given no roles heading`, `a turn answering another agent is told which delegation` |
| ✅ | R-DEL-10 | Only the last complete message a delegation turn writes is returned to the agent that asked | `only the final message of a delegation turn is returned`, `an ask that answered is settled with the words the brain said` |
| ✅ | R-DEL-11 | Every settled delegation owes the asking agent exactly one review, delivered once | `a collected ask stops being owed`, `an ask that answered nothing is settled failed rather than answered`, `an answer is owed to the agent that asked until it is collected`, `a delegated answer wakes the asking agent to review it`, `a delegated answer is left owing when the room is already busy`, `a review that answered marks the delegated answer collected`, `a review that answered nobody leaves the delegated answer owed`, `the delegation review turn is asked as a prompt that stands on its own`, `an answer is delivered once and stops being owed`, `an answer is left owing while the surface is down`, `an answer is left owing when the room is already busy`, `a busy asker adds nothing to the attempt count`, `an undeliverable answer never holds up the ones behind it` |
| ✅ | R-DEL-12 | An answer that cannot be reviewed after a bounded number of attempts is settled and the owner told | `an answer at the ceiling is written off and the owner told`, `an answer nobody could review stops being owed when it is given up on`, `the undeliverable notice repeats no word of the answer` |
| ✅ | R-DEL-13 | A delegation nothing answered inside its window is settled and the asking agent told | `an ask nothing answered inside the window is left alone`, `an ask past the window is settled undeliverable`, `a settled ask past retention is taken away`, `the sweep settles what went unanswered and clears what expired`, `a gateway with no agent behind it sweeps no delegations` |
| ✅ | R-DEL-14 | Rundesk records an answering agent's words and asserts nothing read out of them | `an ask that answered is settled with the words the brain said`, `an answer longer than the ceiling keeps its tail`, `nothing of a delegated answer is read out or summarised`, `a delegated answer is never posted where a person can read it` |
| ✅ | R-DEL-15 | What a delegation shows a person carries no local path and no brief | `what a delegation shows carries no local path and no brief`, `a label carrying a path is never written down as one`, `a listing shows no local path and no task`, `a delegation this agent never handed over is no delegation of its own`, `a delegation record carries no task and no answer`, `the agents name comes out through the shared guard`, `nothing handed to another agent says so rather than answering with nothing`, `what is asked of another agent says who the task and how long` |
| ✅ | R-DEL-16 | Handing work to an agent, its progress and its outcome are shown where the person asked | `handing work to an agent is shown where the person asked`, `a delegation still working is edited in place rather than repeated`, `a delegation still working says who and how long`, `an answer that came back says the agent answered`, `a delegation that failed is shown as a fault`, `a delegation record is shown whether or not activity is on`, `the answering agents own room is told nothing`, `where an ask is shown is the room the person asked in`, `an ask past its window says which check in it has reached`, `an ask still being answered says so once per window`, `an ask this gateway is not carrying is never checked in on`, `a delegation that could not be carried still says how it went`, `a surface that cannot be told never holds up the work`, `two asks in one conversation never share a check in`, `an ask that settled stops being checked in on` |
| ✅ | R-DEL-17 | A delegation record carries everything a surface needs to render it, correlated against nothing earlier | `a record this adapter does not understand renders nothing`, `a state this surface does not know shows nothing`, `a settled record from a rundesk that names no ending still renders`, `a settled record carrying no elapsed renders with no dangling dash`, `nothing stops a delegation so no record ever says one was`, `a role task and a delegation are never the same mark` |

## Open questions

- Nothing tells an asking agent which agents this install has, or what each is for: there is
  no description on an agent as there is on a role, so an agent learns the verb from
  `rundesk --help` and the names from nowhere.
- Whether the four windows should be configurable per install, as a role run's quiet hours
  already are, rather than staying module constants.
- Whether a turn woken to review a delegated answer should be able to delegate again. It is
  legal today; the role path refuses the analogue outright.
- Whether an answering agent should run a delegation turn while already answering somebody
  on a channel. It may today, and two concurrent turns can both write its `MEMORY.md`.
