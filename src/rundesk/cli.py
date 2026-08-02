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
import getpass
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rundesk import __version__, backups_home, data_home  # noqa: E402
from rundesk import agent as _agent  # noqa: E402
from rundesk import backup as backups  # noqa: E402
from rundesk import catalog  # noqa: E402
from rundesk import channel  # noqa: E402
from rundesk import config  # noqa: E402
from rundesk import dependencies  # noqa: E402
from rundesk import gateway as _gateway  # noqa: E402
from rundesk import migration  # noqa: E402
from rundesk import process  # noqa: E402
from rundesk import role  # noqa: E402
from rundesk import role_run as role_runs  # noqa: E402
from rundesk import provider  # noqa: E402
from rundesk import restart_request  # noqa: E402
from rundesk import schedule as schedules  # noqa: E402
from rundesk import script  # noqa: E402
from rundesk import skill  # noqa: E402
from rundesk import store  # noqa: E402
from rundesk import supervisor as _supervisor  # noqa: E402
from rundesk import turn  # noqa: E402
from rundesk import updater  # noqa: E402
from rundesk import update_request  # noqa: E402

#: The installer as published, for the one case where this install has lost its own:
#: removing rundesk is exactly when a broken install has to be removable.
PUBLISHED_INSTALLER = (
    "https://raw.githubusercontent.com/rundesk-ai/rundesk-cli/main/install.sh"
)

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

#: How long install health waits for backup storage to answer. A cloud-backed directory
#: can block inside the operating system indefinitely; status remains useful without it
#: and reports that one answer as unavailable (R-BKP-28).
BACKUP_STATUS_PATIENCE = 1.0

#: How long a command whose whole job is the backups waits for the same directory. Longer
#: than the glance health takes, because here the listing *is* the answer and a slow disk
#: is not an unreachable one — but still bounded, because the directory that blocks never
#: answers at all, and a command that waits forever cannot even name what it is waiting on
#: (R-BKP-29).
BACKUP_PATIENCE = 20.0

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
    "resume": ("carry one run on from where it stopped", {}),
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
WHOSE = {"resume"}

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
    "<words>": "what to look for, in the words that were actually said",
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
        ("rundesk configure ava --provider claude",
         "change ava's default brain without replacing the agent"),
        ("rundesk add ava --provider /opt/my-brain --model fast-1 --set effort=high",
         "one answered by a brain you wrote, told which model and how hard to think"),
        ("rundesk start ava",
         "have the machine keep it running, and bring it back when it falls over"),
    ]),
    ("a channel", [
        ("rundesk channels ava add discord --kind discord --allow 123456789012345678",
         "reachable in direct messages and in every room it has been invited to"),
        ("", "writes two channels — discord-dms and discord-rooms — each with its own "
             "allowed list, settings and instructions"),
        ("rundesk channels ava add discord --kind discord --allow 123456789012345678 -- --dm",
         "direct messages only; --server <id> or --channel <id> narrows the rooms instead"),
        ('rundesk channels ava instructions discord-rooms "You are {agent} in {where.channel}. Others read this, so keep it short."',
         "what it is told about where it is, before it reads a word of the message"),
        ("rundesk channels ava",
         "what it is reachable on, and whether it is reachable at all"),
    ]),
    ("a schedule", [
        ('rundesk schedules ava add nightly --when "0 3 * * *" --ask "summarise what changed today"',
         "at three every morning, one turn, in a conversation of its own"),
        ('rundesk schedules ava add nightly --when "0 3 * * *" --ask "check the deploy" --instructions "Nobody is watching."',
         "the same, told it is running unattended before it reads a word"),
        ('rundesk schedules ava add weekly --when "0 9 * * 1" --ask "what is worth knowing?" --provider codex',
         "a different brain for a different schedule, on the same agent"),
        ("rundesk schedules ava add tidy --when \"0 4 * * *\" -- /usr/local/bin/tidy --quiet",
         "a program rather than a turn, by its full path"),
        ("rundesk schedules ava add tidy-up --at \"2026-07-28T09:00\" -- /usr/local/bin/tidy",
         "a script or command run once, at one moment, and never again"),
        ('rundesk schedules ava add report --at "2026-07-28T09:00" --ask "how did the migration go?" --to ops',
         "the same one moment, asking a turn and saying what it came to on a surface"),
        ("rundesk schedules ava --expired",
         "the one-time schedules that are over — which ran, and which never did"),
        ("rundesk schedules ava off nightly",
         "keep it, and stop it running"),
    ]),
    ("a role", [
        ("rundesk roles ava",
         "the specialists ava can hand heavy work to, and the runs it has admitted"),
        ('rundesk roles ava run development --target ~/code/exporter --label "csv export"',
         "one bounded task, run in that project under the role's own rules"),
        ("", "an agent hands work on from inside its own turn, and the brief arrives on "
             "standard input — the outcome, what it may do, and what done looks like"),
        ("rundesk roles ava show rol-3-vfs3",
         "one run: which role and revision, where it worked, and whether ava has reviewed it"),
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
              ("<agent>", "what one agent has cost")],
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
    # Not offered, because it is not a thing to type: an update hands the rest of its own
    # window to the release it just laid down, and this is how that release is told which
    # gateways are waiting (R-UPD-33). Hidden rather than absent, because argparse has to
    # accept it — the process on the other side of the handover is `rundesk update`.
    moved.add_argument(updater.CONTINUING, dest="after_replacing", metavar="<names>",
                       default=None, help=argparse.SUPPRESS)
    moved.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    moved.add_argument("--automatic", action="store_true", help=argparse.SUPPRESS)
    moved.add_argument("--status", action="store_true",
                       help="show the last queued update and its final outcome")

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
    # Standing instructions may be supplied at creation; `configure` changes them later.
    born.add_argument("--instructions", dest="says", metavar="<text>",
                      help="what every turn for this agent is told before it reads a prompt, "
                           "where neither the schedule nor the surface said — empty takes it off")

    configured = sub.add_parser(
        "configure", help="change an existing agent's durable defaults")
    configured.add_argument("name", nargs="?", metavar="<agent>", help="which agent")
    _brain(configured, "which brain answers by default")
    configured.add_argument(
        "--instructions", dest="says", metavar="<text>",
        help="what every turn is told by default — empty takes it off")

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
    cycled.add_argument(
        "--force", action="store_true",
        help="restart now even when doing so interrupts active work",
    )
    cycled.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)

    listed_agents = sub.add_parser("agents", help="every agent this install has, and what each is doing")
    listed_agents.add_argument("name", nargs="?", metavar="<agent>",
                               help="one agent — what it is, and where it keeps things")

    sub.add_parser("status", help="how rundesk itself is on this machine")

    sub.add_parser("config", help="how this install is configured, and where each value came from")

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
    # What can no longer happen, which the ordinary listing leaves out because it shows work
    # that still can. Kept out of the way rather than deleted: "did that run?" is asked long
    # after the fact, and `runs` alone does not name the schedule.
    listed.add_argument("--expired", action="store_true",
                        help="instead, the one-time schedules whose moment has gone — whether "
                             "each ran, or whether it passed while nothing was running")
    acts = listed.add_subparsers(dest="act", metavar="<action>")
    added = acts.add_parser("add", help="add a schedule")
    added.add_argument("schedule", metavar="<schedule>", help="what to call it, and what to name it by later")
    # **A repeating time or a single moment, and never both.** Cron has no year, so
    # `0 9 28 7 *` is every 28 July for ever and a single occurrence cannot be said in it at
    # all. Refused rather than ranked, the same way a program and a prompt are: a schedule
    # naming both would leave rundesk choosing, and the choice would be invisible afterwards.
    added.add_argument("--when", metavar="<cron>",
                       help="when it runs, over and over, as five cron fields — minute, hour, "
                            "day, month, weekday")
    added.add_argument("--at", dest="moment", metavar="<moment>",
                       help="instead of --when: the one moment it runs, on this machine's own "
                            "clock, as YYYY-MM-DDTHH:MM. It runs then and never again — a "
                            "moment is given, never a phrase like 'tomorrow at nine'")
    # **A schedule starts a program or asks a turn, and never both.** The two are one verb
    # because they are one thing to an owner — work that happens because the time came — and
    # the difference is only what the gateway does when it is due. Refused rather than
    # ranked: a schedule that named both would leave rundesk choosing, and the choice would
    # be invisible in the listing.
    added.add_argument("--ask", dest="prompt", metavar="<prompt>",
                       help="what to ask this agent when it is due, in quotes — a turn "
                            "rather than a program")
    # Two of the three a turn takes, and not `--set`: what a brain is told to run with has
    # no column on a schedule, and an option that could only ever refuse is worse in the
    # help than one that is absent. Written out rather than through `_brain` for that reason
    # alone — the spellings are the same because there is only one right spelling.
    added.add_argument("--provider", metavar="<provider>",
                       help="which brain answers this schedule, whatever the agent reaches "
                            "for otherwise")
    added.add_argument("--model", metavar="<model>",
                       help="which model, in that brain's own words")
    added.add_argument("--instructions", dest="says", metavar="<text>", default="",
                       help="standing instructions for the turn this schedule starts, told to "
                            "the brain apart from the prompt")
    # Where what this came to is said. Nothing at three in the morning has a person at the
    # other end, so the outcome has to reach where its owner already looks — and which place
    # that is, is the owner's to choose. Told nothing it went to *every* surface the agent had,
    # so two channels meant two notices about work that concerned one of them.
    added.add_argument("--to", dest="channel", metavar="<channel>",
                       help="which channel to say what this came to on, by the name it was "
                            "added under — the account and `schedules` say it either way")
    # Which place on that channel, in the surface's own word for one. Never read here: a
    # channel reaching a whole server has many rooms, and which of them an owner meant is
    # theirs to say rather than rundesk's to guess from whoever spoke last.
    added.add_argument("--in", dest="place", metavar="<where>",
                       help="which place on that channel to say it in, in that surface's "
                            "own words — for Discord: a room name or id, or on a DM "
                            "channel the person's user id (the same id as --allow) or the "
                            "DM channel id. Left out, it follows the conversation")
    # After `--`, taken off before the parser sees it, and never read here. It was a
    # required greedy positional, which argparse can carry a tail into on its own — but the
    # moment this verb grew options of its own, an option *inside* the tail was read as one
    # of them: `-- rundesk ask ava "…" --instructions "…"` set the schedule's instructions
    # and dropped them from what it would run. That is finding 31 again by another route, and
    # what stops it is splitting the tail off in front of argparse (see `_handed_on`), which
    # is what naming it `CARRIED` asks for.
    added.add_argument(CARRIED, nargs="*", metavar="<program>",
                       help="after `--`, the full path of what to start when it is due, and its "
                            "arguments — a bare name is refused, because a gateway runs with "
                            "almost no PATH")
    # **Everything `add` took, and only what is named moves.** The listing says what kind of
    # work a schedule is and when; this is where the prompt, the brain and where it reports
    # are read back, because they are sentences and paths and none of them fits a column.
    # Without it the only account of what a schedule does is the one an owner remembers
    # typing — and the edit below would destroy it unseen.
    shown = acts.add_parser("show", help="one schedule, and everything it was given")
    shown.add_argument("schedule", metavar="<schedule>",
                       help="which schedule, by the name it was added under")

    changed = acts.add_parser("edit", help="change an existing schedule, keeping what it has done")
    changed.add_argument("schedule", metavar="<schedule>",
                         help="which schedule, by the name it was added under")
    # Never `default=""` the way `add` spells the same option: not given and given as
    # nothing are different instructions here — leave it alone, and take it off — and one
    # default would make them the same keystroke.
    changed.add_argument("--when", metavar="<cron>",
                         help="a new repeating time, as five cron fields. Clears --at")
    changed.add_argument("--at", dest="moment", metavar="<moment>",
                         help="a new single moment, as YYYY-MM-DDTHH:MM. Clears --when, and "
                              "is refused once the clock has started this schedule — a moment "
                              "already used can never come round again (R-SCH-38)")
    changed.add_argument("--ask", dest="prompt", metavar="<prompt>",
                         help="what to ask instead. Turns a schedule that started a program "
                              "into one that asks a turn")
    changed.add_argument("--provider", metavar="<provider>",
                         help="which brain answers it now")
    changed.add_argument("--model", metavar="<model>", help="which model, in that brain's own words")
    changed.add_argument("--instructions", dest="says", metavar="<text>",
                         help="new standing instructions — given as \"\", it takes them off")
    changed.add_argument("--to", dest="channel", metavar="<channel>",
                         help="which channel to say what this came to on — given as \"\", it "
                              "stops reporting to one")
    changed.add_argument("--in", dest="place", metavar="<where>",
                         help="which place on that channel — given as \"\", it follows the "
                              "conversation again")
    changed.add_argument(CARRIED, nargs="*", metavar="<program>",
                         help="after `--`, a new program and its arguments. Turns a schedule "
                              "that asked a turn into one that starts a program")

    for act, what in (("remove", "take a schedule away"),
                      ("on", "let a schedule run"),
                      ("off", "keep a schedule but stop it running"),
                      ("run", "run a schedule now, whether or not it is due")):
        one = acts.add_parser(act, help=what)
        one.add_argument("schedule", metavar="<schedule>", help="which schedule, by the name it was added under")

    # What an agent has actually done. Read-only, and answered from what it keeps rather
    # than by starting a brain (R-USE-10) — so asking what a night's work cost is a
    # question, not a turn.
    listed_runs = sub.add_parser("runs", help="what an agent has run, and what became of each")
    listed_runs.add_argument("name", nargs="?", metavar="<agent>",
                             help="which agent — the name it was made under")
    listed_runs.add_argument("--most", type=int, default=20, metavar="<n>",
                             help="how many to show, newest first (default: 20)")

    cost = sub.add_parser("usage", help="what agents have cost, in tokens")
    cost.add_argument("name", nargs="?", metavar="<agent>",
                      help="one agent — every agent when left out")

    # Reading back what was said, newest first — the listing an agent uses on itself when a
    # conversation refers to work its own session never saw. Filters are the closed sets the
    # store already keeps, so `--source schedule` is what the clock did and nothing else.
    recent = sub.add_parser("messages", help="what was said, newest first")
    recent.add_argument("name", nargs="?", metavar="<agent>", help="which agent")
    recent.add_argument("--most", type=int, default=20, metavar="<n>",
                        help="how many to show, newest first (default: 20)")
    recent.add_argument("--since", type=int, metavar="<id>",
                        help="only what was said after this one, by the id shown beside it")
    recent.add_argument("--channel", metavar="<channel>",
                        help="only what was said on this channel, by the name it was added "
                             "under")
    recent.add_argument("--conversation", metavar="<where>",
                        help="only what was said in one place on it — the direct message or "
                             "room, either as the WHERE column prints it or in the "
                             "platform's own word alone")
    # The choices are read off the store's own closed sets rather than restated, and the
    # reference prints them, so neither says the list twice.
    recent.add_argument("--author", choices=list(store.AUTHORS), metavar="<kind>",
                        help="only what this kind of author said")
    # Kind and identity are two questions, and one flag answering both is how `--author
    # user` came to return rows whose WHO column shows a platform id. This one is the
    # identity in that column, and is not a closed set: it is whatever the surface calls
    # one person.
    recent.add_argument("--who", metavar="<identity>",
                        help="only what this one person said, as the WHO column names them")
    recent.add_argument("--source", choices=list(store.SOURCES), metavar="<how>",
                        help="only messages belonging to work admitted this way")

    # Searching by the words in something, which is the one question a listing cannot
    # answer: what an agent was told about a thing, whichever surface it arrived on.
    looked_for = sub.add_parser("search", help="what was said, by the words in it")
    looked_for.add_argument("name", nargs="?", metavar="<agent>", help="which agent")
    looked_for.add_argument("words", nargs="?", metavar="<words>",
                            help="what to look for, in the words that were actually said")
    looked_for.add_argument("--most", type=int, default=20, metavar="<n>",
                            help="how many to show (default: 20)")

    said = sub.add_parser("logs", help="what an agent has been saying")
    said.add_argument("name", metavar="<agent>", help="whose log")
    said.add_argument("-n", "--lines", type=int, metavar="<lines>", default=LOG_LINES,
                      help="how many of the last lines to show, from each source")
    said.add_argument("--source", choices=list(_gateway.LOG_SOURCES),
                      default=_gateway.EVERY_LOG, metavar="<source>",
                      help="whose lines to show — what the gateway wrote, or what the "
                           "machine caught that never reached it")

    # **No optional positional in front of the actions.** `agents <agent>` and subcommands
    # under one verb cannot both exist: argparse matches the agent's name against the
    # action names and dies with `invalid choice`. So the bare form takes no name at all
    # and every action names its agent itself, which reads better anyway — the catalog is
    # about the machine and a grant is about one agent.
    known = sub.add_parser("skills", help="the skills on this machine, and who has which")
    known.add_argument("--lay-down", action="store_true", dest="lay_down",
                       help=argparse.SUPPRESS)   # the installer's; not an owner's verb
    known.add_argument("--take-back", action="store_true", dest="take_back",
                       help=argparse.SUPPRESS)   # the same, on the way out
    known.add_argument("--where", action="store_true",
                       help="print the directory they are kept in, and nothing else")
    doing = known.add_subparsers(dest="act", metavar="<action>")
    given = doing.add_parser("grant", help="give an agent one of the skills in the library")
    given.add_argument("name", metavar="<agent>", help="who is being given it")
    given.add_argument("skill", metavar="<skill>", help="which skill, by the name it is under")
    taken = doing.add_parser("revoke", help="take a skill away from an agent")
    taken.add_argument("name", metavar="<agent>", help="who is losing it")
    taken.add_argument("skill", metavar="<skill>", help="which skill, by the name it is under")
    installing = doing.add_parser(
        "install", help="install every skill declared by a repository")
    installing.add_argument("repository", metavar="<repository>",
                            help="a GitHub repository URL, local directory or archive")
    installing.add_argument("--confirm", action="store_true",
                            help="install after reviewing what the repository declares")
    moving = doing.add_parser("update", help="move an installed catalog to its newer version")
    moving.add_argument("catalog", metavar="<catalog>", help="which catalog")
    removing = doing.add_parser("remove", help="remove an installed catalog and its skills")
    removing.add_argument("catalog", metavar="<catalog>", help="which catalog")
    removing.add_argument("--yes", action="store_true",
                          help="do not ask first — for a script, never for a person")
    doing.add_parser("catalogs", help="the installed skill catalogs and their versions")

    commands = sub.add_parser(
        "scripts", help="the integration commands every agent can invoke")
    commands.add_argument(
        "--where", action="store_true",
        help="print the directory they are kept in, and nothing else")

    # A group named the way `channels` and `schedules` are, with the one difference that
    # there is no word for *whose*: a backup is the install's and never an agent's. `skills`
    # above is the same shape for the same reason, and its comment is why there is no
    # optional positional in front of the actions here either.
    copies = sub.add_parser("backups", help="copies of everything this install keeps")
    copies.add_argument("--where", action="store_true",
                        help="print the directory they are kept in, and nothing else")
    keeping = copies.add_subparsers(dest="act", metavar="<action>")
    keeping.add_parser("add", help="take a backup now")
    put_back = keeping.add_parser(
        "restore", help="put a backup back, replacing everything this install keeps")
    put_back.add_argument("backup", metavar="<backup>",
                          help="which one, by the name it is listed under")
    put_back.add_argument("--yes", action="store_true",
                          help="do not ask first — for a script, never for a person")
    dropped = keeping.add_parser("remove", help="delete one backup, and only that one")
    dropped.add_argument("backup", metavar="<backup>",
                         help="which one, by the name it is listed under")
    dropped.add_argument("--yes", action="store_true",
                         help="do not ask first — for a script, never for a person")
    keeping.add_parser("on", help="have the machine take one every day")
    keeping.add_parser("off", help="stop the machine taking one every day")

    # Named the way schedules are: the agent is the word after the verb, the channel is
    # what you call it, and what it *is* comes from `--kind`. Everything a particular
    # platform needs goes after `--` and is never read here (R-CAD-13).
    # **The agent is named before the action, and it is required.** A verb cannot offer an
    # optional `<agent>` *and* sub-actions: argparse matches the agent's name against the
    # action names and dies with `invalid choice`, which is a usage dump about a command
    # somebody typed correctly. `channels` and `schedules` are shaped this way for the
    # same reason.
    specialists = sub.add_parser(
        "roles", help="the specialists an agent hands heavy execution to")
    specialists.add_argument("name", metavar="<agent>",
                             help="whose role runs — a run belongs to the agent that "
                                  "admitted it")
    handing = specialists.add_subparsers(dest="act", metavar="<action>")
    handed = handing.add_parser(
        "run", help="hand one bounded task to a role — the brief is read from standard input")
    handed.add_argument("role", metavar="<role>",
                        help="which role — one this install has, by its own name")
    handed.add_argument("--target", metavar="<directory>",
                        help="the project directory the work happens in — the brain stands "
                             "there, so the project's own instruction files load normally")
    handed.add_argument("--label", metavar="<text>",
                        help="a short safe name for the task, shown where other people can "
                             "read it — never a path and never the brief")
    # This one run's brain, beating what the role says and what this turn is running on
    # (R-ROL-34). Not a list of brains, here or anywhere: a shipped adapter's name and the
    # path of a program somebody wrote are the same kind of thing to the seam that runs it.
    handed.add_argument("--provider", metavar="<provider>",
                        help="which brain runs it, beating the role's own and this turn's "
                             "— one that ships, or the path of a program that speaks yours")
    handed.add_argument("--model", metavar="<model>",
                        help="which model on that brain, beating the role's own — what the "
                             "brain itself calls it")
    guided = handing.add_parser(
        "say", help="say something to a role that is working — read from standard input")
    guided.add_argument("run", metavar="<run>", help="which role run — the id `roles` lists")
    ended = handing.add_parser("stop", help="end a role run before it finishes")
    ended.add_argument("run", metavar="<run>", help="which role run — the id `roles` lists")
    again = handing.add_parser(
        "resume", help="carry a finished role run on — the further task is read from standard input")
    again.add_argument("run", metavar="<run>", help="which role run — the id `roles` lists")
    seen = handing.add_parser("show", help="one role run in full")
    seen.add_argument("run", metavar="<run>", help="which role run — the id `roles` lists")

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
    # On unless an owner says otherwise, because a room that goes quiet for four minutes
    # and then answers looks broken. Off settles the whole turn and not part of it — what
    # the agent is doing *and* what it says on the way — so such a channel gets one message
    # a turn (R-CH-6). `BooleanOptionalAction` is what makes the flag read as the thing it
    # settles rather than as an instruction: `--activity` and `--no-activity`, one of which
    # is already true, so nobody has to remember which way round the default is.
    # Read from a pipe rather than typed, for a script that has the credential in hand. A
    # flag with no value, deliberately: the moment one takes the credential *as* its value
    # it is in `ps` for every user on the machine and in a shell history for ever (R-CAD-11).
    joined.add_argument("--token-stdin", action="store_true", dest="token_stdin",
                        help="read the credential this channel needs from standard input, "
                             "one line; asked for at the terminal when left out")
    joined.add_argument("--activity", action=argparse.BooleanOptionalAction, default=True,
                        help="show what the agent is doing and saying while it works; off "
                             "means one message a turn, the answer (default: on)")
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
    # Who may reach the agent here, changed on a channel that already exists. A separate
    # action for the same reason instructions are one: the people responsible for an agent
    # change over its life, and changing one of them should not mean taking the agent off
    # the channel, proving it again and rewriting everything else about it (R-CAD-19).
    allowing = on.add_parser("allow",
                             help="who may reach this agent through one channel")
    allowing.add_argument("channel", metavar="<channel>",
                          help="which channel, by the name it was added under")
    # Both repeatable, and both optional: with neither, this shows who is allowed. One
    # command doing both is how one person is replaced by another — read, decided and
    # written once, so a replacement is never a moment with nobody allowed in it.
    allowing.add_argument("--add", action="append", default=[], metavar="<user>",
                          help="allow this person too — repeatable")
    allowing.add_argument("--remove", action="append", default=[], metavar="<user>",
                          help="stop allowing this person — repeatable, and never the "
                               "last one")
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


