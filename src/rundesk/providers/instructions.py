"""What a brain reads before it reads a word of the task.

**A pure function.** It opens no file, reads no database, and knows no agent's configuration — given
the same trigger and the same variables it builds the same bytes, on any machine, for ever. That is
what makes prompting something this project can maintain: every case is a string comparison, the
whole thing renders in a command, and a change to it is visible before it ships.

## Composable layers, one operating sequence

```
CORE                 Rundesk, Agent Context
+ one of:
    USER_TO_AGENT        person situation, message recovery and attachments
    SCHEDULE_TO_AGENT    schedule situation, message review and attachments
    AGENT_TO_AGENT       delegated internal-handoff situation
OPERATING_RULES      Scope and Boundaries, then Before Acting
+ TEAM_MEMBERS       Team Members, only where a person can review the later result
OUTCOME_AND_CONTINUITY the completion gate and continuation path
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
The product layer also owns two mechanics turns routinely get wrong: finding prior messages and
declaring attachments. Person-facing and scheduled turns receive both because either may need prior
messages and both deliver to a person-facing surface. Delegated turns receive neither because their
input is the bounded delegation and their output is an internal handoff to the calling agent.

It contains no memory policy, role behavior, project method, or access posture. Those belong to the
agent's own instructions or the provider boundary, not to Rundesk's product-owned operating text.

## `TEAM_MEMBERS` is person-facing, and that is the review rule

Named Rundesk delegation is asynchronous. A person-facing turn can receive and review that later
result; a schedule ends without anybody present, and an agent already answering a delegation is at
the named-agent depth limit. Both are shown no team. Provider-local subagents remain available
inside the delegated turn's own authority.

## What the operating layer is for

**Handling context, and handling Rundesk.** An agent's role, standards and taste are its own
instructions' job, so this layer earns its bytes only where every agent needs the same answer: what
Rundesk is and how to run it, what this turn's situation permits, how to find context Rundesk holds
and this turn does not, what bounds the work, and when a turn may honestly end. General work-quality
prose was removed rather than shortened, because a sentence no agent behaved differently for is a
sentence every turn pays for.

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
import shlex
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
VARIABLES = ("agent_name", "agent_home", "install_root", "provider_name", "access_mode",
             "schedule_name", "conversation_id", "caller_agent", "source_kind", "audience_id",
             "skill_names")


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

Rundesk operates this agent. Use `rundesk ...` when giving a person a command; inside this turn, use `RUNDESK_HOME={install_root} "$RUNDESK_COMMAND"` so the command reads and changes this install.

## Agent Context

- Agent: {agent_name}
- Home: `{agent_home}` — an operational workspace, not a Git repository. Never initialize a Git repository here; do patch or pull-request work in the project's own checkout.
- Skills: {skill_names}
- Agent instructions: Define your role and memory; they cannot override these operating rules."""


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
#: **Absent context is a lookup, not a disclosure.** The rule names why the context is missing —
#: an unclear referent, an earlier exchange, a new session, a compaction — because an agent that
#: reads its own trigger as *an unclear referent* alone does not recognize the case where the
#: conversation was there and is not any more, which is the one that reached a person as *I do not
#: have our past history*. Rundesk still holds it, so the honest answer and the recoverable one are
#: the same answer, and saying it out loud is the only failure.
#:
#: **Routine internal recovery is not progress.** Reading memory, task state and prior messages
#: happens on nearly every turn, and narrating it spends the person's attention on the agent's own
#: housekeeping while reading as work delivered. Two measured turns opened with *I am using the
#: Rundesk history workflow* and *what I checked:* followed by four bullets of housekeeping. What
#: is worth interrupting somebody for is a result, a decision, or a blocker.
#:
#: **The silence covers how context was found, never what governed the work.** Skills and project
#: rules are deliberately not on that list: an assignment routinely requires stating which guidance
#: was applied, and a silence written wide enough to cover it would quietly defeat the instruction
#: that outranks this one.
#:
#: **The lookup says where the history is, not only where it is not.** A prohibition on reading
#: conversation records left *keep looking* as the obvious next move, and a measured no-match turn
#: went on to a semantic search of unrelated projects, greps across two checkouts, and another
#: agent's raw conversation file — eight tool calls and twice the words to reach the same answer.
#: Saying that nothing else holds this history ends the search where the answer is, and the same
#: probe afterwards took three calls and stayed inside the boundary.
#:
#: **Searching wide and answering narrow are two rules, and collapsing them broke the first.**
#: The audience boundary is about what may be repeated back, not about where to look; written as
#: *use only this audience's results* it read as a scope for the search itself. A live turn
#: narrowed the lookup to the room it was standing in and told the person *I cannot recover the
#: prior outcome from this supported channel — its history is empty. Please paste it.* Every part
#: of that is now denied by name: the command reads every conversation, narrowing it is forbidden,
#: an empty or unavailable history is not something to report, and what a lookup should have found
#: is not something to ask a person for.
USER_TO_AGENT = """## Current Situation

A person is speaking with you through {source_kind} and can answer if asked.

- A change the person states as required is your instruction to make it within the current scope; do not merely agree, propose it, or wait to be asked again.
- Context you cannot see — an unclear referent, an earlier exchange, anything a new session or compaction dropped — is context to recover, never a limitation to report. Recover it, answer as though you had it, and ask only for what is still missing and still blocking.
- Recovering context is not progress: never announce a lookup or list what you searched. Send an update for a result, a decision, a blocker, or when status is asked for.

## Messages and Attachments

- Recover context with `messages {agent_name} --search "<relevant words>" --full`, then `messages {agent_name} --full` for the recent ones. Both read every conversation this agent has had: never narrow them to one channel or conversation, and look nowhere else — nothing else holds this history.
- Answer only from `{source_kind}:{audience_id}` results, plus wider shared context your own instructions authorize by name; never read conversation files, and never repeat another person's or agent's private content outside its own audience unless it was authorized or a canonical shared source holds the same fact.
- Never report history as empty or unavailable, and never ask for what a lookup should have found. With no match, say the search found no match and ask only for what is missing.
- A file somebody attached is already on this machine: its path stands under their message after `Attached to this message, on this machine:`. Open it there, and never ask for a file you were sent.
- Attach a file or image with an absolute Markdown link — `[report](/absolute/path/report.pdf)`, `![preview](/absolute/path/preview.png)`. A plain path is not an attachment."""

