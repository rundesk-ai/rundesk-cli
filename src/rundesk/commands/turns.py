"""Every turn an agent has taken, what each cost, and what one actually did.

The ledger. `rundesk messages` is what was *said*; this is what it *cost* and what became of it —
two different questions, kept apart because they are read for different reasons and answered from
different tables.

With an agent it lists the most recent turns. With a turn as well it shows that one whole: what it
was admitted with, what it did in the order it happened, and what it came to.

**The two counters on the right are how a vendor moving under you becomes visible.** `unknown` is
records this release did not understand and `lost` is records that never arrived at all — both are
zero on a healthy turn, and both climbing is the signal that an adapter and its brain have drifted
apart. Nothing else in the product will tell you that before somebody notices an agent behaving
oddly.
"""

import argparse
import json
from typing import Any, Dict, List

from rundesk.agents import directory, records
from rundesk.commands import Subcommands, failed
from rundesk.exits import OK, USAGE
from rundesk.providers import adapters, kept, protocol
from rundesk.utils.terminal import as_table, dim

#: How much of one record's own words is shown on a line. The whole of it is in the records.
ON_ONE_LINE = 90

#: What a column shows for something nobody reported. **Not zero** — a cost nobody measured and a
#: cost of nothing are different answers, and a ledger that showed them alike would be a ledger.
NOT_SAID = "—"


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
        print("turns: FAILED — --limit is how many to list, so it is at least 1")
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
    as_table(("TURN", "WHEN", "WAS", "IN", "COST", "UNKNOWN", "LOST"),
             [(str(one["id"]), one["created_at"], _became(one), str(one["conversation_id"]),
               _cost(one), str(one["unknown_records"]), str(one["lost_records"]))
              for one in there])
    return OK


def _one(agent: str, turn: int) -> int:
    """One turn whole: what it was admitted with, what it did, and what it came to."""
    row = kept.get_turn(agent, turn)
    print(f"turn {turn}")
    as_table(("", ""), [
        ("was", _became(row)),
        ("conversation", str(row["conversation_id"])),
        ("provider", row["provider_name"]),
        ("model", row["model_name"] or NOT_SAID),
        ("access", row["access_mode"]),
        ("resumed", "yes" if row["session_resumed"] else "no"),
        ("started", row["created_at"]),
        ("ended", row["ended_at"] or NOT_SAID),
        ("exit code", NOT_SAID if row["exit_code"] is None else str(row["exit_code"])),
        ("cost", _cost(row)),
        ("instructions", f"{row['instructions_bytes']} bytes, "
                         f"{(row['instructions_sha256'] or '')[:12]}"),
        ("brain said", _said_it_could_do(row)),
    ])
    if row["failure_code"] or row["failure_message"]:
        print()
        print(f"why it did not answer:  {row['failure_message'] or row['failure_code']}")
        for line in _what_to_do_about(row["failure_code"]):
            print(dim(f"        {line}"))

    did = kept.list_turn_records(agent, turn)
    if did:
        print(f"\nwhat it did ({len(did)})")
        as_table(("WHEN", "WHAT", "SAID"),
                 [(one["created_at"], one["record_type"], _briefly(one)) for one in did])
    print(dim(f"\nwhat the brain itself printed:  {adapters.raw_of(agent, row['conversation_id'])}"
              f"  bytes {row['raw_offset_start']} to {row['raw_offset_end']}"))
    return OK


def _became(row: Dict[str, Any]) -> str:
    """What a turn came to. `working` means nothing has settled it, never that it is running."""
    return str(row["turn_status"])


def _cost(row: Dict[str, Any]) -> str:
    """What a turn cost, or that nobody said. **Zero and unknown are different answers.**"""
    if not row["usage_reported"]:
        return NOT_SAID
    each = [f"{row[what]}{short}" for what, short in
            (("input_tokens", "in"), ("output_tokens", "out"),
             ("cache_read_tokens", "cr"), ("cache_write_tokens", "cw"))
            if row[what] is not None]
    return " ".join(each) or "0"


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


def _what_to_do_about(failure_code) -> List[str]:
    """Whether waiting will help, or whether somebody has to act."""
    if not failure_code:
        return []
    if protocol.needs_human_action(failure_code):
        return [f"this will not clear on its own ({failure_code})"]
    if protocol.is_retryable(failure_code):
        return [f"the same turn later may work ({failure_code})"]
    return [f"the brain said: {failure_code}"]


def _briefly(one: Dict[str, Any]) -> str:
    """Enough of a record to recognise it. What it could not read, where that is what happened."""
    said = one["raw_line"] or one["event_data"] or ""
    said = str(said).replace("\n", " ").strip()
    return said if len(said) <= ON_ONE_LINE else said[:ON_ONE_LINE - 1] + "…"


def _failed(why: str, *and_so: str) -> int:
    return failed(f"turns: FAILED — {why}", *and_so)
