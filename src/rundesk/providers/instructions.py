"""What a brain reads before it reads a word of the task.

**A pure function.** It opens no file, reads no database, and knows no agent's configuration — given
the same trigger and the same variables it builds the same bytes, on any machine, for ever. That is
what makes prompting something this project can maintain: every case is a string comparison, the
whole thing renders in a command, and a change to it is visible before it ships.

## Three composable blocks, five required sections

```
CORE                 Rundesk, Agent Context, Core Rules, Messages and Attachments
+ one of:
    USER_TO_AGENT        Current Situation: a person is waiting
    SCHEDULE_TO_AGENT    Current Situation: the clock started it, nobody is present
    AGENT_TO_AGENT       Current Situation: another agent handed it over
+ TEAM_MEMBERS       Team Members, only where a person can review the later result
+ ADDITIONS          whatever the caller appended, each named and bounded
```

They are plain strings. There is no fragment spliced into another, no block built from pieces of a
third, and nothing composed conditionally out of parts — a block is what it looks like, and reading
one tells you everything a turn of that kind is told.

**A trigger belongs to exactly one block, and a person is the answer for anything not named.** What
the other two withhold are the rules that assume somebody is waiting, so a surface this release has
never heard of is given a person's rules and one of the others only by being named. That is the safe
way round, and it is the kind of default that is easy to get backwards.

## What the core owns

**Everything this release runs is a named agent standing in its own directory**, so the core is
written for one. It identifies Rundesk, the agent and its home, the separately loaded agent
instructions, the universal conduct floor, and the two product mechanics every agent routinely
gets wrong: finding prior messages and declaring attachments.

It contains no memory policy, role behavior, project method, or access posture. Those belong to the
agent's own instructions or the provider boundary, not to Rundesk's product-owned operating text.

## `TEAM_MEMBERS` is person-facing, and that is the review rule

Named Rundesk delegation is asynchronous. A person-facing turn can receive and review that later
result; a schedule ends without anybody present, and an agent already answering a delegation is at
the named-agent depth limit. Both are shown no team. Provider-local subagents remain available
inside the delegated turn's own authority.

## What is deliberately not here

**No per-agent instruction text or memory policy.** An agent's identity is in the standing rules its
provider loads natively. The core names that layer and its precedence without reopening it or
copying any of its content.

**No skills index.** A skill costs its description every turn and its body only when used, and every
measured brain discovers skills for itself.

**No content-safety or refusal text.** Neither comparable product ships any, and adding it would
spend an invariant prefix on what the model already does.
"""

import hashlib
import re
from typing import Iterable, List, Mapping, NamedTuple, Optional, Tuple

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
             "conversation_id", "caller_agent", "source_kind", "audience_id")


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

#: The product-owned rules every named agent receives. Agent behavior and memory policy are already
#: in the provider-native standing instructions and are identified here without being repeated.
CORE = """# Rundesk

Rundesk is the operating layer for this agent, its workspace, skills, conversations, schedules, and team delegation. Use `"$RUNDESK_COMMAND"` for this installation.

## Agent Context

This context identifies you and the environment you operate within.

- Agent: {agent_name}
- Home: `{agent_home}`
- Skills: Provided by the runtime.
- Agent instructions: Define your role, behavior, and memory without overriding these operating instructions.

## Core Rules

Follow these operating rules and your agent instructions before taking action.

- Stay within the scope and authority of the current assignment.
- Respect the limitations of the current situation.
- Never invent facts, capabilities, actions, or outcomes.
- Never expose secrets or sensitive information.
- Disclose failures, blockers, incomplete work, and pending work.
- Inspect relevant context and existing state before acting.
- Take only the actions needed to complete the assignment.
- Verify your work before reporting completion.

## Messages and Attachments

Use Rundesk messages and attachments to recover context and deliver files reliably.

- If something seems out of context or refers to prior work, decisions, or discussions not shown here, search all message history before continuing or asking for clarification: `"$RUNDESK_COMMAND" messages {agent_name} --search "<relevant words>" --full`
- Attach files using an absolute local Markdown link, such as `[report](/absolute/path/report.pdf)` or `![preview](/absolute/path/preview.png)`. A plain file path is not an attachment."""


# ── The situations ────────────────────────────────────────────────────────────────────────────

#: A person is on the other end. Everything here is true **because** somebody is waiting, and false
#: the moment nobody is — which is why it is a layer rather than part of the core.
#:
#: It names `rundesk messages` because that closes the retrieval loop inside a turn: an owner refers
#: to work the agent has no record of, and the agent reads its own history back before answering
#: rather than saying it does not know.
USER_TO_AGENT = """## Current Situation

A person is speaking with you through {source_kind}.

- Their current request defines your scope and authority.
- Respond through this conversation.
- Ask a focused question only when a missing decision prevents safe progress."""

#: The clock started this and **nobody is present**. What this withholds is every rule that assumes
#: somebody is waiting: there is nothing to ask, nothing to clarify, and no later turn to report in.
SCHEDULE_TO_AGENT = """## Current Situation

The schedule "{schedule_name}" started this turn. No person is currently present. Your final response will be delivered automatically to the intended recipient or destination.

- Perform only the work the schedule asks of you.
- Do not ask questions or wait for clarification.
- Make your final response a complete, standalone report of what happened, including any failure or blocker."""

