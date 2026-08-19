"""The compact, current teammate directory one eligible turn reads.

Descriptions come from agent records and skill *names* from current grants. Bodies stay in native
skill discovery, where they cost context only when used. This module belongs above both `agents`
and `skills`; neither lower layer has to know the other exists.
"""

import sqlite3

from rundesk.agents import delegating, directory, records
from rundesk.skills import grants
from rundesk.utils import locking

SKILLS_AT_MOST = 8
TEAMMATES_AT_MOST = 12
TEAM_BYTES_AT_MOST = 5720


def for_agent(name: str) -> str:
    """Every permitted, described agent except `name`, with bounded current skill names."""
    lines = []
    unavailable = 0
    try:
        scope = delegating.scope_of(name)
    except (delegating.Refused, directory.Refused, records.NotThere, records.Unreadable,
            sqlite3.DatabaseError, OSError):
        # An unreadable authority is never widened to the historical unrestricted default.
        return ""
    for other in directory.known():
        if other == name or not delegating.allows(scope, other):
            continue
        held = locking.is_held(directory.where(other) / directory.GATEWAY_LOCK)
        if held is None:
            unavailable += 1
            continue
        if not held:
            continue
        try:
            said = records.read(directory.records(other))
            describes = str(said.get("describes") or "").strip()
            skills = [one.name for one in grants.held(other)]
        except (directory.Refused, records.NotThere, records.Unreadable,
                sqlite3.DatabaseError, OSError):
            unavailable += 1
            continue
        if not describes:
            continue
        shown = skills[:SKILLS_AT_MOST]
        skill_names = ", ".join(shown) if shown else "none"
        if len(skills) > SKILLS_AT_MOST:
            skill_names += f" (+{len(skills) - SKILLS_AT_MOST} more)"
        lines.append(f"- **{other}** — {describes} · skills: {skill_names}")
    shown = []
    for line in lines[:TEAMMATES_AT_MOST]:
        # Leave room for the omission marker. Whole entries only: clipping a skill or description
        # makes a routing fact ambiguous.
        if len("\n".join([*shown, line]).encode("utf-8")) > TEAM_BYTES_AT_MOST - 180:
            break
        shown.append(line)
    if len(lines) > len(shown):
        shown.append(f"- … {len(lines) - len(shown)} more online agents omitted")
    if unavailable:
        shown.append(f"- … {unavailable} agents omitted because availability could not be verified")
    return "\n".join(shown) if lines or unavailable else ""
