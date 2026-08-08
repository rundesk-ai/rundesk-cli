# Research: the previous build's provider system, end to end

**Established 2026-08-05**, by reading `src_old/rundesk/{provider,process,turn,instructions,answering}.py`
and `src_old/providers/{claude,codex,grok,antigravity}` — all gitignored, reference-only and expected to
be deleted. Everything here is read off that code and its own docstrings. Where a line says a thing
*happened*, that build recorded it happening; where it says a thing was *designed*, the code says so and
nobody claimed it was ever proven.

[`the-adapter-contracts.md`](the-adapter-contracts.md) is the **contract** — what an adapter had to do,
reproduced exactly. This page is the other half: **what stood behind the contract**, how it was cut into
modules, and what each module cost to get right. The contract is what a stranger read; this is what the
product had to be.

[`the-old-build.md`](the-old-build.md) says in one paragraph what a provider *was*. This says what the
system around it was.

---

## The short version

Six modules, and the cut between them is the thing worth carrying:

| Module | Lines | What it owned | What it deliberately did not know |
|---|--:|---|---|
| `provider.py` | 439 | the seam — the closed vocabularies, the environment a turn is described in, resolving a name to a program | any vendor, any model, any flag |
| `process.py` | 1207 | running a program and keeping hold of it: framing, bounds, signals, backpressure | what the program is for |
| `turn.py` | 1124 | one turn: resolve → record → run → record → settle | how a turn was asked for |
| `instructions.py` | 348 | what a brain reads before it reads the task | which brain, and how it is delivered |
| `answering.py` | 1668 | a message on a surface carried through to an answer | what a brain is |
| `src/providers/*` | 3368 | one vendor each, as **programs** | anything of rundesk's |

**No core module made a decision on a vendor's name.** Grep-checkable, and it held: across
`src_old/rundesk/`, the four vendor names appear only in **docstrings** (explaining why a rule exists —
`turn.py:892` on `grok` and `antigravity` never marking a thought finished) and in **help-text examples**
(`cli.py:136`, `rundesk add ava --provider codex`). Not one of them is read, compared, or branched on. The
whole of what each vendor needed — flags, stream shape, usage arithmetic, session files, permission model, skill
directory — lived in one executable file per vendor, importing nothing.

**The seam was proved once, by accident, and it is the strongest evidence on this page.** Codex was moved
from `codex exec` to `codex app-server` — a completely different transport, gaining the `steer` capability
in the process — and it changed **one file**. Nothing under `src_old/rundesk/` moved.

---

## 1 · The seam: `provider.py`

### An adapter is a program, never code

```python
stands = Path(named) if (os.sep in named or named.startswith("~")) else ADAPTERS / named
```

That is the entire resolution rule. A bare name resolves among the shipped adapters; anything with a path
separator is used as a path. `codex` and `/opt/my-brain` are the same kind of thing, and one of them
merely happens to live in the repository. `ADAPTERS` is read **by looking at a directory**, never listed,
so an adapter added later is reachable the day it lands.

Three consequences the docstring states out loud:

- rundesk never puts a stranger's code inside the gateway that runs every other agent;
- an adapter can be written in anything (the reference smallest adapter is 14 lines of bash);
- **a brain nobody has heard of is the ordinary case rather than an error.** The only failure is
  `NotRunnable` — nothing runnable is at that path.

### Four closed vocabularies, and being closed is the feature

```python
RECORDS      = ("text", "think", "tool", "result", "usage", "file", "limit", "done")
DID          = ("read","search","run","edit","list","make","delegate","memory","rules","identity")
CAPABILITIES = ("tools", "resume", "model", "usage", "steer")
POSTURES     = ("read", "work")
BECAUSE      = ("rate_limited","usage_exhausted","no_credit","signed_out",
                "context_exceeded","cancelled","refused","crashed")   # in turn.py
```

The reasoning, verbatim from the code: *"An open vocabulary would put every vendor's words into every
channel and every reader, which is the thing this seam exists to prevent."* `did` is the sharpest case —
the same action is `Bash` on one brain, `shell` on the next and `run_terminal_command` on a third, and a
surface that recognised any of them would carry that vendor's vocabulary forever.

