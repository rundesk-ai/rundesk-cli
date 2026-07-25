"""The rundesk command line — the one interface anyone using rundesk goes through.

Every verb the finished product will have is registered here from the start, so
`rundesk` and `rundesk --help` describe the whole shape of the thing rather than
whatever happens to be built this week. What is not built yet says so and exits
non-zero: a command that did nothing and reported success is a lie a script will
believe.

Only the install-lifecycle commands are real today — `version` and `update`, plus
the `install.sh` that put the command there in the first place.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rundesk_cli import __version__  # noqa: E402
from rundesk_cli import gateway as _gateway  # noqa: E402
from rundesk_cli import process  # noqa: E402
from rundesk_cli import supervisor as _supervisor  # noqa: E402
from rundesk_cli import updater  # noqa: E402

#: Where this checkout lives — the thing an update replaces in place.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: How many of a gateway's last lines `logs` shows when not told otherwise.
LOG_LINES = 40

#: How long to wait for a gateway to actually appear after the machine takes its job.
#: Generous enough for a cold start, short enough that a gateway which is never coming
#: is reported rather than waited on.
START_PATIENCE = 15.0

#: How long cycling waits for a gateway to actually go before giving up on it. Longer
#: than a gateway is allowed to take stopping, so a slow but correct shutdown is not
#: mistaken for one that is stuck.
CYCLE_PATIENCE = 20.0

#: What a command that exists but is not built yet exits with. Not 0, which a
#: script would take as done; not 1, which is reserved for a command that ran and
#: failed. See `COMING_SOON`.
NOT_BUILT = 2

#: Every verb that is planned but not built, and the one line `--help` shows for it.
#: The finished shape of the CLI, declared up front — each entry graduates out of
#: this table into a real command as it lands.
COMING_SOON: dict[str, str] = {
    "agents": "list the agents this install defines",
    "new": "give an agent a directory to be itself in",
    "doctor": "what stands between an agent and a working turn",
    "run": "one turn, streamed to this terminal",
    "replay": "re-print a stored run",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rundesk",
        description="A lightweight, provider-agnostic multi-agent gateway.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"rundesk {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    for name, help_text in COMING_SOON.items():
        # Marked where the list is, not only when the verb is invoked. Eleven of fourteen
        # commands are planned, and a list that reads as fourteen working ones sends a
        # newcomer to try each in turn to find out which three do anything.
        planned = sub.add_parser(name, help=f"{help_text} [coming soon]",
                                 description=f"{help_text} — planned, not built yet.")
        # Whatever a planned command will eventually take, it takes nothing today —
        # but it must not choke on being given arguments, or the message it prints
        # would be argparse's rather than ours.
        planned.add_argument("args", nargs="*", help=argparse.SUPPRESS)

    said = sub.add_parser("version", help="what is installed, and whether that is current")
    said.add_argument("--check", action="store_true", help="say whether a newer release exists")

    moved = sub.add_parser("update", help="move to the newest published release")
    moved.add_argument("--check", action="store_true", help="say what would happen, and change nothing")

    sub.add_parser("uninstall", help="how to remove rundesk from this machine")

    # The gateway. Every one of these takes the gateway's name and can do without it,
    # because there is one gateway today and there will be one per agent. Leaving the
    # name out means all of them wherever that can mean anything, so what these do
    # today stays true once there are several.
    served = sub.add_parser("serve", help="run a gateway here, until it is asked to stop")
    served.add_argument("name", nargs="?", default=_gateway.DEFAULT_NAME)

    started = sub.add_parser("start", help="have the machine keep a gateway running")
    started.add_argument("name", nargs="?", default=_gateway.DEFAULT_NAME)

    stopped = sub.add_parser("stop", help="stand a gateway down")
    stopped.add_argument("name", nargs="?")

    cycled = sub.add_parser("restart", help="cycle a gateway, leaving the others alone")
    cycled.add_argument("name", nargs="?")

    sub.add_parser("status", help="every gateway, and what it is doing")

    listed = sub.add_parser("schedules", help="what a gateway runs on its own, and when")
    listed.add_argument("--gateway", dest="name", default=_gateway.DEFAULT_NAME,
                        help="whose schedules — a gateway's schedules are its own")
    acts = listed.add_subparsers(dest="act", metavar="<action>")
    added = acts.add_parser("add", help="add a schedule")
    added.add_argument("schedule")
    added.add_argument("--when", required=True, help="when it runs, stated as a schedule is")
    added.add_argument("--run", required=True, nargs=argparse.REMAINDER,
                       help="what to start when it is due")
    for act, what in (("remove", "take a schedule away"),
                      ("on", "let a schedule run"),
                      ("off", "keep a schedule but stop it running")):
        one = acts.add_parser(act, help=what)
        one.add_argument("schedule")

    said = sub.add_parser("logs", help="what a gateway has been saying")
    said.add_argument("name", nargs="?", default=_gateway.DEFAULT_NAME)
    said.add_argument("-n", "--lines", type=int, default=LOG_LINES,
                      help="how many of the last lines to show")
    return parser


def cmd_version(args: argparse.Namespace) -> int:
    if args.check:
        return updater.run(REPO_ROOT, __version__, check_only=True)
    print(f"rundesk {__version__}")
    return 0


def cmd_update(args: argparse.Namespace, gateways, machine) -> int:
    return updater.run(
        REPO_ROOT, __version__, check_only=args.check,
        busy=lambda: _in_flight(gateways),
        pause=lambda: _stand_all_down(gateways, machine),
        resume=lambda names: _bring_all_back(names, gateways, machine),
    )


def _stand_all_down(gateways, machine) -> tuple:
    """Stop every gateway an update is about to replace the files of (R-UPD-21).

    Refuses outright rather than touching one running without a job. `launchctl kill` has
    no handle on a process launchd never started, so such a gateway cannot be stopped
    here at all — and even if it could, nothing could start it again: there is no record
    of the terminal it was started from. Taking it down would leave an owner's gateway
    dead because of a command they thought was routine.
    """
    if not machine.available():
        return [], None
    stopped = []
    for it in gateways.every():
        if not it.running:
            continue
        try:
            kept = machine.loaded(it.name)
        except machine.Unsure:
            # The machine did not answer. Not knowing whether we could start it again is
            # not permission to take it down.
            return stopped, (f"the machine did not say whether it keeps '{it.name}', so it "
                             f"was not taken down for an update")
        # Asked again, immediately before stopping it: the check for work in flight
        # happened before any of this, and a turn that began in between is one this would
        # otherwise kill (R-UPD-23).
        if gateways.what_is_running(it.name):
            return stopped, (f"'{it.name}' began work while the update was starting, so "
                             f"nothing was replaced under it")
        if not kept:
            # Asked of the machine, never of the directory: a job description sitting in
            # `LaunchAgents` is not a job the machine is keeping.
            return stopped, (
                f"'{it.name}' is running unsupervised (pid {it.pid}); it can be stopped "
                f"but not started again, so it is not ours to take down for an update.\n"
                f"        hand it to the machine:  rundesk start {it.name}\n"
                f"        or stop it yourself, then update"
            )
        said = machine.stop(it.name)
        if not said.ok or not _gone(it.name, gateways):
            return stopped, f"'{it.name}' would not stop, so nothing was replaced under it"
        stopped.append(it.name)
    return stopped, None


def _bring_all_back(names: list, gateways, machine) -> list:
    """Start again everything the update stopped, and say what did not come back.

    What this exists to catch is not the machine refusing — it is a gateway that starts,
    finds the install no longer fits it, and ends *well* so as not to be restarted
    forever (R-GW-25). The machine reports that as a job accepted and nothing else does
    at all, so an update replacing a release that needs something new would otherwise
    leave every gateway down and report success.
    """
    down = []
    for name in names:
        try:
            said = machine.start(name)
        except (machine.NotOurs, machine.NoSupervisor):
            down.append(name)
            continue
        if not said.ok or _came_up(name, gateways) is None:
            down.append(name)
    if down:
        unfit = gateways.fitness(REPO_ROOT)
        if unfit:
            print(f"update: what rundesk is made of no longer fits: {unfit}", file=sys.stderr)
    return down


def _in_flight(gateways) -> list:
    """Everything every gateway on this machine says it is working on (R-UPD-23).

    Asked of the gateways rather than of a list kept somewhere, and named by gateway as
    well as by work: an owner told only that "something" is running has to go and find
    which of several it was before they can decide to wait.
    """
    return [
        f"{it.name}/{one}"
        for it in gateways.every() if it.running
        for one in gateways.what_is_running(it.name)
    ]


def cmd_uninstall(_args: argparse.Namespace) -> int:
    # The one thing the command cannot do for you: removing it removes the command
    # that is doing the removing. The installer owns it, and it is what you already
    # have on disk.
    print("uninstall: USE THE INSTALLER — removing rundesk removes this command too")
    print()
    print("  from this checkout:")
    print(f"    {REPO_ROOT / 'install.sh'} --uninstall [--purge]")
    print()
    print("  without one:")
    print("    curl -fsSL https://github.com/rundesk-ai/rundesk-cli/releases/latest/download/"
          "install.sh | bash -s -- --uninstall")
    return 0


def cmd_coming_soon(name: str) -> int:
    print(f"{name}: NOT BUILT — this command is planned, not implemented yet", file=sys.stderr)
    return NOT_BUILT


def _as_table(head: tuple, rows: list) -> None:
    """Columns wide enough for what is in them. Written once, so the two things that
    list something in columns cannot come to disagree about how."""
    if not rows:
        return
    widths = [max(len(row[i]) for row in [head] + rows) for i in range(len(head))]
    for row in [head] + rows:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip())


def cmd_serve(args: argparse.Namespace, gateways) -> int:
    """Run a gateway here, in the foreground. What the machine's job invokes.

    Refusing to run ends *well*, on purpose. The machine is told to start a gateway
    again whenever it ends badly, so a gateway that will never start — its virtualenv
    does not fit, or another already holds its name — would otherwise be started every
    few seconds for as long as the machine is up (R-GW-25).
    """
    try:
        return asyncio.run(gateways.Gateway(args.name).serve())
    except (gateways.AlreadyRunning, gateways.Unfit, gateways.NotAName) as why:
        print(f"{args.name}: NOT STARTED — {why}", file=sys.stderr)
        return 0


def cmd_start(args: argparse.Namespace, gateways, machine) -> int:
    """Hand a gateway to the machine, and see that a gateway actually results.

    The machine taking the job is not the gateway running. A job can be accepted and the
    gateway then refuse to start — and refusing ends cleanly, so the machine does not try
    again and nothing says a word. Reporting the hand-off as the outcome is reporting a
    success this command did not earn.
    """
    name = args.name
    already = gateways.standing(name)
    if already.running:
        # Running is not the same as looked after. A gateway started by hand, or one left
        # behind when its job was taken away, answers everything exactly as a supervised
        # one does — and will not come back when it exits or when the machine reboots.
        # Reporting that as success is telling an owner they are covered when they are not.
        try:
            kept = machine.available() and machine.loaded(name)
        except machine.Unsure:
            print(f"{name}: ALREADY RUNNING (pid {already.pid}) — the machine did not say "
                  f"whether it is keeping it", file=sys.stderr)
            return 1
        if not machine.available() or kept:
            print(f"{name}: ALREADY RUNNING (pid {already.pid})")
            return 0
        print(f"{name}: FAILED — running unsupervised (pid {already.pid}); it will not come back",
              file=sys.stderr)
        # Not something this command can take over: the gateway already running holds the
        # name, so a supervised one started now would refuse it and end cleanly.
        print(f"         stop it first (pid {already.pid}), then: rundesk start {name}",
              file=sys.stderr)
        return 1
    try:
        said = machine.install(name)
    except machine.NotOurs as why:
        print(f"{name}: FAILED — {why}", file=sys.stderr)
        return 1
    except machine.NoSupervisor as why:
        print(f"{name}: FAILED — {why}", file=sys.stderr)
        print(f"         run in this terminal instead: rundesk serve {name}", file=sys.stderr)
        return 1
    if not said.ok:
        print(f"{name}: FAILED — the supervisor refused the job: {said.said}", file=sys.stderr)
        return 1
    up = _came_up(name, gateways)
    if up is None:
        print(f"{name}: FAILED — job accepted, but no gateway started.", file=sys.stderr)
        print(f"         why: rundesk logs {name}", file=sys.stderr)
        return 1
    print(f"{name}: RUNNING (pid {up.pid})")
    return 0


def _came_up(name: str, gateways, patience: float | None = None):
    """The gateway, once it is actually there — or None if it never arrives.

    The patience resolves here rather than in the signature: a default argument is bound
    once, when this file is read, so naming the constant there freezes it and anything
    that changed it afterwards is quietly ignored.
    """
    deadline = time.monotonic() + (START_PATIENCE if patience is None else patience)
    while time.monotonic() < deadline:
        now = gateways.standing(name)
        if now.running:
            return now
        time.sleep(0.2)
    return None


def _named(args: argparse.Namespace, gateways, machine) -> list[str]:
    """The gateways a command is about: the one named, or every one there is.

    Naming none and meaning one is the ambiguity worth refusing; naming none and meaning
    all of them is what an owner wants when they are shutting the machine down.
    """
    if getattr(args, "name", None):
        return [args.name]
    return sorted({it.name for it in gateways.every()} | set(machine.described()))


def cmd_stop(args: argparse.Namespace, gateways, machine) -> int:
    return _stand_down(args, gateways, machine, "stop")


def cmd_restart(args: argparse.Namespace, gateways, machine) -> int:
    return _stand_down(args, gateways, machine, "restart")


def _gone(name: str, gateways, patience: float | None = None) -> bool:
    """Has this gateway actually stopped? Asked of the gateway, not of the machine.

    The patience resolves here, not in the signature — see `_came_up`.
    """
    deadline = time.monotonic() + (CYCLE_PATIENCE if patience is None else patience)
    while time.monotonic() < deadline:
        if not gateways.standing(name).running:
            return True
        time.sleep(0.2)
    return not gateways.standing(name).running


def _stand_down(args: argparse.Namespace, gateways, machine, verb: str) -> int:
    names = _named(args, gateways, machine)
    if not names:
        print("no gateways")
        return 0
    worst = 0
    for name in names:
        try:
            if not machine.known(name):
                # Never a job this install did not write. But one that exists and is not
                # ours is not the same as none at all, and saying "nothing to stop" about
                # a job sitting right there sends someone looking in the wrong place.
                if machine.exists(name):
                    print(f"{name}: FAILED — this job belongs to another install of rundesk",
                          file=sys.stderr)
                    worst = 1
                    continue
                # No job whatsoever, which means three different things depending on what
                # is there and what was asked. Answering all three with one refusal — as
                # a stand-in Spoke fed into the failure block below did — told an owner
                # with no job at all to go looking for a second install of rundesk.
                now = gateways.standing(name)
                if now.running:
                    print(f"{name}: FAILED — running with no job (pid {now.pid}); "
                          "nothing is keeping it up", file=sys.stderr)
                    worst = 1
                elif verb == "restart":
                    # Nothing to stop is a finished job for `stop`, and a request that
                    # did not happen for `restart`: whoever asked wanted it running.
                    print(f"{name}: NO JOB — nothing to restart", file=sys.stderr)
                    worst = 1
                else:
                    print(f"{name}: NO JOB — nothing to stop")
                continue
            if verb == "restart":
                stopped = machine.stop(name)
                if not stopped.ok:
                    print(f"rundesk {name}: could not ask it to stop — {stopped.said}",
                          file=sys.stderr)
                    worst = 1
                    continue
                if not _gone(name, gateways):
                    # Starting it now does nothing — the machine sees a job already
                    # running — and the old one then ends *well*, which is the one
                    # outcome the machine is told not to undo. The gateway would be
                    # left down, having just reported that it was cycled.
                    print(f"rundesk {name}: still running after being asked to stop",
                          file=sys.stderr)
                    worst = 1
                    continue
                said = machine.start(name)
                if not said.ok:
                    # Reported below, this fell into the block written for `stop` and came
                    # out as ALREADY STOPPED with a success exit — a true sentence and a
                    # completely wrong one. It reads as "there was nothing to do"; what
                    # happened is "it was taken down and could not be brought back".
                    print(f"{name}: FAILED — stopped, but the supervisor refused to start "
                          f"it: {said.said}", file=sys.stderr)
                    worst = 1
                    continue
            else:
                said = machine.stop(name)
        except machine.NoSupervisor as why:
            print(f"FAILED — {why}", file=sys.stderr)
            return 1
        except machine.NotOurs as why:
            print(f"{name}: FAILED — {why}", file=sys.stderr)
            worst = 1
            continue
        if not said.ok:
            now = gateways.standing(name)
            if now.running:
                print(f"{name}: FAILED — the supervisor refused to stop it (pid {now.pid}): "
                      f"{said.said}", file=sys.stderr)
                worst = 1
            else:
                # Refused, and already in the state that was asked for. Nothing to report
                # against: the machine declining to stop what is not running is not a
                # failure of this command.
                print(f"{name}: ALREADY STOPPED")
            continue
        if verb == "restart":
            up = _came_up(name, gateways)
            if up is None:
                print(f"{name}: FAILED — stopped, but did not restart.", file=sys.stderr)
                print(f"         why: rundesk logs {name}", file=sys.stderr)
                worst = 1
                continue
            print(f"{name}: RESTARTED (pid {up.pid})")
        elif not _gone(name, gateways):
            print(f"{name}: FAILED — still running after stop request", file=sys.stderr)
            worst = 1
        else:
            print(f"{name}: STOPPED")
    return worst


def cmd_status(_args: argparse.Namespace, gateways, machine) -> int:
    """Every gateway, and what it is actually doing.

    Answered by the gateways themselves rather than by the machine, because the machine
    cannot tell a gateway that is working from one that is up and stuck (R-GW-9).
    """
    has_supervisor = machine.available()
    described = set(machine.described()) if has_supervisor else set()
    found = {it.name: it for it in gateways.every()}
    for name in sorted(described - set(found)):
        found[name] = gateways.Standing(name=name, running=False)
    if not found:
        print("no gateways")
        return 0
    rows = []
    for name in sorted(found):
        it = found[name]
        # Whether the supervisor is keeping this gateway is asked of the supervisor. A
        # job description sitting in a directory is not a job being kept, and the two
        # come apart exactly when something has gone wrong — which is when it is read.
        try:
            kept = has_supervisor and name in described and machine.loaded(name)
        except machine.Unsure:
            kept = None   # asked, and not told — which is not the same as "no"
        doing = gateways.what_is_running(name) if it.running else []
        rows.append((
            name,
            ("WEDGED" if it.stale else "RUNNING") if it.running else "STOPPED",
            str(it.pid) if it.running else "-",
            _how_long(it.started) if it.running else "-",
            "yes" if kept else ("?" if kept is None else "no"),
            _version_of(it),
            (f"{len(doing)} ({', '.join(sorted(doing))})" if doing else "idle") if it.running else "-",
        ))
    _as_table(("GATEWAY", "STATE", "PID", "UPTIME", "SUPERVISED", "VERSION", "WORK"), rows)
    return 0


def _version_of(it) -> str:
    """Which version this gateway is actually running (R-GW-9).

    Asked of the gateway's own record rather than of this install, because the two come
    apart exactly when it matters: an update replaces the files while a gateway keeps the
    code it already imported, so `rundesk version` says one thing and the thing actually
    serving is another. Marked rather than merely shown, since a number a reader has to
    compare against another number by eye is a difference nobody notices.
    """
    if not it.running or not it.version:
        return "-"
    return it.version if it.version == __version__ else f"{it.version} (old)"


def _how_long(started: float | None) -> str:
    """How long it has been up, in the shortest form that is still exact enough."""
    if not started:
        return "-"
    seconds = max(0, int(time.time() - started))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"
    return f"{seconds // 86400}d{(seconds % 86400) // 3600:02d}h"


def cmd_schedules(args: argparse.Namespace, gateways) -> int:
    """List a gateway's schedules, or change them."""
    act = getattr(args, "act", None)
    try:
        if act == "add":
            return _add_schedule(args, gateways)
        if act in ("remove", "on", "off"):
            return _change_schedule(args, gateways, act)
        return _list_schedules(args, gateways)
    except _gateway.Unreadable as why:
        # Answered in one place because every path here reads the same file, and each of
        # them turned "this cannot be read" into "there is nothing there": the listing said
        # NO SCHEDULES and exited zero, and the changes wrote an empty list over a file that
        # still held every schedule as recoverable text (R-SCH-17, R-SCH-18).
        print(f"{args.name}: SCHEDULES UNREADABLE — {why}", file=sys.stderr)
        print("        nothing was changed — move the file aside or repair it",
              file=sys.stderr)
        return 1


