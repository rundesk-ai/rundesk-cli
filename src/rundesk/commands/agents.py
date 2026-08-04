"""The named identity work is run for: making one, configuring it, asking it, diagnosing it.

An agent sits **above** the gateway and never beside it, and that direction holds here: this
resolves what an owner meant by a name and hands the rest over. `rundesk ask` runs a turn in
the terminal that asked rather than inside the agent's gateway — there is nothing to ask a
gateway with yet, and inventing one is not what the verb is for.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

from rundesk import ROOT as REPO_ROOT
from rundesk import __version__
from rundesk import agent as _agent
from rundesk import config
from rundesk import delegation as delegations
from rundesk import gateway as _gateway
from rundesk import migration
from rundesk import provider
from rundesk import schedule as schedules
from rundesk import standing
from rundesk import store
from rundesk import turn
from rundesk.commands import _as_table


#: How many lines of what a brain said went wrong a failed turn puts on the screen. A tail
#: rather than all of it: a brain that failed noisily can say a great deal, and what is
#: worth reading is almost always the last of it.
_TROUBLE_LINES = 6

def _brain_already_named(name: str, agents) -> bool:
    """Does this agent already say which brain answers for it?

    Records this rundesk will not read are **not** an answer of no. Asking them opens the
    store, which refuses what it does not understand — and asked without a guard, the
    ordinary repair (`rundesk add <name>`, no `--provider`, because the brain is already
    remembered) came out as a raw traceback for exactly the agent an owner was repairing.
    The refusal itself is reported a few lines below, by the code that already knows how to
    say it; this only decides whether to demand a brain, and a store nobody can read is not
    a reason to demand one.
    """
    try:
        return bool((agents.chosen(name) or {}).get("provider"))
    except (store.Unreadable, store.TooNew, store.Behind, migration.Failed):
        return True


def _identities(agents, machine) -> list[str]:
    """Every persisted spelling that command resolution must not split."""
    return sorted({*agents.identities(), *machine.described(root=REPO_ROOT)})


def cmd_add(args: argparse.Namespace, gateways, machine, agents) -> int:
    """Make an agent, and the one gateway that runs it (R-AGW-1).

    Making one that already exists puts back only what is missing (R-AGT-4). That is how an
    owner repairs a home they half deleted, and it must not be how they lose the rules they
    spent a month writing — so nothing that is there is written over, whatever is in it.

    Given the name of a gateway that has been running since before there were agents, this
    is also how that gateway gets one: what it wrote moves into the agent's own directories,
    so that afterwards there is one place rather than two that disagree. It moves nothing
    while that gateway is running, because a gateway reading one directory while every
    command reads another is the fault that makes a schedule silently never run.
    """
    given = args.name
    if not given:
        print("add: NAME REQUIRED — say what to call the agent", file=sys.stderr)
        print("        what there is already: rundesk agents", file=sys.stderr)
        return 1
    try:
        name = agents.creation_name(given, _identities(agents, machine))
    except agents.NotAnAgentName as why:
        print(f"{given}: INVALID NAME — {why}", file=sys.stderr)
        return 1
    knew = agents.exists(name)
    pending = agents.creation_pending(name)
    if knew and not pending and any((
        args.provider, args.model, getattr(args, "settings", None),
        getattr(args, "says", None) is not None,
    )):
        print(f"{name}: ALREADY MADE — use configure to change its defaults",
              file=sys.stderr)
        print(f"        like this:  rundesk configure {name} --provider <provider>",
              file=sys.stderr)
        return 1
    # **An agent with no brain cannot take a turn**, so it is not a thing to make. Asked here
    # rather than left to the first `ask`: a half-made agent that reports MADE and then
    # refuses everything is worse than a refusal now, and an owner who has to be told twice
    # was told the wrong thing first. Making one that *already* has a brain is a repair and
    # must not demand it again (R-AGT-4, R-AGT-18).
    if not args.provider and not (knew and _brain_already_named(name, agents)):
        print(f"{name}: NO BRAIN — say which one answers for this agent", file=sys.stderr)
        print(f"        like this:  rundesk add {name} --provider <provider>",
              file=sys.stderr)
        print("        a shipped one, or the path to a program you wrote", file=sys.stderr)
        return 1
    # Validate everything we can before making, adopting or changing anything. Provider
    # settings are deliberately opaque, but their shape and the adapter's executability
    # are ours to prove. A refusal leaves the previous whole configuration intact
    # (R-AGT-32).
    try:
        settings = _given(getattr(args, "settings", None))
        if args.provider:
            provider.program(args.provider)
    except (ValueError, provider.NotRunnable) as why:
        print(f"{name}: NOT SET — {why}", file=sys.stderr)
        return 1
    wrote = agents.standing_before(name)
    # Whether or not the agent already exists. An adoption that was refused leaves the
    # files where they were, and asking again is how an owner retries it — conditioning
    # this on the agent being new would make one refusal permanent, since the home would
    # exist ever after and nothing would look at the old directory again.
    if wrote:
        now = standing.of(name, gateways, agents)
        if now.running:
            print(f"{name}: NOT MADE — a gateway of that name is running (pid {now.pid})",
                  file=sys.stderr)
            print(f"        it has things to move, so stop it first: rundesk stop {name}",
                  file=sys.stderr)
            return 1
    try:
        made = agents.add(name, display_name=given)
    except config.Unreadable as why:
        # A configuration that cannot be read is never treated as absent: the skills this
        # agent would be given are stated there, and making it without them would be an
        # owner's decision silently ignored.
        print(f"{name}: NOT MADE — {why}", file=sys.stderr)
        return 1
    except (store.Unreadable, store.TooNew, store.Behind, migration.Failed) as why:
        # Repairing an agent whose records this rundesk will not read must say so rather
        # than raise: the one thing an owner does when an agent is broken is make it again,
        # and a traceback tells them nothing about which of the four this is.
        print(f"{name}: NOT MADE — {why}", file=sys.stderr)
        print(f"        its records are at {store.path_for(agents.directory(name))}",
              file=sys.stderr)
        return 1
    try:
        moved = agents.adopt(name) if wrote else []
    except agents.InUse as why:
        # The name was claimed between asking and moving. Nothing moved, and saying so is
        # the whole point: a half-adopted agent is the split this refuses to create.
        print(f"{name}: NOT ADOPTED — {why}", file=sys.stderr)
        print(f"        stop it and ask again: rundesk stop {name} && rundesk add {name}",
              file=sys.stderr)
        return 1
    chose = _chose(args, agents, name, settings)
    if knew and not made and not moved and not chose:
        print(f"{name}: ALREADY MADE — its home is as you left it")
        return 0
    print(f"{name}: MADE" if not knew else f"{name}: REPAIRED")
    print(f"        home: {agents.home(name)}")
    if made:
        print(f"        put there: {', '.join(made)}")
    if moved:
        print(f"        brought in what it wrote before it was an agent: {', '.join(moved)}")
    if chose:
        print(f"        reaches for: {chose}")
    return 0


def cmd_configure(args: argparse.Namespace, agents) -> int:
    """Change an existing agent's durable defaults without replacing it (R-AGT-31)."""
    name = args.name
    if not name:
        print("configure: NAME REQUIRED — say which agent to change", file=sys.stderr)
        return 1
    try:
        agents.checked(name)
    except agents.NotAnAgentName as why:
        print(f"{name}: INVALID NAME — {why}", file=sys.stderr)
        return 1
    if not agents.exists(name):
        print(f"{name}: NO AGENT — make it first with rundesk add", file=sys.stderr)
        return 1
    if not any((args.provider, args.model, getattr(args, "settings", None) is not None,
                getattr(args, "says", None) is not None)):
        print(f"{name}: NOTHING TO CHANGE — name a provider, model, setting, or instructions",
              file=sys.stderr)
        return 1
    try:
        settings = _given(getattr(args, "settings", None))
        if args.provider:
            provider.program(args.provider)
        chose = _chose(args, agents, name, settings)
    except (ValueError, provider.NotRunnable, store.Unreadable, store.TooNew,
            store.Behind, migration.Failed) as why:
        print(f"{name}: NOT CONFIGURED — {why}", file=sys.stderr)
        return 1
    print(f"{name}: CONFIGURED")
    print(f"        reaches for: {chose}")
    return 0


