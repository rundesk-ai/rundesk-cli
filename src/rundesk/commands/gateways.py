"""The gateway that hosts each agent, and the six things anybody does with one.

`rundesk gateways` on its own lists them, the way `agents` and `backups` do, because listing is what
somebody wants nine times in ten. The other five are named: `start`, `stop`, `restart`, `logs` and
`run`.

This decides only how a person types it and what they are shown. Whether a gateway is up belongs to
`gateways.standing`, the job belongs to `gateways.job`, and the process itself belongs to
`gateways.host`; every one of them was built and tested before this, and nothing here reaches past
them to launchd or to a lock.

## Four sources, because `launchctl print` answering 113 is ambiguous

A gateway that is up, a job that is loaded, an override store that outlives every plist, and a
Background Task Management store nobody published the format of. `print` answers `113` for a plist
that was never bootstrapped, for a label with only a stale override record, for a label that never
existed, and for a job launchd installed and then threw away — byte-identical, all four. So the
listing shows all four answers and **never says "not installed" on a 113 alone**. `job.stands` is
what decides that; this is what says it out loud.

## The two refusals that are the whole point of the file

**A start never kicks a gateway that is already running.** `kickstart -k` is kill-then-restart, so a
start that ran it unconditionally would end a gateway in the middle of real work — which is the
incident `standing`'s docstring records, one layer up: an ordinary start that had checked first
ended a live agent's whole process tree. So `standing` is asked first, and a kick only ever follows
a bootstrap of a gateway that was confirmed **not** online and did not come up on its own.

**`stop` and `restart` take a name or `--all`, one of them, never both and never neither.** The
build this replaces let a bare `restart` mean every agent, and it took down every gateway somebody
had. A bare verb here is a refusal that shows both spellings and changes nothing — and it exits
`2`, because a command line that named neither is the command line itself being wrong, which is
what `docs/commands.md` promises `2` for and what argparse already exits for a mistyped sub-verb.

## Coming down gracefully is the default, and `--force` is the exception

**Both verbs are graceful unless told otherwise, and this is stated here once.** `stop` and
`restart` take a gateway down with `bootout --wait`, which sends `SIGTERM` and then waits for the
process to really be gone, up to the job's own `ExitTimeOut`. A gateway is holding somebody's work,
so it gets to finish it.

**`--force` does not wait for that.** It ends the process where it stands with `kill SIGKILL`
first; the `bootout --wait` that follows then returns at once, because there is nothing left to
wait for, and a `restart` bootstraps over the name that has just come free. It is for a gateway
that **will not go** — one ignoring `SIGTERM`, so that a graceful stop blocks for the whole window
— and never for one that is merely busy, which is exactly the gateway with something to lose. It
takes work away mid-flight, and both the help text and the output say so.

**`--force` is not a `kickstart`, and the reason is measured.** `kickstart -k` does not get past a
throttle; it waits the whole `ThrottleInterval` out with the caller blocked — 30 seconds, measured
2026-08-05 — while kill, bootout and bootstrap put a new pid up immediately. A `restart --force`
built on `kickstart` under a ten-second ceiling failed on a machine where nothing was wrong, and
`docs/research/launchd-on-macos.md` §5 carries the correction and the numbers.

## And the state that must never be reported as health

A gateway holding its agent's name with no job behind it is **not** running in any sense worth
telling somebody: nothing brings it back when it stops, and nothing starts it at the next login.
Saying "running" there tells a person they are covered when they are not, so it is said as the
failure it is, with the command that resolves it.

**There are two of those states and they are not one state**, because what a person does about them
is not the same. A job that is *not placed yet* is one a restart puts back. A job that can **never**
be placed — the agent is named something a launchd label cannot carry, which `agents` allows and
`job.IN_A_LABEL` does not — is one no command of this product will ever place, however many times it
is run. Both are said as failures; only one of them is offered a restart.

## When there is no job to take back, the gateway is still stopped

**A gateway must never be stuck, and never locked out.** That is the absolute the research page is
built around, and a stopping verb that gives up because there is no job to ask launchd about breaks
it through a supported verb: `gateways run <agent>` starts a gateway for any agent, including one
whose name can never be a label, and every stopping verb used to refuse that name before it had even
asked whether a gateway was running. The process held the agent's name and nothing in the product
could take it back.

So `stop` and `restart` fall back to `utils.programs.stop`, which signals the recorded pid's process
*group* — `SIGTERM`, then `SIGKILL` — whenever there is no launchd job to talk to: a name no label
can carry, or a job that was never bootstrapped, which is what a gateway still holding the name
after its job came back proves.

**The pid is read from `standing`, and only ever while the lock says a gateway is running.** A pid
from a record whose process is gone is a number that now belongs to somebody else, and signalling it
kills a stranger's program — which is the whole reason liveness is a `flock` and not a pid file.

**Graceful still means graceful.** A gateway signalled directly gets the same window to finish that
its job's `ExitTimeOut` would have given it under launchd, and `--force` is the only thing that skips
the waiting — the same bargain it makes on every other path here.

## The supervisor arrives as an argument

`job.Supervising` is passed in, exactly as `lifecycle.release.Asking` and `commands.update.Fetching`
are, and resolved **inside** a body rather than defaulted in a signature. For a stronger reason than
either of those: they leave the machine, so a suite that forgot to replace one fails loudly on
somebody's network. This one does not leave the machine — the real implementation would answer a
test perfectly well, against the owner's own login session, booting out jobs that keep real work
running. The seam is the whole of the defence.

## And a seventh thing, which nobody types: what another command reaches for

`Cycled` is the two of these verbs that another command needs — stand this gateway down, start it
again — as something it can be handed. Two commands have to free an agent's name for the length of
one operation: `update` runs a migration step against records a gateway holds open, and `backups
restore` replaces the very file a gateway's lock lives on. Both were written around a seam and
neither could be given one until this module existed.

**It is built on the verbs above rather than beside them**, and that is the point of it being here
at all. What a stop really means in this product — prove the name came free rather than trust a
`bootout`, fall back to a signal when there is no job to take back, never report a start that no
gateway came up for — is `_stopped_one` and `_started`, and a private stop written for the seam
would be a second opinion about every one of those, wrong the first time either changed.
"""

import argparse
import os
import shlex
import sys
import time
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

from rundesk.agents import directory
from rundesk.commands import Subcommands, failed
from rundesk.core import paths
from rundesk.exits import FAILED, OK, USAGE
from rundesk.gateways import host, job, standing
from rundesk.utils import logs, programs
from rundesk.utils.terminal import as_table

