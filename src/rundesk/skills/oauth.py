"""Declarative OAuth provider discovery from installed catalog skills.

A provider is a JSON file beside a skill's `SKILL.md`. Nothing here executes anything a catalog
ships: what is read is data, every field is checked against a closed schema, and what comes out is
the frozen `core.oauth.Provider` the broker works with. That is the whole reason Rundesk can gain a
provider without gaining a line of provider-specific code.

**A declaration is untrusted input from a repository somebody installed**, so every string and
every collection in it is bounded. An unbounded one is not a crash; it is one skill deciding how
much memory `rundesk login --help` uses.
"""

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Mapping, NamedTuple, Optional
from urllib.parse import urlsplit

from rundesk.core import oauth as mechanics
from rundesk.skills import library

DECLARED = "oauth-provider.json"
SCHEMA = 1
FIELDS = {"schema", "provider", "display_name", "authorization_endpoint", "token_endpoint",
          "identity_endpoint", "base_scopes", "identity", "authorization_parameters",
          "client_secret", "capabilities"}

#: The most of a declaration that is ever read. Far past any real one — the shipped example is
#: under a kilobyte — and short enough that a file cannot be a memory bill.
MOST_BYTES = 65536

#: What any single declared string may be. A scope, an endpoint and a display name are all short;
#: nothing legitimate approaches this.
MOST_TEXT = 1024

#: How many entries each declared collection may hold. Providers publish a handful of identity
#: scopes and a handful of authorization parameters; a catalog with more than this many
#: capabilities has stopped describing one provider.
MOST_SCOPES = 32
MOST_PARAMETERS = 32
MOST_CAPABILITIES = 64

#: Which fields decide what this provider *does*. The fingerprint is taken over exactly these, so a
#: corrected spelling in `display_name` is not a security event — see `_fingerprinted`.
SECURING = FIELDS - {"display_name"}


class Refused(Exception):
    """A catalog OAuth declaration that cannot safely be used."""


class Discovered(NamedTuple):
    """Every usable declaration, and every one that could not be read, kept apart.

    **Two lists rather than an exception, and the separation is the point.** One catalog shipping a
    malformed file used to make every *other* provider on the install unreachable, so a typo in a
    skill nobody was using broke a login that had nothing to do with it. Installing a broken
    declaration is still refused outright — see `trouble_with`, which `skills.catalogs` calls — so
    the only way one of these reaches a running install is if it was already there or was edited in
    place. At that point the honest answer is "this one is unusable, the rest are fine".
    """

    providers: List[mechanics.Provider]
    troubles: List[str]


def read(at: Path) -> mechanics.Provider:
    """The provider one skill declares, or a refusal saying which field was wrong."""
    declared = at / DECLARED
    try:
        with declared.open("rb") as held:
            raw = held.read(MOST_BYTES + 1)
    except OSError as trouble:
        raise Refused(f"{declared} is not readable JSON") from trouble
    if len(raw) > MOST_BYTES:
        raise Refused(f"{declared} is larger than {MOST_BYTES} bytes")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as trouble:
        raise Refused(f"{declared} is not readable JSON") from trouble
    if not isinstance(value, dict) or set(value) != FIELDS or value.get("schema") != SCHEMA:
        raise Refused(f"{declared} does not use OAuth provider schema {SCHEMA}")
    provider = _identifier(value.get("provider"), "provider", declared)
    display = _text(value.get("display_name"), "display_name", declared)
    endpoints = [_endpoint(value.get(name), name, declared) for name in
                 ("authorization_endpoint", "token_endpoint", "identity_endpoint")]
    scopes = _strings(value.get("base_scopes"), "base_scopes", declared)
    identity = value.get("identity")
    if not isinstance(identity, dict) or set(identity) != {"subject", "email", "email_verified"}:
        raise Refused(f"{declared} identity must name subject, email, and email_verified fields")
    fields = [_text(identity.get(name), f"identity.{name}", declared)
              for name in ("subject", "email", "email_verified")]
    parameters = _mapping(value.get("authorization_parameters"), declared, MOST_PARAMETERS)
    overlap = set(parameters) & mechanics.RESERVED_AUTH
    if overlap:
        raise Refused(f"{declared} may not override OAuth mechanics: {', '.join(sorted(overlap))}")
    secret = value.get("client_secret")
    if not isinstance(secret, bool):
        raise Refused(f"{declared} client_secret must be true or false")
    capabilities = _mapping(value.get("capabilities"), declared, MOST_CAPABILITIES,
                            identifiers=True)
    if not capabilities:
        raise Refused(f"{declared} must declare at least one capability")
    return mechanics.Provider(provider, display, *endpoints, tuple(scopes), *fields, parameters,
                              secret, capabilities, _fingerprinted(value))


