# PLAN — an agent's first message, and a description that keeps itself current

Two deferred pieces of one idea: **a new agent should open the conversation rather than wait to be
spoken to**, and **an agent should say what it is for so its teammates can find it**.

**No code has been written.** This was designed alongside `rundesk permissions` and split out so that
the permissions work could ship on its own. It is a decision record, not a status board — and unlike
its predecessor it says so at the top, because `PLAN-CHANNELS.md` claimed to be untouched for a long
time after it stopped being true.

Paths are repo-relative. `src_old/` is the gitignored copy of the previous build.

**Depends on** `rundesk permissions` (shipped separately). The first message offers to run it.

---

## Why this exists

Today a new agent is inert until spoken to. You run `rundesk agents add`, attach Discord with
`--notify`, and the gateway posts one canned `🟢 Gateway online` and then waits. Nobody has told the
agent what it is for; its `MEMORY.md` is the empty scaffold `agents/pages.py` seeded; and its
`describes` is `NULL`, which means `providers/team.py:44` **leaves it out of the team listing
entirely** — so it is invisible to every other agent until the owner types `--describes` by hand.
Nobody does.

The requirement already exists and is already owed: **R-CH-33**, at
`docs/requirements/channel-messaging.md:56` — *"A user newly allowed on a channel is privately
introduced to the agent once in its own words, and never again while allowed"* — built in the
previous build, absent from this one, recorded as a gap at `PLAN-CHANNELS.md:365-368`. The old
implementation is intact and dead in `src_old/{welcome,gateway,answering,instructions}.py` and is the
design precedent for most of Part one.

## Scope, as the owner set it

Deliberately small. **A simple first message** — a greeting, what do you want to get done, and an
offer to run the permissions check with an honest warning about what approving it is like. **Not** a
multi-turn walkthrough, a state machine, a completion checklist, or a per-turn instruction layer;
an earlier draft had all four and they were cut. What is left is one turn, two columns, one latch.

---

# Part one — the first message (R-CH-33)

## 1.1 The state: one column, three answers

New step `agents/steps/0006_the_first_message_an_agent_sends.py`. `0005` is the last shipped step and
is never edited (`steps/__init__.py` rule 4). Additive `ALTER TABLE ADD COLUMN` only, so no table
rebuild and none of `steps/__init__.py:67-88`'s traps apply. Each guarded by
`if "<name>" not in columns`, as `0005:126-133` does, because `ADD COLUMN` has no `IF NOT EXISTS`.

```sql
ALTER TABLE config ADD COLUMN first_contact TEXT
  CHECK (first_contact IS NULL OR first_contact IN ('owed','said'));
ALTER TABLE config ADD COLUMN first_contact_at TEXT;
```

| Value | Means | Written by |
|---|---|---|
| `NULL` | **Nothing written.** This agent predates the feature. Never greeted, ever. | step `0006`, **by omission** |
| `'owed'` | Made after it shipped; owes a first message | `agents/directory.py:427-430`, at `rundesk agents add` |
| `'said'` | The platform took it | `providers/answering.py`, after delivery landed |

**The column must have no `DEFAULT`, and this is the whole safety property.** `directory._built` calls
`migration.carry_one` (`directory.py:420`), which runs **every** step — so `0006` executes against a
brand-new agent as well as a carried one. A `DEFAULT 'owed'` would make the two indistinguishable and
would greet **every agent on the owner's live install** at the next `rundesk update`. The affirmative
answer is written by one line, in one function, after the migration, in the `stated` call that already
writes `agent_name`.

This is the old build's reasoning carried across (`src_old/rundesk/welcome.py:30-40`): *"a mapping and
not a list is the whole feature… an empty list would make 'this channel is new, greet everybody' and
'this channel has greeted everybody already' the same answer — and those are opposites."*

Small module `src/rundesk/agents/first_contact.py`, layer `agents` (reaches `records`, `directory`,
`core.config`, `utils` and nothing else): `owed(agent) -> bool` and `said(agent, when=None)`, the
latter moving `owed → said` inside one `records.writing` transaction and **refusing any other move**
rather than overwriting — `records.stated` is a general setter and would let any caller write
anything.

## 1.2 The trigger

`gateways/host.py`, in `_serving`'s loop, immediately after the `said_up` block at `:669-680` and
before the sleep, with `said_hello = False` seeded beside `landing, swept_for, said_up` at `:654`.
Not in the tail beside `_told_what_changed`: that would cost a whole beat between `🟢 Gateway online`
and the agent's first words.

`_said_hello` asks four questions and stops at the first no:

1. `said_hello` already true → done for the life of this process.
2. `first_contact.owed(name)` → the durable answer.
3. `_the_told_channel_is_connected(name, channels_up)` — **the same function, not a copy of its
   reasoning.** It is the fix for a measured defect (`host.py:669-679`: a notice went into a Discord
   bot four seconds before it had a session, and *"the one person who had asked to be told heard
   nothing at all"*).
4. `delivery.notice(name, "")` is not `None` — **there is somewhere to send it.**

**Question 4 is not redundant with question 3, and omitting it is a real defect.**
`_the_told_channel_is_connected` answers `True` when there is no notified channel, deliberately
(`host.py:1010-1014`) — right for `CAME_UP`, which costs nothing, and wrong here, where it would start
a brain turn, spend the owner's tokens, and have nowhere to put the answer.

Then `said_hello = True` **before** the turn, from `src_old/gateway.py:2483-2485`: *"so a welcome that
raises after the brain has already written to somebody is not asked for a second time."* The two
latches together are the whole retry policy: **once per gateway process in memory, until it succeeds
durably.** The function stands inside one `except Exception`; nothing in this loop may exit non-zero
into `KeepAlive`.

## 1.3 The conversation

**The notified channel's own, keyed on `notify_place`** — the same one the owner's reply lands in, by
construction. `arriving.recorded` keys a channel conversation on `place` alone (`arriving.py:84`), and
Discord's `--check` sets `notify_place` to the DM it opened with the first allowed id
(`src/channels/discord:838-869`). So the opener and the reply resolve to one row with no id to keep in
step.

The old build gave the greeting a conversation of its own (`welcome:<user>`,
`src_old/answering.py:661-664`) because it was a dead end. Here the owner is expected to reply, so it
must be in the exchange that continues — otherwise the agent's own opener is not in the history it
reads back.

## 1.4 The finding worth the whole document: it is a prompt, not an instruction layer

The first draft made this an addition on `USER_TO_AGENT`. **That was wrong twice over.**

*Wrong by membership.* `instructions.py:1` — the module holds *"what a brain reads before it reads a
word of the task."* Everything here **is** the task. `schedules/upkeep.py:_prompt()` is the precedent
already in the tree: rundesk's other "a turn is owed" mechanism expresses its whole instruction as a
hard-coded prompt, not a layer.

*Wrong by consequence, and this is the one that matters.* `turns.py:579-585`:

```python
resume = None if request.fresh else kept.get_session(agent, request.conversation, provider_name)
if resume and kept.latest_instructions(...) != prompt.sha256:
    # Some brains bind the preface when a session starts and accept-but-ignore replacements
    # on resume. Throw the stale handle away…
    kept.delete_session(...); resume = None
```

An addition on turn 1 changes `prompt.sha256`. Turn 2 carries no addition, so its fingerprint differs,
so **turn 1's session handle is deleted and turn 2 opens cold** — and rundesk does not replay
conversation history into a fresh session (`inbound_messages` is only the new messages,
`turns.py:607-610`). The agent would not remember having offered to run the check.

**As a prompt, turn 1's instruction stack is byte-identical to every other `USER_TO_AGENT` turn's.**
Same fingerprint, so turn 2 resumes turn 1's session and the brain has the whole exchange, its own
offer included. **`instructions.py` is not touched by this plan at all**, and
`tests/test_providers_instructions.py` needs no change — which is itself the proof.

Three guarantees fall out, each a test: it cannot reach turn 2, because it is a row in
`conversation_messages` and `_answered` never sets `additions` · `rundesk providers instructions`
renders identically before and after · what rundesk asked for is visible as a `rundesk`-authored
message (`arriving.BY_RUNDESK` — *"deliberately neither the agent nor a person"*), readable with
`rundesk messages`, so the owner can see exactly what their agent was told.

## 1.5 The turn

New `OnAChannel.first_contact(agent, kind, place)` in `providers/answering.py`, a sibling of `answer`,
on a daemon thread as `answer` does (`:211-214`):

```python
landed = arriving.said_by_rundesk(agent, kind, place, first_contact.THE_PROMPT)
got    = turns.run(turns.Request(
             agent=agent, prompt=first_contact.THE_PROMPT,
             conversation=landed.conversation,
             situation=instructions.USER_TO_AGENT,   # and no additions — see 1.4
             source=arriving.FROM_CHANNEL, place=place, fresh=True,
             inbound_messages=(landed.message,)), watching=…)
```

`said_by_rundesk` exists for exactly this (`arriving.py:43-45, 90-97`). `fresh=True` because there is
nothing to resume. No `external_id` — nobody sent this, so there is nothing to mark or quote.

**Delivery reuses `_delivered` but not its apology branch.** `_delivered` falls through to `_instead`
for a turn that produced nothing (`:319, 377-389`), and *"I could not answer that"* as an agent's
first ever words is worse than silence. In order:

```
if not got.worked:                          -> log, return, leave it owed
if nothing said and no files:               -> log NOTHING_SAID, return, leave it owed
if _delivered(...) answered a refusal:      -> log ERROR, return, leave it owed
first_contact.said(agent)
```

**The nothing-said check is the trap.** `_delivered` returns `""` early when there are neither words
nor files (`:337-338`), and `""` is its word for *landed*. Read off the refusal alone, a turn that
said nothing is written down as a greeting the owner never received — which is R-CH-33's own evidence
case *"a turn that said nothing is not reported as a greeting"*.

**`providers` writes the state, not `gateways`**: the layer that knows whether the platform took it is
the layer that writes it down. The write happens **after** delivery; a gateway killed in between
leaves it `owed` and sends a second opener next time. Accepted, because the alternative risks an owner
never greeted at all — `src_old/welcome.py:115-121`: *"this is the one message that cannot be asked
for again by whoever missed it."*

## 1.6 `first_contact.THE_PROMPT`

Lives in `agents/first_contact.py` beside the state. Carried from `src_old/instructions.py:161-174`,
keeping its *"Deliberately empty of purpose: a new agent has no projects, no goals and no focus, and
inventing one here is how an owner is told what they wanted before they have said it."*

```
## Your first message

Nobody has spoken to you yet. Rundesk asked for this turn, and what you write is the first thing your owner will ever read from you. Write that message and nothing else. Run nothing, change nothing, and check nothing this turn.

Two things, warmly and briefly — six sentences at most, to be read on a phone.

- **Introduce yourself and ask what they want.** You are {agent_name}, you are new, and you are set up for nobody in particular yet. Ask what they do and what they want you to take on or get done. Their answer is what you are for, so ask it plainly and leave it open.
- **Ask to run the permissions check.** Say you would like to run `"$RUNDESK_COMMAND" permissions check` to find out what this Mac currently lets you do, and ask them to say when it is a good moment. Warn them what it is like: macOS will ask them to approve several things, some as pop-up prompts to accept and some they have to switch on by hand in System Settings, and you will walk them through whichever come up. Say why it is worth it in one clause — it is what lets you actually operate the machine when they ask you to handle something.

- Never invent, assume or offer a project, goal, focus or speciality, and never write as though work already exists. They decide all of that by replying.
- Do not run the check now, and do not guess what it would say. You are asking, not reporting.
- Change nothing this turn. Nothing has been learned yet, so write nothing to `MEMORY.md`, grant yourself nothing, and leave your description alone — once they answer, your standing rules say what to do with it.
- Write only the message. No preamble, no sign-off, and no account of what you are doing.
```

`{agent_name}` is filled by `first_contact`, not by `instructions._filled` — this is a prompt, and the
substitution is the caller's.

**One honesty point the wording has to keep.** "Accept the prompts" is only half true, and it is
measured: Screen Recording, Accessibility and Full Disk Access have **no prompt at all** — they are
switched on by hand in System Settings and Full Disk Access needs the program added with `+`
(`docs/research/2026-08-08-what-this-mac-lets-a-process-do.md` §5, §8.3). A first message promising a
flow that will not happen is a small lie that costs trust on day one.

**The check runs on a later turn and needs no machinery** — but only because §1.3 and §1.4 both hold.
Sharing the conversation puts the exchange in one place; keeping the fingerprint unchanged lets the
brain still be in it. Either alone leaves the agent cold on turn 2.

## 1.7 Failure modes

| What happens | What rundesk does | State |
|---|---|---|
| Turn fails, says nothing, or delivery refused | one line in the gateway log; nothing written down | `owed` — this process never retries; the next gateway does |
| Nothing hosting the channel when the answer is ready | `_delivered` answers *"there was no channel to answer through"* (`answering.py:352-356`) | `owed` |
| Killed between delivery and the write | a second opener next time — accepted; the alternative risks never greeting at all | `owed` |
| Owner never replies | nothing. No nag, no timer, no follow-up | `said` |
| Owner never answers about the check | nothing chases them; `rundesk permissions` says nothing has been checked | `said` |
| Owner says go ahead and everything is blocked | the expected case on a fresh install (measured). The agent walks them through it from the fix lines | `said` |
| Agent names no brain | `turns._held` resolves the provider before writing anything (`turns.py:557-560`) and raises; caught as *turn fails* | `owed` |
| No notified channel, or removed before | question 4 answers no. No turn, nothing spent, nothing logged per beat | `owed` |
| Two channels | at most one may be `notified` — the partial unique index behind `telling` (`channels/kept.py:13-18`) | — |
| Records unreadable | guarded; the answer is *do nothing*, complained once rather than every fifteen seconds | unchanged |

## 1.8 Tests, against R-CH-33's 27 existing evidence cases

The trigger moved from *a person newly allowed on a channel* to *an agent made after this shipped*, so
the person-keyed half has no subject. **13 carry verbatim · 6 restated · 8 dropped.**

Seven of the eight dropped need a per-person record, which does not exist — `delivery.notice` can only
target the notified channel (`delivery.py:89-99`) and `PLAN-CHANNELS.md` 6.1 records that addressing a
notice at a person is absent. The eighth (*an agent reached on two channels greets one person once*)
is unreachable because only one channel may be notified. Two replacements carry what those protected:
`the first message goes only to the notified place` and `an agent with a second channel still speaks
once, through the notified one`.

The restatement that matters most: `a channel from before this existed greets nobody` becomes
**`an agent from before this existed is never greeted`** — the safety property for the live install.

New cases: `a first message is attempted once for the life of a gateway` · `an agent that tells nobody
anything is not greeted` · `the online notice reaches the platform before the agent's first words` ·
`a gateway killed between delivery and the write leaves it owed` · `a first message resumes nothing` ·
`a first message is written down as rundesk and never as the agent` · `a step run against an agent
that predates this leaves it never owed` · `a step run twice changes nothing` · `an illegal move is
refused and changes nothing`.

**The three that prove §1.4**, and the ones to break the code for: **`a first message leaves the
session resumable`** (its fingerprint equals an ordinary turn's) · **`a first message adds nothing to
what a turn reads`** · **`what rundesk asked for is a message in the conversation and not a layer`**.
Putting the prompt back into `additions` must turn the first of those red.

Also to watch fail: `an agent from before this existed is never greeted` and `a turn that said nothing
is not reported as a greeting` — both stay green against a wrong implementation for a long time.

New suites `tests/test_agents_first_contact.py`, `tests/test_agent_first_contact_step.py`; extensions
to `test_gateway_host.py` and `test_providers_answering.py`.

---

# Part two — a description that keeps itself current

`config.describes` is how one agent decides whether to hand work to another. `providers/team.py:19-46`
is its only reader and composes `- **bob** — <describes> · skills: …` into `AGENTS_LIST`
(`instructions.py:229`) for every person-facing turn. **An agent nobody has described is left out of
that listing entirely** (`team.py:44`). Bounded at 200 characters
(`directory.DESCRIBES_AT_MOST`), because *"every agent's description costs every other agent's
prompt."*

Two writers, no state, and they reach different populations on purpose.

## 2.1 A standing rule, for agents made from here on

`src/templates/AGENTS.md` gains one short rule under its existing `Rundesk` section: when the owner
tells you what you are for, or what you are for changes, set your description with
`"$RUNDESK_COMMAND" agents configure <you> --describes "<one sentence>"` — one line, your own words
about your own work, because it is what every other agent reads when deciding whether to hand you
something.

Standing rules and not an onboarding layer, because it is true for the whole life of the agent rather
than for one conversation — so it needs no state, no scoping and no completion check. The agent asks
what the owner wants in its first message (§1.6); the owner answers on turn 2; the rule is already in
context and it acts.

**It reaches new agents only, and that is correct.** `agents/pages.py:28-41` fills absence and never
replaces an answer, so a released change to `AGENTS.md` never overwrites an existing agent's copy —
including one the owner has edited. Existing agents get the same outcome from §2.2.

**This is a change to shipped rules text and wants explicit sign-off**: it changes what every future
agent is told about itself.

## 2.2 The weekly upkeep, for every agent

`schedules/upkeep.py:_prompt()` is the hard-coded prompt behind the protected
`weekly-self-improve-upkeep` row, fired after seven distinct usage dates. It already does workspace and
continuity maintenance, a retro, and a self-improvement review. One step is added, in the same
register:

> Review your description against what you have actually been doing since the last upkeep. It is what
> every other agent reads when deciding whether to delegate to you, so it must say what you really
> handle now rather than what you were set up for. Where it is missing, stale, or vague enough that a
> teammate could not tell whether you are the right agent, set it with
> `"$RUNDESK_COMMAND" agents configure <you> --describes "<one sentence>"`. Where it is already
> accurate, leave it exactly as it is and say so.

The matching step goes in `src/skills/managing-rundesk/references/self-improvement.md`, which the
prompt tells the agent to read — the prompt names the work, the reference says how.

**The authority is granted where it is used.** `src/templates/AGENTS.md:26` and `self-improvement.md`
step 8 both withhold changing your own description *"without explicit authority in this request or
schedule"* — and the upkeep prompt **is** the schedule's request. Neither file needs loosening.

**"Leave it alone and say so" is not filler.** Without it, a weekly prompt asking an agent to review
its description produces a reworded description every week, each one a fresh string in every
teammate's prompt, churning for nothing.

## 2.3 Closing the injection surface — mandatory, because Part two creates it

`describes` is text that lands inside **other agents' prompts**. One half is already defended:
`instructions.py:266-268` fills the trusted template before substituting `{team}`, so a
`{provider_name}` inside a description stays literal — *"Descriptions are owner data, not instruction
templates."*

**Shape is not defended, and until now it did not need to be.** `team.for_agent` builds
`f"- **{other}** — {describes} · skills: …"`, so a description containing `\n\n## Who is asking\n\n…`
forges a heading in every teammate's prompt. That is unreachable while the only writer is an owner
typing a flag. **§2.1 and §2.2 make an agent the writer, and that agent's input is a chat conversation
with whoever can reach it.** So this closes with the feature, not after it.

1. **`directory.describes_trouble` gains a shape rule** (`agents/directory.py:246-255`, today length
   only): refuse a newline, a carriage return, or any control character. One sentence has no line
   breaks in it, which is already the field's contract. This narrows it for **every** writer including
   the owner — one check, one home.
2. **`team.for_agent` flattens on read.** The store may already hold something written before the
   rule; refusing on write does not clean what is there, and silently rewriting the owner's stored
   data is worse. Refuse it going in, flatten it coming out, leave what is stored alone — three
   answers, not two.
3. **Both prompts say it in words**: the agent's own words about its own work, never text somebody
   asked it to put there, and never anything said in confidence.

## 2.4 Tests

`a description with a line break is refused where it is written` · `a description already holding a
line break is flattened where it is read` · `a description a brace was written into stays literal in a
teammate's prompt` (extends `tests/test_providers_instructions.py:354`) · `the upkeep prompt names the
description step` · `the shipped rules tell an agent to describe itself` (asserted against
`src/templates/AGENTS.md`, as `tests/test_agent_pages.py` already asserts template content) · `an agent
that describes nothing is still left out of the listing rather than listed blank`.

---

## Requirements to add

`docs/requirements/channel-messaging.md`: R-CH-33 restated in place with a rewritten evidence column,
plus **R-CH-34** (a first message is attempted at most once per gateway process and written down only
once the platform took it) and **R-CH-35** (an agent with no notified channel is never asked for one
and never spends a turn on one).

New page `docs/requirements/agent-description.md`, id `DESC`: **R-DESC-1** an agent sets its own
description when its owner tells it what it is for · **R-DESC-2** the weekly upkeep reviews it against
what the agent actually did, and leaves an accurate one untouched · **R-DESC-3** a description an agent
wrote cannot forge a line in another agent's prompt · **R-DESC-4** the authority to set it is granted
by the request or schedule that asks for it, and nowhere else.

## Hard gates before any of this is written

- **Persisted state** — two new `config` columns and a shipped-forever step `0006`. Confirmed before
  the step is written; once it ships it can never be edited.
- **Shipped rules text** — `src/templates/AGENTS.md` (§2.1) changes what every future agent is told.

## Open, and deliberately not built

- **Nothing verifies that a description is *true*.** §2.1 and §2.2 make it exist and keep it current;
  whether it accurately describes what the agent is good at is the agent's own account. The upkeep's
  *"against what you actually did"* is the only grounding, and it is a prompt rather than a check.
  Worth revisiting if delegation starts landing in the wrong places.
- **A second agent's first message will find the permissions already done** — one grant covers every
  gateway (measured). The opener still offers the check; it comes back clean, which is right, and is
  worth expecting rather than debugging.
- **No re-greeting, ever.** There is no `rundesk agents greet <name>` and no way back from `said`. If
  one is wanted later it is a command, not a state change somebody can make by hand.
- **`owner_name`** has been declared and unread since step `0001`, and the first message is the natural
  moment to fill it. Out of scope: it is a second feature wearing this one's clothes.
