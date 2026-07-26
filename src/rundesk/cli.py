"""The rundesk command line — the one interface anyone using rundesk goes through.

Every operation the finished product will have is registered here from the start,
so `rundesk` and `rundesk --help` describe the whole shape of the thing rather
than whatever happens to be built this week. What is not built yet says so and
exits non-zero: a command that did nothing and reported success is a lie a script
will believe, and one that exits the same way a typo does is a lie it cannot even
tell from a typo.

The install lifecycle, the gateway and its schedules are real. The agents that
work is run for, what reaches them and what each run became are `PLANNED`.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rundesk import __version__  # noqa: E402
from rundesk import agent as _agent  # noqa: E402
from rundesk import channel  # noqa: E402
from rundesk import gateway as _gateway  # noqa: E402
from rundesk import migration  # noqa: E402
from rundesk import process  # noqa: E402
from rundesk import provider  # noqa: E402
from rundesk import store  # noqa: E402
from rundesk import supervisor as _supervisor  # noqa: E402
from rundesk import turn  # noqa: E402
from rundesk import updater  # noqa: E402

#: The installer as published, for the one case where this install has lost its own:
#: removing rundesk is exactly when a broken install has to be removable.
PUBLISHED_INSTALLER = ("https://github.com/rundesk-ai/rundesk-cli/releases/latest/"
                       "download/install.sh")

#: Where this checkout lives — the thing an update replaces in place.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: How many lines of what a brain said went wrong a failed turn puts on the screen. A tail
#: rather than all of it: a brain that failed noisily can say a great deal, and what is
#: worth reading is almost always the last of it.
_TROUBLE_LINES = 6

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

#: How often either of those looks again while it waits. Named once rather than written
#: into each waiter, because how long to wait and how often to look are one decision: a
#: patience shorter than a couple of these leaves a wait that can only look once, and
#: whether it looks twice then depends on how loaded the machine is. That is exactly how
#: a correct cycle came to be reported as one that never restarted, on one platform and
#: not the other.
LOOK_AGAIN_SECONDS = 0.2

#: What a command that exists but is not built yet exits with. Not 0, which a script
#: would take as done; not 1, which is reserved for a command that ran and failed; and
#: not 2, which argparse already spends on a usage error. Those last two are different
#: situations wearing one number: "this rundesk does not have that yet" is worth waiting
#: for or upgrading to, and "you typed it wrong" is worth reading the help for, and a
#: script that cannot tell them apart can do neither. 69 is `EX_UNAVAILABLE`, which is
#: what the BSD table has always called this. See `PLANNED`.
NOT_AVAILABLE = 69

#: Every operation that is planned and not built, and the one line `--help` shows for
#: each. The finished shape of the product, declared from the outset (R-CMD-1, R-CMD-2):
#: what an agent, a channel and a run are reached by is registered before any of it
#: exists, so that the first of them to land does not arrive through a configuration path
#: nobody could have found. An entry graduates out of this table into a real command as it
#: is built.
#:
#: An agent has one gateway, made with it and taken away with it, and everything that
#: reaches that agent runs inside it: its channels are held open there, and its schedules
#: fire there. So what a person operates is the agent, and the gateway verbs below name
#: one — the gateway is how an agent runs, not a second thing to keep track of.
#:
#: **A verb says what, and the word after it says whose** — `start ava`, `logs ava`,
#: `channels ava`. `add` needs no noun in front of it for the same reason `start` does
#: not: there is one thing at this level to add, and it is an agent. A nested `add` stays
#: qualified by the group it sits in, so `channels ava add` is a channel and nothing else.
#:
#: There is no verb for a binding. Which provider and model answer on a channel, on a
#: schedule or in this terminal is an option where that entry point is made, and the agent
#: supplies what was left out — so reaching an agent from Discord is one command and not
#: two, and a binding stays what a run resolved rather than a thing anyone maintains.
PLANNED: dict[str, tuple[str, dict[str, tuple[str, str]]]] = {
    "usage": ("what agents have cost, in tokens and in money", {}),
    "runs": ("what an agent has run, and what became of each", {
        "resume": ("<run>", "carry one run on from where it stopped"),
        "show": ("<run> [--stream]", "one run — what was asked, what it cost, and how it ended"),
        "stop": ("<run>", "end one run, leaving the agent it belongs to running"),
    }),
}

#: What is accepted and not offered. `serve` is what every launchd job already on disk
#: invokes, so it goes on working forever; `start <agent> --here` is the one a person types,
#: and both run the same gateway in this terminal. Two verbs for one thing is what this
#: surface removes, and a job written last month is not a reason to keep one on show.
#: Read by the reference generator, so what is hidden is said once.
HIDDEN = {"serve"}

#: The planned verbs that are about one agent's things rather than about an agent, and so
#: name whose before saying which. Optional to the parser and required by the command once
#: built, so that leaving it out is answered in our words rather than by a usage dump.
WHOSE = {"runs"}

#: Every form a planned verb will be typed in, and what each form does — the bare listing
#: and the one that names a thing are different operations, and a reference that showed
#: only `[<agent>]` would say neither. Shown in `--help` and in `CLI.md` so the shape is
#: legible before it is built; whatever is actually given is still accepted and refused
#: today (R-CMD-7).
#: What each name in a planned form stands for. Held beside the forms that use them, so a
#: reference can say what `<run>` is without sending a reader into the source.
MEANS: dict[str, str] = {
    "<agent>": "which agent — the name it was made under",
    "<prompt>": "what to ask it, in quotes",
    "<run>": "which run — the id listed against each by `runs`",
    "--provider <provider>": "which brain — one that ships, or the path to a program you wrote",
    "--model <model>": "which model, in that brain's own words — rundesk never reads it",
    "--set <key=value>": "anything that brain takes, carried to it unread; repeatable",
}

#: What each of the three things an owner makes actually looks like when it is typed.
#: Signatures say what is *allowed*; these say what it *is*. A reader working out how to
#: put an agent on Discord from `[--kind <kind>] [--allow <user>] <channel> [<option> ...]`
#: is reading a grammar and guessing at a command.
#:
#: Real values, deliberately: a made-up id that looks like an id says more than `<id>` said
#: twice, and the shape of a Discord snowflake is itself the answer to a question somebody
#: would otherwise have to go and ask.
EXAMPLES: list[tuple[str, list[tuple[str, str]]]] = [
    ("an agent", [
        ("rundesk add ava --provider codex",
         "an agent called ava, answered by the codex this machine already has"),
        ("rundesk add ava --provider /opt/my-brain --model fast-1 --set effort=high",
         "one answered by a brain you wrote, told which model and how hard to think"),
        ("rundesk start ava",
         "have the machine keep it running, and bring it back when it falls over"),
    ]),
    ("a channel", [
        ("rundesk channels ava add discord --kind discord --allow 279024636254224384",
         "reachable in direct messages and in every room it has been invited to"),
        ("", "writes two channels — discord-dms and discord-rooms — each with its own "
             "allowed list, settings and instructions"),
        ("rundesk channels ava add discord --kind discord --allow 279024636254224384 -- --dm",
         "direct messages only; --server <id> or --channel <id> narrows the rooms instead"),
        ('rundesk channels ava instructions discord-rooms "You are {agent} in {where.channel}. Others read this, so keep it short."',
         "what it is told about where it is, before it reads a word of the message"),
        ("rundesk channels ava",
         "what it is reachable on, and whether it is reachable at all"),
    ]),
    ("a schedule", [
        ('rundesk schedules ava add nightly --when "0 3 * * *" -- rundesk ask ava "summarise what changed today"',
         "at three every morning, one turn, in this agent's own conversation"),
        ('rundesk schedules ava add nightly --when "0 3 * * *" -- rundesk ask ava "check the deploy" --instructions "Nobody is watching."',
         "the same, told it is running unattended before it reads a word"),
        ("rundesk schedules ava off nightly",
         "keep it, and stop it running"),
    ]),

]

#: A verb that can be typed bare *and* given a name is two operations, not one, and a
#: reference showing a single line would say neither. One bracket style per thing means
#: `[<agent>]` is not available to say "optional" — so both forms are listed, and what each
#: does is said here. The signature itself still comes off the parser.
FORMS: dict[str, list[tuple[str, str]]] = {
    "agents": [("", "every agent this install has, and what each is doing"),
               ("<agent>", "what one agent is, and where it keeps things")],
    "doctor": [("", "what stands between every agent and a working turn"),
               ("<agent>", "what stands between one agent and a working turn")],
    "ask": [('<agent> "<prompt>"', "one turn, streamed to this terminal"),
            ('<agent> "<prompt>" --instructions "<text>"',
             "with standing instructions, told apart from the prompt")],
    "usage": [("", "what every agent has cost"),
              ("<agent>", "what one agent has cost"),
              ("<agent> <run>", "what one run cost")],
}


def examples() -> str:
    """The three things an owner makes, as they are actually typed."""
    said = ["what it looks like:"]
    for what, shown in EXAMPLES:
        said.append(f"\n  {what}")
        for typed, means in shown:
            if typed:
                said.append("    " + typed.replace("\n", "\n    "))
            said.append(f"        {means}" if typed else f"    {means}")
    return "\n".join(said)


def _brain(parser: argparse.ArgumentParser, whose: str) -> None:
    """The three options that say which brain, said once for every verb that takes them.

    Written twice they would drift, and the drift would be silent: `add` recording a model
    under one spelling and `ask` reading another is a turn that quietly uses the default.

    **Nothing here enumerates anything.** A provider is a name carried through and a model
    is a word its brain understands; rundesk reads neither, so there are no choices to
    offer and a brain nobody here has heard of is typed exactly like one that ships.
    """
    parser.add_argument("--provider", metavar="<provider>", help=whose)
    parser.add_argument("--model", metavar="<model>",
                        help="which model, in that brain's own words")
    parser.add_argument("--set", dest="settings", action="append", metavar="<key=value>",
                        help="anything that brain takes, carried to it unread; repeatable")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rundesk",
        description="A lightweight, provider-agnostic multi-agent gateway.",
        # Shown under every verb's list, because a signature says what is allowed and an
        # example says what it *is*. Working out how to put an agent on Discord from
        # `[--kind <kind>] [--allow <user>] <channel> [<option> ...]` is reading a grammar
        # and guessing at a command.
        epilog=examples(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"rundesk {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    for name, (help_text, actions) in PLANNED.items():
        # Marked where the list is, not only when the verb is invoked. Most of what is
        # listed is planned, and a surface that reads as working sends a newcomer to try
        # each in turn to find out which ones do anything.
        described = "\n".join(f"  {act} {takes:<12}  {what}".replace("  ", " ", 1)
                              for act, (takes, what) in actions.items())
        planned = sub.add_parser(
            name, help=f"{help_text} [coming soon]",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description=f"{help_text} — planned, not built yet."
                        + (f"\n\nactions:\n{described}" if described else ""))
        if name in WHOSE:
            planned.add_argument("agent", nargs="?", metavar="<agent>", help="which agent — the name it was made under")
        if actions:
            # A plain argument rather than a sub-parser, which cannot be used here: a
            # sub-parser is itself a positional and takes the *first* word after the verb,
            # so `runs ava show` would look for an action called `ava`. The agent comes
            # first everywhere in this surface, so the actions are a choice instead — and
            # each is described above, where it is listed, rather than by argparse.
            planned.add_argument("act", nargs="?", choices=sorted(actions), metavar="<action>",
                                 help="what to do with them")
        # Whatever a planned command will eventually take, it takes nothing today — but it
        # must not choke on being given arguments, or the message it prints would be
        # argparse's rather than ours (R-CMD-7). Everything left, options included: with
        # `nargs="*"` an option nobody has declared yet is an unrecognized argument, so
        # `channels ava add ops --kind discord` — the form the reference lists — ended on
        # argparse's usage code, which is the one thing a script must be able to tell our
        # refusal from.
        planned.add_argument("args", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)

    said = sub.add_parser("version", help="what is installed, and whether that is current")
    said.add_argument("--check", action="store_true", help="say whether a newer release exists")

    moved = sub.add_parser("update", help="move to the newest published release")
    moved.add_argument("--check", action="store_true", help="say what would happen, and change nothing")

    taken_off = sub.add_parser("uninstall", help="remove rundesk from this machine")
    taken_off.add_argument("--purge", action="store_true",
                           help="also take every agent's home, log and history")

    # The agent. Making one makes the gateway that runs it, and taking it away takes both:
    # there is no separate step, and no way to end up with one and not the other.
    born = sub.add_parser("add", help="make an agent, and the gateway that runs it")
    # Optional to the parser and required by the command, the way `remove` is: asking for
    # it wrong is answered in our words rather than by an argparse usage dump.
    born.add_argument("name", nargs="?", metavar="<agent>",
                      help="what to call it, and what to name it by later")
    _brain(born, "which brain answers for it when a turn does not say")

    # One turn, here, in this terminal. It runs here rather than inside the agent's
    # gateway because there is nothing to ask a gateway with — the same reason a schedule
    # run by hand runs here, and the same honest place for it.
    asked = sub.add_parser("ask", help="one turn, streamed to this terminal")
    asked.add_argument("name", nargs="?", metavar="<agent>", help="which agent")
    asked.add_argument("prompt", nargs="?", metavar="<prompt>", help="what to ask it, in quotes")
    _brain(asked, "which brain answers this turn, whatever the agent reaches for otherwise")
    asked.add_argument("--conversation", metavar="<conversation>",
                       help="which conversation to carry on — this terminal's, when left out")
    asked.add_argument("--fresh", action="store_true",
                       help="start the conversation again rather than carrying it on")
    asked.add_argument("--read-only", action="store_true",
                       help="let this turn look at the machine without changing it")
    asked.add_argument("--steer", action="store_true",
                       help="keep saying more to it while it works — a line at a time, until you stop")
    # How a schedule gives a turn standing instructions. A schedule names a command and
    # rundesk carries it without reading it (R-SCH-3), so a schedule that carried its own
    # instructions would have to be read on the way past — and the seam that keeps every
    # kind of work the same would be the thing that broke. Said here instead, it belongs
    # to the command the schedule names, and every kind of work keeps one way of saying it.
    asked.add_argument("--instructions", dest="says", metavar="<text>", default="",
                       help="standing instructions for this turn, told to the brain apart "
                            "from the prompt — what a schedule running unattended says")

    looked = sub.add_parser("doctor", help="what stands between an agent and a working turn")
    looked.add_argument("name", nargs="?", metavar="<agent>",
                        help="which agent — every one of them when left out")

    # The gateway. Every one of these takes the gateway's name and can do without it,
    # because there is one gateway today and there will be one per agent. Leaving the
    # name out means all of them wherever that can mean anything, so what these do
    # today stays true once there are several.
    # No `help`, so argparse leaves it out of `--help` altogether rather than printing it
    # with its description suppressed.
    served = sub.add_parser("serve")
    served.add_argument("name", metavar="<agent>", help="which agent")

    started = sub.add_parser("start", help="have the machine keep an agent running")
    started.add_argument("name", metavar="<agent>", help="which agent")
    started.add_argument("--here", action="store_true",
                         help="run it in this terminal instead of handing it to the machine")

    stopped = sub.add_parser("stop", help="stand an agent down")
    stopped.add_argument("name", nargs="?", metavar="<agent>", help="which agent")
    stopped.add_argument("--all", action="store_true", help="every agent on this machine")

    gone = sub.add_parser("remove", help="take an agent away for good")
    # Optional to the parser and required by the command, so that asking for it wrong is
    # answered in our words rather than by an argparse usage dump. Every other gateway
    # verb defaults to one when the name is left out; this one must never guess.
    gone.add_argument("name", nargs="?", metavar="<agent>",
                      help="which agent — required, because this one never guesses")

    cycled = sub.add_parser("restart", help="cycle an agent, leaving the others alone")
    cycled.add_argument("name", nargs="?", metavar="<agent>", help="which agent")
    cycled.add_argument("--all", action="store_true", help="every agent on this machine")

    listed_agents = sub.add_parser("agents", help="every agent this install has, and what each is doing")
    listed_agents.add_argument("name", nargs="?", metavar="<agent>",
                               help="one agent — what it is, and where it keeps things")

    sub.add_parser("status", help="how rundesk itself is on this machine")

    listed = sub.add_parser("schedules", help="what an agent runs on its own, and when")
    # The agent is the word after the verb, like every other verb here. As an option it
    # was also in the list `--run`'s remainder swallowed, so `--gateway beta` typed after
    # the program became an argument to the program and the schedule landed on another
    # agent, reported as success.
    listed.add_argument("name", metavar="<agent>",
                        help="whose schedules — an agent's schedules are its own")
    # Registered and refused rather than removed, so the old spelling is answered in our
    # words with the new one, instead of by an argparse dump about an unrecognized option.
    listed.add_argument("--gateway", dest="gateway_was", metavar="<agent>",
                        help=argparse.SUPPRESS)
    acts = listed.add_subparsers(dest="act", metavar="<action>")
    added = acts.add_parser("add", help="add a schedule")
    added.add_argument("schedule", metavar="<schedule>", help="what to call it, and what to name it by later")
    added.add_argument("--when", required=True, metavar="<cron>",
                       help="when it runs, as five cron fields — minute, hour, day, month, weekday")
    # After `--`, and a positional rather than an option's remainder. What follows is the
    # program and nothing else, so an option typed after it is a usage error rather than
    # something quietly handed to the program.
    added.add_argument("run", nargs="+", metavar="<program>",
                       help="after `--`, the full path of what to start when it is due, and its "
                            "arguments — a bare name is refused, because a gateway runs with "
                            "almost no PATH")
    for act, what in (("remove", "take a schedule away"),
                      ("on", "let a schedule run"),
                      ("off", "keep a schedule but stop it running"),
                      ("run", "run a schedule now, whether or not it is due")):
        one = acts.add_parser(act, help=what)
        one.add_argument("schedule", metavar="<schedule>", help="which schedule, by the name it was added under")

    said = sub.add_parser("logs", help="what an agent has been saying")
    said.add_argument("name", metavar="<agent>", help="whose log")
    said.add_argument("-n", "--lines", type=int, metavar="<lines>", default=LOG_LINES,
                      help="how many of the last lines to show, from each source")
    said.add_argument("--source", choices=list(_gateway.LOG_SOURCES),
                      default=_gateway.EVERY_LOG, metavar="<source>",
                      help="whose lines to show — what the gateway wrote, or what the "
                           "machine caught that never reached it")

    # Named the way schedules are: the agent is the word after the verb, the channel is
    # what you call it, and what it *is* comes from `--kind`. Everything a particular
    # platform needs goes after `--` and is never read here (R-CAD-13).
    reachable = sub.add_parser("channels", help="the surfaces an agent is reachable on")
    reachable.add_argument("name", metavar="<agent>",
                           help="whose channels — a channel belongs to one agent")
    on = reachable.add_subparsers(dest="act", metavar="<action>")
    joined = on.add_parser("add", help="put this agent on a channel")
    joined.add_argument("channel", metavar="<channel>",
                        help="what to call it, and what to name it by later")
    joined.add_argument("--kind", required=True, metavar="<kind>",
                        help="which kind of surface — one that ships, or the path of a "
                             "program that speaks yours")
    # Repeatable and required, with no default there is any way to ask for. An agent that
    # answers whoever speaks to it, on a machine where it runs tools, is a
    # misconfiguration and never a mode (R-CAD-10).
    joined.add_argument("--allow", action="append", default=[], required=True,
                        metavar="<user>",
                        help="who may reach this agent through it — at least one, always; "
                             "repeatable")
    # Declared so the reference shows it, and carried rather than read. Whatever the
    # platform needs is the adapter's own vocabulary, and the `--` in front is grammar:
    # without it the first thing that looks like an option is refused (R-CAD-13).
    joined.add_argument("options", nargs="*", metavar="<option>",
                        help="after `--`, whatever this kind of channel needs — carried to "
                             "it exactly as typed, and never read here")
    for act, what in (("remove", "take this agent off a channel"),
                      ("show", "one channel, and who may reach this agent through it")):
        one = on.add_parser(act, help=what)
        one.add_argument("channel", metavar="<channel>",
                         help="which channel, by the name it was added under")
    # Standing instructions, by the situation they hold in. A separate action rather than
    # flags on `add`, because these are the part an owner rewrites — a wording that reads
    # well in a room is found by trying it, and finding it should not mean taking the
    # agent off the channel and proving it again.
    telling = on.add_parser("instructions",
                            help="what this agent is told about where it is")
    telling.add_argument("channel", metavar="<channel>",
                         help="which channel, by the name it was added under")
    # One piece of text, because a channel is already one place. An owner who wants an
    # agent to say different things in a room and in private wants two channels, and gets
    # two allow-lists with them — which is what they wanted anyway.
    telling.add_argument("said", nargs="?", metavar="<text>", default=None,
                         help="what to tell it, with {agent} {channel} {surface} {where} "
                              "{called} {user} {conversation} filled in — empty takes it "
                              "back off, and left out shows what is there")
    return parser


def cmd_version(args: argparse.Namespace) -> int:
    if args.check:
        return updater.run(REPO_ROOT, __version__, check_only=True)
    print(f"rundesk {__version__}")
    return 0


def cmd_update(args: argparse.Namespace, gateways, machine, agents) -> int:
    return updater.run(
        REPO_ROOT, __version__, check_only=args.check,
        busy=lambda: _in_flight(gateways, agents),
        pause=lambda: _stand_all_down(gateways, machine, agents),
        resume=lambda names: _bring_all_back(names, gateways, machine, agents),
    )


def _every_name(gateways, machine, agents) -> list[str]:
    """Every gateway there is: one per agent, and any that has no agent yet.

    Four places, because there are four ways one can exist. An agent has a gateway
    whether or not it has ever run; a gateway from before there were agents left its record
    where gateways used to keep them; a job the machine holds names one that may have
    left nothing anywhere; and a name whose record was cleared and whose agent was taken
    away survives in what it was scheduled to do and what it never finished (R-GW-38).
    That last one is the name an owner wants after a crash, and it was the one they had
    to know already before any command would tell them anything about it. Asked of the
    agent module rather than of the gateway module for the first, so that a gateway still
    knows nothing of whose work it holds.
    """
    return sorted({*agents.known(), *(it.name for it in gateways.every()),
                   *machine.described(), *gateways.remembered()})


def _standing(name: str, gateways, agents):
    """What this gateway is doing, asked where that gateway actually keeps it.

    The one place the two are put together. A command that resolved the directory itself
    at each call is how one of them comes to ask the wrong place and report a running
    agent as stopped.
    """
    return gateways.standing(name, agents.resolved(name).run)


def _stand_all_down(gateways, machine, agents) -> tuple:
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
    for name in _every_name(gateways, machine, agents):
        it = _standing(name, gateways, agents)
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
        if gateways.what_is_running(it.name, agents.resolved(it.name).run):
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
        if not said.ok or not _gone(it.name, gateways, agents):
            return stopped, f"'{it.name}' would not stop, so nothing was replaced under it"
        stopped.append(it.name)
    return stopped, None


def _bring_all_back(names: list, gateways, machine, agents) -> list:
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
        if not said.ok or _came_up(name, gateways, agents) is None:
            down.append(name)
    if down:
        unfit = gateways.fitness(REPO_ROOT)
        if unfit:
            print(f"update: what rundesk is made of no longer fits: {unfit}", file=sys.stderr)
    return down


def _in_flight(gateways, agents) -> list:
    """Everything every gateway on this machine says it is working on (R-UPD-23).

    Asked of the gateways rather than of a list kept somewhere, and named by gateway as
    well as by work: an owner told only that "something" is running has to go and find
    which of several it was before they can decide to wait.
    """
    return [
        f"{name}/{one}"
        for name in agents.known() + [it.name for it in gateways.every()]
        if _standing(name, gateways, agents).running
        for one in gateways.what_is_running(name, agents.resolved(name).run)
    ]


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Take rundesk off this machine, or fail saying why.

    It printed instructions and exited zero. A control verb that is an instruction page
    makes someone find a second surface, and exiting zero says the uninstall ran when
    nothing was removed at all — which is the one failure this product is most careful
    about everywhere else.

    The installer owns removal, so this runs it rather than reimplementing it: one thing
    decides what is rundesk's and what is the owner's, and a second copy of that decision
    is how an uninstall comes to delete a home it should have kept.

    **Run where it stands**, which is what `install.sh --uninstall` by hand has always
    done. Running it from a copy elsewhere looked safer and was not: the installer finds
    the command it placed by comparing the symlink against its own directory, so a copy in
    a temporary directory matched nothing and left the command on the PATH — removing
    rundesk and leaving behind the one thing R-RM-1 is about.
    """
    installer = REPO_ROOT / "install.sh"
    if not installer.is_file():
        print(f"uninstall: FAILED — this install has no installer to run ({installer})",
              file=sys.stderr)
        print("        remove it with the published one:", file=sys.stderr)
        print(f"        curl -fsSL {PUBLISHED_INSTALLER} | bash -s -- --uninstall",
              file=sys.stderr)
        return 1
    asked = ["--uninstall"] + (["--purge"] if args.purge else [])
    # Looked up here rather than bound in the signature, so a test can put something else
    # in its place — running the real installer to prove this calls it would stop the
    # gateways of whoever ran the suite.
    try:
        ended = _remove_this_install(installer, asked)
    except OSError as why:
        print(f"uninstall: FAILED — could not run the installer: {why}", file=sys.stderr)
        return 1
    if ended != 0:
        # Said again in our own words: the installer has already explained what stopped
        # it, and a command that ended non-zero without saying so reads as a crash.
        print(f"uninstall: FAILED — nothing was removed (the installer ended {ended})",
              file=sys.stderr)
        return 1
    return 0


