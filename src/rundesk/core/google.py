"""Google identities and grants, sealed at rest and released only through a private FD.

Email is the human selector; Google's immutable ``sub`` is the durable key.  The OAuth client and
every bit of grant metadata stay in the existing sealed store.  Network and browser decisions are
arguments so the complete flow is testable without either.
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
from typing import Callable, Dict, List, Mapping, NamedTuple, Optional, Sequence, Tuple

from rundesk.core import secrets

CLIENT_ID = "GOOGLE_OAUTH_CLIENT_ID"
CLIENT_SECRET = "GOOGLE_OAUTH_CLIENT_SECRET"
GRANTS = "RUNDESK_GOOGLE_OAUTH_GRANTS"
VERSION = 1
PROTOCOL = 1
MAX_FRAME = 65536
WRITE_SECONDS = 5.0
CALLBACK_SECONDS = 180
AUTHORIZE_AT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_AT = "https://oauth2.googleapis.com/token"
USERINFO_AT = "https://openidconnect.googleapis.com/v1/userinfo"
BASE_SCOPES = ("openid", "email")
CAPABILITIES = {
    "analytics": "https://www.googleapis.com/auth/analytics.readonly",
    "search-console": "https://www.googleapis.com/auth/webmasters",
    "merchant": "https://www.googleapis.com/auth/content",
}


class Refused(Exception):
    """A request that cannot safely produce or persist a Google grant."""


class Tokens(NamedTuple):
    """The parts of Google's token response this boundary uses."""

    access: str
    refresh: Optional[str]
    expires_in: int
    scopes: Tuple[str, ...]


class Identity(NamedTuple):
    """A Google identity established from UserInfo, never from caller input."""

    sub: str
    email: str


class Access(NamedTuple):
    """A short-lived access answer for an internal integration caller."""

    token: str
    email: str
    sub: str
    expires_at: int


@dataclass(frozen=True)
class Authorization:
    """Everything the interactive boundary needs, with no durable state attached."""

    client_id: str
    client_secret: str
    scopes: Tuple[str, ...]


Authorizing = Callable[[Authorization], Tuple[Tokens, Identity]]
Posting = Callable[[str, Mapping[str, str]], Mapping[str, object]]
Getting = Callable[[str, str], Mapping[str, object]]


def emails(profile: str = "") -> List[str]:
    """Every unambiguous verified email this client has authorized."""
    key, _, _, _ = _client(profile)
    accounts = _accounts_for_client(key)
    return sorted(str(one["email"]) for one in accounts.values())


def authorize(profile: str = "", scopes: Sequence[str] = BASE_SCOPES,
              authorizing: Optional[Authorizing] = None) -> str:
    """Ask Google for one identity and atomically replace only that immutable account."""
    key, client_id, client_secret, fingerprint = _client(profile)
    wanted = _scopes(scopes)
    tokens, identity = (authorizing or browser_authorize)(
        Authorization(client_id, client_secret, wanted))
    _valid_identity(identity)
    if not tokens.refresh:
        raise Refused("Google returned no refresh token; no account was changed")
    if not set(wanted).issubset(tokens.scopes):
        raise Refused("Google did not grant every requested scope; no account was changed")
    _replace_account(key, identity, tokens, fingerprint)
    return identity.email


