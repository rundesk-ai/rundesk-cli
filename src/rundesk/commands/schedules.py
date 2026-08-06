"""Work an agent starts because the time came, and the six things anybody does with a schedule.

`rundesk schedules` on its own lists every one there is, the way `agents` and `gateways` do, because
listing is what somebody wants nine times in ten. The other five are named: `add`, `update`, `show`,
`run` and `remove`.

This decides only how a person types it and what they are shown. When a schedule is due belongs to
`schedules.due`, what an agent keeps belongs to `schedules.kept`, and starting the work belongs to
`schedules.firing` — and nothing here reaches past them to a database or a lock.

## A schedule is stated on this machine's own clock

`--when` is a repeating time in the five fields schedules have always used, and `--at` is one moment
written `YYYY-MM-DDTHH:MM`. Both are local, kept exactly as typed, and a moment carrying a zone or a
`Z` is refused rather than quietly converted — an owner who wrote one means something rundesk cannot
honour. What a schedule last *did* is recorded in UTC, because that is compared and sorted, and it is
shown back in local time with its offset like every other moment a person reads.

## `--run` takes one string and never reaches a shell

`--run '/usr/local/bin/backup.sh --full'` is split into words the way a shell would split them and
then handed straight to `execve` as a list. Nothing in it is globbed, expanded, or read as `;`, `&&`
or a redirection, so a schedule cannot mean one thing when a person tests it and another when the
gateway runs it. **The program is located when the schedule is added**, so a path that is not there
is refused where somebody can fix it rather than at two in the morning in a log.

## A schedule either asks the agent or starts a program, and never both

`--ask` and `--run`, exactly one of them — the records hold that as a `CHECK` and this says it in
words, because "one of these two" is the kind of rule a person meets by typing neither.

**An asking schedule gets a conversation of its own**, keyed by its name, so a run at three in the
morning never lands in the exchange somebody types into. `providers.answering` is what takes that
turn; nothing here knows how, which is why this file gained two `add_argument` lines and one branch
and nothing else moved.

## Running one by hand is a person checking their own work

`run` starts it in this terminal, waits, and prints what the program wrote. It takes the same lock
the clock takes, so it cannot start a second copy of work a gateway is already doing. It writes down
what became of it, because it did run — and it leaves the minute the schedule next falls due exactly
where it was, because testing a schedule must not be how you stop it happening.
"""

import argparse
import contextlib
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from rundesk.agents import directory, migration, records
from rundesk.commands import Subcommands, as_written, failed
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK, USAGE
from rundesk.providers import answering, turns
from rundesk.schedules import due, firing, kept
from rundesk.utils import locking, programs
from rundesk.utils.terminal import as_table

#: How long `run` waits for a program before giving up on it, and the flag that changes it. An hour,
#: because a schedule somebody runs by hand is usually the slow one they are checking — and a ceiling
#: rather than none at all, because a command that never returns is the failure this product refuses
#: everywhere it appears.
WAITING = 3600.0

#: Everything the schedules layer hands back that a verb here has to turn into a sentence.
#:
#: Spelled out rather than caught as `Exception`, because these are different situations with
#: different things to do about them: a refusal this product decided, records that are not there or
#: cannot be understood, an agent whose name reaches outside where agents are kept, a migration that
#: has not run, the install lock held by something else, and the ordinary failures of a disk.
TROUBLE = (kept.Refused, due.NotASchedule, directory.Refused, records.NotThere, records.Unreadable,
           records.Refused, migration.Ahead, migration.Broken, locking.Stuck, OSError, sqlite3.Error)


