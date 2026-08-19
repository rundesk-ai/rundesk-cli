"""Provider-neutral OAuth2/OIDC mechanics and sealed grant state.

Catalogs declare providers; this module executes no catalog code and knows no vendor names,
endpoints, scopes, capabilities, or identity field spellings. Everything provider-shaped arrives
as a validated `Provider` read from an installed declaration, so adding a provider is publishing a
catalog rather than changing this release.

Three boundaries are worth naming, because each one is the reason a piece of this looks the way it
does:

**A grant is filed under an immutable subject, never under an address.** An email is what a person
types to pick between two connected accounts and nothing more: providers let one be changed, and a
store keyed by it would silently reassign somebody's refresh token the day they renamed their
mailbox.

**Every write is a read-change-write under the install lock**, through `secrets.changed`, and every
one of them re-checks what it expected to find. Consent takes a person the better part of a minute,
and in that minute another terminal can rotate the app client or extend the same account's scopes;
the loser of that race must refuse rather than write a grant derived from a client that is no
longer there.

**A refresh token leaves this module in exactly one direction**: exchanged for a short-lived access
token that crosses an inherited anonymous socket. It is never printed, never logged, never put in
`argv`, and — see `secrets.withheld` — never handed to a provider subprocess. The same is true of
the client secret and of an authorization code. It is *not* true of every value in a flow, and
`browser_authorize` says exactly where that line is: with no browser to open, the authorization URL
is printed for a person to follow, carrying this one flow's short-lived state and PKCE challenge.

**An app client and a person's grant are two different things, kept in two different places.** The
client ID and secret are the *owner's* values, under ordinary names an owner sets with
`rundesk env set` before ever running `login` — see `client_names`. The grants made with that
client are rundesk's, sealed under one name no `env` verb touches. Keeping them together made
`login` the only door a client could come through, which is the wrong shape for a value somebody
pastes out of a cloud console while setting a machine up.
"""

import base64
import hashlib
import hmac
import http.server
import json
import os
import re
import secrets as randomness
import select
import socket
import stat
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from typing import Callable, Dict, List, Mapping, NamedTuple, Optional, Tuple

from rundesk.core import secrets

#: The one sealed name this state is kept under. Named by `secrets` rather than here, because the
#: two modules that must keep it away from an owner — `commands.env` and `providers.environment` —
#: both already import that one and may not import each other.
STATE = secrets.OURS

#: What the app profile nobody named is called. **The ordinary case, and the one to optimise for**:
#: one app client, any number of accounts under it, and nobody typing `--profile` at all.
DEFAULT = "default"

#: How the sealed document is written down, so a later release can change it and still read this.
VERSION = 1

#: The wire version of the private bridge. Bumped only when a reader would misread the old shape.
PROTOCOL = 1

#: The most any single frame — in either direction — may be. A bridge peer is a program on this
#: machine, not the internet, and a length prefix somebody can choose is a length somebody can use
#: to ask for a gigabyte of memory.
MAX_FRAME = 65536

#: How long a peer has to accept an answer, and how long a frame has to arrive. Both bounded, so a
#: peer that stops reading — or never writes — cannot hold a command open for ever.
WRITE_SECONDS = 5.0
READ_SECONDS = 5.0

#: What the callback is bound to, spelled as an address rather than as a name. Providers match a
#: registered redirect as text, and `localhost` is a name whose resolution this product does not
#: control.
LOOPBACK = "127.0.0.1"

#: How long the whole browser round trip has. The clock is on the *flow*, not on one request: a
#: browser makes several requests to a loopback port that are nothing to do with the callback.
CALLBACK_SECONDS = 180

#: What a declaration may never set, because this module sets each of them and a second value would
#: either be ignored or silently replace a security parameter.
RESERVED_AUTH = {
    "client_id", "redirect_uri", "response_type", "scope", "state", "code_challenge",
    "code_challenge_method",
}

#: The most a provider's own error code may be shown as. A code is from a fixed RFC 6749 set; the
#: description beside it is free text from a remote party and is never repeated.
_CODE_SHOWN = 64

#: What an error code may contain before it is shown at all. Anything else is described rather than
#: quoted, so a remote party cannot write terminal escapes into a refusal.
_CODE = re.compile(r"^[A-Za-z0-9_.-]+$")

#: The provider's own word for "the stored grant is gone". RFC 6749 §5.2 — the one token failure
#: that a person fixes by connecting again rather than by retrying.
_REVOKED = "invalid_grant"


class Refused(Exception):
    """A request that cannot safely produce, persist, or release an OAuth grant."""


class Revoked(Refused):
    """The provider no longer honours the stored grant. Connecting again is the whole fix.

    A subclass rather than a message, because it is the one OAuth failure with a different answer:
    everything else here is "retry or look at the declaration", and this one is "the person has to
    consent again". A caller that does not care still catches it as a `Refused`.
    """