def _note(gateways, name: str, said: str) -> None:
    """Say what was changed, in the log of the gateway it was changed for.

    A schedule that appears or vanishes is as much a part of what happened to a gateway
    as anything it ran, and the log is the only account that outlives the gateway.
    """
    gateways.note(name, said)


def _add_schedule(args: argparse.Namespace, gateways) -> int:
    from rundesk_cli import schedule

    try:
        made = schedule.Schedule(args.schedule, args.when)
    except schedule.NotASchedule as why:
        print(f"{args.schedule}: NOT ADDED — {why}", file=sys.stderr)
        return 1
    if not args.run:
        print(f"{args.schedule}: NOT ADDED — nothing was named to run", file=sys.stderr)
        return 1
    if not process.located(args.run[0]):
        # Refused here rather than discovered at three in the morning. The gateway runs
        # with almost no PATH, so a program named rather than located resolves in the
        # shell that typed it and nowhere else (R-PROC-2) — and a schedule that cannot
        # start looks exactly like one that has simply never come due.
        print(f"{args.schedule}: NOT ADDED — '{args.run[0]}' is a name, not a location; "
              f"give the full path (try: command -v {args.run[0]})", file=sys.stderr)
        return 1
    # Read and written under one lock: two `add`s racing would otherwise each read the
    # same list and each write theirs back, and one schedule would simply never exist
    # while both commands reported success.
    with gateways.changing_schedules(args.name) as keeping:
        if any(one.get("name") == args.schedule for one in keeping if isinstance(one, dict)):
            print(f"{args.schedule}: EXISTS — remove it first, or use a different name",
                  file=sys.stderr)
            return 1
        keeping.append({"name": args.schedule, "when": args.when, "run": list(args.run)})
    _note(gateways, args.name, f"schedule '{args.schedule}' added ({args.when})")
    print(f"{args.schedule}: ADDED — next {schedule.describe(made, datetime.now())}")
    return 0


