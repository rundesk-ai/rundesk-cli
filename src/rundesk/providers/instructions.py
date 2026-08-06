"""What a brain reads before it reads a word of the task.

**A pure function.** It opens no file, reads no database, and knows no agent's configuration — given
the same trigger and the same variables it builds the same bytes, on any machine, for ever. That is
what makes prompting something this project can maintain: every case is a string comparison, the
whole thing renders in a command, and a change to it is visible before it ships.

## The shape

```
one CORE                    CORE, or ROLE_CORE where a role is running
+ exactly one SITUATION     a person · a schedule · another agent · a role
+ what it may hand on to    the team and the roles, and only where that is legal
+ ordered ADDITIONS         each named, each bounded where it comes in
```

**Two layers, and each answers a different question.** `CORE` is *where you are and what you can
do* — the directory the turn stands in, the files the agent lives by, the skills beside them, the
command that reaches this install, and the rules that hold before any of it. A situation is *why
this turn is happening at all*, and holds only what is true because of that and false otherwise.

A fact belongs in exactly one of them. The test is whether the sentence would still be true if
nobody had asked: where the agent's own files are does not change because a schedule started this
rather than a person, so it is `CORE` and is written once.

**A trigger belongs to exactly one situation, and a person is the answer for anything not named.**
What the other situations withhold are the rules that assume somebody is waiting, so a surface this
release has never heard of is given a person's rules and one of the others only by being named. That
is the safe way round, and it is the kind of default that is easy to get backwards.

## What the core may say, and what it may not

**Everything this release runs is a named agent standing in its own directory**, so the core is
written for one: it names the agent, its home, the files it lives by and the command that reaches
this install. That is what makes it the operational layer rather than a preamble.

It may still never name **a channel or a schedule**. Those are the two situations, and a fact about
one of them that leaked into the core would be read by every turn of the other — which is exactly
how the build this replaces came to tell a scheduled run, three paragraphs after forbidding it to
ask anybody anything, to go and ask. `tests/test_providers_instructions.py` searches the built core
for both words.

**A role execution has a core of its own, and not this one with pieces removed.** An agent working
as a shared specialist has no home, no memory and no rundesk to operate, so `ROLE_CORE` is written
out in full and `A_ROLE_IS_RUNNING` is what reaches it. Writing it as "strip the core down" is what
this module deliberately does not do: a layer that can be reduced is a layer that can silently lose
the honesty rules at the bottom of it. The two cores repeat those four rules rather than sharing a
fragment, because a fragment composed into both is one somebody can later compose into only one.

## What a turn may hand its work to, and where that is said

An agent is told which colleagues it may delegate to and which roles it may put on. **Both listings
are withheld from a turn that is itself answering a delegation or running a role**, and that is
depth-one made structural rather than asked for: a turn shown nobody cannot hand work to anybody,
so there is no rule for it to be talked out of. `HANDED_ON` is the set, and `build` is where it
applies.

## What is deliberately not here

**No per-agent instruction text.** An agent's own identity is the files in its home — `AGENTS.md`
and `MEMORY.md`, placed there by `agents.pages` when it was made — which the brain discovers because
it is standing in the directory they are in. That is the whole mechanism, it is what every measured
brain does natively, and it means an owner edits a file rather than a database column.

The core names those two files rather than leaving the brain to find them, and that is the pointer
and not a copy: a brain reads its bootstrap page late, or not at all, and one that never opened them
is an agent with no rules and no continuity that reports nothing wrong.

**No skills index.** A skill costs its description in the prompt every turn and its body only when
used, and every measured brain discovers skills for itself. Putting a list here would charge every
turn for every skill an agent has ever been granted.

**No content-safety or refusal text.** Neither comparable product ships any, and adding it would
spend an invariant prefix on what the model already does.
"""

import hashlib
from typing import Iterable, List, Mapping, NamedTuple, Optional, Tuple

#: Which situation a turn is. A trigger absent from this is **a person asking**, which is what makes
#: a surface nobody has taught this release about safe by default.
A_PERSON_ASKED = "a_person_asked"
A_SCHEDULE_CAME_DUE = "a_schedule_came_due"