#: How many lines of a gateway's log are shown when nobody says how many.
LINES = 20

#: What `--force` says it is, in one sentence and **the same sentence on both verbs**. Two spellings
#: of one flag is how somebody comes to believe `stop --force` and `restart --force` differ in what
#: they cost, and what they cost is the same thing: the gateway is killed rather than asked, and
#: whatever it was doing is taken away where it stands.
FORCE = ("kill it where it stands instead of asking it to finish — for a gateway that will not go, "
         "never one that is merely busy: it takes work away mid-flight")

#: Said out loud whenever `--force` really ended a gateway that was running, because a person who
#: typed it on the wrong agent has to be able to see that from the output alone.
WAS_KILLED = ("killed rather than asked to finish — whatever it was doing was taken away "
              "mid-flight")

#: What `Cycled` answers with when the verb behind it did not do what it was asked. Short on
#: purpose: the verb has already printed what went wrong and what that leaves, on the terminal of
#: whoever ran the command, so what is left to say is which agent and which of the two it was —
#: inside a sentence the caller is writing about that agent anyway.
WOULD_NOT = "`rundesk gateways {verb} {name}` could not, and said why in the lines above this one"

#: The same, for the one thing those verbs do not answer for themselves. See `Cycled.down`.
COULD_NOT_BE_ASKED = "`rundesk gateways {verb} {name}` could not be run at all ({why})"

#: Said out loud whenever a gateway was stopped by signalling its process instead of by taking a
#: job back, because those are two different things to have happened and only one of them means
#: launchd will not start it again.
BY_SIGNAL = "this gateway had no job, so it was stopped by signalling the process directly"

#: How long a gateway that has to be signalled directly is given to finish what it was doing.
#: **The job's own `ExitTimeOut`**, which is the window `bootout --wait` would have given it, so a
#: gateway with no job behind it is not held to a shorter standard than one with — a gateway is
#: holding somebody's work whether or not launchd ever heard of it.
GENTLY_FOR = float(job.EXIT_TIMEOUT)

#: How long the process group is given to be gone after `SIGKILL`, which is not a courtesy but the
#: time the kernel takes: a wait of zero here would report a gateway that is on its way out as one
#: that would not stop.
FIRMLY_FOR = 5.0

#: What `--force` gives it instead, and it is the whole of what `--force` means on this path: the
#: `SIGTERM` is still sent, and nothing waits to see whether it was honoured before the `SIGKILL`
#: behind it lands.
FORCED_FOR = 0.0

#: How long a gateway is given to come up on its own after launchd has taken the job. Bootstrapping
#: *is* starting — `KeepAlive {"SuccessfulExit": false}` implies `RunAtLoad` — so this is the window
#: an ordinary start comes up in, and only a gateway sitting behind a throttle needs more.
ON_ITS_OWN_SECONDS = 3.0

#: How long a gateway is given after it has been kicked past whatever throttle it was behind.
CAME_UP_SECONDS = 10.0

#: How long the name is given to come free after the job behind it was taken back. `bootout --wait`
#: has already waited out the whole of `ExitTimeOut`; this is what proves it rather than assuming it.
WENT_AWAY_SECONDS = 5.0

#: How often a wait looks again. Short enough that an ordinary start is not noticeably delayed by
#: the granularity, long enough that waiting is not spinning a core.
LOOKING_AGAIN = 0.05

#: How much of the end of a captured file is read. These two are appended to for ever — launchd
#: opens them `O_APPEND` and rotates nothing — so a crash loop makes them arbitrarily long, and
#: reading one whole to show twenty lines of it is a command that stops answering.
CAPTURED_BYTES = 65536

#: What the four sources are called in the listing, in the words each of them actually answers in.
RUNNING = "running"
UNSUPERVISED = "running, UNSUPERVISED"

#: And the same state one degree worse: a gateway whose agent is named something a launchd label
#: can never carry. `UNSUPERVISED` is a job that is not placed *yet* and a restart places it; this
#: one is a job that can never be placed at all, and no command of this product changes that while
#: the agent is named as it is. Two different facts, so two different words.
UNSUPERVISABLE = "running, NEVER SUPERVISED"

WEDGED = "running, no beat"
NOT_RUNNING = "not running"
CANNOT_TELL = "cannot tell"


class Stood(NamedTuple):
    """How one agent's gateway stands, in the four answers that are kept apart because they differ.

    `gateway` is the kernel's answer and is the one to read first; `supervised` is launchd's;
    `override` is the store that outlives every plist; `allowed` is Background Task Management's.
    No one of them can answer on its own, which is the whole reason there are four.

    `why` is the one thing worth saying about this agent, and `""` when there is nothing — an agent
    that is simply running has nothing said about it beyond the row.
    """

    name: str
    gateway: str
    supervised: str
    override: str
    allowed: str
    why: str


class Pointed(NamedTuple):
    """Which agents a verb was pointed at — or why it was not, and with which exit code.

    **The code is carried rather than decided at the call site**, because the two things that can
    go wrong here exit differently and every caller would otherwise have to know which is which.
    `named` is empty for a refusal, and empty for an install with no agents in it, which is why
    `refusal` is what a caller reads first: those two are not the same answer.
    """

    named: List[str]
    refusal: Tuple[str, ...]
    code: int

    def said(self) -> int:
        """Say the refusal, and hand back the code that says what kind of refusal it was."""
        return _wrong(self.code, *self.refusal)