def _chose(args: argparse.Namespace, agents, name: str, settings: dict) -> str:
    """Keep whichever of provider, model and settings was named, and say what it is now.

    What was not named is left as it was, because naming a model later must not quietly
    forget the brain. Changing providers clears its old provider-specific defaults.
    """
    # `None` is "not named" and `""` is "take it off", which is why this asks whether it was
    # given rather than whether it is truthy: an owner clearing what an agent is told has
    # said something, and reading that as silence would leave the old text in place.
    says = getattr(args, "says", None)
    settings_were_given = getattr(args, "settings", None) is not None
    if not (args.provider or args.model or settings_were_given or says is not None):
        return ""
    keeping = agents.remember(name, provider=args.provider, model=args.model,
                              settings=settings if settings_were_given else None,
                              instructions=says,
                              replace_brain=bool(args.provider))
    said = keeping.get("provider") or "no brain yet"
    return f"{said} ({keeping['model']})" if keeping.get("model") else said


def _given(pairs) -> dict:
    """What an owner set, in either of the two ways it is worth being able to type.

    `--set effort=high` for one thing, and `--set '{"flags": ["--no-color"]}'` for a shape
    that is not one thing. **Nothing here reads what it means**: a value is taken as JSON
    when it parses as JSON and as the text that was typed when it does not, and that is
    the whole of the interpretation. Which of it a brain understands is between the owner
    and their brain, and rundesk being wrong about it is not a failure worth inventing.
    """
    given: dict = {}
    for one in pairs or []:
        said = one.strip()
        if said.startswith("{"):
            try:
                whole = json.loads(said)
            except ValueError:
                raise ValueError(f"'{said}' starts like an object and is not one")
            if not isinstance(whole, dict):
                raise ValueError(f"'{said}' is not a set of settings")
            given.update(whole)
            continue
        key, sep, value = said.partition("=")
        if not sep or not key.strip():
            raise ValueError(f"'{said}' is not <key>=<value>, nor an object")
        try:
            given[key.strip()] = json.loads(value)
        except ValueError:
            given[key.strip()] = value
    return given


