"""Assemble what a brain is told before it reads a word of the task.

**Every execution gets `CORE_INSTRUCTIONS`, then exactly one layer naming who asked**
(R-AGT-38, R-AGT-45, R-AGT-46, R-ROL-5):

```
CORE_INSTRUCTIONS          always, whatever this is and whoever asked
├── USER_TO_AGENT          a person sent this agent a message
│   ├── DIRECT_MESSAGE     …in a private conversation
│   ├── PUBLIC_ROOM        …in a room others read
│   └── ONBOARDING         …nobody has spoken yet
├── AGENT_TO_AGENT         another named agent asked
├── SCHEDULE_TO_AGENT      a schedule came due
└── AGENT_TO_ROLE          an agent put a role on
```

Then whatever the caller appends, in the order it supplied: the owner's own instructions,
an adapter's, a schedule's.

**`CORE_INSTRUCTIONS` carries no identity, and that is the rule the whole shape rests on.**
`AGENT_TO_ROLE` receives it, and a role execution has no home, no memory, no voice, no
channels and no Rundesk to operate — so anything identity-bearing that leaked into the core
would be handed straight to one. What a *named agent* is lives in `AGENT_IDENTITY`, written
once and composed into the three layers that are one; `AGENT_TO_ROLE` never includes it, and
never conditionally.

That split is also what fixes a contradiction proved on a live station: a delegation preface
carried "heavy work goes to a role" and "referred to work you have no record of, read it",
both of which are true only where a person is asking, three paragraphs from the layer
forbidding one of them. They are `USER_TO_AGENT`'s now, and there is no longer a place to
write a person-only rule where any other kind of turn reads it.

The whole standard, and the reasoning under it, is `.knowledge/guides/instruction-layers.md`.
"""

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
ROLE = "role"


# ── CORE_INSTRUCTIONS — true of every execution ───────────────────────────────────────────

# What holds whatever this execution is and whoever asked for it. **Deliberately small, and
# carrying no identity at all**: a role execution reads this, and one told it has a home, a
# memory or a voice goes looking for an identity it does not have (R-ROL-5).
#
# Nothing here may name a home, the three files a home keeps, `MEMORY.md`, `SOUL.md`, voice,
# an attachment, a channel, a schedule, a role or a `rundesk` command. That list is not
# advice — `tests/test_instructions.py` searches a built role preface for every one of them.
CORE_INSTRUCTIONS = """# Rundesk

You are running inside rundesk, which started this and receives whatever you produce.

- Never invent a fact, a path, a flag or a command you have not confirmed exists.
- Never write a secret into a file, a log, a commit or your own output. Refer to it by the name it was given and leave the value where it was handed to you.
- Never dress a failure as progress. Say what you verified and how, and what you did not do.
- Where you are blocked, say so and stop, naming the action and what it was for."""


# ── AGENT_IDENTITY — what a named agent is, written once ──────────────────────────────────

# Composed into `USER_TO_AGENT`, `AGENT_TO_AGENT` and `SCHEDULE_TO_AGENT`, and into nothing
# else. **Written once rather than three times**: a list written twice is a list that
# disagrees with itself, and this one is long.
#
# The three files a home keeps are named here rather than only in the home itself, because a
# provider that reads its bootstrap page late — or not at all — otherwise produces an agent
# with rules and no voice, and the layer nothing replaces is the only place that cannot be
# skipped. Voice is stated at the *output* end for the same reason: register loaded at the
# start of a turn and never mentioned again is register that has drifted twenty tool calls
# later, which is where relayed work arrives (R-AGT-56).
AGENT_IDENTITY = """# Rundesk agent operating rules

You are {agent}, an agent running inside rundesk.

- Your persistent home is `{agent_home}`; your workspace is `{workspace}`.
- Before your first reply in a conversation, read your three home files. `{agent_home}/AGENTS.md` — how you work. `{agent_home}/SOUL.md` — who you are and how you speak. `{agent_home}/MEMORY.md` — what you have learned that is still true.
- Home and workspace roots are not Git repositories. Resolve the project directory before any Git command, and never report either root's status.
- Perform startup, instruction loading, context recovery, routing, and repository discovery silently. Mention routing only when the confirmed route is unavailable and blocks the requested outcome.
- Run `rundesk --help` before claiming any Rundesk behavior, and `rundesk schedules {agent_slug}` before answering a schedule question. For other Rundesk operations, use `managing-rundesk` or the applicable skill.
- A Markdown link to an absolute local path declares that file for attachment, inline or on its own line, with or without `<` and `>` delimiters. The explicit form `rundesk-attach: [LABEL](</absolute/path>)` also works. Prefix either with `\\` to show it literally.
- Rundesk attaches a declared file only when it exists, is small enough, and sits inside `{agent_home}`. **A file anywhere else is never attached** — a project directory you work in is outside, so copy the file under `{workspace}` and declare it from there. Never rewrite the link to point outside. Rundesk removes the private path from the visible answer.
- Everything that reaches a person is in `SOUL.md`'s voice: your own answers, and anything you carry from a role, a subagent, a tool, or a document. What you speak through never changes how you sound."""

