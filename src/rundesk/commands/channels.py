"""How an agent is reached, and the seven things anybody does with a channel.

`rundesk channels` on its own lists every one there is, the way `agents`, `gateways` and `schedules`
do, because listing is what somebody wants nine times in ten. The other six are named: `add`, `show`,
`configure`, `test`, `remove` and `doctor` — and `list`, which is the bare verb said out loud, so
that naming one agent is spelled the way naming one of anything else is.

This decides only how a person types it and what they are shown. What a channel *is* belongs to
`channels.kept`, the program behind one belongs to `channels.adapters`, and whether one is connected
right now belongs to `channels.hosting` — and nothing here reaches past them to a database, a lock or
a child process.

## A channel is a connection, not a place

The channel **is** its adapter, so there is nothing to name and nothing to disambiguate: `add alan
discord` gives alan a channel called `discord`, and that one connection carries private messages and
every room the bot was invited to. One list of ids says who may reach the agent and it says so
wherever they say it — which is why `--allow` is repeatable and why an empty one is refused rather
than read as "anybody".

**`--allow` is required by the verb rather than by argparse**, the same decision `--provider` and
`--confirm` already carry: argparse's own refusal names a flag and does not say what to type, and
this guards an effect rather than describing one. An agent connected to a platform with nobody
allowed is an agent that answers no one, and being told *"the following arguments are required:
--allow"* does not tell somebody whose id to go and find.

## Nothing about a channel is written down until the adapter says it reached something

`add` resolves the adapter, asks it offline what it can do, asks it to connect, and writes the row
only once `--check` has come back `ok`. An agent whose channel is misconfigured has to find that out
while somebody is standing at a terminal, not at three in the morning when they ask it something.

The one thing that *is* written before then is the credential itself, and deliberately: somebody who
has just pasted a bot token into a prompt should not have to paste it again because the connection
was refused for an unrelated reason. `rundesk env unset <name>` empties it.

## The env name a credential is kept under is recorded, and never re-derived

What comes back from `--check` is the name the adapter reads its credential from, and that name is
written into the channel's record exactly as it arrived. `channels.hosting` hands the adapter each
recorded name back with its value under that same name, so the recorded name and the name the
adapter looks in are one fact — a name worked out a second time, anywhere, is a channel that passes
`--check` and finds nothing when it is hosted.

**Where the value is *kept* is the agent's own, though, and that is `channels.credentials`.** One
bot is one identity, so two agents behind one token are one presence that answers twice and cannot
be told apart. A value is kept under `DISCORD_BOT_TOKEN__ALAN` — the profile convention
`skills.needs` already uses, on a name `rundesk env set` already accepts — and **a plain
`DISCORD_BOT_TOKEN` is not read at all**. There is no fallback and no second name to try.

Two refusals follow from that and both are said here rather than discovered later. An agent whose
name cannot carry a credential — folding `a-b` and `a_b` would make them one bot — is refused by
`add` **before anything is typed**, because prompting for a value nothing will ever read is worse
than saying so. And a channel whose scoped name holds nothing is `BLOCKED`, where the release before
this would have quietly connected it on the shared value.

Every verb here reads that through the one module, so what `add` writes, what `show` and `test`
describe, what `doctor` calls blocked and what a gateway really starts an adapter with are one
answer. **No value is printed by any of them** — only which name holds it.

## What leaves this machine arrives as an argument

`reaching` is what runs an adapter, and it is resolved **inside** the body rather than bound in a
signature. It has no stand-in of its own, exactly as `asking` and `fetching` have none: a case that
forgets it gets the real thing, and the real thing reaching Discord fails against the closed proxy
the suite runs behind rather than passing quietly on somebody's laptop.

**No value is ever printed.** The credential is read from the terminal without echoing, handed to the
adapter by name, and described only ever as set or not set — `commands.env` says why at length.
"""

import argparse
import json
import shlex
import sqlite3
import sys
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple

from rundesk.agents import directory, migration, records
from rundesk.channels import adapters, credentials, hosting, kept
from rundesk.commands import Subcommands, as_written, env, failed
from rundesk.core import paths, secrets
from rundesk.exits import FAILED, OK
from rundesk.utils import files, locking, programs
from rundesk.utils.terminal import NOTHING, as_table

#: What runs an adapter. Handed in so that no case here reaches a platform by forgetting it, and
#: **with no default of its own** — see the module docstring on why that is the same decision
#: `asking` and `fetching` already carry rather than a different one.
Reaching = Callable[..., programs.Ran]

#: Everything a verb here can be stopped by. One tuple, because eight verbs catch the same set and
#: eight copies of it is seven chances for one to fall behind.
#:
#: Spelled out rather than caught as `Exception`, because these are different situations: something
#: that may not be done to a channel, no program behind one, records that are not there or cannot be
#: understood, an agent whose name reaches outside where agents are kept, a migration that has not
#: run, a credential store that will not answer, the install lock held by something else, and the
#: ordinary failures of a disk.
TROUBLE = (kept.Refused, adapters.NotRunnable, directory.Refused, records.NotThere,
           records.Unreadable, records.Refused, migration.Ahead, migration.Broken,
           secrets.Refused, secrets.Stuck, locking.Stuck, OSError, sqlite3.Error)

#: What `doctor` can say about one channel, one word per thing there is to do about it.
READY = "READY"
BLOCKED = "BLOCKED"
UNREACHABLE = "UNREACHABLE"
DANGLING = "DANGLING"
#: A channel whose adapter answers every question here correctly and which the gateway hosting it has
#: stopped trying to start. **The one verdict that cannot be reached by asking the adapter**, because
#: `doctor` asks it in a process of its own: a failure that shows itself only at `serve` time leaves
#: every check below satisfied, and this said `READY` for a channel that had been abandoned for hours.
GIVEN_UP = "GIVEN UP"

