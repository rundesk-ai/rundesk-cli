"""Every turn an agent has taken, what each cost, and what one actually did.

The ledger. `rundesk messages` is what was *said*; this is what it *cost* and what became of it —
two different questions, kept apart because they are read for different reasons and answered from
different tables.

With an agent it lists the most recent turns. With a turn as well it shows that one whole: what it
was admitted with, what it did in the order it happened, and what it came to.

**Two of the three counters on the right are how a vendor moving under you becomes visible.**
`unknown` is records this release did not understand and `lost` is records that never arrived at all
— both are zero on a healthy turn, and both climbing is the signal that an adapter and its brain have
drifted apart. Nothing else in the product will tell you that before somebody notices an agent
behaving oddly.

**`unsent` is the opposite direction and is not that signal.** It counts words rundesk could not put
*into* a turn — somebody steering a brain that had just finished, which is an ordinary race whose
words stay durable for the next turn. It shared the `lost` column until `0013`, so a person typing
one word too late looked exactly like an adapter coming apart.
"""

import argparse
import json
from typing import Any, Dict, List, Tuple

from rundesk.agents import directory, records
from rundesk.commands import Subcommands, failed
from rundesk.exits import OK, USAGE
from rundesk.providers import adapters, kept, protocol
from rundesk.providers import turns as running
from rundesk.utils.terminal import as_table, dim

#: How much of one record's own words is shown on a line. The whole of it is in the records.
ON_ONE_LINE = 90

#: What a column shows for something nobody reported. **Not zero** — a cost nobody measured and a
#: cost of nothing are different answers, and a ledger that showed them alike would be a ledger.
NOT_SAID = "—"

#: What is said about a turn whose model was written before the asked-for one and the reported one
#: were kept apart. The value is real and which of the two it is cannot be recovered, so it is said
#: rather than guessed at.
FROM_ONE_COLUMN = "asked for or reported — an older release kept one column"


def register(sub: Subcommands) -> None:
    """One verb: list them, or show one."""
    said = sub.add_parser("turns", help="every turn an agent has taken, and what each cost")
    said.add_argument("agent", metavar="<agent>")
    said.add_argument("turn", metavar="<turn>", nargs="?", type=int,
                      help="show this one whole, with everything it did")
    said.add_argument("--limit", metavar="<n>", type=int, default=kept.FOUND_AT_MOST,
                      help=f"how many to list (default: {kept.FOUND_AT_MOST})")
    said.add_argument("--conversation", metavar="<id>", type=int,
                      help="only turns in this exchange")


def cmd_turns(args: argparse.Namespace) -> int:
    """A `Namespace` in, an exit code out."""
    if args.limit < 1:
        # Through `failed`, like every other refusal in this product: a message on stdout is a
        # message a shell pipeline swallows into the data it was collecting.
        _failed("--limit is how many to list, so it is at least 1")
        return USAGE
    trouble = directory.not_an_agent(args.agent)
    if trouble:
        return _failed(trouble, "see what there is with: rundesk agents")
    try:
        if args.turn is not None:
            return _one(args.agent, args.turn)
        return _listed(args.agent, args.limit, args.conversation)
    except (records.NotThere, records.Unreadable, kept.Refused, OSError) as why:
        return _failed(str(why))


def _listed(agent: str, most: int, conversation) -> int:
    there = kept.list_turns(agent, most=most, conversation=conversation)
    if not there:
        print(f"{agent} has taken no turns yet — ask it something with: rundesk ask {agent} '…'")
        return OK
    print(f"turns {agent} has taken, newest first")
    # The counters are named once, in `kept`, because the trigger that keeps them names them too —
    # a column shown under a heading it does not belong to is a number nobody can act on.
    as_table(("TURN", "WHEN", "WAS", "IN", "COST", *(one.upper() for one in kept.COUNTED)),
             [(str(one["id"]), one["created_at"], _became(agent, one),
               str(one["conversation_id"]), _cost(one),
               *(_counter(one, column) for column in kept.COUNTED.values()))
              for one in there])
    return OK


def _counter(row: Dict[str, Any], column: str) -> str:
    """One drift counter, or a dash where this agent has no such column to answer with.

    **An agent whose carry failed still has a ledger worth reading.** Its turns are all there and
    every other column means what it always did; only the counters a later step added are missing.
    Reaching for one by name would take the whole listing down with a `KeyError` on the one agent
    whose migration is the thing somebody is trying to look into — and a zero would be worse, since
    a count nobody keeps is not a count of nothing.
    """
    said = row.get(column)
    return NOT_SAID if said is None else str(said)