**And being closed is exactly what made forward compatibility cheap.** `understood()` returns `None` for a
line it cannot read, a line that is not an object, and a line of a kind it has never heard of — all three
the same way, meaning *keep it, show it to nobody*. The raw line is kept regardless. So an adapter can be
ahead of the core without waiting for a release, and an upstream format change shows up as **visible
drift** rather than as records quietly going missing.

Two record kinds were added late and each for the same shape of reason — *a brain plainly does this and
the seam had nowhere to put it*:

- **`file`**, because a brain generated a picture, said "here it is", and there was no way to tell anybody
  a file existed. Inferring it from what a tool printed was the alternative and would have meant sending
  anything a brain happened to name.
- **`limit`**, because brains report account state — how much of an allowance is left, when the window
  resets — and a turn stopped by one reached an owner as whatever prose an adapter scraped off a failure
  line. It is deliberately a *record* and not an outcome: **a turn carrying one may have succeeded.**

### Capabilities are asked, never guessed — and only one of them changes how a turn runs

`--capabilities`, one JSON object, exit 0. Absent means no, so `{}` is a complete and honest answer. The
docstring is emphatic that this is not a defect: *"the smallest legitimate adapter in the guide is a shell
script that answers a prompt, and telling its author their brain is broken for not knowing this flag would
be wrong."*

Four of the five only decide what is *recorded*. **`steer` decides how the turn is run**, and it is
declared rather than attempted for a stated reason: an adapter that cannot be sent to mid-turn has its
input closed after the prompt, because *holding input open for a brain that will never read again is a
turn that never ends.*

Two numbers guard the asking, and the second is the interesting one:

| | | Why |
|---|--:|---|
| `ASKING_SILENCE_SECONDS` | 60 | a question whose answer the adapter already knows, asked offline |
| `ASKING_CEILING_SECONDS` | 300 | **this is the one place rundesk runs an unvetted program before a turn is admitted.** Without a backstop a chatty or broken adapter hangs every `rundesk ask` with nothing written down |

It is also deliberately **not** part of diagnosing an agent: diagnosis answers *could this work at all*
without starting anything, and asking capabilities starts a program.

### The environment is the whole interface, and nothing is a vendor variable

`environment()` builds every variable a turn is described in. What is *not* there is as deliberate as what
is: **no vendor variable at all**, because which one a brain wants is that brain's adapter's business and
putting it here would put the vendor in the core.

Three rules the code enforces rather than documents:

1. **Anything left out is left unset rather than set to nothing.** An adapter asked to work with a model
   called empty-string does something odd with it; one told nothing falls back to its own default.
2. **`RUNDESK_SETTINGS` is written sorted**, so the same settings are the same bytes every run and one
   transcript can be compared with another.
3. **The owner's own values may never take a name rundesk decided.** `process.told()` merges by
   `if name not in said` — *whatever rundesk just decided a program is told is exactly what a value may
   not be called* — so the rule cannot come apart from the builder as the builder grows.

Two variables exist purely so an adapter does not hold a copy of rundesk's layout:

- `RUNDESK_SKILLS` — *where* this agent's skills stand. **Which brain looks where is the adapter's**, and
  it has to be, because the three shipped brains read three different directories
  ([`2026-07-27-skills-a-brain-discovers.md`](2026-07-27-skills-a-brain-discovers.md)).
- `RUNDESK_CONTINUITY` — `AGENTS.md=rules,MEMORY.md=memory,SOUL.md=identity`. An adapter that carried
  those four names would silently stop reporting them the day one was renamed here.

### Steering is a record, and it carries rundesk's own words apart from the person's

```python
{"type": "say", "text": "...", "context": STEERING_CONTEXT}
```

`STEERING_CONTEXT` is a fixed sentence telling the brain this is mid-turn guidance inside the original
request. It is carried **beside** the person's text rather than concatenated into it, so a
replacement-style transport can apply it without changing the person's recorded words. Hermes reached the
same conclusion from the opposite direction and it cost them a defect — see
[the companion page](2026-08-05-how-other-gateways-run-a-provider.md).

---

## 2 · Running the program: `process.py`

The largest and most-scarred file in the set. Five facts about what these programs *are* shaped all of it,
and every one of them is a property of agent CLIs specifically: **sessions that run for hours, say a great
deal, start programs of their own, run many at a time, and are talked to rather than merely watched.**

### Silence is the failure, never duration

