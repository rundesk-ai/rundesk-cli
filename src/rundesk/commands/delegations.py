"""One agent's ask of another, from the command line.

Shaped like `channels` rather than like `roles`: every verb here is about one agent's own
asks, so the agent is the word after the verb and argparse holds it directly.

**Nothing here shows a local path or the task text** (R-DEL-15). A listing is read wherever
the agent is, and the task is the agent's own words to another agent.
"""

from __future__ import annotations

import argparse
import os
import sys

from rundesk import delegation as delegations
from rundesk import migration
from rundesk import store


#: How many of an agent's delegations a listing shows. Enough to cover what is in flight
#: and what settled today; the records hold the rest until their retention window closes.
DELEGATIONS_SHOWN = 20


def cmd_delegations(args: argparse.Namespace, agents) -> int:
    """What this agent has handed to other agents, and handing over one more."""
    if not agents.exists(args.name):
        print(f"{args.name}: NO SUCH AGENT", file=sys.stderr)
        print("        what there is:  rundesk agents", file=sys.stderr)
        return 1
    act = getattr(args, "act", None)
    if act == "ask":
        return _hand_to_an_agent(args)
    try:
        found = delegations.every()
    except delegations.Unreadable as why:
        print(f"{args.name}: RECORDS UNREADABLE — {why}", file=sys.stderr)
        return 1
    except (store.Unreadable, store.TooNew, store.Behind, migration.Failed) as why:
        print(f"{args.name}: RECORDS UNREADABLE — {why}", file=sys.stderr)
        return 1
    if act == "show":
        return _show_delegation(args, found)
    return _list_delegations(args, found)


def _mine(name: str, found: list) -> list:
    """Everything this agent handed over, newest first."""
    return list(reversed([one for one in found if one.get("from") == name]))


def _list_delegations(args: argparse.Namespace, found: list) -> int:
    """What this agent has handed to other agents — never a path and never the task."""
    mine = _mine(args.name, found)[:DELEGATIONS_SHOWN]
    if not mine:
        print("nothing handed to another agent right now")
        return 0
    for row in mine:
        it = delegations.shown(row)
        print(f"{it['id']}  {it['to']}  {it['state']}  {it['label']}"
              + ("  reviewed" if it["reviewed"] else ""))
    return 0


def _show_delegation(args: argparse.Namespace, found: list) -> int:
    """One delegation in full — never the task, never the answer, never a path."""
    for row in _mine(args.name, found):
        if row["id"] != args.ask:
            continue
        it = delegations.shown(row)
        for what in ("id", "from", "to", "label", "posture", "state", "parent_run",
                     "settled_at"):
            print(f"{what:16}{it[what]}")
        print(f"{'chain':16}{' then '.join(it['chain'])}")
        print(f"{'elapsed':16}{it['elapsed']}s")
        print(f"{'reviewed':16}{'yes' if it['reviewed'] else 'no'}")
        if row.get("given_up_at"):
            # Said plainly rather than left to be inferred from the attempt count: "nobody
            # has read this" is exactly the fact somebody reads a listing to find out.
            print(f"{'owed review':16}given up after {row.get('review_attempts')} attempts")
        elif not it["reviewed"]:
            print(f"{'owed review':16}yes, tried {row.get('review_attempts') or 0}")
        return 0
    print(f"{args.name}/{args.ask}: NO SUCH DELEGATION", file=sys.stderr)
    print(f"        what there is:  rundesk delegations {args.name}", file=sys.stderr)
    return 1


def _hand_to_an_agent(args: argparse.Namespace) -> int:
    """Hand one bounded task to another named agent, on behalf of the turn asking.

    **Only an agent's own turn may ask** (R-DEL-3). The answer is delivered back into that
    agent's own conversation, so the run that admits it has to be one of that agent's —
    which is what `RUNDESK_RUN` names and what the records then prove.

    The task is read from standard input rather than given as an argument: it is often
    several paragraphs, and an argument would put it in `ps` and in a shell history where
    the rest of a turn's words never go.
    """
    parent = os.environ.get("RUNDESK_RUN") or ""
    if not parent:
        print(f"{args.name}: NOT ADMITTED — a delegation is admitted by this agent's own "
              "turn, and nothing here is running one", file=sys.stderr)
        return 1
    if os.environ.get("RUNDESK_ROLE_RUN"):
        # A role execution has no identity of its own to be asking on behalf of, and the
        # named agent that put the role on hands work to another agent itself.
        print(f"{args.name}: NOT ADMITTED — a role execution cannot hand work to a named "
              "agent", file=sys.stderr)
        return 1
    if os.environ.get("RUNDESK_DELEGATION"):
        # Depth one (R-DEL-8). Said early and cheaply; what actually refuses is the durable
        # record below, which is why this is allowed to be a variable at all.
        print(f"{args.name}: NOT ADMITTED — work another agent handed over cannot be "
              "handed on; use this brain's own subagents instead", file=sys.stderr)
        return 1
    # **After every guard, and that order is the whole of it**: a guard that read standard
    # input first would hang on an empty pipe, which is what a brain's tool shell hands its
    # children.
    brief = sys.stdin.read()
    try:
        record = delegations.ask(
            args.name, args.to, brief, parent,
            label=getattr(args, "label", None),
            posture=getattr(args, "posture", None),
        )
    except delegations.NotDelegable as why:
        print(f"{args.name}: NOT ADMITTED — {why}", file=sys.stderr)
        print("        what agents there are:  rundesk agents", file=sys.stderr)
        return 1
    except (delegations.Unreadable, store.Unreadable, store.TooNew, store.Behind,
            migration.Failed) as why:
        print(f"{args.name}: RECORDS UNREADABLE — {why}", file=sys.stderr)
        return 1
    print(record["id"])
    print(f"        {record['label']} — handed to {record['to']}")
    print("        it runs in that agent's gateway; you are told when it answers")
    return 0
