"""The surfaces an agent is reachable on, and who on them may be answered.

What is written down about a channel is part of what its agent keeps, asked for through
`store.py`; this only decides what an owner is asking for and hands it over. The seam itself
— resolving an adapter, framing a record each way — is `channel.py`, which knows nothing of
any platform, and neither does this.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import getpass
import os
import shutil
import sys
from pathlib import Path

from rundesk import channel
from rundesk import gateway as _gateway
from rundesk import migration
from rundesk import standing
from rundesk import store
from rundesk.commands import _as_table, _note


#: What the credential a surface reads is kept in, beside that channel's own things. The
#: adapters that need one look here, so this is where one taken at the terminal is put.
#:
#: **Decided by the seam now, not here** — the adapter that reads it back cannot import
#: this module, so the name belongs where the contract can state it (`channel.SECRET_FILE`).
#: Re-exported under the name this module has always used, so nothing that reaches for
#: `channels.SECRET_FILE` has to change.
SECRET_FILE = channel.SECRET_FILE


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


def _wants_a_secret(said: dict) -> bool:
    """Whether this check failed for want of a credential, asked of what it named.

    Read off `secret` — the *names* of the places the adapter reads one from — and never
    off `why`, which is the platform's own words and this command's to print rather than
    to parse (R-CAD-13).
    """
    return bool((said.get("secret") or {}).get("env"))


def _took_a_secret(args: argparse.Namespace, said: dict, home: Path) -> bool:
    """Take every credential this surface named, and keep each where the surface looks.

    From a pipe when asked for that, and otherwise from a terminal with echo off. Neither
    is an argument, so neither reaches `ps` or a shell history. Says whether it got any:
    a check that failed for want of a credential nobody can supply is a refusal, not a
    prompt in a script that would hang waiting for one.

    **One prompt each, because one value cannot be two credentials.** This read a single
    value however many were named, joined every name into one question — `slack needs a
    credential (SLACK_BOT_TOKEN, SLACK_APP_TOKEN):` — and wrote what it got into one file.
    So a surface that opens its connection with one credential and calls its API with
    another could never be added by the command that exists to add one: the second was
    left for the owner to place by hand, which is the exact thing R-CAD-11 says must not
    happen. `channel.named` has always kept a list and said why; this is the half that had
    not caught up. A pipe supplies them in the order they were named, one to a line.
    """
    secret = channel.named(said.get("secret")) or {}
    wanted = secret.get("env") or []
    files = secret.get("files") or []
    piped = getattr(args, "token_stdin", False)
    if not piped and not sys.stdin.isatty():
        return False
    took = 0
    home.mkdir(parents=True, exist_ok=True)
    for at, one in enumerate(wanted):
        if piped:
            given = sys.stdin.readline().strip()
        else:
            # Named one at a time, so an owner pasting two tokens knows which is being
            # asked for. Whichever is missing is what the adapter will say next.
            given = getpass.getpass(
                f"        {args.kind} needs a credential ({one}): ").strip()
        if not given:
            continue
        kept = home / (files[at] if at < len(files) else channel.SECRET_FILE)
        kept.write_text(given + "\n", encoding="utf-8")
        # Nobody else's to read. What is kept about a channel says a credential is present
        # and never what it is (R-CAD-12); this file is the credential, so the mode is the
        # guard.
        os.chmod(kept, 0o600)
        took += 1
    return took > 0


def _credential_files(said: dict, home: Path) -> list:
    """Which of the files this surface's credentials are kept in are really there.

    Read off what the adapter named rather than off a filename this module holds, so a
    surface needing two is carried whole and one needing none costs nothing.
    """
    secret = channel.named(said.get("secret")) or {}
    return [one for one in
            (home / name for name in secret.get("files") or []) if one.is_file()]


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
        # Every one of them, not only the first. A surface needing two credentials that
        # was handed one is a channel that proved itself at the terminal and cannot sign
        # in at start-up — the same failure this copy exists to prevent, one credential
        # further along.
        if beside != home:
            for kept_secret in _credential_files(said, home):
                shutil.copy2(kept_secret, beside / kept_secret.name)
                os.chmod(beside / kept_secret.name, 0o600)
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
            carried = _credential_files(said, home)
            if carried:
                print(f"        {'the credential' if len(carried) == 1 else 'the credentials'}"
                      f" in {home} {'was' if len(carried) == 1 else 'were'}"
                      f" carried to {beside}")
            print(f"        {home} is not empty — what else is in it belongs beside "
                  f"{beside} now")
    if len(named) > 1:
        # Said out loud, because they were made together and share the one allow-list that
        # was typed — and the whole reason they are separate channels is that a room and a
        # private conversation usually should not.
        print(f"        {len(named)} channels, one for each kind of place — "
              f"each has its own allowed list and its own instructions")
    if not standing.of(args.name, gateways, agents).running:
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
    #
    # **Asked of both places a credential may be, because the recommended one is the file.**
    # This looked only at the environment of the shell running `show` — and the flow the
    # documentation recommends, `--token-stdin`, never exports anything: it writes the value
    # beside the channel, which is where the adapter reads it. So a channel that signs in
    # perfectly reported `not set`, and sent an owner to fix something that was not wrong.
    secret = channel.named(it.get("secret")) or {}
    named = secret.get("env") or []
    files = secret.get("files") or []
    home = agents.channel_home(args.name, args.channel)

    def stands(at: int, one: str) -> str:
        if os.environ.get(one):
            return "present"
        kept = files[at] if at < len(files) else channel.SECRET_FILE
        # Never opened, only looked for: what is kept about a channel says a credential is
        # present and never what it is (R-CAD-12).
        with contextlib.suppress(OSError):
            if (home / kept).is_file():
                return "present"
        return "not set"

    rows = [
        ("kind", str(it.get("kind", "-"))),
        ("points at", str(it.get("describes") or "-")),
        ("allowed", ", ".join(it.get("allow") or []) or "nobody"),
        ("secret", ", ".join(
            f"{one} — {stands(at, one)}" for at, one in enumerate(named))
            or "none needed"),
        ("instructions", str(it.get(channel.INSTRUCTIONS)
                     or "nothing of its own — rundesk says where it is")),
        ("activity", "shown while it works" if it.get("activity")
                     else "only the answer"),
        ("reachable", "yes" if standing.of(args.name, gateways, agents).running
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
    up = standing.of(args.name, gateways, agents).running
    _as_table(("CHANNEL", "KIND", "POINTS AT", "ALLOWED", "REACHABLE"), [
        (it["name"], str(it.get("kind", "-")), str(it.get("describes") or "-"),
         str(len(it.get("allow") or [])), "yes" if up else "no")
        for it in reachable
    ])
    return 0
