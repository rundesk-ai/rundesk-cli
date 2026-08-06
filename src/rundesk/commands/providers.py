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
import json
from typing import Any, Dict

from rundesk.agents import directory, records
from rundesk.commands import Subcommands, failed
from rundesk.core import paths
from rundesk.exits import OK
from rundesk.providers import adapters, instructions, protocol
from rundesk.utils.terminal import as_table

TROUBLE = (adapters.NotRunnable, directory.Refused, records.NotThere, records.Unreadable, OSError)

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


def cmd_providers(args: argparse.Namespace) -> int:
    """A `Namespace` in, an exit code out."""
    what = getattr(args, "what", None)
    try:
        if what in (None, "list"):
            return _listed()
        if what == "check":
            return _checked(args.provider)
        if what == "instructions":
            return _instructions(getattr(args, "agent", None), args.trigger, args.layers)
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


def _instructions(agent: str, trigger: str, only_layers: bool) -> int:
    """What a brain would read, and what each layer of it costs.

    An agent is optional: with one, the layers are filled in as that agent's turn would fill them;
    without, the placeholders are left standing, which is how somebody reads the shape of a layer
    without needing an install with an agent in it.
    """
    built = instructions.build(trigger=trigger, variables=_about(agent))
    if not only_layers:
        print(built.text)
        print()
    as_table(("LAYER", "BYTES"), [(one.name, str(one.bytes_used)) for one in built.layers])
    print(f"\n{built.total_bytes} bytes in {len(built.layers)} layers, {built.sha256[:12]}")
    return OK


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

