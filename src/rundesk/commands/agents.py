"""The agents this install keeps, and the four things anybody does with them.

`rundesk agents` on its own lists them, the way `backups` and `env` do, because listing is what
somebody wants nine times in ten and a verb they have to remember for it is a verb they will not
remember. The other three are named: `add`, `configure` and `remove`.

This decides only how a person types it and what they are shown. What an agent *is* — a directory
holding `state.db`, standing under `data/agents/` — belongs to `agents.directory`, and this module
never reaches past it to the disk.

**A provider is recorded and it is not proven.** Nothing in this release runs one: a gateway can be
started for an agent, and what that gateway hosts is not a provider yet — no credential is checked
and no request is made. So `add` and `configure` say so out loud on the line that reports success.
An agent added with a provider nobody has ever spelled correctly looks exactly like one that works,
and letting the wording imply otherwise would be claiming a success this release did not earn —
which is the one thing this product is written against.

**`remove` asks for `--confirm`**, and a flag rather than a prompt for the reason `uninstall` gives:
a prompt in a script is a command that hangs, and one that assumes yes with no terminal is worse
than no prompt at all. It takes an agent's whole memory, which is the thing here that no backup of
`data/` taken afterwards can bring back.

**And it refuses while anything is running for that agent**, which is a check that can only be
made here: `agents/` sits below `gateways/`, `schedules/` and `channels/` and may not import any of
them, so the layer that removes an agent cannot ask, and `directory.forgotten` says as much in its
own docstring. Three things to ask about and one reason behind all three — a gateway hosting an
agent that no longer exists, a firing whose lock this removal would hand away, and an adapter still
connected to a platform as an agent that is gone.
"""

import argparse
import sqlite3
import sys
from typing import List, Optional

from rundesk.agents import directory, migration, records
from rundesk.channels import hosting
from rundesk.commands import Subcommands, failed
from rundesk.core import paths
from rundesk.exits import FAILED, OK
from rundesk.gateways import job, standing
from rundesk.schedules import firing, kept
from rundesk.skills import grants
from rundesk.utils import locking
from rundesk.utils.terminal import as_table

#: What is true of a provider in this release, said wherever one is recorded.
#:
#: One string rather than a sentence written twice, because `add` and `configure` make exactly the
#: same claim and two wordings of it would eventually become two different claims.
NOT_PROVEN = ("the provider is recorded and not proven — check it with: "
              "rundesk providers check")

#: What a name outside `job.IN_A_LABEL` costs, said where the name is chosen rather than where it is
#: next needed. `agents` allows any name a directory may have and launchd's labels are narrower, so
#: this is an agent no job can ever be placed for — and the moment somebody finds that out must not
#: be the moment they cannot stop it.
NO_JOB_EVER = ("this name cannot be a launchd label, so no job can ever be placed for it — nothing "
               "starts its gateway at login and nothing brings it back when it stops. Run it with "
               "`rundesk gateways run` and stop it with `rundesk gateways stop`, or add the agent "
               "again under a name of letters, digits, a dot, a dash or an underscore")

#: Everything making, changing or taking an agent away can end as.
#:
#: Named once because three verbs catch the same set, and spelled out because `agents/` hands back
#: several different kinds of trouble rather than one: a refusal it decided itself, records that are
#: not there or cannot be understood, a migration step that will not load, the install lock held by
#: something else, and the ordinary failures of a disk. `sqlite3.Error` is here for the same reason
#: as the rest — `records` turns a file that is not a database into `Unreadable` at open time, but a
#: writer that waits out its whole busy timeout against a gateway still surfaces SQLite's own error,
#: and a traceback is not an answer somebody can act on.
TROUBLE = (directory.Refused, records.NotThere, records.Unreadable, records.Refused,
           migration.Ahead, migration.Broken, locking.Stuck, OSError, sqlite3.Error)