def _remove_this_install(installer: Path, asked: list[str]) -> int:
    """Run the installer's own removal, where it stands, and say how it ended.

    Where it stands, because the installer works out what it placed relative to its own
    directory: run from anywhere else it recognises none of it, and the command it linked
    onto the PATH is left behind by the very thing meant to remove it. This is the same
    invocation someone types by hand, which is what the installer is written against.
    """
    return subprocess.run(["bash", str(installer), *asked],
                          cwd=str(installer.parent)).returncode


def cmd_not_available(name: str, act: str | None = None) -> int:
    """Say that this rundesk does not have that yet, and name what it does have.

    The action is said back when one was given (R-CMD-10): `agents` and `agents show` are
    different things to want, and being told only that "agents" is planned reads as though
    the whole noun is missing rather than that one thing about it is.

    Ends on `NOT_AVAILABLE` rather than argparse's usage code (R-CMD-8), and names a
    command that does work (R-CMD-9), because being told what is missing and nothing else
    leaves a reader exactly where they started.
    """
    asked = f"{name} {act}" if act else name
    print(f"{asked}: NOT AVAILABLE — planned, not built yet", file=sys.stderr)
    print("        what this rundesk can do:  rundesk --help", file=sys.stderr)
    return NOT_AVAILABLE


def _as_table(head: tuple, rows: list) -> None:
    """Columns wide enough for what is in them. Written once, so the two things that
    list something in columns cannot come to disagree about how."""
    if not rows:
        return
    widths = [max(len(row[i]) for row in [head] + rows) for i in range(len(head))]
    for row in [head] + rows:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip())