def cmd_update(args: argparse.Namespace, gateways, machine, agents, catalogs=catalog) -> int:
    if args.after_replacing is not None:
        # This process *is* the release that just landed, so what it does to an owner's
        # records is what the release that shipped it says it should be (R-UPD-33). The
        # window is already open and every gateway named here is already down.
        waiting = [one for one in args.after_replacing.split(",") if one]
        code = updater.carry_on(
            REPO_ROOT, waiting,
            resume=lambda names: _bring_all_back(names, gateways, machine, agents),
            provision=_provisioned,
            carry=lambda: _carry_every(agents),
            # **This process's own version, never the one it was told about.** The release
            # that just landed is the code running this line, while `RUNDESK_UPDATE_VERSION`
            # in the environment is what the *previous* release reported before the window
            # opened — linking that would name the version an owner has just left (R-UPD-46).
            landed=__version__,
        )
        if code == 0:
            cataloged = _refresh_skill_catalogs(agents, skill, gateways, catalogs)
            if not os.environ.get("RUNDESK_UPDATE_WORKER"):
                scheduled = _install_automatic_updates(machine)
                return cataloged or scheduled
            return cataloged
        return code
    if args.worker:
        return _run_update_worker(gateways, machine, agents)
    if getattr(args, "automatic", False) is True:
        return _queue_automatic_update(machine)
    if args.status:
        try:
            row = update_request.read()
        except update_request.Unreadable as why:
            print(f"update: UNKNOWN — {why}", file=sys.stderr)
            return 1
        if row is None:
            print("no queued update")
            return 0
        print(update_request.summary(row))
        return 0 if row.get("state") != "failed" else 1
    # A check remains immediate and read-only even inside a provider turn.
    if args.check:
        update_root, current_version = _update_install()
        return updater.run(
            update_root, current_version, check_only=True,
            unfit=lambda: gateways.fitness(update_root),
            preview=lambda: _what_an_update_would_do(agents, update_root),
        )
    if os.environ.get("RUNDESK_RUN"):
        origin = _origin_of_update(agents)
        if origin.get("agent"):
            return _queue_update(machine, origin)
    update_root, current_version = _update_install()
    code = updater.run(
        update_root, current_version, check_only=False,
        busy=lambda: _in_flight(gateways, agents),
        pause=lambda: _stand_all_down(gateways, machine, agents, update_root),
        resume=lambda names: _bring_all_back(
            names, gateways, machine, agents, update_root
        ),
        provision=lambda: _provisioned(update_root),
        carry=lambda: _carry_every(agents),
        unfit=lambda: gateways.fitness(update_root),
        preview=lambda: _what_an_update_would_do(agents, update_root),
    )
    if code == 0:
        cataloged = _refresh_skill_catalogs(agents, skill, gateways, catalogs)
        scheduled = _install_automatic_updates(machine)
        return cataloged or scheduled
    return code