def register(sub: Subcommands) -> None:
    """Put `schedules` on the parser, with one sub-verb for each thing that happens to a schedule.

    **Nothing here is `required=True`, including what to run and when.** argparse's own refusal names
    a flag and does not say what to type, and every one of these guards an effect rather than
    describing one — so the verb refuses instead, at exit `1`, in a sentence ending with the whole
    command somebody should run. That is the shape `agents add --provider` already has.

    `--enable` and `--disable` are two flags rather than one taking a word, because `--enabled no` is
    a thing to get subtly wrong and `--disable` is not.
    """
    kept_here = sub.add_parser("schedules", help="work an agent starts because the time came")
    what = kept_here.add_subparsers(dest="what", metavar="<what>")

    every = what.add_parser("list", help="what one agent has scheduled, or every agent's")
    every.add_argument("agent", metavar="<agent>", nargs="?", default=None,
                       help="which agent — with none, every agent on this install")

    new = what.add_parser("add", help="schedule something")
    _named(new)
    _stated(new, "required — ")
    new.add_argument("--disabled", action="store_true",
                     help="keep it and do not run it until it is enabled")

    changed = what.add_parser("update", help="change a schedule, keeping what it has already done")
    _named(changed)
    _stated(changed, "")
    changed.add_argument("--enable", action="store_true", help="let it run again")
    changed.add_argument("--disable", action="store_true", help="keep it and stop running it")

    shown = what.add_parser("show", help="everything one schedule was given")
    _named(shown)

    here = what.add_parser("run", help="run one now, in this terminal, whether or not it is due")
    _named(here)
    here.add_argument("--wait", metavar="<seconds>", type=float, default=WAITING,
                      help=f"how long to give it (default: {WAITING:g})")

    gone = what.add_parser("remove", help="take a schedule away")
    _named(gone)


def _named(one: argparse.ArgumentParser) -> None:
    """The two positionals every sub-verb but `list` takes: whose schedule, and which one."""
    one.add_argument("agent", metavar="<agent>", help="which agent, as `rundesk agents` lists it")
    one.add_argument("schedule", metavar="<schedule>",
                     help="what to call it, as `rundesk schedules` lists it")


def _stated(one: argparse.ArgumentParser, required: str) -> None:
    """What a schedule says and what it starts, spelled the same way by `add` and by `update`.

    One function because the two verbs take exactly the same set and a second copy is a second set
    of help strings to keep true. What differs is only whether the words *required —* appear, and
    `update`'s own refusals say the rest.
    """
    one.add_argument("--when", metavar="<cron>", default=None,
                     help=f"{required}how often, in the five fields schedules use: 'minute hour "
                          "day month weekday', on this machine's clock")
    one.add_argument("--at", metavar="<moment>", default=None,
                     help=f"{required}the one moment it runs, as YYYY-MM-DDTHH:MM, "
                          "on this machine's clock — instead of --when, never as well as")
    one.add_argument("--until", metavar="<moment>", default=None,
                     help="the moment it is finished, after which it never runs again")
    one.add_argument("--run", metavar="<program>", dest="program", default=None,
                     help=f"{required}the program to start, with its arguments, as one quoted "
                          "string — never through a shell")
    one.add_argument("--ask", metavar="<prompt>", dest="prompt", default=None,
                     help=f"{required}what to ask the agent, instead of --run — its own "
                          "conversation, so it never lands in the one somebody types into")


def cmd_schedules(args: argparse.Namespace) -> int:
    """Answer whichever of the six was asked for; with none of them, list what there is."""
    try:
        paths.home()
    except paths.Refused as why:
        return _failed(str(why))

    what = getattr(args, "what", None)
    if what in (None, "list"):
        return _listed(getattr(args, "agent", None))
    if what == "add":
        return _added(args)
    if what == "update":
        return _changed(args)
    if what == "show":
        return _shown(args.agent, args.schedule)
    if what == "run":
        return _ran(args.agent, args.schedule, args.wait)
    if what == "remove":
        return _forgotten(args.agent, args.schedule)

    # Unreachable while every sub-verb above is answered, and that is the point: one registered on
    # the parser and wired to nothing fails here loudly rather than exiting 0 having done nothing.
    raise AssertionError(f"schedules {what} is registered on the parser and answered by nothing")


