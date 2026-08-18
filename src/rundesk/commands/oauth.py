"""Private provider-neutral OAuth bridge over an inherited anonymous socket."""

import argparse
import sys
from typing import Optional

from rundesk.commands import Subcommands
from rundesk.core import oauth, secrets
from rundesk.exits import FAILED, OK
from rundesk.skills import oauth as declarations


def register(sub: Subcommands) -> None:
    bridge = sub.add_parser("_oauth", help=argparse.SUPPRESS)
    sub._choices_actions = [choice for choice in sub._choices_actions if choice.dest != "_oauth"]
    action = bridge.add_subparsers(dest="oauth_action", required=True)
    accounts = action.add_parser("accounts", help=argparse.SUPPRESS)
    accounts.add_argument("provider")
    accounts.add_argument("--profile", default="")
    accounts.add_argument("--response-fd", type=int, required=True)
    access = action.add_parser("access", help=argparse.SUPPRESS)
    access.add_argument("provider")
    access.add_argument("capability")
    access.add_argument("--email")
    access.add_argument("--profile", default="")
    access.add_argument("--response-fd", type=int, required=True)


def cmd_oauth(args: argparse.Namespace, authorizing: Optional[oauth.Authorizing] = None,
              posting: Optional[oauth.Posting] = None) -> int:
    try:
        provider = declarations.named(args.provider)
        if args.oauth_action == "accounts":
            oauth.write_frame(args.response_fd, {"ok": True,
                                                  "accounts": oauth.emails(provider, args.profile)})
        else:
            held = oauth.access(provider, args.capability, args.email, args.profile,
                                authorizing, posting)
            oauth.write_frame(args.response_fd, {
                "ok": True, "access_token": held.token, "token_type": "Bearer",
                "expires_at": held.expires_at, "email": held.email, "subject": held.subject,
            })
    except (oauth.Refused, declarations.Refused, secrets.Refused, secrets.Stuck) as trouble:
        try:
            oauth.write_frame(args.response_fd, {"ok": False, "error": str(trouble)})
        except (oauth.Refused, OSError):
            pass
        print(f"oauth: FAILED — {trouble}", file=sys.stderr)
        return FAILED
    return OK
