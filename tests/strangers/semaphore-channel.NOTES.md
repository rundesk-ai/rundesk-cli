# NOTES.md — writing `semaphore-channel` against `write-a-channel-adapter.md`

Blunt, as asked. The guide is unusually good at *why*; it is thin on *what exactly*.
Most of what follows is the same complaint: everything Rundesk sends me is
specified by example only, and examples are not a schema.

## Outright contradictions

**1. Does `answer` come before or after `state: finished`?** The example on lines
104–107 puts it before:

```json
{"type": "answer", "conversation": "1180", "run": "7-a3f1", "text": "Three files changed — the parser was dropping…"}
{"type": "state",  "conversation": "1180", "run": "7-a3f1", "state": "finished"}
```

The state table says the opposite:

> | `finished` | it worked, and **the answer is on its way** |

"On its way" means it has not arrived yet. Both cannot be true. This matters: an
adapter that posts the answer on `finished` posts nothing under one reading, and an
adapter that tears down per-run state on `finished` drops the answer under the
other. I assumed neither ordering — the answer is posted when `answer` arrives,
marks are applied when `finished` arrives, and per-run state is only used for marks.
Say which it is.

**2. Is `RUNDESK_CHANNEL_HOME` set during `--check`?** "All four are always set"
appears under *Question two*, so on the face of it the environment table only
applies to the run. But `--check` is where I am told to verify the credential, and
"Look in both places" tells me the second place is a file inside
`RUNDESK_CHANNEL_HOME`. So the one moment I am supposed to prove the credential is
good is a moment where I may not be able to see where half of it lives — meaning
`--check` can pass on the terminal's exported variable and the channel can still be
deaf forever in the exact deployment the section is written about. I read
`RUNDESK_CHANNEL_HOME` at check time if it happens to be set. Please state
explicitly whether it is.

## Guessed, because the spec does not say