def _delegated_instead(asking: str, to: str, prompt: str) -> int:
    """`rundesk ask <another agent>`, from inside a turn, admitted as a delegation.

    The same record `rundesk delegations <agent> ask <to>` writes, and refused in exactly
    the same places — a role execution may not, work already handed over may not, and the
    durable record settles the rest. Two ways in, one thing admitted, so a rule can never
    hold on one route and not the other.

    **What it says back is the whole difference from an ordinary ask**, and it says it
    plainly: no answer arrives in this turn, one arrives later to be reviewed.
    """
    if os.environ.get("RUNDESK_ROLE_RUN"):
        print(f"{asking}: NOT ASKED — a role execution cannot hand work to a named agent; "
              "the agent that put the role on does that itself", file=sys.stderr)
        return 1
    if os.environ.get("RUNDESK_DELEGATION"):
        print(f"{asking}: NOT ASKED — work another agent handed over cannot be handed on; "
              "use this brain's own subagents instead", file=sys.stderr)
        return 1
    try:
        record = delegations.ask(
            asking, to, prompt, os.environ.get("RUNDESK_RUN") or "",
            posture=os.environ.get("RUNDESK_POSTURE") or None,
        )
    except delegations.NotDelegable as why:
        print(f"{asking}: NOT ASKED — {why}", file=sys.stderr)
        return 1
    except (delegations.Unreadable, store.Unreadable, store.TooNew, store.Behind,
            migration.Failed) as why:
        print(f"{asking}: RECORDS UNREADABLE — {why}", file=sys.stderr)
        return 1
    print(record["id"])
    print(f"        {record['label']} — handed to {record['to']} as a delegation")
    print("        no answer comes back in this turn; you are woken to review one later")
    print(f"        steer or stop it:  rundesk delegations {asking} say|stop {record['id']}")
    return 0


