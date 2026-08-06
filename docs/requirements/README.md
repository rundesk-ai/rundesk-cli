# The channel requirements, and why they are in the tree

Four pages the previous build wrote and tracked, moved here from `.knowledge_old/prd/` — which is
gitignored, reference-only, and expected to be deleted. **That is the whole reason this directory
exists.** A requirements document nobody can see from the repository is one nobody consults.

They are not this build's promises. They are the **previous** build's, and they are kept because a
rewrite with a working predecessor has a specification already written, and rebuilding from its
source instead loses everything the source never said.

## What that cost, measured

| | |
|---|---|
| Requirement rows across these four pages | **140** |
| Met by this build at the time they were found | **34** |
| Met, excluding Slack — a platform this build does not have | **34 of 95** |
| Times the previous build cited a requirement id in its own source | **1,109** |
| Times this build had cited one | **0** |

The one that made it concrete: `R-DIS-1` — *named in a room, the turn happens in a thread* — was
dropped, and then a docstring was written explaining why not doing it was the right design. Nobody
was being careless. The rewrite read `src_old/` carefully and reconstructed a specification from an
implementation, and an implementation does not say which of its behaviours were obligations.

`docs/research/2026-08-05-the-old-builds-channel-system.md` even quotes R-DIS-1's behaviour, having
found it by reading the code. It was recorded as a description of what an old build did, not as a
thing this one owed.

## How to use them

**Cite the id where the requirement is met.** `R-DIS-1` in the docstring of the thing that opens a
thread. That is the mechanism that makes dropping one a *visible edit* rather than a silent absence,
and it is the only reason the previous build could answer "is this still true" at all.

**When a requirement will not be met, say so where somebody will look, with the reason.** Several
here are genuinely unreachable in this build and that is fine — what is not fine is an absence that
reads as an oversight, or a docstring arguing for a gap nobody chose.

**Some of these are now wrong**, and that is expected of a document describing a build that no longer
exists. Three known:

- **R-DIS-3** (*answers in its own thread without being named again*) was unreachable until this build
  enabled `MESSAGE_CONTENT`, and the previous build simply had that intent on. Now met.
- **R-DIS-30** wants a *"scheduled run began"* message to anchor a report to. `gateways/host.py`
  deliberately never announces a successful schedule — *a message per successful nightly job is how
  somebody learns to ignore the channel* — so there is nothing to anchor to.
- **R-CAD-15** (*each kind of place becomes a channel of its own*) describes a shape deliberately
  removed: a channel is a connection, not a place.

**The ❌ rows are the more useful half.** Their evidence columns do not say "unproven" — they say what
kind of proof is missing and why a test cannot supply it. That is a hand-verification protocol, and
this build has no equivalent.

## The general rule

**A rewrite's specification is its predecessor's requirements, not its predecessor's source.**
Everything built fresh here came out right; everything that should have been carried across was
re-derived, and the parts that existed only in prose were lost.