def cmd_serve(args: argparse.Namespace, gateways, agents) -> int:
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
    reachable = agents.reachable(args.name) if agents.exists(args.name) else []
    for one, why in (agents.unrunnable_channels(args.name) if agents.exists(args.name) else []):
        # Said, and the others still held: one surface that cannot be run must not make
        # an agent deaf on every other one it has.
        print(f"{args.name}/{one}: CHANNEL UNAVAILABLE — {why}", file=sys.stderr)
    try:
        return asyncio.run(gateways.Gateway(args.name, where=whose.run, logs=whose.logs,
                                            schedules=whose.schedules,
                                            reachable=reachable).serve())
    except (gateways.AlreadyRunning, gateways.Unfit, gateways.NotAName) as why:
        print(f"{args.name}: NOT STARTED — {why}", file=sys.stderr)
        return 0


def cmd_start(args: argparse.Namespace, gateways, machine, agents) -> int:
    """Hand a gateway to the machine, and see that a gateway actually results.

    The machine taking the job is not the gateway running. A job can be accepted and the
    gateway then refuse to start — and refusing ends cleanly, so the machine does not try
    again and nothing says a word. Reporting the hand-off as the outcome is reporting a
    success this command did not earn.
    """
    if args.here:
        # The same function the machine's own job reaches, so what a person types and what
        # launchd runs cannot come to behave differently.
        return cmd_serve(args, gateways, agents)
    name = args.name
    already = _standing(name, gateways, agents)
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
                               schedules=whose.schedules, agents=agents.agents_home())
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
    up = _came_up(name, gateways, agents)
    if up is None:
        print(f"{name}: FAILED — job accepted, but no gateway started.", file=sys.stderr)
        print(f"         why: rundesk logs {name}", file=sys.stderr)
        return 1
    print(f"{name}: RUNNING (pid {up.pid})")
    return 0