def cmd_ask(args: argparse.Namespace, agents) -> int:
    """One turn for this agent, streamed to this terminal.

    It runs **here**, in the terminal that asked, rather than inside the agent's gateway —
    for the same reason a schedule run by hand does: there is nothing to ask a gateway
    with yet, and inventing one is not what this is for. Ending this command ends the
    brain and everything it started, because the whole tree is its own process group.

    What is shown and what is written down are not the same thing. The account keeps every
    record, whole; the terminal gets the answer, with what the brain was doing beside it —
    and never a tool's output, which can be a file's contents, a private path or a
    credential, and is not this command's to put on somebody's screen.
    """
    name, prompt = args.name, args.prompt
    if not name or not prompt:
        print("ask: WHO AND WHAT — say which agent, and what to ask it", file=sys.stderr)
        print('        for example: rundesk ask ava "what changed today?"', file=sys.stderr)
        return 1
    if not agents.exists(name):
        print(f"{name}: NO SUCH AGENT — nothing of that name has been made", file=sys.stderr)
        print(f"        make it: rundesk add {name} --provider <provider>", file=sys.stderr)
        return 1
    # **One agent asking another is a delegation, whichever verb was typed** (R-DEL-3).
    # Left alone, this ran a whole turn on somebody else's agent from inside a turn: no
    # record, no chain guard, no review owed, and the answering agent told a person had
    # asked. Every rule the feature is made of was one command away from being bypassed —
    # and `ask` is the command an agent reaches for, which is why this is the front door
    # rather than a refusal pointing at another one.
    #
    # Only from inside a turn, and only at somebody else: a person at a terminal is asking
    # for an answer now, and an agent asking itself is already in its own turn.
    asking = os.environ.get("RUNDESK_AGENT") or ""
    if os.environ.get("RUNDESK_RUN") and asking and asking != name:
        return _delegated_instead(asking, name, prompt)
    reaches = agents.chosen(name)
    named = args.provider or reaches.get("provider")
    if not named:
        print(f"{name}: NO BRAIN — nothing says which one answers for this agent",
              file=sys.stderr)
        print(f"        say which: rundesk add {name} --provider <provider>", file=sys.stderr)
        print(f"        or just this turn: rundesk ask {name} \"…\" --provider <provider>",
              file=sys.stderr)
        return 1
    try:
        settings = _given(getattr(args, "settings", None)) or reaches.get("settings")
    except ValueError as why:
        print(f"{name}: NOT ASKED — {why}", file=sys.stderr)
        return 1

    # **The clock's work, or a person's.** A schedule that names `rundesk ask` rather than a
    # prompt is still the clock's, and the gateway says which schedule through the one
    # variable it adds to a scheduled program's environment. Read here, where the command
    # adapts what it was invoked as, and handed on as an argument rather than reached for
    # further in.
    #
    # An explicit `--conversation` wins: somebody who named one has said where this belongs.
    # Otherwise a scheduled turn gets a conversation of its own, named for the schedule, and
    # **starts fresh every firing** — untouched, it landed in the terminal's own conversation,
    # so a run at three in the morning resumed the session its owner types into and left its
    # prompt and answer in the middle of it.
    clock = (os.environ.get(_gateway.SCHEDULE_IS) or "").strip()
    by_the_clock = bool(clock) and not args.conversation

    said = _Shown()
    try:
        outcome = asyncio.run(turn.carry(
            name, prompt, named,
            model=args.model or reaches.get("model"),
            settings=settings,
            posture=provider.READ if args.read_only else provider.WORK,
            conversation=clock if by_the_clock else (args.conversation or turn.TERMINAL),
            on=turn.SCHEDULE if by_the_clock else turn.TERMINAL,
            kind=turn.SCHEDULE if by_the_clock else turn.TERMINAL,
            fresh=args.fresh or by_the_clock,
            watching=said,
            steering=_steering() if args.steer else None,
            # What it is told before it reads a word: this turn's own, then the agent's
            # (R-AGT-16) — and, where the clock started this, what rundesk says about that
            # situation whatever they wrote (R-AGT-34). For a person at a terminal there is
            # nothing to add, because they are here.
            preface=agents.told(name, said=args.says,
                                regardless=schedules.by_default(clock) if clock else ""),
            source=turn.SCHEDULE if clock else None,
        ))
    except provider.NotRunnable as why:
        print(f"{name}: NO BRAIN THERE — {why}", file=sys.stderr)
        print(f"        what stands in the way: rundesk doctor {name}", file=sys.stderr)
        return 1
    said.done()
    print(f"        {name}/{outcome.run} — {_cost(outcome.tokens)}", file=sys.stderr)
    if not outcome.ok:
        print(f"{name}: TURN FAILED — {outcome.why or outcome.reason}", file=sys.stderr)
        # What the brain said went wrong, on the screen rather than only in a file. It is
        # kept apart from what the brain *reported* — that is the whole point of the two
        # streams — but keeping it apart is not the same as keeping it secret, and a turn
        # that failed with its one actionable line filed somewhere nobody looks is a turn
        # somebody is stuck on.
        for line in outcome.trouble[-_TROUBLE_LINES:]:
            print(f"        {line}", file=sys.stderr)
        print(f"        the whole of it: rundesk agents {name}", file=sys.stderr)
    return 0 if outcome.ok else 1


