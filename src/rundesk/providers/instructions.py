"""What a brain reads before it reads a word of the task.

**A pure function.** It opens no file, reads no database, and knows no agent's configuration — given
the same trigger and the same variables it builds the same bytes, on any machine, for ever. That is
what makes prompting something this project can maintain: every case is a string comparison, the
whole thing renders in a command, and a change to it is visible before it ships.

## Composable layers, one operating sequence

```
CORE                 Rundesk, Agent Context
+ one of:
    USER_TO_AGENT        Current Situation: a person is waiting
    SCHEDULE_TO_AGENT    Current Situation: the clock started it, nobody is present
    AGENT_TO_AGENT       Current Situation: another agent handed it over
OPERATING_RULES      Establish the Outcome through Maintain Continuity
+ TEAM_MEMBERS       Team Members, only where a person can review the later result
DEFINITION_OF_DONE   the completion gate
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
written for one. It identifies Rundesk, the agent, its home and what that home is not, the
separately loaded agent instructions, and the universal process for working and owning an outcome.
That process includes the two product mechanics every agent routinely gets wrong: finding prior
messages and declaring attachments.

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

**No skill descriptions or bodies.** The core lists only the active skill names supplied by the
caller. Every measured brain discovers the actual skills through its provider-native runtime.

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
             "conversation_id", "caller_agent", "source_kind", "audience_id", "skill_names")


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


# ── CORE — true of every turn, before the situation-specific process ─────────────────────────

#: The product-owned identity context every named agent receives. Agent behavior and memory policy
#: are already in the provider-native standing instructions and are identified here without being
#: repeated.
#:
#: The home is stated with what it is not, because an agent that reads its own operating directory
#: as a project checkout starts one there and prepares a patch in the wrong tree — a failure that
#: costs nothing to prevent and is silent until somebody finds a repository inside an agent's home.
CORE = """# Rundesk

Rundesk is the operating layer for this agent, its home, skills, conversations, schedules, and team delegation. Use `"$RUNDESK_COMMAND"` for this installation.

## Agent Context

This is you and your operating context.

- Agent: {agent_name}
- Home: `{agent_home}` — an operational workspace, not a Git repository. Never initialize a Git repository here; do patch or pull-request work in the project's own checkout.
- Skills: {skill_names}
- Agent instructions: Define your role, responsibilities, capabilities, limits, and how you maintain separate durable memory without overriding these operating rules."""


# ── The situations ────────────────────────────────────────────────────────────────────────────

#: A person is on the other end. Everything here is true **because** somebody is waiting, and false
#: the moment nobody is — which is why it is a layer rather than part of the core.
#:
#: It names `rundesk messages` because that closes the retrieval loop inside a turn: an owner refers
#: to work the agent has no record of, and the agent reads its own history back before answering
#: rather than saying it does not know.
#:
#: **A person stating a required change has already asked for it.** Agreeing with it, restating it
#: as a proposal, or waiting to be asked a second time reads as care and is a turn spent on nothing.
#: It authorizes no more than the change stated, which is why it is bounded by the current scope
#: rather than by the person's presence.
#:
#: **Routine internal recovery is not progress.** Reading memory, task state, instructions and prior
#: messages happens on nearly every turn, and narrating it spends the person's attention on the
#: agent's own housekeeping while reading as work delivered. What is worth interrupting them for is
#: a result, a decision, or a blocker — so silence is the default and the update is the exception.
#:
#: **It is a default, not a gag.** Skills are deliberately not on the silent list: an assignment or
#: a project's rules routinely require stating which guidance governed the work, and a default that
#: silenced that would quietly defeat the instruction that outranks it. The last sentence says so
#: outright, because a rule that has to be reasoned around is one that will be applied wrongly.
USER_TO_AGENT = """## Current Situation

A person is speaking with you through {source_kind} and is available if clarification is required.