class Cycled:
    """One agent's gateway, stood down and started again — what a command that must move `data/` asks.

    Handed to `commands.update` and to `commands.backups`, which is where the reasoning for wanting
    it lives: a gateway holding an agent's records open while a step rewrites them is the `database
    is locked` failure, and a restore replaces the very inode an agent's lock stands on, so a
    gateway that lived through one goes on holding a name nothing can reach. Both of those commands
    already ask `gateways.standing` which gateways are up **before anything moves**, stand exactly
    those down, and start exactly those again in a `finally`. This is the thing they were missing.

    **It satisfies `commands.update.Gateways` structurally and imports nothing of it.** A `Protocol`
    is a shape rather than a base class, so that type stays where its reasoning is kept and this
    module goes on importing nothing but `gateways`, `agents`, `core` and `utils` — two commands
    that reached into each other would be two commands neither of which could be read on its own.

    **The supervisor is required and there is no default.** `_supervisor` above may resolve one in a
    body, because somebody typing `rundesk gateways` means this machine's launchd. This is built by
    a caller, and a default here would be a real `Launchd` reached by any path that forgot to pass
    one — including a suite, in the owner's own login session, booting out jobs that keep real work
    running, with nothing going red. `tests/support.py:run_with` spends three guards on that one
    hole; the fourth is having no way to build one of these that reaches the machine by accident.

    **What comes back is one sentence and never the detail.** `_stopped_one` and `_started` are the
    verbs themselves: they print what they did, and what a failure leaves, to whoever ran the
    command, and they answer an exit code. So there is nothing left to hand back but which agent and
    which verb — and the caller is already writing a sentence about that agent, into which the
    specifics a second time would be the same failure said twice.
    """

    def __init__(self, by: job.Supervising) -> None:
        self.by = by

    def down(self, name: str) -> str:
        """Stand this agent's gateway down. `""` when it is down, else why it is not.

        **Graceful, never `--force`.** What is wanted is the name, and the gateway holding it is
        holding somebody's work: it gets the whole of its job's `ExitTimeOut` to finish, exactly as
        a person typing `rundesk gateways stop` would give it. A carry or a restore that could not
        wait that out is not one worth taking somebody's work away for.

        **A sentence and never an exception**, which is what the caller's loop needs — an update
        names the agent and goes on to the next one, and a restore starts again what it stood down
        from a `finally`, where a raise would replace whatever the restore itself had answered. So
        the two things the verb below does not word for itself are worded here: a name that reaches
        outside where agents are kept, and the filesystem underneath it failing.
        """
        try:
            went = _stopped_one(name, self.by)
        except (directory.Refused, OSError) as why:
            return COULD_NOT_BE_ASKED.format(verb="stop", name=_as_typed(name), why=why)
        return "" if went == OK else WOULD_NOT.format(verb="stop", name=_as_typed(name))

    def up(self, name: str) -> str:
        """Start this agent's gateway again. `""` when it is up, else why it is not.

        The whole resolver, which is what `_started` is: it puts the job back, enables the label
        against an override nobody remembers, and then asks the kernel whether a gateway is really
        holding the name. A start that reported a job the supervisor accepted would be this seam
        telling a restore it had left the machine as it found it when it had not.
        """
        try:
            went = _started(name, self.by)
        except (directory.Refused, OSError) as why:
            return COULD_NOT_BE_ASKED.format(verb="start", name=_as_typed(name), why=why)
        return "" if went == OK else WOULD_NOT.format(verb="start", name=_as_typed(name))


def register(sub: Subcommands) -> None:
    """Put `gateways` on the parser, with one sub-verb for each thing that happens to a gateway.

    **`--all` is an ordinary flag and the agent is optional to argparse**, so that naming neither is
    refused by the verb rather than by argparse. argparse's own `required` refuses the command line
    itself — exit `2`, in words that name a flag and do not say what to type — and this is a guard
    on an effect rather than a description of one. `agents remove --confirm` and `uninstall
    --confirm` already have that shape, and there is no reason for this to be the second one.
    """
    kept = sub.add_parser("gateways", help="the gateway that hosts each agent")
    what = kept.add_subparsers(dest="what", metavar="<what>")

    what.add_parser("list", help="every agent, and how its gateway stands")

    up = what.add_parser("start", help="start one agent's gateway, and prove it came up")
    up.add_argument("agent", metavar="<agent>", help="which one, as `rundesk agents` lists it")

    down = what.add_parser("stop", help="take one gateway's job back, or every one of them")
    down.add_argument("agent", metavar="<agent>", nargs="?", default=None,
                      help="which one — or --all, and one of the two is required")
    down.add_argument("--all", action="store_true", dest="every",
                      help="every agent on this install")
    down.add_argument("--force", action="store_true", help=FORCE)

    again = what.add_parser("restart", help="stop one gateway and start it again, or every one")
    again.add_argument("agent", metavar="<agent>", nargs="?", default=None,
                       help="which one — or --all, and one of the two is required")
    again.add_argument("--all", action="store_true", dest="every",
                       help="every agent on this install")
    again.add_argument("--force", action="store_true", help=FORCE)

    said = what.add_parser("logs", help="what one agent's gateway has been saying")
    said.add_argument("agent", metavar="<agent>", help="which one, as `rundesk agents` lists it")
    said.add_argument("-n", "--lines", metavar="<lines>", type=int, default=LINES,
                      help=f"how many lines (default: {LINES})")

    here = what.add_parser("run", help="be the gateway for one agent, in this terminal")
    here.add_argument("agent", metavar="<agent>", help="which one, as `rundesk agents` lists it")


def cmd_gateways(args: argparse.Namespace, supervising: Optional[job.Supervising] = None) -> int:
    """Answer whichever of the six was asked for; with none of them, list what there is.

    `supervising` is the machine's supervisor and is resolved **here**, in a body, rather than
    defaulted in any signature — see the module docstring for why this seam is the whole defence
    rather than a convenience.
    """
    try:
        paths.home()
    except paths.Refused as why:
        return _failed(str(why))

    what = getattr(args, "what", None)
    if what in (None, "list"):
        return _listed(_supervisor(supervising))
    if what == "start":
        return _started(args.agent, _supervisor(supervising))
    if what == "stop":
        return _stopped(args.agent, args.every, args.force, _supervisor(supervising))
    if what == "restart":
        return _restarted(args.agent, args.every, args.force, _supervisor(supervising))
    if what == "logs":
        return _said(args.agent, args.lines)
    if what == "run":
        # **Handed straight over, exit code and all.** What a gateway exits with is a conversation
        # with launchd and not with a person: under `KeepAlive {"SuccessfulExit": false}` anything
        # but `0` is a request to be restarted, so `host` reaches `0` on every refusal on purpose.
        # A check here that exited `1` for an agent that is not there would turn the one permanent
        # condition launchd cannot fix into an endless restart loop.
        return host.run(args.agent)

    # Unreachable while every sub-verb above is answered, and that is the point: one registered on
    # the parser and wired to nothing fails here loudly rather than exiting 0 having done nothing.
    raise AssertionError(f"gateways {what} is registered on the parser and answered by nothing")


def _supervisor(supervising: Optional[job.Supervising]) -> job.Supervising:
    """The machine's supervisor, resolved in a body and never bound in a signature.

    A default decided when this module was defined is one nothing can reach past — and what it
    cannot reach past here is `launchctl`, in the owner's own login session, against jobs that keep
    real work running.
    """
    return supervising if supervising is not None else job.Launchd()


