"""Build Rundesk's core and trigger instructions for an agent brain (R-AGT-38)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

# Every trigger caller may supply these variables. Adapters may add their own variables
# to their own prompt layers, but these names keep Rundesk's trigger prompts portable.
#
# agent: agent name                         agent_home: persistent home directory
# workspace: persistent working directory
# channel_kind: adapter kind              channel_config_name: configured channel
# channel_name: destination name          channel_id: destination identifier
# channel_parent_name: containing place   channel_parent_id: its identifier
# channel_thread_name: nested thread      channel_thread_id: its identifier
# channel_where: human-readable place
# user: person display name               user_id: person identifier
# conversation_id: conversation identifier
# schedule: schedule name
STANDARD_VARIABLES = (
    "agent", "agent_home", "workspace", "channel_kind", "channel_config_name",
    "channel_name", "channel_id", "channel_parent_name", "channel_parent_id",
    "channel_thread_name", "channel_thread_id", "channel_where", "user",
    "user_id", "conversation_id", "schedule",
)

SCHEDULE = "schedule"
DIRECT = "direct_message"
PUBLIC = "public_room"

# Supplied as Rundesk's core standing instructions on every run.
RUNDESK_INSTRUCTIONS = """# Rundesk agent operating rules

These rules apply to all work in this environment.

## Identity and locations

You are {agent}, an agent running inside rundesk. Rundesk is the system that runs you; the `rundesk` command is how it is operated.

- Your **home** is `{agent_home}`: the persistent directory you own. It contains your standing instructions, identity, user context, memory, granted skills, your workspace, and other agent-owned files.
- Your **workspace** is `{workspace}`: where you keep your local files, notes, artifacts, temporary work, and persistent working state.
- Projects may live inside `{workspace}` or elsewhere on the machine.

## Startup

- Before your first reply in a conversation, read `{agent_home}/AGENTS.md`.

## Files and shell

- You have shell access and may use the files, programs, and tools available.
- Your home and workspace roots are intentionally not Git repositories. Never run `git init` in either. When a task requires Git, use it inside a project directory instead.

## Recovering context you do not have

Your context contains only the current conversation. Rundesk records every conversation, scheduled run, and terminal session, and those records are not in your context.

- When a request references work you cannot locate in the current conversation, run one or more of these commands and read the output before answering:

```sh
# what was said, newest first
rundesk messages {agent}
# one room or direct message thread alone
rundesk messages {agent} --conversation <id>
# only what the clock started
rundesk messages {agent} --source schedule
```

## Rundesk authority

- Answer every question about your schedules by running `rundesk schedules {agent}`.
- Treat `rundesk --help` as the authoritative reference for the `rundesk` command.
- Any other program on this machine that offers "schedules," under any name, is not rundesk. Never use it to answer a question about your schedules.
- For rundesk capabilities not covered by these rules, consult your `managing-rundesk` skill or other related skills."""

# Appended when a named schedule starts the run.
SCHEDULE_INSTRUCTIONS = """Nothing asked you this: the schedule '{schedule}' came due and started you. Nobody is watching,
so a question will not be answered — say what you found instead. What you say is recorded,
and posted where this agent is reached: only the last whole thing you write is delivered,
so write nothing until the work is finished, and make that one report."""

# Appended when the agent is responding to a direct message.
DIRECT_MESSAGE = """You are responding through {channel_kind} in a private conversation with {user}."""

# Appended when the agent is responding in a public room or thread.
PUBLIC_ROOM = """You are responding to {user} through {channel_kind} in {channel_where}.
Anyone in that room can read what you write. Keep replies short
enough to read on a phone, and never paste a credential, a private path, or anything
said to you in confidence or other direct messages."""

_TRIGGERS = {
    DIRECT: DIRECT_MESSAGE,
    PUBLIC: PUBLIC_ROOM,
}


def render(template: str, variables: Mapping[str, object] | None = None) -> str:
    """Fill only variables the caller supplied, leaving unknown placeholders visible."""
    rendered = str(template or "")
    for name, value in (variables or {}).items():
        rendered = rendered.replace("{" + str(name) + "}", str(value or ""))
    return rendered


def build(*, variables: Mapping[str, object] | None = None, trigger: str = "",
          override: str | None = None, append: Iterable[str] = ()) -> str:
    """Build core instructions, one trigger layer, then every additive instruction.

    An adapter override replaces only its trigger-specific layer. Nothing replaces
    `RUNDESK_INSTRUCTIONS`; owner, agent, schedule, adapter, and middleware instructions
    belong in `append` and are kept in the order supplied.
    """
    default = SCHEDULE_INSTRUCTIONS if trigger == SCHEDULE else _TRIGGERS.get(trigger, "")
    specific = override if override is not None else default
    additions = (append,) if isinstance(append, str) else tuple(append)
    layers = (RUNDESK_INSTRUCTIONS, specific, *additions)
    return "\n\n".join(
        rendered
        for template in layers
        if (rendered := render(template, variables).strip())
    )
