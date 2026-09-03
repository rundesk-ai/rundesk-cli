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
from typing import Any, Dict, Optional

from rundesk.agents import directory, records
from rundesk.channels import arriving
from rundesk.commands import Subcommands, failed
from rundesk.core import paths
from rundesk.delegations import kept as delegations
from rundesk.exits import OK
from rundesk.providers import (
    accounts,
    adapters,
    answering,
    instructions,
    kept,
    protocol,
    team,
    turns,
)
from rundesk.skills import grants
from rundesk.utils import locking
from rundesk.utils.terminal import as_table

TROUBLE = (accounts.Refused, adapters.NotRunnable, answering.Refused, directory.Refused,
           records.NotThere, records.Unreadable, turns.Busy, OSError)

#: What a person is shown for a capability an adapter did not claim. Absent means no, and saying so
#: as a word rather than a blank is what tells "it said no" apart from "nothing was asked".
NO = "no"
YES = "yes"


#: What somebody may type after `--situation`, and the block each names. **The only place a
#: situation has a name at all**: nothing stores one, and `instructions` takes the block itself — so
#: the name exists for the one reason names exist, which is that a person has to type something.
BY_A_PERSON = "person"
SITUATIONS = {
    BY_A_PERSON: instructions.USER_TO_AGENT,
    "schedule": instructions.SCHEDULE_TO_AGENT,
    "agent": instructions.AGENT_TO_AGENT,
}

#: Which block a turn was composed with, from the `conversations.source` written when it ran. The
#: words are `arriving`'s, and a source absent here is a person asking.
FROM_A_SOURCE = {
    arriving.FROM_SCHEDULE: instructions.SCHEDULE_TO_AGENT,
    arriving.FROM_AGENT: instructions.AGENT_TO_AGENT,
}


