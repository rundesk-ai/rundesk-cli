"""Declarative OAuth provider discovery from installed catalog skills."""

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Mapping, Optional
from urllib.parse import urlsplit

from rundesk.core import oauth as mechanics
from rundesk.skills import library

DECLARED = "oauth-provider.json"
SCHEMA = 1
FIELDS = {"schema", "provider", "display_name", "authorization_endpoint", "token_endpoint",
          "identity_endpoint", "base_scopes", "identity", "authorization_parameters",
          "client_secret", "capabilities"}


class Refused(Exception):
    """A catalog OAuth declaration that cannot safely be used."""


def read(at: Path) -> mechanics.Provider:
    declared = at / DECLARED
    try:
        value = json.loads(declared.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as trouble:
        raise Refused(f"{declared} is not readable JSON") from trouble
    if not isinstance(value, dict) or set(value) != FIELDS or value.get("schema") != SCHEMA:
        raise Refused(f"{declared} does not use OAuth provider schema {SCHEMA}")
    provider = _identifier(value.get("provider"), "provider", declared)
    display = _text(value.get("display_name"), "display_name", declared)
    endpoints = [_endpoint(value.get(name), name, declared) for name in
                 ("authorization_endpoint", "token_endpoint", "identity_endpoint")]
    scopes = _strings(value.get("base_scopes"), "base_scopes", declared, required=True)
    identity = value.get("identity")
    if not isinstance(identity, dict) or set(identity) != {"subject", "email", "email_verified"}:
        raise Refused(f"{declared} identity must name subject, email, and email_verified fields")
    fields = [_text(identity.get(name), f"identity.{name}", declared)
              for name in ("subject", "email", "email_verified")]
    parameters = _mapping(value.get("authorization_parameters"), declared)
    overlap = set(parameters) & mechanics.RESERVED_AUTH
    if overlap:
        raise Refused(f"{declared} may not override OAuth mechanics: {', '.join(sorted(overlap))}")
    secret = value.get("client_secret")
    if not isinstance(secret, bool):
        raise Refused(f"{declared} client_secret must be true or false")
    capabilities = _mapping(value.get("capabilities"), declared, identifiers=True)
    if not capabilities:
        raise Refused(f"{declared} must declare at least one capability")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return mechanics.Provider(provider, display, *endpoints, tuple(scopes), *fields, parameters,
                              secret, capabilities, hashlib.sha256(canonical).hexdigest())


def every() -> List[mechanics.Provider]:
    found: Dict[str, mechanics.Provider] = {}
    owners: Dict[str, str] = {}
    for skill in library.every():
        if not skill.at.joinpath(DECLARED).is_file():
            continue
        provider = read(skill.at)
        if provider.provider in found:
            raise Refused(f"OAuth provider {provider.provider!r} is declared by both "
                          f"{owners[provider.provider]} and {skill.address}")
        found[provider.provider], owners[provider.provider] = provider, skill.address
    return [found[name] for name in sorted(found)]


def named(name: str) -> mechanics.Provider:
    providers = every()
    for provider in providers:
        if provider.provider == name:
            return provider
    available = ", ".join(one.provider for one in providers) or "none"
    raise Refused(f"there is no installed OAuth provider called {name!r} (available: {available})")


def trouble_with(at: Path) -> Optional[str]:
    if not at.joinpath(DECLARED).exists():
        return None
    try:
        read(at)
    except Refused as trouble:
        return str(trouble)
    return None


def _text(value: object, field: str, at: Path) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise Refused(f"{at} {field} must be a non-empty bounded string")
    return value.strip()


def _identifier(value: object, field: str, at: Path) -> str:
    text = _text(value, field, at)
    if len(text) > library.NAMED_LIMIT or not library.CALLED.fullmatch(text):
        raise Refused(f"{at} {field} must be a lowercase hyphenated identifier")
    return text


def _endpoint(value: object, field: str, at: Path) -> str:
    endpoint = _text(value, field, at)
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password \
            or parsed.fragment:
        raise Refused(f"{at} {field} must be an HTTPS URL without credentials or a fragment")
    return endpoint


def _strings(value: object, field: str, at: Path, required: bool = False) -> List[str]:
    if not isinstance(value, list) or (required and not value) \
            or any(not isinstance(one, str) or not one.strip() for one in value):
        raise Refused(f"{at} {field} must be a list of non-empty strings")
    result = [one.strip() for one in value]
    if len(result) != len(set(result)):
        raise Refused(f"{at} {field} contains duplicates")
    return result


def _mapping(value: object, at: Path, identifiers: bool = False) -> Mapping[str, str]:
    if not isinstance(value, dict):
        raise Refused(f"{at} expected a string mapping")
    answer: Dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str) or not item.strip():
            raise Refused(f"{at} expected a string mapping")
        name = _identifier(key, "capability", at) if identifiers else key.strip()
        if not name:
            raise Refused(f"{at} mapping keys cannot be empty")
        answer[name] = item.strip()
    return answer