def _listed(by: job.Supervising) -> int:
    """Every agent, and how its gateway stands, read from four independent places.

    Where they stand is printed even when there are none, for the reason `agents` and `backups`
    print it: "no gateways" and "no gateways *here*" are different things to learn.

    The four columns are the four sources and they are shown separately rather than collapsed into
    one word. A disabled job prints as a perfectly healthy one — `disabled` is not among the
    property words launchd renders at all — and a job the owner switched off in Login Items is gone
    from launchd entirely. One column could not say either of those without inventing a verdict
    nothing measured.

    **A listing that answered exits `0`, whatever it found.** The exit code says whether the
    question was answered, and every state below is an answer: a script running `rundesk gateways &&
    …` is asking whether the listing worked, not whether every gateway on the machine is healthy.
    What a bad state costs is the word `running`, which no row here gets unless it earned it.
    """
    at = paths.agents()
    try:
        there = directory.known()
    except OSError as why:
        return _failed(str(why), "nothing was listed")

    print(f"gateways in {at}")
    if not there:
        print("        no agents yet — add one with: "
              "rundesk agents add <agent> --provider <provider>")
        return OK

    stood = [_stood(name, by) for name in there]
    as_table(("AGENT", "GATEWAY", "JOB", "OVERRIDE", "LOGIN ITEM"),
             [(one.name, one.gateway, one.supervised, one.override, one.allowed) for one in stood])
    for one in stood:
        if one.why:
            print(f"        {one.name}: {one.why}")
    return OK


def _stood(name: str, by: job.Supervising) -> Stood:
    """Where one agent's gateway stands, asked of all four places.

    The kernel is asked first and is never overruled: a gateway that crashed, was `SIGKILL`ed or
    lost its machine reads as offline here with its record still whole on disk, and nothing launchd
    says changes that.
    """
    try:
        at = directory.where(name)
    except directory.Refused as why:
        return Stood(name, CANNOT_TELL, CANNOT_TELL, CANNOT_TELL, CANNOT_TELL, str(why))

    how = standing.standing(at)
    one, trouble = _job_for(name, at)
    if one is None:
        # A name a launchd label cannot carry never had a job and never could have one, so there is
        # nothing to ask launchd about — and the gateway may still be running, started by hand.
        #
        # **Which is exactly why this may not report plain `running`.** This branch is reached only
        # when no job can exist in any state, so a gateway found here is the least supervised one
        # there is: nothing brings it back, nothing starts it at the next login, and unlike the
        # branch below there is no restart that changes that.
        return Stood(name, _as_the_kernel_has_it(how, UNSUPERVISABLE), "cannot be placed",
                     CANNOT_TELL, CANNOT_TELL, _what_to_say_about_no_job_ever(name, how, trouble))

    stands = job.stands(one, by)
    return Stood(
        name,
        _as_the_kernel_has_it(how, UNSUPERVISED if stands.how == job.NOT_PLACED else ""),
        {job.PLACED: "placed", job.NOT_PLACED: "not placed"}.get(stands.how, CANNOT_TELL),
        {True: "disabled", False: "enabled"}.get(stands.disabled, CANNOT_TELL),
        {True: "on", False: "switched off"}.get(stands.allowed, CANNOT_TELL),
        _what_to_say_about(name, how, stands),
    )


def _as_the_kernel_has_it(how: standing.Standing, unsupervised: str) -> str:
    """What the flock said, in the words a person reads — and never one that overstates it.

    A gateway up with nothing supervising it is not written as `running`: whoever reads that word
    believes the agent is covered, and it is the one state where they are not.

    **`unsupervised` is the word rather than a flag**, because there are two of those states and
    they are told apart on the row itself: a job that is not placed yet, and one that can never be
    placed at all. A caller with nothing to say about supervision passes `""`.

    The pid comes from the record and is shown only once the lock has already said somebody is
    there — a pid read off a gateway that is gone is a number that now belongs to something else.
    """
    if how.how == standing.CANNOT_TELL:
        return CANNOT_TELL
    if how.how == standing.OFFLINE:
        return NOT_RUNNING
    if unsupervised:
        return f"{unsupervised}{_a_pid(how.pid)}"
    if how.stale:
        return f"{WEDGED}{_a_pid(how.pid)}"
    return f"{RUNNING}{_a_pid(how.pid)}"


def _what_to_say_about_no_job_ever(name: str, how: standing.Standing, trouble: str) -> str:
    """The one thing worth saying about an agent no launchd label can ever be made for.

    **Worded apart from `_what_to_say_about`, because the two facts are different.** There, a job
    that is `NOT_PLACED` is a job that has not been placed *yet*, and the sentence ends in the
    restart that places it. Here no job can be placed at all — not now and not after any command
    this product has — so offering a restart would send somebody round a loop that cannot end, and
    what they need instead is the reason and the two things that really do work: the gateway can
    still be stopped, and it can still be run in a terminal.
    """
    if how.how == standing.CANNOT_TELL:
        return f"{how.why} — this is not the same as the gateway not running"
    if how.how == standing.ONLINE:
        return (f"a gateway is holding this name and launchd can never have a job for it — "
                f"{trouble}. Nothing brings it back when it stops, nothing starts it at the next "
                f"login, and no restart changes either of those while the agent is named this. "
                f"Take it down with: rundesk gateways stop {_as_typed(name)}")
    return f"{trouble} — it can still be run in a terminal with: rundesk gateways run {_as_typed(name)}"


def _what_to_say_about(name: str, how: standing.Standing, stands: job.Stands) -> str:
    """The one thing worth saying about this agent, and what to type about it. `""` when nothing is.

    In the order somebody needs to hear them: what nobody can answer, then the state that looks like
    health and is not, then the two lockouts — the one with a command and the one without.
    """
    if how.how == standing.CANNOT_TELL:
        return f"{how.why} — this is not the same as the gateway not running"
    if how.how == standing.ONLINE and stands.how == job.NOT_PLACED:
        return ("a gateway is holding this name and launchd has no job behind it — nothing brings "
                f"it back when it stops, and nothing starts it at the next login. Run: rundesk "
                f"gateways restart {name}")
    if how.how == standing.ONLINE and how.stale:
        return (f"the gateway is up and has said nothing for {standing.WEDGED_AFTER:g} seconds — "
                f"read what it last said with: rundesk gateways logs {name}")
    if stands.disabled:
        return ("launchd's override store says this label is disabled, so the job will never "
                f"start — `rundesk gateways start {name}` enables it and puts the job back")
    if stands.allowed is False:
        return ("this machine's background item store says the owner has switched this off, and "
                "**no command of any kind puts it back**: System Settings > General > Login Items "
                "& Extensions")
    if stands.why:
        return stands.why
    if how.how == standing.OFFLINE and stands.how == job.NOT_PLACED:
        return f"not running and no job — start it with: rundesk gateways start {name}"
    return ""


