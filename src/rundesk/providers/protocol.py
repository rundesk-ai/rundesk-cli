"""What an adapter may say, and how to read it. **Nothing here knows any particular brain.**

An adapter is a program rundesk runs, never code it loads. That is the whole design: rundesk never
puts a stranger's code inside the gateway that runs every other agent, an adapter can be written in
anything, and a brain nobody here has heard of is reached by exactly the seam a shipped one is.

**Nothing is enumerated here.** There is no list of providers and no list of models. A vendor's
flags, stream shape, session files, permission model and usage arithmetic live in that vendor's own
adapter and appear nowhere else — **if a vendor's name ever shows up in this file, the seam has
already failed**, and `tests/test_providers_protocol.py` checks exactly that.

What *is* closed is small and deliberate: eight kinds of record, ten words for what a tool did, five
things an adapter may say it can do, two postures, and the words for why a turn stopped. An open
vocabulary would put every vendor's words into every channel and every reader, which is the thing
this seam exists to prevent.

**A field is named for what it holds, and the wire name is the column name.** `failure_code`,
`failure_message`, `session_id`, `input_tokens`, `context_tokens` — the same words an adapter writes
are the words `turns` stores, so nothing translates between them and a person reading one file can
read the other. The rule that produced them is that a name must be readable on its own: `because`
and `why` were two different facts a sentence apart, and `session` meant a resume handle on one
record and a token count on the next.

**Being closed is also what makes forward compatibility cheap.** A line that will not parse, a line
that is not an object, and a line of a kind this release has never heard of all come back the same
way from `understood`: `None`, meaning *keep it, show it to nobody*. The caller keeps the raw line
either way, so a vendor changing its output shows up as visible drift rather than as records quietly
going missing.
"""

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, NamedTuple, Optional

#: What an adapter reports, and the whole of it. A ninth is a change to the contract, deliberately.
#:
#: `file` exists because the contract could not otherwise say a thing brains plainly do: make
#: something. One generated a picture, said "here it is", and there was no way to tell anybody a file
#: existed. Inferring it from what a tool printed was the alternative, and it would have meant
#: sending anything a brain happened to name.
#:
#: `limit` exists for the same shape of reason: brains report account state — how much of an
#: allowance is left, when the window resets — and the seam had nowhere to put it, so a turn stopped
#: by one reached an owner as whatever prose an adapter scraped off a failure line. **It is not this
#: turn's activity and it is not an outcome: a turn carrying one may have succeeded**, which is what
#: makes it a record rather than a reason.
RECORDS = ("text", "think", "tool", "result", "usage", "file", "limit", "done")

#: What a brain says on a `text` or `think` record when the thing it just said is *finished* rather
#: than a piece of something still being written.
#:
#: The difference decides whether a person can be shown it while the turn runs. A brain that streams
#: a fragment at a time can only be shown at the end, because a reply that rewrites itself in place
#: is unreadable. A brain that says several complete things as it works can have each shown as it is
#: said. Absent means a fragment, so a brain that says nothing gets the quieter behaviour and
#: nothing breaks.
WHOLE = "whole"

#: What a tool *did*, in words no brain owns. Closed and short on purpose: the same action is `Bash`
#: on one brain, `shell` on the next and `run_terminal_command` on a third, and a surface that
#: recognised any of them would be carrying that vendor's vocabulary forever.
#:
#: A brain that did something outside this list leaves the word out rather than stretching one to
#: fit — a reader shown nothing is better than one taught to believe a word that means something
#: else here. The last three are the same act as `edit` and are told apart on purpose: what an agent
#: keeps of its own is what it *is* between turns, and a file it lives by being changed is not the
#: same news as a working file being changed.
DID = ("read", "search", "run", "edit", "list", "make", "delegate",
       "memory", "rules", "identity")

#: What an adapter may say it can do. Absent means no, so an adapter that answers with nothing at all
#: is a whole brain with the work simply absent — which is what makes a plain conversational CLI
#: first class rather than degraded.
#:
#: `steer` is the one that changes how a turn is *run* rather than only what is recorded of it: an
#: adapter that can be sent to mid-turn has its input held open and is given records, and one that
#: cannot is given the prompt and told there is no more. Declared rather than attempted, because
#: holding input open for a brain that will never read again is a turn that never ends.
CAPABILITIES = ("tools", "resume", "model", "usage", "steer")