def access(capability: str, email: Optional[str], profile: str = "",
           authorizing: Optional[Authorizing] = None,
           posting: Optional[Posting] = None) -> Access:
    """Return one short-lived token, extending consent for the selected profile when needed."""
    scope = CAPABILITIES.get(capability)
    if scope is None:
        raise Refused(f"nothing internal is registered for Google capability {capability!r}")
    key, client_id, client_secret, fingerprint = _client(profile)
    account = _selected(email, key)
    if account.get("client_fingerprint") != fingerprint:
        raise Refused("the Google OAuth client changed; run `rundesk login google` again")
    wanted = _scopes((*tuple(account.get("scopes") or ()), scope))
    if scope not in account.get("scopes", ()):
        tokens, identity = (authorizing or browser_authorize)(
            Authorization(client_id, client_secret, wanted))
        _valid_identity(identity)
        if identity.sub != account["sub"] or identity.email.casefold() != account["email"].casefold():
            raise Refused("Google returned a different account; no grant was changed")
        if not tokens.refresh or not set(wanted).issubset(tokens.scopes):
            raise Refused("Google did not return a reusable grant for every requested scope")
        account = _replace_account(key, identity, tokens, fingerprint, expected=account)
    response = (posting or post_json)(TOKEN_AT, {
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": str(account["refresh_token"]), "grant_type": "refresh_token",
    })
    token = response.get("access_token")
    expires = response.get("expires_in")
    if not isinstance(token, str) or not token or not isinstance(expires, int) or expires <= 0:
        raise Refused("Google did not return a usable access token")
    return Access(token, str(account["email"]), str(account["sub"]), int(time.time()) + expires)


