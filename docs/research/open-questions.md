# What the previous build never answered

Collected 2026-08-04 out of the `Open questions` section of every contract and draft contract in
`.knowledge_old/prd/` and `.knowledge_old/prd-drafts/` — gitignored, reference-only, and expected to
be deleted with the rest. These are not measurements and not decisions. They are the questions that
build wrote down and shipped without settling, which makes them the cheapest thing on the shelf:
**this build will reach every one of them again, and reaching a question you have already seen
written down is a different experience from discovering it in production.**

Each is reworded only enough to remove that build's requirement ids and its retired vocabulary.
Where a question has since been answered, or where this build has already chosen differently, that
is said under the question rather than by deleting it — knowing which questions were open is part of
what this page is for.

**The ten dated research notes keep their own open questions**, which are about the outside world
rather than about this product, and they are better read in place. Nothing from them is repeated
here.

---

## About an agent and what it loads

**Which of an agent's files each provider is proven to *load*, rather than merely to find.** The
previous build probed this once and found that only the files named after a provider are picked up
where they stand, that one CLI expands an `@import` and the others do not, and that a bare `skills/`
directory is discovered by nobody. The measurements are in
[`2026-07-27-skills-a-brain-discovers.md`](2026-07-27-skills-a-brain-discovers.md) and
[`2026-07-26-claude-cli-as-a-brain.md`](2026-07-26-claude-cli-as-a-brain.md), and they are true of
July 2026 versions. Half of the question was settled: **a turn must stand in the agent's home,
beside the files scaffolded for it.** Before that it stood one directory *below* them, so an agent
asked who it was answered, truthfully, that there was nothing there to tell it — the scaffolding was
written and out of reach of the only thing meant to read it. What stayed open is the other half, and
it is two questions: whether a provider standing there actually loads what stands beside it, and
what it makes of the *owner's* own files, which stay reachable because `HOME` is deliberately still
the owner's.

**Whether agents share the owner's provider sign-in or each holds its own.** Redirecting a
provider's home isolated its credentials too, so two agents needed two sign-ins — a cost worth
stating before it is chosen rather than discovered. This one now has numbers against it rather than
an answer: on two of the three brains a private home can hold a copied or symlinked credential, and
on the third a private home cannot be signed in at all without a browser, because setting the
variable *removes* the login rather than redirecting it. So "each holds its own" is not uniformly
available, and "share the owner's" is a decision somebody has to make out loud.

**Whether what a run recorded belongs with the agent or with the gateway that admitted it**, and
**where the product's own account of itself stands** now that everything else belongs to an agent.

**Whether a skill or a specialist definition should be grantable per agent** rather than available
to every agent on the install.

---

## About records, cost and retention

**How long an account is kept, and whether an owner or a size decides.** Asked three times
independently, in three different contracts, and never answered once.

**Whether an account records what a brain was *sent*, or only what it reported back**, and what is
read back when the brain's own session files are gone but the account remains.

**Whether removing one schedule takes the runs it produced, or leaves them as history.** And whether
a run that started no brain at all — a scheduled program, say — is recorded as a run.

**Whether what a brain printed verbatim is deleted on a schedule, on a size, or only when asked**,
given it is deliberately kept apart from the account so that it *can* be thrown away without taking
the account with it.

**What a turn's share of a running total is after a restart lost the total it was reporting
against.** The contract answers what an adapter should do; nothing answers what the record should
say.

**Where prices come from, and what a cost says when the model that ran has no price on record** —
and whether a provider that names no model leaves a run's cost attributable at all.

**Whether an owner should be able to stop an agent that has cost too much, and what decides "too
much".**

---

## About migrations and what is on disk

**What happens to an agent whose records cannot be read at all when every other agent's can.** The
build stopped a whole sweep at the first failure and recorded that as a mistake; what it never
decided is what the *right* thing is for the one that failed.

**What becomes of something an earlier release left behind that belongs to no agent**, given nothing
outside an agent carried a version to move it under.

