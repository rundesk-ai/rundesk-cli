"""The values every program rundesk starts is given — placed, replaced and told apart.

**No form of this command ever prints a value** (R-SEC-4). What it prints instead is a
masked hint and a mark, which together answer which value this is and whether it changed.
An owner asking what one actually is is asking something nothing on the machine can answer,
and there is no flag that changes that — a value that can be read back off a machine is one
its owner has to assume has been.

A value is never an argument either (R-SEC-8). It is typed at a terminal that is not echoing
it, or piped in — the same shape `channels add --token-stdin` already has, and for the same
reason: an option's value is in `ps` for every user on the machine and in a shell history
for ever.

Imports `secret` directly rather than taking it as a collaborator, the way this layer already
imports `config` and `backup`. Everything it touches is under one directory named by one
variable, so a suite isolates the whole of it by pointing that variable somewhere — and a
stand-in would prove the mode, the refusal and the value that never prints against the
stand-in rather than against the module that has to hold them.
"""

from __future__ import annotations

import argparse
import getpass
import os
import shlex
import sys
from datetime import datetime, timezone

from rundesk import secret
from rundesk.commands import _as_table, _out_loud


#: What is shown where a value would be, so a column is never empty and never a value.
NOT_PRODUCED = "—"


def cmd_env(args: argparse.Namespace) -> int:
    """The values this install keeps, and what may be done to one."""
    if getattr(args, "where", False):
        # One line and nothing else: `install.sh` asks this rather than resolving the
        # directory a second time in shell, where the fallback would be a second copy of a
        # rule that already has one home (R-SEC-31).
        print(secret.home())
        return 0
    act = getattr(args, "act", None)
    try:
        if act == "set":
            return _set(args)
        if act == "show":
            return _show(args)
        if act == "unset":
            return _unset(args)
        if act == "check":
            return _check(args)
        return _listed()
    except secret.Unreadable as why:
        print(f"env: UNREADABLE — {why}", file=sys.stderr)
        print("        nothing is given out and nothing is written over it — what is in "
              "that file is still recoverable text", file=sys.stderr)
        return 1


