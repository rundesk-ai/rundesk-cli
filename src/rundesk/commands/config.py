"""What this install's configuration says is in force.

Every effective value is stated in the file an install writes. A missing known value is
unreadable rather than quietly supplied from somewhere else, so what this prints and how the
install behaves cannot disagree (R-CMD-11).
"""

from __future__ import annotations

import argparse
import sys

from rundesk import config


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
