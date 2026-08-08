# Research: what moved between the versions the brain notes describe and the ones that ship

**Date:** 2026-08-06
**Question it answers:** The three brain notes in this directory were carried across intact from the
previous build and none had been re-driven. Two of those brains now have shipping adapters. What did
the re-probe find that the notes get wrong?

The notes themselves are **not rewritten**. That is the point of this directory: a research page is
true of what it was measured against and says so, and correcting one in place would destroy the
record of what was believed when. Read them for the reasoning; read this for what is current.

| Brain | Note describes | Adapter shipped against |
|---|---|---|
| Claude | `claude 2.1.219` / `2.1.220` ([note](2026-07-26-claude-cli-as-a-brain.md)) | **2.1.223** |
| Grok | `grok 0.2.111` / `0.2.112` ([note](2026-07-26-grok-cli-as-a-brain.md)) | **0.2.118** |
| Antigravity | `agy 1.1.8` ([note](2026-07-28-antigravity-cli-as-a-brain.md)) | **not shipped** — the CLI is not on this machine and nothing here was re-probed |

Everything below was driven against a real account on 2026-08-06 and the streams kept; the scrubbed
captures are in `tests/samples/` and named in [`cli-versions.lock`](../../cli-versions.lock).

---

## Claude — three findings the note gets wrong at 2.1.223

### The reply arrives twice, not three times

The note says the reply comes back three ways — as `text_delta` fragments, as whole `assistant`
blocks, and again in `result.result` — and treats picking one as the central decision.

**Measured:** without `--include-partial-messages` there are **no `stream_event` lines at all**. One
turn produced exactly `system/init`, `rate_limit_event`, two `assistant`, one `user`, one `result`.
The reply arrives twice, and the shipped adapter takes the whole `assistant` blocks.

This matters beyond the count. The capture the previous build kept was taken **with** that flag,
while the adapter never passed it — so the fixture proved a de-duplication against an argv nothing
built. The capture that ships now is taken with the exact arguments `opening()` produces.

### `tool_result_meta` is gone

The note describes telling a tool cancelled by an interrupt from one that genuinely failed by reading
`tool_result_meta[].non_execution_kind == "user-rejected"`.

**Measured:** at 2.1.223 an interrupt produces a `tool_result` with `is_error: true` and
`tool_result_meta: null`. The field the previous build filtered on is not sent.

So the only thing left that distinguishes them is that **an interrupt is pending**, which is what the
shipped adapter uses — and why it is deliberately narrow: outside a steer, a failed tool is reported
as the failure it is. Anyone restoring the metadata filter should check whether the field came back
rather than assume it did.

### `error_during_execution` means two different things

The note treats that subtype as the signature of a conversation the brain has forgotten, detected
together with `no conversation found` on stderr.

**Measured:** an *interrupted* turn ends with exactly the same subtype. The distinguishing prose is
on stderr and nowhere else, so **both streams have to be read before either is acted on**. An adapter
reading only the `result` line would either retry every steered turn or never retry a lost one.

### Confirmed unchanged, and worth keeping confirmed

- `result.usage` is a bill and not a turn: two requests reported **40,328** cache reads where the
  conversation ended on **25,046**. The input side must come off the last `assistant` line.
- `modelUsage` names **two** models — a small one runs beside the one asked for — so the answering
  model is read off `system/init`.
- The allowance event carries a status, a window name and a reset time, and **no number of
  anything**. There is still nothing to put in `percent_left`.
- The control protocol still works: `initialize`, then `interrupt` → acknowledgement → the
  interrupted `result` draining → the replacement. Two `result` lines for one steered turn.

### New, and not in the note at all

**A brain that can be steered never ends on its own.** Holding its input open is what steering is, so
after it answers it waits for another word while the reader waits for a stream that will not close.
Each waits for the other. The turn hangs until rundesk's silence window ends it half an hour later
with nothing written down. The adapter closes the brain's input the moment the turn ends.

---

## Grok — two findings the note gets wrong at 0.2.118

### `cacheCreationTokens` exists

The note says there is no cache-*creation* figure at all and that the field is therefore left out
rather than guessed.

**Measured:** `turn_completed.usage` carries `cacheCreationTokens` beside `cachedReadTokens`. The
shipped adapter reports it when the brain reports it. It was `0` on the captured turns, which is
exactly why this needs saying: a reading that omits the field and a reading that reports zero look
identical on a turn that wrote no cache, and only one of them is right.

### A resumed turn's usage is its own

The note does not settle whether a carried-on turn reports its own cost or the conversation's running
total — which is the question that decides whether anything must be subtracted.

**Measured:** turn two of the same conversation reported `inputTokens: 6502` where turn one had
reported `12472`. It is the turn's own share, so **nothing is subtracted** — the opposite of the
shipped codex adapter, whose brain reports the other way round.

### Confirmed, including the one that had shipped broken twice

- **`inputTokens` still contains `cachedReadTokens`.** One turn made two model requests of 6,156 and
  172 fresh input against 6,144 cache reads and reported 12,472 — which is 6,328 + 6,144. Passing it
  through as sent bills the cache twice at the standard rate.
- **The agent profile still scopes a turn, and the command line still does not.** A turn opened with
  a read-only profile and asked to run a shell command answered `NO SUCH TOOL` and called nothing.
  This is the guarantee that shipped broken twice in the previous build, and it holds.
- `--no-memory` is still required. `session/load` still replays the previous turn's updates,
  `turn_completed` and all.

### New, and not in the note at all

- **A tool's name changes between its call and its update.** A call starts as `read_file` and is
  updated to ``Read `note.txt` ``, and the **terminal** update carries no name at all. A table keyed
  on the readable title stops matching the moment the vendor makes its titles friendlier, so the
  adapter keys on `_meta["x.ai/tool"].name` and a synthesised tool record is nameless rather than
  mislabelled.
- `_meta["x.ai/tool"]` also carries `kind` and `read_only`. Only the value `read` was observed, so
  nothing is mapped from it yet — a vocabulary one sighting long is not a vocabulary.
- This machine's session loaded **92 MCP tools** from the owner's own configuration, which is what
  naming `search_tool` and `use_tool` to `disallowedTools` was always guarding against.

---

## What is still unprobed

- **Everything about Antigravity.** `agy` is not installed and no adapter ships. Its note remains the
  only account of it and describes 1.1.8.
- **Grok being steerable.** Never measured, so the adapter says `steer: false` — which is a statement
  about evidence and not about the protocol.
- **Every failure of either brain.** Provoking a spent allowance or a revoked credential means
  abusing an account, so the failure fixtures in `tests/samples/` are the vendor's documented shapes
  and not captures. What they prove is the mapping, not the wording.
