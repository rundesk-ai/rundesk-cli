"""Work that starts itself: what an owner writes down, and what it has already done.

The arithmetic — what a schedule is, when one is next due — is `schedule.py`, which knows
nothing of gateways or processes. This is the other half: what an owner is asking to add,
change or run by hand, and what to show them about a firing that already happened.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime

from rundesk import gateway as _gateway
from rundesk import migration
from rundesk import process
from rundesk import secret
from rundesk import store
from rundesk.commands import _as_table, _note


def cmd_schedules(args: argparse.Namespace, gateways, agents) -> int:
    """List an agent's schedules, or change them."""
    if args.gateway_was:
        # Refused, and nothing written. The old spelling put the agent in the one place
        # `--run`'s remainder could swallow it, so a command that looked like it worked
        # added the schedule to a different agent (R-SCH-14).
        print("schedules: --gateway IS NOW THE WORD AFTER THE VERB", file=sys.stderr)
        print(f"        say:  rundesk schedules {args.gateway_was} ...", file=sys.stderr)
        return 2
    act = getattr(args, "act", None)
    if not agents.exists(args.name):
        # A schedule is something an agent keeps, so there is nowhere to put one for a name
        # that is not an agent. It used to land in a directory beside the agents, where a
        # gateway of that name would have read it; now it would have nowhere to go and
        # saying so is the only honest answer.
        print(f"{args.name}: NO SUCH AGENT — nothing of that name has been made",
              file=sys.stderr)
        print("        what there is:  rundesk agents", file=sys.stderr)
        return 1
    whose = agents.resolved(args.name)
    try:
        kept = agents.records(args.name) if act in ("add", "edit", "remove", "on", "off") \
            else agents.reading(args.name)
        if act == "add":
            return _add_schedule(args, gateways, kept, whose)
        if act == "edit":
            return _edit_schedule(args, gateways, kept, whose)
        if act == "show":
            return _show_schedule(args, kept)
        if act == "run":
            return _run_schedule(args, gateways, agents, kept, whose)
        if act in ("remove", "on", "off"):
            return _change_schedule(args, gateways, kept, whose, act)
        return _list_schedules(args, gateways, kept, whose)
    except (store.Unreadable, store.TooNew, store.Behind, migration.Failed) as why:
        # Answered in one place because every path here reads the same records, and each of
        # them turned "these cannot be read" into "there is nothing there": the listing said
        # NO SCHEDULES and exited zero, and a change would have written over records that
        # still held every schedule (R-SCH-17, R-SCH-18).
        print(f"{args.name}: SCHEDULES UNREADABLE — {why}", file=sys.stderr)
        print(f"        nothing was changed — what stands in the way:  "
              f"rundesk doctor {args.name}", file=sys.stderr)
        return 1