def register(sub: Subcommands) -> None:
    """Put `agents` on the parser, with one sub-verb for each thing that happens to an agent.

    **`--provider` is registered as an ordinary option rather than as `required=True`, and
    `--confirm` as a flag rather than as a positional.** argparse's own `required` would refuse the
    command line itself — exit `2`, in argparse's words, which name the flag and do not say what to
    type. Both of these guard an effect rather than describe one, so they are refused by the verb,
    at exit `1`, in a sentence that ends with the command somebody should run. That is the shape
    `uninstall --confirm` already has, and there is no reason for this to be the second shape.
    """
    # `kept_here` rather than `kept`, which is the name of the schedules store this module now
    # imports. The shadow would be local to this function and harmless today, and the day somebody
    # adds a line here that wants the store it would be a `NoneType has no attribute` from a parser.
    kept_here = sub.add_parser("agents", help="the agents this install keeps")
    what = kept_here.add_subparsers(dest="what", metavar="<what>")

    what.add_parser("list", help="every agent this install keeps, and what is behind it")

    new = what.add_parser("add", help="make an agent")
    new.add_argument("agent", metavar="<agent>", help="what to call it")
    new.add_argument("--provider", metavar="<provider>", default=None,
                     help="required — what is behind it; recorded, and not proven")

    changed = what.add_parser("configure", help="change what an agent is configured with")
    changed.add_argument("agent", metavar="<agent>", help="which one, as `rundesk agents` lists it")
    changed.add_argument("--provider", metavar="<provider>", default=None,
                         help="what is behind it; recorded, and not proven")

    gone = what.add_parser("remove", help="take an agent away, and everything it remembers")
    gone.add_argument("agent", metavar="<agent>", help="which one, as `rundesk agents` lists it")
    gone.add_argument("--confirm", action="store_true",
                      help="required — removal does nothing without it")


def cmd_agents(args: argparse.Namespace) -> int:
    """Answer whichever of the four was asked for; with none of them, list what there is."""
    try:
        paths.home()
    except paths.Refused as why:
        return _failed(str(why))

    what = getattr(args, "what", None)
    if what in (None, "list"):
        return _listed()
    if what == "add":
        return _made(args.agent, args.provider)
    if what == "configure":
        return _configured(args.agent, args.provider)
    if what == "remove":
        return _forgotten(args.agent, args.confirm)

    # Unreachable while every sub-verb above is answered, and that is the point: one registered on
    # the parser and wired to nothing fails here loudly rather than exiting 0 having done nothing.
    raise AssertionError(f"agents {what} is registered on the parser and answered by nothing")


def _listed() -> int:
    """Every agent there is, in name order, with what is recorded behind it.

    Where they stand is printed even when there are none, for the reason `backups` prints it: "no
    agents" and "no agents *here*" are different things to learn, and somebody looking at the wrong
    root needs to see which directory was just found empty.

    An agent whose records cannot be read is listed with a provider nobody can answer for rather
    than left out. Leaving it out would say the agent is not there, which is a different and worse
    thing to be told — the directory is on the disk and something has to be done about it.
    """
    at = paths.agents()
    try:
        there = directory.known()
    except OSError as why:
        return _failed(str(why), "nothing was listed")

    print(f"agents in {at}")
    if not there:
        print("        no agents yet — add one with: "
              "rundesk agents add <agent> --provider <provider>")
        return OK
    as_table(("AGENT", "PROVIDER"), [(name, _provider_of(name)) for name in there])
    return OK


def _provider_of(name: str) -> str:
    """What is recorded behind one agent, or why that could not be answered.

    The two ways it cannot be answered are kept apart, because they are different situations:
    records that have gone away between the listing and the reading, and records that are there and
    cannot be understood. Collapsing them would tell somebody with a corrupt database that their
    agent is simply missing, and what they do next is make a new one over it.
    """
    try:
        return str(records.read(directory.records(name))["provider_name"])
    except records.NotThere:
        return "? — its records are not there"
    except (directory.Refused, records.Unreadable, OSError, sqlite3.Error, KeyError):
        return "? — its records cannot be read"


def _made(name: str, provider: Optional[str]) -> int:
    """Make an agent, and say what was made — one named thing at a time.

    The provider is checked here before anything is built, so somebody who left it out is told what
    to type rather than told by argparse which flag is missing. `directory.made` refuses an empty
    one too, and refuses it again inside the install lock where the name is checked; this is the
    refusal worded for a person, not a second opinion about the rule.
    """
    trouble = _provider_trouble(provider, f"rundesk agents add {name} --provider <provider>")
    if trouble:
        return _failed(trouble, "nothing was made")

    try:
        at = directory.made(name, provider or "")
    except TROUBLE as why:
        return _failed(str(why), "nothing was made")

    print(f"agent {name} added")
    print(f"        provider  {provider}")
    print(f"        home      {at / directory.HOME}")
    print(f"        logs      {at / directory.LOGS}")
    print(f"        records   {at / directory.RECORDS}")
    if job.name_trouble(name):
        print(f"        note      {NO_JOB_EVER}")
    print(f"        note      {NOT_PROVEN}")
    return OK


