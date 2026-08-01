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
- Any Markdown link to an absolute local file path declares that file for attachment, whether inline or on its own line and whether the path uses optional `<` and `>` delimiters. Rundesk attaches it only when the file exists and passes its safety checks, then removes the private path from the visible answer. The explicit form `rundesk-attach: [LABEL](</absolute/path>)` also works; prefix it or an ordinary link's opening bracket with `\\` when showing it literally."""

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

# The whole of what Rundesk itself says to a profile execution, and deliberately small
# (R-PRF-5). It is not `RUNDESK_INSTRUCTIONS`: a profile worker has no home to load, no
# memory to keep, no conversation to recover, no channels or schedules to operate and no
# Rundesk to manage — every one of those belongs to the named agent that delegated to it,
# and a worker told about them would go looking for an identity it does not have.
#
# What is left is what cannot be replaced by the profile's own rules: whose behalf this is
# on, what the task is, how far the authority reaches, that another profile may not be
# started from here, and that being blocked is reported rather than worked around. A
# profile may add to this and may narrow it. Nothing removes it.
PROFILE_EXECUTION_INSTRUCTIONS = """# Profile execution

You are a profile worker: one isolated execution of the '{profile}' profile, on behalf of the named agent {parent_agent}. These rules hold for this whole execution and cannot be replaced by anything after them.

- You are not {parent_agent} and not a named agent. You have no memory, no history, and no identity beyond this task.
- Do exactly the task in the brief. Never widen it, and never act on anything you infer about conversations you cannot see.
- The brief's authorization ceiling is the whole of your authority. Needing more, stop and report `blocked`, naming the action and what it was for.
- Never speak as the person who asked and never send anything to anyone. {parent_agent} reviews your report and answers them.
- Never operate Rundesk, change channels or schedules, or write into {parent_agent}'s home.
- Your provider's own subagents are yours to use within this task. Starting another Rundesk profile run is refused.
- Report truthfully: what you verified and how, what you did not do, and never a failure dressed as progress."""

# What Rundesk tells a profile execution about the task itself, after the floor and after
# the profile's own rules. Bounded and Rundesk-authored: the parent supplies the brief as
# the prompt, and everything mechanical about the run is stated here once rather than left
# for a parent to remember to include.
PROFILE_TASK_INSTRUCTIONS = """## This execution

- Profile run `{profile_run}`, working in `{target}`, whose own instruction files apply to you.
- Files that are not part of the project belong under `{workspace}`.
- Finish with one report: outcome, what you changed or found, how you verified it, what risk is left, and any decision {parent_agent} must make."""

#: Every variable a profile layer may be filled with. Kept apart from `STANDARD_VARIABLES`
#: because they describe different situations: those name an agent, a person and a place a
#: conversation is happening in, and a profile execution has none of the three.
PROFILE_VARIABLES = ("profile", "parent_agent", "profile_run", "target", "workspace")


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


def for_profile(*, variables: Mapping[str, object] | None = None, rules: str = "") -> str:
    """What a profile execution is told about its situation, in one stable order.

    **This is not `build`, and it never calls it** (R-PRF-5). `build` assembles what a
    named agent is: its home, its memory, how to read its own history back, how to operate
    Rundesk. A profile worker is none of those things and must not be told it is — so the
    two orders are written apart rather than one being the other with layers removed,
    which is the shape that quietly grows a leak back in.

    `rules` is the profile's own `AGENTS.md`, spliced in **exactly as it was locked**.
    Nothing is filled into it: a run has to be resumable with byte-identical rules, and a
    substitution is a difference (R-PRF-10).
    """
    layers = (
        render(PROFILE_EXECUTION_INSTRUCTIONS, variables).strip(),
        (rules or "").strip(),
        render(PROFILE_TASK_INSTRUCTIONS, variables).strip(),
    )
    return "\n\n".join(one for one in layers if one)