#: What a listing says about a channel nothing is hosting, and about one nobody could ask about.
NOT_CONNECTED = "not connected"
CANNOT_TELL = "cannot tell"

#: What it says about one a gateway has stopped trying to start. **Apart from `NOT_CONNECTED`,
#: because only one of the two is somebody's to act on**: no gateway at all, a gateway that has not
#: reached this channel yet, and a ten-second hold-off are all conditions that pass on their own,
#: and this one never does.
GAVE_UP = "given up"


class Found(NamedTuple):
    """What `doctor` made of one channel: the verdict, why, and the one command that answers it.

    `fix` is `""` where there is nothing to type. Not every verdict has a command behind it, and a
    heading reading "2 of 3 cannot be used:" with nothing under it reads like output that went
    missing — `skills doctor` writes the same rule down.
    """

    agent: str
    kind: str
    verdict: str
    said: str
    fix: str


def register(sub: Subcommands) -> None:
    """Put `channels` on the parser, one sub-verb for each thing that happens to a channel.

    **Nothing here is `required=True`, including `--allow` and `--confirm`.** argparse's own refusal
    is a usage error naming a flag, and neither of these is a value the command needs in order to
    work: one stands between an agent and answering nobody, the other between a person and a
    connection they would have to set up again. Both are guards on an effect, so the verb refuses
    instead, in a sentence ending with the whole command to run.

    **`--with` takes one string and never reaches a shell**, exactly as `schedules --run` does and
    for the same reason: it is split into words the way a shell would split them and handed to the
    adapter as a list, so nothing in it is globbed, expanded, or read as `;`, `&&` or a redirection.
    Rundesk parses none of what is in it and has no list of what any platform wants — what comes back
    in `settings` is the adapter's own normalised account, which is what an owner will still be
    running on in a year.

    It is a flag rather than a bare `--` passthrough, and that is argparse rather than taste:
    argparse matches positionals in contiguous runs, so `add <agent> <adapter> --allow <id> --
    <opts>` puts a flag between the two runs and the words after `--` are then matched against no
    positional at all — `unrecognized arguments`, exit `2`, on the most natural spelling there is.
    A flag parses in every order, and this product already had the same problem and the same answer.
    """
    said = sub.add_parser("channels", help="how each agent is reached, and how it reaches back")
    what = said.add_subparsers(dest="what", metavar="<what>")

    every = what.add_parser("list", help="one agent's channels, or every agent's")
    every.add_argument("agent", metavar="<agent>", nargs="?", default=None,
                       help="which agent — with none, every agent on this install")

    new = what.add_parser("add", help="connect an agent to a platform")
    _named(new)
    new.add_argument("--allow", metavar="<id>", action="append", default=[],
                     help="required — an id that may reach this agent here, as that platform writes "
                          "it; say it again for each person. `place:<id>` allows anybody in one "
                          "place on that platform, and `sender:<id>` is the plain form said out loud")
    new.add_argument("--notify", action="store_true",
                     help="make this the channel unprompted things go to")
    new.add_argument("--with", dest="options", metavar="<adapter opts>", default="",
                     help="anything the adapter itself takes, as one quoted string — rundesk parses "
                          "none of it and it never reaches a shell")

    shown = what.add_parser("show", help="everything one channel was given")
    _named(shown)

    changed = what.add_parser("configure", help="change who may reach an agent here, or what is told")
    _named(changed)
    changed.add_argument("--allow", metavar="<id>", action="append", default=[],
                         help="somebody else who may reach this agent here, or `place:<id>` for "
                              "anybody in one place on that platform")
    changed.add_argument("--deny", metavar="<id>", action="append", default=[],
                         help="somebody, or a place, that may no longer — written exactly as it "
                              "stands on the list")
    changed.add_argument("--notify", action="store_true",
                         help="make this the channel unprompted things go to")

    tried = what.add_parser("test", help="ask the adapter to connect again, and say what it reached")
    _named(tried)

    gone = what.add_parser("remove", help="take a channel away")
    _named(gone)
    gone.add_argument("--confirm", action="store_true",
                      help="required — without it, nothing is taken")

    checked = what.add_parser("doctor", help="what cannot be used, and exactly why")
    checked.add_argument("agent", metavar="<agent>", nargs="?", default=None,
                         help="whose channels to check; without one, every agent's")


def _named(one: argparse.ArgumentParser) -> None:
    """The two positionals every sub-verb but `list` and `doctor` takes.

    A channel is addressed by its platform because a channel *is* its platform — there is one Discord
    connection per agent, so the adapter's name is the channel's name and there is nothing to invent.
    """
    one.add_argument("agent", metavar="<agent>", help="which agent, as `rundesk agents` lists it")
    one.add_argument("adapter", metavar="<adapter>",
                     help="which platform — the adapter's own name, which is the channel's name")


def cmd_channels(args: argparse.Namespace, reaching: Optional[Reaching] = None) -> int:
    """Answer whichever of the seven was asked for; with none of them, list what there is.

    `reaching` is the one thing here that leaves the machine, resolved inside the body rather than
    bound in the signature so that the whole group is driven against a program on disk instead of
    against somebody else's uptime.
    """
    try:
        paths.home()
    except paths.Refused as why:
        return _failed(str(why))

    what = getattr(args, "what", None)
    if what in (None, "list"):
        return _listed(getattr(args, "agent", None))
    if what == "add":
        return _added(args, reaching)
    if what == "show":
        return _shown(args.agent, args.adapter)
    if what == "configure":
        return _configured(args)
    if what == "test":
        return _tested(args.agent, args.adapter, reaching)
    if what == "remove":
        return _removed(args.agent, args.adapter, args.confirm)
    if what == "doctor":
        return _doctored(args.agent, reaching)

    # Unreachable while every sub-verb above is answered, and that is the point: one registered on
    # the parser and wired to nothing fails here loudly rather than exiting 0 having done nothing.
    raise AssertionError(f"channels {what} is registered on the parser and answered by nothing")


