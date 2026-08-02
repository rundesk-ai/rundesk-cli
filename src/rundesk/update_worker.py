"""The update worker: standing every gateway on this machine down, and putting them back.

The highest-blast-radius path there is. An agent turn, a daily calendar event or an owner
asks for an update; a process **no gateway owns** claims that durable request, waits for
every turn on the machine to finish, stops each supervised gateway, lets the ordinary
guarded updater replace the files, and starts them again. It runs as
`rundesk update --worker`, which is what the launchd job `supervisor.describe_update_worker`
writes invokes — the only way in that nobody types.

It lives beside `updater.py` and `update_request.py` rather than in the command surface
because none of it is a command: the surface adapts what an owner typed, and this decides
what happens to every gateway on a machine. Behind argparse it could only be exercised by
driving the CLI, which is how the worst-consequence code in the product came to be the
least directly tested.

Every collaborator — the gateways, the machine, the agents — is an argument, so the whole
of it runs with no gateway and no supervisor anywhere near it, and `subprocess` and `time`
are reached through this module so a test can replace them here.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from rundesk import ROOT, __version__
from rundesk import config
from rundesk import migration
from rundesk import standing
from rundesk import store
from rundesk import update_request

#: How long the worker waits for every turn on the machine to finish before giving up.
#: Half an hour: long enough for real work to end on its own, bounded so a request that
#: can never proceed is reported rather than waited on forever.
UPDATE_WAIT_SECONDS = 30 * 60

#: How often it looks again while waiting for that work.
UPDATE_POLL_SECONDS = 1.0

#: How long the guarded update itself is given once the machine is quiet.
UPDATE_RUN_SECONDS = 30 * 60


def _origin_of_update(agents) -> dict:
    run_id = os.environ.get("RUNDESK_RUN") or ""
    origin = {"run": run_id}
    for name in agents.known():
        try:
            kept = agents.reading(name)
            run = kept.run(run_id)
        except (store.Unreadable, store.TooNew, store.Behind, migration.Failed):
            continue
        if run is None:
            continue
        origin["agent"] = name
        conversation_id = run.get("conversation_id")
        for conversation in kept.conversations(limit=200):
            if conversation.get("id") == conversation_id:
                origin["channel"] = conversation.get("channel")
                origin["conversation"] = conversation.get("space")
                break
        return origin
    return origin

def _queue_update(machine, origin: dict) -> int:
    """Hand an agent-initiated update to a process its gateway does not own."""
    if not machine.available():
        print("update: NOT QUEUED — this machine has no usable supervisor", file=sys.stderr)
        return 1
    agent = origin.get("agent")
    if agent:
        try:
            if not machine.loaded(agent):
                print(f"update: NOT QUEUED — '{agent}' is not supervised", file=sys.stderr)
                return 1
        except machine.Unsure as why:
            print(f"update: NOT QUEUED — {why}", file=sys.stderr)
            return 1
    try:
        row, created = update_request.queue(origin)
    except update_request.Unreadable as why:
        print(f"update: NOT QUEUED — {why}", file=sys.stderr)
        return 1
    if not created:
        try:
            loaded = machine.update_worker_loaded()
        except machine.Unsure as why:
            print(f"update: NOT QUEUED — {why}", file=sys.stderr)
            return 1
        said = (
            machine.kick_update_worker()
            if loaded else machine.install_update_worker()
        )
        if not said.ok:
            why = said.said or "the supervisor refused the worker"
            update_request.finish(row["id"], "failed", why)
            print(f"update: NOT QUEUED — {why}", file=sys.stderr)
            return 1
        if not loaded:
            print(f"update: RECOVERED — request {row['id']}; "
                  "its missing worker will run after active turns finish")
            print("        outcome: rundesk update --status")
            return 0
        print(f"update: ALREADY QUEUED — request {row['id']}; "
              "it will run after active turns finish")
        print("        outcome: rundesk update --status")
        return 0
    said = machine.install_update_worker()
    if not said.ok:
        why = said.said or "the supervisor refused the worker"
        update_request.finish(row["id"], "failed", why)
        print(f"update: NOT QUEUED — {why}", file=sys.stderr)
        return 1
    print(f"update: QUEUED — request {row['id']}; it will run after active turns finish")
    print("        outcome: rundesk update --status")
    return 0

def _queue_automatic_update(machine) -> int:
    """Turn the daily calendar event into the same recoverable request agents use
    (R-UPD-42)."""
    if not machine.available():
        print("automatic update: NOT QUEUED — this machine has no usable supervisor",
              file=sys.stderr)
        return 1
    try:
        row, created = update_request.queue({})
    except update_request.Unreadable as why:
        print(f"automatic update: NOT QUEUED — {why}", file=sys.stderr)
        return 1
    if not created:
        try:
            if machine.update_worker_loaded():
                said = machine.kick_update_worker()
                if not said.ok:
                    why = said.said or "the supervisor refused the worker"
                    update_request.finish(row["id"], "failed", why)
                    print(f"automatic update: NOT QUEUED — {why}", file=sys.stderr)
                    return 1
                return 0
        except machine.Unsure as why:
            print(f"automatic update: NOT QUEUED — {why}", file=sys.stderr)
            return 1
    said = machine.install_update_worker()
    if not said.ok:
        why = said.said or "the supervisor refused the worker"
        update_request.finish(row["id"], "failed", why)
        print(f"automatic update: NOT QUEUED — {why}", file=sys.stderr)
        return 1
    return 0

def _install_automatic_updates(machine) -> int:
    if not machine.available():
        return 0
    try:
        at = config.updates()["at"]
        said = machine.install_automatic_update(at)
    except (config.Unreadable, machine.NoSupervisor, machine.NotOurs) as why:
        print(f"update: APPLIED, but automatic updates were not scheduled — {why}",
              file=sys.stderr)
        return 1
    if not said.ok:
        why = said.said or "the supervisor refused the daily job"
        print(f"update: APPLIED, but automatic updates were not scheduled — {why}",
              file=sys.stderr)
        return 1
    return 0

def _run_update_worker(gateways, machine, agents) -> int:
    """Wait outside every gateway, run the ordinary guarded updater, persist its outcome."""
    target_root = Path(os.environ.get("RUNDESK_UPDATE_ROOT") or ROOT)
    environment = dict(os.environ)
    for key in ("RUNDESK_RUN", "RUNDESK_RESUME"):
        environment.pop(key, None)
    environment["RUNDESK_UPDATE_WORKER"] = "1"
    try:
        request = update_request.claim()
    except update_request.Unreadable as why:
        print(f"update worker: FAILED — {why}", file=sys.stderr)
        return 1
    if request is None:
        return 0
    if target_root == ROOT:
        target_version = __version__
    else:
        reported = _reported_version(target_root, environment)
        prefix = "rundesk "
        if not reported or not reported.startswith(prefix):
            update_request.finish(
                request["id"], "failed",
                f"could not read the installed version at {target_root}",
            )
            return 1
        target_version = reported[len(prefix):]
    environment["RUNDESK_UPDATE_VERSION"] = target_version
    deadline = time.monotonic() + UPDATE_WAIT_SECONDS
    while True:
        busy = _in_flight(gateways, agents)
        origin = _origin_still_running(request, agents)
        if origin and origin not in busy:
            busy.append(origin)
        if not busy:
            break
        if time.monotonic() >= deadline:
            update_request.finish(
                request["id"], "failed",
                "timed out waiting for active work: " + ", ".join(busy),
                _reported_version(target_root, environment),
            )
            return 1
        time.sleep(UPDATE_POLL_SECONDS)
    try:
        done = subprocess.run(
            [str(ROOT / "rundesk"), "update"],
            capture_output=True, text=True, env=environment, timeout=UPDATE_RUN_SECONDS,
        )
        version = _reported_version(target_root, environment)
        result = (done.stdout + done.stderr).strip() or (
            "update completed" if done.returncode == 0 else "update failed without output"
        )
        state = "succeeded" if done.returncode == 0 else (
            "rolled_back" if "roll" in result.lower() and "back" in result.lower()
            else "failed"
        )
        left_down = _recover_update_gateways(gateways, machine, agents, target_root)
        if left_down:
            result += "\nupdate worker: gateways still offline: " + ", ".join(left_down)
            state = "failed"
        scheduled = _install_automatic_updates(machine)
        if scheduled:
            result += "\nupdate worker: automatic updates could not be scheduled"
            state = "failed"
        update_request.finish(request["id"], state, result, version)
        return 0 if state == "succeeded" else 1
    except subprocess.TimeoutExpired as why:
        # Unknown is not failed. The child was killed somewhere inside the guarded window,
        # so its durable request remains active and launchd starts this worker again. That
        # successor reconciles the install before it considers any marked gateway safe to
        # start (R-UPD-44).
        print(f"update worker: interrupted — retrying: {why}", file=sys.stderr)
        return 1
    except OSError as why:
        left_down = _recover_update_gateways(gateways, machine, agents, target_root)
        result = str(why)
        if left_down:
            result += "; gateways still offline: " + ", ".join(left_down)
        update_request.finish(
            request["id"], "failed", result,
            _reported_version(target_root, environment),
        )
        return 1

def _origin_still_running(request: dict, agents) -> str | None:
    """The initiating run itself, until its durable account says it ended."""
    origin = request.get("origin") or {}
    agent = origin.get("agent")
    run_id = origin.get("run")
    if not agent or not run_id:
        return None
    try:
        run = agents.reading(agent).run(run_id)
    except (store.Unreadable, store.TooNew, store.Behind, migration.Failed):
        return f"{agent}/turn:{run_id}"
    if run is not None and not run.get("ended_at"):
        return f"{agent}/turn:{run_id}"
    return None

def _reported_version(root: Path, environment: dict) -> str | None:
    try:
        return subprocess.run(
            [str(root / "rundesk"), "version"],
            capture_output=True, text=True, env=environment, timeout=30,
        ).stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None

def _stand_all_down(gateways, machine, agents,
                    root: Path = ROOT) -> tuple:
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
    for name in standing.every_name(gateways, machine, agents, root):
        it = standing.of(name, gateways, agents)
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
        run_home = agents.resolved(it.name).run
        protected = [
            one for one in gateways.what_is_working(it.name, run_home)
            if not one.startswith("channel:")
        ]
        protected.extend(
            f"turn:{row['run']}" for row in gateways.what_is_turning(it.name, run_home)
        )
        if protected:
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
        run_home = agents.resolved(it.name).run or gateways.home()
        try:
            update_request.begin_maintenance(it.name, run_home)
        except OSError as why:
            return stopped, (
                f"maintenance could not be recorded for '{it.name}': {why}; "
                "it was not taken down"
            )
        said = machine.stop(it.name, root=root)
        if not said.ok or not standing.gone(it.name, gateways, agents):
            update_request.finish_maintenance(it.name, run_home)
            return stopped, f"'{it.name}' would not stop, so nothing was replaced under it"
        stopped.append(it.name)
    return stopped, None

def _bring_all_back(names: list, gateways, machine, agents,
                    root: Path = ROOT) -> list:
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
            said = machine.start(name, root=root)
        except (machine.NotOurs, machine.NoSupervisor):
            down.append(name)
            continue
        if not said.ok or standing.came_up(name, gateways, agents) is None:
            down.append(name)
    if down:
        unfit = gateways.fitness(root)
        if unfit:
            print(f"update: what rundesk is made of no longer fits: {unfit}", file=sys.stderr)
    return down

def _recover_update_gateways(gateways, machine, agents,
                             root: Path = ROOT) -> list[str]:
    """Repay gateways a previous worker marked before it stopped.

    The marker is the distinction between maintenance and an owner deliberately stopping
    a gateway. It outlives a worker crash, so a replacement can finish the promise without
    starting anything the update did not take down (R-UPD-44).
    """
    marked = []
    for name in standing.every_name(gateways, machine, agents, root):
        run_home = agents.resolved(name).run or gateways.home()
        if update_request.maintaining(name, run_home):
            marked.append((name, run_home))
    # A half-installed release is not safe to serve. Leaving the request active lets the
    # supervisor-owned worker reconcile it; starting gateways first would trade uptime for
    # a process running code known not to fit together.
    if gateways.fitness(root):
        return [name for name, _run_home in marked]
    down = []
    for name, run_home in marked:
        if standing.of(name, gateways, agents).running:
            continue
        try:
            kept = machine.loaded(name)
            said = machine.start(name, root=root) if kept else None
        except (machine.NoSupervisor, machine.NotOurs, machine.Unsure):
            said = None
        if said is None or not said.ok or standing.came_up(name, gateways, agents) is None:
            down.append(name)
            continue
    return down

def _in_flight(gateways, agents) -> list:
    """Everything every gateway on this machine says it is working on (R-UPD-23).

    Asked of the gateways rather than of a list kept somewhere, and named by gateway as
    well as by work: an owner told only that "something" is running has to go and find
    which of several it was before they can decide to wait.
    """
    found = []
    for name in sorted(set(agents.known() + [it.name for it in gateways.every()])):
        run_home = agents.resolved(name).run
        if standing.of(name, gateways, agents).running:
            found.extend(f"{name}/{one}"
                         for one in gateways.what_is_working(name, run_home)
                         if not one.startswith("channel:"))
        found.extend(f"{name}/turn:{row['run']}"
                     for row in gateways.what_is_turning(name, run_home))
    return found