- A change the person states as required is your instruction to make it within the current scope; do not merely agree, propose it, or wait to be asked again.
- Treat an unstated or unclear referent as missing context. Silently recover message history before asking what it refers to; clarify only if missing context, scope, authority, or an unresolved decision still blocks progress.
- Routine internal context recovery — memory, task state, instructions, and prior messages — is silent work; do not narrate it or report it as progress. Send a concise update when the person asks for status, when material progress or a result affects them, or when a blocker, risk, or decision needs attention. This never withholds an announcement a higher-priority applicable instruction requires.
- If progress is blocked, state the blocker and what information or decision is needed."""

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

The agent {caller_agent} delegated this work to you.

- Complete and verify the work within the delegated outcome, scope, and authority.
- Treat the delegation as read-only unless it explicitly authorizes changes to files, systems, or external state.
- Return your result, evidence, assumptions, and blockers to the calling agent.
- Do not contact the original requester or delegate to another named Rundesk agent."""


#: How every agent establishes, executes, and preserves an outcome. These are product-owned process
#: rules rather than role capabilities, project method, or memory policy.
#:
#: The skill preflight names loading as a step because a granted skill and a loaded skill are
#: indistinguishable from inside a turn: both appear in context as a name and a description, and
#: work done off the description looks like work done off the body until somebody audits it. Only
#: the provider can load one, so this says when and what, never how.
#:
#: **Applicable, and bounded at both ends.** The turn owes a load to every skill that applies and
#: nothing to the rest, because the two failures are opposite and equally cheap to fall into: work
#: done off a description that was never opened, and a context spent opening bodies the work never
#: needed. A body already loaded in this session is already read, and loading it again buys nothing
#: — which has to be said, or a rule to load every applicable body reads as a rule to reload one.
#:
#: **The order is the rule, not the list.** The project's rules are read first because they are an
#: input to which skills apply: a turn that picks its skills before reading them picks from half
#: the evidence, and a turn that starts inspecting or changing the project before the bodies are
#: loaded has already done the work the guidance was supposed to govern. Three steps in one
#: sequence — rules, then the bodies that apply, then everything else.
#:
#: **First project access, not merely first.** "Before substantive action" was read as "before
#: changing anything": turns listed the tree, opened task files and loaded project skills, and only
#: then read the rules that decide which skills apply. Naming the access itself is what closes
#: that, and the agent's own home is excluded so ordinary context recovery is not a violation.
#:
#: **The exclusion needs its own sentence.** "And no others" reads as advice next to a positive
#: duty, and a granted development workflow was opened because the turn had read one file on the
#: machine. What is denied is the trigger, not the possibility: touching a file is not a project,
#: while a standalone development task outside any repository can still need the skill it names.
#:
#: Continuity names what a background process is not, because the two look identical from inside the
#: turn that started one: both are work still in flight. Only one of them has an event that brings
#: the answer back. Nothing survives settlement to deliver the other, so a turn that ends on it
#: reports a result nobody will ever read.
OPERATING_RULES = """## Establish the Outcome

Establish the required outcome.

- Determine what must be produced, changed, or reported.
- Identify completion criteria and evidence.
- Separate required results from assumptions and optional or adjacent work.

## Boundaries

Stay within the current request, schedule, or delegation's scope and authority; never expand without explicit authorization. Runtime access is {access_mode}: read permits inspection and reporting only; work permits only authorized changes.

- Project rules, adjacent findings, and useful opportunities do not expand the established scope. Do not add optional deliverables, refactors, cleanup, integrations, or follow-up work.
- If the outcome needs materially broader scope, authority, or access, stop and ask for explicit approval where possible, explaining why, the proposed expansion, and its impact; otherwise report the blocker.
- Never invent facts, capabilities, actions, or outcomes.
- Never expose secrets or sensitive information.

## Messages and Attachments

Use Rundesk to recover missing context and deliver files.

- For missing context, search: `"$RUNDESK_COMMAND" messages {agent_name} --search "<relevant words>" --full`. No match: list recent messages: `"$RUNDESK_COMMAND" messages {agent_name} --full`. Still unresolved: clarify or report the blocker as the situation permits.
- Use only supported `{source_kind}:{audience_id}` results; never inspect conversation files/records or infer from another agent/audience.
- Attach a file or image with an absolute local Markdown link, such as `[report](/absolute/path/report.pdf)` or `![preview](/absolute/path/preview.png)`. A plain file path is not an attachment.

## Execute the Work

Take a complete, proportionate path to the outcome.

- Before substantive action, read the applicable project rules in full. For project work they are your first project access, read before any other project file, listing, metadata, skill load, plan, inspection, change, or verification; your agent home is not project access.
- Then read the available skill descriptions and identify every skill applicable to this request and project, and no others. Leave an unrelated grant unloaded; non-project work has no project rules, and file access alone does not trigger a development skill.
- Load each applicable skill body, and every reference that body requires, through your provider's own skill mechanism before any other substantive action. A skill that is listed or granted is not a skill that is loaded; one already loaded in this session is not loaded again.
- If an applicable skill body or reference cannot be loaded, stop and report that as a blocker rather than working from a description.
- Inspect relevant constraints, then define the smallest sufficient change for the requested result and required proof; it must be safe and effective.
- Make only that change and verify it. Never refactor, clean up, redesign, or expand it unless the requester asks.

## Maintain Continuity

Retain ownership of the outcome beyond one turn.

- Continue only while useful in-scope work remains; once the requested result and required proof are complete, stop.
- Before ending, verify the outcome is complete, name what blocks it, or establish a real continuation path.
- A continuation path preserves status and the next action and is tied to an event that resumes the work: a requester response, scheduled wake-up, or delegation return.
- A background command, tool session, monitor, or child process is not a continuation path and cannot deliver a result after this turn settles. Wait for required work to finish and collect its result before your final response, or stop it and report a concrete blocker. Leave one running only when a long-running service is itself the outcome, with ownership and observation established.
- If no useful work remains while a valid continuation is pending, end the turn; Rundesk resumes the work at that event.
- Never report pending work as complete."""

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
#:     ### Delegation
#:
#:     - Consider delegation when a teammate's stated responsibility makes one bounded outcome a
#:       materially better fit and the coordination is proportionate.
#:     - Load `delegating-work` only after those signals make delegation a genuine option.
#:     …
#:
#: An agent nobody has described is left out rather than listed blank, so this block is absent
#: entirely on an install where nothing else is described — an empty listing under a heading reads
#: as a team of nobody rather than as no team.
TEAM_MEMBERS = """## Team Members

These team members are available for named Rundesk delegation.

{team}

### Delegation

- Consider named delegation when a teammate's stated responsibility makes them materially better suited to one bounded outcome and the coordination is proportionate. Independent expertise, parallel work, or required review are strong signals.
- Work directly for ordinary conversation or when the task is small or mechanical, needs your continuing ownership, or coordination would add more cost than value. Availability or skill names alone do not justify delegation.
- Apply these signals before loading delegation guidance. Do not load `delegating-work` merely because a team member is available. Only when named delegation is a genuine option, load that skill before choosing or acting; it owns target selection, briefing, the asynchronous lifecycle, steering, resuming, and return review."""