def allow_trouble(said: Sequence[str], typed: str) -> str:
    """Why this is not a list of people who may reach an agent, or `""` when it is.

    **Required by the verb, and the sentence ends in the whole command to type.** An empty list
    authorises nobody rather than everybody — `channels.kept` refuses one at the records and this
    refuses it earlier, in words about what somebody typed rather than about a constraint they have
    never seen.

    Nothing said and nothing *in* what was said are different mistakes with different sentences: one
    is a flag left off, the other is almost always a shell variable that was never set, which is
    exactly the case where being told to type the flag again does not help.
    """
    if not said:
        return ("nothing said who may reach this agent — a channel with an empty list answers "
                f"nobody, so say at least your own id with: {typed} --allow <id>")
    blank = [one for one in said if not one.strip()]
    if blank:
        return ("an id with nothing in it is not one — that is usually a shell variable that was "
                f"never set, so say it plainly with: {typed} --allow <id>")
    return typed_trouble(said, typed)


def typed_trouble(said: Sequence[str], typed: str) -> str:
    """Why one of these names nothing, or `""` when each names something.

    **`sender:` with nothing after it is refused where somebody can still see the sentence.**
    `channels.kept` drops such an entry when it reads the list, which is the right thing to do to a
    row that already holds one and the wrong thing to do to a command somebody is standing at a
    terminal typing: they would be told the channel was configured and find it answered nobody.
    """
    for one in said:
        kind, marked, named = one.strip().partition(kept.AS)
        if marked and kind in kept.TYPED and not named:
            return (f"{one.strip()!r} names no {kind} — say which one, as that platform writes it: "
                    f"{typed} --allow {kind}{kept.AS}<id>")
    return ""


def options_trouble(said: str, typed: str) -> str:
    """Why what was given to `--with` is not an adapter's options, or `""` when it is.

    An unbalanced quote is the only way this goes wrong, and it goes wrong **silently**: `shlex`
    hands back nothing at all, which is indistinguishable here from having said nothing — so the
    adapter would be asked its question with none of what somebody meant to point it at, and would
    answer perfectly well about a connection they had not described.
    """
    if not said.strip():
        return ""
    try:
        shlex.split(said)
    except ValueError as why:
        return (f"{said!r} could not be read as an adapter's options ({why}) — check the quoting, "
                f"and say all of it as one quoted string: {typed} --with '<adapter opts>'")
    return ""


def _words(said: str) -> List[str]:
    """What was given to `--with`, as the list an adapter is handed. **Never through a shell.**

    Split the way a shell would word-split it, so an owner writing `--with '--room 9930'` gets the
    two words they meant — and then handed to the adapter as a list, so nothing in it is globbed,
    expanded, or read as `;`, `&&` or a redirection. `schedules.firing.argv_of` says the same thing
    about a schedule's program, and is deliberately not reused: reaching into the schedules layer to
    split a string would be a command group importing a sibling's private reasoning to get at
    `shlex`.
    """
    return shlex.split(said) if said.strip() else []


def change_trouble(add: Sequence[str], remove: Sequence[str], notify: bool, typed: str) -> str:
    """Why this is not a change anybody could make to a channel, or `""` when it is.

    **Naming nothing to change is refused rather than reported as a success**, the decision `agents
    configure` and `schedules update` already make: a command that says it worked having changed
    nothing teaches somebody it worked, and the next thing they do rests on a change that never
    happened.

    One id named on both sides is refused before anything is written, because `kept.allowing` applies
    the removals first and would answer that it had done exactly what was asked — leaving somebody
    believing they had taken access away from a person who still has it.
    """
    if not add and not remove and not notify:
        return (f"nothing was named to change about this channel — change who may reach it with: "
                f"{typed} --allow <id>")
    blank = [one for one in list(add) + list(remove) if not one.strip()]
    if blank:
        return ("an id with nothing in it is not one — that is usually a shell variable that was "
                f"never set, so say it plainly with: {typed} --allow <id>")
    both = sorted(set(add) & set(remove))
    if both:
        return (f"{both[0]} was named both to allow and to deny, which are two different "
                "operations — say one of them, not both")
    return typed_trouble(list(add) + list(remove), typed)


def _listed(agent: Optional[str]) -> int:
    """Every channel there is, or one agent's, and how each one stands.

    Where they are kept is printed even when there are none, for the reason `agents` prints it: "no
    channels" and "no channels *for this agent*" are different things to learn, and somebody looking
    at the wrong install needs to see which directory was just found empty.

    An agent whose channels cannot be read is listed saying so rather than left out. Leaving it out
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

    print(f"channels for {agent}" if agent else f"channels in {paths.agents()}")
    rows: List[Tuple[str, ...]] = []
    for name in names:
        rows.extend(_rows_for(name, showing_who=agent is None))
    if not rows:
        print("        nothing is connected yet — connect one with: rundesk channels add "
              "<agent> <adapter> --allow <id>")
        return OK
    head = ("CHANNEL", "REACHES", "ALLOWED", "TOLD", "STANDING")
    as_table(("AGENT", *head) if agent is None else head, rows)
    return OK


def _rows_for(agent: str, showing_who: bool) -> List[Tuple[str, ...]]:
    """One agent's channels as lines of a table, or one line saying why they could not be read."""
    try:
        found = kept.all(agent)
    except TROUBLE as why:
        return [((agent,) if showing_who else ()) + ("?", f"cannot be read — {why}", "?", "?", "?")]

    rows = []
    for row in found:
        kind = str(row.get("kind") or "")
        rows.append(((agent,) if showing_who else ())
                    + (kind, str(row.get("describes") or NOTHING), _who_many(row),
                       as_written(bool(row.get("notified"))), _how(agent, kind)))
    return rows