def _add_schedule(args: argparse.Namespace, gateways, kept, whose) -> int:
    from rundesk import schedule

    # What it runs is the tail, whichever way argparse ended up with it: `_handed_on` takes
    # it off in front of the parser, and the positional is there so the reference shows it.
    runs = list(args.options) + list(getattr(args, "handed_on", []))
    prompt = (args.prompt or "").strip()
    when = (args.when or "").strip()
    moment = (args.moment or "").strip()
    try:
        made = schedule.Schedule(args.schedule, when or None, at=moment or None)
    except schedule.NotASchedule as why:
        print(f"{args.name}/{args.schedule}: NOT ADDED — {why}", file=sys.stderr)
        if bool(when) == bool(moment):
            print('        say one:  --when "0 3 * * *"   or   '
                  f'--at "{schedule.SAID_AS}"', file=sys.stderr)
        return 1
    now = datetime.now()
    if made.expired_at(now):
        # Refused where it is typed rather than found never to have run. A moment behind us
        # can never come round again — unlike a cron nobody can reach, which at least says
        # `never` in the listing, this would sit there looking like work that is waiting.
        print(f"{args.name}/{args.schedule}: NOT ADDED — "
              f"{made.stated.strftime(schedule.A_MINUTE)} has already passed, so this could "
              f"never run", file=sys.stderr)
        print(f"        say a moment ahead of now, as {schedule.SAID_AS}", file=sys.stderr)
        return 1
    # Exactly one of the two, said here as well as refused by the records themselves: a
    # schedule that named both would leave rundesk choosing which, and the choice would be
    # invisible in the listing.
    if bool(prompt) == bool(runs):
        said = ("names both a program and a prompt" if prompt
                else "names neither a program to run nor a prompt to ask")
        print(f"{args.name}/{args.schedule}: NOT ADDED — it {said}", file=sys.stderr)
        print("        say one:  -- <program> …   or   --ask \"<prompt>\"", file=sys.stderr)
        return 1
    to = (args.channel or "").strip()
    if to and kept.channel(to) is None:
        # Refused where it is written rather than found at three in the morning, the same way
        # a program named rather than located is: a schedule reporting to a surface that is
        # not there says nothing, and looks exactly like one nobody asked to be told about.
        print(f"{args.name}/{args.schedule}: NOT ADDED — this agent has no channel called "
              f"'{to}'", file=sys.stderr)
        print(f"        what it has:  rundesk channels {args.name}", file=sys.stderr)
        return 1
    for named, said in (("--provider", args.provider), ("--model", args.model),
                        ("--instructions", args.says)):
        # Said rather than silently kept: these reach a brain, and a schedule that starts a
        # program has no brain for them to reach. Kept anyway they would sit in the records
        # meaning nothing, and read back as though the schedule were a turn.
        if said and not prompt:
            print(f"{args.name}/{args.schedule}: NOT ADDED — {named} is for a turn, and this "
                  f"schedule starts a program", file=sys.stderr)
            return 1
    if runs and not process.located(runs[0]):
        # Refused here rather than discovered at three in the morning. The gateway runs
        # with almost no PATH, so a program named rather than located resolves in the
        # shell that typed it and nowhere else (R-PROC-2) — and a schedule that cannot
        # start looks exactly like one that has simply never come due.
        print(f"{args.name}/{args.schedule}: NOT ADDED — '{runs[0]}' is a name, not a location; "
              f"give the full path (try: command -v {runs[0]})", file=sys.stderr)
        return 1
    # Asked so the ordinary case is answered in words an owner can act on. **It is not what
    # makes this safe** — asking and then writing is two decisions with a gap, and two of these
    # at once both found the name free. What makes it safe is that the write itself claims the
    # name and refuses, which is caught below.
    if kept.schedule(args.schedule) is not None:
        print(f"{args.name}/{args.schedule}: EXISTS — remove it first, or use a different name",
              file=sys.stderr)
        return 1
    try:
        kept.remember_schedule(args.schedule, when or None, store.stamped(),
                               # The minute it was understood as, not the characters somebody
                               # typed: a space where a `T` goes is the same moment, and one
                               # spelling is what the gateway compares and the listing shows.
                               at=made.stated.strftime(schedule.A_MINUTE) if made.once else None,
                               command=runs or None,
                               prompt=prompt or None,
                               provider=args.provider, model=args.model,
                               instructions=(args.says or "").strip() or None,
                               channel=to or None,
                               place=(args.place or "").strip() or None)
    except store.Taken:
        # The check above answers the ordinary case in words an owner can act on. This answers
        # the race: two of these asked at once both found the name free, and one of them is
        # about to be told it got something it did not.
        print(f"{args.name}/{args.schedule}: EXISTS — remove it first, or use a different name",
              file=sys.stderr)
        return 1
    except store.Refused as why:
        print(f"{args.name}/{args.schedule}: NOT ADDED — {why}", file=sys.stderr)
        return 1
    unlogged = _note(gateways, args.name,
                     f"schedule '{args.schedule}' added ({when or made.at})", whose)
    # Both named, because a schedule belongs to one agent and the success line saying only
    # its own name could not tell you it had landed on the wrong one.
    said = schedule.describe(made, now)
    print(f"{args.name}/{args.schedule}: ADDED — "
          + (f"runs once, at {said}" if made.once else f"next {said}"))
    return unlogged