def _listed(agent: Optional[str]) -> int:
    """Every schedule there is, or one agent's, with when each next runs and what it last did.

    Where they are kept is printed even when there are none, for the reason `agents` prints it: "no
    schedules" and "no schedules *for this agent*" are different things to learn, and somebody
    looking at the wrong install needs to see which directory was just found empty.

    An agent whose schedules cannot be read is listed saying so rather than left out. Leaving it out
    would say the agent has none, which is a different and worse thing to be told.
    """
    if agent is not None:
        gone_wrong = directory.not_an_agent(agent)
        if gone_wrong:
            return _failed(gone_wrong, "see what there is with: rundesk agents", "nothing was listed")
        names = [agent]
    else:
        try:
            names = directory.known()
        except OSError as why:
            return _failed(str(why), "nothing was listed")

    where = f"schedules for {agent}" if agent else f"schedules in {paths.agents()}"
    print(where)
    rows: List[Tuple[str, ...]] = []
    for name in names:
        rows.extend(_rows_for(name, showing_who=agent is None))
    if not rows:
        print("        nothing is scheduled yet — add one with: rundesk schedules add "
              "<agent> <schedule> --when '<cron>' --run '<program>'")
        return OK
    head = ("SCHEDULE", "WHEN", "NEXT", "LAST")
    as_table(("AGENT", *head) if agent is None else head, rows)
    return OK


def _rows_for(agent: str, showing_who: bool) -> List[Tuple[str, ...]]:
    """One agent's schedules as lines of a table, or one line saying why they could not be read."""
    now = _now()
    try:
        found = kept.all(agent)
    except TROUBLE as why:
        return [((agent,) if showing_who else ()) + ("?", "?", "?", f"cannot be read — {why}")]

    rows = []
    for row in found:
        try:
            one = due.understood(row)
            when = one.cron or one.run_at or ""
            following = due.describe(one, now)
        except due.NotASchedule as why:
            # Shown rather than dropped. A schedule nobody can understand is on the disk and is
            # something to be done about, and a listing that left it out would say it is not there.
            when, following = str(row.get("cron") or row.get("run_at") or ""), f"cannot be read — {why}"
        rows.append(((agent,) if showing_who else ())
                    + (str(row.get("name") or ""), when, following, _last(agent, row)))
    return rows


def _last(agent: str, row: Dict[str, Any]) -> str:
    """What became of this schedule last time, or that it is running right now.

    Running is asked of the kernel through the lock, never of the row: an outcome is what the *last*
    firing came to, and a schedule that is working right now would otherwise read as whatever it did
    yesterday.
    """
    name = str(row.get("name") or "")
    try:
        if name and firing.still_running(agent, name):
            return "running"
    except OSError:
        pass
    outcome = row.get("last_outcome")
    if not outcome:
        return "never ran"
    return f"{outcome} {_as_local(row.get('last_run_at'))}"


def _added(args: argparse.Namespace) -> int:
    """Write a new schedule down, or refuse having written nothing."""
    trouble = _what_it_needs(args, f"rundesk schedules add {args.agent} {args.schedule}")
    if trouble:
        return _failed(trouble, "nothing was added")

    gone_wrong = directory.not_an_agent(args.agent)
    if gone_wrong:
        return _failed(gone_wrong, "see what there is with: rundesk agents", "nothing was added")

    values = {"cron": args.when, "run_at": args.at, "expire_at": args.until,
              "command": args.program, "agent_prompt": args.prompt,
              "enabled": 0 if args.disabled else 1}
    try:
        # Understood before it is written, so a cron nobody can parse is refused where it was typed
        # rather than found by a gateway at the moment it was meant to run. The records refuse the
        # pairs; this refuses what only a reader can see.
        due.understood(dict(values, name=args.schedule))
        kept.added(args.agent, args.schedule, values)
    except TROUBLE as why:
        return _failed(str(why), "nothing was added")

    print(f"schedule {args.schedule} added for {args.agent}")
    return _described(args.agent, args.schedule)


