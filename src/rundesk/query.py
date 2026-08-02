"""The read-only answers a channel may ask for, composed for a surface to show.

Seven questions — status, version, agents, skills, schedules, roles, help — and nothing
that changes anything. A channel carries the question and authorizes it; this composes the
answer; the gateway goes on knowing nothing of agents (R-CAD-17).

Apart from `agent.py` because composing what somebody reads in a chat room is not what that
module is for. Its subject is a named identity — what an agent is called, where everything
of its own stands, how one is made and taken away. This reaches `gateway`, `schedule`,
`store` and `role_run` to *describe* an agent, and none of them is needed to resolve one.

Written for a narrow surface throughout: a phone is not where a month of history is read,
so what is over gives way to what is happening.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path

from rundesk import ROOT
from rundesk import agent as agents
from rundesk import gateway, migration, schedule as schedules, skill, store

#: How many role runs a surface is shown. Enough to cover what is happening and what has
#: just happened; the records hold the rest, and a phone is not where a month is read.
ROLES_SHOWN = 10


def answered(name: str, asked: str, where: Path | None = None) -> str:
    """A read-only answer about this install and its agents (R-CAD-17).

    This is the layer that knows agents have gateways. The channel carries the question
    and authorizes it; the gateway remains unaware of agents.
    """
    if asked == "help":
        return (
            "Read-only queries: status, version, agents, skills, schedules, roles, help\n"
            "Conversation controls: stop, forget\n"
            "Agent control: restart"
        )
    if asked == "version":
        standing = gateway.standing(name, agents.resolved(name, where).run)
        running = standing.version or "not running"
        return f"Rundesk installed: {_installed_version()}\n{name} gateway: {running}"
    if asked == "status":
        standing = gateway.standing(name, agents.resolved(name, where).run)
        state = ("WEDGED" if standing.stale else "RUNNING") if standing.running else "STOPPED"
        working = gateway.what_is_working(name, agents.resolved(name, where).run) \
            if standing.running else {}
        turning = gateway.what_is_turning(name, agents.resolved(name, where).run)
        uptime = _query_uptime(standing.started) if standing.running else "-"
        # "?" where the record could not be read: this is answered into a chat room, and a
        # number somebody acts on has to be one we actually know.
        processes = "?" if gateway.could_not_be_read(working) else len(working)
        return (
            f"{name}: {state}\n"
            f"version: {standing.version or '-'}\n"
            f"uptime: {uptime}\n"
            f"processes: {processes}\n"
            f"active turns: {len(turning)}"
        )
    if asked == "agents":
        names = agents.known(where)
        if not names:
            return "no agents"
        rows = []
        for one in names:
            standing = gateway.standing(one, agents.resolved(one, where).run)
            state = ("WEDGED" if standing.stale else "RUNNING") \
                if standing.running else "STOPPED"
            rows.append(f"{one}: {state} ({standing.version or '-'})")
        return "\n".join(rows)
    if asked == "skills":
        # The grant directory is the capability boundary for this agent (R-DIS-36).
        # The shared library and another agent's grants are not things this one can use.
        granted = skill.granted(agents.skills(name, where))
        if not granted:
            return "No skills granted."
        return "\n".join(f"- {called}" for called in granted)
    if asked == "schedules":
        return _query_schedules(name, datetime.now(), where)
    if asked == "roles":
        return _query_roles(name, where)
    raise ValueError(f"unknown read-only query: {asked}")


def _query_roles(name: str, where: Path | None = None, now=None) -> str:
    """What this agent has handed to a role, newest first (R-ROL-28).

    **What is still going, and what has not been reviewed yet.** A run that finished and
    was answered for is over, and on a surface this narrow a list of finished work pushes
    what is actually happening off the bottom of it.

    Never a local path: this is read where other people can see it, so a target is its own
    last component and nothing more (R-ROL-17).
    """
    # Here rather than at the top: `role_run` imports `agent`, and this module imports it
    # too, so naming it up there would close a cycle.
    from rundesk import role_run as role_runs

    try:
        kept = agents.reading(name, where)
        runs = kept.role_runs(limit=200)
        owed = {one["role_run"] for one in kept.owed_role_callbacks()}
    except (store.Unreadable, store.TooNew, store.Behind, migration.Failed) as why:
        return f"could not read what {name} has handed on: {why}"
    live = [one for one in runs
            if one["state"] in store.UNFINISHED_ROLES or one["id"] in owed]
    if not live:
        return "nothing handed to a role right now"
    lines = []
    for row in live[:ROLES_SHOWN]:
        it = role_runs.shown(row, now=now)
        became = "awaiting review" if row["id"] in owed else it["state"]
        where_it_is = f" in {it['target']}" if it["target"] else ""
        lines.append(f"{it['role']} — {it['label']}{where_it_is} — {became}, "
                     f"{_for_how_long(it['elapsed'])}")
    if len(live) > ROLES_SHOWN:
        lines.append(f"and {len(live) - ROLES_SHOWN} more")
    return "\n".join(lines)


def _for_how_long(seconds: int) -> str:
    """How long something has been going, in the largest unit that is not a lie."""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


def _query_schedules(name: str, now: datetime, where: Path | None = None) -> str:
    """What this agent still has waiting, one schedule to a line (R-DIS-37).

    An agent's own, because a schedule belongs to the agent that keeps it (R-SCH-13). The
    moment is an argument for the same reason it is everywhere else this decides anything
    about a clock (R-SCH-12).

    **What can still happen, and nothing else.** A schedule whose one moment has gone can
    never be due again (R-SCH-40), so it is no more part of what this agent runs than one
    that was removed — and on a surface this narrow, a list of things that are over pushes
    the work that is waiting off the bottom of it.
    """
    kept, refused = schedules.read(agents.reading(name, where).schedules())
    # A stated minute is written most-significant first, so what is next reads in order as
    # written. `off` and `never` state no minute at all and go under them, alphabetically.
    lines = sorted(
        ((schedules.describe(one, now), one.name) for one in kept
         if not one.expired_at(now)),
        key=lambda row: (not row[0][:1].isdigit(), row[0], row[1]),
    )
    said = [f"- {when} — {called}" for when, called in lines]
    if not said and not refused:
        said = ["No schedules that can still run." if kept else "No schedules."]
    if refused:
        # Said rather than silently left out: a schedule missing from this list because
        # nobody could read it looks exactly like one that was never added.
        said.append("could not be understood: " + ", ".join(
            sorted(called or "(unnamed)" for called, _why in refused)))
    return "\n".join(said)


def _installed_version(root: Path | None = None) -> str:
    """The code on disk, which may be newer than this still-running gateway."""
    root = root or ROOT
    try:
        source = (root / "src" / "rundesk" / "__init__.py").read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    found = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']\s*$', source, re.MULTILINE)
    return found.group(1) if found else "unknown"


def _query_uptime(started) -> str:
    """A compact duration for a surface whose response has a small text limit."""
    if not isinstance(started, (int, float)):
        return "-"
    seconds = max(0, int(time.time() - started))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _seconds = divmod(seconds, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"