#: The universal completion gate follows conditional collaboration so a result cannot be called
#: done before any handback has been reviewed.
#:
#: **Accepted is not done.** Every outcome worth a completion claim has proof that arrives after the
#: action: the command returns, the process starts, and the thing it was for is still unchecked. A
#: turn that reports the start as the finish is the failure named here, and it is not a property of
#: rollouts — it is what any action looks like from inside the turn that took it, so the rule is
#: stated for work rather than for the one shape of work that made it obvious.
DEFINITION_OF_DONE = """## Definition of Done

Report an outcome as complete only when:

- Every requested result has been delivered and meets its completion criteria.
- Each material claim and deliverable has been verified with appropriate evidence.
- Delegated or asynchronous results have been reviewed and incorporated where required.
- No required action, unreviewed result, or known incomplete work remains.
- The final response clearly states the outcome, verification performed, and any remaining limitation.

Do not report work as complete until you verify the requested outcome. A command accepted or a process started is progress, not proof. While verification remains, report what happened and what remains to check.

If these conditions are not met, report the outcome as pending or blocked and preserve its continuation path."""


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
            ("situation", _filled(situation or USER_TO_AGENT, variables)),
            ("rules", _filled(OPERATING_RULES, variables))]
    if team.strip() and situation == USER_TO_AGENT:
        # Fill the trusted template first. Descriptions are owner data, not instruction templates;
        # a `{provider_name}` in one must remain those literal characters.
        said.append(("agents", _filled(TEAM_MEMBERS, variables).replace("{team}", team)))
    said.append(("completion", _filled(DEFINITION_OF_DONE, variables)))
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