def _now() -> str:
    """When this happened, as something a person reads and a file keeps."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def kept_from() -> str:
    """Where a change was made from — the only account a set an agent may run can have.

    Read off the turn's own environment. `RUNDESK_RUN` is present in every program a
    gateway starts and in nothing a person types, so its absence is the honest answer for
    a terminal rather than a guess about one.
    """
    if not os.environ.get("RUNDESK_RUN"):
        return "this terminal"
    named = os.environ.get("RUNDESK_AGENT_NAME") or os.environ.get("RUNDESK_AGENT")
    return f"{named}'s gateway" if named else "an agent's turn"


def _shown(kept: secret.Kept) -> str:
    """A value as it is ever shown: the end of it, and a mark of it."""
    return f"{kept.hint}  {kept.mark}" if kept.mark else kept.hint


def _listed() -> int:
    """Everything kept, and **nothing produced to answer it** (R-SEC-23)."""
    kept = secret.listed()
    if not kept:
        print("NO VALUES KEPT — every program rundesk starts is given nothing of its own")
        print("        keep one:  rundesk env set <name>")
        return 0
    _as_table(("NAME", "KEPT AS", "VALUE", "MARK", "LAST SEEN"),
              [(one.name, one.kept_as, one.hint, one.mark,
                one.last_seen or one.kept_at) for one in kept])
    print(f"\n{len(kept)} kept, and every program rundesk starts is given them")
    return 0


def _show(args: argparse.Namespace) -> int:
    """One value: how it is kept, and what tells it apart from another."""
    try:
        one = secret.described(args.value_name)
    except secret.Unknown:
        return _no_such(args.value_name)
    rows = [("name", one.name)]
    if one.kept_as == secret.FETCHED:
        rows.append(("kept as", "a command, run again each time a program starts"))
        # The words of a command, which are not a value — and are shown for exactly that
        # reason: it is the one thing about a fetched value an owner can check and correct.
        rows.append(("fetched by", " ".join(shlex.quote(word) for word in one.command)))
        rows.append(("value", f"{_shown(one)}, as last produced"))
        rows.append(("last seen", one.last_seen or "not yet"))
    else:
        rows.append(("kept as", "here, readable only by you"))
        rows.append(("value", _shown(one)))
    rows.append(("kept", one.kept_at))
    rows.append(("kept from", one.kept_from or "not recorded"))
    rows.append(("given to", "every program rundesk starts"))
    _as_table(("WHAT", "IS"), rows)
    return 0


def _taken(name: str, piped: bool):
    """The value itself, from a terminal that does not echo it or from a pipe.

    Never an argument, and **never a wait nobody is there to end** (R-SEC-9, R-SEC-10).

    **Reading standard input is asked for, never inferred**, which is the shape
    `_took_a_secret` already has one verb over and is not a stylistic echo of it. Inferring
    it from "stdin is not a terminal" reads an *open pipe with nothing in it* — which is
    exactly what a brain's tool shell hands its children — and `readline` on one blocks
    until the far end closes, which may be never. An agent running this would hang its own
    turn, and a suite walking the surface would hang the gate, with nothing anywhere saying
    what it was waiting for.

    Answers `None` when there is nobody to ask and nothing was piped, so the caller can say
    which of those it was.
    """
    if piped:
        return sys.stdin.readline()
    if not sys.stdin.isatty():
        return None
    return getpass.getpass(f"        the value for {name} (it will not be echoed): ")


def _set(args: argparse.Namespace) -> int:
    """Keep a value under a name, or replace the one already kept there."""
    name = args.value_name
    fetched_by = getattr(args, "fetched_by", None)
    try:
        secret.checked(name)
    except (secret.NotAName, secret.Refused) as why:
        return _not_kept(name, str(why))

    try:
        if fetched_by:
            command = shlex.split(fetched_by)
            if not command:
                return _not_kept(name, "no command was given to fetch it with")
            _out_loud(f"asking: {' '.join(shlex.quote(word) for word in command)}")
            change = secret.remember_command(name, command, now=_now(),
                                             kept_from=kept_from(), replace=True)
        else:
            given = _taken(name, getattr(args, "stdin", False))
            if given is None:
                return _not_kept(
                    name,
                    "there is no terminal to type it at and it was not asked to read one",
                    f"pipe it in:  printf '%s' \"$TOKEN\" | rundesk env set {name} --stdin")
            if not given.strip("\n"):
                return _not_kept(
                    name, "nothing was given, and an empty value is not a value",
                    f"take it away instead:  rundesk env unset {name}")
            change = secret.remember(name, given, now=_now(), kept_from=kept_from(),
                                     replace=True)
    except (secret.NotKept, secret.NotAName, secret.Refused) as why:
        return _not_kept(name, str(why))
    except OSError as why:
        return _not_kept(name, f"it could not be written: {why}")

    if change.unchanged:
        print(f"{name}: UNCHANGED — {_shown(change.kept)}")
        return 0
    if change.before is not None:
        print(f"{name}: REPLACED — was {_shown(change.before)}, "
              f"now {_shown(change.kept)}")
        # A program already running holds the environment it was started with, and nothing
        # can change one. Every program started from here on gets the new value, which for
        # a brain is the next turn and for a channel adapter is its next start.
        print("        every program started from here on is given the new one")
        return 0
    print(f"{name}: KEPT — {_shown(change.kept)}")
    if change.kept.kept_as == secret.FETCHED:
        print("        the command is kept and run again each time a program starts; "
              "what it printed is not")
    else:
        print("        every program rundesk starts is given it from now on")
    return 0


def _unset(args: argparse.Namespace) -> int:
    """Take one value away, and only that one."""
    try:
        gone = secret.forget(args.value_name)
    except secret.Unknown:
        return _no_such(args.value_name)
    except (secret.NotAName, OSError) as why:
        return _not_kept(args.value_name, str(why))
    print(f"{gone.name}: TAKEN AWAY — {_shown(gone)} is gone")
    print("        no copy of it is kept anywhere, and programs started from here on "
          "are not given it")
    return 0


def _check(args: argparse.Namespace) -> int:
    """Whether each kept value can still be produced — **without showing one**.

    This is the one verb that runs a fetching command, which is why it is a verb rather
    than something the listing does: a vault that wants a fingerprint would otherwise be
    asked for one every time somebody looked at what they had (R-SEC-22, R-SEC-23).
    """
    named = getattr(args, "value_name", None)
    try:
        kept = [secret.described(named)] if named else secret.listed()
    except secret.Unknown:
        return _no_such(named)
    if not kept:
        print("NO VALUES KEPT — there is nothing to reach")
        return 0
    for one in kept:
        if one.kept_as == secret.FETCHED:
            _out_loud(f"asking: {' '.join(shlex.quote(word) for word in one.command)}")
    # **Only the names asked after** — checking one value must not run every other
    # keeper this install has, unannounced and possibly with side effects of its own.
    said = secret.resolve(only=[one.name for one in kept])
    trouble = {one.name: one for one in said.trouble}
    if named:
        return _checked_one(kept[0], trouble.get(named))
    rows = []
    for one in kept:
        went = trouble.get(one.name)
        rows.append((one.name, one.kept_as,
                     one.hint if went is None else NOT_PRODUCED,
                     "yes" if went is None else f"NO — {_went(went)}"))
    _as_table(("NAME", "KEPT AS", "VALUE", "REACHED"), rows)
    if trouble:
        print(f"\n{len(trouble)} of {len(kept)} is not something a program would be given"
              if len(trouble) == 1 else
              f"\n{len(trouble)} of {len(kept)} are not something a program would be given")
        return 1
    print(f"\nall {len(kept)} would be given to a program starting now")
    return 0


def _checked_one(one: secret.Kept, went) -> int:
    if went is None:
        print(f"{one.name}: REACHED — {_shown(one)}")
        return 0
    _said_first()
    print(f"{one.name}: NOT REACHED — {_went(went)}", file=sys.stderr)
    print(f"        what rundesk asks for it:  rundesk env show {one.name}",
          file=sys.stderr)
    return 1


def _went(went: secret.Trouble) -> str:
    """Which of the two kinds of not-given this was, in three words rather than one.

    **A command that could not answer is not one that answered no** — the value may exist
    and be perfectly good, and reading a timeout as "there is no value" is how a working
    credential comes to be replaced by somebody who believed it had gone.
    """
    said = went.why or "it gave nothing back"
    return said if went.answered else f"could not answer: {said}"


def _said_first() -> None:
    """Put out what was already printed before saying what went wrong.

    Standard output is buffered a block at a time when it is piped and standard error is
    not, so a progress line written first arrives *after* the refusal — which reads as a
    command that reported a failure and then went on working.
    """
    sys.stdout.flush()


def _no_such(name) -> int:
    _said_first()
    print(f"{name}: NO SUCH VALUE — nothing is kept under that name", file=sys.stderr)
    print("        what there is:  rundesk env", file=sys.stderr)
    return 1


def _not_kept(name: str, why: str, hint: str = "") -> int:
    _said_first()
    print(f"{name}: NOT KEPT — {why}", file=sys.stderr)
    print(f"        {hint}" if hint else
          "        nothing was written, so no program is given a value that is not there",
          file=sys.stderr)
    return 1
