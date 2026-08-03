"""The specialists an owner writes, and handing work to one.

A role is what an owner writes a specialist as, so nothing here rewrites one: a shipped role
is laid down where it is missing and never over one that is there (R-ROL-18).
"""

from __future__ import annotations

import argparse
import os
import sys

from rundesk import migration
from rundesk import provider
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
    if act == "add":
        # Before the records are opened: writing a role touches none of them, and an
        # agent whose database will not read is not a reason this install cannot have
        # a specialist written for it.
        return _write_a_role(args)
    if act == "edit":
        return _edit_a_role(args)
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


def _a_role_reads_as(one: role.Role) -> list:
    """One role as it is shown, in the one shape both listing it and writing it use."""
    lines = [f"{one.label}  {one.slug}  {one.revision[:12]}  "
             f"{one.posture}  [{' '.join(one.skills)}]",
             f"        {one.description}"]
    if one.provider or one.model:
        # Said before anybody hands it work, because a pinned brain decides what this
        # role can do: not every brain can be sent to mid-turn, so a role pinned to
        # one that cannot is a role no `say` will ever reach (R-ROL-34).
        lines.append("        it runs on "
                     + (provider.label(one.provider) if one.provider
                        else "whatever this turn is on")
                     + (f", model {one.model}" if one.model else ""))
    if one.missing:
        # Said every time it is shown. A set quietly smaller than its manifest is the
        # kind of difference nobody notices until the work comes back thin.
        lines.append(f"        not installed here, so not given: "
                     f"{' '.join(one.missing)}")
    return lines


def _write_a_role(args: argparse.Namespace) -> int:
    """Write one new role, and say what is left to do before it is given real work.

    **The answer is the point of this command, not a courtesy.** What is written is a
    generic skeleton that says nothing about the specialty, so a caller that comes away
    without knowing there is an unfinished file and where it stands has been handed a
    role that will return a report reading well and saying nothing. The path is absolute
    and the instruction is explicit, and the headings to fill in are read off the file
    that was actually written rather than restated here.
    """
    try:
        made = role.write(
            args.role,
            description=args.description,
            skills=[one.strip() for one in (args.skills or "").split(",")
                    if one.strip()],
            posture=args.posture,
            provider_named=(args.provider or "").strip(),
            model=(args.model or "").strip(),
        )
    except role.NotARole as why:
        print(f"{args.role}: NOT WRITTEN — {why}", file=sys.stderr)
        print(f"        what there already is:  rundesk roles {args.name}",
              file=sys.stderr)
        return 1
    except OSError as why:
        print(f"{args.role}: NOT WRITTEN — {why}", file=sys.stderr)
        return 1
    for line in _a_role_reads_as(made):
        print(line)
    print("        written for this whole install — every named agent on it may put "
          "it on")
    rules = made.at / role.INSTRUCTIONS
    print(f"        its rules stand at {rules}")
    headings = [one.strip()[3:] for one in made.instructions.splitlines()
                if one.startswith("## ")]
    print(f"        that file is the generic skeleton and is not yet about this "
          f"specialty — rewrite it before {made.slug} is handed real work, filling in "
          f"{'; '.join(headings)}")
    print(f"        then:  rundesk roles {args.name} run {made.slug} "
          f"--target <directory>")
    return 0


def _edit_a_role(args: argparse.Namespace) -> int:
    """Change what a role says about itself, and say what moved (R-ROL-40).

    **What moved is the answer, not the new state.** A caller who asked for one field
    and reads back a whole role cannot tell what their command did from what was already
    true — and `--skills` replacing the set rather than joining it is exactly the
    difference a reader assumes their way past. The revision is said twice over, old and
    new, because it is how a run's locked bytes are identified afterwards.
    """
    named = {}
    for field in role.FIELDS:
        said = getattr(args, field, None)
        if said is None:
            # Omitted and empty are different answers: no flag keeps what the role says,
            # and an empty one is a decision to say nothing (R-ROL-33).
            continue
        named[field] = ([one.strip() for one in said.split(",") if one.strip()]
                        if field == "skills" else said.strip())
    try:
        before, after = role.edit(args.role, **named)
    except role.NotARole as why:
        print(f"{args.role}: NOT CHANGED — {why}", file=sys.stderr)
        print(f"        what there is:  rundesk roles {args.name}", file=sys.stderr)
        return 1
    except OSError as why:
        print(f"{args.role}: NOT CHANGED — {why}", file=sys.stderr)
        return 1
    for line in _a_role_reads_as(after):
        print(line)
    moved = _what_moved(before, after)
    for line in moved or ["nothing moved — it already said all of that"]:
        print(f"        {line}")
    print(f"        revision {before.revision[:12]} → {after.revision[:12]}")
    print("        it lands on the next run — every run in flight keeps the bytes it "
          "was admitted with")
    print(f"        its rules stand at {after.at / role.INSTRUCTIONS}, and this did not "
          f"touch them — a specialty that moved is yours to bring in line")
    if after.slug in role.shipped():
        # Said for a shipped slug and only for one. What proves a role is still
        # Rundesk's is that it is byte for byte what Rundesk wrote, so this edit is what
        # makes it the owner's — which is not a refusal, but is not reversible either.
        print(f"        {after.slug} is a role this release ships, and one character "
              f"different and it is yours: an uninstall now leaves it standing and no "
              f"release will ever bring it forward")
    return 0


def _what_moved(before: role.Role, after: role.Role) -> list:
    """The fields this edit actually changed, old then new — and only those.

    The skills are compared as the manifest asks for them rather than as this machine
    resolved them: a name no skill here answers to is still part of what the role says,
    and reporting the resolved set would show a change nobody made.
    """
    def asked_for(one: role.Role) -> str:
        return " ".join(sorted([*one.skills, *one.missing]))

    lines = []
    for field, was, now in (("description", before.description, after.description),
                            ("skills", asked_for(before), asked_for(after)),
                            ("posture", before.posture, after.posture),
                            ("provider", before.provider, after.provider),
                            ("model", before.model, after.model)):
        if was != now:
            lines.append(f"{field}: {was or 'nothing'} → {now or 'nothing'}")
    return lines


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
        for line in _a_role_reads_as(one):
            print(line)
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
    # The brain it actually ran on, which is a question only the run can answer: the role
    # may have been edited since, and the agent reconfigured (R-ROL-34). Said only where
    # one was recorded — a run admitted by an older release ran on whatever its parent
    # turn resolved and nothing wrote down which that was.
    if it["provider"]:
        print(f"{'brain':16}{it['provider']}"
              + (f"  {it['model']}" if it["model"] else ""))
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
            named=getattr(args, "provider", None), model=getattr(args, "model", None),
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
