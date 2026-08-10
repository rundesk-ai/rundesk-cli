"""Which named agents one agent may hand work to.

The stored policy has three deliberate states: ``NULL`` means every other agent (the compatible
default), ``[]`` means nobody, and a non-empty JSON array is an exact allowlist.  This module is the
one interpreter shared by prompt composition and admission; a list shown to a brain and a command
that accepts something different would be guidance, not a boundary.
"""

import json
from typing import Any, Iterable, Optional, Tuple

from rundesk.agents import directory, records

ANY = "any"
NONE = "none"


class Refused(Exception):
    """A delegation policy cannot be understood or configured as requested."""


def decoded(value: Any) -> Optional[Tuple[str, ...]]:
    """Return ``None`` for unrestricted or the exact ordered allowlist; fail closed if malformed."""
    if value is None:
        return None
    try:
        settled = json.loads(str(value))
    except (TypeError, ValueError) as why:
        raise Refused("this agent's delegation scope cannot be read safely") from why
    if not isinstance(settled, list) or any(not isinstance(one, str) or not one for one in settled):
        raise Refused("this agent's delegation scope cannot be read safely")
    if len(set(settled)) != len(settled):
        raise Refused("this agent's delegation scope cannot be read safely")
    return tuple(settled)


def scope_of(agent: str) -> Optional[Tuple[str, ...]]:
    """The current policy for ``agent`` from its own records."""
    return decoded(records.read(directory.records(agent)).get("delegates_to"))


def encoded(targets: Optional[Iterable[str]]) -> Optional[str]:
    """The stable SQLite representation of a policy."""
    if targets is None:
        return None
    return json.dumps(list(targets), ensure_ascii=False, separators=(",", ":"))


def allows(scope: Optional[Tuple[str, ...]], target: str) -> bool:
    """Whether ``target`` is permitted by an already-decoded policy."""
    return scope is None or target in scope


def shown(scope: Optional[Tuple[str, ...]]) -> str:
    """The compact value an owner sees in an agents listing or configure result."""
    if scope is None:
        return ANY
    return ", ".join(scope) if scope else NONE


def configured(agent: str, targets: Iterable[str]) -> Tuple[str, ...]:
    """Validate and preserve an exact allowlist supplied by the owner.

    Targets need not be online: policy is durable authority while gateway state is readiness.  They
    must exist now so a typo cannot silently become authority for an agent created later.
    """
    settled = tuple(targets)
    if any(not one for one in settled):
        raise Refused("an agent to delegate to cannot be blank")
    if agent in settled:
        raise Refused(f"{agent} cannot be configured to delegate to itself")
    if len(set(settled)) != len(settled):
        repeated = next(one for index, one in enumerate(settled) if one in settled[:index])
        raise Refused(f"{repeated} was named more than once as a delegation target")
    known = set(directory.known())
    missing = next((one for one in settled if one not in known), None)
    if missing is not None:
        raise Refused(f"{missing} is not an agent on this install")
    return settled