def _came_up(name: str, gateways, agents, patience: float | None = None):
    """The gateway, once it is actually there — or None if it never arrives.

    The patience resolves here rather than in the signature: a default argument is bound
    once, when this file is read, so naming the constant there freezes it and anything
    that changed it afterwards is quietly ignored.
    """
    deadline = time.monotonic() + (START_PATIENCE if patience is None else patience)
    while time.monotonic() < deadline:
        now = _standing(name, gateways, agents)
        if now.running:
            return now
        time.sleep(LOOK_AGAIN_SECONDS)
    return None


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
    return _every_name(gateways, machine, agents)


def cmd_stop(args: argparse.Namespace, gateways, machine, agents) -> int:
    return _stand_down(args, gateways, machine, agents, "stop")


def cmd_add(args: argparse.Namespace, gateways, agents) -> int:
    """Make an agent, and the one gateway that runs it (R-AGW-1).

    Making one that already exists puts back only what is missing (R-AGT-4). That is how an
    owner repairs a home they half deleted, and it must not be how they lose the rules they
    spent a month writing — so nothing that is there is written over, whatever is in it.

    Given the name of a gateway that has been running since before there were agents, this
    is also how that gateway gets one: what it wrote moves into the agent's own directories,
    so that afterwards there is one place rather than two that disagree. It moves nothing
    while that gateway is running, because a gateway reading one directory while every
    command reads another is the fault that makes a schedule silently never run.
    """
    name = args.name
    if not name:
        print("add: NAME REQUIRED — say what to call the agent", file=sys.stderr)
        print("        what there is already: rundesk agents", file=sys.stderr)
        return 1
    try:
        agents.checked(name)
    except agents.NotAnAgentName as why:
        print(f"{name}: INVALID NAME — {why}", file=sys.stderr)
        return 1
    knew = agents.exists(name)
    wrote = agents.standing_before(name)
    # Whether or not the agent already exists. An adoption that was refused leaves the
    # files where they were, and asking again is how an owner retries it — conditioning
    # this on the agent being new would make one refusal permanent, since the home would
    # exist ever after and nothing would look at the old directory again.
    if wrote:
        now = _standing(name, gateways, agents)
        if now.running:
            print(f"{name}: NOT MADE — a gateway of that name is running (pid {now.pid})",
                  file=sys.stderr)
            print(f"        it has things to move, so stop it first: rundesk stop {name}",
                  file=sys.stderr)
            return 1
    try:
        made = agents.add(name)
    except (store.Unreadable, store.TooNew, store.Behind, migration.Failed) as why:
        # Repairing an agent whose records this rundesk will not read must say so rather
        # than raise: the one thing an owner does when an agent is broken is make it again,
        # and a traceback tells them nothing about which of the four this is.
        print(f"{name}: NOT MADE — {why}", file=sys.stderr)
        print(f"        its records are at {store.path_for(agents.directory(name))}",
              file=sys.stderr)
        return 1
    try:
        moved = agents.adopt(name) if wrote else []
    except agents.InUse as why:
        # The name was claimed between asking and moving. Nothing moved, and saying so is
        # the whole point: a half-adopted agent is the split this refuses to create.
        print(f"{name}: NOT ADOPTED — {why}", file=sys.stderr)
        print(f"        stop it and ask again: rundesk stop {name} && rundesk add {name}",
              file=sys.stderr)
        return 1
    try:
        chose = _chose(args, agents, name)
    except ValueError as why:
        print(f"{name}: NOT SET — {why}", file=sys.stderr)
        return 1
    if knew and not made and not moved and not chose:
        print(f"{name}: ALREADY MADE — its home is as you left it")
        return 0
    print(f"{name}: MADE" if not knew else f"{name}: REPAIRED")
    print(f"        home: {agents.home(name)}")
    if made:
        print(f"        put there: {', '.join(made)}")
    if moved:
        print(f"        brought in what it wrote before it was an agent: {', '.join(moved)}")
    if chose:
        print(f"        reaches for: {chose}")
    return 0


def _chose(args: argparse.Namespace, agents, name: str) -> str:
    """Keep whichever of provider, model and settings was named, and say what it is now.

    Nothing named changes nothing, so `add` on an existing agent stays the repair it has
    always been. What was not named is left as it was, because naming a model later must
    not quietly forget the brain.
    """
    settings = _given(getattr(args, "settings", None))
    if not (args.provider or args.model or settings):
        return ""
    keeping = agents.remember(name, provider=args.provider, model=args.model,
                              settings=settings or None)
    said = keeping.get("provider") or "no brain yet"
    return f"{said} ({keeping['model']})" if keeping.get("model") else said


def _given(pairs) -> dict:
    """What an owner set, in either of the two ways it is worth being able to type.

    `--set effort=high` for one thing, and `--set '{"flags": ["--no-color"]}'` for a shape
    that is not one thing. **Nothing here reads what it means**: a value is taken as JSON
    when it parses as JSON and as the text that was typed when it does not, and that is
    the whole of the interpretation. Which of it a brain understands is between the owner
    and their brain, and rundesk being wrong about it is not a failure worth inventing.
    """
    given: dict = {}
    for one in pairs or []:
        said = one.strip()
        if said.startswith("{"):
            try:
                whole = json.loads(said)
            except ValueError:
                raise ValueError(f"'{said}' starts like an object and is not one")
            if not isinstance(whole, dict):
                raise ValueError(f"'{said}' is not a set of settings")
            given.update(whole)
            continue
        key, sep, value = said.partition("=")
        if not sep or not key.strip():
            raise ValueError(f"'{said}' is not <key>=<value>, nor an object")
        try:
            given[key.strip()] = json.loads(value)
        except ValueError:
            given[key.strip()] = value
    return given