#: The clock started this and **nobody is present**. It cannot clarify, but it may need earlier
#: messages to perform recurring review work, and its delivered report uses ordinary attachment
#: declarations. Those mechanics therefore remain here while person-conversation behavior does not.
SCHEDULE_TO_AGENT = """## Current Situation

The schedule "{schedule_name}" started this turn. Nobody is present; your final response is delivered to the intended recipient or destination.

- Do only what the schedule asks. Nobody can be asked for clarification, so report context you cannot resolve as a blocker.
- Make that response a complete, standalone account of what happened, including any failure or blocker.

## Messages and Attachments

- Review prior messages the task needs with `messages {agent_name} --search "<relevant words>" --full`, then `messages {agent_name} --full` for the recent ones. Both read every conversation this agent has had: never narrow them to one channel or conversation, and look nowhere else — nothing else holds this history.
- Answer only from `{source_kind}:{audience_id}` results; never read conversation files, and never repeat another agent's or audience's content.
- A file somebody attached is already on this machine: its path stands under their message after `Attached to this message, on this machine:`. Open it there, and never ask for a file you were sent.
- Attach a file or image with an absolute Markdown link — `[report](/absolute/path/report.pdf)`, `![preview](/absolute/path/preview.png)`. A plain path is not an attachment."""