def _one(agent: str, turn: int) -> int:
    """One turn whole: what it was admitted with, what it did, and what it came to."""
    row = kept.get_turn(agent, turn)
    print(f"turn {turn}")
    as_table(("", ""), [
        ("was", _became(agent, row)),
        ("conversation", str(row["conversation_id"])),
        ("provider", row["provider_name"]),
        ("account alias", row.get("provider_alias") or "provider default"),
        *_models(row),
        ("access", row["access_mode"]),
        ("resumed", "yes" if row["session_resumed"] else "no"),
        ("started", row["created_at"]),
        ("ended", row["ended_at"] or NOT_SAID),
        ("exit code", NOT_SAID if row["exit_code"] is None else str(row["exit_code"])),
        ("cost", _cost(row)),
        ("conversation size", _how_big(row)),
        ("instructions", f"{row['instructions_bytes']} bytes, "
                         f"{(row['instructions_sha256'] or '')[:12]}"),
        ("brain said", _said_it_could_do(row)),
    ])
    if row["failure_code"] or row["failure_message"]:
        print()
        print(f"why it did not answer:  {row['failure_message'] or row['failure_code']}")
        said = protocol.what_to_do_about(row["failure_code"])
        if said:
            print(dim(f"        {said}"))

    did = kept.list_turn_records(agent, turn)
    if did:
        print(f"\nwhat it did ({len(did)})")
        as_table(("WHEN", "WHAT", "SAID"),
                 [(one["created_at"], one["record_type"], _briefly(one)) for one in did])
    print(dim(f"\nwhat the brain itself printed:  {adapters.raw_of(agent, row['conversation_id'])}"
              f"  bytes {row['raw_offset_start']} to {row['raw_offset_end']}"))
    return OK


def _models(row: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Which model this turn asked for and which one answered — **or that nobody can say.**

    Two facts, and a release before `0013` kept them in one column: whichever of them arrived last
    is what such a row holds, and nothing in it says which. Labelling that value as either would be
    this surface claiming something nobody recorded, so it is shown under the word it was written
    under and told plainly that it is one answer where there should be two.

    **Which kind of row it is is `model_provenance_kept` and never the emptiness of the two
    columns.** A turn that selected no model and was answered by a provider that reported none is
    empty in exactly the way an older row is, and reading that as *older* would put an honest answer
    — `provider default`, and a dash — under a sentence about a release that did not write it. An
    agent whose carry failed has no marker at all, which reads as an older row, which is what it is.
    """
    if not row.get("model_provenance_kept"):
        if not row["model_name"]:
            return [("model", NOT_SAID)]
        return [("model", f"{row['model_name']}  ({FROM_ONE_COLUMN})")]
    return [("model asked for", row.get("admitted_model_name") or "provider default"),
            ("model reported", row.get("reported_model_name") or NOT_SAID)]


def _became(agent: str, row: Dict[str, Any]) -> str:
    """What a turn came to, and — while it says `working` — whether anything is still doing it.

    **`working` means nothing settled it, never that it is running.** A turn whose process was
    `SIGKILL`ed leaves that word behind for ever, because the one thing that would have changed it
    died with the process. So the second half of the answer is asked of the kernel: the claim on
    that conversation is held for exactly as long as the turn's adapter tree lives, so a `working`
    row with nobody holding it is a turn that was killed rather than one in flight.

    Asked only for `working`, because it costs a lock probe and every other word is already final.
    """
    became = str(row["turn_status"])
    if became != kept.WORKING:
        return became
    try:
        return became if running.busy(agent, row["conversation_id"]) else f"{became} (abandoned)"
    except OSError:
        return became


def _cost(row: Dict[str, Any]) -> str:
    """What a turn cost, or that nobody said. **Zero and unknown are different answers.**

    Read off `Usage` rather than off the row's columns by hand, so a quantity added to that object
    cannot go missing from this surface — which is what happened to `context_tokens`: the line
    printed the moment a turn finished carried it and the ledger for that same turn did not.
    """
    used = kept.usage_of_turn(row)
    if not used.usage_reported:
        return NOT_SAID
    each = [f"{one}{short}" for one, short in
            ((used.input_tokens, "in"), (used.output_tokens, "out"),
             (used.cache_read_tokens, "cr"), (used.cache_write_tokens, "cw"))
            if one is not None]
    return " ".join(each) or "0"


def _how_big(row: Dict[str, Any]) -> str:
    """How big the conversation was when this turn ended. **A level, not a cost** — it goes down
    when one is compacted, so it is shown apart from the four quantities that are billed."""
    used = kept.usage_of_turn(row)
    return f"{used.context_tokens} tokens" if used.context_tokens else NOT_SAID


def _said_it_could_do(row: Dict[str, Any]) -> str:
    """What the adapter claimed when this turn was admitted.

    Kept per turn so *reported no tools* and *has no tools* stay distinguishable a month later, and
    so anything the adapter volunteered — a version, most usefully — is still here to read.
    """
    try:
        said = json.loads(row["provider_capabilities"] or "{}")
    except ValueError:
        return NOT_SAID
    can = [one for one in protocol.CAPABILITIES if said.get(one)]
    extra = [f"{one}={said[one]}" for one in sorted(said) if one not in protocol.CAPABILITIES]
    return ", ".join([*can, *extra]) or "nothing"


def _briefly(one: Dict[str, Any]) -> str:
    """Enough of a record to recognise it. What it could not read, where that is what happened."""
    said = one["raw_line"] or one["event_data"] or ""
    said = str(said).replace("\n", " ").strip()
    return said if len(said) <= ON_ONE_LINE else said[:ON_ONE_LINE - 1] + "…"


def _failed(why: str, *and_so: str) -> int:
    return failed(f"turns: FAILED — {why}", *and_so)