def write_frame(fd: int, payload: Mapping[str, object], timeout: float = WRITE_SECONDS) -> None:
    """Write one bounded v1 frame to a connected anonymous socket before a fixed deadline."""
    _validated_socket(fd)
    body = json.dumps({"version": PROTOCOL, **payload}, separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_FRAME:
        raise Refused("the response is too large for the Google protocol")
    frame = struct.pack(">I", len(body)) + body
    deadline = time.monotonic() + timeout
    blocking = os.get_blocking(fd)
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
    """Read and validate one response frame; useful to internal callers and protocol tests."""
    _validated_socket(fd)
    heading = _read_exact(fd, 4)
    size = struct.unpack(">I", heading)[0]
    if size > MAX_FRAME:
        raise Refused("the Google protocol frame is too large")
    try:
        payload = json.loads(_read_exact(fd, size).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as trouble:
        raise Refused("the Google protocol frame is malformed") from trouble
    if not isinstance(payload, dict) or payload.get("version") != PROTOCOL:
        raise Refused("the Google protocol version is not supported")
    return payload


def browser_authorize(request: Authorization, posting: Optional[Posting] = None,
                      getting: Optional[Getting] = None) -> Tuple[Tokens, Identity]:
    """Run a loopback PKCE flow, then verify identity with UserInfo."""
    verifier = _url_random(64)
    challenge = _url_b64(hashlib.sha256(verifier.encode("ascii")).digest())
    state = _url_random(32)
    callback_path = "/" + _url_random(24)
    server = _callback_server(callback_path, state)
    redirect = f"http://127.0.0.1:{server.server_port}{callback_path}"
    query = urllib.parse.urlencode({
        "client_id": request.client_id, "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(request.scopes), "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
        "access_type": "offline", "prompt": "consent select_account",
    })
    url = f"{AUTHORIZE_AT}?{query}"
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
        raise Refused("Google login timed out; no account was changed")
    if result.get("error"):
        raise Refused("Google login was declined; no account was changed")
    code = result.get("code")
    if not code:
        raise Refused("Google returned no authorization code; no account was changed")
    raw = (posting or post_json)(TOKEN_AT, {
        "client_id": request.client_id, "client_secret": request.client_secret,
        "code": code, "code_verifier": verifier, "redirect_uri": redirect,
        "grant_type": "authorization_code",
    })
    tokens = _tokens(raw)
    who = (getting or get_json)(USERINFO_AT, tokens.access)
    identity = Identity(str(who.get("sub") or ""), str(who.get("email") or ""))
    if who.get("email_verified") is not True:
        raise Refused("Google did not verify this account's email; no account was changed")
    _valid_identity(identity)
    return tokens, identity


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise Refused("Google unexpectedly redirected a credential request")


def post_json(url: str, fields: Mapping[str, str]) -> Mapping[str, object]:
    """POST form data and refuse redirects before parsing bounded JSON."""
    request = urllib.request.Request(url, urllib.parse.urlencode(fields).encode("ascii"),
                                     method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    return _opened(request)


def get_json(url: str, token: str) -> Mapping[str, object]:
    """GET UserInfo with its bearer token only in an HTTP header."""
    request = urllib.request.Request(url, method="GET")
    request.add_header("Authorization", f"Bearer {token}")
    return _opened(request)


def _opened(request: urllib.request.Request) -> Mapping[str, object]:
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=30) as response:
            raw = response.read(MAX_FRAME + 1)
    except Refused:
        raise
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as trouble:
        raise Refused("Google could not complete the credential request") from trouble
    if len(raw) > MAX_FRAME:
        raise Refused("Google returned an oversized credential response")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as trouble:
        raise Refused("Google returned a malformed credential response") from trouble
    if not isinstance(value, dict):
        raise Refused("Google returned a malformed credential response")
    return value


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
            if not valid:
                self.server.result = {"error": "invalid_callback"}  # type: ignore[attr-defined]
                self.send_response(400)
                body = ("<!doctype html><meta charset=utf-8><title>Authorization rejected</title>"
                        "<h1>Authorization rejected</h1>"
                        "<p>This callback was not accepted. Return to Rundesk and try again.</p>")
            else:
                self.server.result = flat  # type: ignore[attr-defined]
                self.send_response(200)
                body = ("<!doctype html><meta charset=utf-8><title>Authorization received</title>"
                        "<h1>Authorization received</h1><p>Return to Rundesk while it verifies "
                        "the account. This tab will try to close in <span id=count>3</span> "
                        "seconds; if the browser blocks it, you may close this tab manually.</p>"
                        "<script>let n=3;setInterval(()=>{n-=1;document.getElementById('count')"
                        ".textContent=n;if(n<=0)window.close()},1000)</script>")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Pragma", "no-cache")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; script-src 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    server.result = None
    return server


def _tokens(raw: Mapping[str, object]) -> Tokens:
    access, refresh, expires, scope = (raw.get("access_token"), raw.get("refresh_token"),
                                       raw.get("expires_in"), raw.get("scope"))
    if not isinstance(access, str) or not access or not isinstance(expires, int) or expires <= 0:
        raise Refused("Google returned a malformed token response")
    if refresh is not None and (not isinstance(refresh, str) or not refresh):
        raise Refused("Google returned a malformed refresh token")
    scopes = tuple(scope.split()) if isinstance(scope, str) else ()
    return Tokens(access, refresh, expires, scopes)


def _client(profile: str = "") -> Tuple[str, str, str, str]:
    key = _profile_key(profile)
    id_name = secrets.profiled(CLIENT_ID, key if key != "default" else "")
    secret_name = secrets.profiled(CLIENT_SECRET, key if key != "default" else "")
    kept = secrets.kept()
    for name in (id_name, secret_name):
        if name in kept and kept[name].trouble:
            raise Refused(f"the sealed Google OAuth app profile {key.lower()} cannot be read")
    client_id = kept.get(id_name).value if id_name in kept else None
    client_secret = kept.get(secret_name).value if secret_name in kept else None
    if not client_id or not client_secret:
        suffix = f" --profile {profile}" if profile else ""
        raise Refused("set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET with "
                      f"`rundesk env set` for this OAuth app profile{suffix}")
    fingerprint = hashlib.sha256(client_id.encode("utf-8")).hexdigest()
    return key, client_id, client_secret, fingerprint


def _document() -> Dict[str, object]:
    kept = secrets.kept().get(GRANTS)
    if kept and kept.trouble:
        raise Refused("the sealed Google grants cannot be read")
    raw = kept.value if kept else None
    return _document_from(raw)


def _document_from(raw: Optional[str]) -> Dict[str, object]:
    """One opened grant document, including the empty document before the first account."""
    if raw is None:
        return {"version": VERSION, "applications": {}}
    try:
        held = json.loads(raw)
    except json.JSONDecodeError as trouble:
        raise Refused("the sealed Google grants cannot be read") from trouble
    if not isinstance(held, dict) or held.get("version") != VERSION \
            or not isinstance(held.get("applications"), dict):
        raise Refused("the sealed Google grants use a version this release cannot read")
    return held


def _accounts_for_client(key: str) -> Dict[str, Dict[str, object]]:
    applications = dict(_document()["applications"])
    application = applications.get(key) or {}
    accounts = application.get("accounts") if isinstance(application, dict) else {}
    return {sub: value for sub, value in dict(accounts or {}).items()
            if isinstance(value, dict)}


def _selected(email: Optional[str], key: str) -> Dict[str, object]:
    accounts = list(_accounts_for_client(key).values())
    if email:
        accounts = [one for one in accounts
                    if str(one.get("email", "")).casefold() == email.casefold()]
    if not accounts:
        raise Refused("no matching Google account is connected; run `rundesk login google`")
    if len(accounts) != 1:
        available = ", ".join(sorted(str(one.get("email")) for one in accounts))
        raise Refused(f"more than one Google account is connected; choose --email from: {available}")
    return accounts[0]


def _replace_account(key: str, identity: Identity, tokens: Tokens, fingerprint: str,
                     expected: Optional[Mapping[str, object]] = None) -> Dict[str, object]:
    """Replace one immutable account, refusing a stale scope-extension snapshot."""
    account: Dict[str, object] = {
        "sub": identity.sub, "email": identity.email,
        "refresh_token": tokens.refresh, "scopes": sorted(set(tokens.scopes)),
        "client_fingerprint": fingerprint,
    }

    def replacing(raw: Optional[str]) -> str:
        held = _document_from(raw)
        applications = dict(held.get("applications") or {})
        application = dict(applications.get(key) or {})
        accounts = dict(application.get("accounts") or {})
        if expected is not None and accounts.get(identity.sub) != expected:
            raise Refused("this Google account grant changed while consent was open; retry the "
                          "integration request so no newer grant is overwritten")
        accounts[identity.sub] = account
        applications[key] = {"accounts": accounts}
        return json.dumps({"version": VERSION, "applications": applications},
                          sort_keys=True, separators=(",", ":"))

    secrets.changed(GRANTS, replacing)
    return account


def _profile_key(profile: str) -> str:
    """An OAuth app profile as an environment suffix and durable map key."""
    if not profile:
        if secrets.placed(CLIENT_ID) and secrets.placed(CLIENT_SECRET):
            return "default"
        names = set(secrets.names())
        prefix_id = CLIENT_ID + secrets.PROFILED_BY
        prefix_secret = CLIENT_SECRET + secrets.PROFILED_BY
        candidates = {name[len(prefix_id):] for name in names if name.startswith(prefix_id)}
        candidates &= {name[len(prefix_secret):] for name in names if name.startswith(prefix_secret)}
        if len(candidates) == 1:
            return next(iter(candidates))
        if len(candidates) > 1:
            raise Refused("more than one Google OAuth app profile is configured; choose --profile")
        return "default"
    named = profile.strip().upper()
    if secrets.name_trouble(named) or secrets.PROFILED_BY in named:
        raise Refused(f"{profile!r} is not a valid OAuth app profile name")
    return named


def _scopes(scopes: Sequence[str]) -> Tuple[str, ...]:
    return tuple(dict.fromkeys(BASE_SCOPES + tuple(scopes)))


def _valid_identity(identity: Identity) -> None:
    if not identity.sub or not identity.email or "@" not in identity.email:
        raise Refused("Google returned no usable verified identity; no account was changed")


def _url_random(size: int) -> str:
    return _url_b64(randomness.token_bytes(size))


def _url_b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _read_exact(fd: int, wanted: int) -> bytes:
    """Exactly one bounded segment, or a refusal when the anonymous peer closes early."""
    held = bytearray()
    while len(held) < wanted:
        part = os.read(fd, wanted - len(held))
        if not part:
            raise Refused("the Google protocol frame ended early")
        held.extend(part)
    return bytes(held)


def _validated_socket(fd: int) -> None:
    """Refuse everything except one connected unnamed local socket."""
    if fd in (0, 1, 2) or fd < 0:
        raise Refused("the response FD must be inherited and may not be stdin, stdout, or stderr")
    try:
        kind = os.fstat(fd).st_mode
        held = socket.socket(fileno=os.dup(fd))
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