def _change_schedule(args: argparse.Namespace, gateways, kept, whose, act: str) -> int:
    """Take a schedule away, or keep it and stop it running.

    Asked for before it is changed, because a change to a name that is not there is a
    change that did nothing and must say so rather than reporting a success (R-SCH-8). Two
    of these racing settle on the same answer either way: each write is one transaction, and
    turning a schedule off twice is off.
    """
    if kept.schedule(args.schedule) is None:
        print(f"{args.name}/{args.schedule}: NOT FOUND — no schedule by that name",
              file=sys.stderr)
        return 1
    if act == "remove":
        kept.forget_schedule(args.schedule)
        said, told = "REMOVED", f"schedule '{args.schedule}' removed"
    else:
        kept.enable_schedule(args.schedule, act == "on")
        said = "ON" if act == "on" else "OFF"
        told = f"schedule '{args.schedule}' turned {said.lower()}"
    unlogged = _note(gateways, args.name, told, whose)
    print(f"{args.name}/{args.schedule}: {said}")
    return unlogged


def _show_schedule(args: argparse.Namespace, kept) -> int:
    """One schedule, and everything it was given — whole, and changing nothing.

    The listing answers "what runs here, and when" in a row apiece, so what a schedule
    *says* is deliberately not in it: a prompt is a sentence and a program is a path, and
    neither fits a column beside six others. This is where they are read back, which until
    now nothing did — the only account of what a schedule asks was the one an owner
    remembered typing, and editing meant removing it and typing it again from that memory.

    Read through the reading path and writes nothing, for the reason `doctor` does not
    (R-AGT-12): the command an owner runs when a schedule looks wrong must not be the one
    that quietly changes it.
    """
    from rundesk import schedule

    row = kept.schedule(args.schedule)
    if row is None:
        print(f"{args.name}/{args.schedule}: NOT FOUND — no schedule by that name",
              file=sys.stderr)
        return 1
    wanted, refused = schedule.read([row])
    now = datetime.now()
    ran = row.get("last_auto_run_at")
    rows = [("state", "on" if row.get("enabled") else "off — kept, and not running")]
    if wanted:
        one = wanted[0]
        rows.append(("when", (one.stated.strftime(schedule.A_MINUTE) + "  (once)")
                     if one.once else str(one.when)))
        rows.append(("next", schedule.describe(one, now)))
    else:
        # Shown rather than refused. A cron nobody can parse is exactly when an owner needs
        # to see the characters they typed, and a command that answered such a schedule with
        # nothing at all would send them back to the database this exists to replace.
        rows.append(("when", str(row.get("cron") or row.get("at") or "-")))
        rows.append(("next", "NOT UNDERSTOOD — " + (refused[0][1] if refused else "?")))
    runs = row.get("command")
    rows.append(("it", "asks a turn" if row.get("prompt") else "starts a program"))
    rows.append(("asks" if row.get("prompt") else "runs",
                 str(row.get("prompt") or " ".join(runs or []) or "-")))
    if row.get("prompt"):
        # Only of a schedule that asks one. On a program these three cannot be set at all,
        # and rows saying so would be three lines of nothing on every schedule that runs one.
        rows.append(("brain", "/".join(
            one for one in (row.get("provider"), row.get("model")) if one)
            or "whatever the agent uses"))
        rows.append(("instructions", str(row.get("instructions") or "nothing of its own")))
    place = str(row.get("place") or "")
    if row.get("channel"):
        rows.append(("reports to",
                     str(row["channel"]) + (f", in {place}" if place else "")))
    elif place:
        # **A place with no surface to be a place on.** `add` permits `--in` without `--to`,
        # so the word is sitting in the row doing nothing — and a line saying only "nobody"
        # would positively assert it was not there, in the one command that exists so an
        # owner never has to open that database. Said here, a later `--to` switches on
        # delivery into a place they were shown rather than one they were told was absent.
        rows.append(("reports to", f"nobody — and {place} is kept, reaching nothing until "
                                   f"a channel is named"))
    else:
        rows.append(("reports to", "nobody — it is in the account either way"))
    rows.append(("last run", f"{ran} — {row.get('last_outcome') or '?'}" if ran
                 else "never"))
    rows.append(("added", str(row.get("created_at") or "-")))
    _as_table(("WHAT", "IS"), rows)
    return 1 if refused else 0