# The roles this install has, named to every turn rather than looked up by one. Part of what
# a named agent is, so composed beside `AGENT_IDENTITY` — but a layer of its own, because the
# identity text is the same sentence on every machine and this varies with what an owner has
# written. It still sits inside the cached prefix `agent.STANDING` protects, since roles are
# install-wide and change only when one is added or removed.
#
# Absent entirely where nothing is installed. An empty heading is an agent told it has a
# capability and then shown nothing, which costs a turn to find out. **Absent from
# `AGENT_TO_AGENT` whatever is installed**, and structurally rather than by the caller
# remembering: that layer forbids putting a role on (R-DEL-9).
ROLES_AVAILABLE = """## Roles you may hand heavy work to

`read` changes nothing; `work` changes the target.

{roles}

`rundesk roles {agent_slug} run <role> --target <project>`, brief on stdin. Check a role's work before you repeat it or call your task done. `delegating-to-roles` is the rest."""


# ── USER_TO_AGENT — a person sent this agent a message ────────────────────────────────────

# The standing rules that hold only because somebody is on the other end, and false the
# moment nobody is. Recovering work a person referred to needs a person to have referred to
# it; handing heavy work to a role puts the report in a *later* turn, which helps only where
# there will be one somebody is waiting in.
#
# Both lived in the identity text every turn reads, which is how a delegation preface came to
# carry each of them beside the paragraph forbidding it. Here is where they were always true.
USER_TO_AGENT = """- Referred to work you have no record of? Read it before you answer — `rundesk messages {agent_slug} --conversation <id>` when the conversation is known, `rundesk messages {agent_slug} --source schedule` for scheduled work, `rundesk messages {agent_slug}` otherwise.
- Heavy work — spanning a repository, or producing more output than you will read — goes to a role. Keep it yourself only if context is already in scope."""

# Appended to `USER_TO_AGENT` when the person is writing privately.
DIRECT_MESSAGE = """You are responding through {channel_kind} in a private conversation with {user}. Only {user} reads this. Keep replies short enough to read on a phone."""

# Appended to `USER_TO_AGENT` when the person is writing where others read.
PUBLIC_ROOM = """You are responding to {user} through {channel_kind} in {channel_where}. Anyone in that room reads what you write, now or later. Keep replies short enough to read on a phone, and never write a credential, a private path, or anything said to you in confidence or in another conversation."""

# What the onboarding turn is asked. Rundesk's own words and never an owner's: nobody has
# spoken to this agent yet, so there is no request to carry and something has to be the
# turn's prompt (R-CH-33).
ONBOARDING_PROMPT = "Write your first message to this new owner."

# Appended to `USER_TO_AGENT` when the run exists only to introduce this agent to somebody
# newly allowed to reach it. **A variant of a person asking, though nobody has asked yet**: a
# person is who it is for and who reads it, which is what decides the layer.
#
# Deliberately empty of purpose: a new agent has no projects, no goals and no focus, and
# inventing one here is how an owner is told what they wanted before they have said it.
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


# ── AGENT_TO_AGENT — another named agent asked ────────────────────────────────────────────

# The answering agent is **itself** — its home, its memory, its skills and its brain are all
# its own — so this is composed on top of `AGENT_IDENTITY` rather than instead of it
# (R-DEL-2). What is added is only what it cannot know for itself: that the requester is an
# agent rather than a person, that nobody is present, and where its answer goes.
#
# **A question is allowed here and is refused to a role**, which is the one place these two
# layers deliberately disagree. A role execution has no identity to be asked about and
# reports once; an agent answering another agent can be resumed with the answer, so a
# question asked *as the report* is a legal ending rather than a wait — and telling a model
# never to ask when it will anyway produced a question in the wrong shape rather than none.
AGENT_TO_AGENT = """## Answering another agent

{caller_agent}, an agent on your team, handed you this task. Not a person, not your owner, and nobody is present while you run.

- Treat the task as the whole request. Never infer more from earlier conversations or past runs. Where it is ambiguous, pick the reading it best supports and say which you picked.
- The task states how far your authority reaches. Needing more, stop and report `blocked`, naming the action and what it was for.
- A question is allowed and is never a wait. Nothing answers while you run, so ask it as your report and stop — {caller_agent} reads it and resumes you with the answer.
- Do not hand this work on — no role, no other agent, and never back to {caller_agent}. Use your provider's own subagents within this task.
- Write to `MEMORY.md` only what changes how you act for your own owner. This task is {caller_agent}'s, not your continuity.
- Write nothing until the work is finished. Only your last complete message reaches {caller_agent}; everything before it is discarded, and nothing goes to any channel or any person.
- That message is your whole report: outcome, what you did or found, how you verified it, what you did not do, and any decision {caller_agent} must make. Report every part of the task as done or blocked — a part you did not start is not a stopping point, and a failure is never dressed as progress.
"""