```python
SILENCE_SECONDS = 1800.0        # half an hour of saying nothing
CEILING_SECONDS = 48 * 3600.0   # the backstop, not the instrument
```

*"A session may legitimately run for hours, so a clock that ends it is a clock that ends real work. What a
wedged program does is go quiet, so that is what is measured."* The ceiling exists only because **silence
cannot see a program wedged in a loop that keeps announcing itself.**

Silence is measured from the last thing said on **either** stream. Counted on stdout alone, a provider
working steadily and reporting only diagnostics goes quiet by that measure while it is plainly busy.

### The five things that were got wrong at least once

Each of these is written into the code as a paragraph explaining a real failure:

**A program's own session, and the group is what gets signalled.** `start_new_session=True`, and
`os.killpg` — because a brain runs editors, search tools and language servers, and signalling only the
child we can see leaves every one of them behind. `_signal_group` returns False **only** for
`ProcessLookupError` (the group is empty); `PermissionError` returns True, because *being unable to reach a
group that is still there is not the same as there being nothing there* — treating them alike meant one
failed signal ended the whole escalation, so a program that could not be asked politely was never asked
firmly either, and `end()` returned as though it had worked.

**Waiting on exit resolves only when every pipe is closed too.** A program rundesk talks to has three of
them, and anything it left running is holding one — so the exit would land hours late or never. Everything
asks `returncode` on a poll instead. Related: after the pipe closes, *the pipe closing is not the program
dying* — anything that daemonises reaches the end alive, and waiting on it unbounded is a wedge that
nothing recovers from, because the silence window is already spent.

**The drain is a deadline, not a per-read timeout.** Spent per read, a child that inherited the pipe and
keeps writing more often than the drain allows completes every read and the loop goes round again forever
— *"the wait ran on to the 48-hour ceiling, holding the name against a restart of that work for two days.
Anything talkative does it: a dev server, a language server, a log being followed."*

**A slow receiver must not be able to hold the program up, and its patience is not the drain's.** Between
the reading and the receiving sits `Held`, a bounded queue that never waits and never raises — *handed
straight to a receiver, a slow one stops the reading, and for a program rundesk also writes to that is a
deadlock: the program blocks writing what nobody is reading, so it never reads what we are writing.* The
two waits were once one constant at two seconds, and *"a receiver spending a fifth of a second on a record,
which a rate-limited channel post easily does, got nine of fifty and the run still reported that it had
finished."* They are now `DRAIN_SECONDS = 2` and `RECEIVING_SECONDS = 30`.

**One writer at a time, across write *and* drain.** On the oldest supported Python the transport holds a
single waiter and asserts nobody else is there, so two records offered close together — two channel
messages, or an answer racing a queued message, *which is this product's ordinary case* — raised
`AssertionError` at the second caller. With assertions off the second waiter simply replaced the first,
which is a permanent hang rather than an error.

### Loss is reported where it happened, never counted at the end

```python
@dataclass(frozen=True)
class Gap:
    records: int
    why: str        # "too large" | "unterminated" | "fell behind" | "not taken" | "never delivered"
```

A `Gap` is handed to the receiver **in the position the loss happened**. *"A count says something was lost;
a gap says where, and where is what decides whether what surrounds it can still be made sense of. Records
are not independent — text arrives in pieces meant to be joined — so a hole nobody is told about is not
less of an answer, it is a wrong one."*

And `Result.ok` requires both: finished **and** everything handed over. *"Fifty records written, nine
received and `ok` — which is what this said before — is the reading that misleads most."*

### Bounds are in bytes, and never on a `deque(maxlen=…)`

Counting items bounds nothing when one item may be megabytes: 200 records at the record cap is most of a
gigabyte per stream per conversation. And the eviction is done by hand rather than by the deque, because
*"a deque that evicts on its own does it silently — the count stayed right while the byte total kept
climbing past what was actually held, until it exceeded the bound on its own and started throwing away the
newest lines to chase a number that had nothing behind it. The tail this exists to preserve collapsed to
one line."*

### Two framings, one loop

| | for output meant to be **read** | for output meant to be **parsed** |
|---|---|---|
| unit | a line of text | whole bytes, or nothing |
| oversize | pass on what is held and carry on | **drop the record**, resync at the next newline, say so |
| decoding | incremental UTF-8, `replace` | none — a `?` where a byte was is indistinguishable from one the program meant |
| a receiver raising | takes the program with it | counted, retried, never fatal |
| streams | folded together (order is what matters) | kept apart (anything not part of the structure corrupts it) |