def _typed(one):
    """What an owner typed, without the space around it — and still `None` when they did not
    type it at all.

    The three states a change has to keep apart: absent leaves a field alone, empty says it
    off, and whitespace is empty (R-SCH-44). `add` has always stripped; a change that did
    not accepted `--ask "   "`, which `add` refuses outright, and left the schedule enabled
    and firing nightly asking a brain a blank line.
    """
    return one if one is None else one.strip()


def _edit_schedule(args: argparse.Namespace, gateways, kept, whose) -> int:
    """Change an existing schedule, keeping every record of what it has already done.

    **Only what is named moves.** Everything else is left exactly as it was, which is the
    whole difference between this and the path it replaces: removing a schedule and adding
    it again takes its firing history and its last outcome with it, and could only ever
    restore the parts an owner still remembered — because until `show` there was nothing
    that would tell them the rest.

    What `add` refuses, this refuses in the same words, because they are the same mistakes:
    a moment already behind us, a channel this agent has not got, a program named rather
    than located, and `--provider`/`--model`/`--instructions` on a schedule that starts a
    program rather than asking a turn.
    """
    from rundesk import schedule

    runs = list(args.options) + list(getattr(args, "handed_on", []))
    row = kept.schedule(args.schedule)
    if row is None:
        print(f"{args.name}/{args.schedule}: NOT FOUND — no schedule by that name",
              file=sys.stderr)
        return 1
    # Stripped as it arrives, the way `add` already does — every decision below is then
    # asked of what was meant rather than of what was typed around it (R-SCH-44).
    when, moment = _typed(args.when), _typed(args.moment)
    prompt, to = _typed(args.prompt), _typed(args.channel)
    given = {
        "cron": when, "at": moment, "prompt": prompt,
        "provider": _typed(args.provider), "model": _typed(args.model),
        "instructions": _typed(args.says),
        "channel": to, "place": _typed(args.place),
    }
    if runs:
        given["command"] = runs
    named = {key: value for key, value in given.items() if value is not None}
    if not named:
        print(f"{args.name}/{args.schedule}: NOTHING TO CHANGE — say what to change",
              file=sys.stderr)
        print(f"        what it is now:  rundesk schedules {args.name} show "
              f"{args.schedule}", file=sys.stderr)
        return 1
    if when and moment:
        print(f"{args.name}/{args.schedule}: NOT CHANGED — a schedule states a repeating "
              f"time or a single moment, never both", file=sys.stderr)
        return 1
    if prompt and runs:
        print(f"{args.name}/{args.schedule}: NOT CHANGED — a schedule starts a program or "
              f"asks a turn, never both", file=sys.stderr)
        return 1
    if moment:
        try:
            made = schedule.Schedule(args.schedule, None, at=moment)
        except schedule.NotASchedule as why:
            print(f"{args.name}/{args.schedule}: NOT CHANGED — {why}", file=sys.stderr)
            print(f"        say a moment ahead of now, as {schedule.SAID_AS}",
                  file=sys.stderr)
            return 1
        if made.expired_at(datetime.now()):
            print(f"{args.name}/{args.schedule}: NOT CHANGED — "
                  f"{made.stated.strftime(schedule.A_MINUTE)} has already passed, so this "
                  f"could never run", file=sys.stderr)
            return 1
        if (row.get("last_auto_run_at") or "").strip():
            # **The trap this whole option would otherwise walk into.** A single moment is
            # spent the instant anything durable says the clock started this schedule
            # (R-SCH-38), and that is written for every firing a repeating schedule ever
            # had. So a moment set on a schedule that has run would be `used` before it
            # arrived: the listing would show a time, and it could never come round. Adding
            # a new schedule is what an owner wants here, and it is said rather than left
            # to be discovered at the moment nothing happens.
            print(f"{args.name}/{args.schedule}: NOT CHANGED — the clock has already "
                  f"started this schedule, and a single moment is spent once it has "
                  f"(R-SCH-38), so it could never run", file=sys.stderr)
            print(f"        add a new schedule for that moment:  rundesk schedules "
                  f"{args.name} add <name> --at {moment}", file=sys.stderr)
            return 1
        named["at"] = made.stated.strftime(schedule.A_MINUTE)
    if when:
        try:
            schedule.Schedule(args.schedule, when)
        except schedule.NotASchedule as why:
            print(f"{args.name}/{args.schedule}: NOT CHANGED — {why}", file=sys.stderr)
            return 1
    if to and kept.channel(to) is None:
        print(f"{args.name}/{args.schedule}: NOT CHANGED — this agent has no channel "
              f"called '{to}'", file=sys.stderr)
        print(f"        what it has:  rundesk channels {args.name}", file=sys.stderr)
        return 1
    if runs and not process.located(runs[0]):
        print(f"{args.name}/{args.schedule}: NOT CHANGED — '{runs[0]}' is a name, not a "
              f"location; give the full path (try: command -v {runs[0]})", file=sys.stderr)
        return 1
    # **Asked of the schedule as it will be, not of what was typed.** These three reach a
    # brain, and a schedule that starts a program has none for them to reach — which `add`
    # already refuses. An edit can arrive at the same wrong row two ways: by naming one of
    # them on a program, and by turning a turn into a program while the columns it filled
    # stay behind. The second leaves no option to point at, so it is the row after the
    # change that is asked, and what is already there counts exactly as what was typed.
    asks_after = bool(named.get("prompt") or (row.get("prompt") and "command" not in named))
    if not asks_after:
        for option, key in (("--provider", "provider"), ("--model", "model"),
                            ("--instructions", "instructions")):
            after = named[key] if key in named else row.get(key)
            if not (after or "").strip():
                continue
            print(f"{args.name}/{args.schedule}: NOT CHANGED — {option} is for a turn, and "
                  f"this schedule "
                  + ("starts a program" if row.get("command")
                     else "would start a program after this change"), file=sys.stderr)
            # Never cleared on an owner's behalf. Dropping standing instructions because a
            # schedule changed shape is losing something nobody asked to lose — and saying
            # it in one line means the whole change is still one command.
            print('        say them off in the same breath:  --provider "" --model "" '
                  '--instructions ""', file=sys.stderr)
            return 1
    try:
        moved = kept.change_schedule(args.schedule, **named)
    except store.Refused as why:
        print(f"{args.name}/{args.schedule}: NOT CHANGED — {why}", file=sys.stderr)
        return 1
    except ValueError as why:
        print(f"{args.name}/{args.schedule}: NOT CHANGED — {why}", file=sys.stderr)
        return 1
    if not moved:
        # Removed between being read and being written. The change did nothing, and a
        # command that reported one anyway would be a success nobody can find afterwards.
        print(f"{args.name}/{args.schedule}: NOT FOUND — it was taken away while this was "
              f"being changed", file=sys.stderr)
        return 1
    # The names of what moved and never the words in it. A prompt and standing instructions
    # are an owner's own, and the log is read by whoever can read the file — what belongs in
    # an account is that they changed and when, which is what this says.
    changed = ", ".join(sorted(named))
    unlogged = _note(gateways, args.name,
                     f"schedule '{args.schedule}' edited ({changed})", whose)
    print(f"{args.name}/{args.schedule}: EDITED — {changed}")
    print(f"        what it is now:  rundesk schedules {args.name} show {args.schedule}")
    return unlogged