def _who_many(row: Dict[str, Any]) -> str:
    """How many entries are on this channel's allow list, or that the list cannot be read.

    **Entries, and not people.** One `place:` entry admits everybody the platform reports as being
    there, so a count of people is not something this column could ever answer — `channels show`
    prints the entries themselves, which is where the difference is visible. Saying `1` for a channel
    a whole room can reach is the honest shape of a column that counts what was written down.

    A list nobody can read is never shown as zero: an empty one authorises nobody, so a column that
    said `0` for a column that is merely unreadable would report a channel as switched off when it
    may be working perfectly.
    """
    try:
        return str(len(kept.who_may_reach(row)))
    except TROUBLE:
        return "?"


def _how(agent: str, kind: str) -> str:
    """How one channel stands, asked of the kernel through the lock and never of the record.

    **The lock first, the record only after** — the rule `gateways` already keeps. A record holds a
    pid, and a pid whose process is gone is a number that now belongs to something else; the claim an
    adapter holds is dropped by the kernel however the adapter ended, so it is the only thing that
    answers whether one is really there.

    `cannot tell` is a first-class answer. `hosting.still_running` deliberately re-raises anything
    that is not ordinary contention, so a permissions failure or a filesystem that will not lock
    would otherwise read as a channel that is connected — which is a claim nothing has made.

    **And `given up` is the other one.** `not connected` covered four different conditions and only
    the last of them is somebody's to act on: no gateway, a gateway that has not reached this channel
    yet, a channel inside its hold-off, and one this gateway will never start again. Asked only once
    the lock has said nothing is there, because an adapter that is running is the answer whatever a
    previous gateway left behind.
    """
    try:
        if not hosting.still_running(agent, kind):
            gave_up = hosting.will_not_start(agent, kind)
            return f"{GAVE_UP} — {gave_up}" if gave_up else NOT_CONNECTED
    except OSError as why:
        return f"{CANNOT_TELL} — {why}"
    return f"connected{_a_pid(_recorded_pid(agent, kind))}"


def _recorded_pid(agent: str, kind: str) -> Optional[int]:
    """Which process an adapter said it was, read only once the lock has said one is there."""
    how, said = files.read_json(hosting.record_of(agent, kind))
    if how != files.READ or not isinstance(said, dict):
        return None
    return programs.a_pid(said.get("pid"))


def _a_pid(pid: Optional[int]) -> str:
    """` (pid N)`, or nothing when the adapter had nothing readable to say about itself."""
    return f" (pid {pid})" if pid else ""


def _added(args: argparse.Namespace, reaching: Optional[Reaching]) -> int:
    """Connect an agent to a platform, or refuse having written nothing down.

    In the order the module docstring gives, and the order is the whole of it: the flags are checked,
    the agent is checked, the program is found, it is asked offline what it can do, it is asked to
    connect, and only an `ok` from that last question writes a row.
    """
    typed = f"rundesk channels add {args.agent} {args.adapter}"
    trouble = allow_trouble(args.allow, typed) or options_trouble(args.options, typed)
    if trouble:
        return _failed(trouble, "nothing was added")

    gone_wrong = directory.not_an_agent(args.agent)
    if gone_wrong:
        return _failed(gone_wrong, "see what there is with: rundesk agents", "nothing was added")

    try:
        adapters.where(args.adapter)
        # Asked before anything connects and with no credential anywhere near it, so that a fidelity
        # difference is a fact rather than a guess.
        #
        # **Printed here and kept nowhere**, and this said otherwise for a while — it claimed the
        # answer was written into the record, which is a mechanism that does not exist: `values`
        # below has no such key, the `channels` table has no column, and `kept.SETTABLE` names none.
        # The one capability anything reads is `max_text`, and it is read out of `settings`, where a
        # `--check` may put it. `docs/extending/adapters.md` says so under *what is not built yet*; a docstring
        # asserting the opposite is worse than the gap, because nobody re-checks it.
        able = adapters.capabilities(args.adapter, reaching)
    except TROUBLE as why:
        return _failed(str(why), "nothing was added")

    said, wanted, trouble = _reached(args.agent, args.adapter, args.allow, _words(args.options),
                                     reaching)
    if trouble:
        return _failed(trouble, "nothing was added")
    if not said.ok:
        return _failed(said.why,
                       "nothing was added — a channel is written down only once its adapter says it "
                       "reached something")

    values = {
        "describes": said.describes,
        "notify_place": said.notify_place,
        "settings": said.settings,
        # **The final answer's names, falling back to the ones just filled in.** An adapter that
        # names its credential on the refusal and not on the success is not making a mistake, and
        # recording nothing there would leave a channel whose token is kept on this install and
        # handed to nobody — a channel that passes `--check` and cannot be hosted.
        "secret_names": json.dumps(said.secret_names or wanted),
        "allowed": json.dumps(list(args.allow)),
    }

    marked = ""
    try:
        with locking.only_one(paths.lock(), "this install", locking.WHILE_A_DIRECTORY_MOVES):
            kept.added(args.agent, args.adapter, values)
            if args.notify:
                # Inside the same lock and after the row, because there is nothing to mark until the
                # row is there. Its own guard, because by here the channel really has been added:
                # reporting the whole thing as a failure would send somebody to add a channel that
                # is already standing.
                try:
                    kept.telling(args.agent, args.adapter, said.notify_place)
                except TROUBLE as why:
                    marked = str(why)
    except TROUBLE as why:
        return _failed(str(why), "nothing was added")

    print(f"{args.agent} is connected to {args.adapter}")
    went = _described(args.agent, args.adapter, able)
    if said.invite:
        print(f"        invite    {said.invite}")
        print("        the bot is not in any server until somebody with permission adds it there")
    if marked:
        return _failed(
            f"{args.adapter} was added and is not the channel {args.agent} writes to when nobody "
            f"has asked — {marked}",
            f"mark it with: rundesk channels configure {args.agent} {args.adapter} --notify")
    return went