UPDATE_WAIT_SECONDS = 30 * 60
UPDATE_POLL_SECONDS = 1.0
RESTART_POLL_SECONDS = 1.0
RESTART_DEFERRED = 75
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
    if not _standing(name, gateways, agents).running:
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
    target_root = Path(os.environ.get("RUNDESK_UPDATE_ROOT") or REPO_ROOT)
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
    if target_root == REPO_ROOT:
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
            [str(REPO_ROOT / "rundesk"), "update"],
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


def _update_install() -> tuple[Path, str]:
    """The install this externally owned worker is driving."""
    return (
        Path(os.environ.get("RUNDESK_UPDATE_ROOT") or REPO_ROOT),
        os.environ.get("RUNDESK_UPDATE_VERSION") or __version__,
    )


def _what_an_update_would_do(agents, root: Path = REPO_ROOT) -> list:
    """What an update would install and what it would move, before it does either.

    Reads what is on disk and asks nothing of a network, a package index or a database that
    does not already exist (R-UPD-34). Silence where there is nothing to say: an owner who
    reads "nothing to install, nothing to move" every time stops reading it.
    """
    said = []
    for one in dependencies.unsatisfied(root):
        said.append(f"would install: {one}")
    standing = migration.what_would_run(agents.agents_home(), store.VERSION)
    for name, steps in sorted(standing.items()):
        if steps:
            said.append(f"would move {name}: " + ", ".join(repr(one) for one in steps))
    behind = sorted(name for name, steps in standing.items() if steps)
    if behind:
        said.append(f"agents to move: {len(behind)} of {len(standing)}")
    return said


def _carry_every(agents) -> str | None:
    """Bring every agent's records into the shape the new files expect (R-MIG-1).

    Called in the window an update already opens: after the files are replaced and before
    the first agent is brought back, which is the only moment nothing is reading them.
    Never lazily and never by whoever opens a database first — two gateways starting
    together would both begin moving one forward.

    Says what went wrong rather than raising it, because the updater is a decision and
    knows nothing of agents or of what they keep. What each step did, or failed to do, is
    already in that agent's own log.

    **And puts every agent back as it was when one of them cannot be moved** (R-MIG-19).
    Two agents are never at the same version, so the walk stops with earlier ones already
    carried — and the updater then puts the release back, which would leave exactly those
    agents holding records newer than the only code left to read them.
    """
    return migration.carry_every_or_put_back(
        agents.agents_home(), store.VERSION, note=_out_loud,
    )


def _out_loud(said: str) -> None:
    """Each agent as it is reached, so a long update is not a silent one."""
    print(f"        {said}")


def _every_name(gateways, machine, agents, root: Path = REPO_ROOT) -> list[str]:
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
                   *machine.described(root=root), *gateways.remembered()})


def _standing(name: str, gateways, agents):
    """What this gateway is doing, asked where that gateway actually keeps it.

    The one place the two are put together. A command that resolved the directory itself
    at each call is how one of them comes to ask the wrong place and report a running
    agent as stopped.
    """
    return gateways.standing(name, agents.resolved(name).run)


def _stand_all_down(gateways, machine, agents,
                    root: Path = REPO_ROOT) -> tuple:
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
    for name in _every_name(gateways, machine, agents, root):
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
        if not said.ok or not _gone(it.name, gateways, agents):
            update_request.finish_maintenance(it.name, run_home)
            return stopped, f"'{it.name}' would not stop, so nothing was replaced under it"
        stopped.append(it.name)
    return stopped, None


def _bring_all_back(names: list, gateways, machine, agents,
                    root: Path = REPO_ROOT) -> list:
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
        if not said.ok or _came_up(name, gateways, agents) is None:
            down.append(name)
    if down:
        unfit = gateways.fitness(root)
        if unfit:
            print(f"update: what rundesk is made of no longer fits: {unfit}", file=sys.stderr)
    return down


def _recover_update_gateways(gateways, machine, agents,
                             root: Path = REPO_ROOT) -> list[str]:
    """Repay gateways a previous worker marked before it stopped.

    The marker is the distinction between maintenance and an owner deliberately stopping
    a gateway. It outlives a worker crash, so a replacement can finish the promise without
    starting anything the update did not take down (R-UPD-44).
    """
    marked = []
    for name in _every_name(gateways, machine, agents, root):
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
        if _standing(name, gateways, agents).running:
            continue
        try:
            kept = machine.loaded(name)
            said = machine.start(name, root=root) if kept else None
        except (machine.NoSupervisor, machine.NotOurs, machine.Unsure):
            said = None
        if said is None or not said.ok or _came_up(name, gateways, agents) is None:
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
        if _standing(name, gateways, agents).running:
            found.extend(f"{name}/{one}"
                         for one in gateways.what_is_working(name, run_home)
                         if not one.startswith("channel:"))
        found.extend(f"{name}/turn:{row['run']}"
                     for row in gateways.what_is_turning(name, run_home))
    return found


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


def _brain_already_named(name: str, agents) -> bool:
    """Does this agent already say which brain answers for it?

    Records this rundesk will not read are **not** an answer of no. Asking them opens the
    store, which refuses what it does not understand — and asked without a guard, the
    ordinary repair (`rundesk add <name>`, no `--provider`, because the brain is already
    remembered) came out as a raw traceback for exactly the agent an owner was repairing.
    The refusal itself is reported a few lines below, by the code that already knows how to
    say it; this only decides whether to demand a brain, and a store nobody can read is not
    a reason to demand one.
    """
    try:
        return bool((agents.chosen(name) or {}).get("provider"))
    except (store.Unreadable, store.TooNew, store.Behind, migration.Failed):
        return True


def _identities(agents, machine) -> list[str]:
    """Every persisted spelling that command resolution must not split."""
    return sorted({*agents.identities(), *machine.described(root=REPO_ROOT)})


def cmd_add(args: argparse.Namespace, gateways, machine, agents) -> int:
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
    given = args.name
    if not given:
        print("add: NAME REQUIRED — say what to call the agent", file=sys.stderr)
        print("        what there is already: rundesk agents", file=sys.stderr)
        return 1
    try:
        name = agents.creation_name(given, _identities(agents, machine))
    except agents.NotAnAgentName as why:
        print(f"{given}: INVALID NAME — {why}", file=sys.stderr)
        return 1
    knew = agents.exists(name)
    pending = agents.creation_pending(name)
    if knew and not pending and any((
        args.provider, args.model, getattr(args, "settings", None),
        getattr(args, "says", None) is not None,
    )):
        print(f"{name}: ALREADY MADE — use configure to change its defaults",
              file=sys.stderr)
        print(f"        like this:  rundesk configure {name} --provider <provider>",
              file=sys.stderr)
        return 1
    # **An agent with no brain cannot take a turn**, so it is not a thing to make. Asked here
    # rather than left to the first `ask`: a half-made agent that reports MADE and then
    # refuses everything is worse than a refusal now, and an owner who has to be told twice
    # was told the wrong thing first. Making one that *already* has a brain is a repair and
    # must not demand it again (R-AGT-4, R-AGT-18).
    if not args.provider and not (knew and _brain_already_named(name, agents)):
        print(f"{name}: NO BRAIN — say which one answers for this agent", file=sys.stderr)
        print(f"        like this:  rundesk add {name} --provider <provider>",
              file=sys.stderr)
        print("        a shipped one, or the path to a program you wrote", file=sys.stderr)
        return 1
    # Validate everything we can before making, adopting or changing anything. Provider
    # settings are deliberately opaque, but their shape and the adapter's executability
    # are ours to prove. A refusal leaves the previous whole configuration intact
    # (R-AGT-32).
    try:
        settings = _given(getattr(args, "settings", None))
        if args.provider:
            provider.program(args.provider)
    except (ValueError, provider.NotRunnable) as why:
        print(f"{name}: NOT SET — {why}", file=sys.stderr)
        return 1
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
        made = agents.add(name, display_name=given)
    except config.Unreadable as why:
        # A configuration that cannot be read is never treated as absent: the skills this
        # agent would be given are stated there, and making it without them would be an
        # owner's decision silently ignored.
        print(f"{name}: NOT MADE — {why}", file=sys.stderr)
        return 1
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
    chose = _chose(args, agents, name, settings)
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


def cmd_configure(args: argparse.Namespace, agents) -> int:
    """Change an existing agent's durable defaults without replacing it (R-AGT-31)."""
    name = args.name
    if not name:
        print("configure: NAME REQUIRED — say which agent to change", file=sys.stderr)
        return 1
    try:
        agents.checked(name)
    except agents.NotAnAgentName as why:
        print(f"{name}: INVALID NAME — {why}", file=sys.stderr)
        return 1
    if not agents.exists(name):
        print(f"{name}: NO AGENT — make it first with rundesk add", file=sys.stderr)
        return 1
    if not any((args.provider, args.model, getattr(args, "settings", None) is not None,
                getattr(args, "says", None) is not None)):
        print(f"{name}: NOTHING TO CHANGE — name a provider, model, setting, or instructions",
              file=sys.stderr)
        return 1
    try:
        settings = _given(getattr(args, "settings", None))
        if args.provider:
            provider.program(args.provider)
        chose = _chose(args, agents, name, settings)
    except (ValueError, provider.NotRunnable, store.Unreadable, store.TooNew,
            store.Behind, migration.Failed) as why:
        print(f"{name}: NOT CONFIGURED — {why}", file=sys.stderr)
        return 1
    print(f"{name}: CONFIGURED")
    print(f"        reaches for: {chose}")
    return 0


