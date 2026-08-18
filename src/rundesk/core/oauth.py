"""Provider-neutral OAuth2/OIDC mechanics and sealed grant state.

Catalogs declare providers; this module executes no catalog code and knows no vendor names,
endpoints, scopes, capabilities, or identity field spellings.
"""

import base64
import hashlib
import hmac
import http.server
import json
import os
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

STATE = "RUNDESK_OAUTH_STATE"
VERSION = 1
PROTOCOL = 1
MAX_FRAME = 65536
WRITE_SECONDS = 5.0
CALLBACK_SECONDS = 180
RESERVED_AUTH = {
    "client_id", "redirect_uri", "response_type", "scope", "state", "code_challenge",
    "code_challenge_method",
}


class Refused(Exception):
    """A request that cannot safely produce, persist, or release an OAuth grant."""


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


def configured(provider: Provider, profile: str = "") -> bool:
    """Whether one app profile holds a client usable with this exact descriptor."""
    key = profile_key(profile)
    app = _application(provider, key)
    return bool(app and app.get("client_id") and
                (not provider.client_secret or app.get("client_secret")))


def configure(provider: Provider, profile: str, client_id: str,
              client_secret: Optional[str]) -> None:
    """Persist one app client without ever taking either value through argv."""
    if not client_id.strip():
        raise Refused("the OAuth client ID cannot be empty")
    if provider.client_secret and not client_secret:
        raise Refused("this provider requires an OAuth client secret")
    key = profile_key(profile)

    def changing(raw: Optional[str]) -> str:
        held = _document_from(raw)
        providers = dict(held["providers"])
        theirs = dict(providers.get(provider.provider) or {})
        applications = dict(theirs.get("applications") or {})
        previous = dict(applications.get(key) or {})
        if previous:
            raise Refused("an OAuth app client is already configured; use --replace-client to "
                          "rotate it deliberately")
        applications[key] = {
            "client_id": client_id.strip(), "client_secret": client_secret,
            "descriptor_fingerprint": provider.fingerprint,
            "accounts": {},
        }
        theirs["applications"] = applications
        providers[provider.provider] = theirs
        return _encoded({"version": VERSION, "providers": providers})

    secrets.changed(STATE, changing)


def account_count(provider: Provider, profile: str = "") -> int:
    return len(_accounts(provider, profile_key(profile)))


def replace_client(provider: Provider, profile: str, client_id: str,
                   client_secret: Optional[str], authorizing: Optional[Authorizing] = None) -> str:
    """Validate a replacement client first, then atomically replace only its app profile."""
    if not client_id.strip() or (provider.client_secret and not client_secret):
        raise Refused("the replacement OAuth app client is incomplete")
    key = profile_key(profile)
    tokens, identity = (authorizing or browser_authorize)(Authorization(
        provider, client_id.strip(), client_secret, provider.base_scopes))
    _valid_identity(provider, identity)
    if not tokens.refresh or not set(provider.base_scopes).issubset(tokens.scopes):
        raise Refused("the replacement client did not return a complete reusable identity grant")
    fingerprint = hashlib.sha256(client_id.strip().encode("utf-8")).hexdigest()
    account = {"subject": identity.subject, "email": identity.email,
               "refresh_token": tokens.refresh, "scopes": sorted(set(tokens.scopes)),
               "client_fingerprint": fingerprint}

    def replacing(raw: Optional[str]) -> str:
        held = _document_from(raw)
        providers = dict(held["providers"])
        theirs = dict(providers.get(provider.provider) or {})
        applications = dict(theirs.get("applications") or {})
        applications[key] = {"client_id": client_id.strip(), "client_secret": client_secret,
                             "descriptor_fingerprint": provider.fingerprint,
                             "accounts": {identity.subject: account}}
        theirs["applications"], providers[provider.provider] = applications, theirs
        return _encoded({"version": VERSION, "providers": providers})

    secrets.changed(STATE, replacing)
    return identity.email


def emails(provider: Provider, profile: str = "") -> List[str]:
    key, _, _, _ = _client(provider, profile)
    return sorted(str(one["email"]) for one in _accounts(provider, key).values())


def authorize(provider: Provider, profile: str = "",
              authorizing: Optional[Authorizing] = None) -> str:
    """Authorize and intentionally replace only the returned immutable account."""
    key, client_id, client_secret, fingerprint = _client(provider, profile)
    tokens, identity = (authorizing or browser_authorize)(Authorization(
        provider, client_id, client_secret, provider.base_scopes))
    _valid_identity(provider, identity)
    if not tokens.refresh:
        raise Refused(f"{provider.display_name} returned no refresh token; no account was changed")
    if not set(provider.base_scopes).issubset(tokens.scopes):
        raise Refused(f"{provider.display_name} did not grant every identity scope")
    _replace_account(provider, key, identity, tokens, fingerprint)
    return identity.email