def _run_schedule(args: argparse.Namespace, gateways, agents, kept, whose) -> int:
    """Run what a schedule names, now, whether or not it is due (R-SCH-21).

    Here, in this terminal, and **nothing is written down** (R-SCH-22). What is due is
    decided from when each schedule last fired, so a run by hand that recorded itself
    would be indistinguishable from the schedule having come due — and would stop the
    real firing that minute. Running one to see what it does must not move when it next
    happens on its own.

    It runs here rather than inside the gateway because there is nothing to ask a gateway
    with: this is an operator doing by hand what the clock would otherwise do, and the
    honest place for that is the terminal that asked for it. The same environment the
    gateway would have given it, so what it does here is what it does at three in the
    morning (R-PROC-1).
    """
    from rundesk import schedule

    wanted, _ = schedule.read(kept.schedules())
    found = [one for one in wanted if one.name == args.schedule]
    if not found:
        print(f"{args.name}/{args.schedule}: NOT FOUND — no schedule by that name",
              file=sys.stderr)
        return 1
    one = found[0]
    if not one.run:
        print(f"{args.name}/{args.schedule}: NOTHING TO RUN — it names no program", file=sys.stderr)
        return 1
    now = datetime.now()
    was_due = schedule.describe(one, now)
    print(f"{args.name}/{args.schedule}: RUNNING BY HAND — {' '.join(one.run)}")
    said = asyncio.run(process.run(
        list(one.run),
        # Through what was passed in, never the module. Reaching for the real one here
        # read the machine's own directories from inside a suite that had redirected
        # nothing, which is the isolation every other line in this file keeps.
        # The install's own values too, so running a schedule by hand is the same run the
        # gateway would have made (R-SEC-1). Produced synchronously: this is a person at a
        # terminal with nothing else waiting on this process, not a gateway carrying work.
        env=dict(process.environment(whose.run or gateways.home(),
                                     agents=agents.agents_home(),
                                     secrets=secret.resolve().values),
                 **{_gateway.SCHEDULE_IS: one.name}),
        on_line=print,
    ))
    print(f"{args.name}/{args.schedule}: "
          + ("RAN" if said.ok else f"FAILED — {said.reason}")
          + (f" ({said.code})" if said.code else ""))
    # Said out loud, because the whole point of running one by hand is that it changes
    # nothing about when it runs on its own. **A single moment is not used up by this**
    # (R-SCH-22, R-SCH-39): only the clock reaching it can do that, so one still ahead is
    # still ahead afterwards, and one already gone is no more gone than it was.
    print(f"        next, unchanged: {was_due}" if not one.once
          else f"        its one moment, unchanged: "
               f"{one.stated.strftime(schedule.A_MINUTE)} ({was_due})")
    return 0 if said.ok else 1