def _started(name: str, by: job.Supervising) -> int:
    """Start one agent's gateway, and prove a gateway came up rather than that a job was accepted.

    The whole resolver, and it is safe to run again on any state: it rewrites the plist and the
    shim, enables the label against an override nobody remembers, boots out whatever was loaded
    under that label, bootstraps, and only then asks the kernel whether a gateway is actually
    holding the name.

    **Except on a gateway that is already running, where it does nothing at all.** Every step above
    begins with a `bootout --wait`, which ends the gateway that is up — so a start that ran the
    resolver unconditionally would take down an agent in the middle of its work in order to report
    that it was running. That is the recorded incident, and this is the guard for it.
    """
    gone_wrong = _not_an_agent(name)
    if gone_wrong:
        return _failed(gone_wrong, "see what there is with: rundesk agents", "nothing was started")

    at = directory.where(name)
    how = standing.standing(at)
    if how.how == standing.CANNOT_TELL:
        return _failed(f"nobody can tell whether a gateway is running for {name} — {how.why}",
                       "nothing was started — a second gateway started beside a first is the one "
                       "thing this must never do")

    one, trouble = _job_for(name, at)
    if one is None:
        return _no_job_can_ever_be_placed(name, trouble, "nothing was started")

    if how.how == standing.ONLINE:
        return _already_running(name, how, job.stands(one, by))

    return _resolved(name, at, one, by)


def _resolved(name: str, at: Path, one: job.Job, by: job.Supervising) -> int:
    """The resolver itself: place the job, and prove a gateway came up rather than assume one did.

    Split out of `_started` because `restart --force` runs exactly this, over a name it has just
    freed with a kill — and a second copy of it would be a second opinion about what a start
    guarantees. What `_started` keeps to itself is the guard this must not have: it refuses a
    gateway that is already up, and `--force` has just ended the gateway that was.

    Every step begins with a `bootout --wait`, which is why the guard exists at all.
    """
    landed = job.place(one, by)
    if landed.how != job.PLACED:
        return _failed(f"the job for {name} was not placed — {landed.why}", "nothing is running")
    if landed.why:
        # Placed, and with something to say about it — launchd may be holding the definition it
        # already had rather than the one just written.
        print(f"        note   {landed.why}")

    if not _came_up(at, ON_ITS_OWN_SECONDS):
        # **A kick is `kickstart -k`, and it waits out the whole `ThrottleInterval` rather than
        # getting past it** — measured 30 seconds against a throttle of 30, with the caller blocked
        # for all of it. That is why nothing here restarts with one, and why this is the only call
        # to it left in the product: it is reached only after a bootstrap that placed the job and
        # left the name unheld, which is a gateway that came up and died inside its own throttle.
        # An ordinary start never arrives here, and one that does is paying for a real wait.
        by.kick(one.label)
        if not _came_up(at, CAME_UP_SECONDS):
            return _failed(
                f"launchd took the job for {name} and no gateway came up",
                "a job the supervisor accepted is not a gateway that started.",
                f"read what it managed to say with: rundesk gateways logs {name}")

    how = standing.standing(at)
    print(f"gateway started for {name}{_as_pid(how.pid)}")
    print(f"        job    {one.label}")
    print(f"        logs   {standing.logs_at(at)}")
    return OK


def _already_running(name: str, how: standing.Standing, stands: job.Stands) -> int:
    """A start pointed at a gateway that is already up: say so, change nothing — or refuse.

    Refused in exactly one case, and it is not tidiness: a gateway holding the name with no job
    behind it will not come back, so reporting it as "already running" would tell somebody they
    were covered at the moment they were least covered. The way out of it is a restart, because the
    job can only be placed over a name that is free.
    """
    if stands.how == job.NOT_PLACED:
        return _failed(
            f"{name} is running{_as_pid(how.pid)} and launchd has no job behind it",
            "nothing brings that gateway back when it stops, and nothing starts it at the "
            "next login.",
            f"put it under launchd with: rundesk gateways restart {name}",
            "nothing was started")

    print(f"{name} is already running{_as_pid(how.pid)}")
    print("        nothing was changed — a start never kicks a gateway that is already up")
    if stands.why:
        print(f"        note   {stands.why}")
    return OK


def _stopped(name: Optional[str], every: bool, forcing: bool, by: job.Supervising) -> int:
    """Take back the job behind one gateway, or behind every one of them."""
    pointed = _which("stop", name, every)
    if pointed.refusal:
        return pointed.said()
    if not pointed.named:
        print(f"no agents in {paths.agents()} — nothing to stop")
        return OK

    worst = OK
    for one in pointed.named:
        if _stopped_one(one, by, forcing) != OK:
            worst = FAILED
    return worst


