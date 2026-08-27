# Asking, and what was said

## ask

Ask an agent something, here, in this terminal, and watch it work.

| Command | Does |
|---|---|
| `ask <agent> <prompt> [--fresh] [--read-only] [--model <model>] [--thinking] [--quiet]` | ask, and watch it work |
| `ask <agent> <prompt> [--provider <provider>] [--alias <alias>]` | for a delegation only — which brain answers it |
| `messages <agent> [--search <words>] [--channel <channel>] [--source <kind>] [--conversation <id>] [--since <YYYY-MM-DD>] [--limit <n>] [--full]` | what was said, and what was said back |
| `turns <agent> [<turn>] [--limit <n>] [--conversation <id>]` | what each turn cost, and what one did |
| `asked [--agent <agent>]` | what this agent has handed to other agents |
| `asked show <id>` | one delegation in full |
| `asked say <id> <words>` | steer work that is still going |
| `asked stop <id>` | ask for work to end before it finishes |
| `asked resume <id> <words>` | carry a finished one on, in the session it had |

`ask` continues the agent's terminal conversation; `--fresh` starts a new one on the brain.
`--limit` defaults to 20 on both `messages` and `turns`.

```console
$ rundesk ask ava "what changed in the queue today?"
  read
    3 files changed
Nothing urgent — three merged pull requests and one rename.

20 in, 1510 out, 302567 cached, 17453 written · 9200 in the conversation  ·  turn 7
```

The attended way in: a gateway answers a channel and the clock starts a schedule, and this is a
person typing. Type while it works and the words are offered to the active brain, if that brain said
it can be steered. Messages arriving through a channel and guidance sent with `asked say` use the
same active-first rule; anything that misses or is refused stays durable for a following turn.

Tools are shown by what they **did** rather than by whatever the vendor calls them, so a `Bash`, a
`shell` and a `run_terminal_command` all read as `ran`. Prose is shown when it is finished and never
while it is being written, because a reply that rewrites itself in place is unreadable. `--thinking`
adds what it is reasoning about, which is long and off by default.

**One conversation per agent, not one per command** — asking again carries the same exchange on,
which is what a person means by asking again. `--fresh` starts a new one on the brain.

**It refuses rather than queues.** A conversation already being answered in is busy, and the claim
is the kernel's, so this competes correctly with a gateway answering the same agent on a channel
with no coordination between them.

### Run from inside a turn, it hands work over instead

**One agent asking another is a delegation, whichever verb was typed.** Typed by a person, `ask` is
what it always was. Run by an agent from inside its own turn — naming somebody other than itself —
it hands the work over and returns at once:

```console
$ rundesk ask bob "audit the exporter retention policy and report what you find"
handed to bob (claude)  ·  del-1-6c9092
  asynchronous — the result reaches this turn if active and steerable; otherwise wakes a review turn
```

An agent may select another available provider for this delegation alone, with an optional model:

```console
$ rundesk ask bob "audit the exporter" --provider codex --model gpt-5.6-sol
```

Both flags are independent delegation admission data and never configure bob. With neither, bob's
current configured provider and model are captured; `--provider` alone uses that provider and lets
it choose its default model; `--model` alone uses bob's current configured provider with that model;
and both use exactly what was requested. The effective provider must resolve to an executable
adapter before either delegation write, so a missing provider leaves no brief and no delegation row
to claim. Admission stores the requested spellings separately from the effective provider/model. A
relative provider request such as `./brain` remains visible that way while the effective provider is
stored as its resolved executable path, so another gateway cannot reinterpret it from a different
working directory.

The immediate handoff line names that effective provider, plus its account alias when one was
selected, so the terminal and channel notice agree about which brain has the work. A provider named
by path is shown by its final component rather than exposing the directories above it.

This is the front door rather than a second command, and it is not a convenience. Left alone, an
agent could run a whole turn on somebody else's agent from inside its own — no record, no guards,
and nobody owed a review. The build this replaces shipped exactly that and found every rule the
feature is made of was one command away from being bypassed.

**Nothing waits.** Bob's own gateway picks the work up and answers it as itself out of its own home
and memory. The result reaches ava's current turn if it is still running and steerable; otherwise it
wakes a review turn. What ava gets is bob's last complete message, verbatim and labelled unchecked — rundesk
summarises nothing and asserts nothing about it — and nothing bob wrote reaches any person until ava
has reviewed it.