@dataclass(frozen=True)
class Provider:
    """One validated, declarative catalog provider."""

    provider: str
    display_name: str
    authorization_endpoint: str
    token_endpoint: str
    identity_endpoint: str
    base_scopes: Tuple[str, ...]
    subject_field: str
    email_field: str
    verified_field: str
    authorization_parameters: Mapping[str, str]
    client_secret: bool
    capabilities: Mapping[str, str]
    fingerprint: str


class Tokens(NamedTuple):
    access: str
    refresh: Optional[str]
    expires_in: int
    scopes: Tuple[str, ...]


class Identity(NamedTuple):
    subject: str
    email: str


class Client(NamedTuple):
    """One app client as it stands right now, with either half possibly not yet placed."""

    identifier: Optional[str]
    secret: Optional[str]


class AsFound(NamedTuple):
    """One app profile as it stood before consent opened, for a write that must re-check it."""

    identifier: Optional[str]
    secret: Optional[str]
    record: Optional[Dict[str, object]]


class Held(NamedTuple):
    """One resolved app client, and where its ID is kept, for a write that has to re-check it."""

    profile: str
    id_name: str
    identifier: str
    secret: Optional[str]
    fingerprint: str


class Access(NamedTuple):
    token: str
    email: str
    subject: str
    expires_at: int


@dataclass(frozen=True)
class Authorization:
    provider: Provider
    client_id: str
    client_secret: Optional[str]
    scopes: Tuple[str, ...]


Authorizing = Callable[[Authorization], Tuple[Tokens, Identity]]
Posting = Callable[[str, Mapping[str, str]], Mapping[str, object]]
Getting = Callable[[str, str], Mapping[str, object]]


def client_names(provider: Provider, profile: str = "") -> Tuple[str, str]:
    """What this provider's app client ID and secret are called, in one profile.

    Derived from the declared provider ID in the spelling a shell variable takes, so `google`
    becomes `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET`. **No provider name is
    written down in rundesk**: the declaration supplies the ID, `secrets.OAUTH_CLIENT` supplies the
    grammar, and this is the one place the two meet. The profile suffix is `secrets.profiled`'s, the
    same one every other value in this product uses.
    """
    key = profile_key(profile)
    stem = provider.provider.replace("-", "_").upper()
    named = "" if key == DEFAULT else key
    return (secrets.profiled(f"{stem}_OAUTH_CLIENT_ID", named),
            secrets.profiled(f"{stem}_OAUTH_CLIENT_SECRET", named))


def held_client(provider: Provider, profile: str = "") -> Client:
    """The app client values this install holds for one profile, each possibly not placed yet."""
    identifier, secret = client_names(provider, profile)
    held = secrets.kept()
    return Client(_placed(held, identifier), _placed(held, secret))


def configured(provider: Provider, profile: str = "") -> bool:
    """Whether one app profile holds a client complete enough to sign in with."""
    client = held_client(provider, profile)
    return bool(client.identifier and (not provider.client_secret or client.secret))