def cmd_ask(args: argparse.Namespace, agents) -> int:
    """One turn for this agent, streamed to this terminal.

    It runs **here**, in the terminal that asked, rather than inside the agent's gateway —
    for the same reason a schedule run by hand does: there is nothing to ask a gateway
    with yet, and inventing one is not what this is for. Ending this command ends the
    brain and everything it started, because the whole tree is its own process group.

    What is shown and what is written down are not the same thing. The account keeps every
    record, whole; the terminal gets the answer, with what the brain was doing beside it —
    and never a tool's output, which can be a file's contents, a private path or a
    credential, and is not this command's to put on somebody's screen.
    """
    name, prompt = args.name, args.prompt
    if not name or not prompt:
        print("ask: WHO AND WHAT — say which agent, and what to ask it", file=sys.stderr)
        print('        for example: rundesk ask ava "what changed today?"', file=sys.stderr)
        return 1
    if not agents.exists(name):
        print(f"{name}: NO SUCH AGENT — nothing of that name has been made", file=sys.stderr)
        print(f"        make it: rundesk add {name} --provider <provider>", file=sys.stderr)
        return 1
    reaches = agents.chosen(name)
    named = args.provider or reaches.get("provider")
    if not named:
        print(f"{name}: NO BRAIN — nothing says which one answers for this agent",
              file=sys.stderr)
        print(f"        say which: rundesk add {name} --provider <provider>", file=sys.stderr)
        print(f"        or just this turn: rundesk ask {name} \"…\" --provider <provider>",
              file=sys.stderr)
        return 1
    try:
        settings = _given(getattr(args, "settings", None)) or reaches.get("settings")
    except ValueError as why:
        print(f"{name}: NOT ASKED — {why}", file=sys.stderr)
        return 1

    said = _Shown()
    try:
        outcome = asyncio.run(turn.carry(
            name, prompt, named,
            model=args.model or reaches.get("model"),
            settings=settings,
            posture=provider.READ if args.read_only else provider.WORK,
            conversation=args.conversation or turn.TERMINAL,
            fresh=args.fresh,
            watching=said,
            steering=_typed() if args.steer else None,
            preface=args.says,
        ))
    except provider.NotRunnable as why:
        print(f"{name}: NO BRAIN THERE — {why}", file=sys.stderr)
        print(f"        what stands in the way: rundesk doctor {name}", file=sys.stderr)
        return 1
    said.done()
    print(f"        {name}/{outcome.run} — {_cost(outcome.tokens)}", file=sys.stderr)
    if not outcome.ok:
        print(f"{name}: TURN FAILED — {outcome.why or outcome.reason}", file=sys.stderr)
        # What the brain said went wrong, on the screen rather than only in a file. It is
        # kept apart from what the brain *reported* — that is the whole point of the two
        # streams — but keeping it apart is not the same as keeping it secret, and a turn
        # that failed with its one actionable line filed somewhere nobody looks is a turn
        # somebody is stuck on.
        for line in outcome.trouble[-_TROUBLE_LINES:]:
            print(f"        {line}", file=sys.stderr)
        print(f"        the whole of it: rundesk agents {name}", file=sys.stderr)
    return 0 if outcome.ok else 1


async def _typed():
    """Whatever else is typed while the turn runs, a line at a time.

    Read off a thread, because reading a terminal blocks and the turn is running on this
    loop — a blocking read here would stop the very thing the words are meant to reach.
    Ends when the input does, which closes what rundesk is saying and lets the brain
    finish.
    """
    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            return
        said = line.strip()
        if said:
            yield said


class _Shown:
    """A turn as it happens, on a terminal.

    The answer goes to stdout so it can be piped; everything else goes to stderr, so what
    comes out of `rundesk ask ava "…" > answer.txt` is the answer and not a commentary
    around it.
    """

    def __init__(self):
        self._answered = False

    def __call__(self, said: dict) -> None:
        kind = said.get("type")
        if kind == "text":
            self._answered = True
            sys.stdout.write(said.get("text") or "")
            sys.stdout.flush()
        elif kind == "tool":
            did = said.get("did") or "using"
            print(f"        · {did} {said.get('name') or ''}".rstrip(), file=sys.stderr)
        elif kind == "result" and not said.get("ok"):
            print("        · that did not work", file=sys.stderr)

    def done(self) -> None:
        if self._answered:
            sys.stdout.write("\n")
            sys.stdout.flush()


def _cost(tokens: dict) -> str:
    """What a turn cost, or that nobody said — never a cost of nothing (R-USE-7)."""
    if not tokens.get("reported"):
        return "what it cost was never reported"
    said = (f"{tokens.get('input', 0)} in, {tokens.get('output', 0)} out, "
            f"{tokens.get('cached', 0)} cached")
    return f"{said}, {tokens['model']}" if tokens.get("model") else said


def cmd_doctor(args: argparse.Namespace, gateways, agents) -> int:
    """Say what stands between an agent and a working turn (R-AGT-11).

    Starts no provider and changes nothing (R-AGT-12): an owner asking what is wrong is
    usually asking because something already is, and a check that repaired what it found
    would answer a different question the next time it was asked.
    """
    names = [args.name] if args.name else agents.known()
    if not names:
        print("no agents")
        return 0
    worst = 0
    for name in names:
        try:
            said = agents.diagnosed(name, runnable=provider.program)
        except agents.NotAnAgentName as why:
            print(f"{name}: INVALID NAME — {why}", file=sys.stderr)
            worst = 1
            continue
        if not said:
            print(f"{name}: READY")
            continue
        worst = 1
        print(f"{name}: NOT READY", file=sys.stderr)
        for one in said:
            print(f"        {one.said}: {one.about}", file=sys.stderr)
    return worst


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
    now = gateways.standing(name, whose.run)
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
    taken = gateways.forget(name, where=whose.run, schedules=whose.schedules,
                            logs=whose.logs, history=True)
    if agents.exists(name):
        taken += agents.forget(name)
    if not had_job and not taken:
        print(f"{name}: NOTHING TO REMOVE — no job, and nothing kept under that name")
        return 0
    print(f"{name}: REMOVED")
    print("        its home, its log and everything it did went with it")
    return 0


def cmd_restart(args: argparse.Namespace, gateways, machine, agents) -> int:
    return _stand_down(args, gateways, machine, agents, "restart")


def _gone(name: str, gateways, agents, patience: float | None = None) -> bool:
    """Has this gateway actually stopped? Asked of the gateway, not of the machine.

    The patience resolves here, not in the signature — see `_came_up`.
    """
    deadline = time.monotonic() + (CYCLE_PATIENCE if patience is None else patience)
    while time.monotonic() < deadline:
        if not _standing(name, gateways, agents).running:
            return True
        time.sleep(LOOK_AGAIN_SECONDS)
    return not _standing(name, gateways, agents).running


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
                now = _standing(name, gateways, agents)
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
                if not _gone(name, gateways, agents):
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
            now = _standing(name, gateways, agents)
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
            up = _came_up(name, gateways, agents)
            if up is None:
                print(f"{name}: FAILED — stopped, but did not restart.", file=sys.stderr)
                print(f"         why: rundesk logs {name}", file=sys.stderr)
                worst = 1
                continue
            print(f"{name}: RESTARTED (pid {up.pid})")
        elif not _gone(name, gateways, agents):
            print(f"{name}: FAILED — still running after stop request", file=sys.stderr)
            worst = 1
        else:
            print(f"{name}: STOPPED")
    return worst


def cmd_agents(args: argparse.Namespace, gateways, machine, agents) -> int:
    """Every agent, and what each is doing. The table you look at first.

    Answered by the gateways themselves rather than by the machine, because the machine
    cannot tell a gateway that is working from one that is up and stuck (R-GW-9).

    A gateway that has been running since before there were agents is listed too, marked
    as having none. Leaving it out would be the worst of both: still running, still holding
    a name, and invisible to the one command that says what this install has.
    """
    if args.name:
        return _one_agent(args.name, gateways, machine, agents)
    has_supervisor = machine.available()
    described = set(machine.described()) if has_supervisor else set()
    found = {name: _standing(name, gateways, agents)
             for name in _every_name(gateways, machine, agents)}
    if not found:
        print("no agents")
        print("        make one:  rundesk add <agent>")
        return 0
    rows, orphaned = [], []
    for name in sorted(found):
        it = found[name]
        if not agents.exists(name):
            orphaned.append(name)
        # Whether the supervisor is keeping this gateway is asked of the supervisor. A
        # job description sitting in a directory is not a job being kept, and the two
        # come apart exactly when something has gone wrong — which is when it is read.
        try:
            kept = has_supervisor and name in described and machine.loaded(name)
        except machine.Unsure:
            kept = None   # asked, and not told — which is not the same as "no"
        doing = gateways.what_is_running(name, agents.resolved(name).run) if it.running else []
        # A loaded job is one fact; the gateway process and PID are another (R-GW-34).
        # Calling the first "supervised" claimed a relationship the machine never proved:
        # a manually started same-name process can coexist with a loaded dormant job.
        job = "LOADED" if kept else ("UNKNOWN" if kept is None else "NOT LOADED")
        rows.append((
            # The name, and only the name. A marker in this cell makes the column stop
            # holding what it says it holds — anything reading the table by name stops
            # finding one, which is exactly how CI came to report a running gateway as
            # never started. Which of them have no agent is said under the table, where
            # there is room to say what to do about it.
            name,
            ("WEDGED" if it.stale else "RUNNING") if it.running else "STOPPED",
            str(it.pid) if it.running else "-",
            _how_long(it.started) if it.running else "-",
            job,
            _version_of(it),
            (f"{len(doing)} ({', '.join(sorted(doing))})" if doing else "idle") if it.running else "-",
            # What never finished, counted where somebody looks (R-GW-39). The store
            # answering that question has existed since work could be interrupted at
            # all, and nothing in the product ever read it back: "what did not finish"
            # meant reading JSON out of a directory by hand, during an incident.
            str(len(gateways.what_was_interrupted(name, agents.resolved(name).schedules)) or "-"),
        ))
    _as_table(("AGENT", "STATE", "PID", "UPTIME", "LAUNCHD JOB", "VERSION", "WORK", "UNFINISHED"),
              rows)
    if orphaned:
        print()
        print(f"no agent yet — running since before there were any: {', '.join(orphaned)}")
        print(f"  give one an agent:  rundesk add {orphaned[0]}")
    return 0


