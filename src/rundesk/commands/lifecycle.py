"""Starting a gateway, stopping it, cycling it, and taking one away.

One gateway per agent, so one is cycled without disturbing the rest. The restart worker
lives here rather than beside the update worker on purpose: it cycles **one named gateway**
through the path an owner types, where the update worker stops every gateway on the machine
— different blast radius, different owner, different module.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from rundesk import migration
from rundesk import restart_request
from rundesk import store
from rundesk import standing
from rundesk import update_worker


RESTART_POLL_SECONDS = 1.0
RESTART_DEFERRED = 75

def _queue_restart(machine, name: str, origin: dict) -> int:
    """Hand a busy gateway restart to a process that gateway does not own (R-GW-43)."""
    if not machine.available():
        print(f"{name}: RESTART NOT QUEUED — this machine has no usable supervisor",
              file=sys.stderr)
        return 1
    try:
        if not machine.loaded(name):
            print(f"{name}: RESTART NOT QUEUED — it is not supervised", file=sys.stderr)
            return 1
        row, created = restart_request.queue(name, origin)
        loaded = machine.restart_worker_loaded()
        said = (
            machine.kick_restart_worker()
            if loaded else machine.install_restart_worker()
        )
    except machine.Unsure as why:
        print(f"{name}: RESTART NOT QUEUED — {why}", file=sys.stderr)
        return 1
    except machine.NotOurs as why:
        print(f"{name}: RESTART NOT QUEUED — {why}", file=sys.stderr)
        return 1
    except restart_request.Unreadable as why:
        print(f"{name}: RESTART NOT QUEUED — {why}", file=sys.stderr)
        return 1
    if not said.ok:
        why = said.said or "the supervisor refused the worker"
        restart_request.finish(name, row["id"], "failed", why)
        print(f"{name}: RESTART NOT QUEUED — {why}", file=sys.stderr)
        return 1
    state = "RESTART QUEUED" if created else "RESTART ALREADY QUEUED"
    print(f"{name}: {state} — it will restart automatically after active work finishes")
    return 0


def _restart_in_flight(name: str, gateways, agents) -> list[str]:
    run_home = agents.resolved(name).run
    if not standing.of(name, gateways, agents).running:
        return []
    found = [
        one for one in gateways.what_is_working(name, run_home)
        if not one.startswith("channel:")
    ]
    found.extend(f"turn:{row['run']}"
                 for row in gateways.what_is_turning(name, run_home))
    return sorted(found)


def _run_restart_worker(gateways, machine, agents) -> int:
    """Wait outside gateways, cycle each queued target, and persist the outcome."""
    worst = 0
    while True:
        try:
            pending = restart_request.active()
        except restart_request.Unreadable as why:
            print(f"restart worker: FAILED — {why}", file=sys.stderr)
            return 1
        if not pending:
            return worst
        progressed = False
        for pending_row in pending:
            name = pending_row["name"]
            try:
                request = (
                    restart_request.claim(name)
                    if pending_row.get("state") == "pending"
                    else pending_row
                )
            except restart_request.Unreadable as why:
                print(f"restart worker: FAILED — {why}", file=sys.stderr)
                worst = 1
                continue
            if request is None:
                continue
            if not request.get("ready") or _restart_in_flight(name, gateways, agents):
                continue
            args = argparse.Namespace(
                name=name, all=False, force=False, worker=True,
            )
            code = _stand_down(args, gateways, machine, agents, "restart")
            if code == RESTART_DEFERRED:
                continue
            state = "succeeded" if code == 0 else "failed"
            result = (
                f"{name} restarted and is online"
                if code == 0 else f"{name} could not be restarted; see its gateway log"
            )
            try:
                restart_request.finish(name, request["id"], state, result)
            except (restart_request.Unreadable, RuntimeError) as why:
                print(f"restart worker: FAILED — {why}", file=sys.stderr)
                worst = 1
            else:
                worst = max(worst, code)
                progressed = True
        if not progressed:
            time.sleep(RESTART_POLL_SECONDS)


def cmd_serve(args: argparse.Namespace, gateways, agents, skills) -> int:
    """Run a gateway here, in the foreground. What the machine's job invokes.

    Refusing to run ends *well*, on purpose. The machine is told to start a gateway
    again whenever it ends badly, so a gateway that will never start — its virtualenv
    does not fit, or another already holds its name — would otherwise be started every
    few seconds for as long as the machine is up (R-GW-25).
    """
    whose = agents.resolved(args.name)
    # The surfaces this agent is reachable on, resolved here and handed over made. A
    # gateway holds them open for as long as it is up (R-CAD-6) and never works out for
    # itself what an agent is.
    #
    # **Records this rundesk will not read end the same way as a virtualenv that does not
    # fit: well, and once** (R-GW-25). This is what the machine's job invokes, so anything
    # that leaves it exiting badly is started again in ten seconds and for as long as the
    # machine is up — and an agent whose store is behind the installed shape is the
    # ordinary case after a checkout is updated by any means other than `rundesk update`.
    # Refusing loudly and ending well is the whole difference between one line an owner
    # can act on and a log filling for a week.
    try:
        reachable = agents.reachable(args.name) if agents.exists(args.name) else []
        unrunnable = agents.unrunnable_channels(args.name) if agents.exists(args.name) else []
        # Where this gateway's schedules are, opened here and handed over. **None for a name
        # that is not an agent, and that is a whole gateway** — schedules are something an
        # agent keeps, so one that has no records has no schedules, and the clock has
        # nothing to start for it. A gateway of that name still runs, holds its lock and
        # writes its log, exactly as it did before there were agents at all.
        records = agents.records(args.name) if agents.exists(args.name) else None
        # How a schedule that asks a turn is admitted, resolved here and handed over made.
        # None for a name that is not an agent, which is a gateway that can start programs
        # and not turns — and says so rather than passing the minute over in silence.
        asking = agents.asking(args.name) if agents.exists(args.name) else None
        # How the role runs this agent admitted are carried, and how their parents are
        # told. Resolved here and handed over made, for the same reason `asking` is: a
        # role run needs an agent, a bundle and an account, and a gateway knows none of
        # them (R-ROL-4).
        specialists = agents.playing(args.name) if agents.exists(args.name) else None
        # Both halves of handing work to another named agent: answering what was addressed
        # to this agent, and waking this agent to review what it asked for. Resolved here
        # and handed over made, for the same reason `specialists` is (R-DEL-1).
        handed_over = agents.delegated(args.name) if agents.exists(args.name) else None
        # What this agent may do, resolved here and handed over as a question rather than
        # an answer: a grant is a link anything on the machine may add or take away while
        # the gateway runs, and the gateway is what tells the owner it changed (R-CH-32).
        # None for a name that is not an agent, which holds no grants.
        granted = ((lambda: skills.granted(agents.skills(args.name)))
                   if agents.exists(args.name) else None)
    except (store.Unreadable, store.TooNew, store.Behind, migration.Failed) as why:
        print(f"{args.name}: NOT STARTED — {why}", file=sys.stderr)
        print(f"        what stands in the way:  rundesk doctor {args.name}", file=sys.stderr)
        return 0
    for one, why in unrunnable:
        # Said, and the others still held: one surface that cannot be run must not make
        # an agent deaf on every other one it has.
        print(f"{args.name}/{one}: CHANNEL UNAVAILABLE — {why}", file=sys.stderr)
    try:
        return asyncio.run(gateways.Gateway(args.name, where=whose.run, logs=whose.logs,
                                            reachable=reachable,
                                            # Carried in, the same value the machine's job
                                            # is given, so a program the gateway starts
                                            # finds the agents the gateway is running
                                            # (R-SCH-27).
                                            agents=agents.agents_home(),
                                            records=records,
                                            asking=asking,
                                            roles=specialists,
                                            delegations=handed_over,
                                            granted=granted).serve())
    except (gateways.AlreadyRunning, gateways.Unfit, gateways.NotAName) as why:
        print(f"{args.name}: NOT STARTED — {why}", file=sys.stderr)
        return 0


def cmd_start(args: argparse.Namespace, gateways, machine, agents, skills) -> int:
    """Hand a gateway to the machine, and see that a gateway actually results.

    The machine taking the job is not the gateway running. A job can be accepted and the
    gateway then refuse to start — and refusing ends cleanly, so the machine does not try
    again and nothing says a word. Reporting the hand-off as the outcome is reporting a
    success this command did not earn.
    """
    if args.here:
        # The same function the machine's own job reaches, so what a person types and what
        # launchd runs cannot come to behave differently.
        return cmd_serve(args, gateways, agents, skills)
    name = args.name
    already = standing.of(name, gateways, agents)
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
    whose = agents.resolved(name)
    try:
        # The agent's own directories, written into the job. A gateway the machine starts
        # that resolved anywhere other than where the command that started it wrote is the
        # split that has a schedule silently never run (R-AGT-9).
        said = machine.install(name, run=whose.run, logs=whose.logs,
                               agents=agents.agents_home())
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
    up = standing.came_up(name, gateways, agents)
    if up is None:
        print(f"{name}: FAILED — job accepted, but no gateway started.", file=sys.stderr)
        print(f"         why: rundesk logs {name}", file=sys.stderr)
        return 1
    print(f"{name}: RUNNING (pid {up.pid})")
    return 0


def _named(args: argparse.Namespace, gateways, machine, agents, verb: str) -> list[str] | None:
    """The agents a command is about: the one named, or every one there is — or None.

    None is a refusal, and it is the point of this. Leaving the name out used to mean
    every gateway on the machine, silently: the verb says what and the next word says
    whose, so saying no whose is not saying "all of them", it is not saying. `rundesk
    restart` reads as the one you have, and it took down every agent you had.

    `--all` is how an owner says they mean all of them, and it still means all of them —
    the fan-out is kept, and only the way of asking for it changed.
    """
    if getattr(args, "name", None):
        return [args.name]
    if not getattr(args, "all", False):
        print(f"{verb}: NAME or --all IS REQUIRED — say which agent", file=sys.stderr)
        print(f"        every agent at once:  rundesk {verb} --all", file=sys.stderr)
        print("        what there is:        rundesk agents", file=sys.stderr)
        return None
    return standing.every_name(gateways, machine, agents)


def cmd_stop(args: argparse.Namespace, gateways, machine, agents) -> int:
    return _stand_down(args, gateways, machine, agents, "stop")


def cmd_remove(args: argparse.Namespace, gateways, machine, agents) -> int:
    """Take an agent away for good: its home, its gateway's job, and what rundesk kept.

    Ordered so that nothing is deleted until both the machine and the gateway have let
    go. A job outlives the command it names, so removing rundesk's side first leaves the
    machine trying to start something that is not there, every few seconds and again at
    every login.

    The schedules go with the agent (R-AGW-4), because adding the name back would otherwise
    inherit work nobody asked for from an agent that no longer exists — and so does the
    account of what it did (R-AGW-5). There is no second flag for that, because there is
    no longer a second outcome: an account nobody can name an agent for is an account
    nobody reads, and a flag that changes nothing is a distinction the command does not
    make.
    """
    name = args.name
    if not name:
        print("remove: NAME REQUIRED — say which agent to remove", file=sys.stderr)
        print("        what there is: rundesk agents", file=sys.stderr)
        return 1
    whose = agents.resolved(name)
    # Asked of the gateway rather than of the machine. A gateway started by hand, or one
    # left behind when its job was taken away, has no job for the machine to report — and
    # is exactly the one that must not have its record deleted out from under it.
    now = standing.of(name, gateways, agents)
    if now.running:
        print(f"{name}: STILL RUNNING (pid {now.pid}) — nothing was removed", file=sys.stderr)
        print(f"        stop it first: rundesk stop {name}", file=sys.stderr)
        return 1
    had_job = machine.available() and machine.exists(name)
    if had_job and not machine.known(name):
        print(f"{name}: FAILED — this job belongs to another install of rundesk",
              file=sys.stderr)
        return 1
    if had_job:
        try:
            if not machine.take_back(name):
                print(f"{name}: FAILED — the machine would not let go of its job",
                      file=sys.stderr)
                print("        nothing was removed. See: rundesk status", file=sys.stderr)
                return 1
        except machine.NotOurs as why:
            print(f"{name}: FAILED — {why}", file=sys.stderr)
            return 1
    taken = gateways.forget(name, where=whose.run, logs=whose.logs, history=True)
    if agents.exists(name):
        taken += agents.forget(name)
    if not had_job and not taken:
        print(f"{name}: NOTHING TO REMOVE — no job, and nothing kept under that name")
        return 0
    print(f"{name}: REMOVED")
    print("        its home, its log and everything it did went with it")
    return 0


def cmd_restart(args: argparse.Namespace, gateways, machine, agents) -> int:
    if getattr(args, "worker", False):
        return _run_restart_worker(gateways, machine, agents)
    return _stand_down(args, gateways, machine, agents, "restart")


def _stand_down(args: argparse.Namespace, gateways, machine, agents, verb: str) -> int:
    names = _named(args, gateways, machine, agents, verb)
    if names is None:
        # Said which, and nothing was touched. Not a failure of the machine and not a
        # thing that half happened — it is the command being typed without its subject,
        # which is what argparse spends 2 on.
        return 2
    if not names:
        print("no agents")
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
                now = standing.of(name, gateways, agents)
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
                if (getattr(args, "worker", False)
                        and not standing.of(name, gateways, agents).running):
                    # The external worker may have died after stopping the gateway and
                    # before starting it. Its durable request is still running, so the
                    # retry finishes the missing half instead of asking a stopped job to
                    # stop again and calling the recoverable state a failure (R-GW-43).
                    said = machine.start(name)
                    if not said.ok:
                        print(f"{name}: FAILED — queued restart found it stopped, and "
                              f"the supervisor refused to start it: {said.said}",
                              file=sys.stderr)
                        worst = 1
                        continue
                    up = standing.came_up(name, gateways, agents)
                    if up is None:
                        print(f"{name}: FAILED — queued restart found it stopped, but "
                              "it did not come back", file=sys.stderr)
                        worst = 1
                        continue
                    print(f"{name}: RESTARTED (pid {up.pid})")
                    continue
                protected = _restart_in_flight(name, gateways, agents)
                if protected and not getattr(args, "force", False):
                    if getattr(args, "worker", False):
                        return RESTART_DEFERRED
                    worst = max(
                        worst,
                        _queue_restart(
                            machine, name, update_worker._origin_of_update(agents),
                        ),
                    )
                    continue
                stopped = machine.stop(name)
                if not stopped.ok:
                    print(f"rundesk {name}: could not ask it to stop — {stopped.said}",
                          file=sys.stderr)
                    worst = 1
                    continue
                if not standing.gone(name, gateways, agents):
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
            now = standing.of(name, gateways, agents)
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
            up = standing.came_up(name, gateways, agents)
            if up is None:
                print(f"{name}: FAILED — stopped, but did not restart.", file=sys.stderr)
                print(f"         why: rundesk logs {name}", file=sys.stderr)
                worst = 1
                continue
            print(f"{name}: RESTARTED (pid {up.pid})")
        elif not standing.gone(name, gateways, agents):
            print(f"{name}: FAILED — still running after stop request", file=sys.stderr)
            worst = 1
        else:
            print(f"{name}: STOPPED")
    return worst
