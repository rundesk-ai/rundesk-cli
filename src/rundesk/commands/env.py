"""The values this install hands to the things it talks to — a Discord token, a Slack app's key.

Four verbs: list them, check one, set one, empty one. What is kept and why it is kept where it is
belongs to `core.secrets`; this decides only how a person types it and what they are shown.

**A value is never typed as an argument, and this is the security of the command.** `argv` is in the
shell's history file the moment you press return, and it is visible in `ps` to every other user on
the machine for as long as the command runs — so there is no `env set KEY value`, and there is no
flag that takes one. The value is read from the terminal without echoing it, or from a pipe when
something else is driving. Both are deliberate: a prompt in a script is a command that hangs, and
this product refuses those everywhere else it meets them.

**Nothing here ever prints a whole value.** Not in the table, not in an error, not in a refusal that
quotes what was typed. `secrets.hinted` is the only description of a value this command can produce.
"""

import argparse
import getpass
import sys
from typing import Optional

from rundesk.commands import Subcommands, failed
from rundesk.core import paths, secrets
from rundesk.exits import FAILED, OK
from rundesk.utils.terminal import as_table


def register(sub: Subcommands) -> None:
    """Put `env` on the parser, with one sub-verb for each thing done to a value.

    Note what is *not* here: no verb takes a value. `set` takes a name and reads the value itself.
    """
    said = sub.add_parser("env", help="the values rundesk hands to what it talks to")
    what = said.add_subparsers(dest="what", metavar="<what>")

    what.add_parser("list", help="every value this install keeps, shown only as a hint")

    asked = what.add_parser("check", help="whether one value is set")
    asked.add_argument("key", metavar="<key>", help="the name, as a shell variable is written")

    put = what.add_parser("set", help="keep a value under a name, typed rather than passed")
    put.add_argument("key", metavar="<key>", help="the name, as a shell variable is written")

    gone = what.add_parser("unset", help="empty a name, leaving the name")
    gone.add_argument("key", metavar="<key>", help="the name, as a shell variable is written")


def cmd_env(args: argparse.Namespace) -> int:
    """Answer whichever of the four was asked for; with none of them, list what there is."""
    try:
        paths.home()
    except paths.Refused as why:
        return _failed(str(why))

    what = getattr(args, "what", None)
    if what in (None, "list"):
        return _listed()
    if what == "check":
        return _checked(args.key)
    if what == "set":
        return _stated(args.key)
    if what == "unset":
        return _emptied(args.key)

    # Unreachable while every sub-verb above is answered, and that is the point.
    raise AssertionError(f"env {what} is registered on the parser and answered by nothing")


def _listed() -> int:
    """Every name, in order, with only a hint of what it holds."""
    try:
        held = secrets.kept()
    except secrets.Refused as why:
        return _failed(str(why), "nothing was listed")

    if not held:
        print(f"no values kept in {paths.secrets()}")
        print("        keep one with: rundesk env set <key>")
        return OK

    print(f"values in {paths.secrets()}")
    as_table(("NAME", "VALUE"),
             [(key, secrets.hinted(held[key])) for key in sorted(held)])
    return OK


def _checked(key: str) -> int:
    """Whether one name holds a value — an answer a script reads from the exit code.

    Exits non-zero when it is not set, so `rundesk env check DISCORD_TOKEN && ...` does the right
    thing in a shell. A name that was never placed and one that was emptied are told apart in the
    words, because they are different situations, and reported the same way to a script, because a
    script only wants to know whether it can go ahead.
    """
    trouble = secrets.name_trouble(key)
    if trouble:
        return _failed(trouble)
    try:
        held = secrets.kept()
    except secrets.Refused as why:
        return _failed(str(why))

    if key not in held:
        print(f"{key} has never been set here", file=sys.stderr)
        return FAILED
    if held[key].trouble:
        # Not "not set". Telling somebody that would send them to type a new value over one they
        # may still want back.
        return _failed(f"{key} {held[key].trouble}")
    if held[key].value is None:
        print(f"{key} is set to nothing", file=sys.stderr)
        return FAILED
    print(f"{key} is set — {secrets.hinted(held[key])}")
    return OK


def _stated(key: str) -> int:
    """Read a value from whoever is typing and keep it under this name."""
    trouble = secrets.name_trouble(key)
    if trouble:
        return _failed(trouble)

    said = typed(f"{key}: ")
    if said is None:
        return _failed("nothing was typed", "nothing was kept")

    try:
        secrets.stated(key, said)
    except (secrets.Refused, secrets.Stuck, OSError) as why:
        return _failed(str(why), "nothing was kept")

    print(f"{key} is set — {secrets.hinted(secrets.Held(said, None))}")
    return OK


def _emptied(key: str) -> int:
    """Empty a name, leaving the name so it is visible as switched off rather than absent."""
    trouble = secrets.name_trouble(key)
    if trouble:
        return _failed(trouble)
    try:
        secrets.cleared(key)
    except (secrets.Refused, secrets.Stuck, OSError) as why:
        return _failed(str(why), "nothing was changed")
    print(f"{key} is set to nothing")
    return OK


def typed(asking: str) -> Optional[str]:
    """A value from the person at the terminal, or from whatever is piping into this. `None` when
    there was nothing.

    **Public because `skills configure` reads a value the same way**, and there is exactly one right
    way to do it: everything in this docstring is the reason, and a second copy of it beside a second
    copy of the code is how one of them comes to be missing the `sys.stdin is None` case. The build
    this replaces reached across command modules for a *private* and its own notes recorded that as a
    trap; the fix is to say plainly that this is shared, not to duplicate it.

    Not echoed when there is a terminal, so it is not left on screen or in a scrollback buffer. Read
    as an ordinary line when there is not, so `printf %s "$TOKEN" | rundesk env set K` works in an
    installer — which is the case a prompt would turn into a command that hangs for ever.

    Either way it never touches `argv`, and that is the point of reading it here at all.
    """
    if sys.stdin is None:
        # Not the same as an empty pipe. With fd 0 closed outright, CPython sets `sys.stdin` to
        # `None` at start-up, and asking it anything is an `AttributeError` — which is not an
        # `OSError` and reached the person as a traceback.
        return None
    try:
        said = getpass.getpass(asking) if sys.stdin.isatty() else sys.stdin.readline()
    except (EOFError, KeyboardInterrupt, OSError, AttributeError):
        return None
    said = said.rstrip("\n")
    return said or None


def _failed(why: str, and_so: Optional[str] = None) -> int:
    """Say what went wrong — never quoting a value, only ever a name."""
    return failed(f"env: FAILED — {why}", *([and_so] if and_so else []))