def _changed(args: argparse.Namespace) -> int:
    """Change one schedule in place, or refuse having changed nothing.

    **Naming nothing to change is refused rather than reported as a success.** `agents configure`
    makes the same decision for the same reason: a command that reports success having changed
    nothing teaches somebody it worked, and the next thing they do rests on a change that never
    happened.
    """
    if args.enable and args.disable:
        return _mistyped(f"{args.schedule} cannot be enabled and disabled at once",
                         "say one of them, not both", "nothing was changed")

    values = {}
    if args.program is not None and args.prompt is not None:
        return _mistyped(f"{args.schedule} starts a program or asks the agent, never both",
                         "say --run or --ask, not the two of them", "nothing was changed")
    if args.prompt is not None:
        values["agent_prompt"] = args.prompt
        values["command"] = None
    if args.when is not None:
        # **One replaces the other.** A schedule states a repeating time or one moment, so setting
        # either has to clear the other or the records refuse the pair — and the refusal would be
        # about a column somebody did not type.
        values["cron"], values["run_at"] = args.when, None
    if args.at is not None:
        values["cron"], values["run_at"] = None, args.at
    if args.until is not None:
        values["expire_at"] = args.until
    if args.program is not None:
        values["command"] = args.program
    if args.enable:
        values["enabled"] = 1
    if args.disable:
        values["enabled"] = 0

    if not values:
        return _failed(f"nothing was named to change about {args.schedule}",
                       "change one with: rundesk schedules update "
                       f"{args.agent} {args.schedule} --when '<cron>'",
                       "nothing was changed")

    gone_wrong = directory.not_an_agent(args.agent)
    if gone_wrong:
        return _failed(gone_wrong, "see what there is with: rundesk agents", "nothing was changed")
    if "command" in values:
        trouble = firing_trouble(args.program)
        if trouble:
            return _failed(trouble, "nothing was changed")

    try:
        # Read, changed in a copy and understood before anything is written, so a change that would
        # leave a schedule nobody can act on is refused with the schedule as it was.
        was = kept.one(args.agent, args.schedule)
        due.understood(dict(was, **values))
        kept.changed(args.agent, args.schedule, values)
    except TROUBLE as why:
        return _failed(str(why), "nothing was changed")

    print(f"schedule {args.schedule} changed for {args.agent}")
    return _described(args.agent, args.schedule)


def _shown(agent: str, name: str) -> int:
    """Everything one schedule was given, read back whole. Changes nothing."""
    gone_wrong = directory.not_an_agent(agent)
    if gone_wrong:
        return _failed(gone_wrong, "see what there is with: rundesk agents", "nothing was shown")
    try:
        kept.one(agent, name)
    except TROUBLE as why:
        return _failed(str(why), "nothing was shown")
    print(f"schedule {name} for {agent}")
    return _described(agent, name)


def _described(agent: str, name: str) -> int:
    """The whole of one schedule, in the shape `agents add` reports what it made.

    A schedule nobody can understand is still shown, because it is on the disk and is something to
    be done about — what cannot be worked out is said in the line it belongs to rather than
    replacing the readout with a refusal.
    """
    try:
        row = kept.one(agent, name)
    except TROUBLE as why:
        return _failed(str(why), "nothing was shown")

    now = _now()
    print(f"        when      {as_written(row.get('cron') or row.get('run_at'))}")
    print(f"        run       {as_written(row.get('command'))}")
    print(f"        until     {as_written(row.get('expire_at'))}")
    print(f"        enabled   {as_written(bool(row.get('enabled')))}")
    try:
        one = due.understood(row)
        print(f"        next      {due.describe(one, now)}")
    except due.NotASchedule as why:
        print(f"        next      cannot be worked out — {why}")
    print(f"        last      {_last(agent, row)}")
    print(f"        logs      {directory.logs(agent)}")
    print(f"        output    {firing.output_of(agent, name)}")
    return OK


def _asks_the_agent(agent: str, name: str) -> bool:
    """Whether this schedule asks the agent rather than naming a program to start."""
    with contextlib.suppress(Exception):
        return bool((kept.one(agent, name).get("agent_prompt") or "").strip())
    return False


def _asked(agent: str, name: str) -> int:
    """Take this schedule's turn now, in this terminal.

    **The minute it next falls due does not move**, exactly as running a program by hand does not
    use one up: testing a schedule must not be how you stop it happening.
    """
    try:
        got = answering.for_a_schedule(agent, name)
    except (answering.Refused, turns.Busy, turns.NotRunnable) as why:
        return _failed(str(why), "nothing was run")
    except TROUBLE as why:
        return _failed(str(why), "nothing was run")
    if got.reply.strip():
        print(got.reply)
    if got.worked:
        print(f"\nschedule {name} completed  ·  turn {got.turn}")
        return OK
    return _failed(f"{name} did not answer — {got.failure_message or got.turn_status}",
                   f"what it did:  rundesk turns {agent} {got.turn}")