def _became(outcome: str, up: bool) -> str:
    """What a schedule's last firing really came to, given whether its gateway is running.

    The one place the durable word and what is running are put together. `started` is
    written before the run begins and nothing rewrites it if the gateway dies, so read
    on its own it is indistinguishable from work happening right now — while the answer
    was already on disk, in the record saying no gateway of that name is up (R-SCH-24).
    """
    return _gateway.INTERRUPTED if outcome == _gateway.STARTED and not up else outcome


def _list_schedules(args: argparse.Namespace, gateways, kept, whose) -> int:
    """What this gateway runs on its own, when each next runs, and what became of it.

    This gateway's, and no other's: a gateway's schedules are its own, which is what
    makes one agent's schedules that agent's alone (R-SCH-13, R-SCH-14).
    """
    from rundesk import schedule

    rows = kept.schedules()
    wanted, refused = schedule.read(rows)
    now = datetime.now()
    ran = {row["name"]: row for row in rows}
    if args.expired:
        return _list_expired(args, [one for one in wanted if one.expired_at(now)], ran, refused)
    # What can still happen. A schedule whose one moment has gone can never be due again, so
    # it is no more part of what this agent runs than one that was removed — and leaving it
    # here would push the work that *is* waiting down a list of things that are over.
    spent = [one for one in wanted if one.expired_at(now)]
    wanted = [one for one in wanted if not one.expired_at(now)]
    if not wanted and not refused:
        print(f"{args.name}: NO SCHEDULES" + (" THAT CAN STILL RUN" if spent else ""))
        _also_expired(args, spent)
        return 0
    # A firing is written down before the run begins, so `started` on its own means only
    # that — and if no gateway of this name is up, nothing it started is still going. The
    # store is reconciled by the next gateway to claim the name (R-SCH-23); until one
    # does, showing the word as written presents dead work as in flight, which is the
    # first question asked after a crash answered wrongly (R-SCH-24).
    # `whose` is what `standing.of` would resolve, already resolved by the caller; asking
    # again here would mean threading `agents` through a signature to get the same answer.
    up = gateways.standing(args.name, whose.run).running
    rows = [(
        one.name,
        "OFF" if not one.enabled else "ON",
        # What it starts, said in one word rather than in full: a prompt is a sentence and a
        # program is a path, and neither fits a column beside four others. Which of the two it
        # is decides everything about how it runs, so it is the part worth showing.
        # What it starts, and where what that came to is said — one column, because a prompt
        # is a sentence and a program is a path and neither fits beside five others. Which of
        # the two it is decides everything about how it runs, and where it reports is the
        # thing an owner asks next.
        _what_it_starts(one),
        # The one moment where it states one, so the WHEN column answers the same question
        # for both kinds — when does this run — rather than being blank for half of them.
        one.stated.strftime(schedule.A_MINUTE) if one.once else one.when,
        schedule.describe(one, now),
        ran.get(one.name, {}).get("last_auto_run_at") or "-",
        _became(ran.get(one.name, {}).get("last_outcome") or "-", up),
    ) for one in wanted]
    _as_table(("SCHEDULE", "STATE", "IT", "WHEN", "NEXT", "LAST RUN", "OUTCOME"), rows)
    _also_expired(args, spent)
    for name, why in refused:
        print(f"{name or '(unnamed)'}: NOT UNDERSTOOD — {why}", file=sys.stderr)
    return 1 if refused else 0


