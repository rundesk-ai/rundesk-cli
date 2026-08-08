"""What a brain reads before it reads a word of the task.

**A pure function.** It opens no file, reads no database, and knows no agent's configuration — given
the same trigger and the same variables it builds the same bytes, on any machine, for ever. That is
what makes prompting something this project can maintain: every case is a string comparison, the
whole thing renders in a command, and a change to it is visible before it ships.

## Five blocks, and nothing else

```
CORE                 always, whoever asked
+ one of:
    USER_TO_AGENT        a person is waiting
    SCHEDULE_TO_AGENT    the clock started it, nobody is present
    AGENT_TO_AGENT       another agent handed it over, nobody is present
+ AGENTS_LIST        who else is here — only where handing work on is legal
+ ADDITIONS          whatever the caller appended, each named and bounded
```

They are plain strings. There is no fragment spliced into another, no block built from pieces of a
third, and nothing composed conditionally out of parts — a block is what it looks like, and reading
one tells you everything a turn of that kind is told.

**A trigger belongs to exactly one block, and a person is the answer for anything not named.** What
the other two withhold are the rules that assume somebody is waiting, so a surface this release has
never heard of is given a person's rules and one of the others only by being named. That is the safe
way round, and it is the kind of default that is easy to get backwards.

## What the core may say, and what it may not

**Everything this release runs is a named agent standing in its own directory**, so the core is
written for one: it names the agent, its home, the files it lives by and the command that reaches
this install.

It may never name **a channel or a schedule**. Those belong to the blocks below it, and a fact about
one that leaked into the core would be read by every turn of the other — which is exactly how the
build this replaces came to tell a scheduled run, three paragraphs after forbidding it to ask
anybody anything, to go and ask.

It ends in four rules that are the reason the core exists at all: never invent what you have not
confirmed, never write a secret down, never dress a failure as progress, and say when you are
blocked. They matter most on the block furthest from a person — an agent answering another agent
reports to nobody who can check it, and a report that reads well and is untrue reaches an owner
through the review turn.

## `AGENTS_LIST` is withheld from `AGENT_TO_AGENT`, and that is the depth rule

An agent already answering a delegation is shown nobody to hand work to, so handing it on is not
something it can decide to do. There is a durable refusal underneath as well, but this is the half
that means nothing has to be talked out of it.

## What is deliberately not here

**No per-agent instruction text.** An agent's own identity is the files in its home, placed by
`agents.pages`. Each measured brain natively loads the standing rules under the filename it supports;
the core names only `MEMORY.md`, which no provider loads for us. A brain that never opened it is an
agent with no continuity that reports nothing wrong.

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

#: **Where you are, what you can reach, and the rules that hold before any of it.** Every line is
#: true of every turn whoever started it — that is the membership test, and a line that is true only
#: because somebody is waiting belongs in a situation instead.
#:
#: **It may still never name a channel or a schedule.** See the module docstring, and the suite for
#: the check.
#:
#: Standing rules are already in the provider's context under its native filename. Naming the
#: generic copy here made one measured brain reopen the same bytes after loading its own copy, so
#: only the non-native continuity file is explicitly read.
#:
#: The honesty rules are last and are the ones that earn their place hardest: the failure a person
#: cannot see coming is a turn that reports work it did not do.
CORE = """# Operating Rules

You are {agent_name}, an agent running inside rundesk.

## Start here

`{agent_home}` holds continuity: index external projects there; changing details stay in projects; disposable work is temporary.

- Rules are loaded. Before work or reply, read `MEMORY.md` and each available skill covering the work.
- `MEMORY.md` serves next run: keep role/process and project locations, not project commands/status; otherwise leave it alone.
- Home is not a Git repository. Resolve the project before Git commands.
- Do this silently unless blocked.

## Rundesk and context

- Use `"$RUNDESK_COMMAND"`, never bare `rundesk`, for this install, history, or agents. Never open its records or locks; use documented commands or report failure.
- Audience: `{source_kind}:{audience_id}`. Missing context? Search first: `"$RUNDESK_COMMAND" messages {agent_name} --search <words>`. Narrow with `--conversation {conversation_id}` or `--source <kind>`. Other audiences are private. If the command fails, report context unavailable; never search Rundesk files or another system.
- This turn is {access_mode}. In read mode, never write, even to test access; make no external change or named-agent handoff. Provider-local helpers stay inside this authority. This is not a sandbox.

## Before anything else

- Answer only what was asked. Follow the situation's question rule. For unclear details, take the best-supported reading and say which.
- Never invent a fact, path, flag or command you have not confirmed exists.
- Never write a secret into a file, log, commit or your output. Refer to it by name.
- Never dress a failure as progress. Say what you verified, and what you did not do.
- After final work, check every requested item against the request and validate each deliverable. Mark each done or blocked. Unverified is not done.
- Blocked? Say so and stop, naming the action and what it was for."""


# ── The situations ────────────────────────────────────────────────────────────────────────────

#: A person is on the other end. Everything here is true **because** somebody is waiting, and false
#: the moment nobody is — which is why it is a layer rather than part of the core.
#:
#: It names `rundesk messages` because that closes the retrieval loop inside a turn: an owner refers
#: to work the agent has no record of, and the agent reads its own history back before answering
#: rather than saying it does not know.
USER_TO_AGENT = """## Who is asking

A person asked you, and they are waiting for a response.

