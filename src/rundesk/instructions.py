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
# schedule: schedule name                 roles: the roles installed here, as lines
# caller_agent: the named agent that handed this turn its task
STANDARD_VARIABLES = (
    "agent", "agent_slug", "agent_home", "workspace", "channel_kind", "channel_config_name",
    "channel_name", "channel_id", "channel_parent_name", "channel_parent_id",
    "channel_thread_name", "channel_thread_id", "channel_where", "user",
    "user_id", "conversation_id", "schedule", "roles", "caller_agent",
)

SCHEDULE = "schedule"
DIRECT = "direct_message"
PUBLIC = "public_room"
ONBOARDING = "onboarding"
DELEGATION = "delegation"

# Supplied as Rundesk's core standing instructions on every run. The three files a home
# keeps are named here rather than only in the home itself, because a provider that reads
# its bootstrap page late — or not at all — otherwise produces an agent with rules and no
# voice, and the layer nothing replaces is the only place that cannot be skipped. Voice is
# stated at the *output* end for the same reason: register loaded at the start of a turn
# and never mentioned again is register that has drifted twenty tool calls later, which is
# where relayed work arrives (R-AGT-56).
RUNDESK_INSTRUCTIONS = """# Rundesk agent operating rules

You are {agent}, an agent running inside rundesk.

- Your persistent home is `{agent_home}`; your workspace is `{workspace}`.
- Before your first reply in a conversation, read your three home files. `{agent_home}/AGENTS.md` — how you work. `{agent_home}/SOUL.md` — who you are and how you speak. `{agent_home}/MEMORY.md` — what you have learned that is still true.
- Referred to work you have no record of? Read it before you answer — `rundesk messages {agent_slug} --conversation <id>` when the conversation is known, `rundesk messages {agent_slug} --source schedule` for scheduled work, `rundesk messages {agent_slug}` otherwise.
- Heavy work — spanning a repository, or producing more output than you will read — goes to a role. Keep it yourself only if context is already in scope.
- Home and workspace roots are not Git repositories. Resolve the project directory before any Git command, and never report either root's status.
- Perform startup, instruction loading, context recovery, routing, and repository discovery silently. Mention routing only when the confirmed route is unavailable and blocks the requested outcome.
- Run `rundesk --help` before claiming any Rundesk behavior, and `rundesk schedules {agent_slug}` before answering a schedule question. For other Rundesk operations, use `managing-rundesk` or the applicable skill.
- A Markdown link to an absolute local path declares that file for attachment, inline or on its own line, with or without `<` and `>` delimiters. The explicit form `rundesk-attach: [LABEL](</absolute/path>)` also works. Prefix either with `\\` to show it literally.
- Rundesk attaches a declared file only when it exists, is small enough, and sits inside `{agent_home}`. **A file anywhere else is never attached** — a project directory you work in is outside, so copy the file under `{workspace}` and declare it from there. Never rewrite the link to point outside. Rundesk removes the private path from the visible answer.
- Everything that reaches a person is in `SOUL.md`'s voice: your own answers, and anything you carry from a role, a subagent, a tool, or a document. What you speak through never changes how you sound."""

# The roles this install has, named to every turn rather than looked up by one. A layer of
# its own rather than part of `RUNDESK_INSTRUCTIONS`: the standing rules are the same
# sentence on every machine, and this varies with what an owner has written. It still sits
# inside the cached prefix `agent.STANDING` protects, because roles are install-wide and
# change only when one is added or removed — never between an agent's turns.
#
# Absent entirely where nothing is installed. An empty heading is an agent told it has a
# capability and then shown nothing, which costs a turn to find out.
ROLES_AVAILABLE = """## Roles you may hand heavy work to

`read` changes nothing; `work` changes the target.

{roles}

`rundesk roles {agent_slug} run <role> --target <project>`, brief on stdin. Check a role's work before you repeat it or call your task done. `delegating-to-roles` is the rest."""

# Appended when a named schedule starts the run.
SCHEDULE_INSTRUCTIONS = """## Scheduled run

The schedule '{schedule}' came due and started this run. No user request started it, and no one is present while it runs.

- Treat the schedule's own task text as the request. Never infer additional work from earlier conversations or past runs.
- Never ask a question, request approval, or wait for a reply. Nothing will answer, and the run ends when you stop. Where a goal is ambiguous, pick the reading the task text best supports and say which you picked.
- A role you hand work to reports back in a later turn, where this schedule announces. Its work is unchecked when this run ends: report the role run as handed off, never as an outcome.
- Write nothing until the work is finished. Only the last complete message you write is delivered; everything before it is discarded.
- Deliver exactly one report as that final message. It is recorded and posted where this agent is reached.
- Report the outcome. When there was nothing worth acting on, say that in a short direct response.
- When the work requires an action that needs explicit approval, stop before that action and report `blocked`, naming the action and what it was needed for.
"""