def _reached(agent: str, kind: str, allow: Sequence[str], options: Sequence[str],
             reaching: Optional[Reaching]) -> Tuple[adapters.Checked, List[str], str]:
    """Ask an adapter to connect, taking the credential it names on the way through.

    Two questions where it looks like one, and the first is the reason there is a second: an adapter
    asked to connect with nothing set answers `ok: false` **and names the variable it looked in**,
    which is the whole of how rundesk knows what to ask somebody for without holding a list of what
    any platform wants.

    Hands back what the adapter said, the names that were filled in on the way, and a sentence when
    the asking itself could not finish. The first answer comes back with that sentence rather than
    nothing, so that a caller has only one shape to read whichever way this went.
    """
    said = adapters.checked(kind, options, _handed(agent, allow, []), reaching)
    if said.ok or not said.secret_names:
        return said, [], ""

    trouble = _asked_for(agent, kind, said.secret_names)
    if trouble:
        return said, [], trouble
    return (adapters.checked(kind, options, _handed(agent, allow, said.secret_names), reaching),
            list(said.secret_names), "")


def _asked_for(agent: str, kind: str, names: Sequence[str]) -> str:
    """Read each credential this adapter named, one at a time. `""` when there is something to try.

    Read from the terminal without echoing, or from a pipe when something else is driving — never
    from `argv`, which is in the shell's history the moment somebody presses return and is visible in
    `ps` to every other user on the machine while the command runs. `commands.env.typed` is the one
    right way to do that and is reused rather than copied.

    **What is typed is kept under this agent's own name**, so a second agent on the same platform is
    a second bot rather than the same one answering twice. There is no other name: an install-wide
    value is not read, so nothing typed here can end up shared.

    **Refused before the first prompt for an agent whose name cannot carry one.** Asking somebody to
    paste a bot token into a name this release will never look in is worse than telling them, and
    they would find out at three in the morning instead of now.

    **Whatever is already kept is said out loud rather than written over.** Somebody who meant a
    different token types one; typing nothing keeps what is there.
    """
    trouble = credentials.name_trouble(agent)
    if trouble:
        return trouble
    found = credentials.standing(agent, names)
    print(f"the {kind} adapter needs {len(names)} value"
          f"{'s' if len(names) != 1 else ''} before {agent} can use it")
    for one in found:
        print(f"        {one.scoped}   {_what_a_name_is_for(agent, kind, one)}")
        typed = env.typed("        > ")
        if typed is None:
            if one.holding:
                continue
            return (f"nothing was typed for {one.scoped}, so there is nothing to connect with — "
                    f"keep it separately with: rundesk env set {one.scoped}")
        try:
            secrets.stated(one.scoped, typed)
        except (secrets.Refused, secrets.Stuck, OSError) as why:
            return str(why)
    return ""


def _what_a_name_is_for(agent: str, kind: str, one: credentials.Standing) -> str:
    """The sentence beside a name somebody is being asked to type a value for.

    Three cases, and each changes what a person should do: a value that cannot be opened has to be
    typed over, one that is there is kept by saying nothing, and one that is not there has to be
    typed. An agent that can hold no credential never reaches here — `_asked_for` refuses first.
    """
    reads = f"the {kind} adapter reads {one.declared}"
    if one.trouble:
        return f"{reads} — {one.trouble}, so a value has to be typed over it"
    if one.holding:
        return f"{reads}, and this is {agent}'s own — already set; type nothing to keep it"
    return f"{reads}, and this is {agent}'s own"


def _handed(agent: str, allow: Sequence[str], names: Sequence[str]) -> Dict[str, str]:
    """What an adapter is asked its question with: who it may answer, and each named credential.

    **`RUNDESK_ALLOW` is here and not only at hosting time**, and it is not decoration: an adapter
    that opens private conversations for unsolicited notices has to know whose conversations, so a
    `--check` handed no allow list can be refused by the adapter before it has even signed in.
    `channels.hosting` builds the same variable from the same list for the long-lived half.

    The credentials are `channels.credentials`' to resolve, and are resolved by the same call
    `channels.hosting` makes — so a `--check` that connected and an adapter that is really serving
    were handed the same value, out of the same name, for the same agent.

    Reading a whole value is what `secrets.value` exists for — the programs rundesk starts — and a
    `--check` is one of them. Nothing here prints it.

    **Sorted into senders and places by the one module that reads an entry**, so a `--check` and the
    hosted half of the same channel are handed the same two lists. Building them here from the raw
    strings would be a second reading of what an entry means, and the two would eventually differ
    about which of them a person was on.
    """
    admitting = kept.admitted_by(allow)
    built = {"RUNDESK_ALLOW": ",".join(admitting.senders),
             "RUNDESK_ALLOW_PLACES": ",".join(admitting.places)}
    built.update(credentials.handed(agent, names))
    return built


def _reconnected(agent: str, kind: str, row: Dict[str, Any],
                 reaching: Optional[Reaching]) -> adapters.Checked:
    """Ask an adapter to reach again what its channel already has on record.

    **The shape `test` and `doctor` share, and it is the whole of what they share.** Both ask with no
    options — what an adapter made of the ones it was given at `add` came back as `settings` and is
    what the channel is really running on — and both hand it the allow list and the credentials the
    row names. `add` is deliberately not written in terms of this: it asks twice, prompts between the
    two, and passes the options somebody typed.

    **Whose channel it is has to be carried in**, because which value answers a declared name is an
    agent's own fact: a `test` that resolved without the agent would connect as whatever the
    install-wide name holds and report a bot that is not the one this agent is hosted as.
    """
    return adapters.checked(kind, (), _handed(agent, kept.who_may_reach(row), _named_secrets(row)),
                            reaching)


