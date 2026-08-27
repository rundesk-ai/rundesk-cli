"""`rundesk login` — connect an account using an installed provider declaration.

Nothing here knows a provider. The name typed on the command line is looked up among the
declarations installed catalogs shipped, and every endpoint, scope and identity rule comes from
that file. What this module owns is the shape of the conversation: what is asked for, what is
previewed before anything is discarded, and what a refusal says.

**The app client is not asked for twice.** An owner sets it once, under ordinary names, with
`rundesk env set` — usually while they are already in the provider's console with the values on
screen. `login` uses what is there and prompts only for what is genuinely missing, so connecting a
second account, or reconnecting after a revocation, is one command and no typing.
"""

import argparse
import sys
from typing import Callable, Optional

from rundesk.commands import Subcommands, env
from rundesk.core import oauth, secrets
from rundesk.exits import FAILED, OK
from rundesk.skills import oauth as declarations

#: How a value is read when nobody replaced the seam. `Optional[str]`, because "nothing was typed"
#: is an answer a command has to be able to give without a traceback.
Asking = Callable[[str], Optional[str]]


def register(sub: Subcommands) -> None:
    login = sub.add_parser("login", help="connect an account through its verified sign-in flow")
    login.add_argument("provider", metavar="<provider>",
                       help="provider ID declared by an installed catalog skill")
    login.add_argument("--profile", default="",
                       help="a second OAuth app configuration; rarely needed")
    login.add_argument("--replace-client", action="store_true",
                       help="replace this app client and discard its old account grants")
    login.add_argument("--confirm", action="store_true",
                       help="required with --replace-client after reviewing its impact")


def cmd_login(args: argparse.Namespace, authorizing: Optional[oauth.Authorizing] = None,
              asking: Optional[Asking] = None) -> int:
    """Connect one account, or say exactly why nothing was connected."""
    ask = asking or env.typed
    try:
        provider = declarations.named(args.provider)
        if args.confirm and not args.replace_client:
            raise oauth.Refused("--confirm is only used with --replace-client")
        if args.replace_client and not args.confirm:
            raise oauth.Refused(_preview(provider, args.profile))
        if args.replace_client:
            email = oauth.replace_client(provider, args.profile,
                                         *_typed(ask, provider, args.profile, every=True),
                                         authorizing=authorizing)
        else:
            client_id, client_secret = _typed(ask, provider, args.profile)
            oauth.configure(provider, args.profile, client_id, client_secret)
            email = oauth.authorize(provider, args.profile, authorizing=authorizing)
    except (oauth.Refused, declarations.Refused, secrets.Refused, secrets.Stuck) as trouble:
        print(f"login: FAILED — {trouble}", file=sys.stderr)
        return FAILED
    print(f"Connected {email}")
    return OK


def _typed(ask: Asking, provider: oauth.Provider, profile: str, every: bool = False):
    """The client values that have to be asked for, and only those.

    With `every`, both are asked for regardless: that is a deliberate rotation, and reusing half of
    the client being replaced would produce a pair that was never issued together.
    """
    id_name, secret_name = oauth.client_names(provider, profile)
    held = oauth.Client(None, None) if every else oauth.held_client(provider, profile)
    client_id = None if held.identifier else _asked(ask, id_name, "client ID")
    client_secret = None
    if provider.client_secret and not held.secret:
        client_secret = _asked(ask, secret_name, "client secret")
    return client_id, client_secret


def _preview(provider: oauth.Provider, profile: str) -> str:
    """What `--replace-client` would discard, counted from what is really stored.

    Counted rather than described, because "your grants" is not a number somebody can weigh against
    an afternoon of reconnecting integrations. Reading the count also proves the profile exists and
    its declaration still matches before anybody is asked to confirm anything.
    """
    count = oauth.account_count(provider, profile)
    return (f"replacing the {provider.provider} app client will discard {count} connected account "
            "grant(s); nothing else is touched. Repeat with --confirm to be prompted for the new "
            "client, sign in with it, and replace both together")


def _asked(ask: Asking, name: str, called: str) -> str:
    """One value read without echoing it, refusing rather than hanging or raising.

    **Nothing typed is a refusal, not an empty string.** A closed stdin, a `^D`, a pipe that ended
    and a line longer than a value could be all arrive here as `None`; every one of them means the
    command was not given what it needs, and continuing with `""` would store an app client that
    cannot work and report success for it.

    The name is in the prompt because it is the name to `rundesk env set` next time, and somebody
    setting a machine up should learn it here rather than from a document.
    """
    said = ask(f"{name} ({called}): ")
    if said is None or not said.strip():
        raise oauth.Refused(f"no OAuth {called} was given — place it with `rundesk env set {name}` "
                            "and run this again; nothing was changed")
    return said.strip()
