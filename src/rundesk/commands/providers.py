"""The brains this install can run, and what one is told before it reads a word of the task.

Three verbs, and all three are offline: they run no turn, need no account and reach no network.

`rundesk providers` lists what this install can run and whether each is really there.

`rundesk providers check <provider>` asks one what it can do — the same question a turn asks before
it is admitted — and shows the answer as the adapter gave it, including anything it reported that
rundesk did not ask for, because a version an adapter volunteers is exactly what somebody reads a
month later to find out what changed.

`rundesk providers instructions <agent>` prints what a brain would be told, with a byte breakdown per
layer. **That is the whole of how prompting stays maintainable here**: a change is inspected before
it ships rather than inferred from how an agent behaved afterwards, and the fingerprint says whether
anything changed at all.

This decides only how a person types it and what they are shown. Where an adapter is found belongs to
`providers.adapters`, what it may say belongs to `providers.protocol`, and what a brain reads belongs
to `providers.instructions`.
"""

import argparse
import contextlib
import json
from typing import Any, Dict, Optional

from rundesk.agents import directory, records
from rundesk.commands import Subcommands, failed
from rundesk.core import paths
from rundesk.exits import OK
from rundesk.providers import adapters, answering, instructions, kept, protocol, turns
from rundesk.schedules import kept as schedules_kept
from rundesk.utils.terminal import as_table

TROUBLE = (adapters.NotRunnable, answering.Refused, directory.Refused,
           records.NotThere, records.Unreadable, turns.Busy, OSError)

#: What a person is shown for a capability an adapter did not claim. Absent means no, and saying so
#: as a word rather than a blank is what tells "it said no" apart from "nothing was asked".
NO = "no"
YES = "yes"


def register(sub: Subcommands) -> None:
    """`providers` on its own lists; the other two are named."""
    kept_here = sub.add_parser("providers", help="the brains this install can run")
    what = kept_here.add_subparsers(dest="what", metavar="<what>")

    what.add_parser("list", help="every provider adapter this install can run")

    asking = what.add_parser("check", help="ask one what it can do, offline")
    asking.add_argument("provider", metavar="<provider>",
                        help="a shipped name, one this install was given, or a path to a program")

    said = what.add_parser("instructions",
                           help="what a brain is told before it reads the task")
    said.add_argument("agent", metavar="<agent>", nargs="?",
                      help="fill the layers in for this agent")
    said.add_argument("--trigger", metavar="<situation>", default=instructions.A_PERSON_ASKED,
                      choices=list(instructions.TRIGGERS),
                      help="which situation to render (default: a person asking)")
    said.add_argument("--layers", action="store_true",
                      help="show only the byte breakdown, not the prompt itself")
    said.add_argument("--turn", metavar="<turn>", type=int,
                      help="re-compose what a past turn was sent, and say whether it still matches")

    taking = what.add_parser("run", help="take one scheduled turn here — what a firing starts")
    taking.add_argument("agent", metavar="<agent>")
    taking.add_argument("--schedule", metavar="<schedule>", required=True,
                        help="which schedule this turn is for")


def cmd_providers(args: argparse.Namespace) -> int:
    """A `Namespace` in, an exit code out."""
    what = getattr(args, "what", None)
    try:
        if what in (None, "list"):
            return _listed()
        if what == "check":
            return _checked(args.provider)
        if what == "instructions":
            return _instructions(getattr(args, "agent", None), args.trigger, args.layers,
                                 args.turn)
        if what == "run":
            return _took_a_turn(args.agent, args.schedule)
    except TROUBLE as why:
        return _failed(str(why))
    raise AssertionError(f"providers {what} is registered on the parser and answered by nothing")


def _listed() -> int:
    """Every adapter this install can run, and where each was found."""
    there = adapters.known()
    print(f"providers in {paths.code() / adapters.SHIPPED_IN} "
          f"and {paths.data() / adapters.GIVEN_IN}")
    if not there:
        print("\nno provider adapter here yet — put an executable in either directory, or name "
              "one by path when adding an agent")
        return OK
    as_table(("PROVIDER", "PROGRAM"), [(one, str(adapters.where(one))) for one in there])
    return OK


def _checked(provider: str) -> int:
    """What one adapter says it can do, asked the way a turn asks it.

    Everything it answered is shown, not only the five things rundesk asks about: an adapter
    reporting its own brain's version is answering a question we did not ask, and that is the line
    somebody reads when a vendor moves under them.
    """
    at = adapters.where(provider)
    said = adapters.capabilities(provider)
    print(f"{provider}\n  program   {at}")
    as_table(("CAN", "IT SAYS"),
             [(one, YES if said.get(one) else NO) for one in protocol.CAPABILITIES])
    extra = _besides_what_was_asked(said)
    if extra:
        print("\nit also said, and rundesk did not ask:")
        as_table(("NAME", "VALUE"), [(one, json.dumps(extra[one])) for one in sorted(extra)])
    if not said:
        print("\nit answered nothing, which is a complete answer: it can do none of the above")
    return OK


def _besides_what_was_asked(said: Dict[str, Any]) -> Dict[str, Any]:
    """Whatever an adapter volunteered, kept exactly as it said it."""
    return {one: said[one] for one in said if one not in protocol.CAPABILITIES}


