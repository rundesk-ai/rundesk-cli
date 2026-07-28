"""What the command actually does. Standard library only.

The command contract this obeys is the one in the `building-integration-clis` skill, and it
is not decoration — an agent reads `--help` to decide what is possible, `status` to decide
whether it can work at all, and stderr plus a non-zero exit to know that what it asked for
did not happen.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import store

WHAT = "example"


def main(argv: list[str], state: Path) -> int:
    parser = argparse.ArgumentParser(
        prog=WHAT,
        description="One line an agent can act on, with no credential in it.",
    )
    parser.add_argument("--json", action="store_true",
                        help="structured output instead of the compact text an agent reads")
    doing = parser.add_subparsers(dest="doing", required=True)

    doing.add_parser("status", help="whether this can reach the service, and as whom")

    listing = doing.add_parser("list", help="recent items, newest first")
    listing.add_argument("--limit", type=int, default=20,
                         help="how many at most (default: 20)")

    args = parser.parse_args(argv)
    if args.doing == "status":
        return _status(state, args)
    if args.doing == "list":
        return _list(state, args)
    return 2


def _status(state: Path, args) -> int:
    """Reachable, as whom, and where the records are — the three things worth knowing.

    Says which credentials are missing **by name**, never their values, and answers without
    a network where it can: "you have no token" is a better answer than a timeout.
    """
    missing = [name for name in ("EXAMPLE_TOKEN",) if not _credential(name)]
    said = {
        "plugin": WHAT,
        "records": str(state / store.RECORDS),
        "credentials_missing": missing,
        "ready": not missing,
    }
    if args.json:
        print(json.dumps(said, indent=2))
    else:
        print(f"{WHAT}: {'ready' if said['ready'] else 'not ready'}")
        print(f"  records  {said['records']}")
        if missing:
            print(f"  missing  {', '.join(missing)}")
            print(f"  set them in  {_config_home()}/env")
    return 0 if said["ready"] else 1


def _list(state: Path, args) -> int:
    """Bounded by default, because an agent's context is the scarce thing here."""
    try:
        conn = store.open(state)
    except store.Unusable as why:
        print(f"{WHAT}: {why}", file=sys.stderr)
        return 1
    try:
        rows = conn.execute(
            "SELECT ref, title FROM item ORDER BY seen_at DESC LIMIT ?", (args.limit,)
        ).fetchall()
    finally:
        conn.close()
    if args.json:
        print(json.dumps([dict(one) for one in rows], indent=2))
        return 0
    if not rows:
        print("nothing yet")
        return 0
    for one in rows:
        print(f"{one['ref']}  {one['title']}")
    return 0


def _config_home() -> Path:
    """Where credentials live — outside the plugin, and outside everything rundesk backs up.

    Rundesk sweeps its whole data directory into backups, so a token written beside the
    records would be copied into every archive an owner keeps. This is the other reason the
    manifest carries credential *names* only.
    """
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / WHAT


def _credential(name: str) -> str | None:
    """The process environment first, then the plugin's own env file. Never a shell profile.

    Rundesk deliberately gives programs a small environment, so anything exported in the
    owner's interactive shell is not there. Reading the file is what makes this work at all.
    """
    if os.environ.get(name):
        return os.environ[name]
    at = Path(os.environ.get(f"{WHAT.upper()}_ENV_FILE") or _config_home() / "env")
    try:
        for line in at.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip().strip("'\"") or None
    except OSError:
        return None
    return None
