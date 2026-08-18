"""`rundesk login` — connect an account through its own verified sign-in flow."""

import argparse
import sys
from typing import Optional

from rundesk.commands import Subcommands
from rundesk.core import google, secrets
from rundesk.exits import FAILED, OK


def register(sub: Subcommands) -> None:
    """The deliberately small public login surface."""
    login = sub.add_parser("login", help="connect an account through its verified sign-in flow")
    provider = login.add_subparsers(dest="login_provider", required=True)
    google = provider.add_parser("google", help="connect a Google account in the browser")
    google.add_argument("--profile", default="",
                        help="OAuth app profile (required only when more than one is configured)")


def cmd_login(args: argparse.Namespace,
              authorizing: Optional[google.Authorizing] = None) -> int:
    """Connect one Google identity, saying only its verified email."""
    try:
        email = google.authorize(args.profile, authorizing=authorizing)
    except (google.Refused, secrets.Refused, secrets.Stuck) as trouble:
        print(f"login: FAILED — {trouble}", file=sys.stderr)
        return FAILED
    print(f"Connected {email}")
    return OK