Folding stderr into a parsed stream is **refused rather than obliged**: *"the records would be corrupted by
exactly the warning that explains why, and nothing downstream could tell that apart from the program
talking nonsense."* And stderr is drained **unconditionally** whether or not anyone wants it, because a
pipe nobody reads fills, and a program blocked writing to a full pipe stops reading what we write to it —
*"a deadlock that presents half an hour later as a perfectly healthy program having gone quiet."*

---

## 3 · One turn: `turn.py`

The only module that knows the others exist, and the whole of what it does:

```
resolve -> write down what was resolved -> run the brain -> write down what it said
        -> keep where the conversation got to -> write down how it ended
```

### Three invariants stated as rules

**What a turn resolved is written when it is admitted and never changed after.** A binding is not
something anybody maintains: it is whatever this turn was asked for plus what the agent supplies for what
was left out, settled once and recorded.

**Nothing is sent that the account does not show.** Everything reaching a brain — the prompt, and anything
rundesk ever adds to it — is a record in the run *before* the brain is started. *"Injecting text a person
never wrote and leaving it out of the audit makes the audit a lie, and it is invisible precisely because it
**is** the audit."*

**A run that was begun is settled, whatever happens next.** The path this exists for cannot be caught by
the body it wraps: a gateway standing down cancels the turn, and a cancellation unwinds straight past the
`ended` on the happy path — so a run that had been admitted stayed `running` in an owner's records for
ever, `rundesk runs` showed a turn in flight that nothing was doing, and no restart cleared it because
nothing afterwards knew it had been begun. Fixed with a context manager entered *outside* the account
writer, settling exactly once via a shared list.

### The seven readings taken off what a brain said

Every one of these is a small function, and each exists because a plausible-looking simpler version was
wrong:

| Reading | The trap it avoids |
|---|---|
| `_ended` | `done.ok` is what the **brain** made of the turn; the exit code is what became of the **program**. A brain that answered "no" through a process that exited zero is a failed turn |
| `_answered` | *a program exiting well is not an answer.* Measured: a resumed session reported `done ok:true` with four zero usage counters 14 ms in and said nothing at all — the run was written `finished`, the question was marked answered, and nothing had happened to it |
| `_because` | a word from a **newer** rundesk is dropped rather than stored, because the whole value of a closed set is that a reader can exhaust it |
| `_tokens` | only what was actually reported. A brain that cannot tell fresh from cached omits `cached`, and summing that into nothing says it read nothing from the cache. `session` is a **level**, not a quantity — the last one wins, never the sum, because it goes *down* on compaction |
| `_thoughts` | a finished thought ends a paragraph and a fragment does not, or an account reads back `caught it running.The worker` |
| `_close` | *decided after the turn is over, which is the only moment it is a fact* — a brain cannot mark its own final message, because only not calling another tool makes it the last |
| `_never_ran` | five conditions, all required, because *the cost of being wrong is a brain asked to do the same work twice* |

Two of these deserve their own paragraph.

**`_thoughts` had to work for brains that never mark anything.** `whole` is not a seam every adapter has:
`grok` refuses it on purpose (it writes a token at a time and nothing restates it) and `antigravity` streams
deltas. Read on `whole` alone, every turn either of them takes is one thought. So the split *also* breaks
where the brain **went to work** — `tool` or `result` — because a thought said before further tool calls is
working narration. That makes the split defined for every shipped adapter.