#: Another named agent handed this turn a task, and a role execution running on one's behalf.
#: `conversations.source` holds the matching words.
ANOTHER_AGENT_ASKED = "another_agent_asked"
A_ROLE_IS_RUNNING = "a_role_is_running"

TRIGGERS = (A_PERSON_ASKED, A_SCHEDULE_CAME_DUE, ANOTHER_AGENT_ASKED, A_ROLE_IS_RUNNING)

#: The two triggers where nobody is waiting **and the turn may not hand its work on again**. Named
#: as a set because three places ask the same question — which core to build on, whether to list the
#: team, and whether to list the roles — and three separate conditions would be three chances to
#: answer it differently.
HANDED_ON = (ANOTHER_AGENT_ASKED, A_ROLE_IS_RUNNING)

#: How much of one supplied addition is used. **Bounded where it comes in, and the finished stack is
#: never clipped** — clipping the whole would silently drop whichever later layers fell past the
#: boundary, which is the failure that looks like a layer having no effect.
AN_ADDITION_AT_MOST = 4000

#: Every variable a layer may read. Named here so that adding one is a decision somebody makes rather
#: than a placeholder that silently renders as nothing.
#:
#: They are **communication concepts, not platform concepts**: an agent, a home, a brain, how much of
#: the machine this turn may touch. Nothing here says Discord, or Slack, or a room — a variable that
#: named one would be a layer that has to be rewritten for the second surface.
VARIABLES = ("agent_name", "agent_home", "provider_name", "access_mode", "schedule_name",
             "conversation_id", "caller_agent", "role_name", "delegation_id", "workspace")


class Layer(NamedTuple):
    """One piece of a built prompt, and what it cost.

    `bytes_used` is what makes prompt budget a measurement rather than a feeling: a layer that
    doubled is visible in a command, without anybody having to count.
    """

    name: str
    bytes_used: int


class Prompt(NamedTuple):
    """What a brain will read, and everything needed to say what it was afterwards.

    `sha256` is over the whole text. It is what a turn records instead of the text itself: the
    builder is deterministic and every input is already a column on the turn, so what was sent is
    re-composable while the release stands — and when it is not, the fingerprint says the prompt
    changed rather than leaving somebody to guess. That is a **better** audit than a stored copy,
    because it detects the change instead of merely surviving it.
    """

    text: str
    layers: List[Layer]
    sha256: str
    total_bytes: int


# ── CORE — true of every turn, and carrying no identity ───────────────────────────────────────

#: **Where you are, what you can reach, and the rules that hold before any of it.** Every line is
#: true of every turn whoever started it — that is the membership test, and a line that is true only
#: because somebody is waiting belongs in a situation instead.
#:
#: **It may still never name a channel or a schedule.** See the module docstring, and the suite for
#: the check.
#:
#: The three files are named rather than left to be discovered, because a brain that never opened
#: them is an agent with no rules and no continuity that reports nothing wrong. The names are the
#: ones `agents.pages` really places; `tests/test_layers.py` compares the two lists rather than
#: trusting they were kept in step.
#:
#: The honesty rules are last and are the ones that earn their place hardest: the failure a person
#: cannot see coming is a turn that reports work it did not do.
CORE = """# rundesk

You are {agent_name}, an agent running inside rundesk — the program that started this turn and receives whatever you produce.

## Where you are

You are standing in your own directory, `{agent_home}`. It is yours, no other agent reads it, and what you keep between turns belongs in it.

- `AGENTS.md` is how you work. `MEMORY.md` is what you have learned that is still true. Read both before your first reply in a conversation — they are the only thing you carry, and you start fresh every time.
- `skills/` beside them is what you know how to do. Each skill says when it applies; read one when the work is what it describes, rather than guessing at the work.
- This directory is not a Git repository and neither is anything above it. Resolve a project's own directory before any Git command, and never report yours as though it were a project's.
- Work all of that out silently. Say something about it only when one of them is what blocked you.

## What you can reach

- The machine, as your owner would: their shell, their files, the tools they have installed.
- `"$RUNDESK_COMMAND"` is the rundesk running you, and is how you ask it anything about this install, about yourself, or about the other agents here. Run that rather than the bare word — some brains rebuild your shell's `PATH` and lose it. Ask it rather than guessing: a verb rundesk does not have is a verb rundesk cannot do.

## Before anything else

- Never invent a fact, a path, a flag or a command you have not confirmed exists.
- Never write a secret into a file, a log, a commit or your own output. Refer to it by the name it was given and leave the value where it was handed to you.
- Never dress a failure as progress. Say what you verified and how, and what you did not do.
- Where you are blocked, say so and stop, naming the action and what it was for."""