def access(provider: Provider, capability: str, email: Optional[str], profile: str = "",
           authorizing: Optional[Authorizing] = None,
           posting: Optional[Posting] = None) -> Access:
    """Release a short-lived token, extending one account without stale overwrites."""
    scope = provider.capabilities.get(capability)
    if scope is None:
        raise Refused(f"{provider.provider} declares no OAuth capability {capability!r}")
    key, client_id, client_secret, fingerprint = _client(provider, profile)
    account = _selected(provider, email, key)
    wanted = tuple(dict.fromkeys((*tuple(account.get("scopes") or ()), scope)))
    if scope not in account.get("scopes", ()):
        tokens, identity = (authorizing or browser_authorize)(Authorization(
            provider, client_id, client_secret, wanted))
        _valid_identity(provider, identity)
        if identity.subject != account["subject"] \
                or identity.email.casefold() != str(account["email"]).casefold():
            raise Refused(f"{provider.display_name} returned a different account; no grant changed")
        if not tokens.refresh or not set(wanted).issubset(tokens.scopes):
            raise Refused(f"{provider.display_name} did not return the requested reusable grant")
        account = _replace_account(provider, key, identity, tokens, fingerprint, expected=account)
    fields = {
        "client_id": client_id, "refresh_token": str(account["refresh_token"]),
        "grant_type": "refresh_token",
    }
    if provider.client_secret and client_secret:
        fields["client_secret"] = client_secret
    response = (posting or post_json)(provider.token_endpoint, fields)
    token, expires = response.get("access_token"), response.get("expires_in")
    if not isinstance(token, str) or not token or not isinstance(expires, int) or expires <= 0:
        raise Refused(f"{provider.display_name} did not return a usable access token")
    return Access(token, str(account["email"]), str(account["subject"]),
                  int(time.time()) + expires)


def browser_authorize(request: Authorization, posting: Optional[Posting] = None,
                      getting: Optional[Getting] = None) -> Tuple[Tokens, Identity]:
    """Run a loopback Desktop PKCE flow, then verify identity through the declared endpoint."""
    verifier = _url_random(64)
    challenge = _url_b64(hashlib.sha256(verifier.encode("ascii")).digest())
    state, callback_path = _url_random(32), "/" + _url_random(24)
    server = _callback_server(callback_path, state)
    redirect = f"http://127.0.0.1:{server.server_port}{callback_path}"
    query = {
        "client_id": request.client_id, "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(request.scopes), "state": state, "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    query.update(request.provider.authorization_parameters)
    url = f"{request.provider.authorization_endpoint}?{urllib.parse.urlencode(query)}"
    if not webbrowser.open(url, new=1, autoraise=True):
        print("Open this address in a browser to continue:")
        print(url)
    server.timeout = CALLBACK_SECONDS
    try:
        server.handle_request()
        result = server.result
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
    tokens = _tokens(request.provider, (posting or post_json)(request.provider.token_endpoint,
                                                               fields))
    who = (getting or get_json)(request.provider.identity_endpoint, tokens.access)
    identity = Identity(str(who.get(request.provider.subject_field) or ""),
                        str(who.get(request.provider.email_field) or ""))
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
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=30) as response:
            raw = response.read(MAX_FRAME + 1)
    except Refused:
        raise
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as trouble:
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


def read_frame(fd: int) -> Mapping[str, object]:
    _validated_socket(fd)
    size = struct.unpack(">I", _read_exact(fd, 4))[0]
    if size > MAX_FRAME:
        raise Refused("the OAuth protocol frame is too large")
    try:
        payload = json.loads(_read_exact(fd, size).decode("utf-8"))
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


def _client(provider: Provider, profile: str) -> Tuple[str, str, Optional[str], str]:
    key = profile_key(profile)
    app = _application(provider, key)
    if not app or not app.get("client_id") or (provider.client_secret and not app.get("client_secret")):
        raise Refused(f"no OAuth app client is configured for {provider.display_name} profile "
                      f"{key.lower()}")
    fingerprint = hashlib.sha256(str(app["client_id"]).encode("utf-8")).hexdigest()
    return key, str(app["client_id"]), (str(app["client_secret"])
                                        if app.get("client_secret") else None), fingerprint


def _application(provider: Provider, key: str) -> Optional[Dict[str, object]]:
    theirs = dict(_document()["providers"]).get(provider.provider) or {}
    applications = theirs.get("applications") if isinstance(theirs, dict) else {}
    app = dict(applications or {}).get(key)
    if not isinstance(app, dict):
        return None
    if app.get("descriptor_fingerprint") != provider.fingerprint:
        raise Refused(f"the installed declaration for {provider.display_name} changed; "
                      "review it and reconnect this app profile")
    return app