def _change_schedule(args: argparse.Namespace, gateways, act: str) -> int:
    with gateways.changing_schedules(args.name) as keeping:
        found = [one for one in keeping
                 if isinstance(one, dict) and one.get("name") == args.schedule]
        if not found:
            print(f"{args.schedule}: NOT FOUND — {args.name} has no schedule by that name",
                  file=sys.stderr)
            return 1
        if act == "remove":
            keeping[:] = [one for one in keeping if one is not found[0]]
            said, told = "REMOVED", f"schedule '{args.schedule}' removed"
        else:
            found[0]["enabled"] = act == "on"
            said = "ON" if act == "on" else "OFF"
            told = f"schedule '{args.schedule}' turned {said.lower()}"
    _note(gateways, args.name, told)
    print(f"{args.schedule}: {said}")
    return 0


def _list_schedules(args: argparse.Namespace, gateways) -> int:
    """What this gateway runs on its own, when each next runs, and what became of it.

    This gateway's, and no other's: a gateway's schedules are its own, which is what
    makes one agent's schedules that agent's alone (R-SCH-13, R-SCH-14).
    """
    from rundesk_cli import schedule

    wanted, refused = gateways.scheduled(args.name)
    if not wanted and not refused:
        print(f"{args.name}: NO SCHEDULES")
        return 0
    now = datetime.now()
    ran = gateways.what_was_scheduled(args.name)
    rows = [(
        one.name,
        "OFF" if not one.enabled else "ON",
        one.when,
        schedule.describe(one, now),
        ran.get(one.name, {}).get("at", "-"),
        ran.get(one.name, {}).get("outcome", "-"),
    ) for one in wanted]
    _as_table(("SCHEDULE", "STATE", "WHEN", "NEXT", "LAST RUN", "OUTCOME"), rows)
    for name, why in refused:
        print(f"{name or '(unnamed)'}: NOT UNDERSTOOD — {why}", file=sys.stderr)
    return 1 if refused else 0