async def _steering():
    """Whatever else is typed while the turn runs, a line at a time.

    Read off a thread, because reading a terminal blocks and the turn is running on this
    loop — a blocking read here would stop the very thing the words are meant to reach.
    Ends when the input does, which closes what rundesk is saying and lets the brain
    finish.
    """
    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            return
        said = line.strip()
        if said:
            yield said


class _Shown:
    """A turn as it happens, on a terminal.

    The answer goes to stdout so it can be piped; everything else goes to stderr, so what
    comes out of `rundesk ask ava "…" > answer.txt` is the answer and not a commentary
    around it.
    """

    def __init__(self):
        self._answered = False

    def __call__(self, said: dict) -> None:
        kind = said.get("type")
        if kind == "text":
            self._answered = True
            sys.stdout.write(said.get("text") or "")
            sys.stdout.flush()
        elif kind == "tool":
            did = said.get("did") or "using"
            if did in provider.CONTINUITY.values():
                # What changed, and not which tool changed it (R-PRV-29). These four name
                # a file rather than an act, so the vendor's own word beside one reads as
                # `rules Write` — and which tool wrote it is the half nobody wanted.
                print(f"        · updated {did}", file=sys.stderr)
                return
            print(f"        · {did} {said.get('name') or ''}".rstrip(), file=sys.stderr)
        elif kind == "result" and not said.get("ok"):
            print("        · that did not work", file=sys.stderr)

    def done(self) -> None:
        if self._answered:
            sys.stdout.write("\n")
            sys.stdout.flush()


def _cost(tokens: dict) -> str:
    """What a turn cost, or that nobody said — never a cost of nothing (R-USE-7)."""
    if not tokens.get("reported"):
        return "what it cost was never reported"
    said = (f"{tokens.get('input', 0)} in, {tokens.get('output', 0)} out, "
            f"{tokens.get('cached', 0)} cached")
    # Only where the brain reported the split. Most do not, and a `0 written` on every one
    # of them would read as "wrote nothing to the cache" rather than "does not say".
    if tokens.get("written") is not None:
        said += f", {tokens['written']} written"
    return f"{said}, {tokens['model']}" if tokens.get("model") else said


def _running_old_code(name, gateways, agents) -> list:
    """Is this agent's gateway serving the release that is actually installed (R-AGT-21)?

    **A gateway holds the modules it imported when it started.** Replacing the files under
    a running one changes nothing it has already loaded, so it goes on serving the old code
    for everything it has and reads the new files only for whatever it has not imported
    yet — which is a version nobody can see it is on. An update stands them all down for
    exactly this reason, and the case that gets past it is the one an owner caused: a
    gateway started before the code was last replaced.

    Asked of the version the gateway wrote down when it started rather than of a file's
    modification time. It is the thing itself rather than a proxy for it, it costs a record
    this command already reads, and a checkout whose files are touched by anything at all
    would make the proxy cry wolf for ever.

    Reported as a fault rather than a note: the whole trap is that nothing says anything.
    """
    try:
        it = standing.of(name, gateways, agents)
    except Exception as why:   # noqa: BLE001 — a boundary; a diagnosis reports, never raises
        # **Said, not swallowed.** `gateway._held` deliberately re-raises an OSError that is
        # not a lock being held, so returning nothing here would let `doctor` print READY
        # for an agent whose gateway could not be looked at — a truthful-looking silence,
        # which is the one thing this command must never produce.
        return [_agent.Complaint(str(why), "what this agent's gateway is doing cannot be read",
                                 f"rundesk status {name}")]
    if not it.running or not it.version or it.version == __version__:
        return []
    return [_agent.Complaint(
        f"it started on {it.version} and this install is {__version__}",
        "this agent's gateway is running code that is no longer installed",
        f"rundesk stop {name} && rundesk start {name}",
    )]