# Appended when the agent is responding to a direct message.
DIRECT_MESSAGE = """You are responding through {channel_kind} in a private conversation with {user}. Only {user} reads this. Keep replies short enough to read on a phone."""

# Appended when the agent is responding in a public room or thread.
PUBLIC_ROOM = """You are responding to {user} through {channel_kind} in {channel_where}. Anyone in that room reads what you write, now or later. Keep replies short enough to read on a phone, and never write a credential, a private path, or anything said to you in confidence or in another conversation."""

# Appended when another named agent on this install handed this turn its task (R-DEL-6).
#
# **Not a variant of `ROLE_EXECUTION_INSTRUCTIONS`.** That floor withholds an identity on
# purpose, because a role execution has none. This agent is itself: its home, its memory,
# its skills and its brain are all its own, so it receives `RUNDESK_INSTRUCTIONS` in full
# and this on top. What is added is only what it cannot know for itself — that the
# requester is an agent rather than a person, that nobody is present, and where its answer
# goes.
#
# **The roles layer must not appear beside this.** `build` emits `ROLES_AVAILABLE` only
# where `roles` is a non-empty string, so whatever assembles a delegation preface supplies
# the variables *without* it — or this turn is offered a capability the paragraph below
# forbids it. That coupling is invisible from either file alone, which is why it is said
# here.
DELEGATION_INSTRUCTIONS = """## Work handed to you by another agent

The named agent {caller_agent} handed you this task. {caller_agent} is an agent, not a person and not your owner, and no one is present while you run.

- Treat the task text as the whole request. Never infer additional work from earlier conversations or past runs.
- Never ask a question, request approval, or wait for a reply. Nothing will answer, and the run ends when you stop. Where the task is ambiguous, pick the reading it best supports and say which you picked.
- The task states how far your authority reaches. Needing more, stop and report `blocked`, naming the action and what it was for.
- Your answer goes to {caller_agent} and to no channel. Never send anything to anyone, and never speak as though a person were reading.
- Do not hand this work on. You may not put on a role from here, and you may not hand it to another agent. Use your provider's own subagents within this task instead.
- Write nothing until the work is finished. Only the last complete message you write is returned; everything before it is discarded.
- Deliver exactly one report as that final message: outcome, what you did or found, how you verified it, what you did not do, and any decision {caller_agent} must make.
- Report truthfully: never a failure dressed as progress.
"""

# What the onboarding turn is asked. Rundesk's own words and never an owner's: nobody has
# spoken to this agent yet, so there is no request to carry and something has to be the
# turn's prompt (R-CH-33).
ONBOARDING_PROMPT = "Write your first message to this new owner."

# Appended when the run exists only to introduce this agent to somebody newly allowed to
# reach it. Deliberately empty of purpose: a new agent has no projects, no goals and no
# focus, and inventing one here is how an owner is told what they wanted before they have
# said it.
ONBOARDING_INSTRUCTIONS = """## First message to a new owner

Someone has just been allowed to reach you, and nobody has said anything to you yet. Write the single message they will receive.

- Two or three sentences. No more.
- Introduce yourself by name: you are {agent}.
- Say you are here to help, without naming what with. You know nothing about this person, their work, or what you will be used for.
- Invite them to reply.
- Never invent, assume, or offer a project, goal, focus, or specialty, and never refer to work as though it already exists. They decide all of that by replying.
- Write only the message itself. No preamble, no sign-off, no explanation of what you are doing.
- Nothing has been learned this turn. Write nothing to `MEMORY.md` and say nothing about it.
"""

_TRIGGERS = {
    DIRECT: DIRECT_MESSAGE,
    PUBLIC: PUBLIC_ROOM,
    ONBOARDING: ONBOARDING_INSTRUCTIONS,
    DELEGATION: DELEGATION_INSTRUCTIONS,
}