def discovered() -> Discovered:
    """Every declaration this install has, with the unusable ones set aside rather than fatal."""
    found: Dict[str, mechanics.Provider] = {}
    owners: Dict[str, str] = {}
    troubles: List[str] = []
    for skill in library.every():
        if not skill.at.joinpath(DECLARED).is_file():
            continue
        try:
            provider = read(skill.at)
        except Refused as trouble:
            troubles.append(f"{skill.address}: {trouble}")
            continue
        if provider.provider in found:
            # **Both are dropped, not the second one.** Which of two skills declaring one ID is the
            # real provider is not a question a walk order should answer: a grant made against the
            # wrong one is a credential handed to whichever catalog was installed first.
            troubles.append(f"OAuth provider {provider.provider!r} is declared by both "
                            f"{owners[provider.provider]} and {skill.address}")
            found.pop(provider.provider)
            continue
        found[provider.provider], owners[provider.provider] = provider, skill.address
    return Discovered([found[name] for name in sorted(found)], troubles)


def every() -> List[mechanics.Provider]:
    """Every provider that can be used. See `discovered` for the ones that cannot."""
    return discovered().providers


def named(name: str) -> mechanics.Provider:
    """The provider called `name`, or a refusal that says what there is instead."""
    held = discovered()
    for provider in held.providers:
        if provider.provider == name:
            return provider
    available = ", ".join(one.provider for one in held.providers) or "none"
    unusable = (f"; {len(held.troubles)} installed declaration(s) cannot be used: "
                + "; ".join(held.troubles)) if held.troubles else ""
    raise Refused(f"there is no installed OAuth provider called {name!r} "
                  f"(available: {available}){unusable}")


def trouble_with(at: Path) -> Optional[str]:
    """Why this skill's declaration may not be installed, or `None`.

    The strict half of the pair: `skills.catalogs` calls this before accepting a catalog, so a
    malformed declaration is refused at the door rather than discovered by somebody trying to log
    in. `discovered` is deliberately lenient about what is already on disk; this is not.
    """
    if not at.joinpath(DECLARED).exists():
        return None
    try:
        read(at)
    except Refused as trouble:
        return str(trouble)
    return None


def _fingerprinted(value: Mapping[str, object]) -> str:
    """What this declaration promises, as one hash — over what it *does*, not what it is called.

    A stored grant is pinned to this, so a declaration that changes under an install is refused
    until somebody has looked at it. Taken over the whole file, that guarantee also fired on a
    typo fixed in `display_name`, and telling an owner to reconnect every account because a catalog
    corrected its capitalisation trains them to reconnect without reading. Every field that decides
    where a token goes, what it can do, or who it belongs to is still in here.
    """
    securing = {name: value[name] for name in sorted(SECURING) if name in value}
    return hashlib.sha256(
        json.dumps(securing, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _text(value: object, field: str, at: Path) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MOST_TEXT:
        raise Refused(f"{at} {field} must be a non-empty string of at most {MOST_TEXT} characters")
    return value.strip()


def _identifier(value: object, field: str, at: Path) -> str:
    text = _text(value, field, at)
    if len(text) > library.NAMED_LIMIT or not library.CALLED.fullmatch(text):
        raise Refused(f"{at} {field} must be a lowercase hyphenated identifier")
    return text


def _endpoint(value: object, field: str, at: Path) -> str:
    """One HTTPS endpoint, with no query and no fragment.

    **Both are refused rather than merged**, and that is what lets `core.oauth` build an
    authorization URL by appending `?` and its own parameters. A declared query would either be
    thrown away by that append or — worse, in the version this replaces — sit in front of it, where
    a `?scope=` in the declaration is read by the provider before Rundesk's own. A provider that
    genuinely requires an extra parameter has `authorization_parameters`, which is checked against
    `RESERVED_AUTH`.
    """
    endpoint = _text(value, field, at)
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password \
            or parsed.query or parsed.fragment:
        raise Refused(f"{at} {field} must be an HTTPS URL with no credentials, query, or fragment")
    return endpoint


def _strings(value: object, field: str, at: Path) -> List[str]:
    if not isinstance(value, list) or not value or len(value) > MOST_SCOPES \
            or any(not isinstance(one, str) or not one.strip() or len(one) > MOST_TEXT
                   for one in value):
        raise Refused(f"{at} {field} must be 1 to {MOST_SCOPES} non-empty bounded strings")
    result = [one.strip() for one in value]
    if len(result) != len(set(result)):
        raise Refused(f"{at} {field} contains duplicates")
    return result


def _mapping(value: object, at: Path, most: int, identifiers: bool = False) -> Mapping[str, str]:
    if not isinstance(value, dict):
        raise Refused(f"{at} expected a string mapping")
    if len(value) > most:
        raise Refused(f"{at} may declare at most {most} entries in one mapping")
    answer: Dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str) or not item.strip() \
                or len(key) > MOST_TEXT or len(item) > MOST_TEXT:
            raise Refused(f"{at} expected a string mapping of bounded values")
        name = _identifier(key, "capability", at) if identifiers else key.strip()
        if not name:
            raise Refused(f"{at} mapping keys cannot be empty")
        answer[name] = item.strip()
    return answer