def _stopped_one(name: str, by: job.Supervising, forcing: bool = False) -> int:
    """Stop one gateway: take the job away, then prove the name came free.

    **Graceful, unless `--force`.** `job.remove` takes the job back with `bootout --wait`, which
    sends `SIGTERM` and then waits for the process to really be gone, up to the job's own
    `ExitTimeOut`. That is the default for the reason it is the default everywhere here: a gateway
    is holding somebody's work, and a stop that does not let it finish is a stop that loses some.

    **`--force` ends it first, with `kill SIGKILL`.** The `bootout --wait` that follows then returns
    at once, because there is no process left to wait for — which is the whole of what `--force`
    buys, and it buys it by taking whatever the gateway was doing away where it stood.

    **The plist goes with the job**, and that is what makes this a stop rather than a pause. At
    login, `loginwindow` bootstraps the `LaunchAgents` directories on its own — so a stop that left
    the file behind would be a stop that undid itself the next time somebody logged in, with
    nothing anywhere having said so.

    **And when there is no job to take back, the gateway is stopped anyway** — by signalling the
    process, which is the only thing left that can. Reached two ways: a name no label can carry, so
    there is nothing to ask launchd about at all, and a name still held after the job came back,
    which proves it was not launchd that started it. A stop that refused either of those would leave
    a gateway holding its agent's name with nothing in the product able to take it back.
    """
    at = directory.where(name)
    one, trouble = _job_for(name, at)
    if one is None:
        return _signalled_directly(name, at, forcing, trouble)

    was = standing.standing(at)
    had_a_job = job.plist_of(one).is_file()

    if forcing:
        _ended(one, by)

    why = job.remove(one, by)
    if why:
        return _failed(f"the job for {name} could not be taken back — {why}",
                       f"the gateway for {name} may still be running, and its job may still be "
                       "loaded")

    if not _went_away(at):
        # **The job came back cleanly and something is still holding the name**, which is the proof
        # that it was never launchd keeping it up — a job that was never bootstrapped, or a gateway
        # started by hand in a terminal. Nothing supervises it, so nothing but a signal stops it,
        # and the job it never had is exactly why there is no gentler way left.
        return _signalled_directly(
            name, at, forcing,
            "launchd took its job back and a gateway is still holding the name, so it was not "
            "launchd that started it")

    if was.how == standing.ONLINE:
        print(f"gateway stopped for {name}")
        if forcing:
            # Only where a gateway really was up. `--force` on a name nothing was holding took
            # nothing away, and saying it did would be this command overstating what it cost.
            print(f"        {WAS_KILLED}")
    elif had_a_job:
        print(f"the job for {name} was taken back — no gateway was running")
    else:
        # Stopping something that was never started is not a failure; it is the state asked for.
        print(f"{name} is not running")
        return OK
    print(f"        took   {one.label}")
    print(f"        took   {job.plist_of(one)}")
    return OK


def _restarted(name: Optional[str], every: bool, forcing: bool, by: job.Supervising) -> int:
    """Stop and start again — or, with `--force`, end it where it stands and start it now."""
    pointed = _which("restart", name, every)
    if pointed.refusal:
        return pointed.said()
    if not pointed.named:
        print(f"no agents in {paths.agents()} — nothing to restart")
        return OK

    worst = OK
    for one in pointed.named:
        went = _restarted_one(one, by, forcing)
        if went != OK:
            worst = FAILED
    return worst


def _restarted_one(name: str, by: job.Supervising, forcing: bool = False) -> int:
    """Stop, prove the old one is gone, then start. **Never the other way round.**

    **`--force` is this same cycle with a kill in front of the stop, and it was once its own
    function that skipped the proving.** That copy ran `kill SIGKILL` against the *label* and went
    straight on to bootstrap a replacement — which is correct only while launchd holds a job for
    that label. Against a gateway with no job — one started by `rundesk gateways run`, or one whose
    job was never bootstrapped, both states this command documents and points people here to fix —
    the kill reached nothing, the replacement launchd started found the name already held and stood
    down as it should, and the check that a gateway was up was then satisfied by *the original
    process*, which had never been touched. It reported killing and replacing a gateway that was
    still running, under its original pid. Measured, not reasoned about.

    Routing both through `_stopped_one` is what fixes it: that is the one place that proves the name
    came free, and the only place that falls back to signalling the process when there is no job to
    take back. `--force` still skips the *waiting* — it kills first, so the `bootout --wait` behind
    it returns at once — and now skips none of the proving, which is what it always claimed.

    A start bootstraps, and bootstrapping over a label launchd still holds keeps the definition it
    already had *without failing* — so a restart that started before the old one was proven gone
    would report a restart and go on running the old program. A stop that did not clearly work
    therefore ends the cycle here, with the gateway down and the failure said out loud, rather than
    being followed by a start that cannot mean what it says.

    **Nothing on this path can block for a throttle, and nothing on it kills.** The stop is
    `bootout --wait`, the start is `bootstrap`, and a fresh bootstrap is measured to put a new pid
    up immediately; the one call in this module that waits out a `ThrottleInterval` is the kick in
    `_resolved`, reached only by a gateway that came up and died inside its own throttle window.
    """
    if _stopped_one(name, by, forcing) != OK:
        # Said as a continuation of the stop's own failure rather than as a second one: what went
        # wrong has already been named, and what is added here is the consequence.
        print(f"        {name} was not started again — a start over a job launchd still holds "
              "keeps the definition it already had, and does not fail", file=sys.stderr)
        return FAILED

    one, _trouble = _job_for(name, directory.where(name))
    if one is None:
        # **Stopped, and it is the start that can never happen** — the agent is named something no
        # launchd label can carry. Said here rather than left to `_started`, which would answer
        # "nothing was started" and so describe a restart that did nothing at all. Half of this one
        # really happened, and the half that cannot is the failure.
        return _no_job_can_ever_be_placed(name, _trouble, "it was stopped and not started again")
    return _started(name, by)


def _ended(one: job.Job, by: job.Supervising) -> None:
    """`kill SIGKILL` — what `--force` adds, and the one call here that does not ask first.

    Answers nothing, and the two callers say why at length: a `bootout --wait` follows it in both
    of them, goes back to the same `launchctl`, and reports for itself whatever this would have
    had to report. A gateway that was already stopped is the ordinary case rather than an error —
    launchd answers `113` for a label it has no record of, and `--force` on something already down
    is a request for the state it is already in.
    """
    by.end(one.label)