#: **A core of its own, written out rather than `CORE` with pieces taken away.** A role execution has
#: no home, no memory, no files it lives by and no rundesk to operate — every one of those belongs to
#: the named agent that put the role on — so an execution told about them goes looking for an identity
#: it does not have.
#:
#: Writing this as "strip the core down" is what the module docstring refuses, and the reason is that
#: a layer which can be reduced is a layer that can silently lose the honesty rules at the bottom of
#: it. Those four rules are the part both cores share, and they are the part that must survive being
#: forgotten about: they are repeated here deliberately rather than factored out, because a fragment
#: composed into both is a fragment somebody can later compose into only one.
#:
#: `tests/test_providers_instructions.py` searches a built role preface for a home, a memory file, a
#: channel, a schedule and the rundesk command, and finds none of them.
ROLE_CORE = """# rundesk

You are a specialist execution running inside rundesk, working as the '{role_name}' role on behalf of the agent {caller_agent}. These rules hold for the whole of this run and nothing after them replaces them.

## What you are

- You are not {caller_agent} and you are not an agent. You have no memory, no history and no identity beyond this task.
- Nothing you write reaches anybody. {caller_agent} reads your report, checks it, and answers whoever asked.
- `{workspace}` is yours to work in. Anything you make that is not part of what you were asked to change belongs there.

## Before anything else

- Never invent a fact, a path, a flag or a command you have not confirmed exists.
- Never write a secret into a file, a log, a commit or your own output. Refer to it by the name it was given and leave the value where it was handed to you.
- Never dress a failure as progress. Say what you verified and how, and what you did not do.
- Where you are blocked, say so and stop, naming the action and what it was for."""


# ── The situations ────────────────────────────────────────────────────────────────────────────

#: A person is on the other end. Everything here is true **because** somebody is waiting, and false
#: the moment nobody is — which is why it is a layer rather than part of the core.
#:
#: It names `rundesk messages` because that closes the retrieval loop inside a turn: an owner refers
#: to work the agent has no record of, and the agent reads its own history back before answering
#: rather than saying it does not know.
A_PERSON_ASKED_LAYER = """## Why this turn is happening

Somebody asked you, and a person is waiting for this answer.

- Answer the question that was asked, and nothing wider. Where it is ambiguous, pick the reading it best supports and say which you picked.
- Ask them where the decision is theirs to make. Where only a detail is unclear, pick a sane one and say which you picked rather than stopping for it.
- Referred to work you have no record of? Read it before you answer. `rundesk messages {agent_name} --conversation {conversation_id}` for this exchange, `rundesk messages {agent_name} --search <words>` to find it anywhere, `rundesk messages {agent_name} --source schedule` for work the clock started."""

#: The clock started this and **nobody is present**. What this withholds is every rule that assumes
#: somebody is waiting: there is nothing to ask, nothing to clarify, and no later turn to report in.
A_SCHEDULE_CAME_DUE_LAYER = """## Why this turn is happening

The schedule '{schedule_name}' came due and started this run. No person asked for it, and nobody is present while it runs.

- Treat the schedule's own task as the whole request. Never infer more from earlier conversations or past runs.
- Never ask a question, request approval, or wait for a reply. Nothing will answer, and the run ends when you stop. Where the task is ambiguous, pick the reading it best supports and say which you picked.
- Where the work needs an action somebody would have to approve, stop before that action and report that you are blocked, naming the action and what it was for.
- Write nothing until the work is finished. Only your last complete message is kept as this run's answer; everything before it is working notes.
- That message is the whole report: what you did or found, how you verified it, and what you did not do. Nobody will be there to ask you a follow-up.
- Report the outcome. When there was nothing worth acting on, say that in a short direct answer."""