def cmd_doctor(args: argparse.Namespace, gateways, agents) -> int:
    """Say what stands between an agent and a working turn (R-AGT-11).

    Starts no provider and changes nothing (R-AGT-12): an owner asking what is wrong is
    usually asking because something already is, and a check that repaired what it found
    would answer a different question the next time it was asked.
    """
    names = [args.name] if args.name else agents.known()
    if not names:
        print("no agents")
        return 0
    worst = 0
    for name in names:
        try:
            said = agents.diagnosed(name, runnable=provider.program)
        except agents.NotAnAgentName as why:
            print(f"{name}: INVALID NAME — {why}", file=sys.stderr)
            worst = 1
            continue
        said = said + _running_old_code(name, gateways, agents)
        if not said:
            print(f"{name}: READY")
            continue
        worst = 1
        print(f"{name}: NOT READY", file=sys.stderr)
        for one in said:
            print(f"        {one.said}: {one.about}", file=sys.stderr)
            # What to do about it, under the thing it is about (R-AGT-19). An owner running
            # this is already asking because something is wrong; leaving them to work the
            # command out from the fault is asking them to diagnose it twice.
            if one.fix:
                print(f"            fix: {one.fix}", file=sys.stderr)
    # Per page, where a *new* agent's would come from (R-AGT-26). Said once for the install
    # rather than once per agent, because it is a fact about this machine and not about any
    # one of them — and said only when an owner has overridden something, since a list of
    # five identical "install" lines every time is a list nobody reads.
    from_each = agents.where_each_page_comes_from()
    if any(whose == "owner" for _called, whose, _at in from_each):
        print("templates a new agent would be made from:")
        for called, whose, at in from_each:
            print(f"        {called}: {whose} ({at})")
    if _cannot_search(names, agents):
        # A fact about the machine rather than a fault of any agent, so it is said here
        # and is not a complaint: this SQLite was built without FTS5. Said by the command
        # an owner runs to find out what is wrong, because the alternative is `search`
        # answering nothing and reading exactly like there being nothing to find (R-STO-8).
        print("searching: UNAVAILABLE — this machine's sqlite cannot search by the words "
              "in something")
        print("        every run is still listed, read and queried:  rundesk runs <agent>")
    return worst


def _cannot_search(names, agents) -> bool:
    """Whether this machine can search at all, asked of the first agent that can answer.

    Asked rather than assumed, and asked once: it is a property of the SQLite this Python
    was built against, so every agent on the machine gives the same answer, and an agent
    whose records cannot be opened has no answer to give rather than a negative one.
    """
    for name in names:
        try:
            return not agents.reading(name).searchable()
        except Exception:   # noqa: BLE001 — an agent that cannot answer is not an answer
            continue
    return False


def cmd_agents(args: argparse.Namespace, gateways, machine, agents) -> int:
    """Every agent, and what each is doing. The table you look at first.

    Answered by the gateways themselves rather than by the machine, because the machine
    cannot tell a gateway that is working from one that is up and stuck (R-GW-9).

    A gateway that has been running since before there were agents is listed too, marked
    as having none. Leaving it out would be the worst of both: still running, still holding
    a name, and invisible to the one command that says what this install has.
    """
    if args.name:
        return _one_agent(args.name, gateways, machine, agents)
    has_supervisor = machine.available()
    described = set(machine.described()) if has_supervisor else set()
    found = {name: standing.of(name, gateways, agents)
             for name in standing.every_name(gateways, machine, agents)}
    if not found:
        print("no agents")
        print("        make one:  rundesk add <agent>")
        return 0
    rows, orphaned = [], []
    for name in sorted(found):
        it = found[name]
        if not agents.exists(name):
            orphaned.append(name)
        # Whether the supervisor is keeping this gateway is asked of the supervisor. A
        # job description sitting in a directory is not a job being kept, and the two
        # come apart exactly when something has gone wrong — which is when it is read.
        try:
            kept = has_supervisor and name in described and machine.loaded(name)
        except machine.Unsure:
            kept = None   # asked, and not told — which is not the same as "no"
        run_home = agents.resolved(name).run
        doing = gateways.what_is_working(name, run_home) if it.running else {}
        turning = gateways.what_is_turning(name, run_home)
        # A loaded job is one fact; the gateway process and PID are another (R-GW-34).
        # Calling the first "supervised" claimed a relationship the machine never proved:
        # a manually started same-name process can coexist with a loaded dormant job.
        job = "LOADED" if kept else ("UNKNOWN" if kept is None else "NOT LOADED")
        rows.append((
            # The name, and only the name. A marker in this cell makes the column stop
            # holding what it says it holds — anything reading the table by name stops
            # finding one, which is exactly how CI came to report a running gateway as
            # never started. Which of them have no agent is said under the table, where
            # there is room to say what to do about it.
            name,
            ("WEDGED" if it.stale else "RUNNING") if it.running else "STOPPED",
            str(it.pid) if it.running else "-",
            _how_long(it.started) if it.running else "-",
            job,
            _version_of(it),
            # "?" rather than a count where the record could not be read: counting the
            # marker would report one process that may not exist.
            ("?" if gateways.could_not_be_read(doing)
             else str(len(doing))) if it.running else "-",
            str(len(turning)) or "-",
            # What never finished, counted where somebody looks (R-GW-39). The store
            # answering that question has existed since work could be interrupted at
            # all, and nothing in the product ever read it back: "what did not finish"
            # meant reading JSON out of a directory by hand, during an incident.
            str(len(gateways.what_was_interrupted(name, agents.resolved(name).logs)) or "-"),
        ))
    _as_table(("AGENT", "STATE", "PID", "UPTIME", "LAUNCHD JOB", "VERSION",
               "PROCESSES", "TURNS", "UNFINISHED"),
              rows)
    for name in sorted(found):
        run_home = agents.resolved(name).run
        it = found[name]
        working = gateways.what_is_working(name, run_home) if it.running else {}
        turning = gateways.what_is_turning(name, run_home)
        if not working and not turning:
            continue
        print()
        print(f"{name}:")
        details = [
            ("ADAPTER" if work.startswith("channel:") else "PROCESS",
             work.removeprefix("channel:"), "-", str(how.get("pgid") or "-"), "-")
            for work, how in sorted(working.items())
        ]
        details.extend((
            "TURN",
            f"{row['source']}:{row['surface']}",
            row["conversation"],
            str(row["pid"]),
            _how_long(row.get("since")),
        ) for row in turning)
        _as_table(("KIND", "SOURCE", "CONVERSATION", "PID", "ELAPSED"), details)
    if orphaned:
        print()
        print(f"no agent yet — running since before there were any: {', '.join(orphaned)}")
        print(f"  give one an agent:  rundesk add {orphaned[0]}")
    return 0