def _configured(name: str, provider: Optional[str]) -> int:
    """Change what one agent is configured with, or refuse having changed nothing.

    **Naming nothing to change is refused rather than reported as a success.** `configure` makes the
    same decision one layer up and for the same reason: a command that reports success having
    changed nothing teaches somebody that it worked, and the next thing they do rests on a change
    that never happened. Showing what the agent is configured with instead is a listing wearing the
    name of a change, and `rundesk agents` already answers that question.
    """
    if provider is None:
        return _failed(f"nothing was named to change about {name}",
                       f"change one with: rundesk agents configure {name} --provider <provider>",
                       "nothing was changed")
    trouble = _provider_trouble(provider,
                                f"rundesk agents configure {name} --provider <provider>")
    if trouble:
        return _failed(trouble, "nothing was changed")

    gone_wrong = directory.not_an_agent(name)
    if gone_wrong:
        return _failed(gone_wrong, "see what there is with: rundesk agents", "nothing was changed")

    try:
        records.stated(directory.records(name), {"provider_name": provider})
    except TROUBLE as why:
        return _failed(str(why), "nothing was changed")

    print(f"{name}: provider is now {provider}")
    print(f"        {NOT_PROVEN}")
    return OK


def _forgotten(name: str, confirming: bool) -> int:
    """Take an agent away, or — with nothing confirming it — say exactly what that would take."""
    gone_wrong = directory.not_an_agent(name)
    if gone_wrong:
        # Checked before the confirmation is asked for, so somebody who mistyped the name finds out
        # now rather than after typing `--confirm` for an agent that was never there.
        return _failed(gone_wrong, "nothing was removed")
    if not confirming:
        return _needs_confirming(name)

    # Whether a gateway is running is checked *here*, and it cannot be checked anywhere lower:
    # `agents/` sits below `gateways/` and may not import it, which `tests/test_layers.py`
    # enforces, and `directory.forgotten`'s own docstring says the caller must do it. Below the
    # confirmation rather than above it, because a description of a removal describes what would be
    # taken while this decides whether it may happen at all — and a gateway can come up between the
    # two commands anyway, so the only moment worth asking in is the moment of acting.
    running = _its_gateway_is_up(name)
    if running:
        return _failed(running, f"stop it with: rundesk gateways stop {name}", "nothing was removed")

    # And whether any of its *schedules* is running, which is a different question with the same
    # answer. A schedule run by hand holds only its own lock and never `gateway.lock`, so an agent
    # with no gateway at all can still have work in flight — and this removal takes `schedules/`
    # with everything else. See `_its_schedules_are_running`.
    working = _its_schedules_are_running(name)
    if working:
        return _failed(working, f"see what it is doing with: rundesk schedules list {name}",
                       "nothing was removed")

    # And whether any of its *channels* has an adapter connected, which is the same question again
    # about the other thing a gateway hosts. An adapter holds its channel's lock and never
    # `gateway.lock`, and one adopted from a gateway that is gone outlives every gateway there has
    # been — so an agent that reads as free to both checks above can still have a program connected
    # to a platform as it. See `_its_channels_are_running`.
    connected = _its_channels_are_running(name)
    if connected:
        return _failed(connected, f"see what is connected with: rundesk channels list {name}",
                       "nothing was removed")

    at = paths.agents() / name
    try:
        gone = directory.forgotten(name)
    except TROUBLE as why:
        return _failed(str(why), f"{at} is not fully taken away")

    print(f"agent {name} removed")
    for one in gone:
        print(f"        took   {one}")
    if at not in gone:
        # `directory.forgotten` removes the agent's own directory only when it is then empty.
        # Something the owner put in there is kept, along with the directory holding it — and the
        # removal is still a removal, because everything that made this an agent is gone.
        print(f"        kept   {at} — something you put in there is still there")
    return OK