def _one_agent(name: str, gateways, machine, agents) -> int:
    """What one agent is, and every place it resolves.

    The paths are the point. Which install, which run state, which schedules and which log
    are authoritative is otherwise something an owner works out by reading the source, and
    it is exactly what they need when a supervised agent and a command disagree.
    """
    try:
        where_it_is = agents.paths(name)
    except agents.NotAnAgentName as why:
        print(f"{name}: INVALID NAME — {why}", file=sys.stderr)
        return 1
    if not agents.exists(name):
        print(f"{name}: NO SUCH AGENT", file=sys.stderr)
        print(f"        what there is:  rundesk agents", file=sys.stderr)
        return 1
    it = _standing(name, gateways, agents)
    print(f"{name}: " + (("WEDGED" if it.stale else f"RUNNING (pid {it.pid})")
                         if it.running else "STOPPED"))
    _as_table(("WHAT", "WHERE"),
              [(what, str(at)) for what, at in sorted(where_it_is.items())])
    # What never finished, with the time and the reason for each (R-GW-39). Told apart by
    # whether rundesk could show the work was definitely gone: one of them is over, and
    # the other may still be running with nobody owning it, which is a different problem
    # and a different thing to do about it.
    unfinished = gateways.what_was_interrupted(name, agents.resolved(name).schedules)
    if unfinished:
        print()
        _as_table(("UNFINISHED", "AT", "ENDED", "WHY"), [
            (work, str(how.get("at", "-")),
             "yes" if how.get("ended") else "unproven", str(how.get("why", "-")))
            for work, how in sorted(unfinished.items())
        ])
    return 0


def cmd_status(_args: argparse.Namespace, gateways, machine, agents) -> int:
    """How rundesk itself is on this machine — not what it is running.

    Two questions, two commands. `agents` answers "what do I have and what is it doing";
    this answers "is the thing that runs them fit". They were one command answering
    neither, because a list of gateways says nothing about whether the install behind them
    can start one.
    """
    unfit = gateways.fitness(REPO_ROOT)
    try:
        supervisor = "yes" if machine.available() else "no — nothing keeps an agent up here"
    except Exception:                                    # pragma: no cover - defensive
        supervisor = "?"
    _as_table(("WHAT", "IS"), [
        ("version", __version__),
        ("install", str(REPO_ROOT)),
        ("fit to run", "yes" if not unfit else f"no — {unfit}"),
        ("supervisor", supervisor),
        ("agents", str(len(agents.known()))),
    ])
    return 1 if unfit else 0


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


def cmd_channels(args: argparse.Namespace, gateways, agents) -> int:
    """The surfaces an agent is reachable on — list them, or change them."""
    if not agents.exists(args.name):
        print(f"{args.name}: NO SUCH AGENT", file=sys.stderr)
        print("        what there is:  rundesk agents", file=sys.stderr)
        return 1
    # What a channel may be called is checked here, the way an agent's name is checked
    # before any verb acts on it. A channel's name becomes a directory, so one that could
    # climb out of where channels are kept is refused — and refused in our words, because
    # every other verb answers that way and a traceback is not an answer.
    named = getattr(args, "channel", None)
    if named is not None:
        try:
            gateways.checked(named)
        except gateways.NotAName as why:
            print(f"{args.name}/{named}: INVALID NAME — {why}", file=sys.stderr)
            return 1
    whose = agents.paths(args.name)["agent"]
    act = getattr(args, "act", None)
    if act == "add":
        return _add_channel(args, gateways, agents, whose)
    if act == "remove":
        return _remove_channel(args, gateways, agents, whose)
    if act == "show":
        return _show_channel(args, gateways, agents, whose)
    if act == "instructions":
        return _channel_instructions(args, gateways, agents, whose)
    return _list_channels(args, gateways, agents, whose)


def _add_channel(args: argparse.Namespace, gateways, agents, whose) -> int:
    """Put this agent on a channel, once the channel has proved it works (R-CAD-9).

    In this order, and the order is the requirement: the kind resolves, somebody is
    allowed, the adapter connects and reports what it can see, and only then is anything
    written. An agent whose channel is misconfigured finds out while a person is standing
    at the terminal, rather than at three in the morning when somebody asks it something.
    """
    if not [one for one in args.allow if one]:
        # The grammar already refuses the flag being absent. This catches it being there
        # and empty, which allows exactly as many people. Never defaulted, and there is
        # deliberately no way to say "anybody" — that is the shortest path to the worst
        # outcome this product has (R-CAD-10).
        print(f"{args.name}/{args.channel}: NOT ADDED — nobody is allowed to use it",
              file=sys.stderr)
        print(f"        say who:  rundesk channels {args.name} add {args.channel} "
              f"--kind {args.kind} --allow <user>", file=sys.stderr)
        return 1
    try:
        at = channel.program(args.kind)
    except channel.NotRunnable as why:
        print(f"{args.name}/{args.channel}: NOT ADDED — {why}", file=sys.stderr)
        return 1

    # Somewhere for the check to work in, under the name that was typed. What each
    # channel is finally given is made below, once the adapter has said what it reached.
    home = agents.channel_home(args.name, args.channel)
    home.mkdir(parents=True, exist_ok=True)
    # What follows `--` is taken off before the parser sees it, for the same reason a
    # schedule's program is: a tail with an option in it is unparseable on the oldest
    # Python this runs on.
    carried = list(args.options) + list(getattr(args, "handed_on", []))
    said = asyncio.run(channel.checked(at, carried, channel.environment(
        home=agents.paths(args.name)["run"], channel=args.channel, agent=args.name,
        channel_home=home, allow=args.allow, checking=True)))
    if not said["ok"]:
        # Nothing is written for a channel that has not proved itself, and the adapter's
        # own words are the whole of the owner's diagnosis.
        print(f"{args.name}/{args.channel}: NOT ADDED — {said['why'] or 'it could not be reached'}",
              file=sys.stderr)
        return 1
    # **What one `add` makes is the adapter's to say** (R-CAD-15). A platform is rarely
    # one place — Discord has private messages and rooms full of people, and they are not
    # the same thing to talk in — so an adapter reports the kinds of place its options
    # actually reached and each becomes a channel of its own. One that reports none gets
    # exactly one channel, under the name that was typed, as every adapter did before.
    making = said[channel.SHAPES] or [{
        channel.SHAPE_AT: "", "settings": said["settings"],
        "describes": said["describes"], channel.FILLS: [], channel.INSTRUCTIONS: ""}]
    named = []
    for shape in making:
        one = args.channel + (f"-{shape[channel.SHAPE_AT]}" if shape[channel.SHAPE_AT] else "")
        try:
            gateways.checked(one)
        except gateways.NotAName as why:
            print(f"{args.name}/{one}: NOT ADDED — {why}", file=sys.stderr)
            return 1
        if channel.of(whose, one) is not None:
            # Checked for every one of them *before* any is written, so a second shape
            # colliding does not leave the first half-added.
            print(f"{args.name}/{one}: EXISTS — remove it first, or use a different name",
                  file=sys.stderr)
            return 1
        named.append((one, shape))
    unlogged = 0
    for one, shape in named:
        # **Its own home, under its own name** (R-CAD-15). The check ran under the name
        # that was typed, which is the right place for a question asked before any channel
        # exists — but what a channel is *given* at start-up is the home of the name it was
        # written under, and one `add` may write several. Made here, so a channel whose
        # name gained a suffix is not handed a directory that was never created: the token
        # an owner put beside it, and anything a person attaches, both live there.
        agents.channel_home(args.name, one).mkdir(parents=True, exist_ok=True)
        if not channel.remember(whose, one, args.kind, args.allow,
                                settings=shape["settings"], secret=said["secret"],
                                describes=shape["describes"], says=shape[channel.INSTRUCTIONS],
                                fills=shape[channel.FILLS]):
            print(f"{args.name}/{one}: NOT ADDED — the record could not be written",
                  file=sys.stderr)
            return 1
        unlogged |= _note(gateways, args.name, f"channel '{one}' added ({args.kind})",
                          agents.resolved(args.name))
        print(f"{args.name}/{one}: ADDED — {shape['describes'] or args.kind}")
    if not any(one == args.channel for one, _ in named):
        # The check's own directory, when no channel ended up under that name. Removed only
        # if it is empty, so an owner who had already put a token in it keeps it — and is
        # told where it now belongs rather than left to find out when nothing connects.
        with contextlib.suppress(OSError):
            home.rmdir()
        if home.is_dir():
            print(f"        {home} is not empty — what is in it belongs beside "
                  f"{', '.join(one for one, _ in named)} now")
    if len(named) > 1:
        # Said out loud, because they were made together and share the one allow-list that
        # was typed — and the whole reason they are separate channels is that a room and a
        # private conversation usually should not.
        print(f"        {len(named)} channels, one for each kind of place — "
              f"each has its own allowed list and its own instructions")
    if not gateways.standing(args.name, agents.resolved(args.name).run).running:
        # An agent that is not running is not reachable, and saying so here is the
        # difference between a channel that is quiet and one that is deaf (R-CAD-8).
        print(f"        not reachable yet:  rundesk start {args.name}")
    return unlogged