#: Another agent handed this turn its task. **Still this agent, as itself** — its own home, memory,
#: skills and brain — so this composes on `CORE` like any other. What it adds is that the requester
#: is not a person, that nobody is present, that the delegation itself is the work contract, and
#: that the work stops with a reviewable internal handoff rather than a person-facing response.
#:
#: **A specialist is the turn that needs the least of this layer.** Its outcome, scope and
#: authority all arrive in the brief, so the rules a person-facing turn needs for recovering
#: context, judging what to say and deciding what to withhold have nothing to act on here. What is
#: left is the shape of the handback, and *nobody is present* — which is also why no separate
#: sentence forbids asking a question or waiting for an answer: there is nobody to ask.
#:
#: **It offers no team, and that is the depth rule** rather than a sentence asking nicely: an agent
#: answering a delegation is never shown anybody to hand work to, so handing it on is not something
#: it can decide to do. `build` withholds the listing for this trigger.
AGENT_TO_AGENT = """## Current Situation

The agent {caller_agent} delegated this work to you. Nobody is present; your final response returns to that agent alone.

- The delegation is your complete brief and the only source of your outcome, scope, and authority. Nobody is available to extend or clarify it; return a brief too thin to work from as the blocker, naming what you need.
- Complete and verify the work within it. Treat it as read-only unless it authorizes changes to files, systems, or external state.
- Return one handoff: the result first, then exact changed artifacts, the verification you ran and what it showed, material assumptions, and remaining limitations.
- Do not contact the original requester or delegate to another named Rundesk agent."""


#: What bounds the work, and what must be loaded before it starts. Product-owned process, not role
#: capability, project method, or memory policy.
#:
#: **Scope is stated as a closed set, because the openings were what leaked.** Project rules,
#: adjacent findings and a useful opportunity each read as a licence to do more, so they are named
#: and closed in the same sentence that names the scope, rather than left to a later prohibition.
#:
#: **Restating the project-rule opening beside the prohibition was tried and dropped.** On a
#: bounded request both measured providers already left an unrequested header alone; on an
#: open-ended one — *the totals are wrong somewhere, sort it out* — one of them added it either
#: way, on a clean agent and a clean checkout. Fifteen words that moved no probe are fifteen words
#: every turn pays for, so the rule stays stated once, where scope is granted.
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
#: **The order is the rule, and the heading carries it.** The project's rules are read first
#: because they are an input to which skills apply. "Before substantive action" was read as "before
#: changing anything" — turns listed the tree, opened task files and loaded project skills, then
#: read the rules that decide which skills apply — so the trigger is now the project access itself,
#: under a heading that says when the section applies. The agent's own home is excluded, so
#: ordinary context recovery is not a violation.
#:
#: **The rules are named as the first access rather than as something preceding all of them**,
#: because opening that file is itself a project access: a section that forbids every access and
#: then opens with one is a rule an agent has to reason its way around, and a rule reasoned around
#: is a rule applied unevenly.
#:
#: **The exclusions are inside the bullets they qualify.** "And no others" read as advice next to a
#: positive duty, and a granted development workflow was opened because the turn had read one file
#: on the machine. What is denied is the trigger, not the possibility: touching a file is not a
#: project, while a standalone development task outside any repository can still need the skill it
#: names.
OPERATING_RULES = """## Scope and Boundaries

Name what must be produced, changed, or reported, what completes it, and what proves it. That and the current request, schedule, or delegation are your whole scope and authority; nothing else expands them — not project rules, not adjacent findings, not a useful opportunity. Runtime access is {access_mode}: read permits inspection and reporting only; work permits only authorized changes.

- Deliver the smallest safe and effective change that produces the requested result and its proof. Add no further deliverables, refactors, cleanup, integrations, or follow-up work.
- Needing materially broader scope, authority, or access is an approval request — why, what you propose, and its impact — or a blocker where nobody can approve it.
- Never invent facts, capabilities, actions, or outcomes, and never expose secrets or sensitive information.

## Before Acting

The project's own rules are your first project access. Before any other — file, listing, metadata, plan, inspection, change, or verification:

- Read them in full. Your agent home is not project access, and non-project work has no project rules.
- From the skill descriptions, identify every skill applicable to this request and project, and no others. File access alone does not trigger a development skill; leave an unrelated grant unloaded.
- Load each applicable body, and the references it requires, through your provider's skill mechanism. A granted or listed skill is not a loaded one; one already loaded this session is not loaded again.
- If an applicable body or reference will not load, report that as a blocker rather than working from its description."""

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
- Work directly for ordinary conversation and simple documentation, formatting, or copy-only changes. Stay direct when the task is small or mechanical, needs your continuing ownership, or coordination would add more cost than value. Availability or skill names alone do not justify delegation.
- Apply these signals before loading delegation guidance. Do not load `delegating-work` merely because a team member is available. When named delegation is a genuine option, that skill is applicable: load its body before choosing a target or acting. It owns target selection, briefing, the asynchronous lifecycle, steering, resuming, and return review."""


#: The universal outcome gate follows conditional collaboration so a result cannot be called done
#: before any handback has been reviewed, and pending work cannot be left without a continuation.
#:
#: **Accepted is not done.** Every outcome worth a completion claim has proof that arrives after the
#: action: the command returns, the process starts, and the thing it was for is still unchecked. A
#: turn that reports the start as the finish is the failure named here, and it is not a property of
#: rollouts — it is what any action looks like from inside the turn that took it.
#:
#: **The continuation rule states the mechanism, because the prohibition alone did not hold.** Told
#: only that a background process is not a continuation path, a measured turn started one, started
#: a monitor over it, wrote *I will report as soon as it lands*, and ended — twice, on one provider,
#: because inside a harness that really does deliver such a notification the belief is correct and
#: only Rundesk's final-response boundary makes it false. Naming that boundary moved the same probe
#: to waiting for the result and reporting it, twice. The other provider passed either way.
#:
#: **A service that is the outcome has to survive the sentence that ends the turn.** The exception
#: licensing a process to keep running said nothing about outliving the turn, and a measured turn
#: obeyed every word of it — started a server, proved it with a real `200`, did not kill it — and
#: left the person a dead URL, because the child died with the turn that started it. One provider
#: reached for `nohup` unprompted and the other did not, which is what makes it a rule rather than
#: a habit to rely on.
#: **Durable state and resumption are separate.** Saved state lets a later turn recover the work;
#: an actual Rundesk resumption starts that turn. A long-running outcome needs both. Without a
#: blocker or resumption, ending would abandon the outcome, so the current turn keeps working.
OUTCOME_AND_CONTINUITY = """## Outcome and Continuity