def _ran(agent: str, name: str, waiting: float) -> int:
    """Run one schedule now and hand back what the program said, including its exit code.

    **The command's own exit code is the program's**, so `rundesk schedules run` in a script answers
    the way the program it started answers. A run that could not start is `1` — nothing ran, so
    there is no code to pass on, and reporting one would say the program ran and disagreed.
    """
    gone_wrong = directory.not_an_agent(agent)
    if gone_wrong:
        return _failed(gone_wrong, "see what there is with: rundesk agents", "nothing was run")
    if waiting <= 0:
        return _mistyped(f"{waiting:g} seconds is not long enough for anything to run",
                         "say a number of seconds greater than zero", "nothing was run")

    if _asks_the_agent(agent, name):
        # **One verb for both kinds.** A schedule starts a program or asks the agent, and a person
        # checking their own work should not have to know which they wrote. The turn is taken here,
        # in this terminal, exactly as `providers run` takes it under a gateway.
        return _asked(agent, name)

    try:
        ran = firing.by_hand(agent, name, waiting=waiting, where=directory.logs(agent))
    except firing.Occupied as why:
        return _failed(str(why),
                       f"see what it is doing with: rundesk gateways logs {agent}",
                       "nothing was run")
    except firing.NoRunner as why:
        return _failed(str(why), "nothing was run")
    except TROUBLE as why:
        return _failed(str(why), "nothing was run")

    _what_it_said(ran)
    if ran.trouble:
        return _failed(f"{name} did not run: {ran.trouble}", "nothing it would have done was done")
    if ran.code != 0:
        return _failed(f"{name} ran and ended with exit {ran.code}",
                       f"everything it wrote is in {firing.output_of(agent, name)}")
    print(f"schedule {name} completed")
    return OK


def _what_it_said(ran: programs.Ran) -> None:
    """Everything the program wrote, on the stream it wrote it to and nowhere else.

    Not indented and not prefixed: this is another program's output, and a person running a schedule
    by hand is reading *it* rather than reading rundesk. Standard error stays standard error, so a
    pipeline that keeps the two apart goes on keeping them apart.

    Standard output is flushed before anything reaches standard error, because a block-buffered
    stdout into a pipe reorders them otherwise — `skills` already writes this down.
    """
    if ran.out:
        print(ran.out, end="" if ran.out.endswith("\n") else "\n")
    sys.stdout.flush()
    if ran.err:
        print(ran.err, end="" if ran.err.endswith("\n") else "\n", file=sys.stderr)


def _forgotten(agent: str, name: str) -> int:
    """Take a schedule away.

    **No `--confirm`.** That is kept for what no backup brings back — an agent's whole memory, an
    install's data directory — and a schedule is four flags to type again. What it has already done
    goes with it; the account of every firing stays in the agent's own log, which this never touches.

    **What its firings left behind goes too, and each thing that went is named**, the way `agents
    remove` names what it took. A schedule that is gone leaving a lock and an output file is litter
    the next schedule of that name would inherit. The one exception is work that is still running:
    unlinking a held lock is how two firings of one schedule come to run at once, so those files stay
    and the line says so rather than leaving somebody to notice.
    """
    gone_wrong = directory.not_an_agent(agent)
    if gone_wrong:
        return _failed(gone_wrong, "see what there is with: rundesk agents", "nothing was removed")
    try:
        kept.forgotten(agent, name)
        # After the row and never before it. The row is what makes the schedule a schedule, so a
        # removal interrupted between the two leaves files with nothing scheduling them — litter —
        # rather than a schedule the clock still reaches and whose lock has been taken away.
        gone = firing.let_go(agent, name)
    except TROUBLE as why:
        return _failed(str(why), "nothing was removed")

    print(f"schedule {name} removed from {agent}")
    for one in gone:
        print(f"        took   {one}")
    if not gone and firing.still_running(agent, name):
        print(f"        kept   what {name} started is still running, so what it holds was left")
    return OK