#: How much of the machine a turn may touch, in rundesk's words rather than any vendor's. Two,
#: because a posture nobody can act on is not worth carrying: an adapter maps these onto whatever
#: its own brain understands, or ignores them. **rundesk enforces neither** — it has no way to, and
#: pretending otherwise would be worse than saying so.
ACCESS_READ = "read"
ACCESS_WORK = "work"
ACCESS_MODES = (ACCESS_READ, ACCESS_WORK)

#: What rundesk sends a brain that can be steered. One kind, because there is one thing to say to a
#: running brain: more words.
SAY = "say"

#: What rundesk says alongside a word that reaches work already in flight. Carried **apart from** the
#: person's text, so an adapter can apply it without changing the person's recorded words — and so a
#: brain is told this is genuine mid-turn guidance. A plain line appended to a tool result is
#: refused by real brains as suspected prompt injection, which is a failure observed in the wild by
#: a comparable product and fixed there the same way.
STEERING_CONTEXT = (
    "Mid-turn guidance for the current request. Integrate it, then continue the original work "
    "unless it explicitly replaces or stops it."
)


# ── Why a turn stopped ────────────────────────────────────────────────────────────────────────

#: The closed words for why a turn stopped. Deliberately **not** a database `CHECK`: this vocabulary
#: grows every time a vendor invents a new way to fail, and widening a `CHECK` costs a full table
#: rebuild. `providers.kept` refuses a word that is not here, before the write.
#:
#: Two things produce one of these and they must not be confused. **A brain classifies its own
#: failure** and says so on its `done` record. **rundesk classifies only what rundesk observed** —
#: that it cancelled the turn, that the program died, that it went quiet. Nothing here is ever
#: inferred from the prose beside it: a word guessed from a failure message is a word that will be
#: wrong on the first vendor that rewords one.
SIGNED_OUT = "signed_out"                 # no usable credential — a person runs the login command
NO_ACCESS = "no_access"                   # signed in and not permitted: no entitlement to this model
NO_CREDIT = "no_credit"                   # the account cannot pay — a person acts
USAGE_EXHAUSTED = "usage_exhausted"       # the plan's allowance is spent until its window resets
RATE_LIMITED = "rate_limited"             # too fast, right now — the same request later is fine
CONTEXT_EXCEEDED = "context_exceeded"     # the conversation is too big to continue
UPSTREAM_ERROR = "upstream_error"         # the vendor's own fault: a 5xx, a bad gateway, a wedge
OFFLINE = "offline"                       # this machine could not reach the vendor at all
REFUSED = "refused"                       # the brain declined the work — a decision, not a fault
CANCELLED = "cancelled"                   # somebody stopped it, or the gateway went down under it
TIMED_OUT = "timed_out"                   # rundesk ended it: silent too long, or past the ceiling
CRASHED = "crashed"                       # the adapter or its brain fell over

FAILURE_CODES = (SIGNED_OUT, NO_ACCESS, NO_CREDIT, USAGE_EXHAUSTED, RATE_LIMITED, CONTEXT_EXCEEDED,
           UPSTREAM_ERROR, OFFLINE, REFUSED, CANCELLED, TIMED_OUT, CRASHED)

#: The words rundesk may write on its own account, because they are about what rundesk did or saw
#: rather than about what the brain decided. Everything else in `BECAUSE` has to come from the brain.
OBSERVED_BY_RUNDESK = (CANCELLED, TIMED_OUT, CRASHED)

#: The words where trying the same turn again could reasonably work, once. Everything absent from
#: this needs a person: a login to run, a card to add, a conversation to start fresh, or a decision
#: the brain already made and will make again.
#:
#: **This is a classification and never a policy.** Nothing here retries anything; what this answers
#: is the only question a caller asks about one of these words, so that the answer is in one place
#: rather than re-derived — differently — at each call site.
RETRYABLE_FAILURE_CODES = (RATE_LIMITED, UPSTREAM_ERROR, OFFLINE, CRASHED)


def is_retryable(failure_code: Optional[str]) -> bool:
    """Whether this is a turn the same request could survive later. Unknown or absent is **no**.

    The safe way round: a word this release does not know might mean "your card was declined", and
    answering yes to that is how a product bills somebody twice for a turn nobody can run.
    """
    return failure_code in RETRYABLE_FAILURE_CODES


