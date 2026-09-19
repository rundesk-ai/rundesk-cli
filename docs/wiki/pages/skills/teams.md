+++
title = "Teams"
subtitle = "a catalog's declaration of several agents, and what reconciling one changes"
status = "draft"
intent = """
A team exists so that several agents with their own instructions, descriptions and skills are installed
and moved forward together, from one declaration a person reviews. Installing a team should never adopt an
agent the owner already made, and a failed update should leave every member as it was.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Commands", value = "rundesk teams list, install, update", cite = "commands" },
  { label = "Declaration", value = "team.json", cite = "declared" },
  { label = "Member instructions", value = "AGENTS.md", cite = "member" },
]

[[infobox]]
group = "Values"
rows = [
  { label = "Declaration version", value = "2, and 1 still read", cite = "declared" },
  { label = "Member keys", value = "6", cite = "member" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "An executable hook in the repository", value = "never accepted", cite = "declared" },
  { label = "An agent another team owns", value = "refused", cite = "preflight" },
  { label = "A failed update", value = "every member put back", cite = "rollback" },
]
+++

A team is a `team.json` inside a [skill catalog](../skills.md) naming several agents and what each one
is.[^declared] Installing it makes those [agents](../agents.md) and grants each the skills the
declaration names.[^apply] Three verbs list the installed teams, install one and update it.[^commands]

## Declaration

Only the exact envelope is recognized, so an ordinary catalog carrying its own `team.json` is not treated
as a team.[^declared] Version 2 names the catalogs a member may draw skills from; version 1 is still
read.[^declared] A declaration whose name does not match the catalog's manifest is refused, and the whole
declaration is refused at once rather than one fault at a time.[^declared]

The repository is data, and no executable hook is accepted from it.[^declared]

## Members

A member gives exactly six things: its name, its description, its instructions, its skills, the agents it
may delegate to, and whether it improves itself.[^member] Each is checked before the first agent is
made.[^member]

| Given | Refused when |
|---|---|
| name | it is not a name an agent may have[^member] |
| description | it is longer than an agent's description may be[^member] |
| instructions | the path is absolute, climbs out of the tree, or is not named `AGENTS.md`[^member] |
| skills | a skill the team's own catalog does not hold, a duplicate, or two skills that would install under one name[^member] |
| skills | `managing-rundesk` or `delegating-work`, which the product grants itself[^member] |
| delegates to | the list repeats a name[^member] |

## Reconciling

Installing refuses unless every member is a brand-new agent, so a team never adopts an agent the owner
already made.[^preflight] Updating refuses an agent another team owns, and refuses when a grant made by
hand occupies a name the team needs.[^preflight]

Reconciling a member replaces its `AGENTS.md` and `CLAUDE.md`, removes its `MEMORY.md`, sets its
description, delegation scope and self-improvement, then revokes what this team declared before and no
longer declares, and grants what it declares and the agent lacks.[^apply]

The comparison is against the **previous declaration**, never against whatever the agent holds, so a skill
an owner granted by hand survives the next update.[^apply] A managed member is repaired again just before
a turn is admitted.[^current]

## Rollback

An update snapshots each member's three pages, its three settings and its grants, and puts them back when
any part of the run raises.[^rollback]

[^commands]: `src/rundesk/commands/teams.py` — `register()` declares `list`, `install` and `update`.
[^declared]: `src/rundesk/teams/catalogs.py` — `declared()` recognizes only the exact envelope, `SCHEMA`
    and `LEGACY_SCHEMA` are the two versions read, `read()` refuses the whole declaration at once
    including a name that does not match the manifest, and the module docstring states the repository is
    untrusted data and no executable hook is accepted.
[^member]: `src/rundesk/teams/catalogs.py` — `_member()` reads the six keys and raises for each refusal
    above; `AGENTS` and `INSTRUCTIONS` fix the folder and file a member's instructions come from.
[^preflight]: `src/rundesk/teams/reconcile.py` — `preflight()` refuses an agent another team owns,
    `preflight_install()` requires every member to be new, and `preflight_grants()` refuses a
    user-managed grant standing in a name the team needs.
[^apply]: `src/rundesk/teams/reconcile.py` — `apply()` makes the missing agents and reconciles each,
    `_member()` replaces the pages and settings and then revokes and grants, `retiring()` answers what the
    previous declaration held, and the module docstring states the comparison is against that declaration.
[^current]: `src/rundesk/teams/reconcile.py` — `current()`, called by `_admit()` in
    `src/rundesk/providers/turns.py`.
[^rollback]: `src/rundesk/teams/restoring.py` — `kept()` snapshots `PAGES`, `COLUMNS` and the member's
    grants, and puts them back when the run raises.