def configure(provider: Provider, profile: str, client_id: Optional[str],
              client_secret: Optional[str]) -> None:
    """Keep app client values somebody has just typed, without ever taking one through argv.

    Only what is passed is written, and only over a name holding nothing: an owner who already set
    one of these has a value this should not silently replace. Rotating deliberately is
    `--replace-client`, which also says what it will discard.
    """
    identifier, secret = client_names(provider, profile)
    said = {}
    if client_id is not None:
        said[identifier] = _client_value(client_id, "OAuth client ID")
    if client_secret is not None:
        said[secret] = _client_value(client_secret, "OAuth client secret")

    def changing(before: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
        for name in said:
            if before.get(name):
                raise Refused(f"{name} is already set; change it with `rundesk env set {name}`, or "
                              "rotate the whole client with --replace-client")
        return said

    if said:
        secrets.changed(tuple(said), changing)


def account_count(provider: Provider, profile: str = "") -> int:
    """How many verified accounts one app profile holds, for a preview that must not guess."""
    return len(_accounts(provider, profile_key(profile)))


def replace_client(provider: Provider, profile: str, client_id: str,
                   client_secret: Optional[str], authorizing: Optional[Authorizing] = None) -> str:
    """Validate a replacement client first, then atomically replace only its app profile.

    The order is the guarantee. Consent runs against the *new* client before anything is written,
    so a replacement that cannot produce a reusable grant leaves the old client and every grant
    under it exactly as they were — a rotation that half-happened is an integration that has
    stopped working with nothing left to put back.

    The client and its grants live under different names, so both go in one `secrets.changed`
    transaction. Written separately, a failure between them leaves stored refresh tokens belonging
    to a client that is gone.

    **What was there before consent opened is read first and re-checked inside that transaction.**
    Consent is slow, and everything this replaces is discarded rather than merged, so a blind write
    is the one shape where a concurrent change is lost in silence: two confirmed replacements would
    both report success and one client and its grant would simply be gone, and a grant connected in
    another terminal during the browser step would be thrown away by a command that never saw it.
    The loser refuses and writes nothing.
    """
    identifier = _client_value(client_id, "replacement OAuth client ID")
    secret = (_client_value(client_secret, "replacement OAuth client secret")
              if provider.client_secret else None)
    key = profile_key(profile)
    id_name, secret_name = client_names(provider, profile)
    expected = _as_found(provider, key, id_name, secret_name)
    tokens, identity = _consented(provider, authorizing, Authorization(
        provider, identifier, secret, provider.base_scopes))
    if not tokens.refresh or not set(provider.base_scopes).issubset(tokens.scopes):
        raise Refused("the replacement client did not return a complete reusable identity grant")
    account = _account(identity, tokens.refresh, tokens.scopes, _fingerprint(identifier))

    def replacing(before: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
        if (before.get(id_name), before.get(secret_name)) != (expected.identifier, expected.secret):
            raise Refused("this OAuth app client changed while the replacement was being "
                          "authorized; nothing was replaced — check what is stored and run "
                          "`--replace-client --confirm` again")
        if _record_in(before.get(STATE), provider, key) != expected.record:
            raise Refused("an account was connected or changed under this app client while the "
                          "replacement was being authorized; nothing was replaced — review the "
                          "connected accounts and run `--replace-client --confirm` again")
        held = _document_from(before.get(STATE))
        providers = dict(held["providers"])
        theirs = _mapping_at(providers, provider.provider)
        applications = _mapping_at(theirs, "applications")
        applications[key] = {"descriptor_fingerprint": provider.fingerprint,
                             "accounts": {identity.subject: account}}
        theirs["applications"], providers[provider.provider] = applications, theirs
        return {STATE: _encoded({"version": VERSION, "providers": providers}),
                id_name: identifier, secret_name: secret}

    secrets.changed((STATE, id_name, secret_name), replacing)
    return identity.email


def _as_found(provider: Provider, key: str, id_name: str, secret_name: str) -> AsFound:
    """What one app profile holds right now: both client values and its stored record.

    Read once, before anybody is sent to a browser, so the transaction afterwards has something
    exact to compare against rather than a description of it. An unreadable value refuses here
    rather than after consent, which is the difference between wasting a person's time and
    wasting it *and* leaving them unsure whether anything changed.
    """
    held = secrets.kept()
    state = held.get(STATE)
    if state is not None and state.trouble:
        raise Refused("the sealed OAuth state cannot be read")
    return AsFound(_placed(held, id_name), _placed(held, secret_name),
                   _record_in(state.value if state is not None else None, provider, key))


def _record_in(raw: Optional[str], provider: Provider, key: str) -> Optional[Dict[str, object]]:
    """One app profile's stored record exactly as the document holds it, or `None` when absent.

    Deliberately not `_application`: this compares what is on disk with what was on disk, so it
    must not apply the descriptor check that reader does — a replacement is how somebody recovers
    from drift, and refusing it for being drifted would close the exit.

    Both sides of that comparison come through here, so what `None` is spelled as does not matter
    on its own; what matters is that one function decides it for both. A record this returns is the
    stored object, so a profile holding a client with no accounts is a populated dict and stays
    distinct from one that was never configured.
    """
    theirs = _mapping_at(dict(_document_from(raw)["providers"]), provider.provider)
    record = _mapping_at(theirs, "applications").get(key)
    return record if isinstance(record, dict) else None


def emails(provider: Provider, profile: str = "") -> List[str]:
    """Every connected address under one app profile, which is all a chooser ever needs."""
    held = _client(provider, profile)
    return sorted(_email_of(one) for one in _accounts(provider, held.profile).values())


def authorize(provider: Provider, profile: str = "",
              authorizing: Optional[Authorizing] = None) -> str:
    """Authorize and intentionally replace only the returned immutable account."""
    held = _client(provider, profile)
    tokens, identity = _consented(provider, authorizing, Authorization(
        provider, held.identifier, held.secret, provider.base_scopes))
    if not tokens.refresh:
        raise Refused(f"{provider.display_name} returned no refresh token; no account was changed")
    if not set(provider.base_scopes).issubset(tokens.scopes):
        raise Refused(f"{provider.display_name} did not grant every identity scope")
    _replace_account(provider, held, identity, tokens.refresh, tokens.scopes)
    return identity.email


def access(provider: Provider, capability: str, email: Optional[str], profile: str = "",
           authorizing: Optional[Authorizing] = None,
           posting: Optional[Posting] = None) -> Access:
    """Release a short-lived token, extending one account without stale overwrites."""
    scope = provider.capabilities.get(capability)
    if scope is None:
        raise Refused(f"{provider.provider} declares no OAuth capability {capability!r}")
    held = _client(provider, profile)
    account = _selected(provider, email, held.profile)
    _from_this_client(provider, account, held.fingerprint)
    if scope not in _scopes_of(account):
        # **Escalation is one capability wide.** What is asked for is exactly what this account
        # already has plus this one declared scope, so a second integration's consent never quietly
        # widens the first one's.
        wanted = tuple(dict.fromkeys((*_scopes_of(account), scope)))
        account = _extended(provider, held, account, wanted, authorizing)
    fields = {
        "client_id": held.identifier, "refresh_token": _refresh_of(account),
        "grant_type": "refresh_token",
    }
    if provider.client_secret and held.secret:
        fields["client_secret"] = held.secret
    response = (posting or post_json)(provider.token_endpoint, fields)
    _no_error(provider, response)
    token, expires = response.get("access_token"), _seconds(response.get("expires_in"))
    if not isinstance(token, str) or not token or expires is None:
        raise Refused(f"{provider.display_name} did not return a usable access token")
    _rotated(provider, held, account, response.get("refresh_token"))
    return Access(token, _email_of(account), _subject_of(account), int(time.time()) + expires)


def browser_authorize(request: Authorization, posting: Optional[Posting] = None,
                      getting: Optional[Getting] = None) -> Tuple[Tokens, Identity]:
    """Run a loopback Desktop PKCE flow, then verify identity through the declared endpoint."""
    verifier = _url_random(64)
    challenge = _url_b64(hashlib.sha256(verifier.encode("ascii")).digest())
    state, callback_path = _url_random(32), "/" + _url_random(24)
    server = _callback_server(callback_path, state)
    # **`127.0.0.1`, an ephemeral port, and a random path, and each of the three is load-bearing.**
    # The literal address rather than `localhost`, because that name can resolve to `::1` or to
    # whatever a `hosts` file says and the provider is matching the string. Port 0, because a fixed
    # one is a port something else on the machine may already hold and a redirect somebody else can
    # register. A random path, because every other program on this machine can also reach a
    # loopback port, and the path plus the state is what makes a callback this flow's own.
    redirect = f"http://{LOOPBACK}:{server.server_port}{callback_path}"
    query = {
        "client_id": request.client_id, "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(request.scopes), "state": state, "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    query.update(request.provider.authorization_parameters)
    # Safe to append rather than merge because a declaration's endpoints are refused if they carry
    # a query or a fragment at all: there is nothing here to collide with.
    url = f"{request.provider.authorization_endpoint}?{urllib.parse.urlencode(query)}"
    # **Said out loud, every time.** The port is ephemeral and the path is random, so the one thing
    # somebody debugging a refused redirect cannot guess is the address rundesk is listening on.
    # This line is the address and nothing else: no client secret, no state, no PKCE challenge.
    print(f"Listening for the sign-in callback on {redirect}")
    if not webbrowser.open(url, new=1, autoraise=True):
        # **The fallback line is a different claim, and it has to be the honest one.** When no
        # browser can be opened, the person has to make this request themselves, so the whole
        # authorization URL is printed — and that URL *does* carry this flow's short-lived
        # authorization mechanics: the client ID, the redirect, the state, and the PKCE challenge.
        # It is not a leak, it is the request; the state and challenge are meaningful only to the
        # loopback server standing behind them, for one flow, for at most `CALLBACK_SECONDS`.
        #
        # What is never in it, and what the boundary actually is: no client secret, no
        # authorization code, no refresh token, no access token. The secret is a form field of a
        # POST this module makes, and the code comes *back* over the loopback socket; neither has
        # any path to a terminal. Printing it is what keeps a manual browser usable — a provider's
        # retired copy-and-paste code flow is not supported and is not what this is.
        print("Open this address in a browser to continue:")
        print(url)
    try:
        result = _awaited(server, time.monotonic() + CALLBACK_SECONDS)
    finally:
        server.server_close()
    if result is None:
        raise Refused("OAuth login timed out; no account was changed")
    if result.get("error"):
        raise Refused("OAuth login was declined; no account was changed")
    code = result.get("code")
    if not code:
        raise Refused("the provider returned no authorization code")
    fields = {
        "client_id": request.client_id, "code": code, "code_verifier": verifier,
        "redirect_uri": redirect, "grant_type": "authorization_code",
    }
    if request.provider.client_secret and request.client_secret:
        fields["client_secret"] = request.client_secret
    answered = (posting or post_json)(request.provider.token_endpoint, fields)
    _no_error(request.provider, answered)
    tokens = _tokens(request.provider, answered)
    who = (getting or get_json)(request.provider.identity_endpoint, tokens.access)
    _no_error(request.provider, who)
    identity = Identity(_field(who, request.provider.subject_field),
                        _field(who, request.provider.email_field))
    if who.get(request.provider.verified_field) is not True:
        raise Refused(f"{request.provider.display_name} did not verify this account's email")
    _valid_identity(request.provider, identity)
    return tokens, identity


def post_json(url: str, fields: Mapping[str, str]) -> Mapping[str, object]:
    request = urllib.request.Request(url, urllib.parse.urlencode(fields).encode("ascii"),
                                     method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    return _opened(request)


def get_json(url: str, token: str) -> Mapping[str, object]:
    request = urllib.request.Request(url, method="GET")
    request.add_header("Authorization", f"Bearer {token}")
    return _opened(request)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise Refused("an OAuth credential request unexpectedly redirected")


def _opened(request: urllib.request.Request) -> Mapping[str, object]:
    """One JSON answer, including the JSON body of a refusal.

    **A 4xx with a body is an answer, not a transport failure.** RFC 6749 §5.2 says a revoked
    refresh token comes back as `400` with `{"error": "invalid_grant"}`, and a client that treats
    every non-200 the same way tells somebody to check their network when what they need is to
    connect again.
    """
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=30) as response:
            raw = response.read(MAX_FRAME + 1)
    except Refused:
        raise
    except urllib.error.HTTPError as answered:
        raw = _refusal_body(answered)
        if raw is None:
            raise Refused("the OAuth credential request could not be completed") from answered
    except (OSError, urllib.error.URLError) as trouble:
        raise Refused("the OAuth credential request could not be completed") from trouble
    if len(raw) > MAX_FRAME:
        raise Refused("the OAuth endpoint returned an oversized response")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as trouble:
        raise Refused("the OAuth endpoint returned malformed JSON") from trouble
    if not isinstance(value, dict):
        raise Refused("the OAuth endpoint returned malformed JSON")
    return value


def _refusal_body(answered: urllib.error.HTTPError) -> Optional[bytes]:
    """The bounded body of a refusal, or `None` when there is nothing to read it as."""
    try:
        raw = answered.read(MAX_FRAME + 1)
    except OSError:
        return None
    finally:
        answered.close()
    return raw or None


def _no_error(provider: Provider, response: Mapping[str, object]) -> None:
    """Turn a provider's own refusal into this module's, keeping revocation separate.

    The code is repeated only when it is one of the plain identifiers the specification defines;
    anything else is described rather than quoted, because what comes back is remote text and a
    refusal is printed to a terminal. `error_description` is never shown at all.
    """
    said = response.get("error")
    if said is None:
        return
    code = str(said)[:_CODE_SHOWN]
    shown = code if _CODE.match(code) else "an unrecognised error"
    if code == _REVOKED:
        raise Revoked(f"{provider.display_name} no longer honours this connection; reconnect with "
                      f"`rundesk login {provider.provider}`")
    raise Refused(f"{provider.display_name} refused the OAuth request ({shown})")


def write_frame(fd: int, payload: Mapping[str, object], timeout: float = WRITE_SECONDS) -> None:
    _validated_socket(fd)
    body = json.dumps({"version": PROTOCOL, **payload}, separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_FRAME:
        raise Refused("the OAuth protocol response is too large")
    frame, deadline, blocking = struct.pack(">I", len(body)) + body, time.monotonic() + timeout, \
        os.get_blocking(fd)
    written = 0
    try:
        os.set_blocking(fd, False)
        while written < len(frame):
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([], [fd], [], remaining)[1]:
                raise Refused("the response socket did not accept the answer before its deadline")
            try:
                sent = os.write(fd, frame[written:])
            except BlockingIOError:
                continue
            if sent <= 0:
                raise Refused("the response socket closed before the answer was written")
            written += sent
    finally:
        os.set_blocking(fd, blocking)


def read_frame(fd: int, timeout: float = READ_SECONDS) -> Mapping[str, object]:
    """One bounded answer, or a refusal. **The read has a deadline of its own.**

    Without one, a peer that connects and then says nothing holds the reader for ever, and the
    caller here is the integration process an owner is waiting on. The deadline covers the whole
    frame rather than one `read`, so a peer cannot extend it a byte at a time.
    """
    _validated_socket(fd)
    deadline = time.monotonic() + timeout
    size = struct.unpack(">I", _read_exact(fd, 4, deadline))[0]
    if size > MAX_FRAME:
        raise Refused("the OAuth protocol frame is too large")
    try:
        payload = json.loads(_read_exact(fd, size, deadline).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as trouble:
        raise Refused("the OAuth protocol frame is malformed") from trouble
    if not isinstance(payload, dict) or payload.get("version") != PROTOCOL:
        raise Refused("the OAuth protocol version is not supported")
    return payload


def profile_key(profile: str) -> str:
    if not profile:
        return "default"
    named = profile.strip().upper()
    if secrets.name_trouble(named) or secrets.PROFILED_BY in named:
        raise Refused(f"{profile!r} is not a valid OAuth app profile name")
    return named


def _consented(provider: Provider, authorizing: Optional[Authorizing],
               request: Authorization) -> Tuple[Tokens, Identity]:
    """One consent round trip, with the identity it produced already checked."""
    tokens, identity = (authorizing or browser_authorize)(request)
    _valid_identity(provider, identity)
    return tokens, identity


def _extended(provider: Provider, held: Held, account: Mapping[str, object],
              wanted: Tuple[str, ...], authorizing: Optional[Authorizing]) -> Dict[str, object]:
    """Reopen consent for a declared capability scope, for this same account and no other."""
    tokens, identity = _consented(provider, authorizing, Authorization(
        provider, held.identifier, held.secret, wanted))
    if identity.subject != _subject_of(account) \
            or identity.email.casefold() != _email_of(account).casefold():
        raise Refused(f"{provider.display_name} returned a different account; no grant changed")
    if not tokens.refresh or not set(wanted).issubset(tokens.scopes):
        raise Refused(f"{provider.display_name} did not return the requested reusable grant")
    return _replace_account(provider, held, identity, tokens.refresh, tokens.scopes,
                            expected=account)


def _client(provider: Provider, profile: str) -> Held:
    """The app client for one profile, refused by name when it is not all there.

    The refusal names the exact values to place, because that is the whole of what somebody has to
    do next and it is a `rundesk env set` they can copy.
    """
    key = profile_key(profile)
    id_name, secret_name = client_names(provider, profile)
    client = held_client(provider, profile)
    missing = [id_name] if not client.identifier else []
    if provider.client_secret and not client.secret:
        missing.append(secret_name)
    if missing:
        raise Refused(f"no OAuth app client is configured for {provider.display_name}: set "
                      + " and ".join(f"`rundesk env set {name}`" for name in missing)
                      + f", then run `rundesk login {provider.provider}`")
    return Held(key, id_name, str(client.identifier),
                client.secret if provider.client_secret else None,
                _fingerprint(str(client.identifier)))


def _placed(held: Mapping[str, secrets.Held], name: str) -> Optional[str]:
    """One kept value, refusing rather than reporting a name this install can no longer open."""
    one = held.get(name)
    if one is None:
        return None
    if one.trouble:
        raise Refused(f"{name} {one.trouble}")
    return one.value


def _application(provider: Provider, key: str) -> Optional[Dict[str, object]]:
    """What is stored for one app profile, or `None` when nothing has been connected under it.

    Absent is not the same as unreadable, so every level is required to be an object it could have
    written. Read leniently, a provider entry corrupted to a string reports "no accounts
    connected", which is the one answer that sends somebody to connect a second one over the top.
    """
    theirs = _mapping_at(dict(_document()["providers"]), provider.provider)
    app = _mapping_at(_mapping_at(theirs, "applications"), key)
    if not app:
        return None
    if app.get("descriptor_fingerprint") != provider.fingerprint:
        raise Refused(f"the installed declaration for {provider.display_name} changed; "
                      "review it and reconnect this app profile")
    return app


def _accounts(provider: Provider, key: str) -> Dict[str, Dict[str, object]]:
    app = _application(provider, key) or {}
    return {subject: account for subject, account in _mapping_at(app, "accounts").items()
            if isinstance(account, dict)}


def _selected(provider: Provider, email: Optional[str], key: str) -> Dict[str, object]:
    """The one account meant, saying which of "none", "not that one" and "which one" it was."""
    accounts = list(_accounts(provider, key).values())
    if not accounts:
        raise Refused(f"no {provider.display_name} account is connected; connect one with "
                      f"`rundesk login {provider.provider}`")
    if email:
        accounts = [one for one in accounts if _email_of(one).casefold() == email.casefold()]
        if not accounts:
            raise Refused(f"no connected {provider.display_name} account uses that address")
    if len(accounts) != 1:
        available = ", ".join(sorted(_email_of(one) for one in accounts))
        raise Refused(f"more than one account is connected; choose --email from: {available}")
    return accounts[0]


def _from_this_client(provider: Provider, account: Mapping[str, object],
                      fingerprint: str) -> None:
    """Refuse a grant that was not issued by the client this app profile now holds.

    A refresh token is only meaningful to the client it was issued to, so a grant left behind by a
    rotation is not a credential — it is a confusing 400 from the provider at the moment somebody
    needs the integration to work. Said here instead, with the command that fixes it.
    """
    if account.get("client_fingerprint") != fingerprint:
        raise Refused(f"this {provider.display_name} account was connected with a different app "
                      f"client; reconnect it with `rundesk login {provider.provider}`")


def _replace_account(provider: Provider, held: Held, identity: Identity, refresh: str,
                     scopes: Tuple[str, ...],
                     expected: Optional[Mapping[str, object]] = None) -> Dict[str, object]:
    account = _account(identity, refresh, scopes, held.fingerprint)

    def replacing(before: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
        document = _document_from(before.get(STATE))
        providers = dict(document["providers"])
        theirs = _mapping_at(providers, provider.provider)
        applications = _mapping_at(theirs, "applications")
        app = _mapping_at(applications, held.profile)
        _still_ours(provider, app, before.get(held.id_name), held.fingerprint)
        accounts = _mapping_at(app, "accounts")
        if expected is not None and accounts.get(identity.subject) != expected:
            raise Refused("this account grant changed while consent was open; retry the integration "
                          "request so no newer grant is overwritten")
        accounts[identity.subject] = account
        app["accounts"], app["descriptor_fingerprint"] = accounts, provider.fingerprint
        applications[held.profile] = app
        theirs["applications"], providers[provider.provider] = applications, theirs
        return {STATE: _encoded({"version": VERSION, "providers": providers})}

    secrets.changed((STATE, held.id_name), replacing)
    return account


def _rotated(provider: Provider, held: Held, account: Mapping[str, object], said: object) -> None:
    """Keep a refresh token the provider replaced during an ordinary refresh.

    **A provider that rotates on every refresh hands back the only token that will work next
    time**, and dropping it turns one working refresh into a connection that is revoked from the
    next one onward. Written under the same compare-and-set as every other grant change: if
    somebody else has already replaced this account, theirs is the newer grant and this one is
    simply not applied — there is nothing to report, because the access token in hand is still the
    one that was asked for.
    """
    if not isinstance(said, str) or not said or said == _refresh_of(account):
        return
    try:
        _replace_account(provider, held, Identity(_subject_of(account), _email_of(account)),
                         said, tuple(_scopes_of(account)), expected=account)
    except Refused:
        return


def _still_ours(provider: Provider, app: Mapping[str, object], identifier: Optional[str],
                fingerprint: str) -> None:
    """Refuse to file a grant under a client or a declaration that changed while consent was open.

    Both are here rather than only on the read path because consent is slow: the client and the
    declaration are read before a person is sent to a browser, and another terminal can change
    either in the minute that takes. Written without this, the loser of that race stores a refresh
    token the current client cannot use, and nothing says so until the integration fails.

    A profile with no grant yet has no declaration pinned to it, and that absence is not drift.
    """
    if app.get("descriptor_fingerprint") not in (None, provider.fingerprint):
        raise Refused("the OAuth provider declaration changed while authorization was open")
    if not identifier or _fingerprint(identifier) != fingerprint:
        raise Refused("this OAuth app client was replaced while authorization was open; no grant "
                      "was written — connect again")


def _account(identity: Identity, refresh: str, scopes: Tuple[str, ...],
             fingerprint: str) -> Dict[str, object]:
    """One stored grant, in the one shape every writer here produces."""
    return {"subject": identity.subject, "email": identity.email, "refresh_token": refresh,
            "scopes": sorted(set(scopes)), "client_fingerprint": fingerprint}


def _fingerprint(client_id: str) -> str:
    return hashlib.sha256(client_id.encode("utf-8")).hexdigest()


def _document() -> Dict[str, object]:
    kept = secrets.kept().get(STATE)
    if kept and kept.trouble:
        raise Refused("the sealed OAuth state cannot be read")
    return _document_from(kept.value if kept else None)


def _document_from(raw: Optional[str]) -> Dict[str, object]:
    if raw is None:
        return {"version": VERSION, "providers": {}}
    try:
        held = json.loads(raw)
    except json.JSONDecodeError as trouble:
        raise Refused("the sealed OAuth state cannot be read") from trouble
    if not isinstance(held, dict) or held.get("version") != VERSION \
            or not isinstance(held.get("providers"), dict):
        raise Refused("the sealed OAuth state uses an unsupported version")
    return held


def _mapping_at(held: Mapping[str, object], name: str) -> Dict[str, object]:
    """One nested object, copied, refusing a stored value that is not one.

    Every writer walks the same four levels of the document, and each level is data that could have
    been edited on disk. Reached with `dict(...)` alone, a string where an object belongs raises a
    `ValueError` out of a command as a traceback; reached through here it is the same refusal as
    any other unreadable state.
    """
    value = held.get(name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise Refused("the sealed OAuth state cannot be read")
    return dict(value)


def _stored_text(held: Mapping[str, object], name: str) -> str:
    value = held.get(name)
    if not isinstance(value, str) or not value:
        raise Refused("the sealed OAuth state cannot be read")
    return value


def _email_of(account: Mapping[str, object]) -> str:
    return _stored_text(account, "email")


def _subject_of(account: Mapping[str, object]) -> str:
    return _stored_text(account, "subject")


def _refresh_of(account: Mapping[str, object]) -> str:
    return _stored_text(account, "refresh_token")


def _scopes_of(account: Mapping[str, object]) -> Tuple[str, ...]:
    held = account.get("scopes")
    if not isinstance(held, list) or any(not isinstance(one, str) for one in held):
        raise Refused("the sealed OAuth state cannot be read")
    return tuple(held)


def _client_value(said: Optional[str], called: str) -> str:
    if not said or not said.strip():
        raise Refused(f"the {called} cannot be empty")
    return said.strip()


def _seconds(said: object) -> Optional[int]:
    """A positive lifetime in seconds, or `None` when what came back is not one.

    Two exactness problems, both measured against real providers. `True` **is** an `int` in Python,
    so a plain `isinstance` check accepts `expires_in: true` and turns it into a token that expires
    one second from now. And several providers send the number as a string, which the specification
    allows a reader to accept — refusing those would refuse a working provider outright.
    """
    if isinstance(said, bool):
        return None
    if isinstance(said, int):
        return said if said > 0 else None
    if isinstance(said, str) and said.strip().isdigit() and len(said.strip()) <= 12:
        value = int(said.strip())
        return value if value > 0 else None
    return None


def _tokens(provider: Provider, raw: Mapping[str, object]) -> Tokens:
    access, refresh = raw.get("access_token"), raw.get("refresh_token")
    expires, scope = _seconds(raw.get("expires_in")), raw.get("scope")
    if not isinstance(access, str) or not access or expires is None:
        raise Refused(f"{provider.display_name} returned a malformed token response")
    if refresh is not None and (not isinstance(refresh, str) or not refresh):
        raise Refused(f"{provider.display_name} returned a malformed refresh token")
    return Tokens(access, refresh, expires, tuple(scope.split()) if isinstance(scope, str) else ())


def _field(who: Mapping[str, object], name: str) -> str:
    """One declared identity field, only when the provider sent it as text."""
    value = who.get(name)
    return value if isinstance(value, str) else ""


def _valid_identity(provider: Provider, identity: Identity) -> None:
    if not identity.subject or not identity.email or "@" not in identity.email:
        raise Refused(f"{provider.display_name} returned no usable verified identity")


def _encoded(value: Mapping[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _awaited(server, deadline: float) -> Optional[Dict[str, str]]:
    """Keep serving until the callback itself arrives, or the whole flow runs out of time.

    **A browser makes requests to a loopback port that are not the callback**: a favicon, a
    speculative preconnect, a probe from something else on the machine. Answering exactly one
    request meant the first of those became the answer, and the person was told their login had
    been declined while the real redirect was still on its way. Only the exact random path with the
    exact state ends the wait; everything else is answered and ignored.
    """
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        server.timeout = remaining
        server.handle_request()
        if server.result is not None:
            return server.result


def _callback_server(path: str, state: str):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.path != path:
                # Not the callback. Answered so the browser is not left hanging, and deliberately
                # not recorded: the flow is still waiting for the redirect.
                self._answer(404, "Not found", "This address is not part of an authorization.")
                return
            try:
                query = urllib.parse.parse_qs(parsed.query, strict_parsing=True)
            except ValueError:
                query = {}
            flat = {key: values[0] for key, values in query.items() if len(values) == 1}
            # OAuth and OpenID Connect providers may append response metadata that Rundesk does
            # not consume. Google, for example, returns `iss`, `scope`, `authuser` and `prompt`
            # beside the authorization code. The callback's authority comes from its random path
            # and exact state, not from rejecting provider-owned metadata. Keep every parameter
            # unambiguous, require exactly one terminal result, then retain only the values this
            # flow actually uses.
            terminal = int("code" in flat) + int("error" in flat)
            valid = (not parsed.fragment and len(flat) == len(query) and terminal == 1
                     and hmac.compare_digest(flat.get("state", ""), state))
            if not valid:
                # The path is right and the rest is not, which is a forgery or a stale tab rather
                # than this flow's answer. Refused to the sender and *not* recorded, so somebody
                # else's request cannot end the login somebody is in the middle of.
                self._answer(400, "Authorization rejected",
                             "This callback was not accepted. Return to Rundesk and try again.")
                return
            kept = {key: flat[key] for key in ("state", "code", "error", "error_description")
                    if key in flat}
            self.server.result = kept  # type: ignore[attr-defined]
            self._answer(200, "Authorization received",
                         "Return to Rundesk while it verifies the account. This tab will try to "
                         "close in <span id=count>3</span> seconds; if the browser blocks it, you "
                         "may close this tab manually.",
                         "<script>let n=3;setInterval(()=>{n-=1;document.getElementById('count')"
                         ".textContent=n;if(n<=0)window.close()},1000)</script>")

        def _answer(self, status: int, title: str, said: str, extra: str = "") -> None:
            body = (f"<!doctype html><meta charset=utf-8><title>{title}</title>"
                    f"<h1>{title}</h1><p>{said}</p>{extra}")
            self.send_response(status)
            for name, value in (("Content-Type", "text/html; charset=utf-8"),
                                ("Cache-Control", "no-store"), ("Pragma", "no-cache"),
                                ("Referrer-Policy", "no-referrer"),
                                ("X-Content-Type-Options", "nosniff"),
                                ("Content-Security-Policy",
                                 "default-src 'none'; script-src 'unsafe-inline'")):
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, _format: str, *_args: object) -> None:
            return

    # Port 0: the operating system picks a free ephemeral port for this one flow.
    server = http.server.HTTPServer((LOOPBACK, 0), Handler)
    server.result = None
    return server


def _url_random(size: int) -> str:
    return _url_b64(randomness.token_bytes(size))


def _url_b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _read_exact(fd: int, wanted: int, deadline: float) -> bytes:
    held = bytearray()
    while len(held) < wanted:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
            raise Refused("the OAuth protocol frame did not arrive before its deadline")
        part = os.read(fd, wanted - len(held))
        if not part:
            raise Refused("the OAuth protocol frame ended early")
        held.extend(part)
    return bytes(held)


def _validated_socket(fd: int) -> None:
    if fd in (0, 1, 2) or fd < 0:
        raise Refused("the response FD may not be stdin, stdout, or stderr")
    try:
        kind, held = os.fstat(fd).st_mode, socket.socket(fileno=os.dup(fd))
    except OSError as trouble:
        raise Refused("the response FD is not an open socket") from trouble
    try:
        if not stat.S_ISSOCK(kind) or held.family != socket.AF_UNIX \
                or held.getsockname() not in ("", b"") or held.getpeername() not in ("", b""):
            raise Refused("the response FD must be a connected anonymous local socket")
    except OSError as trouble:
        raise Refused("the response FD must be a connected anonymous local socket") from trouble
    finally:
        held.close()