#: Another agent handed this turn its task. **Still this agent, as itself** — its own home, memory,
#: skills and brain — so this composes on `CORE` like any other. What it adds is that the requester
#: is not a person, that nobody is present, and that the work stops here.
#:
#: **It offers no team, and that is the depth rule** rather than a sentence asking nicely: an agent
#: answering a delegation is never shown anybody to hand work to, so handing it on is not something
#: it can decide to do. `build` withholds the listing for this trigger.
AGENT_TO_AGENT = """## Current Situation

The agent {caller_agent} delegated this assignment to you.

- Work only within the delegated scope and authority.
- Return your result, evidence, assumptions, and blockers to the calling agent.
- Do not contact the original requester or delegate to another named Rundesk agent.
- If needed, you may use your provider's built-in subagents for bounded work within this assignment.
- The calling agent owns integration, final verification, and communication."""

#: Who a turn may hand work to. `{team}` is a listing the caller supplies, because which agents an
#: install has is a fact about that install and this module reads nothing — `providers.team`
#: builds it, excluding the agent being told.
#:
#: Composed only where a person-facing turn can review the later result. A schedule ends before an
#: asynchronous named handoff can return, and a turn already answering a delegation is at depth one.
#:
#: What an agent actually reads::
#:
#:     ## Team Members
#:
#:     - **bob** — keeps the billing system; knows every invoice edge case we have hit
#:     - **nina** — runs the deploy pipeline and the incident history
#:
#:     - Choose a team member whose stated role, focus, or skills make them better suited.
#:     - Delegate with `"$RUNDESK_COMMAND" ask <agent> "<task>"` and review the later result.
#:     …
#:
#: An agent nobody has described is left out rather than listed blank, so this block is absent
#: entirely on an install where nothing else is described — an empty listing under a heading reads
#: as a team of nobody rather than as no team.
TEAM_MEMBERS = """## Team Members

These team members are available for named Rundesk delegation.

{team}

- Choose a team member whose stated role, focus, or skills make them better suited for the work.
- Delegate a bounded assignment with `"$RUNDESK_COMMAND" ask <agent> "<task>"`. Include the context, scope, authority, expected result, and completion criteria.
- Named Rundesk delegation is asynchronous. Do not wait for or duplicate active delegated work.
- Review and verify the result before using it or reporting the larger assignment complete.
- Keep simple or general work with you when delegation would add more overhead than value."""


def build(*, situation: str = USER_TO_AGENT, variables: Optional[Mapping[str, object]] = None,
          additions: Iterable[Tuple[str, str]] = (), team: str = "") -> Prompt:
    """The core, the one situation naming who asked, then every addition in the order supplied.

    `additions` are `(name, text)` pairs. The name is what a byte breakdown calls them, so an owner
    reading `rundesk providers instructions` can see which one grew.

    Nothing replaces the core and nothing replaces the situation. An addition adds, which is the
    whole of the composition rule — a layer that could replace an earlier one is a layer that can
    silently delete the honesty rules.

    `situation` is **one of the blocks above**, passed as itself. There is no name for it to be
    looked up by: a caller that has to name a situation and a table that turns that name back into
    the block are two things to keep in step, and the name was never stored, compared or shown
    anywhere outside this module. Omitted, it is a person asking — which is the safe default for
    the same reason it always was, and is now the signature rather than a fallback in a lookup.

    `team` is who this turn may hand work to, and it is composed only for person-facing work. A
    schedule cannot review a later asynchronous result, and a turn already answering a delegation
    remains at named-agent depth one.
    """
    said = [("core", _filled(CORE, variables)),
            ("situation", _filled(situation or USER_TO_AGENT, variables))]
    if team.strip() and situation == USER_TO_AGENT:
        # Fill the trusted template first. Descriptions are owner data, not instruction templates;
        # a `{provider_name}` in one must remain those literal characters.
        said.append(("agents", _filled(TEAM_MEMBERS, variables).replace("{team}", team)))
    said.extend((name, _bounded(text, AN_ADDITION_AT_MOST, variables))
                for name, text in additions)

    kept = [(name, one.strip()) for name, one in said if one.strip()]
    text = "\n\n".join(one for _, one in kept)
    return Prompt(
        text=text,
        layers=[Layer(name, len(one.encode("utf-8"))) for name, one in kept],
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        total_bytes=len(text.encode("utf-8")),
    )


def _filled(template: str, variables: Optional[Mapping[str, object]]) -> str:
    """Fill in what the caller supplied, leaving anything it did not visible.

    A single substitution pass, never `str.format`. Owner text arrives with braces in it eventually
    — a code sample, a JSON snippet, a shell brace expansion — and must stay literal. A recognized
    placeholder inside a replacement value must stay literal too rather than being replaced again.

    A placeholder nobody filled is left standing rather than blanked, so a variable somebody forgot
    to pass shows up in the rendered prompt as itself instead of as a sentence with a hole in it.
    """
    values = variables or {}

    def replacement(found: re.Match) -> str:
        name = found.group(1)
        value = values.get(name)
        return found.group(0) if value is None else str(value)

    return re.sub(r"\{(" + "|".join(re.escape(one) for one in VARIABLES) + r")\}",
                  replacement, str(template or ""))


def _bounded(text: str, at_most: int, variables: Optional[Mapping[str, object]]) -> str:
    """Fill one addition and keep at most `at_most` UTF-8 bytes without leaving broken text."""
    return _filled(text, variables).encode("utf-8")[:at_most].decode("utf-8", errors="ignore")