def _skills_it_holds(name: str) -> List[str]:
    """What this agent holds, for the removal to name. Empty when it holds nothing or cannot be read.

    Answered as nothing rather than raised. This is one line of a description somebody is about to
    agree to, and a listing that could not be built is not a reason to refuse to describe the
    removal — the removal itself does not depend on it.
    """
    try:
        return [one.name for one in grants.held(name)]
    except (grants.Refused, directory.Refused, OSError):
        return []


def _what_it_has_scheduled(name: str) -> int:
    """How many schedules this agent keeps, for the removal to name. `0` when it cannot be read.

    Answered as nothing rather than raised, for the reason `_skills_it_holds` gives: this is one line
    of a description somebody is about to agree to, and a count that could not be taken is not a
    reason to refuse to describe the removal.
    """
    try:
        return len(kept.all(name))
    except (kept.Refused, records.NotThere, records.Unreadable, directory.Refused,
            migration.Ahead, OSError, sqlite3.Error):
        return 0


def _needs_confirming(name: str) -> int:
    """Say exactly what a removal would take, and take none of it.

    Every line names one thing, the way `uninstall` does, because a removal described as a sweep is
    a removal nobody can check before they agree to it.
    """
    at = paths.agents() / name
    print(f"remove: this would take the agent {name} from {paths.agents()}", file=sys.stderr)
    print(f"        take   {at / directory.RECORDS} — everything {name} remembers, and what "
          "SQLite keeps beside it", file=sys.stderr)
    print(f"        take   {at / directory.HOME} — where {name} started, and what it put there",
          file=sys.stderr)
    held = _skills_it_holds(name)
    if held:
        # Named separately although `home/` already covers it. A grant is a link inside that
        # directory, so it goes with it either way — and somebody reading a line about "where the
        # agent started" has no way to know that the skills they granted are inside it. What is
        # *not* taken is the skill itself, and saying so is the point: this reads as though a
        # removal could cost them a catalog.
        print(f"        take   {len(held)} skill grant(s) — {', '.join(held)}; the skills "
              "themselves stay in the library", file=sys.stderr)
    print(f"        take   {at / directory.LOGS}", file=sys.stderr)
    if (at / directory.CHANNELS).is_dir():
        # Named for the reason the schedules line below is, and only when it is there: `forgotten`
        # really does take this directory, and everything that ever arrived through a channel is
        # inside it — a preview that left it out would describe a smaller removal than the one
        # about to happen.
        print(f"        take   {at / directory.CHANNELS} — every channel it is reached on, what "
              "arrived through each, and what their adapters wrote", file=sys.stderr)
    scheduled = _what_it_has_scheduled(name)
    if scheduled:
        # Named because `directory.forgotten` really does take this directory, and a preview that
        # left it out would describe a smaller removal than the one about to happen — which is the
        # one thing this list exists not to do. What goes with it is everything every firing of
        # those schedules wrote.
        print(f"        take   {at / directory.SCHEDULES} — {scheduled} schedule(s), what each has "
              "already done, and everything their runs wrote", file=sys.stderr)
    for one in (at / directory.GATEWAY_RECORD, at / directory.GATEWAY_LOCK):
        # Named only when it is there. Listing what a gateway *might* have left would describe a
        # removal larger than the one that would happen, and this list is what somebody checks
        # before they agree to it.
        if one.exists():
            print(f"        take   {one} — what a gateway left behind", file=sys.stderr)
    print(f"        keep   anything else you put in {at}", file=sys.stderr)
    print("        nothing was removed. To go ahead:", file=sys.stderr)
    print(f"        rundesk agents remove {name} --confirm", file=sys.stderr)
    return FAILED


def _its_gateway_is_up(name: str) -> str:
    """Why this agent may not be taken away yet, or `""` when it may.

    **Removing an agent whose gateway is up leaves a running program with no records**: the process
    goes on holding the name, writing into a directory that is no longer there, hosting an agent
    that no longer exists — and launchd puts it back when it dies, because the job outlives the
    records the removal took.

    Asked of the kernel through `gateways.standing`, and never of the record beside the lock. Its
    third answer is kept as a third answer here too: an agent nobody can ask about is not an agent
    that is safe to remove, and reporting it as free is how a second gateway comes to be started
    beside a first — or, here, how a live one is quietly orphaned.
    """
    how = standing.standing(directory.where(name))
    if how.how == standing.ONLINE:
        return (f"a gateway is running for {name}"
                + (f" as pid {how.pid}" if how.pid else "")
                + " — removing it now would leave a running program with no records")
    if how.how == standing.CANNOT_TELL:
        return f"nobody can tell whether a gateway is running for {name} — {how.why}"
    return ""