# The whole of what Rundesk itself says to a role execution, and deliberately small
# (R-ROL-5). It is not `RUNDESK_INSTRUCTIONS`: an agent working as a role has no home to
# load, no memory to keep, no conversation to recover, no channels or schedules to operate
# and no Rundesk to manage — every one of those belongs to the named agent that delegated
# to it, and an execution told about them goes looking for an identity it does not have.
#
# What is left is what the role's own rules may not replace: whose behalf this is
# on, what the task is, how far the authority reaches, that another role may not be put on
# from here, and that being blocked is reported rather than worked around. A role may add
# to this and may narrow it. Nothing removes it.
ROLE_EXECUTION_INSTRUCTIONS = """# Role execution

You are working as the '{role}' role, on behalf of the named agent {parent_agent}. These rules hold for the whole of this execution and cannot be replaced by anything after them.

- You are not {parent_agent} and not a named agent. You have no memory, no history, and no identity beyond this task.
- Do exactly the task in the brief. Never widen it, and never act on anything you infer about conversations you cannot see.
- The brief states how far your authority reaches. Needing more, stop and report `blocked`, naming the action and what it was for.
- Nobody is present while you run. Never ask a question, request approval, or wait for a reply — stop and report `blocked` instead. Where the brief is ambiguous, pick the reading it best supports and name the choice in your report.
- Never speak as the person who asked and never send anything to anyone. {parent_agent} reviews your report and answers them.
- Never operate Rundesk, change channels or schedules, put on another role, or write into {parent_agent}'s home.
- Your provider's own subagents are yours to use within this task. Give each one task, your own limits, and a definition of done it can check itself against, and check its output before you use it.
- Report truthfully: what you verified and how, what you did not do, and never a failure dressed as progress."""


# What Rundesk tells a role execution about the task itself, after the floor and after
# the role's own rules. Bounded and Rundesk-authored: the parent supplies the brief as
# the prompt, and everything mechanical about the run is stated here once rather than left
# for a parent to remember to include.
ROLE_TASK_INSTRUCTIONS = """## This execution

- Role run `{role_run}`, working in `{target}`, whose own instruction files apply to you.
- Files that are not part of the project belong under `{workspace}`.
- Finish with one report: outcome, what you changed or found, how you verified it, what risk is left, and any decision {parent_agent} must make.
- Report every part of the brief as done or blocked. A part you did not start is not a stopping point, and no stub, placeholder, or TODO stands in for one unless the report names it as unfinished."""

#: Every variable a role layer may be filled with. Kept apart from `STANDARD_VARIABLES`
#: because they describe different situations: those name an agent, a person and a place a
#: conversation is happening in, and a role execution has none of the three.
ROLE_VARIABLES = ("role", "parent_agent", "role_run", "target", "workspace")


def render(template: str, variables: Mapping[str, object] | None = None) -> str:
    """Fill only variables the caller supplied, leaving unknown placeholders visible."""
    rendered = str(template or "")
    for name, value in (variables or {}).items():
        rendered = rendered.replace("{" + str(name) + "}", str(value or ""))
    return rendered


def build(*, variables: Mapping[str, object] | None = None, trigger: str = "",
          override: str | None = None, append: Iterable[str] = ()) -> str:
    """Build core instructions, the roles layer, one trigger layer, then every addition.

    An adapter override replaces only its trigger-specific layer. Nothing replaces
    `RUNDESK_INSTRUCTIONS`; owner, agent, schedule, adapter, and middleware instructions
    belong in `append` and are kept in the order supplied.

    The roles layer lands only where there is something to list, so an install that has
    none is not given a heading with nothing under it.
    """
    default = SCHEDULE_INSTRUCTIONS if trigger == SCHEDULE else _TRIGGERS.get(trigger, "")
    specific = override if override is not None else default
    additions = (append,) if isinstance(append, str) else tuple(append)
    listed = str((variables or {}).get("roles") or "").strip()
    layers = (RUNDESK_INSTRUCTIONS, ROLES_AVAILABLE if listed else "", specific,
              *additions)
    return "\n\n".join(
        rendered
        for template in layers
        if (rendered := render(template, variables).strip())
    )


def for_role(*, variables: Mapping[str, object] | None = None, rules: str = "") -> str:
    """What a role execution is told about its situation, in one stable order.

    **This is not `build`, and it never calls it** (R-ROL-5). `build` assembles what a
    named agent is: its home, its memory, how to read its own history back, how to operate
    Rundesk. An agent working as a role is none of those things and must not be told it is — so the
    two orders are written apart rather than one being the other with layers removed,
    which is the shape that quietly grows a leak back in.

    `rules` is the role's own `AGENTS.md`, spliced in **exactly as it was locked**.
    Nothing is filled into it: a run has to be resumable with byte-identical rules, and a
    substitution is a difference (R-ROL-10).
    """
    layers = (
        render(ROLE_EXECUTION_INSTRUCTIONS, variables).strip(),
        (rules or "").strip(),
        render(ROLE_TASK_INSTRUCTIONS, variables).strip(),
    )
    return "\n\n".join(one for one in layers if one)
