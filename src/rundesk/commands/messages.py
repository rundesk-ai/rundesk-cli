"""What an agent has been told and what it said back, and finding a particular one again.

**The agent is the first caller of this, before its owner is.** A person refers to work the agent has
no record of — "the invoice bug you looked at last week" — and the agent reads its own history back
before answering rather than saying it does not know. Its instructions name this command for exactly
that, so it has to be here and it has to be cheap.

That is what shapes the output. Every line the agent reads costs tokens, so the default is one
bounded line per message — who, where, when, and enough of the words to recognise it — and `--full`
is what prints bodies. A listing that answered with fifty whole messages would spend a turn's budget
on finding out what the turn was about.

Four ways to narrow, and they compose: `--search` for words, `--channel` for where it was said,
`--source` for what kind of thing started it, and `--conversation` for one exchange. With no words at
all it is the conversation read back, newest first.

**Where there is no full-text index it says so.** A scan finds different things — no stemming, no
phrase, no ranking — and somebody comparing two searches has to know which they got.
"""

import argparse
from typing import Any, Dict, List, Optional

from rundesk.agents import directory, records
from rundesk.commands import Subcommands, failed
from rundesk.exits import OK, USAGE
from rundesk.providers import kept
from rundesk.utils.terminal import as_table

TROUBLE = (directory.Refused, records.NotThere, records.Unreadable, kept.Refused, OSError)

#: How much of a message is shown on one line when the whole of it was not asked for.
ON_ONE_LINE = 70

#: What the source column shows for a conversation nothing has said where it came from.
NOWHERE = "—"


def register(sub: Subcommands) -> None:
    """One verb, because there is one thing to do with a history: look through it."""
    said = sub.add_parser("messages", help="what an agent has been told, and what it said back")
    said.add_argument("agent", metavar="<agent>")
    said.add_argument("--search", metavar="<words>", default="",
                      help="find messages holding these words")
    said.add_argument("--channel", metavar="<channel>",
                      help="only what was said on this channel")
    said.add_argument("--source", metavar="<kind>",
                      help="only conversations of this kind, such as channel or schedule")
    said.add_argument("--conversation", metavar="<id>", type=int,
                      help="only this exchange")
    said.add_argument("--since", metavar="<YYYY-MM-DD>",
                      help="only what was said on or after this day")
    said.add_argument("--limit", metavar="<n>", type=int, default=kept.FOUND_AT_MOST,
                      help=f"how many to show (default: {kept.FOUND_AT_MOST})")
    said.add_argument("--full", action="store_true",
                      help="print whole messages rather than one line each")


def cmd_messages(args: argparse.Namespace) -> int:
    """A `Namespace` in, an exit code out."""
    if args.limit < 1:
        return _mistyped("--limit is how many to show, so it is at least 1")
    try:
        trouble = directory.not_an_agent(args.agent)
        if trouble:
            return _failed(trouble, "see what there is with: rundesk agents")
        found = kept.search_messages(
            args.agent, saying=args.search, channel=args.channel, source=args.source,
            conversation=args.conversation, since=_a_day(args.since), most=args.limit)
    except TROUBLE as why:
        return _failed(str(why))
    return _shown(args, found)


def _shown(args: argparse.Namespace, found: List[Dict[str, Any]]) -> int:
    """What was found, and — when nothing was — what was actually looked for.

    A listing that answered an empty table is one somebody reads as a broken search. Saying back the
    narrowing is what tells "nothing matched" from "you narrowed it to nothing".
    """
    if not found:
        print(f"nothing {_narrowed_by(args)}")
        return OK
    print(f"{len(found)} {_narrowed_by(args)}{_and_how(args.agent, args.search)}")
    if args.full:
        for one in found:
            print(f"\n[{one['created_at']}] {one['author']}"
                  f"{_where(one)} — conversation {one['conversation_id']}")
            print(one["body"])
        return OK
    as_table(("WHEN", "WHO", "WHERE", "IN", "SAID"),
             [(one["created_at"], one["author"], _where(one).strip(" ()") or NOWHERE,
               str(one["conversation_id"]), _briefly(one)) for one in found])
    return OK


def _narrowed_by(args: argparse.Namespace) -> str:
    """The question that was asked, said back, so an empty answer is readable."""
    each = []
    if args.search:
        each.append(f"holding {args.search!r}")
    if args.channel:
        each.append(f"on {args.channel}")
    if args.source:
        each.append(f"from a {args.source}")
    if args.conversation is not None:
        each.append(f"in conversation {args.conversation}")
    if args.since:
        each.append(f"since {args.since}")
    return f"{args.agent} said or was told" + (" " + ", ".join(each) if each else "")


def _and_how(agent: str, searched: str) -> str:
    """Whether this was a search or a scan, said only when it was one of the two.

    A scan has no stemming, no phrase and no ranking, and somebody comparing two answers has to know
    which they got.
    """
    if not searched.strip() or kept.has_search_index(agent):
        return ""
    return "  (no search index on this install — matched as plain text)"


def _where(one: Dict[str, Any]) -> str:
    """Which channel it was said on, or which kind of thing started it."""
    if one.get("channel"):
        return f" ({one['channel']})"
    return f" ({one['source']})" if one.get("source") else ""


def _briefly(one: Dict[str, Any]) -> str:
    """Enough of a message to recognise it. What matched, where the records could say."""
    said = str(one.get("excerpt") or one.get("body") or "").replace("\n", " ").strip()
    return said if len(said) <= ON_ONE_LINE else said[:ON_ONE_LINE - 1] + "…"


def _a_day(said: Optional[str]) -> Optional[str]:
    """A day somebody typed, as the moments in these records are written.

    The start of that day, so `--since 2026-08-01` includes everything said on the first rather than
    only what was said at midnight exactly.
    """
    return f"{said}T00:00:00Z" if said else None


def _failed(why: str, *and_so: str) -> int:
    return failed(f"messages: FAILED — {why}", *and_so)


def _mistyped(why: str) -> int:
    """The command line itself was wrong, which argparse's own code is for."""
    print(f"messages: FAILED — {why}")
    return USAGE