#: Another agent handed this turn its task. **Still this agent, as itself** — its own home, memory,
#: skills and brain — so this composes on `CORE` like any other. What it adds is that the requester
#: is not a person, that nobody is present, and that the work stops here.
#:
#: **It offers no team and no roles, and that is the depth rule** rather than a sentence asking
#: nicely: an agent answering a delegation is never shown anybody to hand work to, so handing it on
#: is not something it can decide to do. `build` withholds both listings for this trigger.
ANOTHER_AGENT_ASKED_LAYER = """## Why this turn is happening

{caller_agent}, an agent on your team, handed you this task. Not a person, not your owner, and nobody is present while you run.

- Treat the task as the whole request. Never infer more from earlier conversations or past runs. Where it is ambiguous, pick the reading it best supports and say which you picked.
- The task says how far your authority reaches. Needing more than that, stop and say you are blocked, naming the action and what it was for.
- A question is allowed and it is never a wait. Nothing will answer while you run, so ask it as your report and stop — {caller_agent} reads it and comes back to you with the answer.
- Do not hand this work on. It is yours to finish or to report blocked. Your own brain's subagents are yours to use within it.
- Write to `MEMORY.md` only what changes how you act for your own owner. This task is {caller_agent}'s, not your continuity.
- Write nothing until the work is finished. Only your last complete message reaches {caller_agent}; everything before it is working notes, and none of it goes to any channel or any person.
- That message is your whole report: what you did or found, how you verified it, what you did not do, and any decision {caller_agent} has to make. Report every part of the task as done or blocked."""

#: The second half of what a role execution is told — what rundesk knows about *this* run, standing
#: after the role's own rules. Two parts with the role's file between them, because a role that
#: receives its own rules after the task details is a different run from the one that was admitted.
A_ROLE_IS_RUNNING_LAYER = """## This run

- Role run `{delegation_id}`, working on behalf of {caller_agent}.
- Do exactly the task in the brief. Never widen it, and never act on anything you infer about conversations you cannot see.
- Nobody is present. Never ask a question, request approval, or wait for a reply — stop and say you are blocked instead. Where the brief is ambiguous, pick the reading it best supports and name the choice in your report.
- Never speak as whoever asked, and never send anything to anyone.
- Never put on another role and never hand this work to an agent.
- Finish with one report: the outcome, what you changed or found, how you verified it, what risk is left, and any decision {caller_agent} has to make. Report every part of the brief as done or blocked — a part you did not start is not a stopping point."""

#: Which layer each trigger is. **A trigger absent from this is a person asking**, which is the safe
#: way round: a surface this release has never heard of is somebody typing, and what the other
#: situations withhold are the rules that assume somebody is waiting.
_SITUATIONS = {
    A_PERSON_ASKED: A_PERSON_ASKED_LAYER,
    A_SCHEDULE_CAME_DUE: A_SCHEDULE_CAME_DUE_LAYER,
    ANOTHER_AGENT_ASKED: ANOTHER_AGENT_ASKED_LAYER,
    A_ROLE_IS_RUNNING: A_ROLE_IS_RUNNING_LAYER,
}

#: Which core each trigger builds on. **A role is the only thing that is not a named agent**, so it
#: is the only entry here; everything else — including a trigger this release has never heard of —
#: gets the agent core, which is the safe way round for the same reason `_SITUATIONS` is.
_CORES = {A_ROLE_IS_RUNNING: ROLE_CORE}