def cmd_logs(args: argparse.Namespace, gateways) -> int:
    """What a gateway has been saying. Reads the file, so a gateway that has gone can
    still be asked what happened (R-GW-18)."""
    path = gateways.log_path(args.name)
    if not path.exists():
        print(f"{args.name}: NO LOG — nothing written yet ({path})", file=sys.stderr)
        return 1
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError as why:
        # Every other verb answers in our words when it cannot do the thing. A log that
        # cannot be read is a thing to be told about, not a traceback.
        print(f"{args.name}: FAILED — could not read the log: {why}", file=sys.stderr)
        return 1
    for line in lines[-args.lines:] if args.lines > 0 else []:
        print(line)
    return 0


def main(argv: list[str], gateways=None, machine=None) -> int:
    """The command surface.

    What the gateway commands act on is passed in rather than imported here, so this
    file knows the verbs and nothing about locks, records or process groups — and so
    every one of them is exercised without a gateway or a supervisor anywhere near it.
    """
    gateways = gateways if gateways is not None else _gateway
    machine = machine if machine is not None else _supervisor
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0
    named = getattr(args, "name", None)
    if named is not None:
        try:
            gateways.checked(named)
        except gateways.NotAName as why:
            print(f"{named}: INVALID NAME — {why}", file=sys.stderr)
            return 1
    if args.command in COMING_SOON:
        return cmd_coming_soon(args.command)
    if args.command == "version":
        return cmd_version(args)
    if args.command == "update":
        return cmd_update(args, gateways, machine)
    if args.command == "uninstall":
        return cmd_uninstall(args)
    if args.command == "serve":
        return cmd_serve(args, gateways)
    if args.command == "start":
        return cmd_start(args, gateways, machine)
    if args.command == "stop":
        return cmd_stop(args, gateways, machine)
    if args.command == "restart":
        return cmd_restart(args, gateways, machine)
    if args.command == "status":
        return cmd_status(args, gateways, machine)
    if args.command == "schedules":
        return cmd_schedules(args, gateways)
    if args.command == "logs":
        return cmd_logs(args, gateways)

    # Unreachable through argparse, which rejects an unknown command before this —
    # but a dispatch that silently returns 0 for a verb nobody handled is how a
    # command comes to exist and do nothing.
    print(f"rundesk: no handler for '{args.command}'", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
