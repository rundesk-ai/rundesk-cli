"""The specialists an owner writes, and handing work to one.

A role is what an owner writes a specialist as, so nothing here rewrites one: a shipped role
is laid down where it is missing and never over one that is there (R-ROL-18).
"""

from __future__ import annotations

import argparse
import os
import sys

from rundesk import migration
from rundesk import role
from rundesk import role_run as role_runs
from rundesk import store


#: How many of an agent's role runs a listing shows. Enough to cover what is in flight
#: and what finished today; the records hold the rest.
ROLE_RUNS_SHOWN = 20

def cmd_roles(args: argparse.Namespace, agents) -> int:
    """What an agent can hand heavy execution to, and what it has handed over."""
    if not agents.exists(args.name):
        print(f"{args.name}: NO SUCH AGENT", file=sys.stderr)
        print("        what there is:  rundesk agents", file=sys.stderr)
        return 1
    act = getattr(args, "act", None)
    if act == "run":
        return _hand_to_a_role(args, agents)
    if act in ("say", "stop", "resume"):
        return _guide_a_role(args, act)
    try:
        whose = agents.reading(args.name)
    except (store.Unreadable, store.TooNew, store.Behind, migration.Failed) as why:
        print(f"{args.name}: RECORDS UNREADABLE — {why}", file=sys.stderr)
        return 1
    if act == "show":
        return _show_role_run(args, whose)
    return _list_roles(args, whose)


def _list_roles(args: argparse.Namespace, whose) -> int:
    """The roles this agent may reach for, and the runs it has already admitted."""
    installed = role.known()
    if not installed:
        print("no roles installed")
    for slug in installed:
        try:
            one = role.read(slug)
        except role.NotARole as why:
            print(f"{slug}  UNUSABLE — {why}")
            continue
        print(f"{one.label}  {one.slug}  {one.revision[:12]}  "
              f"{one.posture}  [{' '.join(one.skills)}]")
        print(f"        {one.description}")
        if one.missing:
            # Said every time it is listed. A set quietly smaller than its manifest is the
            # kind of difference nobody notices until the work comes back thin.
            print(f"        not installed here, so not given: {' '.join(one.missing)}")
    runs = whose.role_runs(limit=ROLE_RUNS_SHOWN)
    if not runs:
        return 0
    print()
    for row in runs:
        it = role_runs.shown(row)
        print(f"{it['id']}  {it['role']}  {it['state']}  {it['label']}"
              + (f"  in {it['target']}" if it["target"] else "")
              + ("  reviewed" if it["reviewed"] else ""))
    return 0


def _show_role_run(args: argparse.Namespace, whose) -> int:
    """One role run in full — never its brief, and never a local path (R-ROL-17)."""
    row = whose.role_run(args.run)
    if row is None:
        print(f"{args.name}/{args.run}: NO SUCH ROLE RUN", file=sys.stderr)
        print(f"        what there is:  rundesk roles {args.name}", file=sys.stderr)
        return 1
    it = role_runs.shown(row)
    for what in ("id", "role", "label", "revision", "posture", "state", "outcome",
                 "parent_run", "target", "retained_until"):
        print(f"{what:16}{it[what]}")
    print(f"{'skills':16}{' '.join(it['skills'])}")
    print(f"{'elapsed':16}{it['elapsed']}s")
    print(f"{'reviewed':16}{'yes' if it['reviewed'] else 'no'}")
    waiting = whose.words_waiting(args.run)
    if waiting:
        print(f"{'waiting to say':16}{waiting}")
    if row.get("stop_asked_at"):
        print(f"{'stop asked':16}{row['stop_asked_at']}")
    owed = role_runs.owed_review(args.name, args.run)
    if owed["owed"]:
        # Said only while one is owed, and with the count: a review tried many times and
        # never delivered is the shape of a surface that is not coming back, and nothing
        # else an owner can read says so.
        print(f"{'owed review':16}yes, tried {owed['attempts']}")
    return 0


def _hand_to_a_role(args: argparse.Namespace, agents) -> int:
    """Admit one role run for this agent, on behalf of the turn asking (R-ROL-4).

    **Only an agent's own turn may ask.** A role acts on a named agent's behalf
    and answers into that agent's conversation, so the run that admits it has to be one of
    that agent's — which is what `RUNDESK_RUN` names and what the records then prove.

    The brief is read from standard input rather than given as an argument: it is the task,
    it is often several paragraphs, and an argument would put it in `ps` and in a shell
    history where the rest of a turn's words never go.
    """
    parent = os.environ.get("RUNDESK_RUN") or ""
    if not parent:
        print(f"{args.name}: NOT ADMITTED — a role run is admitted by this agent's own "
              "turn, and nothing here is running one", file=sys.stderr)
        return 1
    if os.environ.get("RUNDESK_ROLE_RUN"):
        # Said early and cheaply. What actually refuses is the durable record below, which
        # is why this is allowed to be a variable at all (R-ROL-13).
        print(f"{args.name}: NOT ADMITTED — a role run cannot start another one",
              file=sys.stderr)
        return 1
    brief = sys.stdin.read()
    try:
        admitted = role_runs.admit(
            args.name, args.role, brief, parent,
            target=getattr(args, "target", None), label=getattr(args, "label", None),
        )
    except role_runs.NotDelegable as why:
        print(f"{args.name}: NOT ADMITTED — {why}", file=sys.stderr)
        print(f"        what it can hand work to:  rundesk roles {args.name}",
              file=sys.stderr)
        return 1
    except (store.Unreadable, store.TooNew, store.Behind, migration.Failed) as why:
        print(f"{args.name}: RECORDS UNREADABLE — {why}", file=sys.stderr)
        return 1
    print(admitted.id)
    print(f"        {admitted.label} — {role.label(admitted.role)}, "
          f"retained until {admitted.retained_until}")
    print("        it runs in this agent's gateway; you are told when it reports back")
    return 0


def _guide_a_role(args: argparse.Namespace, act: str) -> int:
    """Say something to a role run, end one, or carry a finished one on (R-ROL-23).

    **Three verbs because there are three things to mean**, and each refusal names the one
    that was wanted. A single verb that guessed from the run's state would say something
    into work in flight when an owner meant to start it again, and spend a turn's money
    doing it.
    """
    said = sys.stdin.read() if act in ("say", "resume") else ""
    try:
        if act == "stop":
            if not role_runs.stop(args.name, args.run):
                print(f"{args.name}/{args.run}: ALREADY OVER — nothing was running to end",
                      file=sys.stderr)
                return 1
            print(f"{args.run} was asked to stop")
            print("        it ends as soon as this agent's gateway reaches it")
            return 0
        if act == "say":
            # Said *after* it was taken, never before: a line printed on the way in is a
            # line a refusal cannot take back, and this one reported success while the
            # command was busy failing.
            lands = role_runs.say(args.name, args.run, said)
            print(f"said to {args.run}")
            print(f"        {lands}")
            return 0
        role_runs.resume(args.name, args.run, said)
        print(f"{args.run} was carried on")
        print("        it starts again in the conversation it already had")
        return 0
    except role_runs.NotDelegable as why:
        print(f"{args.name}/{args.run}: NOT DONE — {why}", file=sys.stderr)
        print(f"        where it stands:  rundesk roles {args.name} show {args.run}",
              file=sys.stderr)
        return 1
    except (store.Unreadable, store.TooNew, store.Behind, migration.Failed) as why:
        print(f"{args.name}: RECORDS UNREADABLE — {why}", file=sys.stderr)
        return 1