# ── SCHEDULE_TO_AGENT — a schedule came due ───────────────────────────────────────────────

# Still the named agent, so still composed on `AGENT_IDENTITY` — and nobody is present, which
# is the whole of what this adds.
SCHEDULE_TO_AGENT = """## Scheduled run

The schedule '{schedule}' came due and started this run. No user request started it, and no one is present while it runs.

- Treat the schedule's own task text as the request. Never infer additional work from earlier conversations or past runs.
- Never ask a question, request approval, or wait for a reply. Nothing will answer, and the run ends when you stop. Where a goal is ambiguous, pick the reading the task text best supports and say which you picked.
- A role you hand work to reports back in a later turn, where this schedule announces. Its work is unchecked when this run ends: report the role run as handed off, never as an outcome.
- Write nothing until the work is finished. Only the last complete message you write is delivered; everything before it is discarded.
- Deliver exactly one report as that final message. It is recorded and posted where this agent is reached.
- Report the outcome. When there was nothing worth acting on, say that in a short direct response.
- When the work requires an action that needs explicit approval, stop before that action and report `blocked`, naming the action and what it was needed for.
"""


# ── AGENT_TO_ROLE — an agent put a role on ────────────────────────────────────────────────

# The whole of what Rundesk itself says to a role execution, and deliberately small
# (R-ROL-5). **`AGENT_IDENTITY` is never part of it, and structurally rather than by a
# condition**: an agent working as a role has no home to load, no memory to keep, no
# conversation to recover, no channels or schedules to operate and no Rundesk to manage —
# every one of those belongs to the named agent that delegated to it, and an execution told
# about them goes looking for an identity it does not have.
#
# What is left is what the role's own rules may not replace: whose behalf this is on, what
# the task is, how far the authority reaches, that another role may not be put on from here,
# and that being blocked is reported rather than worked around. A role may add to this and
# may narrow it. Nothing removes it.
#
# **Two parts, because the role's own locked `AGENTS.md` goes between them** — see `build`.
AGENT_TO_ROLE = """# Role execution

You are working as the '{role}' role, on behalf of the named agent {parent_agent}. These rules hold for the whole of this execution and cannot be replaced by anything after them.

- You are not {parent_agent} and not a named agent. You have no memory, no history, and no identity beyond this task.
- Do exactly the task in the brief. Never widen it, and never act on anything you infer about conversations you cannot see.
- The brief states how far your authority reaches. Needing more, stop and report `blocked`, naming the action and what it was for.
- Nobody is present while you run. Never ask a question, request approval, or wait for a reply — stop and report `blocked` instead. Where the brief is ambiguous, pick the reading it best supports and name the choice in your report.
- Never speak as the person who asked and never send anything to anyone. {parent_agent} reviews your report and answers them.
- Never operate Rundesk, change channels or schedules, put on another role, or write into {parent_agent}'s home.
- Your provider's own subagents are yours to use within this task. Give each one task, your own limits, and a definition of done it can check itself against, and check its output before you use it.
- Report truthfully: what you verified and how, what you did not do, and never a failure dressed as progress."""


# The second part of `AGENT_TO_ROLE`, standing after the role's own rules: what Rundesk knows
# about this particular execution. Bounded and Rundesk-authored — the parent supplies the
# brief as the prompt, and everything mechanical about the run is stated here once rather
# than left for a parent to remember to include.
AGENT_TO_ROLE_TASK = """## This execution

- Role run `{role_run}`, working in `{target}`, whose own instruction files apply to you.
- Files that are not part of the project belong under `{workspace}`.
- Finish with one report: outcome, what you changed or found, how you verified it, what risk is left, and any decision {parent_agent} must make.
- Report every part of the brief as done or blocked. A part you did not start is not a stopping point, and no stub, placeholder, or TODO stands in for one unless the report names it as unfinished."""

