# Duplication, simplicity, and speculation

Three passes over one question: is this more code than the problem needs? They stay separate because
their evidence differs. Duplication asks what is now stated in two places. Simplicity asks whether a
thing the change genuinely needs is built more elaborately than it needs to be. Speculation asks
whether it is needed at all.

Each finding meets the same bar as any other, and each is normally **Optional**. Promote one only
when it breaks a rule the repository states for itself or carries a defect you can reach.

## Duplication: one piece of knowledge in two places

The rule is about knowledge, not about text. Every piece of knowledge should have a single,
unambiguous, authoritative representation, and two blocks that read the same are not thereby the
same knowledge. Two validators that both require a positive integer — one for an age, one for a
quantity — are a coincidence. Merging them couples two rules that were free to diverge, and the
first requirement that moves one of them proves it.

The question is never whether two places look alike. It is: **when this rule changes, must both
places change together?**

| In the change | Why it is a finding |
|---|---|
| A block copied to a second module with a value or two altered | One rule, two homes; the next correction lands in one of them |
| A conditional chain repeated per case, gaining a branch with each new case | The shape is a lookup written out longhand; every addition edits the same chain |
| Validation, error mapping, or formatting restated at a second call site | The behavior a caller sees now depends on which site it reached |
| A literal that must match one elsewhere — a width, a limit, a key, a route | The relationship is invisible, so nothing fails when one of them moves |
| A rule stated in both the code and a comment or document beside it | They drift, and the reader cannot tell which one is current |

Where duplication is the right answer, and the finding is not:

- **The wrong abstraction costs more than the repetition.** An extraction made for two callers, then
  bent with a parameter for a third and a flag for a fourth, ends up harder to read than what it
  replaced and much harder to undo. Prefer duplication until the shared knowledge is clear.
- **Two or three lines repeated twice** rarely pay for a shared home. Three occurrences, or two that
  are certain to change together, are where the case starts.
- **Framework-required structure** — a registration, a lifecycle method, a serializer stanza — is
  what the framework demands, not repetition the author chose.
- **An extraction nobody will find** is not a consolidation. If the shared home would sit somewhere
  no future author would look, the duplication is more honest.
- **A test that spells out its own inputs** is keeping its causal values visible, which is a property
  worth more than brevity.

Report both locations, the knowledge they share, what goes wrong when it changes in one of them, and
the single consolidation you would accept.

## Simplicity: a needed thing built more elaborately than it needs

*Too complex* has a working definition: it cannot be understood quickly by the people who will read
it. That makes it observable rather than a matter of taste — the reviewer is one of those readers.

| In the change | The question it fails |
|---|---|
| An interface, base class, strategy, or factory with one implementation and no second caller | What does the indirection buy that a direct call does not? |
| A wrapper around a wrapper, each adding a name and no behavior | Which layer would a reader have to open to find the rule? |
| An option, flag, or setting that only ever takes one value | Who sets the other one? |
| A pattern applied where a function or a branch would carry the whole rule | What is the ceremony protecting? |
| Nesting that a guard clause or early return would flatten | Which condition has to hold for the real work to run? |
| Hand-rolled logic the language, framework, or an existing helper already provides | Why is this version better than the one that is already tested? |
| An optimization with no measurement behind it | What was slow, and by how much? |

Where the structure stays:

- Never push simplicity through correctness. Error handling, validation, and the cases a reader finds
  fussy are usually the cases production found first.
- Short is not simple. A dense expression that takes a minute to parse is the failure this pass
  exists to catch, not its goal.
- Structure that earns its place is affirmed, not stripped. Say so, and move on.

## Speculation: built for a requirement that has not arrived

The test is a present caller. A capability with no caller in the change, none in the tree, and no
test exercising it is not needed today, however cleanly it is written.

The cost is not only the code. Building it spends effort that a real requirement was waiting for, it
makes every later change to that area more expensive to read and modify, and if the guess turns out
wrong the work is repaid twice — once to build and once to unpick. The middle two costs land even
when the guess turns out right.

| In the change | The evidence it is unneeded |
|---|---|
| A parameter or option every call site passes the same value for | One value, no second caller |
| A function, endpoint, component, or command nothing invokes | No reference anywhere in the tree |
| An enum case, status, or field nothing reads or writes | Written and never consumed, or declared and never set |
| An extension point added so a second implementation can arrive | One implementation, and no second one in the change |
| A compatibility shim for a version, format, or provider not in use | Nothing in the tree produces that shape |
| Caching, batching, or pooling for load nobody has measured | No figure, no report, no incident behind it |

Where it stays:

- The assignment asked for it. A requirement someone stated is in scope even with no caller yet; note
  it and move on.
- It handles an input that can actually occur. Validation, authorization, and defensive code for real
  inputs address today, not a speculative future.
- A caller exists in the change itself. Present usage is the test, not appearance.

## Telling the three apart

Most over-built code trips more than one of these. Pick the pass whose correction is the one you
would actually accept, and report it once.

| What the change did | Pass | The correction |
|---|---|---|
| Stated one rule in two places | Duplication | One authoritative home for the rule |
| Solved a real need through more machinery than the need has | Simplicity | The plain path that meets the same need |
| Built a capability nothing asks for | Speculation | Remove it; add it when the requirement lands |

A finding gives the smallest direction that resolves it. None of these passes licenses redesigning
the change, rewriting it, or reporting the same line three times under three headings.