def _signalled_directly(name: str, at: Path, forcing: bool, why_there_is_no_job: str) -> int:
    """Stop a gateway nothing supervises, by signalling the process itself. The last thing that can.

    **`utils.programs.stop` and not a `kill` written here.** It signals the process *group*, so what
    the gateway started stops with it rather than being orphaned with nothing left holding its ids;
    it asks with `SIGTERM` before it insists with `SIGKILL`; and it refuses a pid of `1` or less and
    a group that is this command's own, which is what stands between a reused pid and a command that
    kills itself mid-sentence. Every one of those was already built and tested there.

    **The pid is read here, from `standing`, and never carried in from a caller.** `standing` hands
    one back only while the lock says a gateway is holding the name — a pid off a record whose
    process is gone is a number that now belongs to something else, and this is the one function in
    the product that would signal it.

    Three answers, and the middle one is not a failure: a gateway that is not running is the state
    that was asked for, and a stop that reported an error for it would make `stop` unsafe to run
    twice.

    **What the signal answered is not what decides this. The lock is.** The same rule `_stopped_one`
    holds to for `launchctl kill`, and here it is not a preference: measured on this machine
    2026-08-05, `killpg` against the group of a process that has just become a **zombie** answers
    `EPERM` on macOS rather than `ESRCH`, so a gateway that took the `SIGTERM` and died in the
    instant before the `SIGKILL` behind it has that `SIGKILL` refused — and `utils.programs.stop`
    reports a program it really did stop as one that would not go. Asking the kernel whether the
    name came free settles it either way, and it is the same question `_went_away` asks after a
    `bootout`.
    """
    how = standing.standing(at)
    if how.how == standing.CANNOT_TELL:
        return _failed(f"nobody can tell whether a gateway is running for {name} — {how.why}",
                       "there is no job to take it back, and nothing may be signalled on a guess",
                       "nothing was stopped")
    if how.how != standing.ONLINE:
        # Nothing is holding the name, and there was no job to take back either — so there is
        # nothing here to stop, which is the state that was asked for.
        print(f"{name} is not running")
        return OK
    if how.pid is None:
        return _failed(
            f"a gateway is holding {name} and nothing readable says which process it is",
            f"there is no job to take back and no pid in {at / standing.RECORD}, so nothing here "
            "can reach it — find it with: ps -axo pid,command | grep rundesk",
            "nothing was stopped")

    trouble = programs.stop(how.pid, FORCED_FOR if forcing else GENTLY_FOR, FIRMLY_FOR)
    if not _went_away(at):
        went_wrong = f"the gateway holding {name} could not be stopped"
        return _failed(f"{went_wrong} — {trouble}" if trouble else went_wrong,
                       f"it is still holding the name{_as_pid(how.pid)}", "nothing was stopped")

    print(f"gateway stopped for {name}{_as_pid(how.pid)}")
    print(f"        {BY_SIGNAL}")
    print(f"        why    {why_there_is_no_job}")
    if forcing:
        print(f"        {WAS_KILLED}")
    return OK


def _no_job_can_ever_be_placed(name: str, trouble: str, and_so: str) -> int:
    """Refuse a start for a name launchd can never carry, and say what still works instead.

    **Never a restart, which is what the refusal beside this one offers.** A job that is not placed
    is placed by running the resolver again; this one cannot be placed by running anything, so the
    only two true things left are that the gateway can be run in a terminal, and that an agent named
    inside `job.IN_A_LABEL` is one launchd can host.
    """
    return _failed(trouble,
                   f"no command puts it under launchd while it is named this — but a gateway for "
                   f"it can still be run in this terminal with: rundesk gateways "
                   f"run {_as_typed(name)}",
                   and_so)


def _as_typed(name: str) -> str:
    """One agent's name as somebody would have to type it, quoted only when it needs to be.

    Every command this module prints is meant to be pasted, and the names that reach these
    particular sentences are exactly the ones a shell would take apart: an agent called `my agent`
    is two arguments unless it is quoted, and a suggestion that does not work is worse than none.
    """
    return shlex.quote(name)


def _said(name: str, lines: int) -> int:
    """What this agent's gateway has been saying — lines, none yet, or could not be read.

    Three answers and never two. An empty list handed back for a directory nobody may read is a
    report of a quiet gateway, and whoever reads that goes looking in entirely the wrong place.

    **What the supervisor caught is shown every time, and not only when the day log is empty.**
    It was shown only then, and that made it unreachable in practice: a gateway writes `gateway up
    for …` as its first act after claiming the lock and `logs.tail` walks backwards across the day
    files, so one successful start anywhere in the retained window meant the fallback never fired
    again. The incident is a gateway that started, wrote its `up` line, and died inside its throttle
    window on an uncaught exception — and `gateways logs` showed the `up` line and nothing else,
    while the traceback sat in `gateway.err`.

    They are two orthogonal facts about one gateway: what it wrote, and what the machine's
    supervisor caught around it. Both are bounded reads, both are labelled with the file they came
    from, and whichever is genuinely empty says so — because *nothing yet* and *nobody could tell*
    are not the same answer, and neither is *I did not look*.
    """
    gone_wrong = _not_an_agent(name)
    if gone_wrong:
        return _failed(gone_wrong, "see what there is with: rundesk agents", "nothing was read")
    if lines < 1:
        # Refused rather than answered with nothing. `logs.tail` hands back an empty list for a
        # count of zero, which is indistinguishable here from a gateway that has never said a word.
        #
        # **`USAGE`, because argparse already exits `2` for `-n lots`.** One flag answering `2` for
        # a value that is not a number and `1` for a value that is not a count is the same mistake
        # reported two ways, and neither the person nor the script reading it can tell why.
        return _mistyped(f"{lines} is not a number of lines to show",
                         f"ask for at least one: rundesk gateways logs {name} -n {LINES}",
                         "nothing was read")

    at = directory.where(name)
    where = standing.logs_at(at)
    said = logs.tail(where, lines)

    print(f"logs for {name} in {where}")
    if said.how == logs.UNREADABLE:
        return _failed(said.why, "nothing was read")

    print(f"        what {name}'s own gateway wrote, in {where}:")
    for line in said.lines:
        print(line)
    if not said.lines:
        print(f"        nothing has been written by {name}'s own gateway yet")
    return _what_the_supervisor_caught(at, lines, bool(said.lines))


def _what_the_supervisor_caught(at: Path, lines: int, wrote_its_own: bool) -> int:
    """The end of `gateway.out` and `gateway.err`, which launchd wrote and this product never does.

    Both, not only the erroring one: the very first thing a gateway does is write one line to
    standard output saying what pid it is, and a refusal it decided for itself is said there too.
    An empty `gateway.out` beside a job launchd says has run is the signal that the failure is
    upstream of this product entirely, and belongs in the unified log.

    **`wrote_its_own` decides only the last sentence, and it decides a real difference.** A gateway
    that said nothing anywhere may never have started at all, and the unified log is then the one
    place left to look; a gateway with a log of its own and quiet capture files is the ordinary
    healthy shape, and sending somebody to `log show` for it is sending them nowhere.
    """
    caught = standing.captured(at)
    empty = True
    for one in caught:
        how, said = _the_end_of(one, lines)
        if how == logs.UNREADABLE:
            print(f"        {one} could not be read ({said[0] if said else ''})")
            empty = False
            continue
        if not said:
            continue
        empty = False
        print(f"        what the supervisor caught in {one}:")
        for line in said:
            print(f"        {line}")

    if empty and wrote_its_own:
        print(f"        the supervisor caught nothing in {caught[0].name} or {caught[1].name} — "
              "everything above is the gateway's own log")
    elif empty:
        print("        and the supervisor caught nothing either — a gateway that never started at "
              "all leaves its only account in the unified log:")
        print("        log show --last 10m --predicate 'process == \"launchd\" OR "
              "process == \"xpcproxy\"' --style compact")
    return OK