**3. The shape of the `--check` command line.** "Run with `--check`, followed by
whatever options the owner typed" versus "Everything after `--` on the command line
reaches you exactly as typed" plus the example `... --allow 2207 -- --space 9930
--room 1180`. Am I invoked as `adapter --check --station 4471` or `adapter --check
-- --station 4471`? I had to re-read this three times and still cannot tell. I
accept both (strip a leading `--`). If Rundesk actually passes the `--` through,
say so; if it strips it, say that.

**4. Exit code when `ok` is false.** The spec gives an exit code for exactly one
case: "print one JSON object, exit `0`". Nothing about the refusal path. I exit 0
always, on the grounds that the object is the payload and a non-zero exit invites
someone to ignore it. That is a guess and it is the kind of guess that produces two
adapters behaving differently.

**5. `secret` has no way to name a file.** The spec shows `{"env": "MY_TOKEN"}` and
that is the only shape given — yet the same document insists my real credential
source in production is *a file inside `RUNDESK_CHANNEL_HOME`*. There is no
`{"file": ...}` form documented, so I declare `{"env": "SEMAPHORE_TOKEN"}` and read
the file anyway, silently. Whatever UI shows "present without being shown" will
therefore show the wrong thing when the token came from disk. Also: no filename is
specified for that file. I look for `token` then `semaphore.token`. Two adapters
will pick two names and owners will have to guess.

**6. Is `secret` required?** The table lists four keys; the worked example at the
bottom of the page returns only `ok`, `settings` and `describes`. Not stated which
are mandatory.

**7. `RUNDESK_SETTINGS` encoding.** "the object your own `--check` returned, handed
straight back." An environment variable is a string. JSON-encoded, presumably. Never
said.

**8. `arrived.direct` is never defined.** It is in the "may have" column and that is
the entire documentation. Direct message? Addressed-at-the-agent? Not-in-a-thread? I
omitted it. If it changes Rundesk's behaviour at all, omitting it is a silent
behaviour change and I have no way to know.

## Everything on stdin is specified by one example line

This is the biggest gap. There is a precise table for the four records I *emit*
("must have" / "may have"), and nothing at all for the seven record types I *receive*.
I reverse-engineered from the block on lines 101–107. Specifically unanswered:

- **`tool.did`: `"run"`.** What is this? A verb, a phase, a status, free text? Is
  there a closed set? I show it verbatim next to the tool name because I cannot
  responsibly interpret it.
- **`state.why` on `failed`** is mentioned only in prose ("`why` says what went
  wrong") and never appears in any example record. I assumed the key is `why`.
- **`can`** shows one key, `steer`. Are there others? Is `can` present on every
  `state` or only on `taken`? I cache it per conversation from `taken` and treat
  an absent `can` as permissive.
- **`result.summary` / `result.ok`** — optional? `ok: false` vs `ok` absent are
  different things and I had to invent a display for each.
- **`run`** — assumed unique and stable per turn. Nothing says whether two runs can
  be live in one conversation at once; if they can, my per-conversation `can` cache
  and my "last ref" fallback are both wrong.
- Is `conversation` guaranteed on every record? Every example has it; nothing
  promises it. I guard for its absence.

## Things I expected to be told and was not

**9. What "running … said again from time to time for anything that lapses" means.**
What lapses? A typing indicator, presumably — but the same page tells me a surface
without one simply never types, and Semaphore has none. So for my surface `running`
is a record with no representation at all. If something on Rundesk's side lapses
without it, I need to know; if not, say that `running` is purely cosmetic.

**10. No throttling guidance for a surface that cannot edit.** "If your platform can
edit a message, edit the running commentary; never the answer" and "one that cannot
edit posts again instead." Semaphore cannot edit. Taken literally, a forty-tool turn
becomes forty chat messages, which is not a first-class channel, it is a denial of
service against the conversation. I coalesce commentary into one post every 5
seconds. That number is mine, invented, and every adapter author will invent a
different one.

**11. Nothing about `ready` and ordering.** Is Rundesk allowed to send me `state`
records before I emit `ready`? Must `arrived` come after `ready`? Is re-emitting
`ready` after a `gone` expected (I think yes, from "say `gone` when you lose the
connection and `ready` when you have it again")? Is a duplicate `arrived` for the
same `ref` deduplicated, or does it dispatch twice? That last one decides whether a
reconnect that replays history is safe. It is not answered, and "a reconnection
finds the conversation it already had" in the test list implies somebody thought
about it.

**12. `forget` never appears in an example**, and there is no list of valid
`control` values — only two named in prose. Nor is it said what happens to a
`forget` when no turn is running: "what a control did comes back as the turn's own
outcome" cannot be true if there is no turn, so the user who typed it gets silence
and I am explicitly told not to acknowledge it with an outcome. That is a real hole
in the UX and the spec waves at it.

**13. Presence.** "set it when you connect and clear it on the way out" — Semaphore
has none, so this is a no-op here. Fine, but worth noting the guide's advice
degrades to nothing on the surface I was given.

## Where the Semaphore brief itself fights the guide

Not the guide's fault, but it blocks a clean implementation:

- **I cannot identify my own posts.** `semaphore check` returns the *station's* name,
  not the adapter's user id, and `listen` gives me `from` for every message with no
  way to know which one is me. If Semaphore echoes my own `send` back on the stream,
  a naive adapter loops forever. I suppress by matching `(flag, body)` within 120s,
  which is a hack. The real fix is `semaphore check` returning the caller's own id.
- **Message bodies go on argv.** `semaphore send --flag X --body <text>` documents no
  stdin or file input, so every agent answer is visible in the process list. The
  guide reasons carefully about exactly this hazard — "anything on a command line is
  readable through the process list" — for credentials, and then the platform forces
  me to do it with content. Also: no documented maximum body length (I chunk at 3000
  chars, arbitrary), and no stated behaviour for a body beginning with `-`.
- **Marks are one-way and their semantics are unstated.** Can a message hold both
  `eyes` and `tick`? Does a second `mark` replace the first or add to it? Is there an
  unmark? I mark `eyes` on `taken` and `tick`/`cross` on completion, which is either
  a clean progression or an accumulating pile of three markers depending on an answer
  I do not have.

## Smaller

- "A record we do not recognise is kept, not refused" is stated for records I emit.
  Nothing says what I should do with an inbound record type I do not recognise. I log
  and skip.
- No guidance on stdout line length limits or what happens if I emit a non-JSON line.
- The verification suite is a `git clone` of a repo I was told not to fetch, so the
  claim "the same suite every shipped channel passes" is untested here. The closing
  line — "if your adapter follows this page and the suite still fails, this page is
  wrong" — is a good norm and completely unverifiable from where I sit.

## Verdict

I could write a working adapter from this page alone, and that is a real
compliment — the *shape* of the contract (two questions, four outbound records,
"you are told; you show") is clear on one read. But every decision I had to make
under uncertainty was about a field, an ordering, or an exit code, and all of them
would have been settled by one schema table for the stdin side and three sentences
about `--check`'s argv and exit code. As it stands, two competent authors writing
against this page ship adapters that disagree.