def needs_human_action(failure_code: Optional[str]) -> bool:
    """Whether nothing will change until somebody does something about it.

    What this is for is saying so *once* rather than every time: an agent whose brain is signed out
    fails identically on every message until a person logs in, and a surface that could not tell
    that apart from a transient failure would say the same thing all day.
    """
    return failure_code in (SIGNED_OUT, NO_ACCESS, NO_CREDIT)


# ── Reading what an adapter said ──────────────────────────────────────────────────────────────


def what_to_do_about(failure_code: Optional[str]) -> str:
    """The one line that says whether this is worth trying again, or whether somebody has to act.

    **The whole point of a closed vocabulary reaching a person.** Somebody reading a failure should
    not have to know a vendor's error strings to know whether to wait — so the sentence is derived
    from the word rather than from the prose beside it, and it is derived *here*, once, because
    three surfaces asked the same question and two of them had already worded it differently.

    Empty when there is no word at all, which is a turn that failed without the brain saying why.
    """
    if not failure_code:
        return ""
    if needs_human_action(failure_code):
        return f"this will not clear on its own ({failure_code})"
    if is_retryable(failure_code):
        return f"the same request later may work ({failure_code})"
    return f"the brain said: {failure_code}"


def parse_record(said: str) -> Optional[Dict[str, Any]]:
    """One line, as one of the records this release knows — or `None` if it is not one.

    **Nothing is refused here and nothing raises.** A line that will not parse, a line that is not an
    object, and a line of a kind never heard of all come back `None`, meaning *keep it, show it to
    nobody*. The caller keeps the raw line either way, which is what makes an upstream format change
    show up as visible drift rather than as a silent gap — and what lets an adapter be ahead of this
    release without waiting for one.
    """
    try:
        it = json.loads(said)
    except ValueError:
        return None
    if not isinstance(it, dict):
        return None
    return it if it.get("type") in RECORDS else None


def build_say_line(text: str, context: str = "") -> str:
    """One thing said *to* a brain, as the line it reads.

    Records rather than plain text, and only for an adapter that said it can be steered: its input
    has to stay open for more, so nothing can mean "the prompt ended" any more — a brain reading to
    the end of its input would wait for an end that is not coming. One line, with the text encoded,
    so a prompt with newlines in it is still one thing.

    rundesk's own context is carried in its own field rather than concatenated into the text, so an
    adapter can apply it without altering the person's recorded words.
    """
    record = {"type": SAY, "text": text}
    if context:
        record["context"] = context
    return json.dumps(record) + "\n"


def parse_capabilities(said: Any) -> Dict[str, bool]:
    """What an adapter says it can do, as an answer to every question rather than some.

    Absent is no, so a brain that says nothing is not asked to have anything. Read from whatever came
    back rather than trusted: an adapter that answers with a number, a list, or nothing readable at
    all can do nothing, which is a complete and honest answer and not an error.
    """
    given = said if isinstance(said, dict) else {}
    return {what: bool(given.get(what)) for what in CAPABILITIES}


# ── The readings: what a turn's records add up to ─────────────────────────────────────────────
#
# Each is a pure function of the records a turn produced, and each exists because a plausible-looking
# simpler version of it was wrong on a real machine. They are here rather than beside the turn so
# that proving them costs a list of dicts and nothing else.


class Usage(NamedTuple):
    """What a turn cost, or that nobody said what it cost.

    `reported` is the field to read first. **Zero and unknown are different answers**, and a spend
    limit that read the first for the second would never fire — so every quantity is `None` until a
    brain says otherwise, and `reported` says whether a `usage` record arrived at all.

    The four billed quantities are kept apart because they are billed at three different rates:
    cache *writes* bill above standard input where cache *reads* bill at a fraction of it, so folding
    any two together reports a number that is real and misleading. `context` is not a cost at all —
    it is how big the conversation is *now*, which is the one thing a person reads a footer to find
    out, and it goes **down** when a conversation is compacted, which no total can.
    """

    usage_reported: bool = False
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    cache_write_tokens: Optional[int] = None
    context_tokens: Optional[int] = None
    model_name: Optional[str] = None


def brain_said_ok(said: Iterable[Dict[str, Any]]) -> Optional[bool]:
    """Whether the brain said the turn worked, or said nothing about it at all.

    Three answers, and the third is the one that matters: **no `done` record at all** is the shape a
    killed adapter leaves, and nothing may declare such a turn over on its behalf.
    """
    for one in _backwards(said):
        if one.get("type") == "done":
            return bool(one.get("ok"))
    return None