def _shown(agent: str, kind: str) -> int:
    """Everything one channel was given, read back whole. Changes nothing."""
    gone_wrong = directory.not_an_agent(agent)
    if gone_wrong:
        return _failed(gone_wrong, "see what there is with: rundesk agents", "nothing was shown")
    try:
        kept.one(agent, kind)
    except TROUBLE as why:
        return _failed(str(why), "nothing was shown")
    print(f"{kind} channel for {agent}")
    return _described(agent, kind, {})


def _described(agent: str, kind: str, able: Dict[str, Any]) -> int:
    """The whole of one channel, in the shape `agents add` and `schedules add` report what they made.

    Read back out of the records rather than out of whatever was just handed in, so what somebody is
    shown is what was actually written down.

    **A credential is described and never shown.** `set` and `not set` is the whole of what this can
    say about one, which is what `commands.env` promises of every listing in this product.
    """
    try:
        row = kept.one(agent, kind)
    except TROUBLE as why:
        return _failed(str(why), "nothing was shown")

    print(f"        reaches   {as_written(row.get('describes'))}")
    print(f"        allowed   {_who(row)}")
    print(f"        told      {as_written(bool(row.get('notified')))}"
          f"{_where_it_writes(row)}")
    print(f"        needs     {_credentials(agent, row)}")
    print(f"        settings  {as_written(row.get('settings'))}")
    if able:
        print(f"        can       {', '.join(f'{one}={able[one]}' for one in sorted(able))}")
    print(f"        adapter   {_the_program_behind(kind)}")
    print(f"        keeps     {hosting.at(agent, kind)}")
    print(f"        standing  {_how(agent, kind)}")
    return OK


def _who(row: Dict[str, Any]) -> str:
    """Everybody who may reach the agent here, or that the list cannot be read."""
    try:
        return ", ".join(kept.who_may_reach(row)) or NOTHING
    except TROUBLE as why:
        return f"cannot be read — {why}"


def _where_it_writes(row: Dict[str, Any]) -> str:
    """Where unprompted things land, said only about the channel that is really the notified one."""
    if not row.get("notified"):
        return ""
    if row.get("kind") == "discord":
        return " — unprompted things go privately to every allowed user"
    return f" — unprompted things go to {as_written(row.get('notify_place'))}"


def _credentials(agent: str, row: Dict[str, Any]) -> str:
    """Each credential this channel names, and whether it is set — never what it holds.

    **The name shown is this agent's own**, which is the only name a value is read from. It is named
    whether or not anything is kept under it, because that is the name somebody has to set.
    """
    names = _named_secrets(row)
    if not names:
        return "nothing"
    try:
        found = credentials.standing(agent, names)
    except TROUBLE as why:
        return f"cannot be read — {why}"
    return ", ".join(_one_credential(one) for one in found)


def _one_credential(one: credentials.Standing) -> str:
    """One credential in the words a readout uses: the name that holds it, and how it stands."""
    if one.holding:
        return f"{one.holding} (set)"
    if one.trouble:
        return one.trouble
    return f"{one.scoped} (NOT SET)"


def _named_secrets(row: Dict[str, Any]) -> List[str]:
    """The environment names this channel's credentials are kept under, as the record holds them.

    A record that will not parse names nothing, which is the least this can claim: it is read the
    same way `channels.hosting` reads it, so what `doctor` reports missing is what an adapter would
    really be started without.
    """
    try:
        held = json.loads(row.get("secret_names") or "[]")
    except (TypeError, ValueError):
        return []
    return [str(one) for one in held] if isinstance(held, list) else []


def _kept_under(agent: str, row: Dict[str, Any]) -> List[str]:
    """The name each of this channel's credentials really stands under, for a removal to name.

    **The name that is really still there afterwards**, which is this agent's own: telling somebody
    `DISCORD_BOT_TOKEN` is kept, when what is kept is `DISCORD_BOT_TOKEN__ALAN`, sends them to
    `rundesk env unset` a name holding nothing.

    Nothing is named for an agent that can hold no credential, because nothing was ever kept for it.
    Falls back to the declared names when the store will not answer: this is a line describing what
    a removal left behind, and by the time it prints the removal has already happened — a readout
    that cannot be composed must not turn a completed removal into a traceback.
    """
    names = _named_secrets(row)
    try:
        return [one.holding or one.scoped
                for one in credentials.standing(agent, names) if one.holding or one.scoped]
    except TROUBLE:
        return names


def _the_program_behind(kind: str) -> str:
    """Where the adapter for this channel stands, or that there is not one."""
    try:
        return str(adapters.where(kind))
    except adapters.NotRunnable as why:
        return str(why)


def _configured(args: argparse.Namespace) -> int:
    """Change who may reach an agent here, or which channel is the one it writes to unprompted."""
    typed = f"rundesk channels configure {args.agent} {args.adapter}"
    trouble = change_trouble(args.allow, args.deny, args.notify, typed)
    if trouble:
        return _failed(trouble, "nothing was changed")

    gone_wrong = directory.not_an_agent(args.agent)
    if gone_wrong:
        return _failed(gone_wrong, "see what there is with: rundesk agents", "nothing was changed")

    try:
        with locking.only_one(paths.lock(), "this install", locking.WHILE_A_DIRECTORY_MOVES):
            if args.allow or args.deny:
                # Read, decided and written inside one transaction by `kept.allowing`, which is why
                # the whole list is never handed back and forth: two commands racing each other over
                # a rewritten list lose one of the two changes, and this is the list that decides
                # who may reach the agent.
                kept.allowing(args.agent, args.adapter, add=args.allow, remove=args.deny)
            if args.notify:
                # No place said, so whatever the channel already knows is kept — re-marking a channel
                # that already knows where to write does not make somebody name the place again.
                kept.telling(args.agent, args.adapter)
    except TROUBLE as why:
        return _failed(str(why), "nothing was changed")

    print(f"{args.agent}'s {args.adapter} channel changed")
    return _described(args.agent, args.adapter, {})