def _the_end_of(one: Path, lines: int) -> Tuple[str, List[str]]:
    """The last `lines` of one captured file, and which of the three answers reading it was.

    **Not `utils.logs.tail`**, which walks the day files a program wrote through `utils.logs`. These
    two are not day files and nothing in this product writes them: launchd opens them `O_APPEND`,
    never truncates them and never rotates them, so a crash loop appends another traceback to the
    same file for ever. Only the end of it is read, for that reason.
    """
    try:
        with open(one, "rb") as reading:
            reading.seek(0, os.SEEK_END)
            standing_at = reading.tell()
            reading.seek(max(0, standing_at - CAPTURED_BYTES))
            held = reading.read()
    except (FileNotFoundError, NotADirectoryError):
        return logs.NOTHING_YET, []
    except OSError as why:
        return logs.UNREADABLE, [str(why)]
    return logs.READ, held.decode("utf-8", "replace").splitlines()[-lines:]


def _which(verb: str, name: Optional[str], every: bool) -> Pointed:
    """Which agents this verb was pointed at: one named, or all of them.

    **One of the two, and never both and never neither.** The build this replaces let a bare
    `restart` mean every agent, and it took down every gateway somebody had — so a verb with
    nothing to point it at refuses, shows both spellings, and changes nothing.

    **Those two refusals exit `2` and the other two exit `1`**, and `Pointed` carries which because
    they are different kinds of wrong. Naming neither, or naming both, is the command line itself
    being wrong — the same thing argparse exits `2` for when a sub-verb is spelled wrongly. An agent
    that is not on this install, or an agents directory nobody can read, is a command line that was
    right and could not be carried out.
    """
    if name and every:
        return Pointed([], (
            f"{verb} was given both {name} and --all, which are two different operations",
            f"one:   rundesk gateways {verb} {name}",
            f"every: rundesk gateways {verb} --all",
            "nothing was changed"), USAGE)
    if not name and not every:
        return Pointed([], (
            f"{verb} was not told which gateway",
            f"one:   rundesk gateways {verb} <agent>",
            f"every: rundesk gateways {verb} --all",
            "nothing was changed"), USAGE)
    if name:
        gone_wrong = _not_an_agent(name)
        if gone_wrong:
            return Pointed([], (gone_wrong, "see what there is with: rundesk agents",
                                "nothing was changed"), FAILED)
        return Pointed([name], (), OK)
    try:
        return Pointed(directory.known(), (), OK)
    except OSError as why:
        return Pointed([], (str(why), "nothing was changed"), FAILED)


def _job_for(name: str, at: Path) -> Tuple[Optional[job.Job], str]:
    """This install's job for one agent, or why there can never be one. `(job, "")` when there can.

    The label is derived from the resolved root, so a scratch install and a real one cannot reach
    each other's jobs — and an agent whose name a launchd label cannot carry is refused here rather
    than acted on, because such a label could never have its disable state persisted and so could
    never be enabled again after anything disabled it.
    """
    try:
        return job.job(name, at, paths.home()), ""
    except (job.Refused, paths.Refused) as why:
        return None, str(why)


def _came_up(at: Path, patience: float) -> bool:
    """Whether a gateway is holding the name within `patience` seconds. Asked, never slept through.

    A guessed sleep is wrong in both directions: long enough for the slowest machine is a start that
    takes seconds to say what it already knows, and short enough to feel quick is a start that
    reports a failure on a loaded laptop. An ordinary start is through this in a fraction of a
    second.
    """
    return _waited_for(at, standing.ONLINE, patience)


def _went_away(at: Path) -> bool:
    """Whether the name came free within `WENT_AWAY_SECONDS`.

    `bootout --wait` has already waited for the process, and this proves it rather than trusting
    it: without `--wait` a bootout **reports success while the label is still registered and the
    process still running**, measured on a real gateway, and a build that read rc 0 as "it is gone"
    ended with no job at all.
    """
    return _waited_for(at, standing.OFFLINE, WENT_AWAY_SECONDS)


def _waited_for(at: Path, wanted: str, patience: float) -> bool:
    """Ask the kernel until it answers `wanted`, up to a ceiling. Asked once when there is none."""
    ceiling = time.monotonic() + patience
    while True:
        if standing.standing(at).how == wanted:
            return True
        if time.monotonic() >= ceiling:
            return False
        time.sleep(LOOKING_AGAIN)


def _not_an_agent(name: str) -> str:
    """Why this name is not an agent on this install, or `""` when it is.

    Asked of `directory.known`, which is the one answer to what an agent is — a directory holding
    `state.db`. A check written against the directory merely existing would accept a half-made one,
    and a gateway hosting one of those is a gateway with nothing to host.
    """
    try:
        there = directory.known()
    except OSError as why:
        return str(why)
    if name in there:
        return ""
    return f"{name} is not an agent on this install"


def _as_pid(pid: Optional[int]) -> str:
    """` as pid N`, or nothing at all when the gateway had nothing readable to say about itself."""
    return f" as pid {pid}" if pid else ""


def _a_pid(pid: Optional[int]) -> str:
    """` (pid N)`, the same answer in the shape a column carries it."""
    return f" (pid {pid})" if pid else ""


def _failed(why: str, *and_so: str) -> int:
    """Say what went wrong, and what that leaves — never one without the other. Exits `1`."""
    return _wrong(FAILED, why, *and_so)


def _mistyped(why: str, *and_so: str) -> int:
    """The same, for a command line that was itself wrong — which exits `2` and not `1`.

    `docs/commands.md`'s table promises `2` for *the command line itself was wrong*, and argparse
    already exits `2` here for a sub-verb spelled wrongly, a flag this verb does not have, and an
    `-n` that is not a number. **A guard written by hand rather than left to argparse must not
    answer a different number for the same kind of mistake**, and two of them did: naming neither a
    gateway nor `--all`, and naming both, exited `1` — so a script reading the code was told the
    gateway would not stop, when what had happened is that nobody said which gateway.

    They are refused here rather than by argparse's own `required` because that refuses in words
    that name a flag and do not say what to type, and because this is a guard on an effect —
    `agents remove --confirm` and `uninstall --confirm` have the same shape. That is a reason to
    word the refusal ourselves. It was never a reason to renumber it.
    """
    return _wrong(USAGE, why, *and_so)


def _wrong(code: int, why: str, *and_so: str) -> int:
    """The mechanics both of those share: one first line, what it leaves under it, and a code."""
    failed(f"gateways: FAILED — {why}", *and_so)
    return code