def _its_schedules_are_running(name: str) -> str:
    """Why this agent may not be taken away yet because work is in flight, or `""` when it may.

    **A schedule running by hand holds only its own lock, never `gateway.lock`**, so an agent with no
    gateway anywhere reads as free to `_its_gateway_is_up` and can still have a program running. This
    removal takes `schedules/` with everything else — and unlinking a lock while something holds it
    hands the name away, so a later agent and schedule of the same names claim a *fresh* inode and
    lock that, while the original child is still holding the old one. Two firings of one schedule,
    running at once, which is the single thing the whole locking design exists to prevent.

    Asked of the kernel through the lock files rather than of the records, so it is still answerable
    when the database cannot be read — which is one of the states somebody removes an agent in.
    """
    try:
        working = firing.in_flight(name)
    except (directory.Refused, OSError):
        # Not a reason to refuse a removal on its own: an agent whose directory cannot be listed has
        # bigger problems, and `directory.forgotten` will raise about the same thing in a moment with
        # a sentence about what it could not take.
        return ""
    if not working:
        return ""
    return (f"{name} has work still running: {', '.join(working)} — removing it now would take the "
            "lock that work is holding, and a schedule of the same name later would start a second "
            "copy beside it")


def _its_channels_are_running(name: str) -> str:
    """Why this agent may not be taken away yet because it is still connected, or `""` when it may.

    **An adapter holds its channel's own lock, never `gateway.lock`**, so an agent with no gateway
    anywhere reads as free to `_its_gateway_is_up` and can still have a program connected to a
    platform as it — an adopted one outlives every gateway there has been. This removal takes
    `channels/` with everything else, and unlinking a lock while something holds it hands the name
    away, so a later agent and channel of the same names claim a *fresh* inode and lock that, while
    the original adapter is still holding the old one. Two adapters connected as one agent, both
    answering the people on its allow list, which is the single thing the whole locking design
    exists to prevent.

    Asked of the kernel through the lock files rather than of the records, so it is still answerable
    when the database cannot be read — which is one of the states somebody removes an agent in.

    **A claim nobody can ask about is refused, not read as free**, which is `_its_gateway_is_up`'s
    third answer kept as a third answer here too. `hosting.still_running` deliberately re-raises
    anything that is not ordinary contention — a permission problem, a filesystem that will not lock
    — and treating that as "nothing is connected" is exactly how a live adapter comes to be orphaned
    by a removal. A channels directory that cannot be *listed* is the other thing and is not this
    one: `hosting.in_flight` answers nothing for it, and `directory.forgotten` will raise about the
    same directory in a moment with a sentence about what it could not take.
    """
    try:
        connected = hosting.in_flight(name)
    except directory.Refused:
        # A name that reaches outside where agents are kept. `forgotten` refuses the same name a
        # moment later and says so in words about the name rather than about a lock.
        return ""
    except OSError as why:
        return (f"nobody can tell whether {name} is still connected — {why}")
    if not connected:
        return ""
    return (f"{name} is still connected: {', '.join(connected)} — removing it now would take the "
            "lock that adapter is holding, and a channel of the same name later would connect a "
            "second one beside it")


def _provider_trouble(said: Optional[str], typed: str) -> str:
    """Why this is not a provider, or `""` when it is.

    Nothing said and nothing *in* what was said are different mistakes and get different sentences:
    one is a flag somebody left off, and the other is a flag they gave an empty value to — usually
    a shell variable that was not set, which is exactly the case where being told what to type again
    does not help.
    """
    if said is None:
        return f"nothing said which provider — say which with: {typed}"
    if not said.strip():
        return "a provider with nothing in it is not one — an agent with nothing behind it cannot answer"
    return ""


def _failed(why: str, *and_so: str) -> int:
    """Say what went wrong, and what that leaves — never one without the other."""
    return failed(f"agents: FAILED — {why}", *and_so)