#: What a turn is told it may hand work to. Both are **listings the caller supplies**, because what
#: agents exist and what roles ship are facts about an install and this module reads nothing.
#:
#: They are composed only where handing work on is legal — see `HANDED_ON`. A turn that is itself
#: answering a delegation or running a role is shown neither, which is what makes depth-one a thing
#: an agent cannot do rather than a rule it is asked to keep.
YOUR_TEAM = """## Agents on your team you may delegate to

{team}

`rundesk delegate <agent>`, task on standard input. They answer as themselves, in a later turn, and you review what comes back — nothing they wrote reaches anybody until you have."""

ROLES_YOU_MAY_PUT_ON = """## Roles you may put on

A role is you, working in a mode, with your own identity withheld. `read` changes nothing; `work` changes what you point it at.

{roles}

`rundesk delegate --role <role>`, task on standard input — say in it where the work is. It reports back in a later turn and you review it."""


def build(*, trigger: str = A_PERSON_ASKED, variables: Optional[Mapping[str, object]] = None,
          additions: Iterable[Tuple[str, str]] = (), rules: str = "",
          team: str = "", roles: str = "") -> Prompt:
    """The core, the one situation naming who asked, then every addition in the order supplied.

    `additions` are `(name, text)` pairs. The name is what a byte breakdown calls them, so an owner
    reading `rundesk providers instructions` can see which one grew.

    Nothing replaces the core and nothing replaces the situation. An addition adds, which is the
    whole of the composition rule — a layer that could replace an earlier one is a layer that can
    silently delete the honesty rules.

    `rules` are a role's own, and they are **spliced in exactly as they were given** — between the
    role core and what rundesk knows about this run, with nothing filled into them. A run has to be
    resumable under byte-identical rules, and a substitution is a difference. They are ignored for
    every other trigger, so a caller that passes them by mistake cannot put arbitrary text in front
    of an agent.

    `team` and `roles` are what this turn may hand work to, and they are composed **only where doing
    so is legal**. A turn already answering a delegation or running a role is shown neither, which is
    the depth rule made structural: there is nothing for it to route around, because it was never
    told anybody exists.
    """
    core = _CORES.get(trigger, CORE)
    said = [("core", _filled(core, variables)),
            (_named(trigger), _filled(_SITUATIONS.get(trigger, A_PERSON_ASKED_LAYER), variables))]
    if trigger == A_ROLE_IS_RUNNING and rules.strip():
        # Between the two halves, and never rendered. See the docstring, and R-ROL-10.
        said.insert(1, ("role rules", rules))
    if trigger not in HANDED_ON:
        if team.strip():
            said.append(("team", _filled(YOUR_TEAM.replace("{team}", team), variables)))
        if roles.strip():
            said.append(("roles", _filled(ROLES_YOU_MAY_PUT_ON.replace("{roles}", roles), variables)))
    said.extend((name, _filled(text, variables)[:AN_ADDITION_AT_MOST])
                for name, text in additions)

    kept = [(name, one.strip()) for name, one in said if one.strip()]
    text = "\n\n".join(one for _, one in kept)
    return Prompt(
        text=text,
        layers=[Layer(name, len(one.encode("utf-8"))) for name, one in kept],
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        total_bytes=len(text.encode("utf-8")),
    )


def _named(trigger: str) -> str:
    """What a byte breakdown calls this situation. An unnamed trigger is a person asking."""
    return trigger if trigger in _SITUATIONS else A_PERSON_ASKED


def _filled(template: str, variables: Optional[Mapping[str, object]]) -> str:
    """Fill in what the caller supplied, leaving anything it did not visible.

    **`str.replace` and never `str.format`.** Owner text arrives with braces in it eventually — a
    code sample, a JSON snippet, a shell brace expansion — and `str.format` raises on one, mid-turn,
    in the one function whose whole job is to produce a prompt.

    A placeholder nobody filled is left standing rather than blanked, so a variable somebody forgot
    to pass shows up in the rendered prompt as itself instead of as a sentence with a hole in it.
    """
    said = str(template or "")
    for name in VARIABLES:
        value = (variables or {}).get(name)
        if value is not None:
            said = said.replace("{" + name + "}", str(value))
    return said