**Six things are refused**, each with what to type instead:

| | |
|---|---|
| a person typing it | not a delegation — it is an ordinary turn on that agent |
| an agent naming itself | that is a turn, not a delegation |
| a turn already answering a delegation | work handed over cannot be handed on again |
| a target outside the asking agent's delegation scope | change that agent's scope, or keep the work here |
| an agent whose gateway is not running | nothing would ever answer it, so it says how to start one |
| a provider adapter this install cannot run, or a blank provider/model value | correct the scoped selection before anything is written |

The last is the one worth knowing about operationally: **an agent you intend to delegate to needs a
gateway running.** Its own gateway is what picks the work up, so `rundesk gateways start bob` is a
prerequisite, and launchd brings it back at every login afterwards. A delegation to an agent nothing
is running would otherwise wait for ever while the agent that made it believed it had handed work
over, which is a success nothing earned.

## asked

What this agent has handed to other agents, and the four verbs that act on one.

`rundesk asked --agent ava` lists ava's work. Inside a turn the agent is already known, so `--agent`
is needed only from a terminal.

| Verb | Acts on | What happens |
|---|---|---|
| `asked show <id>` | any | the whole delegation, in full |
| `asked say <id> <words>` | work still going | guidance is stored, then offered to the active turn |
| `asked stop <id>` | work still going | an early end is recorded, and the next gateway beat carries it out |
| `asked resume <id> <words>` | work already answered | the same ask continues, in the session it had |

**`say` never fails for being late.** The recipient's gateway offers the guidance to the active
provider turn immediately; if that turn has just ended or cannot be steered, the guidance stays for
its next turn on the same delegation.

**`stop` is not instant, and says so.** The next gateway beat stops the live provider process group,
or settles an unstarted brief as stopped without launching it. The listing reads `stopping` until
that terminal outcome comes back, then settles without waking the asking agent for another
review — and lists it as `stopped`, never `answered`. **Stopped work cannot be resumed.**

Each delegation has its own conversation, so two tasks handed to the same specialist by one parent
turn cannot share an answer.

`asked show <id>` distinguishes the requested values, the effective provider/model fixed at
admission, and the provider/model the newest terminal target turn actually recorded. The unchecked
result delivered for review distinguishes those same three sources.

**`terminal model` is what the target's brain reported and nothing else.** A model that was asked
for is not evidence of the model that ran, so a target on a provider that reports none — the shape
`antigravity` ships today — says `provider did not report one` rather than naming what it was
configured with. On a target turn taken before agent step `0013` there is only the one column that
release kept, and that value is shown because it is the best there is. `asked say`, `asked stop`, and
`asked resume` expose no provider/model flags and cannot change the selection. A resumed delegation
reuses the stored effective provider/model and its provider-specific session through gateway
restarts. A new no-override delegation captures the target's defaults again at its own admission.

**All three are shown where the person asked**, in the room the work was handed out in, as one line
of small print — *updated bob*, *asked bob to stop*, *carried on with bob*. Never the words
themselves: guidance is between two agents. Saying nothing here was what made steering invisible to
somebody watching a channel, who saw work go out and then nothing until it came back.

**`resume` starts the clock again; `say` and `stop` do not.** How long work has been out is counted
from the phase it is in, so carrying an hour-old ask on reads as *carried on with bob* and then
silence until the new work is twenty minutes old, and the answer says how long that new work took
rather than how old the ask is. The delegation keeps its id, its conversation and its provider
session throughout — resuming is the same ask continued, which is the whole difference between it
and handing the task over again.

**The depth is one.** An agent answering a delegation is shown no team in its instructions and is
refused here if it tries anyway, so `ava → bob → ava` has no path to exist and there is no chain to
walk. A turn woken to *review* an answer is an ordinary turn and may hand out new work, subject to
the reviewing agent's current delegation scope.

## messages

What an agent has been told, and what it said back.

**The agent is the first caller of this, before its owner is.** A person refers to work the agent has
no record of — *"the invoice bug you looked at last week"* — and the agent reads its own history back
before answering rather than saying it does not know. Its own instructions name this command for
exactly that.

