# PLAN — the Discord channel and the two attachment paths

A repair plan for the channel seam: inbound replies, attachments in **and** out, and the critical
defects found while checking them. Companion to [`REVIEW.md`](REVIEW.md), which is the wider audit.

Paths are repo-relative. `src_old/` is the gitignored copy of the previous build.

**Most of this has since shipped.** This said *"no code has been written"* long after that stopped
being true, which makes a plan read as untouched when what is left is only its tail. Phases 1–5
landed in `a266b0a` (*a reply carries its context, a file goes both ways, and a refusal is not a ✅*);
the defects found in a later audit landed in the four commits after it.

**What is left is Phase 6, and not all of it:** there are no per-person notices and no greeting for a
newly allowed user (6.1); rooms cannot be addressed by name (6.3); slash commands are synced
globally, so a fresh bot waits up to an hour for them (6.5); `retry_after` is emitted and read by
nothing — and, on the shipped adapter, is not even reachable (6.6); `/help` remains absent (the
remaining half of 6.7); `--capabilities` is still asked for and thrown away (6.8); and
`allowed_mentions` is unset (6.9). `/agents` now supplies the approved private install-wide agent
directory, and long private slash answers continue losslessly across ordered ephemeral followups.

Read the item statuses below as *what was true when this was written*, and this header as what is
true now.

Scope was set by the owner: **fix inbound replies, make files attach in and out, and confirm nothing
critical is missing or broken in Discord.** Turning activity commentary off is **explicitly out of
scope** and is not planned here.

**Verified** = read out of the code while writing this. **Reported** = came from an investigation
pass with a citation, not re-confirmed here.

---

## What the investigation changed about the ask

Three things turned up that the original ask did not anticipate. They belong in this plan because
two of them are worse than the thing that prompted it.

1. **Outbound attachments are not "partly working" — the chain is dead at its first link, on
   purpose.** Seven of eight links are built and correct; **no shipped provider adapter emits a
   `file` record**, and all three refuse to in their own docstrings. This is a design gap, not a bug,
   and it needs an owner decision before any code (Phase 3).
2. **Inbound attachments land, but the integrity guarantee is a no-op.** The documented
   declared-vs-actual size check cannot fire, because the adapter reports its own measurement.
3. **A delivery Discord refuses still marks the asker's message ✅**, and the answer is lost to a log
   line. That is the product's cardinal rule broken on an ordinary permission failure, and it is
   fixed first.

---

## Phase 0 — decisions needed before code

Work should not start on Phases 3, 4 or 5 until these are settled. Each names a recommendation.

### D1 — How does a brain say "send this file"? *(blocks Phase 3)*

The old build had **two** mechanisms merged before approval:
- a markdown-link convention — the brain wrote `[label](/abs/path)` in its answer and
  `src_old/rundesk/attachment.py:108` (`declared_in`) parsed it out, **stripping the link from the
  visible text** so the machine path was never posted into the room (R-CH-31);
- structured `file` records, which **only `src_old/providers/codex` ever emitted**.

For claude, grok and antigravity the markdown link was the *only* route a file could leave. This
build kept the containment/verification half verbatim and dropped the candidate-producing half.

The blocker is not path availability — it is **intent**. All three streams report files *touched*;
none reports *this is the artifact you asked for*:
- **claude** — has the absolute path for every `Write`/`Edit` (`src/providers/claude:123`, `:944-957`)
  and no intent signal; its docstring refuses on exactly that ground (`:63-66`).
- **codex** — has the path and a real create-vs-modify distinction
  (`src/providers/codex:572-575`, `:594-595` tests `kind.type == "add"`); still no intent.
- **grok** — cites `locations[].path` (`:66`) but **never reads it**, and the captured samples are
  read-only turns, so whether a `create_file` update carries an absolute path is **not established**
  and needs a live probe.

Nothing in `src/rundesk/providers/instructions.py` currently asks a brain to name what it made.