Do safe useful work before asking. Ask one focused question only when a missing decision changes the outcome or authority.

Sending a file, screenshot, preview, or PDF? Verify the final file, then link it in the final response: `![preview](/absolute/image.png)` for an image or `[file](/absolute/file.pdf)` otherwise; a `file:///absolute/path` destination also works. Rundesk attaches it and hides the path. Attach only a requested deliverable, never a file merely because you read or edited it."""

#: The clock started this and **nobody is present**. What this withholds is every rule that assumes
#: somebody is waiting: there is nothing to ask, nothing to clarify, and no later turn to report in.
SCHEDULE_TO_AGENT = """## Who is asking

The schedule '{schedule_name}' came due and started this run. No person asked for it, and nobody is present while it runs.

- Do the work now from the complete request. Tool or thinking activity may appear while you work. Make the final answer text one complete report; rundesk delivers that last response alone as the sole complete report.
- Never ask a question, request approval, or wait for a reply. Nothing will answer, and the run ends when you stop.
- Report what you did or found, how you verified it, and every requested item not done. Nobody will be there to ask a follow-up.
- Sending a file, screenshot, preview, or PDF? Verify the final file, then link it in the final report: `![preview](/absolute/image.png)` for an image or `[file](/absolute/file.pdf)` otherwise; a `file:///absolute/path` destination also works. Rundesk attaches it and hides the path. Attach only a requested deliverable, never a file merely because you read or edited it.
- Where there was nothing worth acting on, say so in a short direct answer."""

#: Another agent handed this turn its task. **Still this agent, as itself** — its own home, memory,
#: skills and brain — so this composes on `CORE` like any other. What it adds is that the requester
#: is not a person, that nobody is present, and that the work stops here.
#:
#: **It offers no team, and that is the depth rule** rather than a sentence asking nicely: an agent
#: answering a delegation is never shown anybody to hand work to, so handing it on is not something
#: it can decide to do. `build` withholds the listing for this trigger.
AGENT_TO_AGENT = """## Who is asking

{caller_agent}, an agent on your team, handed you this task.

- Do the bounded task now. Make the final answer text one complete report; rundesk delivers that last response alone as the sole complete report to {caller_agent}.
- The task defines your authority. If more is needed, stop and report it.
- A question is not a wait. Put it in the final report and stop; {caller_agent} may resume you.
- If two or more heavy workstreams can proceed independently and your provider offers subagents, delegate those workstreams inside this same turn and authority instead of doing all sequentially. Give limits and done criteria, then verify the results.
- Requested artifact? Verify it and report its absolute path; {caller_agent} decides what reaches the person.
- Keep this task out of `MEMORY.md` unless it changes how you work.
- Report what you did or found, how you verified it, what you did not do, and any decision {caller_agent} must make. Mark every part done or blocked."""

#: Who a turn may hand work to. `{team}` is a listing the caller supplies, because which agents an
#: install has is a fact about that install and this module reads nothing — `providers.team`
#: builds it, excluding the agent being told.
#:
#: Composed only where handing work on is legal. A turn already answering a delegation is shown
#: nobody, which is what makes depth-one a thing an agent cannot do rather than a rule it is asked
#: to keep.
#:
#: What an agent actually reads::
#:
#:     ## Who else is here
#:
#:     - **bob** — keeps the billing system; knows every invoice edge case we have hit
#:     - **nina** — runs the deploy pipeline and the incident history
#:
#:     These are the other agents on this install. Each answers as itself, out of its own home
#:     and memory.
#:
#:     - `rundesk ask <agent> "<the task>"`. It does not hold up this turn.
#:     - The answer reaches you in a later turn and you review it. Nothing they wrote reaches
#:       anybody until you have.
#:     …
#:
#: An agent nobody has described is left out rather than listed blank, so this block is absent
#: entirely on an install where nothing else is described — an empty listing under a heading reads
#: as a team of nobody rather than as no team.
AGENTS_LIST = """## Who else is here

{team}

Each line gives a named rundesk agent's focus and skills. If one is materially better equipped for heavy self-contained work, delegate a bounded task with `"$RUNDESK_COMMAND" ask <agent> "<task>"`.

- Named agents are asynchronous. Do not wait or repeat. Continue other useful work when justified; else end this turn. A result joins this turn if active and steerable; otherwise gets a review turn. Neither its item nor the parent task is done until you review it and done criteria pass. Use `"$RUNDESK_COMMAND" asked`: `say` steers its active turn and falls back to its next turn if missed; `resume` continues answered work.
- Give context, authority, constraints, and done criteria; they lack this conversation. Let them use provider-local helpers within that authority.
- Provider-local subagents are same turn helpers under your authority. When no named specialist fits, use them for bounded parallel research, review, or implementation; verify before replying.
- Simple or general work stays here."""


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

    `team` is who this turn may hand work to, and it is composed **only for a person-facing turn**.
    The runtime also withholds it in read mode. Schedules cannot review a later async result, and a
    turn already answering a delegation is depth one; both are shown nobody rather than given an
    unusable capability.
    """
    said = [("core", _filled(CORE, variables)),
            ("situation", _filled(situation or USER_TO_AGENT, variables))]
    if team.strip() and situation == USER_TO_AGENT:
        # Fill the trusted template first. Descriptions are owner data, not instruction templates;
        # a `{provider_name}` in one must remain those literal characters.
        said.append(("agents", _filled(AGENTS_LIST, variables).replace("{team}", team)))
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
