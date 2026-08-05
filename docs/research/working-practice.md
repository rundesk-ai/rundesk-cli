# How the previous build wrote things down, named things, and moved things

Distilled 2026-08-04 from the previous build's writing standards and project how-tos — gitignored,
reference-only, and expected to be deleted. The documentation system those standards governed is not
this build's and is not carried across; what is carried is the small number of rules inside them
that are about *how to work* rather than about where a file went. Every one of them was written
after something went wrong, and several of them are why the pages in this directory are shaped the
way they are.

Nothing here was measured. It is that build's own practice, read off its guides, and it is offered
as practice rather than as fact.

---

## Writing a research note

Everything in this directory is a research note in the sense that build meant, so its rules apply to
what gets added here next.

**Report the world, then say what you think — never both at once.** The reporting section is
reporting; the borrowing, the avoiding and the verdict are yours. Keeping them apart is what stops a
thought becoming a borrow, then a verdict, then a requirement, with nobody noticing where it
entered. The mechanism that enforces it is **sourcing at the point of claim**: every non-obvious
statement in the reporting section carries a citation, so anything uncited is visibly yours.

| The urge | Where it goes |
|---|---|
| Say what they should have done | the avoid section |
| Say what we would do about it | the verdict |
| State our own design position | the verdict — never inside the reporting |
| Say what the product must do | nowhere here; tell the owner |
| Say what you could not find out | open questions, one line |

**A note is input, never truth.** The path is `research → somebody reads it → somebody states a
requirement → the requirement is written down`, and never `research → requirement` directly. A note
informs a decision and is not one.

**"Last updated" is the date the whole note was last re-read against its sources**, not the date the
file was touched. Updating means re-reading, not patching: fix one section, re-stamp the date, and
every stale paragraph beside it now looks fresh. Change a note when its sources actually moved —
never to reword.

**Cite the specific page you read, not the vendor**, keep the real link, and never cite a source you
did not open. A source blob at the top is not sourcing, and a URL that resolves is not the same as a
source that supports the claim.

**Open questions are honest to have many of.** One line each. A note with none is usually a note
that stopped asking.

---

## Writing down friction

The previous build kept a friction log — the traps hit in that codebase and the workaround for each
— and four of its rules are worth more than the log was.

**Write it at the moment of pain, not at the end of the task.** A workaround stays obvious for about
five minutes; after that it stops feeling worth writing down, and the task finishes with somebody
genuinely believing they hit nothing. Every entry that never got written was lost exactly that way.

**The test for whether something is friction: did it cost you an attempt?** If a command failed and
the fix was *knowledge* rather than a code change — an ordering, a flag, a guard to satisfy, a
second run — that is friction, and the next person loses the same attempt unless it is written down.
Do not wait for something dramatic; the ordinary case is a one-line workaround found in ninety
seconds and forgotten by the end of the day.

**It is a living list, and it is the one document that shrinks as a project matures.** When friction
is genuinely solved — fixed in code, or made impossible by a guard — delete its entry. A long
friction log means something was solved and never pruned. If a trap hardens into a permanent rule,
it graduates into the rules file and leaves.

**Never record the absence of friction.** No "none hit this task", no dated all-clear. A task that
hit nothing leaves the file untouched and says so in its reply.

**It is committed and world-readable, so it carries no personal information.** Describe the failing
thing generically; refer to people by role.

---

## Writing a rules file

Three rules from that build's standard for its own `AGENTS.md`, all of which are about the failure
mode rather than the format.

**A rule that routes an obligation through a mechanism must say what happens without the
mechanism.** This is the defect that testing found most often, and it fails silently: the obligation
is not flagged, it simply disappears, because somebody hitting the uncovered case copies whatever
the codebase already does — and the codebase is usually where the hole came from.

```
❌ Authorize in the policy via the form request.
   → an action with no input has no form request, so it ships with no authorization at all
✅ Every state-changing route is authorized — no exceptions. With input, authorize in the form
   request via a policy; without input, call the policy directly.
```

Write the critical ones — authorization, money, data loss, privacy — as **"no exceptions" first and
*how* second.** A rule phrased as a mechanism is only as complete as the mechanism.

**If a rule is mechanically checkable, put it in the gate.** A checkable rule left as prose is the
first one skipped. In that build's own testing, the one styling rule stated only in prose was missed
by every agent who read the file, while the rules the check enforced were followed without
exception.