def _instructions(agent: str, trigger: str, only_layers: bool,
                  turn: Optional[int] = None) -> int:
    """What a brain would read, and what each layer of it costs.

    An agent is optional: with one, the layers are filled in as that agent's turn would fill them;
    without, the placeholders are left standing, which is how somebody reads the shape of a layer
    without needing an install with an agent in it.
    """
    # **Every refusal in this product ends with what to type**, and a name that is not an agent is
    # the one somebody most often reaches by a typo — asked here, the way `ask` and `turns` ask it.
    trouble = directory.not_an_agent(agent) if agent else ""
    if trouble:
        return _failed(trouble, "see what there is with: rundesk agents")
    if turn is not None:
        if not agent:
            return _failed("a turn belongs to an agent, so say which one",
                           "rundesk providers instructions <agent> --turn <turn>")
        return _what_a_turn_was_sent(agent, turn, only_layers)
    return _shown(instructions.build(trigger=trigger, variables=_about(agent)), only_layers)


def _what_a_turn_was_sent(agent: str, turn: int, only_layers: bool) -> int:
    """Re-compose what a past turn was sent, and say whether this release still composes it.

    **Nothing stores the prompt.** A fingerprint and a byte count are kept instead, and the words
    are re-derived from the inputs that produced them — every one of which is on the turn or on the
    record written beside it. That is a better audit than a stored blob and forty bytes instead of
    five kilobytes: a stored copy survives a change to the composer, and this one *detects* it.

    So a match prints the prompt, and a mismatch says so plainly rather than showing today's words
    as though they were the ones that turn was sent.
    """
    row = kept.get_turn(agent, turn)
    built = instructions.build(trigger=_the_situation_it_ran_in(agent, turn),
                               variables=_as_that_turn_saw_it(agent, row))
    print(f"turn {turn}, {row['created_at']}")
    if built.sha256 != row["instructions_sha256"]:
        print(f"\nthis release composes a different prompt for these inputs "
              f"({built.sha256[:12]} against the recorded {(row['instructions_sha256'] or '')[:12]}"
              f", {built.total_bytes} bytes against {row['instructions_bytes']}) — what is below is "
              f"today's words and not the ones that turn was sent")
        print()
        return _shown(built, only_layers)
    print(f"unchanged since it ran, {row['instructions_sha256'][:12]}\n")
    return _shown(built, only_layers)


def _the_situation_it_ran_in(agent: str, turn: int) -> str:
    """Which situation that turn was composed for, off the record written beside it.

    Read from the layers rather than kept as a column of its own: the situation *is* the layer that
    is not the core, so a column would be the same fact written down twice and free to disagree.
    """
    for one in kept.list_turn_records(agent, turn):
        if one["record_type"] != "instructions":
            continue
        with contextlib.suppress(ValueError, TypeError, KeyError):
            for layer in json.loads(one["event_data"])["layers"]:
                if layer["name"] in instructions.TRIGGERS:
                    return str(layer["name"])
    return instructions.A_PERSON_ASKED


def _as_that_turn_saw_it(agent: str, row: Dict[str, Any]) -> Dict[str, object]:
    """The variables as they stood for that turn, off the turn's own columns."""
    said = dict(_about(agent))
    said.update({"provider_name": row["provider_name"], "access_mode": row["access_mode"],
                 "conversation_id": row["conversation_id"],
                 "schedule_name": _the_schedule(agent, row["schedule_id"])})
    return said


def _the_schedule(agent: str, schedule_id: Optional[int]) -> str:
    """What the schedule that caused a turn is called, or nothing when no schedule did."""
    if not schedule_id:
        return ""
    for one in schedules_kept.all(agent):
        if one["id"] == schedule_id:
            return str(one["name"])
    return ""


def _shown(built: instructions.Prompt, only_layers: bool) -> int:
    if not only_layers:
        print(built.text)
        print()
    as_table(("LAYER", "BYTES"), [(one.name, str(one.bytes_used)) for one in built.layers])
    print(f"\n{built.total_bytes} bytes in {len(built.layers)} layers, {built.sha256[:12]}")
    return OK


def _took_a_turn(agent: str, schedule: str) -> int:
    """One scheduled turn, in this process. **What a firing starts, and rarely typed by a person.**

    Documented the way `gateways run` is: it exists because something has to be the program a
    schedule's firing spawns, and a verb that is only reachable from inside the product is a verb
    nobody can debug.

    **Exit `0` if and only if the turn finished.** `schedules.firing` reads this code to decide
    whether the firing completed or failed, so a turn that did not answer must not look like one that
    did — that is the whole of what a schedule's owner reads the next morning.
    """
    got = answering.for_a_schedule(agent, schedule)
    turns.note(agent, f"schedule {schedule}: turn {got.turn} {got.turn_status}"
                      + (f" — {got.failure_message}" if got.failure_message else ""))
    if got.worked:
        return OK
    # **The closed word as well as the prose.** This is the unattended path — nobody was watching
    # — so the one thing its owner needs from it the next morning is whether waiting will help.
    return _failed(f"{agent} did not answer the schedule {schedule} — "
                   f"{got.failure_message or got.turn_status}",
                   *([protocol.what_to_do_about(got.failure_code)] if got.failure_code else []),
                   f"what it did:  rundesk turns {agent} {got.turn}")


def _about(agent: str) -> Dict[str, object]:
    """The variables a layer may read, for this agent — or none of them, for nobody in particular."""
    if not agent:
        return {}
    trouble = directory.not_an_agent(agent)
    if trouble:
        raise records.NotThere(trouble)
    said = records.read(directory.records(agent))
    return {
        "agent_name": agent,
        "agent_home": str(directory.home(agent)),
        "provider_name": said.get("agent_provider") or "",
        "access_mode": protocol.ACCESS_WORK,
        "schedule_name": "<the schedule>",
        "conversation_id": "<id>",
    }


def _failed(why: str, *and_so: str) -> int:
    return failed(f"providers: FAILED — {why}", *and_so)

