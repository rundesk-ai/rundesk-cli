# The brain behind a turn

A provider is a **program Rundesk runs**, never code it loads. Rundesk owns the turn — what was
asked, what it was told, what it cost, and what became of it. The provider owns the model, the
context, caching, compaction and tool execution.

The verbs are [`../api/providers.md`](../api/providers.md); the adapter contract, and what a turn is
from the adapter's side, is [`../extending/providers.md`](../extending/providers.md). What every turn
is told is [`instructions.md`](./instructions.md).

## No module here names a vendor

Nothing in the core knows what `codex` or `claude` is. A bare name resolves among the adapters that
ship and then among the ones this install was given, in that order — a release's own adapter is what
somebody gets by typing its name, and an install cannot quietly shadow it. Anything with a separator
in it is used as a path, so an adapter being written right now needs nothing installed anywhere.

Vendor facts live in the adapters and in `cli-versions.lock`, which records which vendor CLI version
each shipped adapter was written against and the captured stream that stands in for it, so no suite
needs an account or a network.

**Absent means no.** An adapter that answers `{}` to `--capabilities` can do none of it, which is a
complete and honest answer rather than an error: a plain conversational CLI is a first-class brain
here, not a degraded one.

## One turn at a time in one conversation, and the kernel says so

A turn takes an exclusive `flock` on the conversation's own lock and **hands the descriptor to the
adapter**. The lock belongs to the open file description, so it lives exactly as long as the adapter
and everything it started, and the kernel drops it however they end.

Three things fall out of that:

- **A second turn cannot begin in a busy conversation, across processes.** `rundesk ask` at a
  terminal and a gateway answering a channel compete for the same lock correctly, with no
  coordination between them.
- **It refuses rather than queues.** A conversation already being answered in is busy, and says so.
- **Nothing has to be tidied up after a crash** for the answer to become correct.

The order is fixed: claim → resolve → write down what was resolved → compose → run → write down what
it said → keep where the conversation got to → settle.

## What an adapter is told, and what it is not

An adapter is a program, so there is no object to hand it: what a turn *is* arrives as environment
variables, the prompt arrives on its input, and what the brain did comes back on its output.

| Variable | Carries |
|---|---|
| `RUNDESK_AGENT`, `RUNDESK_RUN` | whose turn this is, and which one |
| `RUNDESK_CWD` | where the turn stands |
| `RUNDESK_PROVIDER_HOME`, `RUNDESK_PROVIDER_ALIAS`, `RUNDESK_PROVIDER_ACCOUNT_HOME` | the provider-owned home this turn uses |
| `RUNDESK_MODEL` | the model asked for, or unset |
| `RUNDESK_RESUME` | the handle this conversation reached last time on this brain, or unset |
| `RUNDESK_ACCESS_MODE` | read-only, or not |
| `RUNDESK_COMMAND` | the absolute `rundesk` for this install |
| `RUNDESK_SKILLS`, `RUNDESK_SETTINGS`, `RUNDESK_PREFACE`, `RUNDESK_CONTINUITY`, `RUNDESK_RAW` | what it may read, and where its account goes |
| `RUNDESK_DELEGATION` | set when this turn is answering one |

**What is absent is as deliberate as what is there.** No vendor variable, because which one a brain
wants is that adapter's business and putting it here would put the vendor in the core.

**Anything left out is left unset, never set to nothing.** An adapter asked for a model called
empty-string does something odd with it; one told nothing falls back to its own default, which is
what `${RUNDESK_MODEL:-default}` is written expecting.

**The environment is built from nothing, never inherited.** The alternative — copy this process's
environment and strip what should not go — is a list somebody has to keep true for ever, and a
comparable product had to retrofit exactly that after handing a coding subprocess every credential it
held. An owner's own value may never take a name Rundesk decided, **including the names Rundesk
decided to leave unset**.

## Accounts are named, never held

An alias is only a name and a private provider-owned home. Rundesk never opens anything inside that
home: the adapter's own login, status, logout and turn processes are the only readers and writers.
Directory existence *is* the registry, so there is no second index to disagree with it. `default` is
reserved, and an omitted alias means the provider's ordinary account.

## How a turn settles, and the three counters that say a vendor moved

A turn is one row, written at admission and settled once — so a turn that died before it reached the
brain still shows what somebody asked for. `working` means nothing has settled it, and it is never a
terminal answer; the terminal ones are `done`, `stopped` and `failed`.

| Counter | Counts | Means |
|---|---|---|
| `UNKNOWN` | records this release did not understand | the adapter and its brain have drifted apart |
| `LOST` | records that never arrived | the same |
| `UNSENT` | words Rundesk could not put *into* a turn | usually somebody steering a brain that had already finished — an ordinary race, and the words stay durable for the next turn |

Both of the first two are zero on a healthy turn, and nothing else in the product will tell you
before somebody notices an agent behaving oddly. `UNSENT` shared the `LOST` column until agent step
`0013`, so a person typing one word too late used to look exactly like an adapter coming apart.

**`model asked for` and `model reported` are two facts.** The first is what the turn was admitted
with; the second is what the brain said actually ran. A dash under the second means the brain named
none, which is not the same as none having been chosen.

## What is written down, and what is swept

| Table | Holds | Swept |
|---|---|---|
| `turns` | what one was admitted with, what it came to, what it cost | no — it is history |
| `turn_records` | what it *did*, in order | yes — it is diagnostic, and `turn-records-days` sets how long |
| `provider_sessions` | where one conversation got to on one brain | no |
| `lifecycle_continuations` | one lifecycle result owed to one conversation | at most once, transactionally |

A provider session has three columns because a session belongs to a **conversation and a brain**, not
to a model — which can change under a resumed session without invalidating it. Its instruction
boundary is the fingerprint on that provider's latest turn, and a changed fingerprint makes the
opaque handle stale.

Every run also leaves `raw.jsonl` and `stderr.log` under the agent's own `providers/<run>/`
directory, which is what makes a turn that behaved strangely inspectable afterwards.

## When a turn is not doing what you expected

| What you see | Usually |
|---|---|
| a turn refuses immediately | the conversation is busy — something else holds its lock |
| `UNKNOWN` or `LOST` climbing | the vendor CLI moved under its adapter; compare against `cli-versions.lock` |
| the model reported is not the one asked for | the brain chose; `rundesk turns <agent> <turn>` shows both |
| a resumed conversation starts fresh | the instruction fingerprint changed, so the stored handle went stale |
| an adapter reports nothing at all | run `rundesk providers check <provider>` — it asks offline and needs no account |
