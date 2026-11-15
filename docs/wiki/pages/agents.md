+++
title = "Agents"
subtitle = "the home an agent works in, the records it holds, and making or removing one"
status = "draft"
intent = """
An agent exists so that a coding CLI has a name, a place of its own and a memory that outlives any one
session. Making one and taking one away should each be a single command, and a command that fails partway
should leave no half-built agent behind.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Commands", value = "rundesk agents list, add, configure, remove", cite = "commands" },
  { label = "Home", value = "home", cite = "home" },
]

[[infobox]]
group = "Values"
rows = [
  { label = "Description limit", value = "200 characters", cite = "naming" },
  { label = "Work areas", value = "plans, research, scripts, retros, tasks", cite = "home" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "Two names differing only in case", value = "refused", cite = "naming" },
  { label = "Removal", value = "needs --confirm", cite = "commands" },
  { label = "An agent's own edits", value = "survive an update", cite = "home" },
]
+++

An agent is a named place on the machine that a coding CLI works in and remembers.[^what] Four verbs make
one, change it, list them and take one away.[^commands] The process that keeps an agent answering when no
terminal is open is its [gateway](gateways.md).

## Home

`home/` is where the agent starts every turn, so a file it writes without saying where lands
there.[^turncwd] Rundesk CLI puts a set of pages in it: the rules the agent reads under two names its
providers each recognize, a memory file, and five work areas — plans, research, scripts, retros and
tasks.[^home]

**Placing fills what is absent and overwrites nothing**, so an agent's own edits, and the owner's, survive
every update.[^home] Adopting a team replaces those pages.[^team]

## Records

An agent remembers its own work and no other agent's: what it was asked and answered, the schedules it
runs, the channels it is reachable on, every turn it has taken and what each one cost, and the work it
handed to other agents.[^tables] Past conversations are searchable by their words.[^tables]

Those records are carried forward as Rundesk CLI changes, and each agent is carried on its own, so one
agent that cannot be moved never blocks the others.[^steps]

## Creation

`rundesk agents add <agent> --provider <provider>` builds the agent under a temporary name and only
renames it into place once everything succeeded, so a failure part-way leaves nothing behind.[^made]

A name is checked before the directory is built.[^naming] Two names that differ only in capital letters
are refused, because a person typing either would expect the same agent.[^naming] A description runs to
200 characters.[^naming]

## Removal

`rundesk agents remove <agent> --confirm` takes away everything the agent holds — its records, its home,
its logs, its schedules, its channels and its conversations — one named thing at a time, and removes the
directory only once it is empty.[^forgotten] It does not stop a running gateway first; that is
`rundesk gateways stop`.[^forgotten]

## Delegation scope

`rundesk agents configure` sets which agents this one may hand work to: any agent, no agent, or an exact
list.[^scope] What happens to work handed over is described on [delegation](asking/delegation.md).

[^what]: `src/rundesk/agents/directory.py` — `known()` lists a directory only when it holds the records
    file, and `not_an_agent()` reports one that does not.
[^commands]: `src/rundesk/commands/agents.py` — `register()` declares `list`, `add`, `configure` and
    `remove`, and makes `--confirm` the guard on `remove`.
[^home]: `src/rundesk/agents/pages.py` — `PAGES` names the placed pages, `CONTINUITY` places the rules
    file under both names from one source, `AREAS` names the five work areas, and `place()` fills
    absences without overwriting.
[^team]: `src/rundesk/agents/pages.py` — `replace_team()`.
[^turncwd]: `src/rundesk/providers/adapters.py` — `talking_to()` starts the adapter with the agent's home
    as its working directory.
[^tables]: `src/rundesk/agents/steps/0002_the_schedules_an_agent_keeps.py`,
    `0003_the_channels_an_agent_keeps.py`, `0004_the_turns_an_agent_takes.py` and
    `0005_the_work_an_agent_delegates.py` — the schedules, the channels and conversations, the turns and
    the full-text index over message bodies, and the delegations.
[^steps]: `src/rundesk/agents/migration.py` — `carry_every()` carries each agent on its own;
    `src/rundesk/agents/steps/__init__.py` — the rules a step keeps, and the fourteen shipped steps.
[^made]: `src/rundesk/agents/directory.py` — `made()` takes the install claim, and `_built()` stages the
    directory under a temporary name, carries it, writes its configuration and renames it into place,
    discarding the staging on any failure.
[^naming]: `src/rundesk/agents/directory.py` — `name_trouble()`, `taken()`, which refuses a name colliding
    in ASCII case, and `DESCRIBES_AT_MOST`.
[^forgotten]: `src/rundesk/agents/directory.py` — `_forgotten()` removes each named thing and then the
    directory only when empty, and its docstring leaves a running gateway to the caller.
[^scope]: `src/rundesk/agents/delegating.py` — `decoded()` reads the three states and `allows()` decides
    one target.