**Reading a codebase surfaces the rules it *shows*, and three kinds never appear in it.** A rules
file written only from research looks finished while omitting the rules the owner cares most about:
rules the code already obeys perfectly leave zero trace, so searching for the violation finds
nothing; rules describing an intended pattern not built yet look like an empty directory; and
workflow and taste live only with the owner. End by naming what you inferred against what you
guessed, and ask about the gaps.

---

## Naming, and the overlaps worth removing

That build's command surface is not this one's and is deliberately not carried across. Four of its
naming rules are about words rather than about verbs, and they survive the surface being replaced.

**One name means the same thing everywhere it appears.** Its gateway verbs took `<name>` while
everything else took `<agent>`, for the historical reason that a gateway had once been the subject.
The subject was the agent, and the argument had to say so.

**A thing you make is named by you, and described by options.** `add <schedule> --when …` and `add
<channel> --kind …` are the same shape; an earlier draft had `add <kind>`, which made the slot after
`add` mean the *type* on one verb and the *name* on another.

**`[--flag]` for what is optional to pass, `<value>` for a value you supply** — never both marks on
one token.

**Leaving the word out is not how you say "all of them" — it is not saying.** The incident behind
that, where a bare restart cycled every gateway on the machine, is in
[`the-old-build.md`](the-old-build.md). The rule is the general form: an omitted argument means the
command was incomplete, never that it applies to everything.

And one that is about design rather than words: **an overlap is resolved rather than lived with.**
Every pair that meant nearly the same thing was collapsed into one, and the reasoning was recorded,
because recording it is what stops the second one coming back. The sharpest instance is worth
keeping: a distinction that needs a paragraph to explain is one a consumer will get wrong.

---

## Moving readers onto a new store

The previous build did this once, moving a directory of JSON files into a database, and paid for six
things in the doing. They are the durable half of a guide whose specifics are gone.

**If the design turns out to be wrong, the contract moves first.** The point of designing a store
before pointing anything at it is that the pointing does not discover the design while building it.
A surprise is a finding against the contract, not a special case in the code.

**Wire and prove the runner on the release that has nothing to carry.** The version that *does* have
data on real machines must not be the one that discovers the wiring.

**A component need not learn what holds its records.** Hand it a store and let it refuse in its own
words, so it imports neither the store module nor the database driver — which is what keeps "no SQL
outside the one module that owns it" true for *exceptions* as well as for queries. Before that, a
corrupt database raised the driver's own error straight through every command.

**When the units change, make the wrong comparison inexpressible rather than merely discouraged.**
One value had been a float of seconds since the epoch, the store held an ISO string in UTC, and a
schedule's own field was local time. The conversion was put in exactly one place, returning
something timezone-aware, so comparing two clock faces directly cannot be written rather than being
something to remember not to write.

**Never merge two keys that might have been one thing.** A real install held a conversation keyed by
a provider's own session handle, because somebody had once passed one where a name was expected.
Nothing in the data can prove two keys were one conversation, so minting one conversation per
distinct key is the only honest move — guessing silently joins two histories, and nothing afterwards
can tell they were joined.

**Whatever a reader used to report, it must go on reporting after it moves.** A schedule that could
not fire, a channel that could not connect, an account that could not be written — the rule to hold
is that one agent's log tells the whole story of that agent, and no part of that story is only in a
caller's return value.

---

## Keeping a checkout away from the live install

The previous build needed a whole page for this because it read a dozen location variables and a
launchd label that no directory redirect could isolate. This build has one root, so most of that
page is gone with the defect it described. Three things survive it.

**A turn's shell is a gateway's child, so a checkout run from inside one inherits the live install's
environment.** That is the surprise, and it is the ordinary case rather than an edge one: an agent
asked to try something in a checkout is running new code against the owner's own data, having asked
for nothing of the kind. Check the environment before believing otherwise.

**Unset every inherited variable rather than only the ones that look dangerous.** One kept "because
it seemed harmless" is the whole failure. And **put an override *after* the scrubber, not before
it** — a prefix that sets a variable and then scrubs it takes it away again, and the fallback wins
silently. That one is measured: it wrote a real credential into the owner's live install while
reporting an ordinary success, and nothing in the output named the directory it had used.

**Check the destructive half from both ends.** `ls` the live location before and after anything that
uninstalls or purges, and confirm the scratch location actually has something in it before believing
a run was isolated. An empty scratch directory proves the redirect failed; an unchanged live
directory is the only thing that proves it did not.
