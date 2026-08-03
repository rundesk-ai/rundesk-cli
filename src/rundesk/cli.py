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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rundesk import __version__, backups_home  # noqa: E402
from rundesk import agent as _agent  # noqa: E402
from rundesk import catalog  # noqa: E402
from rundesk import gateway as _gateway  # noqa: E402
from rundesk import script  # noqa: E402
from rundesk import skill  # noqa: E402
from rundesk.commands import NOT_AVAILABLE, cmd_not_available  # noqa: E402
from rundesk.commands.skills import cmd_scripts, cmd_skills  # noqa: E402
from rundesk.commands.update import cmd_uninstall, cmd_update, cmd_version  # noqa: E402
from rundesk.commands import history  # noqa: E402
from rundesk.commands.history import (  # noqa: E402
    cmd_logs, cmd_messages, cmd_runs, cmd_search, cmd_usage,
)
from rundesk.commands.backups import (  # noqa: E402
    cmd_backups,
)
from rundesk.commands.status import (  # noqa: E402
    cmd_status,
)
from rundesk.commands.config import (  # noqa: E402
    cmd_config,
)
from rundesk.commands.lifecycle import (  # noqa: E402
    cmd_remove, cmd_restart, cmd_serve, cmd_start, cmd_stop,
)
from rundesk.commands.channels import (  # noqa: E402
    cmd_channels,
)
from rundesk.commands.roles import (  # noqa: E402
    cmd_roles,
)
from rundesk.commands.schedules import (  # noqa: E402
    cmd_schedules,
)
from rundesk.commands.agents import (  # noqa: E402
    _identities, cmd_add, cmd_agents, cmd_ask, cmd_configure, cmd_doctor,
)
from rundesk import store  # noqa: E402
from rundesk import supervisor as _supervisor  # noqa: E402
from rundesk import turn  # noqa: E402
from rundesk import updater  # noqa: E402

#: Where this checkout lives — the thing an update replaces in place.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
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
        ('rundesk roles ava add archaeology --description "Trace one behaviour through '
         'the whole history of a repository." --skills python-patterns,python-testing '
         '--posture read',
         "write a new role — then rewrite the rules file it names, which is a generic "
         "skeleton until you do"),
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
    said.add_argument("-n", "--lines", type=int, metavar="<lines>", default=history.LOG_LINES,
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
    # The agent is named because every roles action names one, and a role is **not** that
    # agent's: it is written once and every named agent on this install may put it on.
    # What the command answers with says so, or the surface teaches the wrong model.
    written = handing.add_parser(
        "add", help="write a new role — a generic skeleton to rewrite for the specialty")
    written.add_argument("role", metavar="<role>",
                         help="what to call it — lowercase letters, digits and single "
                              "hyphens, and never one this install already has")
    # All three required, and the posture most deliberately of all: it is a real safety
    # narrowing — on some brains `read` is an allowlist with no shell in it at all — so
    # a default would pick the widest boundary on the author's behalf without saying so.
    written.add_argument("--description", required=True, metavar="<text>",
                         help="what it answers for and how heavy the work is, in one "
                              "sentence — what a named agent reads while deciding "
                              "whether to delegate at all")
    written.add_argument("--skills", required=True, metavar="<a,b,c>",
                         help="the skills every run of it is given, comma separated — at "
                              "least one; a name this machine has not got is carried and "
                              "reported rather than refused")
    # Not `choices=`: what a posture may be is decided where a role is read, and a second
    # copy here is a list that disagrees with itself the day a third one exists.
    written.add_argument("--posture", required=True, metavar="read|work",
                         help="how far a run of it may reach — `read` changes nothing, "
                              "and on some brains has no shell in it at all")
    written.add_argument("--provider", metavar="<provider>",
                         help="the brain every run of it uses, beating the parent turn's "
                              "— left out, a run continues on whatever its parent is on")
    written.add_argument("--model", metavar="<model>",
                         help="which model on that brain — what the brain itself calls it")
    # The mirror of `add`, where all but the brain fields are required: here every one is
    # optional, because what a flag does not name is what the role goes on saying. An
    # empty value is a decision rather than a spelling of "left out" — `--provider ""`
    # unpins a brain, which is the shape `schedules edit --instructions ""` already uses.
    changed = handing.add_parser(
        "edit", help="change what a role says about itself — never its rules")
    changed.add_argument("role", metavar="<role>",
                         help="which role — one this install has, by its own name")
    changed.add_argument("--description", metavar="<text>",
                         help="what it answers for and how heavy the work is, in one "
                              "sentence — replacing what it says now")
    # Said in these words because a reader who assumes it appends will silently narrow a
    # role: the set they meant to add one name to comes out holding only that name.
    changed.add_argument("--skills", metavar="<a,b,c>",
                         help="the skills every run of it is given, comma separated — "
                              "this replaces the whole set rather than adding to it, so "
                              "name every skill the role is to have")
    changed.add_argument("--posture", metavar="read|work",
                         help="how far a run of it may reach — `read` changes nothing, "
                              "and on some brains has no shell in it at all")
    changed.add_argument("--provider", metavar="<provider>",
                         help="the brain every run of it uses — an empty value unpins "
                              "one, and a run then continues on whatever its parent is on")
    changed.add_argument("--model", metavar="<model>",
                         help="which model on that brain — an empty value unpins one")
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