def _chose(args: argparse.Namespace, agents, name: str, settings: dict) -> str:
    """Keep whichever of provider, model and settings was named, and say what it is now.

    What was not named is left as it was, because naming a model later must not quietly
    forget the brain. Changing providers clears its old provider-specific defaults.
    """
    # `None` is "not named" and `""` is "take it off", which is why this asks whether it was
    # given rather than whether it is truthy: an owner clearing what an agent is told has
    # said something, and reading that as silence would leave the old text in place.
    says = getattr(args, "says", None)
    settings_were_given = getattr(args, "settings", None) is not None
    if not (args.provider or args.model or settings_were_given or says is not None):
        return ""
    keeping = agents.remember(name, provider=args.provider, model=args.model,
                              settings=settings if settings_were_given else None,
                              instructions=says,
                              replace_brain=bool(args.provider))
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

    # **The clock's work, or a person's.** A schedule that names `rundesk ask` rather than a
    # prompt is still the clock's, and the gateway says which schedule through the one
    # variable it adds to a scheduled program's environment. Read here, where the command
    # adapts what it was invoked as, and handed on as an argument rather than reached for
    # further in.
    #
    # An explicit `--conversation` wins: somebody who named one has said where this belongs.
    # Otherwise a scheduled turn gets a conversation of its own, named for the schedule, and
    # **starts fresh every firing** — untouched, it landed in the terminal's own conversation,
    # so a run at three in the morning resumed the session its owner types into and left its
    # prompt and answer in the middle of it.
    clock = (os.environ.get(_gateway.SCHEDULE_IS) or "").strip()
    by_the_clock = bool(clock) and not args.conversation

    said = _Shown()
    try:
        outcome = asyncio.run(turn.carry(
            name, prompt, named,
            model=args.model or reaches.get("model"),
            settings=settings,
            posture=provider.READ if args.read_only else provider.WORK,
            conversation=clock if by_the_clock else (args.conversation or turn.TERMINAL),
            on=turn.SCHEDULE if by_the_clock else turn.TERMINAL,
            kind=turn.SCHEDULE if by_the_clock else turn.TERMINAL,
            fresh=args.fresh or by_the_clock,
            watching=said,
            steering=_typed() if args.steer else None,
            # What it is told before it reads a word: this turn's own, then the agent's
            # (R-AGT-16) — and, where the clock started this, what rundesk says about that
            # situation whatever they wrote (R-AGT-34). For a person at a terminal there is
            # nothing to add, because they are here.
            preface=agents.told(name, said=args.says,
                                regardless=schedules.by_default(clock) if clock else ""),
            source=turn.SCHEDULE if clock else None,
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
            if did in provider.CONTINUITY.values():
                # What changed, and not which tool changed it (R-PRV-29). These four name
                # a file rather than an act, so the vendor's own word beside one reads as
                # `rules Write` — and which tool wrote it is the half nobody wanted.
                print(f"        · updated {did}", file=sys.stderr)
                return
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
    # Only where the brain reported the split. Most do not, and a `0 written` on every one
    # of them would read as "wrote nothing to the cache" rather than "does not say".
    if tokens.get("written") is not None:
        said += f", {tokens['written']} written"
    return f"{said}, {tokens['model']}" if tokens.get("model") else said


def _running_old_code(name, gateways, agents) -> list:
    """Is this agent's gateway serving the release that is actually installed (R-AGT-21)?

    **A gateway holds the modules it imported when it started.** Replacing the files under
    a running one changes nothing it has already loaded, so it goes on serving the old code
    for everything it has and reads the new files only for whatever it has not imported
    yet — which is a version nobody can see it is on. An update stands them all down for
    exactly this reason, and the case that gets past it is the one an owner caused: a
    gateway started before the code was last replaced.

    Asked of the version the gateway wrote down when it started rather than of a file's
    modification time. It is the thing itself rather than a proxy for it, it costs a record
    this command already reads, and a checkout whose files are touched by anything at all
    would make the proxy cry wolf for ever.

    Reported as a fault rather than a note: the whole trap is that nothing says anything.
    """
    try:
        it = _standing(name, gateways, agents)
    except Exception as why:   # noqa: BLE001 — a boundary; a diagnosis reports, never raises
        # **Said, not swallowed.** `gateway._held` deliberately re-raises an OSError that is
        # not a lock being held, so returning nothing here would let `doctor` print READY
        # for an agent whose gateway could not be looked at — a truthful-looking silence,
        # which is the one thing this command must never produce.
        return [_agent.Complaint(str(why), "what this agent's gateway is doing cannot be read",
                                 f"rundesk status {name}")]
    if not it.running or not it.version or it.version == __version__:
        return []
    return [_agent.Complaint(
        f"it started on {it.version} and this install is {__version__}",
        "this agent's gateway is running code that is no longer installed",
        f"rundesk stop {name} && rundesk start {name}",
    )]


def _provisioned(root: Path = REPO_ROOT) -> str | None:
    """What an install is made of, brought forward: what it needs, then what it ships.

    Skills after dependencies, which is the same order the window itself keeps and for the
    same reason — the failure that cannot touch an owner's files happens first. Bringing a
    built-in forward is what makes it rundesk's rather than a copy an owner then owns, and
    it is the whole of "always the latest version" (R-AGT-30): the set is read off the
    release each time, while the ownership marker says which same-named directories may
    safely be replaced. A skill that could not be written is not an update that failed —
    `doctor` says which one, and everything else is already forward.
    """
    went_wrong = dependencies.provision(root)
    if went_wrong:
        return went_wrong
    # Values this release knows and an earlier one never wrote. Values already there are
    # never touched, so this cannot be how an owner's configuration is lost (R-UPD-48).
    config.ensure()
    skill.lay_down(force=True)
    # Shipped roles are laid down where they are missing and never over one that is
    # there. A role is what an owner writes their specialists as, so bringing one
    # "forward" the way a built-in skill is brought forward would rewrite what every
    # future run of an edited role is allowed to do (R-ROL-18).
    role.lay_down()
    # A persisted skill name can move only after both old and replacement packages are
    # proven as Rundesk built-ins. The earlier pass fills values; this one carries names.
    config.ensure()
    # Existing agents are brought forward too. Optional owner grants are not removed; the
    # configured list is the minimum every agent must hold, not its complete grant set.
    for name in _agent.known():
        _agent.require_skills(name)
    _agent.retire_renamed_skills()
    return None


def cmd_config(args: argparse.Namespace) -> int:
    """What this install's configuration file says is in force.

    Every effective value is stated in the file. Missing known values are unreadable rather
    than silently supplied elsewhere, so the answer here and the behavior of the install
    cannot disagree (R-CMD-11).

    **What was written and is not understood is said here too, and nowhere else.** `ensure`
    preserves an unknown key faithfully and every reader passes straight over it, so a
    mistyped `keepDays` is a value an owner stated, can see in their own file, and which
    nothing on the machine has ever read — the same silence this command was built to end,
    arriving by the one route printing the known keys cannot show.
    """
    at = config.path()
    try:
        stated = config.read()
        now = {"backups": config.backups(), "updates": config.updates(),
               "roles": config.roles(), "skills": config.skills()}
    except config.Unreadable as why:
        print(f"config: UNREADABLE — {why}", file=sys.stderr)
        print("        every value below it is refused rather than guessed",
              file=sys.stderr)
        return 1
    print(at)
    ignored = []
    for section in config.SECTIONS:
        print(f"\n  {section}")
        said = stated.get(section) or {}
        for key, value in sorted(now[section].items()):
            shown = " ".join(value) if isinstance(value, tuple) else value
            print(f"    {key:<10} {shown}")
        ignored += [f"{section}.{key}" for key in sorted(said)
                    if key not in now[section]]
    # A whole section this release has never heard of, which is the same silence one key
    # wide. Sorted rather than left in the file's order, because what is shown is never
    # decided by how somebody's editor happened to write it.
    ignored += [one for one in sorted(stated) if one not in config.SECTIONS]
    if ignored:
        print(f"\n  read by nothing on this machine: {', '.join(ignored)}")
        print("    each was written, is kept exactly as it is, and no default it looks "
              "like is taken from it")
    return 0


def cmd_backups(args: argparse.Namespace, gateways, machine, agents) -> int:
    """Copies of everything this install keeps: what there is, taking one, putting one back.

    The listing is deliberately the bare form, because the question somebody asks after
    trouble is "what have I got" and it should cost them no second word.
    """
    if getattr(args, "where", False):
        # Said by the command rather than written into any prose: this is the one directory
        # an owner may point off the machine entirely, so a guide naming a path would be
        # wrong for exactly the people who moved it.
        print(backups_home())
        return 0
    act = getattr(args, "act", None)
    if act is None:
        return _list_backups()
    if act == "add":
        return _take_a_backup()
    if act == "restore":
        return _restore_a_backup(args, gateways, machine, agents)
    if act == "remove":
        return _remove_a_backup(args)
    if act in ("on", "off"):
        return _daily_backups(act, machine)
    return cmd_not_available(f"backups {act}")


def _remove_a_backup(args: argparse.Namespace) -> int:
    """Delete one copy, by name, having said what it holds."""
    where = backups_home()
    try:
        said = backups.manifest_of(where / args.backup)
    except backups.Unreadable:
        said = None                       # unreadable is exactly what somebody removes
    except backups.Refused as why:
        print(f"backups remove: FAILED — {why}", file=sys.stderr)
        return 1
    if said:
        print(f"{args.backup} holds {len(said.get('records', {}))} agents, "
              f"taken {said.get('taken_at', 'at an unknown moment')}")
    else:
        print(f"{args.backup} cannot be read, so what it holds is unknown")
    if not args.yes and not _agreed():
        print("nothing was removed")
        return 0
    try:
        backups.remove(where, args.backup)
    except (backups.Refused, OSError) as why:
        print(f"backups remove: FAILED — {why}", file=sys.stderr)
        return 1
    print(f"removed {args.backup}")
    return 0


def _daily_backups(act: str, machine) -> int:
    """Hand the daily backup to the machine, or take it back.

    rundesk supervises nothing itself, so this is the machine's job in exactly the way a
    gateway is — and it is the install's rather than any agent's, which is why it is not a
    schedule: a schedule is a row one agent keeps, and a backup that stopped when that agent
    was removed would be a backup nobody noticed had stopped.
    """
    if not machine.available():
        print("backups: there is no supervisor on this machine to hand a daily backup to",
              file=sys.stderr)
        return 1
    if act == "off":
        said = machine.remove_backup()
        if not said.ok:
            print(f"backups off: FAILED — {said.why}", file=sys.stderr)
            return 1
        print("the machine no longer takes a backup every day")
        return 0
    try:
        at = config.backups()["at"]
    except config.Unreadable as why:
        print(f"backups on: FAILED — {why}", file=sys.stderr)
        return 1
    said = machine.install_backup(at)
    if not said.ok:
        print(f"backups on: FAILED — {said.why}", file=sys.stderr)
        return 1
    print(f"the machine will take a backup every day at {at}")
    print(f"        the last {config.backups()['keep_last']} are kept, in {backups_home()}")
    return 0


def _restore_a_backup(args: argparse.Namespace, gateways, machine, agents) -> int:
    """Put one back, having said what it will change and been told to go ahead.

    **The window an update already opens is reused rather than a second one invented.**
    Standing every gateway down and refusing while work is in flight is exactly what
    `rundesk update` does before it replaces the files, it is already proved, and a restore
    needs the same thing for the same reason (R-UPD-21, R-UPD-23).
    """
    at = backups_home() / args.backup
    try:
        said = backups.manifest_of(at)
    except (backups.Refused, backups.Unreadable) as why:
        print(f"backups restore: FAILED — {why}", file=sys.stderr)
        return 1
    why = backups.refusals(said)
    if why:
        # Said before anything moves rather than after, which is the whole point of the
        # manifest being readable without unpacking anything.
        print(f"backups restore: REFUSED — {'; '.join(why)}", file=sys.stderr)
        return 1

    data = data_home()
    changing = backups.what_changes(said, data)
    print(f"this replaces everything under {data} with what is in {args.backup}")
    print(f"        taken {said.get('taken_at', 'at an unknown moment')} "
          f"by rundesk {said.get('rundesk', '?')}")
    for what, named in (("comes back", changing["comes_back"]),
                        ("goes away", changing["goes_away"]),
                        ("replaced", changing["stays"])):
        if named:
            print(f"        {what}:  {', '.join(named)}")
    if not args.yes and not _agreed():
        print("nothing was changed")
        return 0

    stopped_by = backups.restore(
        at, data, backups_home(),
        busy=lambda: _in_flight(gateways, agents),
        pause=lambda: _stand_all_down(gateways, machine, agents),
        resume=lambda names: _bring_all_back(names, gateways, machine, agents),
        carry=lambda incoming: migration.carry_every_or_put_back(
            incoming / "agents", store.VERSION, aside=incoming / ".carrying",
            note=_out_loud),
        note=_out_loud,
    )
    if stopped_by:
        print(f"backups restore: NOT DONE — {stopped_by}", file=sys.stderr)
        return 1
    print(f"put back {args.backup}")
    return 0


def _agreed() -> bool:
    """Ask, and take anything that is not yes as no.

    Never assumed from a pipe: a restore that went ahead because nothing was attached to
    answer is the failure this whole command is careful about.
    """
    try:
        return input("continue? [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def _take_a_backup() -> int:
    """Take one now, and say where it went and what it cost."""
    try:
        at = backups.take(data_home(), backups_home(), note=_out_loud)
    except (backups.Refused, config.Unreadable) as why:
        print(f"backups add: FAILED — {why}", file=sys.stderr)
        return 1
    except OSError as why:
        # The destination may be a disk that is not plugged in or a cloud directory that
        # will not answer, which is a different thing from having nothing to back up.
        print(f"backups add: FAILED — {backups_home()} could not be written to: {why}",
              file=sys.stderr)
        return 1
    said = backups.manifest_of(at)
    print(f"took a backup: {at}")
    print(f"        {len(said['records'])} agents, {updater.readable(at.stat().st_size)}")
    if said.get("copied_whole"):
        # Never silent. A copy that is not a consistent copy is still worth having and is
        # not the same thing, and the only moment anybody can act on the difference is now.
        for one in said["copied_whole"]:
            print(f"        WARNING: {one} could not be copied consistently and is in the "
                  f"backup exactly as it is on disk", file=sys.stderr)
    # Pruned here rather than on a second schedule of its own: the only thing that puts a
    # copy past the last few is a newer one arriving, so this is the moment the question has
    # a new answer, and a machine that has stopped taking backups stops deleting them too.
    # Bounded like every other reading of this directory: the copy is already written and
    # safe, so a directory that stops answering costs the tidying and never the backup
    # itself, and the command says which of the two happened (R-BKP-29).
    keep_last = config.backups()["keep_last"]
    reached, gone = _answered_within(
        BACKUP_PATIENCE,
        lambda: backups.prune(backups_home(), keep_last, note=_out_loud),
        "rundesk-backups-prune",
    )
    if not reached:
        print(f"        WARNING: {backups_home()} did not answer within "
              f"{BACKUP_PATIENCE:.0f}s, so older copies were left as they are",
              file=sys.stderr)
    elif gone:
        print(f"        {len(gone)} beyond the last {keep_last} were removed")
    return 0


def _list_backups() -> int:
    """Every copy there is, oldest first, with what each cost and what it holds."""
    where = backups_home()

    def describe() -> list:
        # Read and described inside the bound together, because the size of each copy is
        # a `stat` of its own: a directory that answers `opendir` and then blocks on the
        # files in it would otherwise hang after the guard had already let go (R-BKP-29).
        return [(
            one.at.name,
            one.taken_at if one.readable else "-",
            updater.readable(one.held_bytes) if one.held_bytes is not None else "-",
            str(len(said.get("records", {}))) if one.readable else "-",
            said.get("why", "-") if one.readable else "UNREADABLE",
            one.why if not one.readable else None,
        ) for one, said in ((one, one.said or {}) for one in backups.every(where))]

    reached, rows = _answered_within(BACKUP_PATIENCE, describe, "rundesk-backups-list")
    if not reached:
        # Named, and never answered with the empty listing. "There are no backups" and
        # "the place they are kept did not answer" send an owner somewhere completely
        # different, and only one of them means their agents are unprotected (R-BKP-29).
        print(f"backups: FAILED — {where} did not answer within "
              f"{BACKUP_PATIENCE:.0f}s, so what is kept there is unknown", file=sys.stderr)
        return 1
    if not rows:
        print("no backups")
        print(f"        take one:  rundesk backups add")
        return 0
    _as_table(("BACKUP", "TAKEN", "SIZE", "AGENTS", "WHY"), [row[:5] for row in rows])
    print()
    print(f"kept in {where}")
    for row in rows:
        if row[5] is not None:
            print(f"        {row[0]}: {row[5]}", file=sys.stderr)
    return 0


def _all_granted_skills(agents, skills) -> set[str]:
    """Every skill at least one agent holds, asked from the links that are the grants."""
    return {
        called
        for name in agents.known()
        for called in skills.granted(agents.skills(name))
    }


@contextlib.contextmanager
def _retiring_catalog_grants(agents, skills, gateways, catalogs, names, retired):
    """Revoke catalog skills only while every affected agent is proven stopped.

    The gateway holds stay open across the catalog mutation. If that mutation fails,
    restore every grant while the old catalog package is available again.
    """
    with skills.changing_grants(skills.home()):
        affected = []
        for name in agents.known():
            mine = agents.skills(name)
            held = [
                called for called in sorted(set(names).intersection(skills.granted(mine)))
                if skills.ours(mine / called, skills.home())
            ]
            affected.append((name, held))
        affected = [(name, held) for name, held in affected if held]
        revoked = []
        with contextlib.ExitStack() as locks:
            for name, _ in affected:
                stopped = locks.enter_context(
                    gateways.holding(name, agents.resolved(name).run)
                )
                if not stopped:
                    raise catalogs.InUse(
                        f"cannot remove skills from running agent {name}; stop it first"
                    )
            try:
                for name, held in affected:
                    for called in held:
                        skills.revoke(agents.skills(name), called)
                        revoked.append((name, called))
                yield
            except BaseException as original:
                failed = []
                for name, called in reversed(revoked):
                    try:
                        skills.grant(agents.skills(name), called)
                    except Exception as rollback:
                        failed.append(f"{name}/{called}: {rollback}")
                if failed:
                    raise catalogs.RollbackFailed(
                        f"the catalog change failed ({original}); restoring grants also "
                        f"failed for {', '.join(failed)}"
                    ) from original
                raise
        retired.extend(revoked)


def _refresh_skill_catalogs(agents, skills, gateways, catalogs) -> int:
    """Seed the general collection and check every installed repository version."""
    try:
        retired = []
        checked = catalogs.refresh(
            granted=_all_granted_skills(agents, skills),
            retiring=lambda names: _retiring_catalog_grants(
                agents, skills, gateways, catalogs, names, retired,
            ),
        )
    except (catalogs.NotACatalog, OSError) as why:
        print(f"skills: CATALOGS NOT UPDATED — {why}", file=sys.stderr)
        return 1
    failed = False
    for one in checked:
        if one.why:
            failed = True
            print(f"skills: {one.name} NOT UPDATED — {one.why}", file=sys.stderr)
        elif one.before is None:
            print(f"skills: {one.name} {one.after}: installed by default")
        elif one.before == one.after:
            print(f"skills: {one.name} {one.after}: up to date")
        else:
            print(f"skills: {one.name}: {one.before} -> {one.after}")
    for name, called in retired:
        print(f"{name} no longer has removed skill {called}")
    return 1 if failed else 0


def _install_skill_catalog(args: argparse.Namespace, catalogs) -> int:
    try:
        if not args.confirm:
            manifest = catalogs.inspect(args.repository)
            print(f"{manifest.name} {manifest.version} — {manifest.description}")
            print(f"source: {args.repository}")
            print("skills:")
            for called, _ in manifest.skills:
                print(f"  {called}")
            print()
            print(f"install: rundesk skills install {args.repository} --confirm")
            return 0
        landed = catalogs.install(args.repository)
    except (catalogs.NotACatalog, catalogs.InTheWay, OSError) as why:
        print(f"skills: NOT INSTALLED — {why}", file=sys.stderr)
        return 1
    print(f"{landed.name} {landed.version}: installed")
    print("        its skills are available and none were granted")
    return 0


def _update_skill_catalog(args: argparse.Namespace, agents, skills, gateways, catalogs) -> int:
    retired = []
    try:
        before = catalogs.installed().get(args.catalog)
        landed = catalogs.update(
            args.catalog, granted=_all_granted_skills(agents, skills),
            retiring=lambda names: _retiring_catalog_grants(
                agents, skills, gateways, catalogs, names, retired,
            ),
        )
    except (catalogs.NotACatalog, catalogs.InTheWay, catalogs.InUse,
            catalogs.Unknown, catalogs.RollbackFailed, OSError) as why:
        print(f"skills: NOT UPDATED — {why}", file=sys.stderr)
        return 1
    if before is not None and before.version == landed.version:
        print(f"{landed.name} {landed.version}: up to date")
    else:
        print(f"{landed.name}: {before.version if before else '-'} -> {landed.version}")
    for name, called in retired:
        print(f"{name} no longer has removed skill {called}")
    return 0


def _remove_skill_catalog(args: argparse.Namespace, agents, skills, gateways, catalogs) -> int:
    retired = []
    try:
        standing = catalogs.installed().get(args.catalog)
        if standing is None:
            raise catalogs.Unknown(f"there is no installed catalog called {args.catalog}")
        if not args.yes:
            print(f"{standing.name} {standing.version} would be removed")
            for called, _ in standing.manifest.skills:
                print(f"  {called}")
            print()
            print(f"remove: rundesk skills remove {args.catalog} --yes")
            return 0
        removed = catalogs.remove(
            args.catalog, granted=_all_granted_skills(agents, skills),
            retiring=lambda names: _retiring_catalog_grants(
                agents, skills, gateways, catalogs, names, retired,
            ),
        )
    except (catalogs.NotACatalog, catalogs.InUse, catalogs.Unknown,
            catalogs.RollbackFailed, OSError) as why:
        print(f"skills: NOT REMOVED — {why}", file=sys.stderr)
        return 1
    print(f"{args.catalog}: removed {', '.join(removed)}")
    for name, called in retired:
        print(f"{name} no longer has removed skill {called}")
    return 0


def _list_skill_catalogs(catalogs) -> int:
    try:
        held = catalogs.installed()
    except catalogs.NotACatalog as why:
        print(f"skills: catalogs could not be read — {why}", file=sys.stderr)
        return 1
    if not held:
        print("no skill catalogs")
        print("        install one:  rundesk skills install <repository>")
        return 0
    _as_table(
        ("CATALOG", "VERSION", "SOURCE", "SKILLS"),
        [(one.name, one.version, one.source, str(len(one.manifest.skills)))
         for one in held.values()],
    )
    return 0


def cmd_skills(args: argparse.Namespace, agents, skills, gateways, catalogs) -> int:
    """The skills on this machine, who has which, and giving or taking one away.

    The catalog is read off the library and the agents rather than from anything written
    down about them: a grant *is* the link standing in an agent's own directory, so there
    is no record that could disagree with what a brain will actually find.
    """
    if getattr(args, "where", False):
        # Said by the command rather than written into any prose, because where the
        # library is depends on where this install is: an install pointed elsewhere
        # keeps its skills there too, and a guide naming `~/.rundesk` would be wrong
        # for every one of them.
        print(skills.home())
        return 0
    if getattr(args, "take_back", False):
        # The installer's too, on the way out: what a release laid down is the program's and
        # goes with it (R-RM-7). Left behind, it is a piece of rundesk on a machine somebody
        # has removed rundesk from — and it keeps the whole install directory standing after
        # an uninstall that said it had left nothing.
        retired = []
        taken = catalogs.take_back_seeded(
            retiring=lambda names: _retiring_catalog_grants(
                agents, skills, gateways, catalogs, names, retired,
            ),
        )
        taken.extend(skills.take_back())
        # What the release laid down and nobody has touched, for the same reason a
        # built-in skill goes: it is a piece of the program, and it is what leaves the
        # install directory standing after an uninstall that said it left nothing
        # (R-RM-7). An edited role is the owner's and stays.
        taken.extend(role.take_back())
        print(" ".join(taken))
        return 0
    if getattr(args, "lay_down", False):
        # The installer's, and deliberately not an owner's verb: what a release ships is
        # not a thing anybody should have to ask for.
        laid = skills.lay_down()
        agents.reconcile_skill_config()
        if _refresh_skill_catalogs(agents, skills, gateways, catalogs):
            return 1
        # `skills.granted` is a floor for every agent, including ones that predate the
        # value. Re-running the installer is an upgrade route, so reconcile the existing
        # population here as well as in `_provisioned` (R-AGT-36).
        for name in agents.known():
            agents.require_skills(name)
        agents.retire_renamed_skills()
        print(" ".join(laid))
        return 0
    act = getattr(args, "act", None)
    if act == "install":
        return _install_skill_catalog(args, catalogs)
    if act == "update":
        return _update_skill_catalog(args, agents, skills, gateways, catalogs)
    if act == "remove":
        return _remove_skill_catalog(args, agents, skills, gateways, catalogs)
    if act == "catalogs":
        return _list_skill_catalogs(catalogs)
    if act in ("grant", "revoke"):
        try:
            whose = agents.skills(args.name)
        except agents.NotAnAgentName as why:
            print(f"{args.name}: INVALID NAME — {why}", file=sys.stderr)
            return 1
        if not agents.exists(args.name):
            print(f"{args.name}: NO SUCH AGENT", file=sys.stderr)
            print(f"        make one:  rundesk add {args.name} --provider <provider>",
                  file=sys.stderr)
            return 1
        try:
            if act == "grant":
                with skills.changing_grants(skills.home()):
                    skills.grant(whose, args.skill)
                print(f"{args.name} was given {args.skill}")
            else:
                # Rundesk's product floor and the configured baseline are requirements, not
                # creation-time suggestions. Only the owner-selected part can be changed
                # before revocation (R-AGT-37).
                if args.skill in config.required_grants():
                    print(f"{args.skill}: RUNDESK REQUIRED — every agent retains it",
                          file=sys.stderr)
                    print("        this skill cannot be configured away or revoked",
                          file=sys.stderr)
                    return 1
                if args.skill in config.skills()["granted"]:
                    print(f"{args.skill}: REQUIRED — config.json attaches it to every agent",
                          file=sys.stderr)
                    print(f"        remove it from {config.path()} before revoking it",
                          file=sys.stderr)
                    return 1
                with skills.changing_grants(skills.home()):
                    skills.revoke(whose, args.skill)
                print(f"{args.name} no longer has {args.skill}")
        except (skills.Unknown, skills.NotASkill, skills.InTheWay,
                config.Unreadable) as why:
            print(f"{args.skill}: {why}", file=sys.stderr)
            return 1
        return 0

    held = skills.library()
    if not held:
        print("no skills")
        print(f"        write one:  {skills.home()}/<name>/SKILL.md")
        return 0
    ships = set(skills.shipped())
    # Asked of every agent rather than kept anywhere, because "who has this" is otherwise
    # a question only a reverse scan can answer and a stored answer would go stale the
    # first time somebody removed a link by hand.
    whose: dict = {name: skills.granted(agents.skills(name)) for name in agents.known()}
    # **What put it there, not whose it is.** `rundesk` is one this release ships and an
    # update brings forward; `custom` is one somebody wrote, which nothing here ever
    # touches. Said this way because the column has more answers coming — a skill that
    # arrived with a plugin, or with a tool — and "yours" against "built-in" is a pair with
    # nowhere for a third to stand.
    rows = [(name, "rundesk" if name in ships else (catalogs.whose(held[name]) or "custom"),
             ", ".join(sorted(who for who, mine in whose.items() if name in mine)) or "-")
            for name in sorted(held)]
    _as_table(("SKILL", "FROM", "AGENTS"), rows)
    return 0


def cmd_scripts(args: argparse.Namespace, scripts) -> int:
    """The owner's shared integration commands and where they stand."""
    where = scripts.home()
    if getattr(args, "where", False):
        print(where)
        return 0
    held = scripts.commands()
    if not held:
        print("no scripts")
        print(f"        write one:  {where}/<command>")
        return 0
    _as_table(("SCRIPT", "COMMAND"), [
        (name, str(at)) for name, at in sorted(held.items())
    ])
    print()
    print(f"kept in {where}")
    return 0


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
        said = said + _running_old_code(name, gateways, agents)
        if not said:
            print(f"{name}: READY")
            continue
        worst = 1
        print(f"{name}: NOT READY", file=sys.stderr)
        for one in said:
            print(f"        {one.said}: {one.about}", file=sys.stderr)
            # What to do about it, under the thing it is about (R-AGT-19). An owner running
            # this is already asking because something is wrong; leaving them to work the
            # command out from the fault is asking them to diagnose it twice.
            if one.fix:
                print(f"            fix: {one.fix}", file=sys.stderr)
    # Per page, where a *new* agent's would come from (R-AGT-26). Said once for the install
    # rather than once per agent, because it is a fact about this machine and not about any
    # one of them — and said only when an owner has overridden something, since a list of
    # five identical "install" lines every time is a list nobody reads.
    from_each = agents.where_each_page_comes_from()
    if any(whose == "owner" for _called, whose, _at in from_each):
        print("templates a new agent would be made from:")
        for called, whose, at in from_each:
            print(f"        {called}: {whose} ({at})")
    if _cannot_search(names, agents):
        # A fact about the machine rather than a fault of any agent, so it is said here
        # and is not a complaint: this SQLite was built without FTS5. Said by the command
        # an owner runs to find out what is wrong, because the alternative is `search`
        # answering nothing and reading exactly like there being nothing to find (R-STO-8).
        print("searching: UNAVAILABLE — this machine's sqlite cannot search by the words "
              "in something")
        print("        every run is still listed, read and queried:  rundesk runs <agent>")
    return worst


def _cannot_search(names, agents) -> bool:
    """Whether this machine can search at all, asked of the first agent that can answer.

    Asked rather than assumed, and asked once: it is a property of the SQLite this Python
    was built against, so every agent on the machine gives the same answer, and an agent
    whose records cannot be opened has no answer to give rather than a negative one.
    """
    for name in names:
        try:
            return not agents.reading(name).searchable()
        except Exception:   # noqa: BLE001 — an agent that cannot answer is not an answer
            continue
    return False


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
                if (getattr(args, "worker", False)
                        and not _standing(name, gateways, agents).running):
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
                    up = _came_up(name, gateways, agents)
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
                            machine, name, _origin_of_update(agents),
                        ),
                    )
                    continue
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
        run_home = agents.resolved(name).run
        doing = gateways.what_is_working(name, run_home) if it.running else {}
        turning = gateways.what_is_turning(name, run_home)
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
            str(len(doing)) if it.running else "-",
            str(len(turning)) or "-",
            # What never finished, counted where somebody looks (R-GW-39). The store
            # answering that question has existed since work could be interrupted at
            # all, and nothing in the product ever read it back: "what did not finish"
            # meant reading JSON out of a directory by hand, during an incident.
            str(len(gateways.what_was_interrupted(name, agents.resolved(name).logs)) or "-"),
        ))
    _as_table(("AGENT", "STATE", "PID", "UPTIME", "LAUNCHD JOB", "VERSION",
               "PROCESSES", "TURNS", "UNFINISHED"),
              rows)
    for name in sorted(found):
        run_home = agents.resolved(name).run
        it = found[name]
        working = gateways.what_is_working(name, run_home) if it.running else {}
        turning = gateways.what_is_turning(name, run_home)
        if not working and not turning:
            continue
        print()
        print(f"{name}:")
        details = [
            ("ADAPTER" if work.startswith("channel:") else "PROCESS",
             work.removeprefix("channel:"), "-", str(how.get("pgid") or "-"), "-")
            for work, how in sorted(working.items())
        ]
        details.extend((
            "TURN",
            f"{row['source']}:{row['surface']}",
            row["conversation"],
            str(row["pid"]),
            _how_long(row.get("since")),
        ) for row in turning)
        _as_table(("KIND", "SOURCE", "CONVERSATION", "PID", "ELAPSED"), details)
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
    unfinished = gateways.what_was_interrupted(name, agents.resolved(name).logs)
    if unfinished:
        print()
        _as_table(("UNFINISHED", "AT", "ENDED", "WHY"), [
            (work, str(how.get("at", "-")),
             "yes" if how.get("ended") else "unproven", str(how.get("why", "-")))
            for work, how in sorted(unfinished.items())
        ])
    return 0