def _tested(agent: str, kind: str, reaching: Optional[Reaching]) -> int:
    """Ask the adapter to connect again with what the channel already has, and say what it reached.

    **Changes nothing, including the record of what it found.** A credential that was reset in
    somebody's developer portal is the case this exists for, and the answer to that is a sentence at
    a terminal rather than a channel quietly rewritten underneath whoever is reading it.

    The options an owner typed after `--` when the channel was added are deliberately not replayed:
    what an adapter made of them came back as `settings` and is what the channel is really running
    on, and a second copy of the words that produced it is a second thing to keep in step.
    """
    gone_wrong = directory.not_an_agent(agent)
    if gone_wrong:
        return _failed(gone_wrong, "see what there is with: rundesk agents", "nothing was tried")

    try:
        row = kept.one(agent, kind)
        adapters.where(kind)
        said = _reconnected(agent, kind, row, reaching)
    except TROUBLE as why:
        return _failed(str(why), "nothing was tried")

    if not said.ok:
        return _failed(f"{agent}'s {kind} channel could not reach anything — {said.why}",
                       "what the channel is configured with is unchanged — see it with: "
                       f"rundesk channels show {agent} {kind}")
    print(f"{agent}'s {kind} channel reached {said.describes}")
    print(f"        needs     {_credentials(agent, row)}")
    print(f"        standing  {_how(agent, kind)}")
    return OK


def _removed(agent: str, kind: str, confirm: bool) -> int:
    """Take a channel away, or say what taking it away would cost.

    **`--confirm` is required here and is not on `configure`**, and the line between them is the one
    `skills` draws: would somebody want to read this before it happened. Setting up a channel is a
    credential, an allow list and a round trip to a platform. A backup can restore those pieces, but
    taking the live channel away is still a user-visible destructive change worth confirming.
    """
    gone_wrong = directory.not_an_agent(agent)
    if gone_wrong:
        return _failed(gone_wrong, "see what there is with: rundesk agents", "nothing was removed")
    try:
        row = kept.one(agent, kind)
    except TROUBLE as why:
        return _failed(str(why), "nothing was removed")

    if not confirm:
        return _would_remove(agent, kind, row)

    try:
        with locking.only_one(paths.lock(), "this install", locking.WHILE_A_DIRECTORY_MOVES):
            kept.forgotten(agent, kind)
    except TROUBLE as why:
        return _failed(str(why), "nothing was removed")

    print(f"{agent} is no longer connected to {kind}")
    print(f"        kept   {hosting.at(agent, kind)} — what arrived through it, and what its "
          "adapter wrote")
    for name in _kept_under(agent, row):
        print(f"        kept   {name} — rundesk env forgets nothing here")
    if _still_hosted(agent, kind):
        # Said rather than refused. Nothing here can stop an adapter another process started, and a
        # gateway that is hosting one will let it go when it next looks; what must not happen is
        # somebody reading "no longer connected" and believing the connection is already down.
        print(f"        note   an adapter for {kind} is still connected — the gateway hosting "
              f"{agent} lets it go when it next looks, and nothing starts another")
    return OK


def _would_remove(agent: str, kind: str, row: Dict[str, Any]) -> int:
    """What removing this channel would take, on stderr, having taken none of it."""
    print(f"remove: this would take {agent}'s {kind} channel", file=sys.stderr)
    print(f"        take     the connection — {agent} would no longer be reachable on {kind}, and "
          f"{_who(row)} could no longer reach it there", file=sys.stderr)
    if row.get("notified"):
        print(f"        take     this is the channel {agent} writes to when nobody has asked, so "
              "it would then write nowhere", file=sys.stderr)
    print(f"        keep     {hosting.at(agent, kind)} — what arrived through it, and what its "
          "adapter wrote", file=sys.stderr)
    for name in _kept_under(agent, row):
        print(f"        keep     {name} — rundesk env forgets nothing here", file=sys.stderr)
    print("        nothing was removed. To go ahead:", file=sys.stderr)
    print(f"        rundesk channels remove {agent} {kind} --confirm", file=sys.stderr)
    return FAILED


def _still_hosted(agent: str, kind: str) -> bool:
    """Whether something is still holding this channel's claim. `False` when nobody can tell.

    Only ever used to add a sentence to a removal that has already happened, so being unable to ask
    is not worth a failure — and it is never the other way round: nothing here decides whether to act
    on this answer.
    """
    try:
        return hosting.still_running(agent, kind)
    except OSError:
        return False