**What a migration does with the raw files a run references**, given they are allowed to be
destroyed and a migration cannot recreate one.

**Whether a machine that never updates, only reinstalls, needs any of this.**

---

## About the gateway and the machine

**Whether an owner may ask a gateway to stop without waiting for work in flight to finish.**

**Whether a program the gateway was running is started again when it fails**, given that repeating a
turn repeats whatever that turn already did to the machine.

**How often a gateway may be started before the product treats *starting it* as the fault**, rather
than whatever it is starting for.

**What a gateway that has no agent should do after long enough.** Nothing takes one away on its own,
and nothing says how long is long enough.

**Whether an agent whose gateway will not start is reported as the agent failing or as the gateway
failing.**

**What a receiver may conclude from the order of two things a program said on two different
streams.** Within one stream there is an exact order; between the two there is none at all, and
nothing outside the program can supply one — a timestamp stamped on arrival is when *we* read it,
not when the program said it. Anything needing the two related has to take that from inside what it
is parsing.

**Whether how long a program may say nothing, and how long it may run at all, are fixed for every
program or set per kind of program.** The numbers the previous build chose, and the reasoning behind
each, are in [`the-adapter-contracts.md`](the-adapter-contracts.md).

---

## About schedules

**Whether the time a schedule is stated in is ever anything other than the machine's own.** It was
the machine's, which is what makes an hour that repeats — the clock going back — a thing to survive
rather than to avoid.

**Whether two commands changing one gateway's schedules at once should wait for each other or
refuse.** Waiting is what they did, and neither was told it had waited.

---

## About surfaces

**Whether an adapter is told which of its abilities the product will use, the way a brain is
asked.**

**Whether one agent may be reached on two surfaces at once**, and what that does to a conversation.
And whether a conversation may ever *span* two surfaces, and what joining two of them would mean.

**Whether a surface may refuse a turn outright, and what an owner sees when it does.**

**Where an adapter that is not on the machine is reported** — by a diagnosis command, at setup, or
both.

**Whether a channel can be turned off and left in place, the way a schedule can.** What is kept has
somewhere to say so, and no command offered it.

**Whether a mark between "seen" and "finished" is worth having for a turn that runs a long time**,
and whether showing work as it happens is one decision or each surface's own.

**Which of an agent's activity belongs where everybody can read it and which belongs to the owner
alone.**

**Whether more than one person may steer the same agent in one thread, or only the one who started
it.**

---

## About the values a program is given

**Whether an owner may run a program under those values from their own terminal**, given such a
program can print one back.

**Which name endings count as plainly a credential, and whether an owner may extend that set.** The
reason that list exists at all is worth keeping with the question: the list of what is *dangerous*
can never be finished, because every new brain and every new integration brings its own runtime's
variables — so what an agent may place is stated positively instead, as a small list of what is
plainly a secret.

**Whether the length of a kept value may be shown beside its hint.**

**How often a value produced by running a command is produced, when many programs start at once.**

---

## About handing work to somebody else

The previous build had two shapes of this — one agent asking another, and an agent putting on a
shared specialist definition. Both are unbuilt here, and the questions transfer whole.

**Nothing tells an asking agent which agents this install has, or what each is for.** There was no
description on an agent as there was on a specialist definition, so an agent learned the verb from
the help output and the names from nowhere.

**Whether a turn woken to review delegated work may delegate again.** It was legal on one path and
refused outright on the other, which is two answers to one question.

**Whether a stopped delegation should be resumable**, or whether stopping should be the one ending
that closes an ask for good.

**Whether an agent should run a delegated turn while already answering somebody on a channel.** It
could, and two concurrent turns could both write the same memory file. That last clause is the whole
problem in one line.

**How a worker proves which turn it belongs to**, given that the only identity a child process
carries is one it can change.

**Where a worker's skills should be presented**, given that every adapter places them beside the
directory it stands in, and a worker stands in the owner's project rather than in the agent's home.

**Whether the several timing windows should be configurable per install** rather than staying module
constants.
