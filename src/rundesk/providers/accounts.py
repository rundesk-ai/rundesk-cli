"""Registered additional accounts for provider adapters, without credential custody.

An alias is only a name and a private provider-owned home. Rundesk never opens anything inside that
home: the adapter's official login, status, logout, and turn processes are the only readers and
writers. Directory existence is the registry, avoiding a second index that could disagree with it.
"""

import os
from pathlib import Path
from typing import List, NamedTuple, Optional

from rundesk.core import paths
from rundesk.providers import adapters
from rundesk.utils import files

RESERVED = "default"
HOME = "home"


class Refused(Exception):
    """An alias operation that would be ambiguous or cross its exact account boundary."""


class Account(NamedTuple):
    """Provider-neutral metadata for one registered additional account."""

    provider_name: str
    alias: str
    home: Path


def alias_trouble(alias: str) -> str:
    """Why this cannot name an additional account, or an empty string when it can."""
    trouble = files.name_trouble(alias)
    if trouble:
        return trouble
    if alias.casefold() == RESERVED:
        return (f"{RESERVED} is reserved for the provider's ordinary account and can never be "
                "an alias")
    return ""


def provider_at(provider_name: str) -> Path:
    """The registry directory for one canonical provider identity."""
    return paths.provider_accounts() / adapters.key(adapters.canonical(provider_name))


def same(provider_name: str, alias: Optional[str], other_provider: str,
         other_alias: Optional[str]) -> bool:
    """Whether two spellings name the same exact provider account boundary.

    Provider spelling is provenance everywhere else. Only an account decision collapses a path
    spelling to the adapter program behind it, so ``./adapter`` cannot acquire a second alias
    registry or evade an active/reference check against its absolute spelling.
    """
    return alias == other_alias and adapters.canonical(provider_name) == adapters.canonical(
        other_provider)


def alias_at(provider_name: str, alias: str) -> Path:
    """The exact registered directory, refusing traversal before deriving it."""
    trouble = alias_trouble(alias)
    if trouble:
        raise Refused(trouble)
    at = provider_at(provider_name) / alias
    if files.escapes(at, provider_at(provider_name)):
        raise Refused(f"{alias} does not stand below this provider's account registry")
    return at


def account_home(provider_name: str, alias: Optional[str]) -> Optional[Path]:
    """The named account home, or ``None`` for the unchanged implicit default."""
    if alias is None:
        return None
    at = alias_at(provider_name, alias)
    if not at.is_dir() or at.is_symlink():
        raise Refused(f"{alias} is not a registered alias for {provider_name}")
    return at / HOME


def known(provider_name: str) -> List[Account]:
    """Registered aliases for one provider, sorted without following links."""
    root = provider_at(provider_name)
    if not root.is_dir() or root.is_symlink():
        return []
    canonical = adapters.canonical(provider_name)
    return [Account(canonical, one.name, one / HOME)
            for one in sorted(root.iterdir(), key=lambda item: item.name.casefold())
            if one.is_dir() and not one.is_symlink() and alias_trouble(one.name) == ""]


def registered(provider_name: str, alias: str) -> Account:
    """Register one empty private provider-owned home, refusing case collisions."""
    at = alias_at(provider_name, alias)
    for one in known(provider_name):
        if one.alias.casefold() == alias.casefold():
            if one.alias == alias:
                raise Refused(f"{alias} is already registered for {provider_name}")
            raise Refused(f"{one.alias} is already registered for {provider_name}, and this "
                          f"machine may not tell {one.alias} and {alias} apart")
    if at.exists() or at.is_symlink():
        raise Refused(f"{at} is already there and will not be replaced")
    at.mkdir(parents=True, mode=0o700)
    os.chmod(at, 0o700)
    home = at / HOME
    home.mkdir(mode=0o700)
    os.chmod(home, 0o700)
    return Account(adapters.canonical(provider_name), alias, home)


def removed(provider_name: str, alias: str) -> Path:
    """Remove one exact registered alias and its provider-owned home."""
    at = alias_at(provider_name, alias)
    if not at.is_dir() or at.is_symlink():
        raise Refused(f"{alias} is not a registered alias for {provider_name}")
    files.remove_one(at)
    if at.exists() or at.is_symlink():
        raise Refused(f"{at} could not be removed")
    root = provider_at(provider_name)
    try:
        root.rmdir()
    except OSError:
        pass
    return at