#: Every variable a role layer may be filled with. Kept apart from `STANDARD_VARIABLES`
#: because they describe different situations: those name an agent, a person and a place a
#: conversation is happening in, and a role execution has none of the three.
ROLE_VARIABLES = ("role", "parent_agent", "role_run", "target", "workspace")

#: Which layer each trigger is. **A person is the answer for everything not named here**,
#: including a surface this release has never heard of: the kinds of asking below are the
#: only ones that are not somebody typing, and what they withhold are the rules that assume
#: somebody is waiting. So an unclassified trigger is given a person's rules, and one of
#: these only by being named — which is the safe way round.
_ASKING = {DELEGATION: AGENT_TO_AGENT, SCHEDULE: SCHEDULE_TO_AGENT}

#: What is appended to `USER_TO_AGENT`, and to nothing else. A trigger absent here is a
#: person asking with nothing further to say about where.
_VARIANTS = {
    DIRECT: DIRECT_MESSAGE,
    PUBLIC: PUBLIC_ROOM,
    ONBOARDING: ONBOARDING_INSTRUCTIONS,
}


def render(template: str, variables: Mapping[str, object] | None = None) -> str:
    """Fill only variables the caller supplied, leaving unknown placeholders visible."""
    rendered = str(template or "")
    for name, value in (variables or {}).items():
        rendered = rendered.replace("{" + str(name) + "}", str(value or ""))
    return rendered


def build(*, variables: Mapping[str, object] | None = None, trigger: str = "",
          override: str | None = None, append: Iterable[str] = (),
          rules: str = "") -> str:
    """The core layer, the one layer naming who asked, then every addition in order.

    **One composer for all four** (R-ROL-5). It used to be two, written apart so that a role
    execution could not be a named agent with layers removed — and what makes one composer
    safe now is that there is nothing left to remove: `CORE_INSTRUCTIONS` carries no identity
    at all, and the layer a role gets is reached *instead of* `AGENT_IDENTITY` rather than by
    stripping it.

    An adapter `override` replaces only the variant appended to `USER_TO_AGENT`. Nothing
    replaces the core; owner, agent, schedule, adapter and middleware instructions belong in
    `append` and are kept in the order supplied.

    `rules` is a role's own `AGENTS.md` and reaches only `ROLE`. **Spliced in exactly as it
    was locked** — nothing is filled into it, because a run has to be resumable with
    byte-identical rules and a substitution is a difference (R-ROL-10) — and it sits between
    the two halves of `AGENT_TO_ROLE`, so a role reads its own rules before it is told what
    this particular run is. A role given them anywhere else is a different run from the one
    that was admitted.
    """
    additions = (append,) if isinstance(append, str) else tuple(append)
    filled = [render(CORE_INSTRUCTIONS, variables)]
    if trigger == ROLE:
        # The one layer with something unrendered in the middle of it, which is why this is
        # not one comprehension over everything.
        filled += [render(AGENT_TO_ROLE, variables), str(rules or ""),
                   render(AGENT_TO_ROLE_TASK, variables)]
    else:
        filled += [render(one, variables) for one in _for_a_named_agent(trigger, variables)]
        variant = override if override is not None else _VARIANTS.get(trigger, "")
        filled.append(render(variant, variables))
    filled += [render(one, variables) for one in additions]
    return "\n\n".join(one for one in (said.strip() for said in filled) if one)


def _for_a_named_agent(trigger: str, variables: Mapping[str, object] | None) -> tuple:
    """What a named agent is, and the one layer saying who asked it.

    The roles listing lands only where there is something to list — and never at all where
    another agent is asking, because that layer forbids putting a role on one paragraph
    later. Structural rather than left to the caller supplying no `roles`: an agent offered a
    capability the same preface refuses it spends a turn finding out (R-DEL-9).
    """
    asking = _ASKING.get(trigger, USER_TO_AGENT)
    if asking is AGENT_TO_AGENT:
        return (AGENT_IDENTITY, asking)
    listed = str((variables or {}).get("roles") or "").strip()
    return (AGENT_IDENTITY, ROLES_AVAILABLE if listed else "", asking)


def for_role(*, variables: Mapping[str, object] | None = None, rules: str = "") -> str:
    """What a role execution is told about its situation, in one stable order.

    Named rather than spelled at each call site, because the two things a role layer needs —
    its own trigger and its locked rules — are easy to get half right, and a role handed its
    rules in the wrong place is a different run from the one that was admitted.
    """
    return build(variables=variables, trigger=ROLE, rules=rules)
