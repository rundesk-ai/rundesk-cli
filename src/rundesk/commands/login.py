"""`rundesk login` — connect an account using an installed provider declaration."""

import argparse
import getpass
import sys
from typing import Callable, Optional

from rundesk.commands import Subcommands
from rundesk.core import oauth, secrets
from rundesk.exits import FAILED, OK
from rundesk.skills import oauth as declarations


def register(sub: Subcommands) -> None:
    login = sub.add_parser("login", help="connect an account through its verified sign-in flow")
    login.add_argument("provider", help="provider ID declared by an installed catalog skill")
    login.add_argument("--profile", default="", help="OAuth app profile (default: default)")
    login.add_argument("--replace-client", action="store_true",
                       help="replace this app client and discard its old account grants")
    login.add_argument("--confirm", action="store_true",
                       help="required with --replace-client after reviewing its impact")


def cmd_login(args: argparse.Namespace, authorizing: Optional[oauth.Authorizing] = None,
              asking: Callable[[str], str] = input,
              asking_secret: Callable[[str], str] = getpass.getpass) -> int:
    try:
        provider = declarations.named(args.provider)
        if args.confirm and not args.replace_client:
            raise oauth.Refused("--confirm is only used with --replace-client")
        if args.replace_client and not args.confirm:
            count = oauth.account_count(provider, args.profile)
            name = oauth.profile_key(args.profile).lower()
            raise oauth.Refused(f"replacing {provider.provider} app profile {name} will discard "
                                f"{count} connected account grant(s); repeat with --confirm")
        if args.replace_client or not oauth.configured(provider, args.profile):
            client_id = asking(f"{provider.display_name} OAuth client ID: ")
            client_secret = (asking_secret(f"{provider.display_name} OAuth client secret: ")
                             if provider.client_secret else None)
            if args.replace_client:
                email = oauth.replace_client(provider, args.profile, client_id, client_secret,
                                             authorizing)
            else:
                oauth.configure(provider, args.profile, client_id, client_secret)
                email = oauth.authorize(provider, args.profile, authorizing=authorizing)
        else:
            email = oauth.authorize(provider, args.profile, authorizing=authorizing)
    except (oauth.Refused, declarations.Refused, secrets.Refused, secrets.Stuck) as trouble:
        print(f"login: FAILED — {trouble}", file=sys.stderr)
        return FAILED
    print(f"Connected {email}")
    return OK