def cmd_status(_args: argparse.Namespace, gateways, machine, agents) -> int:
    """How rundesk itself and its current load stand on this machine.

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
    names = _every_name(gateways, machine, agents)
    standing = {name: _standing(name, gateways, agents) for name in names}
    running = sum(1 for one in standing.values() if one.running)
    working = 0
    turning = 0
    for name in names:
        run_home = agents.resolved(name).run
        working += len(gateways.what_is_working(name, run_home)) if standing[name].running else 0
        turning += len(gateways.what_is_turning(name, run_home))
    _as_table(("WHAT", "IS"), [
        ("version", __version__),
        ("install", str(REPO_ROOT)),
        ("fit to run", "yes" if not unfit else f"no — {unfit}"),
        ("supervisor", supervisor),
        ("configured agents", str(len(agents.known()))),
        ("running gateways", str(running)),
        ("live processes", str(working + turning)),
        ("active turns", str(turning)),
        # Said here because "am I backed up" is a question about the install rather than
        # about any agent, and the answer somebody needs is not how many copies there are
        # but whether anything is still making them.
        ("backups", _how_backups_stand(machine)),
    ])
    return 1 if unfit else 0


def _answered_within(patience: float, work, called: str) -> tuple:
    """Do something that may block inside the operating system, and give up on it.

    Returns `(True, what it gave back)`, or `(False, None)` when it did not answer in
    time or failed. **The bound belongs to every command that touches the directory, not
    only to health (R-BKP-29).** `status` grew this guard first, for a backup directory
    symlinked into cloud storage that blocks in `opendir` forever; `backups` then sat on
    the identical call with no bound at all, which is the one command that cannot answer
    without it.

    A Python thread cannot interrupt an operating-system `opendir`, but a daemon does not
    keep this one-shot CLI process alive: the blocked call is abandoned with the process
    rather than turning one unreachable filesystem into a command that never returns.
    """
    answered: queue.Queue = queue.Queue(maxsize=1)

    def carry() -> None:
        try:
            answered.put((True, work()))
        except BaseException:                           # pragma: no cover - defensive boundary
            answered.put((False, None))

    threading.Thread(target=carry, name=called, daemon=True).start()
    try:
        return answered.get(timeout=patience)
    except queue.Empty:
        return (False, None)


def _how_backups_stand(machine) -> str:
    """Whether daily copies run and how many exist, without waiting forever (R-BKP-28)."""
    reached, count_kept = _answered_within(
        BACKUP_STATUS_PATIENCE,
        lambda: len(backups.every(backups_home())),
        "rundesk-backup-status",
    )
    if not reached:
        count_kept = None
    held = ("unavailable" if count_kept is None else
            (f"{count_kept} kept" if count_kept else "none yet"))
    try:
        daily = machine.keeps_backups()
    except Exception:                                    # pragma: no cover - defensive
        return held
    return f"{held}, daily {'on' if daily else 'off'}"


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
    # What this agent keeps, resolved once and handed to whichever of the five acts on
    # it — the same reason the three directories are resolved once (R-AGT-9). A listing
    # only asks, so it is opened for reading and never built.
    try:
        whose = (agents.reading(args.name) if getattr(args, "act", None) in (None, "show")
                 else agents.records(args.name))
    except (store.Unreadable, store.TooNew, store.Behind, migration.Failed) as why:
        print(f"{args.name}: RECORDS UNREADABLE — {why}", file=sys.stderr)
        return 1
    act = getattr(args, "act", None)
    doing = {"add": _add_channel, "remove": _remove_channel, "show": _show_channel,
             "allow": _allow_channel,
             "instructions": _channel_instructions}.get(act, _list_channels)
    try:
        return doing(args, gateways, agents, whose)
    except Exception as why:   # noqa: BLE001 — a command boundary, reporting truthfully
        # **A write that could not happen is a refusal, not a traceback.** What this
        # replaced answered `False` when the record could not be written, and the command
        # said so and failed; asking the store instead means the failure arrives as an
        # exception, and one that reached here uncaught would tell an owner adding a
        # channel to read a stack trace. Caught broadly because *what* went wrong with
        # somebody else's disk matters far less than the channel not having been added.
        print(f"{args.name}: NOT CHANGED — {why}", file=sys.stderr)
        print(f"        what stands in the way:  rundesk doctor {args.name}",
              file=sys.stderr)
        return 1


#: How many of an agent's role runs a listing shows. Enough to cover what is in flight
#: and what finished today; the records hold the rest.
ROLE_RUNS_SHOWN = 20


def cmd_roles(args: argparse.Namespace, agents) -> int:
    """What an agent can hand heavy execution to, and what it has handed over."""
    if not agents.exists(args.name):
        print(f"{args.name}: NO SUCH AGENT", file=sys.stderr)
        print("        what there is:  rundesk agents", file=sys.stderr)
        return 1
    act = getattr(args, "act", None)
    if act == "run":
        return _hand_to_a_role(args, agents)
    if act in ("say", "stop", "resume"):
        return _guide_a_role(args, act)
    try:
        whose = agents.reading(args.name)
    except (store.Unreadable, store.TooNew, store.Behind, migration.Failed) as why:
        print(f"{args.name}: RECORDS UNREADABLE — {why}", file=sys.stderr)
        return 1
    if act == "show":
        return _show_role_run(args, whose)
    return _list_roles(args, whose)


def _list_roles(args: argparse.Namespace, whose) -> int:
    """The roles this agent may reach for, and the runs it has already admitted."""
    installed = role.known()
    if not installed:
        print("no roles installed")
    for slug in installed:
        try:
            one = role.read(slug)
        except role.NotARole as why:
            print(f"{slug}  UNUSABLE — {why}")
            continue
        print(f"{one.label}  {one.slug}  {one.revision[:12]}  "
              f"{one.posture}  [{' '.join(one.skills)}]")
        print(f"        {one.description}")
        if one.provider or one.model:
            # Said before anybody hands it work, because a pinned brain decides what this
            # role can do: not every brain can be sent to mid-turn, so a role pinned to
            # one that cannot is a role no `say` will ever reach (R-ROL-34).
            print("        it runs on "
                  + (provider.label(one.provider) if one.provider
                     else "whatever this turn is on")
                  + (f", model {one.model}" if one.model else ""))
        if one.missing:
            # Said every time it is listed. A set quietly smaller than its manifest is the
            # kind of difference nobody notices until the work comes back thin.
            print(f"        not installed here, so not given: {' '.join(one.missing)}")
    runs = whose.role_runs(limit=ROLE_RUNS_SHOWN)
    if not runs:
        return 0
    print()
    for row in runs:
        it = role_runs.shown(row)
        print(f"{it['id']}  {it['role']}  {it['state']}  {it['label']}"
              + (f"  in {it['target']}" if it["target"] else "")
              + ("  reviewed" if it["reviewed"] else ""))
    return 0


def _show_role_run(args: argparse.Namespace, whose) -> int:
    """One role run in full — never its brief, and never a local path (R-ROL-17)."""
    row = whose.role_run(args.run)
    if row is None:
        print(f"{args.name}/{args.run}: NO SUCH ROLE RUN", file=sys.stderr)
        print(f"        what there is:  rundesk roles {args.name}", file=sys.stderr)
        return 1
    it = role_runs.shown(row)
    for what in ("id", "role", "label", "revision", "posture", "state", "outcome",
                 "parent_run", "target", "retained_until"):
        print(f"{what:16}{it[what]}")
    # The brain it actually ran on, which is a question only the run can answer: the role
    # may have been edited since, and the agent reconfigured (R-ROL-34). Said only where
    # one was recorded — a run admitted by an older release ran on whatever its parent
    # turn resolved and nothing wrote down which that was.
    if it["provider"]:
        print(f"{'brain':16}{it['provider']}"
              + (f"  {it['model']}" if it["model"] else ""))
    print(f"{'skills':16}{' '.join(it['skills'])}")
    print(f"{'elapsed':16}{it['elapsed']}s")
    print(f"{'reviewed':16}{'yes' if it['reviewed'] else 'no'}")
    waiting = whose.words_waiting(args.run)
    if waiting:
        print(f"{'waiting to say':16}{waiting}")
    if row.get("stop_asked_at"):
        print(f"{'stop asked':16}{row['stop_asked_at']}")
    owed = role_runs.owed_review(args.name, args.run)
    if owed["owed"]:
        # Said only while one is owed, and with the count: a review tried many times and
        # never delivered is the shape of a surface that is not coming back, and nothing
        # else an owner can read says so.
        print(f"{'owed review':16}yes, tried {owed['attempts']}")
    return 0


def _hand_to_a_role(args: argparse.Namespace, agents) -> int:
    """Admit one role run for this agent, on behalf of the turn asking (R-ROL-4).

    **Only an agent's own turn may ask.** A role acts on a named agent's behalf
    and answers into that agent's conversation, so the run that admits it has to be one of
    that agent's — which is what `RUNDESK_RUN` names and what the records then prove.

    The brief is read from standard input rather than given as an argument: it is the task,
    it is often several paragraphs, and an argument would put it in `ps` and in a shell
    history where the rest of a turn's words never go.
    """
    parent = os.environ.get("RUNDESK_RUN") or ""
    if not parent:
        print(f"{args.name}: NOT ADMITTED — a role run is admitted by this agent's own "
              "turn, and nothing here is running one", file=sys.stderr)
        return 1
    if os.environ.get("RUNDESK_ROLE_RUN"):
        # Said early and cheaply. What actually refuses is the durable record below, which
        # is why this is allowed to be a variable at all (R-ROL-13).
        print(f"{args.name}: NOT ADMITTED — a role run cannot start another one",
              file=sys.stderr)
        return 1
    brief = sys.stdin.read()
    try:
        admitted = role_runs.admit(
            args.name, args.role, brief, parent,
            target=getattr(args, "target", None), label=getattr(args, "label", None),
            named=getattr(args, "provider", None), model=getattr(args, "model", None),
        )
    except role_runs.NotDelegable as why:
        print(f"{args.name}: NOT ADMITTED — {why}", file=sys.stderr)
        print(f"        what it can hand work to:  rundesk roles {args.name}",
              file=sys.stderr)
        return 1
    except (store.Unreadable, store.TooNew, store.Behind, migration.Failed) as why:
        print(f"{args.name}: RECORDS UNREADABLE — {why}", file=sys.stderr)
        return 1
    print(admitted.id)
    print(f"        {admitted.label} — {role.label(admitted.role)}, "
          f"retained until {admitted.retained_until}")
    print("        it runs in this agent's gateway; you are told when it reports back")
    return 0


def _guide_a_role(args: argparse.Namespace, act: str) -> int:
    """Say something to a role run, end one, or carry a finished one on (R-ROL-23).

    **Three verbs because there are three things to mean**, and each refusal names the one
    that was wanted. A single verb that guessed from the run's state would say something
    into work in flight when an owner meant to start it again, and spend a turn's money
    doing it.
    """
    said = sys.stdin.read() if act in ("say", "resume") else ""
    try:
        if act == "stop":
            if not role_runs.stop(args.name, args.run):
                print(f"{args.name}/{args.run}: ALREADY OVER — nothing was running to end",
                      file=sys.stderr)
                return 1
            print(f"{args.run} was asked to stop")
            print("        it ends as soon as this agent's gateway reaches it")
            return 0
        if act == "say":
            # Said *after* it was taken, never before: a line printed on the way in is a
            # line a refusal cannot take back, and this one reported success while the
            # command was busy failing.
            lands = role_runs.say(args.name, args.run, said)
            print(f"said to {args.run}")
            print(f"        {lands}")
            return 0
        role_runs.resume(args.name, args.run, said)
        print(f"{args.run} was carried on")
        print("        it starts again in the conversation it already had")
        return 0
    except role_runs.NotDelegable as why:
        print(f"{args.name}/{args.run}: NOT DONE — {why}", file=sys.stderr)
        print(f"        where it stands:  rundesk roles {args.name} show {args.run}",
              file=sys.stderr)
        return 1
    except (store.Unreadable, store.TooNew, store.Behind, migration.Failed) as why:
        print(f"{args.name}: RECORDS UNREADABLE — {why}", file=sys.stderr)
        return 1


#: What the credential a surface reads is kept in, beside that channel's own things. The
#: adapters that need one look here, so this is where one taken at the terminal is put.
SECRET_FILE = "token"


def _wants_a_secret(said: dict) -> bool:
    """Whether this check failed for want of a credential, asked of what it named.

    Read off `secret` — the *names* of the places the adapter reads one from — and never
    off `why`, which is the platform's own words and this command's to print rather than
    to parse (R-CAD-13).
    """
    return bool((said.get("secret") or {}).get("env"))


def _took_a_secret(args: argparse.Namespace, said: dict, home: Path) -> bool:
    """Take the credential this surface named, and keep it where the surface looks.

    From a pipe when asked for that, and otherwise from a terminal with echo off. Neither
    is an argument, so neither reaches `ps` or a shell history. Says whether it got one:
    a check that failed for want of a credential nobody can supply is a refusal, not a
    prompt in a script that would hang waiting for one.
    """
    named = ", ".join((said.get("secret") or {}).get("env") or [])
    if getattr(args, "token_stdin", False):
        given = sys.stdin.readline().strip()
    elif sys.stdin.isatty():
        given = getpass.getpass(f"        {args.kind} needs a credential ({named}): ").strip()
    else:
        return False
    if not given:
        return False
    home.mkdir(parents=True, exist_ok=True)
    at = home / SECRET_FILE
    at.write_text(given + "\n", encoding="utf-8")
    # Nobody else's to read. What is kept about a channel says a credential is present and
    # never what it is (R-CAD-12); this file is the credential, so the mode is the guard.
    os.chmod(at, 0o600)
    return True


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

    def checking() -> dict:
        return asyncio.run(channel.checked(at, carried, channel.environment(
            home=agents.paths(args.name)["run"], channel=args.channel, agent=args.name,
            channel_home=home, allow=args.allow, checking=True)))

    said = checking()
    if not said["ok"] and _wants_a_secret(said):
        # **The one credential it named, taken and kept, and then asked again.** Exporting a
        # variable before typing a command is friction that ends in the command failing after
        # everything else about it worked — but a token given as an argument is in `ps` for
        # every user on the machine and in a shell history for ever (R-CAD-11). So it is read
        # from a terminal that is not echoing it, or from a pipe, and written where this
        # adapter already looks. Asked *again* rather than assumed: the credential being
        # present is not the channel being reachable, and only the adapter can say which.
        if _took_a_secret(args, said, home):
            said = checking()
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
        if whose.channel(one) is not None:
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
        beside = agents.channel_home(args.name, one)
        beside.mkdir(parents=True, exist_ok=True)
        # The credential goes with the channel that was written, not with the name that was
        # checked. One `add` may write several, and each is started with the home of the
        # name it was written under — so a token left only in the check's directory is a
        # channel that proved itself at the terminal and cannot sign in at start-up.
        kept_secret = home / SECRET_FILE
        if kept_secret.is_file() and beside != home:
            shutil.copy2(kept_secret, beside / SECRET_FILE)
            os.chmod(beside / SECRET_FILE, 0o600)
        # **A new channel has introduced this agent to nobody**, written down before the
        # record exists so that everybody in the list that follows is owed one (R-CH-33).
        # This is also what tells a channel added today from one an older release wrote:
        # no record at all means the people on it have been reaching this agent for
        # months, and greeting them after an update would be rundesk claiming something
        # happened that did not.
        gateways.remember_no_one_welcomed(beside)
        whose.remember_channel(one, args.kind, args.allow, store.stamped(),
                               settings=shape["settings"], secret=said["secret"],
                               describes=shape["describes"],
                               instructions=shape[channel.INSTRUCTIONS] or None,
                               fills=shape[channel.FILLS], activity=args.activity)
        unlogged |= _note(gateways, args.name, f"channel '{one}' added ({args.kind})",
                          agents.resolved(args.name))
        print(f"{args.name}/{one}: ADDED — {shape['describes'] or args.kind}")
    if not any(one == args.channel for one, _ in named):
        # The check's own directory, when no channel ended up under that name. Removed only
        # if it is empty, so anything an owner had already put there is theirs and stays.
        # The credential is the one thing carried across for them, because a channel that
        # cannot sign in at start-up is one that proved itself and then went quiet.
        with contextlib.suppress(OSError):
            home.rmdir()
        if home.is_dir():
            beside = ", ".join(one for one, _ in named)
            if (home / SECRET_FILE).is_file():
                print(f"        the credential in {home} was carried to {beside}")
            print(f"        {home} is not empty — what else is in it belongs beside "
                  f"{beside} now")
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


def _schedules_reporting_to(kept, channel: str) -> list:
    """Which of this agent's schedules say what they came to on this surface.

    Asked before the surface is taken away, because the reference is what stops one outliving
    the other and the database refuses in its own words: an owner saw `FOREIGN KEY constraint
    failed` and was sent to `doctor`, which does not look at schedules at all.
    """
    return sorted(one["name"] for one in kept.schedules() if one.get("channel") == channel)


def _remove_channel(args: argparse.Namespace, gateways, agents, whose) -> int:
    if whose.channel(args.channel) is None:
        print(f"{args.name}/{args.channel}: NOT FOUND — no channel by that name",
              file=sys.stderr)
        return 1
    reporting = _schedules_reporting_to(whose, args.channel)
    if reporting:
        # Named, so the owner knows what to change. Refused rather than passed to the database
        # to refuse: it would, and in its own words — `FOREIGN KEY constraint failed`, followed
        # by advice to run `doctor`, which does not look at schedules at all.
        print(f"{args.name}/{args.channel}: NOT REMOVED — "
              f"{'schedule' if len(reporting) == 1 else 'schedules'} "
              f"{', '.join(repr(one) for one in reporting)} still report here", file=sys.stderr)
        print(f"        point them elsewhere or take them away:  "
              f"rundesk schedules {args.name}", file=sys.stderr)
        return 1
    whose.forget_channel(args.channel)
    unlogged = _note(gateways, args.name, f"channel '{args.channel}' removed",
                     agents.resolved(args.name))
    print(f"{args.name}/{args.channel}: REMOVED")
    return unlogged


def _allow_channel(args: argparse.Namespace, gateways, agents, whose) -> int:
    """Who may reach this agent here — shown, or changed (R-CAD-19).

    **Changed on the channel that is already there.** Who is responsible for an agent
    changes over its life, and the only way to say so was to take the agent off the
    surface and add it again — which throws away its instructions, its settings and
    whatever the adapter had kept for it, to change one line.

    With nothing to change this shows the list, one id to a line, so a script reads it
    without parsing a table. What is added and what is removed are decided in one hold
    below this, so replacing one person with another is never a moment with nobody
    allowed in it and never a change two owners can lose between them.
    """
    it = whose.channel(args.channel)
    if it is None:
        print(f"{args.name}/{args.channel}: NOT FOUND — no channel by that name",
              file=sys.stderr)
        return 1
    adding = [one for one in (args.add or []) if one is not None]
    removing = [one for one in (args.remove or []) if one is not None]
    if not adding and not removing:
        allowed = it.get("allow") or []
        if not allowed:
            # Nothing writes this and nothing should ever read it as a mode. Said rather
            # than printed as an empty list, which reads as a command that did nothing.
            print(f"{args.name}/{args.channel}: NO ONE ALLOWED")
            return 0
        for one in allowed:
            print(one)
        return 0
    was = list(it.get("allow") or [])
    try:
        resulting = whose.allow_channel(args.channel, add=adding, remove=removing)
    except ValueError as why:
        print(f"{args.name}/{args.channel}: NOT CHANGED — {why}", file=sys.stderr)
        print(f"        who is allowed now:  rundesk channels {args.name} allow "
              f"{args.channel}", file=sys.stderr)
        return 1
    if resulting == sorted(was):
        print(f"{args.name}/{args.channel}: UNCHANGED — {', '.join(resulting)}")
        return 0
    gone = [one for one in was if one not in resulting]
    if gone:
        # Forgotten here as well as by the gateway, because the gateway is exactly what is
        # *not* running while somebody rearranges who may reach an agent. Without it,
        # taking a person off and putting them back while nothing was up would leave them
        # written down as already introduced, and they would never be greeted (R-CH-33).
        try:
            gateways.forget_welcomed(
                agents.channel_home(args.name, args.channel), gone)
        except (OSError, _gateway.Unreadable) as why:
            # The change itself is written and stands. Only the note of who has already
            # been introduced could not be brought up to date, and the worst it costs is
            # one greeting somebody has had before.
            print(f"        who has been introduced could not be updated: {why}")
    print(f"{args.name}/{args.channel}: ALLOWED — {', '.join(resulting)}")
    unlogged = _note(gateways, args.name,
                     f"channel '{args.channel}' now allows {', '.join(resulting)}",
                     agents.resolved(args.name))
    if [one for one in resulting if one not in was]:
        # **What is written down is not what the adapter is holding.** A surface is handed
        # who it may listen to when it starts, so somebody added while the agent is running
        # is allowed by the record and still unknown to the program — and the introduction
        # rundesk owes them waits for the same moment. Said, because a new owner messaging
        # an agent that ignores them has no way to know why.
        print(f"        in effect when the channel next starts:  "
              f"rundesk restart {args.name}")
    return unlogged


def _channel_instructions(args: argparse.Namespace, gateways, agents, whose) -> int:
    """What this agent is told about the situation it is answering in (R-CH-22).

    Checked before it is written, and that is the point of writing it here rather than by
    hand: a name misspelled in a template is an instruction that goes quietly blank at
    every turn from then on, and says nothing about having done so. With nothing to set,
    this shows what is already there — so an owner can read back exactly what their agent
    will be told before anyone says anything to it.
    """
    it = whose.channel(args.channel)
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
    whose.tell_channel(args.channel, (args.said or "").strip() or None)
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
    it = whose.channel(args.channel)
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
        ("activity", "shown while it works" if it.get("activity")
                     else "only the answer"),
        ("reachable", "yes" if gateways.standing(
            args.name, agents.resolved(args.name).run).running
            else "no — the agent is not running"),
    ]
    _as_table(("WHAT", "IS"), rows)
    return 0


def _list_channels(args: argparse.Namespace, gateways, agents, whose) -> int:
    reachable = whose.channels()
    if not reachable:
        print(f"{args.name}: NO CHANNELS")
        print(f"        put it on one:  rundesk channels {args.name} add <channel> "
              f"--kind <kind> --allow <user>")
        return 0
    up = gateways.standing(args.name, agents.resolved(args.name).run).running
    _as_table(("CHANNEL", "KIND", "POINTS AT", "ALLOWED", "REACHABLE"), [
        (it["name"], str(it.get("kind", "-")), str(it.get("describes") or "-"),
         str(len(it.get("allow") or [])), "yes" if up else "no")
        for it in reachable
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
        env=dict(process.environment(whose.run or gateways.home(),
                                     agents=agents.agents_home()),
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


def _reading(name: str, agents) -> "store.Store | None":
    """What this agent keeps, opened for a command that only asks.

    `None` where the answer is a refusal already printed, so the three read-only verbs
    below say the same thing when an agent is missing or its records will not be read —
    written once, because three of them saying it three ways is three ways to be wrong.
    """
    if not agents.exists(name):
        print(f"{name}: NO SUCH AGENT — nothing of that name has been made", file=sys.stderr)
        print("        what there is:  rundesk agents", file=sys.stderr)
        return None
    try:
        return agents.reading(name)
    except (store.Unreadable, store.TooNew, store.Behind, migration.Failed) as why:
        print(f"{name}: RECORDS UNREADABLE — {why}", file=sys.stderr)
        print(f"        what stands in the way:  rundesk doctor {name}", file=sys.stderr)
        return None


def _wants_a_name(verb: str) -> int:
    """Refuse a verb that is about one agent and was given none, in our own words.

    Never argparse's usage code: a script has to be able to tell a command that is not
    there from one it typed wrongly, and that is the whole distinction (R-CMD-8).
    """
    print(f"{verb}: NAME REQUIRED — say which agent", file=sys.stderr)
    print("        what there is:  rundesk agents", file=sys.stderr)
    return 1


def cmd_runs(args: argparse.Namespace, gateways, agents) -> int:
    """What this agent has run, newest first.

    Read from what it keeps, with nothing started: a night's work is asked about far more
    often than it is done, and a listing that had to run a brain to answer would be one
    nobody uses (R-USE-10).
    """
    if not args.name:
        return _wants_a_name("runs")
    kept = _reading(args.name, agents)
    if kept is None:
        return 1
    found = kept.runs(limit=max(1, args.most))
    if not found:
        print(f"{args.name}: NOTHING RUN YET")
        print(f'        ask it something:  rundesk ask {args.name} "…"')
        return 0
    # Which schedule, where there was one. `source` alone says the clock started it and
    # leaves an owner to work out which of their schedules that was — and the whole reason to
    # read this at all is that something happened while nobody was watching.
    named = {row["id"]: row["name"] for row in kept.schedules()}
    _as_table(("RUN", "WHEN", "SOURCE", "ANSWERED BY", "OUTCOME", "COST"), [
        (one["id"], str(one["started_at"]), _admitted_by(one, named),
         _answered_by(one["provider"]), _came_to(one), _spent(one))
        for one in found
    ])
    return 0


def _came_to(one: dict) -> str:
    """What became of this run, and the word for why where the brain gave one (R-RUN-19).

    `failed` on its own answers "did it work" and not "what do I do about it" — a turn
    stopped by an account limit reads exactly like a crashed adapter or a bad flag. The word
    is added rather than substituted, so the outcome column still says the one thing it has
    always said and can still be grepped for.

    Absent for every run whose adapter did not classify the failure, which is every run
    written before there was a column for it. Nothing is inferred from the prose in `why`.
    """
    became = str(one["outcome"] or "running")
    word = one.get("because")
    return f"{became} ({word})" if word else became


def _admitted_by(one: dict, named: dict) -> str:
    """What started this run, said the way an owner would ask about it (R-RUN-16).

    A schedule is named rather than merely reported as one: a listing of six runs that all
    say `schedule` is a listing that answers "was this me?" and not "which of mine was it?".
    A schedule that has since been removed leaves the run saying what kind it was, because
    the run outlives it.
    """
    said = str(one["source"])
    which = named.get(one.get("schedule_id"))
    return f"{said} '{which}'" if which else said


def _answered_by(named: str) -> str:
    """Which provider answered, as the owner named it — elided from the front if it is a path.

    Their own words rather than the settled form that names its private directory: that one
    carries a hash so two adapters of one name cannot share a directory, and nobody typed a
    hash. A long path keeps its end, because the part that tells one adapter from another is
    the last of it.
    """
    said = str(named or "-")
    return said if len(said) <= _ANSWERED_BY_CHARS else "…" + said[-(_ANSWERED_BY_CHARS - 1):]


#: How much of a provider's name a listing shows. Long enough for every shipped adapter and
#: for the end of a path; the whole of it is in the record.
_ANSWERED_BY_CHARS = 28


def _spent(one: dict) -> str:
    """What one run cost, or that nobody said.

    A cost that never arrived reads as unknown rather than as nothing: a run that cost an
    unknown amount and one that cost zero are different facts, and a total that folded the
    first into the second would quietly claim to know more than it does (R-USE-7).
    """
    if not one["tokens_reported"]:
        return "not reported"
    # **Cached input is shown where the provider reported it** (R-USE-12). It is billed and
    # routinely dwarfs the fresh input beside it — one agent's fifty-six runs carried 101,510
    # fresh and 4,684,800 cached — so a row naming only the other two hid the whole of what
    # the run actually cost, and hid which conversations should have been started again.
    # Absent stays absent rather than becoming zero: a provider that reports no cache and one
    # that read nothing from it are different facts (R-USE-6).
    cached = one.get("tokens_cached")
    held = "" if cached is None else f" / {cached} cached"
    # **Cache writes are shown apart from fresh input** (R-USE-13), on the same rule as the
    # line above and for the opposite reason: a write is billed *above* fresh input, so a
    # run that folded them together priced its most expensive tokens as its cheapest. Absent
    # on every brain that does not report the split, and on every row written before there
    # was a column for it — where the two cannot be separated after the fact.
    written = one.get("tokens_written")
    made = "" if written is None else f" / {written} written"
    return f"{one['tokens_in'] or 0} in{held}{made} / {one['tokens_out'] or 0} out"


def cmd_usage(args: argparse.Namespace, gateways, agents) -> int:
    """What an agent has cost, in tokens. Every agent when none is named."""
    wanted = [args.name] if args.name else agents.known()
    if not wanted:
        print("NO AGENTS — nothing has cost anything yet")
        print("        make one:  rundesk add <agent> --provider <provider>")
        return 0
    rows = []
    for name in wanted:
        kept = _reading(name, agents)
        if kept is None:
            return 1
        spent = kept.usage()
        rows.append((
            name, str(spent["runs"]),
            # Absent rather than zero, all the way out to what is printed. `SUM` over no
            # rows is NULL and a run whose usage never arrived leaves it so, which is the
            # one distinction a spend limit reading this must not lose (R-USE-6).
            "-" if spent["input"] is None else str(spent["input"]),
            "-" if spent["output"] is None else str(spent["output"]),
            "-" if spent["cached"] is None else str(spent["cached"]),
            "-" if spent["written"] is None else str(spent["written"]),
            str(spent["unreported"]),
        ))
    _as_table(("AGENT", "RUNS", "IN", "OUT", "CACHED", "WRITTEN", "NOT REPORTED"), rows)
    return 0


def cmd_messages(args: argparse.Namespace, gateways, agents) -> int:
    """What has been said, newest first, across every surface this agent is reached on.

    The listing an agent reads about itself. `runs` says that work happened and `search`
    needs a word nobody always has — this is the one that answers "what was I just told,
    and what did I say", which is what a turn resuming a conversation it has no session for
    actually needs (R-STO-25).
    """
    if not args.name:
        return _wants_a_name("messages")
    kept = _reading(args.name, agents)
    if kept is None:
        return 1
    try:
        found = kept.latest(limit=max(1, args.most), since=args.since,
                            channel=args.channel, author=args.author, source=args.source,
                            conversation=args.conversation, who=args.who)
    except ValueError as why:
        # The closed sets say what they are rather than being quietly ignored, so a filter
        # nobody can spell is refused instead of answering a different question (R-STO-26).
        print(f"{args.name}: {why}", file=sys.stderr)
        return 1
    if not found:
        if args.conversation and not kept.has_conversation(args.conversation):
            # A conversation nobody has and a conversation with nothing in it are different
            # answers, and returning the empty listing for both is how an agent comes to
            # report that work it did never happened (R-STO-28).
            print(f"{args.name}: no conversation called {args.conversation}", file=sys.stderr)
            print("        the WHERE column names every one it has:  "
                  f"rundesk messages {args.name}", file=sys.stderr)
            return 1
        print(f"{args.name}: NOTHING SAID YET")
        print(f'        ask it something:  rundesk ask {args.name} "…"')
        return 0
    _as_table(("ID", "WHEN", "WHERE", "WHO", "MESSAGE"), [
        (str(one["id"]), str(one["at"]), f"{one['channel']}/{one['space']}",
         _said_by(one, args.name), " ".join(str(one["text"]).split())[:_MESSAGE_CHARS])
        for one in found
    ])
    return 0


def _said_by(one: dict, named: str) -> str:
    """Who said it: a person by their name, and the agent by its own.

    Two people in two direct messages are two conversations and would otherwise both read
    as `user`, which is the one thing this column exists to tell apart. A surface reports
    the name it shows a human — Discord hands over a display name rather than a number —
    and it is kept on the message, so it is shown wherever there is one.

    **The agent is named too**, because a listing that was asked for by name and answers
    `agent` spends a column saying the one thing its reader already knew. Said here rather
    than kept on the row: these are one agent's records, so the name is already the
    directory they stand in, and a copy on every message is a second place for it to be
    wrong. What stays generic is `rundesk` itself, which is not the agent and never a
    person.
    """
    if one.get("who"):
        return str(one["who"])
    return named if one["author"] == "agent" else str(one["author"])


#: How much of one message is shown. Far more than a search result shows, because these are
#: read for their content rather than scanned for a hit — an agent working out what it was
#: told needs the sentence, not the fact that a sentence exists. The whole of it is in the
#: record; `--most 1` on one id is how a reader asks for that.
_MESSAGE_CHARS = 255


def cmd_search(args: argparse.Namespace, gateways, agents) -> int:
    """What was said about something, wherever it was said and whoever said it.

    Unavailable is said out loud rather than answered as nothing found (R-STO-8): an empty
    answer and an impossible question look identical to whoever typed it, and one of them
    means "go and look somewhere else".
    """
    if not args.name or not args.words:
        print("SEARCH NEEDS AN AGENT AND SOMETHING TO LOOK FOR", file=sys.stderr)
        print(f'        like this:  rundesk search {args.name or "<agent>"} "the parser"',
              file=sys.stderr)
        return 1
    kept = _reading(args.name, agents)
    if kept is None:
        return 1
    try:
        found = kept.search(args.words, limit=max(1, args.most))
    except store.Unsearchable as why:
        print(f"{args.name}: SEARCHING UNAVAILABLE — {why}", file=sys.stderr)
        print("        every run is still listed and read:  rundesk runs "
              f"{args.name}", file=sys.stderr)
        return 1
    if not found:
        print(f"{args.name}: NOTHING SAID ABOUT THAT")
        return 0
    _as_table(("WHEN", "WHERE", "WHO", "SAID"), [
        (str(one["at"]), f"{one['channel']}/{one['space']}", str(one["author"]),
         " ".join(str(one["text"]).split())[:_SAID_CHARS])
        for one in found
    ])
    return 0


#: How much of one thing said is shown in a listing. The whole of it is in the record; this
#: is what fits on a line beside four other columns.
_SAID_CHARS = 80


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


def main(argv: list[str], gateways=None, machine=None, agents=None, skills=None,
         scripts=None, catalogs=None) -> int:
    """The command surface.

    What the commands act on is passed in rather than imported here, so this file knows
    the verbs and nothing about locks, records or process groups — and so every one of
    them is exercised without a gateway or a supervisor anywhere near it.
    """
    gateways = gateways if gateways is not None else _gateway
    machine = machine if machine is not None else _supervisor
    agents = agents if agents is not None else _agent
    skills = skills if skills is not None else skill
    scripts = scripts if scripts is not None else script
    catalogs = catalogs if catalogs is not None else catalog
    parser = build_parser()
    argv, handed_on = _handed_on(argv, _carries_a_tail(parser))
    args = parser.parse_args(argv)
    args.handed_on = handed_on

    if args.command is None:
        parser.print_help()
        return 0
    named = getattr(args, "name", None)
    # Every command speaks in an agent's human name while the rest of the program speaks
    # in its filesystem identity. Resolve that seam once: a case-insensitive slug reaches
    # a legacy spelling already on disk, and a name with spaces reaches the same agent as
    # its lowercase directory slug (R-AGT-40).
    if named is not None and args.command != "add":
        try:
            args.name = agents.command_name(named, _identities(agents, machine))
        except agents.NotAnAgentName as why:
            print(f"{named}: INVALID NAME — {why}", file=sys.stderr)
            return 1
    # What this install calls its jobs is *this process's* environment rather than a
    # collaborator's decision, so it is read from the module and not from the supervisor
    # passed in — and read once here, before a command runs, because a prefix that could
    # escape the jobs directory must stop the command rather than plant a job somewhere.
    try:
        _supervisor.prefix()
    except _supervisor.NotAPrefix as why:
        print(f"RUNDESK_JOB_PREFIX: INVALID — {why}", file=sys.stderr)
        return 1
    if args.command in PLANNED:
        return cmd_not_available(args.command, getattr(args, "act", None))
    if args.command == "version":
        return cmd_version(args)
    if args.command == "update":
        return cmd_update(args, gateways, machine, agents, catalogs)
    if args.command == "uninstall":
        return cmd_uninstall(args)
    if args.command == "agents":
        return cmd_agents(args, gateways, machine, agents)
    if args.command == "add":
        return cmd_add(args, gateways, machine, agents)
    if args.command == "configure":
        return cmd_configure(args, agents)
    if args.command == "doctor":
        return cmd_doctor(args, gateways, agents)
    if args.command == "ask":
        return cmd_ask(args, agents)
    if args.command == "serve":
        return cmd_serve(args, gateways, agents, skills)
    if args.command == "start":
        return cmd_start(args, gateways, machine, agents, skills)
    if args.command == "stop":
        return cmd_stop(args, gateways, machine, agents)
    if args.command == "remove":
        return cmd_remove(args, gateways, machine, agents)
    if args.command == "restart":
        return cmd_restart(args, gateways, machine, agents)
    if args.command == "status":
        return cmd_status(args, gateways, machine, agents)
    if args.command == "config":
        return cmd_config(args)
    if args.command == "backups":
        return cmd_backups(args, gateways, machine, agents)
    if args.command == "skills":
        return cmd_skills(args, agents, skills, gateways, catalogs)
    if args.command == "scripts":
        return cmd_scripts(args, scripts)
    if args.command == "roles":
        return cmd_roles(args, agents)
    if args.command == "channels":
        return cmd_channels(args, gateways, agents)
    if args.command == "schedules":
        return cmd_schedules(args, gateways, agents)
    if args.command == "logs":
        return cmd_logs(args, gateways, agents)
    if args.command == "runs":
        return cmd_runs(args, gateways, agents)
    if args.command == "usage":
        return cmd_usage(args, gateways, agents)
    if args.command == "messages":
        return cmd_messages(args, gateways, agents)
    if args.command == "search":
        return cmd_search(args, gateways, agents)

    # Unreachable through argparse, which rejects an unknown command before this —
    # but a dispatch that silently returns 0 for a verb nobody handled is how a
    # command comes to exist and do nothing.
    print(f"rundesk: no handler for '{args.command}'", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