| Option | Cost | Risk |
|---|---|---|
| **A. Reinstate the markdown-link convention** in the engine, plus an instruction telling the brain the convention | medium | brain must comply; prose parsing |
| B. Per-provider heuristic (e.g. codex `kind.type == "add"` inside `RUNDESK_CWD`) | medium | attaches files nobody asked for; different per brain |
| C. New explicit seam record the brain opts into | large | needs all three adapters changed + contract change |

**Recommend A.** It is provider-agnostic (works for all three brains without touching any adapter),
it is what R-CH-31 was written against, it has a proven design in `src_old`, and it puts intent where
intent actually exists — in the answer the brain chose to write. B silently attaches wrong files; C
is A's cost plus three adapter rewrites.

**Owner call needed.** This is the largest single decision in the plan.

### D2 — Reply field name and shape *(blocks Phase 4)*

`reply_to` is already taken on the **outbound** `deliver` record, as a bare external-id string
(`docs/adapters.md:356`, `:367`). The old build used the same word inbound for an object.

**Recommend** `reply_to` inbound as an object `{"id", "resolved", "author"?, "text"?}` — matching
`src_old` and R-CH-29's own vocabulary — and state plainly in `docs/adapters.md` that the word means
two different things on the two records. Alternative `replies_to` avoids the collision but departs
from the requirement's language.

### D3 — Where the reply's bounds are enforced *(blocks Phase 4)*