def _remove_channel(args: argparse.Namespace, gateways, agents, whose) -> int:
    if not channel.forget(whose, args.channel):
        print(f"{args.name}/{args.channel}: NOT FOUND — no channel by that name",
              file=sys.stderr)
        return 1
    unlogged = _note(gateways, args.name, f"channel '{args.channel}' removed",
                     agents.resolved(args.name))
    print(f"{args.name}/{args.channel}: REMOVED")
    return unlogged


def _channel_instructions(args: argparse.Namespace, gateways, agents, whose) -> int:
    """What this agent is told about the situation it is answering in (R-CH-22).

    Checked before it is written, and that is the point of writing it here rather than by
    hand: a name misspelled in a template is an instruction that goes quietly blank at
    every turn from then on, and says nothing about having done so. With nothing to set,
    this shows what is already there — so an owner can read back exactly what their agent
    will be told before anyone says anything to it.
    """
    it = channel.of(whose, args.channel)
    if it is None:
        print(f"{args.name}/{args.channel}: NOT FOUND — no channel by that name",
              file=sys.stderr)
        return 1
    if args.said is None:
        standing = it.get(channel.INSTRUCTIONS)
        if not standing:
            print(f"{args.name}/{args.channel}: NO INSTRUCTIONS — rundesk says where it "
                  f"is and no more")
            print(f"        write your own:  rundesk channels {args.name} instructions "
                  f"{args.channel} \"<text>\"")
            return 0
        print(standing)
        return 0
    wrong = channel.wrong_with_instructions(args.said, it.get(channel.FILLS)) if args.said else ""
    if wrong:
        print(f"{args.name}/{args.channel}: NOT CHANGED — {wrong}", file=sys.stderr)
        return 1
    written = channel.tell(whose, args.channel, args.said)
    if written is None:
        print(f"{args.name}/{args.channel}: NOT FOUND — no channel by that name",
              file=sys.stderr)
        return 1
    if not written:
        print(f"{args.name}/{args.channel}: NOT CHANGED — the record could not be written",
              file=sys.stderr)
        return 1
    unlogged = _note(gateways, args.name,
                     f"channel '{args.channel}' was given instructions"
                     if args.said else f"channel '{args.channel}' had its instructions taken off",
                     agents.resolved(args.name))
    print(f"{args.name}/{args.channel}: "
          + ("INSTRUCTED" if args.said else "INSTRUCTIONS TAKEN OFF"))
    # **New conversations, not the next turn.** A brain is told this where its conversation
    # is *opened*, which is the only place a brain of this shape reads it — measured against
    # a real one, where the same instruction was obeyed at the start of a thread and ignored
    # on every resume after. So an owner rewording something must be told which
    # conversations it reaches, or they will reword it, watch the open one carry on exactly
    # as before, and have nothing to tell them why.
    print("        in effect for new conversations — say /new to start one")
    return unlogged


def _show_channel(args: argparse.Namespace, gateways, agents, whose) -> int:
    """One channel, and who may reach the agent through it.

    The secret is named as present and never shown (R-CAD-12). Nothing here has ever held
    one — the record keeps the name of a variable the adapter itself said it read, so
    there is no value to print by accident.
    """
    it = channel.of(whose, args.channel)
    if it is None:
        print(f"{args.name}/{args.channel}: NOT FOUND — no channel by that name",
              file=sys.stderr)
        return 1
    # However many a surface needs — one that opens a connection with one credential and
    # calls its API with another names both, and an owner has to be told which of them is
    # missing rather than that "the secret" is.
    named = (it.get("secret") or {}).get("env") or []
    named = [named] if isinstance(named, str) else named
    rows = [
        ("kind", str(it.get("kind", "-"))),
        ("points at", str(it.get("describes") or "-")),
        ("allowed", ", ".join(it.get("allow") or []) or "nobody"),
        ("secret", ", ".join(
            f"{one} — {'present' if os.environ.get(one) else 'not set'}" for one in named)
            or "none needed"),
        ("instructions", str(it.get(channel.INSTRUCTIONS)
                     or "nothing of its own — rundesk says where it is")),
        ("reachable", "yes" if gateways.standing(
            args.name, agents.resolved(args.name).run).running
            else "no — the agent is not running"),
    ]
    _as_table(("WHAT", "IS"), rows)
    return 0


def _list_channels(args: argparse.Namespace, gateways, agents, whose) -> int:
    reachable = channel.known(whose)
    if not reachable:
        print(f"{args.name}: NO CHANNELS")
        print(f"        put it on one:  rundesk channels {args.name} add <channel> "
              f"--kind <kind> --allow <user>")
        return 0
    up = gateways.standing(args.name, agents.resolved(args.name).run).running
    _as_table(("CHANNEL", "KIND", "POINTS AT", "ALLOWED", "REACHABLE"), [
        (name, str(it.get("kind", "-")), str(it.get("describes") or "-"),
         str(len(it.get("allow") or [])), "yes" if up else "no")
        for name, it in sorted(reachable.items())
    ])
    return 0


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
    whose = agents.resolved(args.name)
    try:
        if act == "add":
            return _add_schedule(args, gateways, whose)
        if act == "run":
            return _run_schedule(args, gateways, whose)
        if act in ("remove", "on", "off"):
            return _change_schedule(args, gateways, whose, act)
        return _list_schedules(args, gateways, whose)
    except _gateway.Unreadable as why:
        # Answered in one place because every path here reads the same file, and each of
        # them turned "this cannot be read" into "there is nothing there": the listing said
        # NO SCHEDULES and exited zero, and the changes wrote an empty list over a file that
        # still held every schedule as recoverable text (R-SCH-17, R-SCH-18).
        print(f"{args.name}: SCHEDULES UNREADABLE — {why}", file=sys.stderr)
        print("        nothing was changed — move the file aside or repair it",
              file=sys.stderr)
        return 1


def _note(gateways, name: str, said: str, whose=None) -> int:
    """Say what was changed, in the log of the agent it was changed for, and say so out
    loud when it could not be written (R-GW-37).

    A schedule that appears or vanishes is as much a part of what happened to an agent
    as anything it ran, and the log is the only account that outlives the gateway. The
    change itself stands either way — it is already on disk by the time this is called,
    and unwinding a good mutation because its audit line failed would be the worse of
    the two outcomes. What must not happen is the command reporting a plain success:
    that is a mutation and its history disagreeing, with nobody told.

    The code it returns is what the command exits with, so a caller adds it to nothing
    and simply returns it.
    """
    logs = whose.logs if whose else None
    why = gateways.note(name, said, logs)
    if why is None:
        return 0
    print(f"{name}: WARNING — change applied, but not logged: "
          f"{gateways.log_path(name, logs)}: {why}", file=sys.stderr)
    return 1


def _add_schedule(args: argparse.Namespace, gateways, whose) -> int:
    from rundesk import schedule

    try:
        made = schedule.Schedule(args.schedule, args.when)
    except schedule.NotASchedule as why:
        print(f"{args.name}/{args.schedule}: NOT ADDED — {why}", file=sys.stderr)
        return 1
    if not process.located(args.run[0]):
        # Refused here rather than discovered at three in the morning. The gateway runs
        # with almost no PATH, so a program named rather than located resolves in the
        # shell that typed it and nowhere else (R-PROC-2) — and a schedule that cannot
        # start looks exactly like one that has simply never come due.
        print(f"{args.name}/{args.schedule}: NOT ADDED — '{args.run[0]}' is a name, not a location; "
              f"give the full path (try: command -v {args.run[0]})", file=sys.stderr)
        return 1
    # Read and written under one lock: two `add`s racing would otherwise each read the
    # same list and each write theirs back, and one schedule would simply never exist
    # while both commands reported success.
    with gateways.changing_schedules(args.name, whose.schedules) as keeping:
        if any(one.get("name") == args.schedule for one in keeping if isinstance(one, dict)):
            print(f"{args.name}/{args.schedule}: EXISTS — remove it first, or use a different name",
                  file=sys.stderr)
            return 1
        keeping.append({"name": args.schedule, "when": args.when, "run": list(args.run)})
    unlogged = _note(gateways, args.name, f"schedule '{args.schedule}' added ({args.when})", whose)
    # Both named, because a schedule belongs to one agent and the success line saying only
    # its own name could not tell you it had landed on the wrong one.
    print(f"{args.name}/{args.schedule}: ADDED — next {schedule.describe(made, datetime.now())}")
    return unlogged


def _change_schedule(args: argparse.Namespace, gateways, whose, act: str) -> int:
    with gateways.changing_schedules(args.name, whose.schedules) as keeping:
        found = [one for one in keeping
                 if isinstance(one, dict) and one.get("name") == args.schedule]
        if not found:
            print(f"{args.name}/{args.schedule}: NOT FOUND — no schedule by that name",
                  file=sys.stderr)
            return 1
        if act == "remove":
            keeping[:] = [one for one in keeping if one is not found[0]]
            said, told = "REMOVED", f"schedule '{args.schedule}' removed"
        else:
            found[0]["enabled"] = act == "on"
            said = "ON" if act == "on" else "OFF"
            told = f"schedule '{args.schedule}' turned {said.lower()}"
    unlogged = _note(gateways, args.name, told, whose)
    print(f"{args.name}/{args.schedule}: {said}")
    return unlogged