def has_answer(said: Iterable[Dict[str, Any]]) -> bool:
    """Whether whoever asked got anything back at all.

    **A program exiting well is not an answer.** Measured on a live gateway: a resumed session
    reported `done ok:true` with four zero usage counters fourteen milliseconds after it started and
    said nothing else. The run was written down as finished and the question that caused it was
    marked answered — so somebody was told their question had been dealt with, and nothing had
    happened to it. This is the only place that can tell the two apart before a surface acts on it.

    A file counts and a tool call does not: something delivered is an answer even when nothing was
    typed about it, while reading a file and thinking about it is work nobody receives. Whitespace is
    not an answer either — a surface posts nothing for it.
    """
    for one in said:
        if one.get("type") == "file" and Path(str(one.get("at") or "")).is_absolute():
            return True
        if one.get("type") == "text" and str(one.get("text") or "").strip():
            return True
    return False


def resume_handle(said: Iterable[Dict[str, Any]]) -> Optional[str]:
    """Where the brain says this conversation got to, off the record that ends the turn.

    Opaque to everything here. It is the brain's own word for its conversation, kept so a later turn
    can be carried on from it, and never parsed.
    """
    for one in _backwards(said):
        if one.get("type") == "done":
            handle = one.get("session_id")
            return handle if isinstance(handle, str) and handle else None
    return None


def failure_message(said: Iterable[Dict[str, Any]]) -> Optional[str]:
    """What the brain said went wrong, in its own words — the prose a person reads.

    Taken off the record that ends the turn rather than from the error stream, because a turn that
    failed with its one actionable line filed in a log nobody opens is a turn somebody is stuck on.
    """
    for one in _backwards(said):
        if one.get("type") == "done":
            said = one.get("failure_message")
            return said if isinstance(said, str) and said else None
    return None


def failure_code(said: Iterable[Dict[str, Any]]) -> Optional[str]:
    """Which of the closed words the brain gave for stopping, if it gave one at all.

    A word this release does not know is **dropped rather than stored**. The whole value of a closed
    set is that a reader can exhaust it, and one unknown member sitting silently in the column takes
    that away — while an adapter reporting a word from a *newer* rundesk is exactly the case that
    must not corrupt an older one's totals. Never inferred from the prose beside it.
    """
    for one in _backwards(said):
        if one.get("type") == "done":
            word = one.get("failure_code")
            return word if isinstance(word, str) and word in FAILURE_CODES else None
    return None


def usage_of(said: Iterable[Dict[str, Any]]) -> Usage:
    """What this turn cost, or that nobody said.

    What a brain reported is recorded as reported and never adjusted: the arithmetic that turns a
    conversation's running total into a turn's share belongs in the adapter, which is the only thing
    that knows its brain reports one.

    Only what was actually reported is carried. A brain that cannot tell fresh tokens from cached
    ones omits the cached field, and summing that into zero would say it read nothing from the cache
    — the same lie as a cost of nothing, one level down.

    `context` is a **level, not a quantity**: several snapshots may arrive while a brain works, and a
    smaller one after it compacts, so the last is how large the conversation ended and adding them
    would invent a number nothing measured.
    """
    counted = [one for one in said if one.get("type") == "usage"]
    if not counted:
        return Usage()
    totals = {}
    # **The wire name and the column name are the same word**, so nothing translates between them
    # and a reader of one file can read the other. See the module docstring on why they must be.
    for named in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
        values = [one[named] for one in counted if _a_count(one.get(named))]
        if values:
            totals[named] = sum(values)
    levels = [one["context_tokens"] for one in counted if _a_count(one.get("context_tokens"))]
    if levels:
        totals["context_tokens"] = levels[-1]
    # Only ever what a brain said actually answered. One that names none leaves none claimed, rather
    # than the one that happened to be asked for — a model requested is not a model measured.
    named = [str(one.get("model_name")) for one in counted if one.get("model_name")]
    if named:
        totals["model_name"] = named[-1]
    return Usage(usage_reported=True, **totals)