**Recommend rundesk, in `channels/hosting.py`** — flatten `author` to one line ≤80 chars, clip `text`
at 255 with an explicit truncation marker. This is what `src_old/rundesk/channel.py:451-478` did and
what `channels/files.py` already does for attachment names (*"a stranger's text, flattened by rundesk
and nowhere else"*, `docs/adapters.md:305`).

**Note the conflict:** `docs/adapters.md:555` currently assigns the display-name bound to *the
adapter*. That row needs restating, or an explicit exception. Enforcing only adapter-side makes a
third-party adapter's bug a prompt-injection surface.

### D4 — Does the reply block go in the stored body, or only in the prompt? *(blocks Phase 4)*

**Recommend fold into `body`** in `hosting._arrived` before `arriving.recorded`, reusing the
`_also_attached` precedent exactly (`hosting.py:1065`, `:1139-1150`). It needs no new parameter down
three call layers, and `rundesk messages` then reads back as the conversation actually happened.

**This keeps the plan clear of the persisted-state gate** — see D5.

### D5 — Schema: none needed, and one thing that *would* need a gate

**No new column is required** for any of this. `conversation_messages.external_id` already exists
(`agents/steps/0003_the_channels_an_agent_keeps.py:109-123`). *Verified.*

Two things **would** cross `AGENTS.md`'s persisted-state hard gate and are **not** in this plan
unless the owner asks:
- adding a parent/reply column (a new step `0006`; a shipped step is never edited);
- **starting to write `external_id` onto the agent's own answers.** Today `turns.py:598` calls
  `said_by_agent(...)` without one, so answers are stored with that column NULL, and the platform id
  lives only in `hosting.py:1021`'s in-memory `one.posted` (capped 200, lost on restart). *Verified.*
  Closing that would make reply-by-lookup possible **and** would fix a schedule's ability to quote
  its own notice across a restart — but it changes what an install keeps, so it is an owner call.

**Consequence of not doing it:** a reply to *the agent's own answer* — the commonest case on Discord
— cannot be resolved from rundesk's own store. That is why D1's recommendation takes the quoted text
from the adapter (Phase 4), with a store-lookup hybrid left open for later.

### D6 — How much channel context should reach the brain? *(blocks Phase 5)*

`instructions.VARIABLES` is a closed set of seven and is deliberately platform-neutral — *"a variable
that named one would be a layer that has to be rewritten for the second surface"*
(`instructions.py:78-81`). *Verified.* So server/room/thread names **must not** become instruction
variables.

**Recommend** carrying who-and-where in the **user turn**, the same way attachments and replies are —
communication-agnostic words composed in `channels/hosting.py`, never platform nouns in `providers/`.
The old build used exactly this split (`src_old/rundesk/answering.py:1628-1640`).

---

## Phase 1 — honesty first (no new features)

These are correctness bugs in the code the rest of the plan builds on. Do them first.

### [ ] 1.1 A refused delivery must not leave a ✅ — **critical**

- **Now:** `_deliver` reports `{"say":"failed"}` (`src/channels/discord:1345-1357`);
  `hosting._heard` writes one WARNING and pops the in-flight entry (`hosting.py:937-939`); then
  `answering.py:209-211` marks the asker's message from `got.turn_status` alone. *Verified.*
- **Symptom:** the question wears ✅ and no answer ever appears. Triggers are ordinary — a bot
  invited before this release lacking `ATTACH_FILES` or `SEND_MESSAGES_IN_THREADS` (the adapter
  already documents that an existing bot is not granted newly-added permissions,
  `src/channels/discord:158-166`), a locked thread, a deleted channel.
- **Do:** make the delivery outcome reach the mark. A turn that produced an answer the platform
  refused is not `done`. Decide the mark for that case (recommend `failed`, since the person got
  nothing) and make sure the reason reaches somewhere a person looks, not only the day log.
- **Watch for:** `hosting.py:993-1008` records that turning an *acknowledgement* into ✅ was
  deliberately removed, and why. This fix must not reintroduce that — the turn still owns the mark;
  what changes is that a known-failed delivery is an input to it.
- **Prove:** a delivery the adapter refuses leaves the asker's message not-✅, with the reason
  visible. Break it and watch it fail.

### [ ] 1.2 Files a delivery may not carry must be reported — **important**

- **Now:** `delivery.carried` returns `Carrying(files, refused)` and its docstring says a caller
  reading only the first *"would report a delivery as whole when part of what it was asked to send
  was quietly left behind — which is the failure this product is built around not committing"*
  (`delivery.py:64-75`). The single caller reads `carrying.files` and **never `carrying.refused`**
  (`answering.py:267`, `:281`). Nothing consumes it anywhere. *Reported.*
- **Symptom:** a file outside the agent's roots, over 32 MiB, or past the 10-file bound vanishes —
  not attached, not mentioned, not logged.
- **Do:** consume `refused`. At minimum a log line; better, a sentence to the person, since they are
  the one expecting the file.
- Same class as the known dead `retry_after`.

### [x] 1.3 Long private slash answers are split losslessly — **resolved**

- **Now:** the Discord adapter splits an `answered` result without dropping or reordering any text
  and sends each piece sequentially as an ephemeral followup to the interaction that asked. A
  refused continuation is logged and followed by a private incomplete-response warning.
- **Applies to:** `/skills`, `/schedules`, `/agents`, and every other private slash answer that
  exceeds Discord's message limit.
- **Requirements:** R-DIS-11, R-DIS-36, R-DIS-37, R-DIS-42.

---

## Phase 2 — inbound attachments: make the guarantee true

The path works and the brain **is** told about the file — `hosting._also_attached` (`:1139-1150`)
appends name and absolute path to the body, and that body reaches the prompt via
`answering.py:205-208` → `turns.py:493/497`. *Reported, traced end to end.* Engine-side validation is
genuinely strong: containment, `lstat` symlink refusal, `S_ISREG`, three size checks, name
flattening, collision-free naming, staged-file cleanup in a `finally`, and a 60-day sweep that is
wired and fires.

What is wrong is narrower, and one item is a documented guarantee that cannot fire.

### [ ] 2.1 The `bytes` integrity check is a no-op end to end — **critical**

- **Promised:** `docs/adapters.md:306` — *"what the platform said it would be. Checked against the
  file's real size, and a mismatch is refused."* Implemented correctly at
  `channels/files.py:198-204`.
- **Now:** the adapter has Discord's declaration in `declared` (`discord:1234`) and uses it only as a
  pre-fetch bound. What it *reports* is `fetched` — its own `stat()` of the file it just wrote
  (`:1246`, `:1254`). So rundesk compares its measurement against itself; they always agree. A
  download cut off part way lands and is named to the brain as complete. The adapter also never
  compares `fetched` against `declared`. *Verified as the shape of the code.*
- **Do:** report Discord's declared size as `bytes`, and drop the file when `fetched != declared`.
  This makes an existing, tested, correct check reachable. Smallest high-value fix in the plan.

### [ ] 2.2 A partly-written file is orphaned for ever — **important**

`discord:1240-1253` — if `save()` raises mid-write the handler notes and `continue`s **without
unlinking**; only the oversize branch cleans up (`:1248`). Debris is never reported, so
`files.landed` never removes it, and `files.swept` sweeps only `<kind>/in/<day>`, never
`<kind>/fetched/`. Same for a staged path refused by containment, which fires *before* the
`try/finally`. **Do:** unlink on the failure path, and reap `fetched/` debris.

### [ ] 2.3 The 64 KiB clip can silently drop the attachment block from the record — **minor**

`_also_attached` appends *after* the text (`hosting.py:1150`) and `arriving._bounded` clips at 64 KiB
(`arriving.py:53`, `:388`). A very long message loses the attachment block from the stored body. The
brain is unaffected (it gets the unclipped body), but `rundesk messages` shows a message whose files
vanished, with nothing saying so. **Do:** at minimum log when the block is clipped away.

### [ ] 2.4 `_brought` is completely untested — **important**

`grep` for `_brought` / `BROUGHT_MOST` / `BROUGHT_BYTES` in `tests/` returns nothing. The stub
`Message` declares `attachments: List[Any] = []` (`tests/test_channels_discord.py:288`) and no test
ever populates it, so every call returns before doing anything; there is no `Attachment` stub with a
`save()`. **2.1 is exactly the defect a test here would have caught.** The end-to-end coverage uses a
12-line stub that hardcodes `"bytes": 8` *correctly* — it proves rundesk's half and cannot prove the
adapter's.

**Do:** add an `Attachment` stub with `save()`; cover the count cap, the declared-size skip, the
post-fetch check, the unset-`RUNDESK_CHANNEL_HOME` note, and **which number goes into `bytes`**.

---

## Phase 3 — outbound files: the missing link *(gated on D1)*

**Nothing an agent makes can reach Discord today.** Verified: no `file` record is emitted anywhere in
`src/`; the only place one exists at runtime is a test stand-in
(`tests/samples/a-stand-in:82-89`).

Everything downstream is built and good — `protocol.file_records` → `Outcome.files` →
`answering` → `delivery.carried` (dedupe by path, 10-file bound) → `files.approved` (absolute-path
check, `..` refusal by shape, root containment, `O_NOFOLLOW` component walk, hardlink refusal,
`S_ISREG`, size+SHA-256 from the descriptor) → `hosting` puts `files` on the last piece →
`a_verified_file` re-walks from `/`, reads bounded by the declared size, compares size and digest,
and uploads a **snapshot** rather than the path. `_deliver` refuses the whole delivery if any file
fails. Three separate recorded exploits are cited as the reason for three of those checks.

### [ ] 3.1 Produce candidates *(the actual work; shape depends on D1)*

Under recommendation **A**: reinstate a markdown-link convention in the engine — parse absolute local
links out of the brain's final answer, **strip them from the visible text** so the machine path is
never posted, and merge them with any structured `file` records before approval. `src_old/rundesk/
attachment.py:108` (`declared_in`) and the merge funnel at `src_old/rundesk/answering.py:1313-1314`
are the worked reference.

Layering: this is composition over an answer, so it belongs in `providers/answering.py` alongside the
existing `got.files` read at `:267` — not in `channels/`.

### [ ] 3.2 Tell the brain the convention

Nothing in `instructions.py` currently mentions attaching or sending a file. A convention the brain is
never told is a convention it will not follow. Must stay platform-neutral (D6).

### [ ] 3.3 A scheduled turn can never attach a file — **independent second gap**

`answering.for_a_schedule` returns the `Outcome`, but the report is posted by
`gateways/host.py:819-848` (`reported()`), which reads back only the **answer text** via
`arriving.last_answer` and calls `_told(...)` — and `_told` (`host.py:940-941`) has **no `sending`
parameter at all**. *Reported.* Fixing 3.1 alone leaves scheduled reports unable to carry files.

### [ ] 3.4 `a_verified_file` is untested

Zero hits in `tests/`. `tests/test_channels_discord.py` never builds a `deliver` with a `files` key.
The Discord half of the twice-verified contract — the half `docs/adapters.md:487` calls *"yours"*, and
the half that closes the TOCTOU window — has never been executed. Engine-side coverage is good
(`test_channels_files.py:190-294`, 15 cases; `test_channels_delivery.py:218-253`), which makes this
the one real hole.

### [ ] 3.5 Decide what "a long answer becomes a file" means *(REVIEW.md P3.4)*

R-DIS-18 says an answer is *"split **or attached**"*; old posted `answer.md` past a threshold. This
rides on Phase 3 and is cheap once files work. Without it a 40k-char answer is ~22 messages.

---

## Phase 4 — inbound replies *(gated on D2, D3, D4)*

The headline ask. Requirements **R-DIS-34, R-CH-29, R-CH-30** — all ✅ rows against the previous
build, none cited anywhere in `src/`.

**What exists to build on:** the adapter already asks for the *read the history* permission
(`discord:173`, *"Discord refuses a reply reference without it"*) and sets `message_content`
(`:464`), so the raw material is present. `self.handled` (`:1161`) maps id → place/ours but holds
**no bodies**, so it cannot resolve a parent's text on its own.

### [ ] 4.1 Adapter reads the reference

Follow `src_old/channels/discord:1739-1770` closely — it is a careful piece of code:
- `message.reference` absent → no reply;
- **keep only ordinary reply references**, rejecting forwards and pins (R-DIS-34 names *"a non reply
  reference is not presented as a reply"*). The old code hedged the enum with
  `getattr(kind, "name", "default")` against discord.py drift;
- parent from `reference.resolved` **or** `reference.cached_message` — **never fetch** (a round trip
  on the hot inbound path, and R-CH-30 exists so an unavailable parent is honest rather than chased);
- unresolvable → `{"id", "resolved": False}` and **nothing invented**;
- emit the key only when there is a reply, so ordinary messages carry no empty field.

**Accept the quality ceiling:** `reference.resolved` is populated inconsistently, so a real share of
replies will arrive `resolved: false`. That is visible to users and the owner should agree to it.

### [ ] 4.2 Engine normalises and bounds it

In `hosting._arrived` (`:1046-1066`). Per D3: flatten `author`, clip `text` at 255 with an explicit
truncation marker, and **discard author/text supplied beside `resolved: false`** — they would be a
guess (`src_old/rundesk/channel.py:456-462`). Treat the adapter's own bounding as a courtesy, not a
guarantee.

### [ ] 4.3 Compose the block into the body

Beside `_also_attached` (`hosting.py:1139-1150`), per D4. Reuse the old build's proven prose
(`src_old/rundesk/answering.py:1650-1660`) and its `\n\n--\n\n` separator, which keeps rundesk's words
and the person's told apart. **One thing to reconsider:** the old wording says *"conversation message
{id}"* where the id is a *platform* id the brain cannot look up with `rundesk messages` — consider
saying only the author and the quote.

### [ ] 4.4 Contract and requirements

Add the field to the `arrived` table (`docs/adapters.md:284-291`); resolve the `reply_to` naming
collision in both directions; cite R-DIS-34 / R-CH-29 / R-CH-30 in the docstrings that meet them.

**Forward compatibility is safe:** unknown records are ignored in silence by contract
(`docs/adapters.md:253-254`) and `_arrived` reads named keys without validating the key set, so an
adapter that does not send the field is unchanged. Absent must read as "no reply".

---

## Phase 5 — the brain is never told where it is or who is speaking *(gated on D6)*

**Critical, and it was not in the original ask.** The `arrived` record carries only
`place: "dm"|"room"` and a flattened `display` (`discord:1166-1178`) — no server, room or thread
name. Rundesk reads **neither**: `display` appears nowhere under `src/rundesk/` (*verified*), and
`instructions.VARIABLES` has no slot for any of it (*verified*).

**Symptom:** in a shared room the agent cannot say who asked, cannot tell two people apart in one
thread, and does not know which room it is in. Every answer is written as if it were a private
terminal session. This also silently disables R-CH-22 (owner-written per-channel instructions), since
there is nothing for them to attach to.

**Requirements:** R-CH-21, R-DIS-21 — both ✅ against the old build, both unmet.

**Previously:** carried in full — `where` (channel/server/thread), `called` (display name), and a
communication-agnostic `channel_name/id`, `channel_parent_name/id`, `channel_thread_name/id`
(`src_old/channels/discord:859-865`, `:1685-1717`).

Per D6 this rides in the **user turn**, not in instruction variables. It shares its composition site
with Phases 2 and 4 — attachments, replies and context are three blocks on one body — so doing them
in one pass is cheaper than three.

---

## Phase 6 — the rest of the Discord list

Ordered by value. Detail and citations in [`REVIEW.md`](REVIEW.md) §P3 unless noted.

- [ ] **6.1 No notice can be addressed to a person, and there is no newly-allowed-user greeting.**
  `delivery.notice` can only target the channel's `notify_place` (`delivery.py:77-87`) and the adapter
  parses `place` as a channel snowflake (`discord:1330`). R-CH-33's whole mechanism — greet each newly
  allowed user once, privately, in the agent's own words — is absent. R-DIS-39, R-CH-33. *Reported.*
- [ ] **6.2 The reply tint pings nobody in a fresh thread** (REVIEW P3.2). The first answer in every
  freshly-opened thread has no mention path, because `_quoting` drops the reference across channels
  (`discord:1404-1405`). Old put the mention under the stats line for exactly this case.
- [ ] **6.3 Room-by-name addressing** (REVIEW P3.5) — *"a schedule reports into #ops"* is not
  expressible. Pairs naturally with 6.1, since both are about naming a destination.
- [ ] **6.4 Gateway up/down notices lost their update wording and release link** (REVIEW P3.6).
- [ ] **6.5 Guild command sync** — commands take up to an hour to appear on a fresh setup
  (REVIEW P3.8). Small fix, disproportionate first-run impact.
- [ ] **6.6 `retry_after` is emitted and read by nothing** (REVIEW P4.6) — a rate-limited delivery is
  a WARNING and a lost message. Overlaps 1.1; do them together.
- [ ] **6.7 Slash surface** — `/agents` now exists as the approved private install-wide directory;
  `/help` still has no successor or note (REVIEW P3.7).
- [ ] **6.8 `--capabilities` is asked and thrown away**, so `max_text` is never negotiated
  (`commands/channels.py:427`, `:591-592`). Harmless for Discord (2000 == `MAX_TEXT`), **latent for
  any second adapter** declaring a smaller limit — every answer would be split at 2000 and refused
  wholesale. The comment at `commands/channels.py:424-426` claims the opposite of what the code does
  and is false. *Reported.*
- [ ] **6.9 `allowed_mentions` is never set** (`discord:1343-1344`), so a role mention echoed out of
  brain output pings for real. `@everyone` is inert only because `MENTION_EVERYONE` is absent from
  `PERMITS` — a permission accident, not a guard. **Not a regression** (old did not set it either),
  but it is a real ping-safety gap in a shared room.
- [ ] **6.10 Adapter constants carry the wrong docstrings** (`discord:146-176`) — the invite paragraph
  sits on `GOING_OFFLINE_WITHIN`, `SCOPES` has two unrelated paragraphs merged, `PERMITS` has none.
  Cosmetic, but in this file the docstrings are the reasoning of record.
- [ ] **6.11 `delivered` omits the documented `place` field** (`discord:1366` vs
  `docs/adapters.md:261`). Nothing reads it; fold into the Phase 7 docs pass.

---

## Phase 7 — make the documents true

Do this **in the same tasks** that change the code, per `AGENTS.md` definition-of-done 6 — not as a
cleanup pass at the end.

- [ ] **7.1** `docs/adapters.md:654-656` wrongly says `control`/`query`/`configure` do not exist, and
  `:352` says there are four `do:` kinds when there is a fifth (`answered`). A third-party author
  cannot implement slash commands from this page. *Verified.* (REVIEW P2.2)
- [ ] **7.2** The `arrived` table gains `reply_to` (Phase 4); the `bytes` row (`:306`) becomes true
  once 2.1 lands; the display-name bound row (`:555`) is restated per D3.
- [ ] **7.3** Cite requirement ids where met. This is the mechanism that turns the remaining uncited
  rows from silence into a decision (`docs/requirements/README.md:39-41`).
- [ ] **7.4** `README.md` still advertises Slack, `--kind`, `channels instructions` and
  `discord-dms`/`discord-rooms` — none of which exist. *Verified.* (REVIEW P2.1)

---

## How each phase is proved

`AGENTS.md` definition-of-done, applied to this work specifically:

1. **Every new guarantee gets a test watched to fail.** Break the code, run the suite, see red,
   restore **from a `cp` copy and never from git** — the working tree holds uncommitted work.
2. **The two untested halves are the point, not an afterthought.** `_brought` (2.4) and
   `a_verified_file` (3.4) are the adapter-side halves of two twice-verified contracts, and both
   defects found in Phase 2 live in exactly that blind spot.
3. **Run it for real** against a scratch `RUNDESK_HOME` and a scratch `--bin-dir`, never `~/.rundesk`.
   Check `ls ~/.rundesk` before *and* after. `./dev` scrubs the environment and refuses the real
   install.
4. **Attachment work needs a real Discord round trip** — a truncated download, a file over 32 MiB, a
   bot missing `ATTACH_FILES`. None of Phase 2 or 3 is provable from a green suite alone.
5. `python3 scripts/suites` on the 3.9 floor as well as current Python; read the `Ran N tests` line,
   not the word `OK`. `ruff check src tests scripts/suites rundesk` clean.

---

## Sequencing

```
Phase 1  honesty            ─┐ independent, start now, no decisions needed
Phase 2  inbound files      ─┘ (2.1 is the cheapest high-value fix in the plan)

D1 ─→ Phase 3  outbound files      ─┐
D2/D3/D4 ─→ Phase 4  replies       ─┤ 2, 4 and 5 share a composition site —
D6 ─→ Phase 5  who and where       ─┘ do them in one pass over the body

Phase 6  the rest           after the above; 6.1 and 6.3 pair
Phase 7  docs               inside every phase, never at the end
```

**Start with Phase 1 and 2.1.** They need no decisions, they are small, and 1.1 is a correctness bug
in the delivery path that Phases 3–5 all build on.

**Phases 2, 4 and 5 all compose a block onto the inbound body** (`hosting._also_attached` and its
neighbours). Doing them as one pass avoids three separate rounds of the same review.

---

## Risks

1. **The working tree is mid-refactor.** `src/rundesk/providers/instructions.py`, `turns.py`,
   `answering.py`, `commands/providers.py`, `commands/ask.py` and
   `tests/test_providers_instructions.py` are uncommitted. The refactor renames the prompt's
   `trigger=<name>` to `situation=<block>`, and **the test file still calls
   `instructions.build(trigger=…)` against a `build(*, situation=…)` signature** — so that suite is
   currently broken by in-flight work. Phases 3 and 5 land directly on those files. *Reported —
   confirm before starting.*
2. **D1 is a genuine design decision, not a detail.** Getting it wrong means either files that never
   attach or files nobody asked for being mailed into a chat room.
3. **grok's outbound path is unproven.** Whether a `create_file` update carries an absolute path is
   not established and needs a live probe; the repo's grok samples are read-only turns.
4. **Phase 1.1 touches the mark, which has burned this project before.** `hosting.py:993-1008`
   records a previous race where two producers disagreed about the same run. The fix must keep one
   producer.

---

*Prepared read-only against `568731e`, with uncommitted changes in the tree. `~/.rundesk` untouched.
No code written.*