def _one_agent(name: str, gateways, machine, agents) -> int:
    """What one agent is, and every place it resolves.

    The paths are the point. Which install, which run state, which schedules and which log
    are authoritative is otherwise something an owner works out by reading the source, and
    it is exactly what they need when a supervised agent and a command disagree.
    """
    try:
        where_it_is = agents.paths(name)
    except agents.NotAnAgentName as why:
        print(f"{name}: INVALID NAME — {why}", file=sys.stderr)
        return 1
    if not agents.exists(name):
        print(f"{name}: NO SUCH AGENT", file=sys.stderr)
        print(f"        what there is:  rundesk agents", file=sys.stderr)
        return 1
    it = standing.of(name, gateways, agents)
    print(f"{name}: " + (("WEDGED" if it.stale else f"RUNNING (pid {it.pid})")
                         if it.running else "STOPPED"))
    _as_table(("WHAT", "WHERE"),
              [(what, str(at)) for what, at in sorted(where_it_is.items())])
    # What never finished, with the time and the reason for each (R-GW-39). Told apart by
    # whether rundesk could show the work was definitely gone: one of them is over, and
    # the other may still be running with nobody owning it, which is a different problem
    # and a different thing to do about it.
    unfinished = gateways.what_was_interrupted(name, agents.resolved(name).logs)
    if unfinished:
        print()
        _as_table(("UNFINISHED", "AT", "ENDED", "WHY"), [
            (work, str(how.get("at", "-")),
             "yes" if how.get("ended") else "unproven", str(how.get("why", "-")))
            for work, how in sorted(unfinished.items())
        ])
    return 0


def _version_of(it) -> str:
    """Which version this gateway is actually running (R-GW-9).

    Asked of the gateway's own record rather than of this install, because the two come
    apart exactly when it matters: an update replaces the files while a gateway keeps the
    code it already imported, so `rundesk version` says one thing and the thing actually
    serving is another. Marked rather than merely shown, since a number a reader has to
    compare against another number by eye is a difference nobody notices.
    """
    if not it.running or not it.version:
        return "-"
    return it.version if it.version == __version__ else f"{it.version} (old)"


def _how_long(started: float | None) -> str:
    """How long it has been up, in the shortest form that is still exact enough."""
    if not started:
        return "-"
    seconds = max(0, int(time.time() - started))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"
    return f"{seconds // 86400}d{(seconds % 86400) // 3600:02d}h"