def _what_it_starts(one) -> str:
    """What this schedule starts, and where what that came to is said — one column.

    Said in a word rather than in full: a prompt is a sentence and a program is a path and
    neither fits beside five others. Which of the two it is decides everything about how it
    runs, and where it reports is the thing an owner asks next.
    """
    return ("asks" if one.prompt else "runs") + (f" → {one.channel}" if one.channel else "")


def _also_expired(args: argparse.Namespace, spent: list) -> None:
    """Say that there are schedules this listing left out, and how to read them.

    The listing shows work that can still happen, which is what an owner wants nine times in
    ten. The tenth is "did that run?", and an option nobody knows about cannot answer it —
    so the listing names the option rather than leaving it to be discovered.
    """
    if not spent:
        return
    print(f"        {len(spent)} expired — "
          f"rundesk schedules {args.name} --expired")


def _list_expired(args: argparse.Namespace, spent: list, ran: dict, refused: list) -> int:
    """The one-time schedules whose moment has gone, and which kind of gone each is
    (R-SCH-40, R-SCH-41).

    **Two ways to be expired, and they are not the same news** (R-SCH-4): one came due while
    a gateway was up and ran, and its outcome says what that came to; the other's moment
    passed while nothing was running, so it never ran at all. An owner told only that both
    are over cannot tell work that happened from work that silently did not — which is the
    whole question this listing exists to answer.

    Nothing is deleted to get here. What each of these last did, and the run that says which
    schedule started it, are exactly as they were.
    """
    from rundesk import schedule

    if not spent:
        print(f"{args.name}: NOTHING EXPIRED")
        return 1 if refused else 0
    rows = [(
        one.name,
        _what_it_starts(one),
        one.stated.strftime(schedule.A_MINUTE),
        ran.get(one.name, {}).get("last_auto_run_at") or "-",
        schedule.became_of(one, ran.get(one.name, {}).get("last_outcome")),
    ) for one in spent]
    _as_table(("SCHEDULE", "IT", "WHEN", "RAN AT", "OUTCOME"), rows)
    for name, why in refused:
        print(f"{name or '(unnamed)'}: NOT UNDERSTOOD — {why}", file=sys.stderr)
    return 1 if refused else 0