def _doctored(agent: Optional[str], reaching: Optional[Reaching]) -> int:
    """Say what cannot be used and why, and exit non-zero when anything is wrong.

    The verb a script gates on, the way `env check` and `skills doctor` are — which is why it exits
    non-zero for a channel it could not reach even though the question it was asked was answered
    perfectly well.

    **It really connects.** A credential that is set and no longer accepted is the failure this
    exists to find, and nothing on this machine can tell that from one that is: the adapter has to be
    asked. So a channel whose credential is missing is `BLOCKED` without a round trip, and everything
    else pays for one.
    """
    if agent is not None:
        gone_wrong = directory.not_an_agent(agent)
        if gone_wrong:
            return _failed(gone_wrong, "see what there is with: rundesk agents",
                           "nothing was checked")
        names = [agent]
    else:
        try:
            names = directory.known()
        except OSError as why:
            return _failed(str(why), "nothing was checked")

    found: List[Found] = []
    unreadable: List[Tuple[str, str]] = []
    for name in names:
        try:
            rows = kept.all(name)
        except TROUBLE as why:
            # Reported rather than dropped, and counted as trouble: an agent whose channels cannot be
            # read is not an agent with no channels, and answering "nothing to check" would say so.
            unreadable.append((name, str(why)))
            continue
        for row in rows:
            found.append(_looked_over(name, row, reaching))

    if not found and not unreadable:
        who = agent or "any agent"
        print(f"nothing is connected for {who}, so there is nothing to check")
        return OK

    for line in _by_agent(found, unreadable):
        print(line)

    trouble = [one for one in found if one.verdict != READY]
    if not trouble and not unreadable:
        print(f"all {len(found)} of them are ready")
        return OK

    # Flushed before anything goes to stderr. The findings are on stdout so a script can read them
    # and the summary is on stderr so a script can ignore it — but stdout is block-buffered into a
    # pipe and stderr is not, so `rundesk channels doctor | less` would otherwise show the summary
    # above the findings it summarises.
    sys.stdout.flush()
    typing = [one.fix for one in trouble if one.fix]
    # The colon is only earned when something follows it: a heading reading "1 of 2 cannot be used:"
    # with nothing under it reads like output that went missing.
    ending = ":" if typing else " — each of them says what is in the way"
    print(f"channels: {len(trouble) + len(unreadable)} of {len(found) + len(unreadable)} cannot be "
          f"used{ending}", file=sys.stderr)
    for line in typing:
        print(f"        {line}", file=sys.stderr)
    return FAILED


def _looked_over(agent: str, row: Dict[str, Any], reaching: Optional[Reaching]) -> Found:
    """What is wrong with one channel, in the order the answers rule each other out.

    The program first, because a channel whose adapter is gone cannot be asked anything; then the
    credential, because an adapter asked to connect without one refuses for a reason nobody has to
    pay a round trip to learn; then the connection itself, which is the only question left.

    **`GIVEN_UP` is asked last, and only of a channel that answered everything else correctly.** It
    is the one verdict here that does not come from the adapter: this verb asks in a process of its
    own, so a failure that shows itself only once an adapter is really serving — a close code the
    platform will answer with for ever — satisfies every check above. Where the adapter *does* refuse,
    its own reason is the more specific one and is worth more than this, which is why this stands
    below rather than in front.
    """
    kind = str(row.get("kind") or "")
    try:
        adapters.where(kind)
    except adapters.NotRunnable as why:
        return Found(agent, kind, DANGLING, str(why),
                     f"rundesk channels remove {agent} {kind} --confirm")

    try:
        found = credentials.standing(agent, _named_secrets(row))
    except TROUBLE as why:
        return Found(agent, kind, BLOCKED, str(why), "rundesk env list")
    missing = [one for one in found if not one.holding]
    if missing:
        # **Resolved by the same call that starts an adapter**, so a channel this says is blocked is
        # one a gateway really cannot host, and one it passes is one whose credential a gateway
        # really finds. Two answers to *which name holds this* is how a `READY` verdict comes to
        # describe a channel that has never connected.
        #
        # **No command for an agent that can hold no credential**, because there is not one: setting
        # any name would not help, and `Found.fix` is empty exactly for the verdicts nothing can be
        # typed at.
        return Found(agent, kind, BLOCKED, "; ".join(_nothing_kept(one) for one in missing),
                     f"rundesk env set {missing[0].scoped}" if missing[0].scoped else "")

    try:
        said = _reconnected(agent, kind, row, reaching)
    except TROUBLE as why:
        return Found(agent, kind, UNREACHABLE, str(why),
                     f"rundesk channels show {agent} {kind}")
    if not said.ok:
        return Found(agent, kind, UNREACHABLE, said.why,
                     f"rundesk channels test {agent} {kind}")
    gave_up = hosting.will_not_start(agent, kind)
    if gave_up:
        return Found(agent, kind, GIVEN_UP,
                     f"{gave_up}, and it checks out from here — a gateway has to be started again "
                     f"before it will try",
                     f"rundesk gateways restart {agent}")
    return Found(agent, kind, READY, said.describes, "")


def _nothing_kept(one: credentials.Standing) -> str:
    """Why one credential cannot be used, naming the one place its value is kept.

    One place, because there is one: a plain `{declared}` is not read and saying it was looked for
    would send somebody to set a name this release ignores. An agent that can hold no credential
    says that instead, in `credentials.name_trouble`'s own words.
    """
    if one.trouble:
        return one.trouble
    return f"{one.scoped} — nothing this install can read is kept under that name"


def _by_agent(found: Sequence[Found], unreadable: Sequence[Tuple[str, str]]) -> List[str]:
    """The findings as lines, grouped under each agent's own name.

    **Measured rather than guessed.** Fixed widths are wrong the first time a real adapter is
    installed — a channel named for a path somebody is writing right now is far wider than `discord`
    — and running one column into the next is the kind of defect a test asserting `assertIn` never
    sees.
    """
    kind = max((len(one.kind) for one in found), default=0) + 2
    verdict = max((len(one.verdict) for one in found), default=0) + 2

    lines: List[str] = []
    standing = ""
    for one in found:
        if one.agent != standing:
            standing = one.agent
            lines.append(standing)
        lines.append(f"  {one.kind:<{kind}}{one.verdict:<{verdict}}{one.said}")
    for agent, why in unreadable:
        lines.append(agent)
        lines.append(f"  {agent}'s channels cannot be read — {why}")
    return lines


def _failed(why: str, *and_so: str) -> int:
    """Say what went wrong, and what that leaves — never one without the other."""
    return failed(f"channels: FAILED — {why}", *and_so)
