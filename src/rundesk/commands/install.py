"""Putting rundesk on this machine.

Reached two ways and both do the same work: `install.sh` fetches a release and hands off to this, and
somebody with a checkout runs it directly. There is no separate first-install path — an install that
is a special case of itself is an install with a route nobody exercises.

What it does, in order, and the order matters:

1. Refuse a root that must not be one, **before anything is written**.
2. Place the program at `app/`, staging and renaming so a failure leaves what was there.
3. Hand off to the release that just landed to settle the install — make the directories, write or
   fill in `config.json`, and carry the migrations.
4. Put `rundesk` on a PATH, refusing to write over a command belonging to something else.
5. Prove the installed command answers, and fail if it does not.

Step 3 is a handoff for the same reason it is one in `update`: installing over an existing install is
an update by another name, and the migration steps that must run belong to the release that just
landed rather than to whichever copy of rundesk happened to run the installer.

Step 5 is the one worth defending: an installer that reports success without checking has told
somebody their machine is ready when it is not, and they find out later and somewhere else.
"""

import argparse
import os
from pathlib import Path

from rundesk import __version__
from rundesk.commands import failed, the_reason, update
from rundesk.core import config, paths
from rundesk.exits import OK
from rundesk.lifecycle import tree
from rundesk.utils import programs

#: How long the installed command is given to answer before the install is called a failure.
ANSWER_SECONDS = 30


def cmd_install(args: argparse.Namespace) -> int:
    """Install rundesk, and refuse to report success it did not earn."""
    from_where = Path(args.source).expanduser().resolve() if args.source else paths.program()

    try:
        root = paths.home()
    except paths.Refused as why:
        return _failed(str(why))

    try:
        app = tree.place(from_where, root)
    except (tree.Refused, tree.HalfReplaced, OSError) as why:
        return _failed(str(why))

    # Settled by the release that just landed, not by this process. Installing over an existing
    # install is an update by another name, and the migration steps that must run are the *new*
    # release's — which are the ones now in `app/`, and not necessarily the ones this command
    # imported. One rule with no special case: whatever landed settles the install.
    gone_wrong = update.settled_by_the_new_release(app)
    if gone_wrong:
        return _failed(gone_wrong)

    try:
        at = tree.link(app, args.bin_dir)
    except (tree.Refused, OSError) as why:
        return _failed(str(why))

    # Written down because the directory is chosen here and can be anywhere. An uninstall that only
    # knew the usual places would leave the link dangling and report an ordinary success.
    try:
        config.stated("command_link", str(at), paths.data())
        config.moved(data=paths.data())
    except (config.Unreadable, config.Refused, config.Stuck) as why:
        return _failed(f"the command was linked and could not be recorded: {why}")

    answered = _answers(at)
    if answered:
        return _failed(f"rundesk was installed and would not run — {answered}")

    print(f"rundesk {__version__} installed")
    print(f"        program   {app}")
    print(f"        data      {paths.data()}")
    print(f"        command   {at}")
    _say_if_unreachable(at)
    return OK


def _answers(at: Path) -> str:
    """`""` when the installed command runs, otherwise why it did not.

    Run as a real subprocess, because what is being checked is exactly the thing importing the module
    would skip: that the link resolves, the interpreter is found, and the tree that landed is whole.

    **`status` rather than `version`, because this question must be answerable with the machine
    offline.** `version` asks GitHub what is published — so an installer that proved itself with it
    reported a failure it had not earned whenever GitHub was slow or unreachable, and dragged the
    network into every case in `tests/test_install.py`. `status` answers from this machine, and
    answers more: it is the one verb that refuses when the interpreter behind the link is too old,
    which is exactly the install that looks finished and cannot run.
    """
    ended = programs.run([str(at), "status"], ANSWER_SECONDS)
    if ended.trouble:
        return ended.trouble
    if ended.code != 0:
        return the_reason(ended.err) or the_reason(ended.out) or f"it ended {ended.code}"
    return ""


def _say_if_unreachable(at: Path) -> None:
    """Say when the command is not on this shell's PATH — and never edit the PATH to fix it.

    Where somebody's PATH is set is theirs. An installer that edits a shell profile has changed
    something it was not asked to change, in a file it does not own.
    """
    on_path = [Path(part).expanduser() for part in os.environ.get("PATH", "").split(os.pathsep) if part]
    if at.parent not in on_path:
        print(f"        note      {at.parent} is not on your PATH — add it to use `rundesk`")


def _failed(why: str) -> int:
    return failed(f"install: FAILED — {why}")