**`_never_ran` and the retry it authorises.** Measured twice in 82 minutes on a live gateway: a resumed
session's first record was a notification left over from the *previous* session, and it ended the turn 14 ms
later reporting `ok` with nothing said. Two real questions were consumed, each answered with an activity
mark and silence. The fix asks again **once, on a fresh session** — but only when the prompt
`stands_alone`, because *most* of what rundesk writes into a turn is a continuation ("carry on where the
last gateway stopped") that means nothing without the session it was written for. Asked fresh, the brain
answers about nothing, the turn records `finished`, and the handle the retry ends on **replaces the
interrupted conversation's own — which is the work itself going.**

### The account, and what is a message versus what is a record

`_Account` splits one stream two ways: **what was said is a message** (in the conversation, searchable,
written whole at the end) and **what happened is a record** (`seq`-ordered, append-only, never rewritten).
`seq` is a total order that does not depend on a clock, so an account still reads in the order the work
happened on a machine whose clock went backwards.

A reply is *gathered*, not recorded per fragment: *"a row per fragment is a history nobody can read back
and a search that matches half a sentence."*

And what the brain itself printed is **not** in the account at all — it goes to a file beside the log,
because *that file may be destroyed, so nothing a run recorded is recoverable only from it.*

---

## 4 · What a brain reads first: `instructions.py`

Fully distilled already in [`instruction-layers.md`](instruction-layers.md). The three things that matter
to a rebuild of the provider layer:

**One composer, one core, exactly one layer naming who asked.** `CORE` → one of `USER_TO_AGENT` /
`AGENT_TO_AGENT` / `SCHEDULE_TO_AGENT` / `AGENT_TO_ROLE`, then whatever the caller appends in order.

**The core carries no identity, and that is the rule the whole shape rests on** — because the role layer
receives the core and a role execution has no home, no memory, no voice. It is asserted by a test that
*searches the built string* for each forbidden thing, never by reading the composition back.

**It reaches the adapter as one variable and never as a flag.** `RUNDESK_PREFACE`, mapped by each adapter
onto whatever its brain has for *adding* to instructions. The contract's warning is the load-bearing one:
*never map it to anything that replaces the system prompt* — measured on Claude, `--system-prompt` takes
about 6,100 tokens of the brain's own instructions with it, nothing reports that, the tools keep working,
and the turn merely behaves differently, which is the failure mode that gets blamed on the model.

Substitution is by hand (`str.replace`) and never `str.format`, because owner text arrives with braces in
it eventually and `str.format` raises mid-turn when it does.

---

## 5 · What the four shipped adapters actually absorbed

Each is one executable file, no `.py`, importing nothing of rundesk's. The interesting thing is **how much
per-vendor knowledge the seam successfully kept out of the core** — this is the list of things that would
otherwise have been in it:

| | claude (1251 ln) | codex (893 ln) | grok (736 ln) | antigravity (488 ln) |
|---|---|---|---|---|
| transport | `-p --output-format stream-json --verbose --include-partial-messages` | `codex app-server` JSON-RPC over stdio | `grok agent stdio` (ACP) | `agy --output-format stream-json`, prompt piped |
| `steer` | **yes** — `control_request: interrupt`, drain, then the new user message on the same session | **yes** — `turn/steer` with `expectedTurnId` as a precondition | not measured | no |
| resume | `--session-id` (**caller mints it**, so the handle exists before the first byte) | `thread/resume` | `--resume`, plus `--no-memory` or it answers from other sessions | `--conversation`; an unknown id **silently starts a new one** |
| usage | per-turn, but read off `result` only — `message_start` and `message_delta` carry full blocks too, and counting them triples the cost | **cumulative** — must be subtracted, and what you subtract from lives in the adapter's own home keyed by session | per-turn | per-turn when fresh, **cumulative when resumed** |
| model | named on `system/init` | **nothing names one** — claims `model: false` | first key of `end.modelUsage` | `init.model` |
| posture | the allowlist is a **pre-approval** list, not the tool list; the vendor's permission system is what refuses | `--sandbox` / `SandboxPolicy`, both spellings hold | the `--tools` list on one-shot; `_meta.agentProfile` on ACP — and `--tools` is **accepted in silence and inert** there | `--sandbox` is OS containment; `--mode plan` is not a boundary |
| home | `CLAUDE_CONFIG_DIR` — **removes** the login rather than redirecting it; keyed on `USER`, so a built environment with `USER` unset reads as logged out on a signed-in machine | `CODEX_HOME`, a plain `auth.json` | `GROK_HOME`, fails closed with the command to run | OS keyring, **no documented override at all** |

Two rows are the ones a core would have got wrong:

- **The reply arrives three times on Claude** and two of the copies are byte-identical. Reporting both
  reports every answer twice, and the turn looks correct while saying everything twice.
- **`thought` and `text` on grok are one field apart** — same `{"type","data"}` shape. Anything scanning
  raw lines for `data` publishes what the model merely considered.

Neither is a fact any generic core could hold correctly, and neither ever entered one.

---

## 6 · Every provider-side incident recorded

Beyond the ones already stated above.

**Locations and secrets.** `RUNDESK_DATA_DIR` did not isolate a scratch install when *an agent* was doing
the work, because a gateway exported `RUNDESK_AGENTS_DIR` into every turn and it won. This build's single
root makes that unexpressible; the shape to remember is that **a turn's environment is a second place a
location can leak from.**

**A gateway holds the module it imported when it started.** Editing a module and restarting the *adapter*
is not enough — the adapter is a fresh process each time and the gateway is not. An attachment downloaded
correctly by a new adapter was dropped by an old seam, *"which reads exactly like the adapter being
broken."*

**A turn a schedule asked for is not in `running`.** Taking that for "nothing left" reported a clean stop,
exit zero and "down", while a brain was still working.

**`_held()` answers about the moment it was called.** Between that answer and a signal, a gateway of that
name can claim the name and start work — so an ordinary `start` ended a live agent's whole process tree.
Fixed by holding the name *across* the decision. The new build's `standing.holding` and
`firing.claiming` already carry that lesson forward.

**Registration before the spawn, and undone if the boundary fails.** `turn._run` registers the pid with
`activity.began` immediately after `start()`, and *if that raises, it ends the program* — because
registration needs the pid, and a provider left running with nobody reading or owning it is an orphan
whose only identity nobody wrote down.

**Nothing that goes wrong while speaking to a brain may be silent.** `_saying` runs as its own task, and a
task whose exception nobody retrieves failed invisibly — so a word that could not be written down would
leave the turn reporting that it was fine. Whatever went wrong is put into the account as a `lost` record
*and* into the outcome's `trouble`, and the turn is downgraded by counting it as undelivered.

**And whatever happened, the brain is told there is no more coming.** *"A steerable brain reads until its
input closes; leaving it open because we went wrong is a turn that never ends, waiting on somebody who has
already stopped speaking."*

---

## 7 · What was worth keeping, and what was not

**Kept, and it is the reason this page is long:**

- adapter-as-program, resolved by looking rather than by a table;
- closed record/verb/capability/posture/reason vocabularies, with unknown lines kept rather than refused;
- capability declaration, asked once per turn and written into the run;
- the environment as the whole interface, with no vendor variable in it;
- silence-not-duration as the failure, with a far-away ceiling as the backstop;
- process **group** signalling, and `PermissionError ≠ gone`;
- a bounded, non-blocking queue between reading and receiving, with losses reported *in place* as gaps;
- messages and records told apart, with `seq` as a clock-independent order;
- the seven readings, especially `_ended` vs the exit code and `_answered`;
- one instruction composer with a core that carries no identity.

**Not kept:**

- **asyncio.** `process.py` is 1207 lines of `asyncio` and roughly a third of its scar tissue is
  asyncio-specific — the single-waiter `drain()` assertion, cancellation unwinding past the settle,
  `ensure_future` tasks whose exceptions nobody retrieved, `shield` inside `wait_for`. The new build is
  synchronous (`utils/programs.py`, `gateways/host.py`) and Hermes independently chose the same for the
  same reason. See the companion page.
- **`answering.py` as one module.** 1668 lines holding authorization, the turn lifecycle, a per-conversation
  waiting queue, a 200-entry conversation cache, recovery prompts, delegation reports and role handoffs. It
  is the module that grew every feature, and its own docstring already names three separate concerns it
  "only" owns.
- **Registering a run in `activity` as a JSON file under `run/`.** The lock-plus-record pattern the new
  build already uses for gateways and firings answers the same question better.

---

## What to prove again, and how

The previous build's provider tests never reached the network, and the mechanism is worth copying whole:
**a committed golden stream per brain**, captured once against a stated version and re-driven offline.
`tests/samples/claude-stream.jsonl` is 184 real lines that cost real money and cannot be re-derived by
reading anything; `cli-versions.lock` records what each capture is true of. Anything that would need an
account, a token or a network is a probe script that a person runs deliberately, never a test.

The four properties a rebuilt provider layer has to break the code to prove:

1. a record of an unknown kind is **kept and shown to nobody**, and the raw line survives;
2. a receiver that is slow, and one that raises, neither stops nor ends the program — and both are
   reported as gaps in the right place;
3. an adapter that says `steer: false` has its input closed after the prompt, and one that says `steer: true`
   does not;
4. a program that exits zero having said nothing is **not** a turn that worked.