def _run_schedule(args: argparse.Namespace, gateways, whose) -> int:
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

    wanted, _ = gateways.scheduled(args.name, whose.schedules)
    found = [one for one in wanted if one.name == args.schedule]
    if not found:
        print(f"{args.name}/{args.schedule}: NOT FOUND — no schedule by that name",
              file=sys.stderr)
        return 1
    one = found[0]
    if not one.run:
        print(f"{args.name}/{args.schedule}: NOTHING TO RUN — it names no program", file=sys.stderr)
        return 1
    was_due = schedule.describe(one, datetime.now())
    print(f"{args.name}/{args.schedule}: RUNNING BY HAND — {' '.join(one.run)}")
    said = asyncio.run(process.run(
        list(one.run),
        # Through what was passed in, never the module. Reaching for the real one here
        # read the machine's own directories from inside a suite that had redirected
        # nothing, which is the isolation every other line in this file keeps.
        env=process.environment(whose.run or gateways.home()),
        on_line=print,
    ))
    print(f"{args.name}/{args.schedule}: "
          + ("RAN" if said.ok else f"FAILED — {said.reason}")
          + (f" ({said.code})" if said.code else ""))
    # Said out loud, because the whole point of running one by hand is that it changes
    # nothing about when it runs on its own.
    print(f"        next, unchanged: {was_due}")
    return 0 if said.ok else 1


def _became(outcome: str, up: bool) -> str:
    """What a schedule's last firing really came to, given whether its gateway is running.

    The one place the durable word and what is running are put together. `started` is
    written before the run begins and nothing rewrites it if the gateway dies, so read
    on its own it is indistinguishable from work happening right now — while the answer
    was already on disk, in the record saying no gateway of that name is up (R-SCH-24).
    """
    return _gateway.INTERRUPTED if outcome == _gateway.STARTED and not up else outcome


def _list_schedules(args: argparse.Namespace, gateways, whose) -> int:
    """What this gateway runs on its own, when each next runs, and what became of it.

    This gateway's, and no other's: a gateway's schedules are its own, which is what
    makes one agent's schedules that agent's alone (R-SCH-13, R-SCH-14).
    """
    from rundesk import schedule

    wanted, refused = gateways.scheduled(args.name, whose.schedules)
    if not wanted and not refused:
        print(f"{args.name}: NO SCHEDULES")
        return 0
    now = datetime.now()
    ran = gateways.what_was_scheduled(args.name, whose.schedules)
    # A firing is written down before the run begins, so `started` on its own means only
    # that — and if no gateway of this name is up, nothing it started is still going. The
    # store is reconciled by the next gateway to claim the name (R-SCH-23); until one
    # does, showing the word as written presents dead work as in flight, which is the
    # first question asked after a crash answered wrongly (R-SCH-24).
    up = gateways.standing(args.name, whose.run).running
    rows = [(
        one.name,
        "OFF" if not one.enabled else "ON",
        one.when,
        schedule.describe(one, now),
        ran.get(one.name, {}).get("at", "-"),
        _became(ran.get(one.name, {}).get("outcome", "-"), up),
    ) for one in wanted]
    _as_table(("SCHEDULE", "STATE", "WHEN", "NEXT", "LAST RUN", "OUTCOME"), rows)
    for name, why in refused:
        print(f"{name or '(unnamed)'}: NOT UNDERSTOOD — {why}", file=sys.stderr)
    return 1 if refused else 0


def cmd_logs(args: argparse.Namespace, gateways, agents) -> int:
    """What a gateway has been saying. Reads the files, so a gateway that has gone can
    still be asked what happened (R-GW-18, R-GW-36).

    Every source, not one file. A failed start tells the owner to run this, and the line
    explaining it is as likely to be in the rotation behind the current log, or in what
    the machine captured before there was a logger at all, as in the tail of `.log` —
    so reading only the last file answered the question this command exists for with
    NO LOG while the answer sat beside it.
    """
    logs = agents.resolved(args.name).logs
    found = gateways.log_sources(args.name, logs, args.source)
    if not found:
        print(f"{args.name}: NO LOG — nothing written yet ({gateways.log_path(args.name, logs)})",
              file=sys.stderr)
        return 1
    # One gateway's own account is one stream that rotation happens to have cut up, so
    # it is put back together before the tail is taken; what the machine captured is a
    # different account of the same gateway, and each of those is tailed on its own.
    streams: list[tuple[str, list[str]]] = []
    for whose, path in found:
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError as why:
            # Every other verb answers in our words when it cannot do the thing. A log
            # that cannot be read is a thing to be told about, not a traceback.
            print(f"{args.name}: FAILED — could not read the log: {why}", file=sys.stderr)
            return 1
        if streams and streams[-1][0] == whose == gateways.GATEWAY_LOG:
            streams[-1][1].extend(lines)
        else:
            streams.append((whose, lines))
    shown = [(whose, lines[-args.lines:] if args.lines > 0 else []) for whose, lines in streams]
    shown = [(whose, lines) for whose, lines in shown if lines]
    labelled = len({whose for whose, _ in shown}) > 1
    for whose, lines in shown:
        for line in lines:
            print(f"{whose:<8}{line}" if labelled else line)
    return 0


#: What a verb calls the tail it carries and does not read. One name, so the verbs that
#: have one are found by looking at the parser rather than by being listed here.
CARRIED = "options"


def _carries_a_tail(parser: argparse.ArgumentParser) -> set:
    """Which verbs hand everything after `--` to something that is not rundesk.

    Walked off the parser, so a verb that grows one is covered the day it lands and no
    hand-kept copy of the list can come to disagree with it. A verb is one of these
    exactly when an action under it declares the tail as a positional.
    """
    carries = set()
    for verb, under in _offered(parser).items():
        for act in _offered(under).values():
            if any(not it.option_strings and it.dest == CARRIED for it in act._actions):
                carries.add(verb)
    return carries


def _offered(parser: argparse.ArgumentParser) -> dict:
    """The commands a parser offers, by name — its own sub-parsers, or none."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    return {}


def _handed_on(argv: list[str], carries: set) -> tuple[list[str], list[str]]:
    """Split what rundesk reads from what it only carries, for the verbs that carry one.

    Taken out **before** the parser rather than left to it, because argparse cannot do
    this on the oldest Python a fresh macOS ships: a tail with an option in it
    (`-- --room 1180`) is accepted on a current one and refused as an unrecognized
    argument on the floor version CI pins. A surface that works on the developer's machine
    and not on the user's is worse than one that does neither.

    Scoped to those verbs rather than done to every one, because argparse *can* carry a
    tail into a positional that is required and greedy — which is what a schedule's
    program is — and taking that one away from it would break the form it already
    accepts on both.
    """
    if not argv or argv[0] not in carries or "--" not in argv:
        return list(argv), []
    at = argv.index("--")
    return list(argv[:at]), list(argv[at + 1:])


def main(argv: list[str], gateways=None, machine=None, agents=None) -> int:
    """The command surface.

    What the commands act on is passed in rather than imported here, so this file knows
    the verbs and nothing about locks, records or process groups — and so every one of
    them is exercised without a gateway or a supervisor anywhere near it.
    """
    gateways = gateways if gateways is not None else _gateway
    machine = machine if machine is not None else _supervisor
    agents = agents if agents is not None else _agent
    parser = build_parser()
    argv, handed_on = _handed_on(argv, _carries_a_tail(parser))
    args = parser.parse_args(argv)
    args.handed_on = handed_on

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
    if args.command in PLANNED:
        return cmd_not_available(args.command, getattr(args, "act", None))
    if args.command == "version":
        return cmd_version(args)
    if args.command == "update":
        return cmd_update(args, gateways, machine, agents)
    if args.command == "uninstall":
        return cmd_uninstall(args)
    if args.command == "agents":
        return cmd_agents(args, gateways, machine, agents)
    if args.command == "add":
        return cmd_add(args, gateways, agents)
    if args.command == "doctor":
        return cmd_doctor(args, gateways, agents)
    if args.command == "ask":
        return cmd_ask(args, agents)
    if args.command == "serve":
        return cmd_serve(args, gateways, agents)
    if args.command == "start":
        return cmd_start(args, gateways, machine, agents)
    if args.command == "stop":
        return cmd_stop(args, gateways, machine, agents)
    if args.command == "remove":
        return cmd_remove(args, gateways, machine, agents)
    if args.command == "restart":
        return cmd_restart(args, gateways, machine, agents)
    if args.command == "status":
        return cmd_status(args, gateways, machine, agents)
    if args.command == "channels":
        return cmd_channels(args, gateways, agents)
    if args.command == "schedules":
        return cmd_schedules(args, gateways, agents)
    if args.command == "logs":
        return cmd_logs(args, gateways, agents)

    # Unreachable through argparse, which rejects an unknown command before this —
    # but a dispatch that silently returns 0 for a verb nobody handled is how a
    # command comes to exist and do nothing.
    print(f"rundesk: no handler for '{args.command}'", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