def _accounts(provider: Provider, key: str) -> Dict[str, Dict[str, object]]:
    app = _application(provider, key) or {}
    return {subject: account for subject, account in dict(app.get("accounts") or {}).items()
            if isinstance(account, dict)}


def _selected(provider: Provider, email: Optional[str], key: str) -> Dict[str, object]:
    accounts = list(_accounts(provider, key).values())
    if email:
        accounts = [one for one in accounts
                    if str(one.get("email", "")).casefold() == email.casefold()]
    if not accounts:
        raise Refused(f"no matching {provider.display_name} account is connected")
    if len(accounts) != 1:
        available = ", ".join(sorted(str(one.get("email")) for one in accounts))
        raise Refused(f"more than one account is connected; choose --email from: {available}")
    return accounts[0]


def _replace_account(provider: Provider, key: str, identity: Identity, tokens: Tokens,
                     fingerprint: str, expected: Optional[Mapping[str, object]] = None
                     ) -> Dict[str, object]:
    account: Dict[str, object] = {
        "subject": identity.subject, "email": identity.email,
        "refresh_token": tokens.refresh, "scopes": sorted(set(tokens.scopes)),
        "client_fingerprint": fingerprint,
    }

    def replacing(raw: Optional[str]) -> str:
        held = _document_from(raw)
        providers = dict(held["providers"])
        theirs = dict(providers.get(provider.provider) or {})
        applications = dict(theirs.get("applications") or {})
        app = dict(applications.get(key) or {})
        if app.get("descriptor_fingerprint") != provider.fingerprint:
            raise Refused("the OAuth provider declaration changed while authorization was open")
        accounts = dict(app.get("accounts") or {})
        if expected is not None and accounts.get(identity.subject) != expected:
            raise Refused("this account grant changed while consent was open; retry the integration "
                          "request so no newer grant is overwritten")
        accounts[identity.subject] = account
        app["accounts"], applications[key] = accounts, app
        theirs["applications"], providers[provider.provider] = applications, theirs
        return _encoded({"version": VERSION, "providers": providers})

    secrets.changed(STATE, replacing)
    return account


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


def _tokens(provider: Provider, raw: Mapping[str, object]) -> Tokens:
    access, refresh, expires, scope = (raw.get("access_token"), raw.get("refresh_token"),
                                       raw.get("expires_in"), raw.get("scope"))
    if not isinstance(access, str) or not access or not isinstance(expires, int) or expires <= 0:
        raise Refused(f"{provider.display_name} returned a malformed token response")
    if refresh is not None and (not isinstance(refresh, str) or not refresh):
        raise Refused(f"{provider.display_name} returned a malformed refresh token")
    return Tokens(access, refresh, expires, tuple(scope.split()) if isinstance(scope, str) else ())


def _valid_identity(provider: Provider, identity: Identity) -> None:
    if not identity.subject or not identity.email or "@" not in identity.email:
        raise Refused(f"{provider.display_name} returned no usable verified identity")


def _encoded(value: Mapping[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _callback_server(path: str, state: str):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlsplit(self.path)
            try:
                query = urllib.parse.parse_qs(parsed.query, strict_parsing=True)
            except ValueError:
                query = {}
            flat = {key: values[0] for key, values in query.items() if len(values) == 1}
            allowed = ({"state", "code"} if "code" in flat
                       else {"state", "error", "error_description"})
            valid = (parsed.path == path and not parsed.fragment and set(query).issubset(allowed)
                     and len(flat) == len(query)
                     and hmac.compare_digest(flat.get("state", ""), state))
            if valid:
                self.server.result, status = flat, 200  # type: ignore[attr-defined]
                body = ("<!doctype html><meta charset=utf-8><title>Authorization received</title>"
                        "<h1>Authorization received</h1><p>Return to Rundesk while it verifies the "
                        "account. This tab will try to close in <span id=count>3</span> seconds; if "
                        "the browser blocks it, you may close this tab manually.</p><script>let n=3;"
                        "setInterval(()=>{n-=1;document.getElementById('count').textContent=n;if(n"
                        "<=0)window.close()},1000)</script>")
            else:
                self.server.result, status = {"error": "invalid_callback"}, 400  # type: ignore[attr-defined]
                body = ("<!doctype html><meta charset=utf-8><title>Authorization rejected</title>"
                        "<h1>Authorization rejected</h1><p>This callback was not accepted. Return "
                        "to Rundesk and try again.</p>")
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

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    server.result = None
    return server


def _url_random(size: int) -> str:
    return _url_b64(randomness.token_bytes(size))


def _url_b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _read_exact(fd: int, wanted: int) -> bytes:
    held = bytearray()
    while len(held) < wanted:
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