def _what_it_needs(args: argparse.Namespace, typed: str) -> str:
    """Why this is not yet a schedule anybody could add, or `""` when it is.

    Every one of these is a flag somebody left off or gave an empty value to, and each gets its own
    sentence ending in the whole command to type — never argparse's, which names the flag and stops.
    """
    if args.when is None and args.at is None:
        return ("nothing said when it runs — say a repeating time or the one moment it runs, "
                f"with: {typed} --when '<cron>' --run '<program>'")
    if args.when is not None and args.at is not None:
        return ("a schedule runs over and over or runs once, never both — say --when or --at, "
                "not the two of them")
    # **A schedule starts a program or asks the agent, and never both.** The records hold the same
    # rule as a `CHECK`; this is what says it in words, where somebody typed it.
    if args.program is not None and args.prompt is not None:
        return ("a schedule starts a program or asks the agent, never both — say --run or --ask, "
                "not the two of them")
    if args.program is None and args.prompt is None:
        return ("nothing said what it does — say the program to start or what to ask the agent, "
                f"with: {typed} --run '<program>'  or  {typed} --ask '<prompt>'")
    return firing_trouble(args.program) if args.program is not None else ""


def firing_trouble(said: Optional[str]) -> str:
    """Why this is not a program that can be started, or `""` when it is.

    **Located here, when the schedule is written down.** A path that is not on the machine is a
    mistake somebody can fix at the moment they make it; found instead by a gateway, it is a line in
    a log at two in the morning saying a schedule nobody was watching did not run.

    Nothing said and nothing *in* what was said are different mistakes with different sentences: one
    is a flag left off, the other is usually a shell variable that was not set — which is exactly
    the case where being told what to type again does not help.
    """
    if said is None:
        return "nothing said what to run — say it with: --run '<program> <arguments>'"
    if not said.strip():
        return "a program with nothing in it is not one — a schedule with nothing to start cannot run"
    argv = firing.argv_of(said)
    if not argv:
        return f"{said!r} could not be read as a program and its arguments — check the quoting"
    where = _found_on_the_machine(argv[0])
    if not where:
        return (f"{argv[0]} is not a program on this machine — a schedule naming one that is not "
                "there can never run, so say where it really is")
    return ""


def _found_on_the_machine(program: str) -> str:
    """Where this program really is, or `""` when nothing of that name can be run.

    `shutil.which` answers for both spellings — a path somebody wrote out, and a bare name to be
    found on `PATH` — and it asks whether the file is executable rather than only whether it exists,
    which is the difference between a schedule that runs and one that reports permission denied.
    """
    return shutil.which(program) or ""


def _as_local(said: Any) -> str:
    """A moment the records keep in UTC, shown in the machine's own time with its offset.

    The rule `docs/time.md` states: a record takes UTC because it is compared and may be restored on
    another machine, and a line somebody reads takes their own clock because they are placing it
    against their own day. A moment that will not parse is shown exactly as it is written rather
    than blanked — a record nobody can read is a thing to see, not a thing to hide.
    """
    if not said:
        return ""
    try:
        when = datetime.strptime(str(said), config.MOMENT).replace(tzinfo=timezone.utc)
    except ValueError:
        return str(said)
    return when.astimezone().strftime(due.A_MINUTE)


def _now() -> datetime:
    """The moment this command is answering about. One call, so a listing cannot straddle a minute."""
    return datetime.now()


def _failed(why: str, *and_so: str) -> int:
    """Say what went wrong, and what that leaves — never one without the other."""
    return _wrong(FAILED, why, *and_so)


def _mistyped(why: str, *and_so: str) -> int:
    """The same, for a command line that was itself wrong — which exits `2` and not `1`.

    `gateways` already draws this line and for the same reason: argparse exits `2` for a command
    line that was never a command, and a guard written by hand for the same class of mistake must
    not renumber it.
    """
    return _wrong(USAGE, why, *and_so)


def _wrong(code: int, why: str, *and_so: str) -> int:
    failed(f"schedules: FAILED — {why}", *and_so)
    return code