def register(sub: Subcommands) -> None:
    """`providers` on its own lists; the other two are named."""
    kept_here = sub.add_parser("providers", help="the brains this install can run")
    what = kept_here.add_subparsers(dest="what", metavar="<what>")

    what.add_parser("list", help="every provider adapter this install can run")

    aliases = what.add_parser("aliases", help="registered additional accounts for one provider")
    alias_what = aliases.add_subparsers(dest="alias_what", metavar="<what>")
    alias_list = alias_what.add_parser("list", help="list registered aliases and current status")
    alias_list.add_argument("provider", metavar="<provider>")
    alias_add = alias_what.add_parser("add", help="register one additional account")
    alias_add.add_argument("provider", metavar="<provider>")
    alias_add.add_argument("alias", metavar="<alias>")
    alias_remove = alias_what.add_parser("remove", help="remove one registered alias and its home")
    alias_remove.add_argument("provider", metavar="<provider>")
    alias_remove.add_argument("alias", metavar="<alias>")
    alias_remove.add_argument("--confirm", action="store_true")

    for verb, help_text in (("status", "check one account with the provider's official command"),
                            ("login", "run the provider's official interactive login"),
                            ("logout", "run the provider's official logout")):
        account = what.add_parser(verb, help=help_text)
        account.add_argument("provider", metavar="<provider>")
        account.add_argument("--alias", metavar="<alias>")
        if verb == "logout":
            account.add_argument("--confirm", action="store_true")

    asking = what.add_parser("check", help="ask one what it can do, offline")
    asking.add_argument("provider", metavar="<provider>",
                        help="a shipped name, one this install was given, or a path to a program")

    said = what.add_parser("instructions",
                           help="what a brain is told before it reads the task")
    said.add_argument("agent", metavar="<agent>", nargs="?",
                      help="fill the layers in for this agent")
    said.add_argument("--situation", metavar="<who asked>", default=BY_A_PERSON,
                      choices=list(SITUATIONS),
                      help=f"which of {', '.join(SITUATIONS)} to render (default: {BY_A_PERSON})")
    said.add_argument("--layers", action="store_true",
                      help="show only the byte breakdown, not the prompt itself")
    said.add_argument("--turn", metavar="<turn>", type=int,
                      help="re-compose what a past turn was sent, and say whether it still matches")

    taking = what.add_parser("run", help="take one scheduled turn here — what a firing starts")
    taking.add_argument("agent", metavar="<agent>", help="whose scheduled turn to take")
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
        if what == "aliases":
            return _aliases(args)
        if what == "status":
            return _account_status(args.provider, args.alias)
        if what == "login":
            return _account_login(args.provider, args.alias)
        if what == "logout":
            return _account_logout(args.provider, args.alias, args.confirm)
        if what == "instructions":
            return _instructions(getattr(args, "agent", None), args.situation, args.layers,
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


def _aliases(args: argparse.Namespace) -> int:
    """Register, list, or remove provider-neutral additional accounts."""
    what = getattr(args, "alias_what", None)
    if what is None:
        return _failed("aliases was not told what to do",
                       "list them with: rundesk providers aliases list <provider>")
    with locking.only_one(paths.lock(), "this install"):
        provider = _canonical_provider(args.provider)
        _supports_aliases(provider)
        if what == "list":
            there = accounts.known(provider)
            print(f"aliases for {args.provider} in {accounts.provider_at(provider)}")
            if not there:
                print("        no additional accounts registered")
                return OK
            as_table(("ALIAS", "STATUS"),
                     [(one.alias, adapters.account_status(provider, one.alias, one.home))
                      for one in there])
            return OK
        if what == "add":
            one = accounts.registered(provider, args.alias)
            print(f"registered {args.provider} ({one.alias})")
            print(f"        home    {one.home}")
            print(f"        status  {adapters.account_status(provider, one.alias, one.home)}")
            print(f"        login   rundesk providers login {args.provider} --alias {one.alias}")
            return OK
        if what == "remove":
            home = accounts.account_home(provider, args.alias)
            if not args.confirm:
                return _failed(
                    f"this would remove {args.provider} ({args.alias}) and its provider-owned home",
                    f"take   {home.parent if home else ''}",
                    "nothing was removed. To go ahead:",
                    f"rundesk providers aliases remove {args.provider} {args.alias} --confirm")
            used = _alias_in_use(provider, args.alias, include_references=True)
            if used:
                return _failed(used, "nothing was removed")
            gone = accounts.removed(provider, args.alias)
            print(f"removed {args.provider} ({args.alias})")
            print(f"        took   {gone}")
            return OK
    raise AssertionError(f"providers aliases {what} is registered and answered by nothing")


def _account_status(named: str, alias: Optional[str]) -> int:
    provider = _canonical_provider(named)
    home = accounts.account_home(provider, alias)
    state = adapters.account_status(provider, alias, home)
    print(f"{_shown_account(named, alias)}: {state}")
    return OK if state != "unable_to_check" else _failed(
        f"{_shown_account(named, alias)} was unable to check authentication")


def _account_login(named: str, alias: Optional[str]) -> int:
    provider = _canonical_provider(named)
    home = accounts.account_home(provider, alias)
    state = adapters.account_login(provider, alias, home)
    if state != "authenticated":
        return _failed(f"{_shown_account(named, alias)} login did not earn authenticated status")
    print(f"{_shown_account(named, alias)}: authenticated")
    return OK


def _account_logout(named: str, alias: Optional[str], confirming: bool) -> int:
    with locking.only_one(paths.lock(), "this install"):
        provider = _canonical_provider(named)
        home = accounts.account_home(provider, alias)
        if not confirming:
            return _failed(f"logout would target {_shown_account(named, alias)}",
                           "nothing was logged out. To go ahead:",
                           f"rundesk providers logout {named}"
                           + (f" --alias {alias}" if alias else "") + " --confirm")
        used = _alias_in_use(provider, alias, include_references=False)
        if used:
            return _failed(used, "nothing was logged out")
        state = adapters.account_logout(provider, alias, home)
    if state != "signed_out":
        return _failed(f"{_shown_account(named, alias)} logout did not earn signed-out status")
    print(f"{_shown_account(named, alias)}: signed_out")
    return OK


def _canonical_provider(named: str) -> str:
    return adapters.canonical(named)


def _supports_aliases(provider: str) -> None:
    if not adapters.capabilities(provider).get("account_aliases"):
        raise adapters.NotRunnable(f"the {provider} adapter does not support account aliases")


def _shown_account(provider: str, alias: Optional[str]) -> str:
    return f"{provider} ({alias})" if alias else f"{provider} (implicit default)"


def _alias_in_use(provider: str, alias: Optional[str], include_references: bool) -> str:
    """Why this exact account boundary cannot change now, or an empty string."""
    for agent in directory.known():
        for row in kept.list_unfinished_turns(agent):
            if accounts.same(str(row["provider_name"]), row.get("provider_alias"), provider, alias):
                if turns.standing(agent, int(row["conversation_id"])) is not False:
                    return (f"{_shown_account(provider, alias)} has an active turn for {agent}; "
                            "its account cannot change underneath it")
        if not include_references or alias is None:
            continue
        configured = records.read(directory.records(agent))
        if accounts.same(str(configured.get("provider_name") or ""),
                         configured.get("provider_alias"), provider, alias):
            return f"{agent} uses {_shown_account(provider, alias)} as its configured default"
        for one in delegations.outstanding(agent):
            if accounts.same(one.provider_name, one.provider_alias, provider, alias):
                return f"{one.delegation_id} still uses {_shown_account(provider, alias)}"
    return ""


def _besides_what_was_asked(said: Dict[str, Any]) -> Dict[str, Any]:
    """Whatever an adapter volunteered, kept exactly as it said it."""
    return {one: said[one] for one in said if one not in protocol.CAPABILITIES}


def _instructions(agent: str, situation: str, only_layers: bool,
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
    may_hand_off = bool(agent and situation == BY_A_PERSON)
    return _shown(instructions.build(
        situation=SITUATIONS[situation], variables=_about(agent),
        team=team.for_agent(agent) if may_hand_off else ""), only_layers)


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
    built = instructions.build(situation=_the_situation_it_ran_in(agent, row),
                               variables=_as_that_turn_saw_it(agent, row),
                               team=_team_that_turn_saw(agent, turn))
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


def _the_situation_it_ran_in(agent: str, row: Dict[str, Any]) -> str:
    """Which block that turn was composed with, off what is actually written down about it.

    **`conversations.source` is the record of who started a turn**, and it is the durable one: a
    word in a column with a `CHECK` behind it, written when the conversation was made. Read from
    there rather than from the name of a layer in the turn's own instruction record, which is a
    label for a byte breakdown and not a fact about the turn.

    A source this release has never heard of is a person asking, which is the safe way round for the
    reason it always was: what the other two blocks withhold are the rules that assume somebody is
    waiting.
    """
    stood = arriving.where_it_stands(agent, int(row["conversation_id"]))
    return FROM_A_SOURCE.get(stood[0] if stood else "", instructions.USER_TO_AGENT)


def _as_that_turn_saw_it(agent: str, row: Dict[str, Any]) -> Dict[str, object]:
    """The variables as they stood for that turn, off the turn's own columns."""
    said = dict(_about(agent))
    stood = arriving.where_it_stands(agent, int(row["conversation_id"]))
    caller = stood[1].split("/", 1)[0] if stood and stood[0] == arriving.FROM_AGENT else ""
    said.update({"provider_name": row["provider_name"], "access_mode": row["access_mode"],
                 "conversation_id": row["conversation_id"],
                 "caller_agent": caller,
                 "source_kind": stood[0] if stood else "unknown",
                 "audience_id": stood[1] if stood else "unknown",
                 # **Read off the turn, never looked up again.** This scanned every schedule for a
                 # matching id, which answered nothing at all once that schedule had been taken
                 # away — so a turn re-read after a tidy-up claimed nobody had scheduled it. The
                 # turn writes the name down at admission; what that turn saw is on the turn.
                 "schedule_name": row["schedule_name"] or "",
                 "skill_names": _skill_names_that_turn_saw(agent, int(row["id"]))})
    return said


def _team_that_turn_saw(agent: str, turn: int) -> str:
    """The compact team snapshot recorded with `turn`; old turns predate that field."""
    for record in kept.list_turn_records(agent, turn):
        if record["record_type"] != turns.INSTRUCTIONS:
            continue
        try:
            return str(json.loads(record["event_data"]).get("team") or "")
        except (TypeError, ValueError):
            return ""
    return ""


def _skill_names_that_turn_saw(agent: str, turn: int) -> str:
    """The active skill names recorded with `turn`, or today's names for an older turn."""
    for record in kept.list_turn_records(agent, turn):
        if record["record_type"] != turns.INSTRUCTIONS:
            continue
        try:
            event = json.loads(record["event_data"])
            if "skill_names" in event:
                return str(event["skill_names"])
        except (TypeError, ValueError):
            break
    return _skill_names(agent)


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
        "install_root": str(paths.home()),
        "provider_name": said.get("provider_name") or "",
        "access_mode": protocol.ACCESS_WORK,
        "schedule_name": "<the schedule>",
        "conversation_id": "<id>",
        "caller_agent": "<caller agent>",
        "source_kind": "<source>",
        "audience_id": "<audience>",
        "skill_names": _skill_names(agent),
    }


def _skill_names(agent: str) -> str:
    """The active granted skill names, in stable order."""
    try:
        return ", ".join(one.name for one in grants.held(agent)) or "none"
    except OSError:
        return "unavailable"


def _failed(why: str, *and_so: str) -> int:
    return failed(f"providers: FAILED — {why}", *and_so)