def file_records(said: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Everything the brain said it made, in the order it said so.

    Named by the brain and never guessed at: what a tool printed is not a promise that a file exists,
    and treating it as one would send whatever a brain happened to mention.
    """
    return [one for one in said if one.get("type") == "file"]


def limit_records(said: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every piece of account state the brain reported — what is left, and when it comes back.

    Kept apart from the turn's outcome on purpose: **a turn carrying one of these may have
    succeeded.** It is news about the account rather than about the work, and a surface that treated
    it as a failure would report a working agent as broken every time it neared its allowance.
    """
    return [one for one in said if one.get("type") == "limit"]


#: Going to work, in a brain's own records. An adapter reports the call and it reports the call's one
#: terminal update; both are here because a tool already over by the time this process heard of it
#: arrives as a `result` alone, and the seam must still be found.
WENT_TO_WORK = ("tool", "result")


def thoughts(said: Iterable[Dict[str, Any]], kind: str = "text") -> List[str]:
    """What the brain said, split where it finished a thought.

    **A finished thought ends a paragraph; a fragment does not.** Concatenating every record with
    nothing between it and the next is right for fragments and wrong for whole thoughts — a brain
    that says several complete things as it works had the last word of one run into the first word of
    the next, so an account read back `caught it running.The worker`.

    **A brain that never marks anything finished still finishes a thought by going to work.** The
    `whole` marker is not a seam every adapter has — one shipped brain writes its reply a token at a
    time and nothing in its stream ever restates it, and another streams deltas. Read on `whole`
    alone, every turn either of them takes is one thought. What both *do* report is the moment the
    brain stopped talking and called a tool, and that is the same seam said another way: a thought
    said before further tool calls is working narration.

    So the split is defined for every adapter, and a brain that streamed straight through without
    ever going to work said one thing — which is right, because there was no working to drop.

    `kind` is `text` for what the brain said and `think` for what it was reasoning about. One
    function for both because the splitting rule is identical, and two copies of this would drift.
    """
    parts, piece = [], ""
    for one in said:
        at = one.get("type")
        if at in WENT_TO_WORK:
            # Whatever was open is finished: the brain left off saying it in order to do something.
            if piece:
                parts.append(piece)
                piece = ""
            continue
        if at != kind:
            continue
        text = str(one.get("text") or "")
        if not one.get(WHOLE):
            piece += text
            continue
        if piece:
            parts.append(piece)
            piece = ""
        parts.append(text)
    if piece:
        parts.append(piece)
    # Stripped of the blank lines a brain put at its own edges, never of the ones inside a thought:
    # what is between paragraphs here is rundesk's, and what is within one is the brain's.
    return [kept for kept in (part.strip("\n") for part in parts) if kept.strip()]


def reply(said: Iterable[Dict[str, Any]]) -> str:
    """Everything the brain said, as the one thing it said."""
    return "\n\n".join(thoughts(said))


def last_thought(said: Iterable[Dict[str, Any]]) -> str:
    """The last whole thing the brain said — what a turn nobody watched answers with.

    **Decided after the turn is over, which is the only moment it is a fact.** A provider that
    explicitly distinguishes its final answer wins; otherwise the last post-tool thought is the
    closing response.

    A turn somebody is watching shows its working as it goes and its last thought is already the
    answer, because the surface sends each earlier one on as it is finished. A turn nobody watched
    never passes that way — what it said is read back out of one row afterwards, so everything it
    thought aloud on the way would arrive as a report with the report buried at the end of it.
    """
    # Text before the last tool boundary is activity, not a closing response. If the brain went to
    # work and then stopped without saying anything else, there is no final report to publish.
    records = list(said)
    explicit = [one for one in records if one.get("type") == "text" and one.get("final") is True]
    if explicit:
        each = thoughts(explicit)
        return each[-1] if each else ""
    after = 0
    for at, one in enumerate(records):
        if one.get("type") in WENT_TO_WORK:
            after = at + 1
    each = thoughts(records[after:])
    return each[-1] if each else ""


def _backwards(said: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The records in reverse, for the four readings that want the last `done` and not the first.

    A list rather than `reversed()` because these take any iterable and one of them is handed a
    generator; reversing a generator raises, and it would raise only on the path where a turn had
    already gone wrong.
    """
    return list(said)[::-1]


def _a_count(said: Any) -> bool:
    """Whether this is a number of things. `True` is an `int` to Python and is not a count."""
    return isinstance(said, int) and not isinstance(said, bool)
