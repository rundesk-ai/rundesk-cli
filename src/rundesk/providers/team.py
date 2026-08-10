"""The compact, current teammate directory one eligible turn reads.

Descriptions come from agent records and skill *names* from current grants. Bodies stay in native
skill discovery, where they cost context only when used. This module belongs above both `agents`
and `skills`; neither lower layer has to know the other exists.
"""

import sqlite3

from rundesk.agents import delegating, directory, pages, records
from rundesk.skills import grants
from rundesk.utils import locking

SKILLS_AT_MOST = 8
TEAMMATES_AT_MOST = 12
TEAM_BYTES_AT_MOST = 5720


def for_agent(name: str) -> str:
    """Every permitted, described agent except `name`, with bounded current skill names."""
    grouped = {role: [] for role in pages.ROLES}
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
            role = str(said.get("role") or pages.DEFAULT_ROLE)
            skills = [one.name for one in grants.held(other)]
        except (directory.Refused, records.NotThere, records.Unreadable,
                sqlite3.DatabaseError, OSError):
            unavailable += 1
            continue
        if not describes or role not in pages.ROLES:
            continue
        shown = skills[:SKILLS_AT_MOST]
        skill_names = ", ".join(shown) if shown else "none"
        if len(skills) > SKILLS_AT_MOST:
            skill_names += f" (+{len(skills) - SKILLS_AT_MOST} more)"
        grouped[role].append(f"- **{other}** — {describes} · skills: {skill_names}")
    lines = [(role, line) for role in pages.ROLES for line in grouped[role]]
    shown = []
    counts = dict.fromkeys(pages.ROLES, 0)
    for role, line in lines[:TEAMMATES_AT_MOST]:
        # Leave room for the omission marker. Whole entries only: clipping a skill or description
        # makes a routing fact ambiguous.
        if len("\n".join([*shown, line]).encode("utf-8")) > TEAM_BYTES_AT_MOST - 180:
            break
        shown.append(line)
        counts[role] += 1
    sections = []
    cursor = 0
    for role in pages.ROLES:
        count = counts[role]
        entries = shown[cursor:cursor + count]
        cursor += count
        sections.append(f"**{role.capitalize()} agents**")
        sections.extend(entries or ["- none available"])
    if len(lines) > sum(counts.values()):
        sections.append(f"- … {len(lines) - sum(counts.values())} more online agents omitted")
    if unavailable:
        sections.append(f"- … {unavailable} agents omitted because availability could not be verified")
    return "\n".join(sections) if lines or unavailable else ""