```console
$ rundesk messages ava --search invoice
2 ava said or was told holding 'invoice'
WHEN                  WHO   WHERE            IN  SAID
2026-08-06T13:11:29Z  user  discord 9930-ops  2   [invoice] again, different room
2026-08-06T13:11:29Z  user  discord dm-4471   1   the [invoice] bug is in the parser
```

One bounded line each, because every line the agent reads costs tokens and a listing that answered
with fifty whole messages would spend a turn's budget on finding out what the turn was about.
`--full` prints bodies. `IN` is the conversation, which is what `--conversation` takes.

**`WHERE` says what carried it *and* which exchange on that thing**, and the second half is not
decoration. A private message and a public room are both `discord`, and two schedules are both
`schedule` — so an agent reading its own history back could not tell what it had been told in
confidence from what it had said in front of a room, and one asked *how did the client update go*
got a listing in which nothing said which schedule any line came from. The second word is the
platform's own name for the place, or the schedule's own name, and it is what
`rundesk schedules show` is typed with.

Four ways to narrow and they compose: `--search` for words, `--channel` for where it was said,
`--source` for what kind of thing started it, `--conversation` for one exchange, and `--since` for a
day. With no words at all it is the conversation read back, newest first.

**`--search` takes words, and only words.** Whatever you type is matched as the words themselves, so
`C++`, `it's fine` and `50%` all mean what they look like. There is no query syntax to learn and none
to get wrong: `AND` is the word *and*, a bare `"` is a quote mark, and several words means a message
holding all of them. This is why there are no operators — the alternative was a search that answered
an apostrophe with an error about the agent's records.

**An empty answer says what was looked for**, so "nothing matched" is readable apart from "you
narrowed it to nothing":

```console
$ rundesk messages ava --search invoice --channel nowhere
nothing ava said or was told holding 'invoice', on nowhere
```

**Where an install has no full-text index it says so.** SQLite is not always built with one; the
search then falls back to matching plain text, which finds different things — no stemming, no phrase,
no ranking — and somebody comparing two answers has to know which they got.

## turns

Every turn an agent has taken, what each cost, and what one actually did.

`rundesk messages` is what was *said*; this is what it *cost* and what became of it. Two different
questions, kept apart because they are read for different reasons and answered from different tables.

```console
$ rundesk turns ava
turns ava has taken, newest first
TURN  WHEN                  WAS   IN  COST                           UNKNOWN  LOST  UNSENT
2     2026-08-06T13:39:13Z  done  2   20in 1510out 302567cr 17453cw  0        0     0
1     2026-08-06T13:38:14Z  done  1   20in 1510out 302567cr 17453cw  0        0     0
```

The four billed quantities are shown apart because they are billed at three different rates — fresh
input, cache reads and cache writes — and a single total would be a number that is real and
misleading. **A dash is not a zero**: it means nobody reported one, and a cost nobody measured and a
cost of nothing are different answers.

**`UNKNOWN` and `LOST` are how a vendor moving under you becomes visible.** The first counts records
this release did not understand and the second records that never arrived. Both are zero on a healthy
turn; both climbing means an adapter and its brain have drifted apart, and nothing else in the product
will tell you before somebody notices an agent behaving oddly.

**`UNSENT` is the other direction and is not that signal.** It counts words rundesk could not put
*into* a turn — usually somebody steering a brain that had already finished, an ordinary race whose
words stay durable for the next turn. It shared the `LOST` column until agent step `0013`, so a
person typing one word too late looked exactly like an adapter coming apart.

With a turn as well, it shows that one whole: what it was admitted with, what the adapter said it
could do, every record in the order it happened, what it came to — and, where it did not answer,
whether waiting will help or whether somebody has to act.

**`model asked for` and `model reported` are two facts.** The first is what the turn was admitted
with — the model asked for, or the agent's configured one — and the second is what the brain said
actually ran. `provider default` means no model was selected and the provider chose; a dash under
`model reported` means the brain named none, which is not the same as none having been chosen. A
turn taken before agent step `0013` shows a single `model` line instead, saying that the one value
it has may be either: that release kept both in one column and nothing can now say which it holds.
