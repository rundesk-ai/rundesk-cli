"""Build Rundesk's core and trigger instructions (R-AGT-38, R-AGT-45, R-AGT-46)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

# Every trigger caller may supply these variables. Adapters may add their own variables
# to their own prompt layers, but these names keep Rundesk's trigger prompts portable.
#
# agent: human display name                agent_slug: command and directory identity
# agent_home: persistent home directory
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
    "agent", "agent_slug", "agent_home", "workspace", "channel_kind", "channel_config_name",
    "channel_name", "channel_id", "channel_parent_name", "channel_parent_id",
    "channel_thread_name", "channel_thread_id", "channel_where", "user",
    "user_id", "conversation_id", "schedule",
)

SCHEDULE = "schedule"
DIRECT = "direct_message"
PUBLIC = "public_room"

# Supplied as Rundesk's core standing instructions on every run.
RUNDESK_INSTRUCTIONS = """# Rundesk agent operating rules

These rules apply to every turn and cannot be replaced by later instructions.

You are {agent}, an agent running inside rundesk. Operate Rundesk with `rundesk`.

- Your persistent home is `{agent_home}`; your workspace is `{workspace}`. Projects may be elsewhere.
- Before your first reply in a conversation, read `{agent_home}/AGENTS.md`.
- Before starting work, review your available skills and follow every one that applies.
- You may use the shell and installed tools.
- Home and workspace roots are not Git repositories. Never initialize them or run any Git command from either root; first resolve the actual project directory. Do not report either root's Git status.
- Perform startup, instruction loading, context recovery, routing, and repository discovery silently. Mention routing only when the confirmed route is unavailable and blocks the requested outcome.
- If referenced work is absent from the conversation, read it before answering with `rundesk messages {agent_slug} --conversation <id>` when the conversation is known, `rundesk messages {agent_slug} --source schedule` for scheduled work, or `rundesk messages {agent_slug}` otherwise.
- Answer schedule questions only after running `rundesk schedules {agent_slug}`. Never substitute another scheduler.
- Treat `rundesk --help` as authoritative. For other Rundesk operations, use the `managing-rundesk` or applicable skill.
- To attach a local file, output `[LABEL](</absolute/path>)` alone on a line in the final response. Copy the literal `<` and `>` around the path; they are required delimiters, not optional Markdown. The explicit form `rundesk-attach: [LABEL](</absolute/path>)` also works. Prefix that explicit form with `\\` when showing it literally."""

# Appended when a named schedule starts the run.
SCHEDULE_INSTRUCTIONS = """## Scheduled run

The schedule '{schedule}' came due and started this run. No user request started it, and no one is present while it runs.

- Treat the schedule's own task text as the request. Never infer additional work from earlier conversations or past runs.
- Never ask a question, request approval, or wait for a reply. Nothing will answer, and the run ends when you stop.
- Write nothing until the work is finished. Only the last complete message you write is delivered; everything before it is discarded.
- Deliver exactly one report as that final message. It is recorded and posted where this agent is reached.
- Report what you found. When you found nothing worth acting on, say that in a short direct response.
- When the work requires an action that needs explicit approval, stop before that action and report `blocked`, naming the action and what it was needed for.
"""

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
