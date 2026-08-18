"""The private Google bridge: capability grants cross only an inherited anonymous FD."""

import argparse
import sys
from typing import Optional

from rundesk.commands import Subcommands
from rundesk.core import google, secrets
from rundesk.exits import FAILED, OK


def register(sub: Subcommands) -> None:
    """Register a hidden protocol surface for integration processes, not people."""
    bridge = sub.add_parser("_google", help=argparse.SUPPRESS)
    sub._choices_actions = [choice for choice in sub._choices_actions
                            if choice.dest != "_google"]
    action = bridge.add_subparsers(dest="google_action", required=True)
    accounts = action.add_parser("accounts", help=argparse.SUPPRESS)
    accounts.add_argument("--profile", default="")
    accounts.add_argument("--response-fd", type=int, required=True)
    access = action.add_parser("access", help=argparse.SUPPRESS)
    access.add_argument("capability", choices=sorted(google.CAPABILITIES))
    access.add_argument("--email")
    access.add_argument("--profile", default="")
    access.add_argument("--response-fd", type=int, required=True)


def cmd_google(args: argparse.Namespace, authorizing: Optional[google.Authorizing] = None,
               posting: Optional[google.Posting] = None) -> int:
    """Answer through the FD; stderr carries only bounded, token-free refusals."""
    try:
        if args.google_action == "accounts":
            google.write_frame(args.response_fd, {
                "ok": True, "accounts": google.emails(args.profile)})
        else:
            held = google.access(args.capability, args.email, args.profile, authorizing, posting)
            google.write_frame(args.response_fd, {
                "ok": True, "access_token": held.token, "expires_at": held.expires_at,
                "email": held.email, "sub": held.sub,
            })
    except (google.Refused, secrets.Refused, secrets.Stuck) as trouble:
        print(f"google: FAILED — {trouble}", file=sys.stderr)
        return FAILED
    return OK