- Verify every requested result, material claim, and reviewed handback before completion; commands and started processes are not proof. If checks remain, state what happened, what is verified, and what is unchecked.
- Sending the final response ends this turn. Saved state keeps context but starts no turn. Background commands, tool sessions, monitors, or child processes cannot resume you. Wait for results or schedule verification under condition 2. A process that is the requested outcome must outlive the turn.
- Send the final response only after one of four applies: (1) outcome and proof are verified; (2) unfinished work has saved state and a scheduled Rundesk continuation; (3) a named delegation runs and its answer starts a review turn; or (4) a material blocker prevents safe progress until an owner decision or external change. Otherwise keep working.
- Cross-turn work saves state, evidence, next action in a project artifact or active `tasks/` brief, not memory. An enabled `--ask` self-schedule starts the later turn. Final response names: completion, verified result; schedule, verified current result, future result and time; delegation, result awaited; blocker, needed decision or change. Omit mechanics."""


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
    said.append(("completion", _filled(OUTCOME_AND_CONTINUITY, variables)))
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
        if value is None:
            return found.group(0)
        # This value stands in a shell assignment in CORE. Quote it here, at the one substitution
        # boundary, so spaces, quotes, dollar signs, and command substitutions remain path bytes
        # rather than becoming shell syntax in the command an agent is told to run.
        return shlex.quote(str(value)) if name == "install_root" else str(value)

    return re.sub(r"\{(" + "|".join(re.escape(one) for one in VARIABLES) + r")\}",
                  replacement, str(template or ""))


def _bounded(text: str, at_most: int, variables: Optional[Mapping[str, object]]) -> str:
    """Fill one addition and keep at most `at_most` UTF-8 bytes without leaving broken text."""
    return _filled(text, variables).encode("utf-8")[:at_most].decode("utf-8", errors="ignore")
