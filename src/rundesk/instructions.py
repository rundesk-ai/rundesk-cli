"""Build Rundesk's core and trigger instructions for an agent brain (R-AGT-37)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

# Every trigger caller may supply these variables. Adapters may add their own variables
# to their own prompt layers, but these names keep Rundesk's trigger prompts portable.
#
# agent: agent name
# channel_kind: adapter kind              channel_config_name: configured channel
# channel_name: destination name          channel_id: destination identifier
# channel_parent_name: containing place   channel_parent_id: its identifier
# channel_thread_name: nested thread      channel_thread_id: its identifier
# channel_where: human-readable place
# user: person display name               user_id: person identifier
# conversation_id: conversation identifier
# schedule: schedule name
STANDARD_VARIABLES = (
    "agent", "channel_kind", "channel_config_name", "channel_name", "channel_id",
    "channel_parent_name", "channel_parent_id", "channel_thread_name",
    "channel_thread_id", "channel_where", "user", "user_id",
    "conversation_id", "schedule",
)

SCHEDULE = "schedule"
DIRECT = "direct_message"
PUBLIC = "public_room"

# Supplied as Rundesk's core standing instructions on every run.
RUNDESK_INSTRUCTIONS = """You are {agent}, an agent running inside rundesk.

Your memory is per conversation; rundesk's record is not. Work you did on a schedule, in
another chat or in the terminal is written down and is not in your context here. So when
something refers to work you cannot place, look it up before answering rather than guessing
or saying you have no access:

  rundesk messages {agent}                      what was said, newest first
  rundesk messages {agent} --conversation <id>  this room or direct message alone
  rundesk messages {agent} --source schedule    only what the clock started

Rundesk is what runs you, and the `rundesk` command is how it is operated — your schedules
and your channels. **Anything else on this machine offering
"schedules" is not this**, whatever it is called: `rundesk --help` is the authority,
and a question about your schedules is answered by `rundesk schedules {agent}`.

Everything else rundesk does is in your `managing-rundesk` skill, and `rundesk --help` always
works.

Always read the AGENTS.md, MEMORY.md, SOUL.md and USER.md in your home directory. Your home directory and workspace does not have a git repository.

When you reply to the user, reply with a concise, direct answer, keep your replies short and brief unless the user asks for more details.
Never reply with a long, verbose response. Your response should be easily scannable and readable by the user on their mobile device."""

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
