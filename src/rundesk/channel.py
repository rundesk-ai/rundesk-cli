"""The seam a surface is reached through, and nothing about any particular platform.

An adapter is a **program** rundesk runs, never code it loads (R-CAD-1). The mirror image
of the seam a brain is reached through, and the same design for the same reasons: rundesk
never puts a stranger's code inside the gateway that runs every other agent, an adapter can
be written in anything, and a surface nobody here has heard of is reached by exactly the
seam a shipped one is.

**Nothing is enumerated here.** There is no list of platforms and no list of what one
needs. A kind is a name carried through — a shipped adapter, or a path to a program
somebody wrote — and whatever that platform calls its places arrives as options this file
never parses and hands straight back (R-CAD-13). If a platform's word shows up in this
file, the seam has already failed.

Two things cross this seam that the surface does not get to decide, and both are here
because two adapters deciding them separately would eventually disagree about the same run:

- **What state a turn is in is rundesk's** (R-CAD-3). An adapter is told, and chooses only
  how its platform shows it (R-CAD-4).
- **What an adapter is shown is rundesk's.** Work goes out while it happens and prose does
  not, so an adapter is never handed a part-written answer — which makes showing half a
  sentence impossible rather than merely discouraged (R-CH-7, R-CH-8).

The contract is written for a stranger in
`docs/extending/channel-adapters/references/the-contract.md`.
**That reference is the specification and this file is an implementation of it** — where
the two disagree, the reference is right.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from rundesk import gateway, instructions, process, provider

#: Where the adapters that ship with rundesk stand. Read by looking rather than listed, so
#: one added later is reachable the day it lands and no second copy of the list can come to
#: disagree with the directory.
ADAPTERS = Path(__file__).resolve().parent.parent / "channels"

#: What an adapter reports, and the whole of it (R-CAD-1, R-CAD-17). A query is kept
#: apart from both a message and a control: it starts no brain turn and changes nothing,
#: but still crosses the authorization boundary before Rundesk answers it.
ARRIVING = ("ready", "arrived", "control", "configure", "query", "gone")

#: What each of those must carry to mean anything. A record missing one of them is not a
#: partial record to be patched up — it is one nothing can be done with, and passing it on
#: would put the decision about what it meant somewhere further from the adapter that
#: knows. Whole records or nothing, in both directions.
NEEDED = {
    "ready": (),
    "arrived": ("conversation", "user", "text"),
    "control": ("conversation", "user", "control"),
    "configure": ("conversation", "user", "provider", "ref"),
    "query": ("conversation", "user", "query", "ref"),
    "gone": (),
}

#: What somebody attached to a message, once the adapter has put it somewhere on this
#: machine (R-CH-17). A path and never a link: the brain that will read it runs here, has
#: no credential for anybody's platform, and asking it to fetch one would be asking it to
#: reach the network on a stranger's say-so.
#:
#: Kept out of `NEEDED` because a message with nothing attached is the ordinary one.
ATTACHED = "attachments"

#: What the surface calls the place this was said, and the person who said it — as it shows
#: them to a human, not as it stores them (R-CH-21). A brain was being handed the words and
#: nothing else, so it answered every conversation as though it were the only one: it could
#: not tell a room from a direct message, and the person it was talking to was an opaque
#: number it never saw.
#:
#: Optional, and separately so. A surface that has no name for either says neither and the
#: turn is exactly what it was before. What is here is never a control: the answer goes
#: where the conversation is, which is rundesk's to decide and not the sender's to say.
WHERE, CALLED = "where", "called"

#: What an owner has this agent told about where it is, before it reads a word of what
#: somebody typed (R-CH-22). One piece of text, because a channel is already one place.
#:
#: **It was briefly three, keyed by situation** — one said every time, one for a direct
#: message, one for a room — and that was a conditional language invented to paper over a
#: single channel that had been pointed at everything. A channel record already *is* a
#: scope: `--dm` takes direct messages, `--server` and `--channel` confine to a room. An
#: owner who wants both wants two channels, and gets two allow-lists with them, which is
#: what they wanted anyway — the people who may speak to an agent in a public room are not
#: the people who may speak to it in private. With one channel per surface there is no
#: branch left to write, and nothing here has to explain, get right, and keep right the
#: rules for composing one.
INSTRUCTIONS = "instructions"

# Optional per-arrival adapter hooks. An override replaces only the channel-specific
# instruction; an append follows it. Rundesk's core instructions are never replaceable.
PROMPT_OVERRIDE = "prompt_override"
PROMPT_APPEND = "prompt_append"
# One exact adapter-owned prompt that its current trigger supersedes. This exists for
# adapters migrating defaults they previously stored as owner instructions: only an exact
# match is omitted, so anything the owner changed remains additive.
PROMPT_REPLACES = "prompt_replaces"

# Optional standardized context supplied by an adapter. These are communication concepts,
# never platform concepts; Discord's server, for example, is a parent place here.
ADAPTER_VARIABLES = (
    "channel_name", "channel_id", "channel_parent_name", "channel_parent_id",
    "channel_thread_name", "channel_thread_id",
)

#: What an owner may write `{like this}` and have filled in. Closed, because a name that is
#: not here is a typo, and a typo that silently becomes empty is an instruction that quietly
#: stopped saying what it said. Refused when it is written, not when a turn runs.
FILLED = instructions.STANDARD_VARIABLES
# Names accepted before the standardized vocabulary. Existing owner instructions keep
# rendering, while new adapters and documentation use the communication-agnostic names.
LEGACY_VARIABLES = ("kind", "channel", "where", "called", "conversation")

#: The pieces `where` was made of, each written `{where.channel}`. `where` on its own is the
#: whole phrase the surface would show a person — "#ops on the Acme server" — and a phrase
#: is all an owner could use it as: there was no way to name the room without dragging the
#: server along with it.
#:
#: **Which pieces exist is the adapter's to say, never this file's.** They are declared by
#: `--check` and kept in the channel's record, so a misspelt one is still refused the moment
#: it is written — the core never learns that Discord has servers, and a surface with a
#: different shape of place declares a different shape of parts.
PARTS = "parts"
WHERE_IN = "where."
FILLS = "fills"

#: The kinds of place a surface comes in, as the adapter itself names them (R-CAD-15).
#: A platform is rarely one place: Discord has private messages and rooms full of people,
#: and they are not the same thing to talk in. **Each is its own channel**, because a
#: channel carries who may reach the agent through it — and the people who may speak to an
#: agent in a public room are not the people who may speak to it in private.
#:
#: Reported by `--check`, so the core never learns what kinds of place any platform has. An
#: adapter that reports none is a whole adapter and gets exactly one channel, which is what
#: every adapter did before this existed.
SHAPES = "shapes"
SHAPE_AT = "suffix"

#: How many one `add` may make. A bound rather than a belief: an adapter that reported a
#: thousand shapes would otherwise write a thousand records under one command.
SHAPES_MOST = 8

#: How much one externally supplied instruction layer may carry. Each layer is bounded at
#: ingestion; the completed stack is not clipped, because doing so would silently replace
#: whichever later append-only layers fell beyond the boundary.
INSTRUCTIONS_MOST = 4000

#: How much of either is carried. These are a stranger's words on their way into a prompt,
#: so they are clipped and flattened to one line — a display name is a place somebody can
#: write whatever they like, including something shaped like an instruction.
SAID_MOST = 80

#: How many attachments on one message are carried through, and how much of one. A chat
#: platform will accept far more than a turn can use, and an agent's workspace is not
#: somewhere a stranger gets to fill.
ATTACHED_MOST = 10
ATTACHED_BYTES = 32 * 1024 * 1024

#: What an adapter is told, and the whole of it. Four of these are the brain's own records
#: passed through in the words no brain owns; `state` and `answer` are rundesk's.
#:
#: **`text` is deliberately not here.** A brain writing its reply a fragment at a time is
#: held and handed over once, as `answer` — an adapter cannot show a reply that rewrites
#: itself in place, because it is never given one to show (R-CH-7, R-CH-8).
#:
#: `said` is the other half of that: a *complete* thing a brain said while it was still
#: working. Holding those to the end was the same rule applied too widely — an agent that
#: says "I will look at the logs" and then, a minute later, what it found, is writing the
#: way a person does, and both arriving at once loses the first one's whole purpose. The
#: last thing it says is still the `answer`, because that is the one somebody replies to.
TELLING = ("state", "think", "tool", "result", "usage", "said", "answer",
           "configure-result", "query-result")

#: What a tool did, in the words a surface shows. **The provider seam's list, not a
#: second copy of it** — a brain says what it did and a surface shows it, so the two must
#: be the same five words or a reader is shown a verb nothing produces, or a brain
#: produces one nothing can show. Taken from where it is defined rather than repeated
#: here, because a vocabulary written down twice is two vocabularies (R-PRV-8).
DID = provider.DID

#: How a turn stands, decided here and shown there (R-CAD-3, R-CAD-4). Told apart because
#: each sends whoever is watching somewhere different: `TAKEN` says it was heard, `RUNNING`
#: keeps saying so for anything that lapses, and the last three are how it ended — which
#: matters because "it stopped" and "it broke" are different news about the same silence.
TAKEN = "taken"
RUNNING = "running"
FINISHED = "finished"
STOPPED = "stopped"
FAILED = "failed"
STATES = (TAKEN, RUNNING, FINISHED, STOPPED, FAILED)

#: What a gesture may be (R-CH-9, R-CH-10, R-CH-16). None of them is an approval: they are
#: about the conversation, or about the agent, rather than about a brain's permission
#: model — which is what lets them exist before approvals do.
#:
#: `STOP` and `FORGET` are aimed at one conversation and touch nothing else. `RESTART` is
#: aimed at the agent, so it is the one gesture whose blast radius is larger than the
#: conversation it was made in — which is why it is spelled out here rather than being
#: something a surface could arrive at by combining the other two.
STOP = "stop"
FORGET = "forget"
RESTART = "restart"
CONTROLS = (STOP, FORGET, RESTART)

#: Read-only questions a surface may ask Rundesk itself (R-CAD-17). Closed for the same
#: reason controls are: an adapter may offer its own word for one of these, but it cannot
#: turn arbitrary command-line input into gateway access.
STATUS = "status"
VERSION = "version"
AGENTS = "agents"
HELP = "help"
QUERIES = (STATUS, VERSION, AGENTS, HELP)

#: What is asked of an adapter to find out whether it can reach what it was pointed at.
#: Unlike asking a brain what it can do, this one really does reach a network — that is the
#: whole point of it, and why it happens when a channel is added and never again.
CHECKING = "--check"

#: How long an adapter may say nothing while it connects, signs in and looks (R-CAD-9). A
#: window of silence and not a stopwatch, like everything else rundesk waits on.
CHECK_SILENCE_SECONDS = 60.0

#: The longest the checking may take however much it is saying. Silence cannot see a
#: program wedged in a loop that keeps announcing itself, which is the whole reason a
#: ceiling exists beside it (R-PROC-13). Generous against a slow platform, and finite
#: because a person is standing at a terminal waiting for this one.
CHECK_CEILING_SECONDS = 300.0


class NotRunnable(Exception):
    """There is nothing runnable where this kind of channel said there would be.

    The only way resolving a channel adapter fails. Not recognising a kind is not a
    failure — a surface rundesk has never heard of is the case this seam exists for.
    """


def program(named: str, adapters: Path | None = None) -> Path:
    """The program that speaks this kind of channel, or why there is not one.

    A path is used as it stands and anything else is looked for among the adapters that
    ship. The same rule a brain is resolved by, deliberately: `discord` and
    `/opt/my-channel` are the same kind of thing here, one of them merely happens to live
    in this repository.
    """
    where = ADAPTERS if adapters is None else adapters
    if not named:
        raise NotRunnable("no kind of channel was named")
    stands = Path(named) if (os.sep in named or named.startswith("~")) else where / named
    stands = stands.expanduser()
    if not stands.is_absolute():
        stands = stands.resolve()
    if not stands.is_file():
        raise NotRunnable(f"there is no channel at {stands}")
    if not os.access(stands, os.X_OK):
        raise NotRunnable(f"{stands} is not something this machine can run")
    return stands


def environment(
    home: Path,
    channel: str,
    agent: str,
    channel_home: Path,
    allow=None,
    settings: dict | None = None,
    secret: dict | None = None,
    environ: dict | None = None,
    path: str | None = None,
    checking: bool = False,
) -> dict[str, str]:
    """Everything an adapter is told, and the whole of it (R-CAD-13).

    Built on the environment every program rundesk runs gets, so an adapter is a program
    like any other and is given nothing extra by being one. What is *not* here is as
    deliberate as what is: no platform variable, because what a surface needs is that
    surface's adapter's business and putting it here would put the platform in the core.

    **One variable is let through from the owner's own environment, and only one** — the
    name the adapter itself gave back when it was checked (R-CAD-11). Everything a program
    rundesk runs gets is built rather than inherited, so a credential has to be named to
    arrive, and naming one is the adapter's own doing. The value is never written down
    anywhere and never comes back out (R-CAD-12).

    **`checking` is the one exception, and it is the owner's own shell.** An adapter being
    checked has not yet had the chance to say which variable it reads — that is what it is
    answering — so there is no name to let through and it would be asked to sign in with
    nothing. A check is a person at a terminal running a program they just chose to run,
    once, in their own shell: giving it what they exported is what running any command
    does. Holding one open unattended for weeks is not, which is why the tight environment
    is the one that lasts.
    """
    said = dict(environ if environ is not None else os.environ) if checking else {}
    said.update(process.environment(home, path=path))
    said["RUNDESK_CHANNEL"] = channel
    said["RUNDESK_AGENT"] = agent
    said["RUNDESK_CHANNEL_HOME"] = str(channel_home)
    if allow:
        # Who may use this channel is rundesk's to *enforce* and never the adapter's
        # (R-CH-4) — but a surface that greets its owner has to know which of them that
        # is, and one that showed the list to anybody would be handing out the list.
        # Told, so it can address them; not trusted, because nothing here reads it back.
        said["RUNDESK_ALLOW"] = ",".join(str(one) for one in allow if one)
    # Always set, empty object and all. The guide says all four of these are always
    # there, and an adapter that believed it and reached for the key rather than asking
    # politely for it crashed the first time it was held open with nothing configured —
    # which is exactly the case the guide's own smallest example produces. Sorted, so the
    # same settings are the same bytes every time; never read on the way past, because
    # what a platform needs is between it and its adapter.
    said["RUNDESK_SETTINGS"] = json.dumps(settings or {}, sort_keys=True)
    for one in (secret or {}).get("env") or []:
        found = (os.environ if environ is None else environ).get(one)
        if found:
            said[one] = found
    return said


def spoken(**it) -> bytes:
    """One thing said *to* an adapter, as a record it reads a line at a time.

    Sorted, so the same thing said twice is the same bytes and what crossed the seam can
    be compared with what was shown. One line each, with everything encoded, so a message
    with newlines in it is still one record.
    """
    return (json.dumps(it, sort_keys=True) + "\n").encode("utf-8")


def understood(said: bytes | str) -> dict | None:
    """One line, as one of the six records we know — or nothing, if it is not one.

    Nothing is refused here and nothing raises (R-CAD-1). A line we cannot read, a line
    that is not an object, a line of a kind we have never heard of, and a line of a kind we
    know that is missing what that kind means all come back the same way: `None`, meaning
    "keep it, act on nothing". The caller keeps the raw line either way, which is what
    makes an adapter's drift show up as something readable rather than as a silent gap.

    A `control` or `query` naming something that does not exist is refused for the same
    reason a missing field is: accepting an open vocabulary here would either guess at a
    destructive gesture or expose an arbitrary gateway operation.
    """
    try:
        it = json.loads(said)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(it, dict):
        return None
    kind = it.get("type")
    if kind not in ARRIVING:
        return None
    for wanted in NEEDED[kind]:
        if not isinstance(it.get(wanted), str):
            return None
        if not it[wanted] and wanted != "text":
            return None
    if kind == "control" and it["control"] not in CONTROLS:
        return None
    if kind == "query" and it["query"] not in QUERIES:
        return None
    if kind == "arrived":
        it[ATTACHED] = attached(it.get(ATTACHED))
        # A message is words, or something attached, or both — and a photograph sent with
        # nothing typed is the most ordinary message there is. Text was required to be
        # non-empty, so an adapter that dutifully reported one had it refused here and
        # said nothing, which is the worst of the three possible outcomes.
        if not it["text"] and not it[ATTACHED]:
            return None
        it[WHERE], it[CALLED] = plainly(it.get(WHERE)), plainly(it.get(CALLED))
        for key in (PROMPT_OVERRIDE, PROMPT_APPEND, PROMPT_REPLACES):
            value = it.get(key)
            it[key] = value.strip()[:INSTRUCTIONS_MOST] if isinstance(value, str) else ""
        for key in ADAPTER_VARIABLES:
            it[key] = plainly(it.get(key))
    return it


def plainly(said) -> str:
    """A name a surface shows, made safe to put in a sentence (R-CH-21).

    One line and a bounded one. A display name is chosen by whoever holds the account, and
    it reaches a brain inside a prompt — so a newline, which is how somebody would try to
    end our sentence and start one of their own, is not a character it gets to have.
    """
    if not isinstance(said, str):
        return ""
    return " ".join(said.split())[:SAID_MOST]


def attached(said) -> list:
    """What arrived with a message, as things that are really on this machine (R-CH-17).

    Anything that is not a readable file here is dropped rather than passed on. An
    adapter that reports a path it never wrote, or a link it expected somebody else to
    fetch, would be handing the brain an instruction to go and get something — and the
    brain runs on this machine with the owner's tools.
    """
    if not isinstance(said, list):
        return []
    found = []
    for one in said[:ATTACHED_MOST]:
        if not isinstance(one, dict):
            continue
        at = one.get("at")
        if not isinstance(at, str) or not at:
            continue
        stands = Path(at)
        if not stands.is_absolute() or not stands.is_file():
            continue
        found.append({"name": str(one.get("name") or stands.name), "at": str(stands)})
    return found


def surface(kind: str) -> str:
    """What to call this kind of surface, in a sentence a brain is going to read.

    `--kind` takes a shipped name *or* the path of a program, which is what makes a surface
    nobody here has heard of reachable exactly like one that ships. A shipped one is its
    own name. A path is its last part and nothing else: rendered whole, an owner's
    stranger-written adapter had a brain told it was "reached over
    /opt/acme/my-telegram-adapter", which reads badly and hands over a path on this machine
    that is no part of answering anybody.

    Not `provider.key`, which is next door and does a different job: that one names a
    *directory* and adds a hash so two adapters of one name stay apart. Here the two are
    the same surface as far as anybody talking to it is concerned, and a hash in a sentence
    is noise.
    """
    kind = str(kind or "").strip()
    if not kind:
        return ""
    if os.sep in kind or kind.startswith("~"):
        return Path(kind).expanduser().name or kind
    return kind


def preface(record: dict, agent: str, name: str, it: dict, append: str = "") -> str:
    """Build core, channel, adapter, and owner instructions for this arrival (R-CH-22)."""
    stored = record.get(INSTRUCTIONS)
    stored = stored.strip() if isinstance(stored, str) and stored.strip() else ""
    replaced = it.get(PROMPT_REPLACES)
    replaced = replaced.strip() if isinstance(replaced, str) and replaced.strip() else ""
    if stored and stored == replaced and _shipped_adapter(record.get("kind")):
        stored = ""
    arrived = it.get(PROMPT_OVERRIDE)
    override = arrived.strip() if isinstance(arrived, str) and arrived.strip() else None
    adapter_append = it.get(PROMPT_APPEND)
    adapter_append = adapter_append.strip() \
        if isinstance(adapter_append, str) and adapter_append.strip() else ""
    variables = prompt_variables(record, agent, name, it)
    return instructions.build(
        variables=variables,
        trigger=_trigger(it),
        override=override,
        append=(adapter_append, stored, append),
    )


def prompt_variables(record: dict, agent: str, name: str, it: dict) -> dict[str, str]:
    """Communication-agnostic builder variables plus legacy owner-written place parts."""
    parts = parts_of(it)
    where = plainly(it.get(WHERE))
    called = plainly(it.get(CALLED))
    channel_name = plainly(it.get("channel_name"))
    channel_parent_name = plainly(it.get("channel_parent_name"))
    channel_thread_name = plainly(it.get("channel_thread_name"))
    user_id = str(it.get("user") or "")
    channel_where = (
        where or channel_thread_name or channel_name or channel_parent_name
        or ("this public conversation" if it.get("direct") is False else "")
    )
    user = called or user_id or "the user"
    variables = {
        "agent": agent,
        "channel_kind": surface(record.get("kind")),
        "channel_config_name": name,
        "channel_name": channel_name,
        "channel_id": plainly(it.get("channel_id")),
        "channel_parent_name": channel_parent_name,
        "channel_parent_id": plainly(it.get("channel_parent_id")),
        "channel_thread_name": channel_thread_name,
        "channel_thread_id": plainly(it.get("channel_thread_id")),
        "channel_where": channel_where,
        "user": user,
        "user_id": user_id,
        "conversation_id": str(it.get("conversation") or ""),
        "schedule": "",
        # Existing stored channel instructions may still use the names shipped before
        # the builder standardized them. They remain fillable but are not public variables.
        "called": called,
        "kind": surface(record.get("kind")),
        "channel": name,
        "where": where,
        "conversation": str(it.get("conversation") or ""),
        **parts,
    }
    return variables


def _trigger(it: dict) -> str:
    """Which standardized channel instruction the adapter classified this arrival for."""
    if it.get("direct") is True:
        return instructions.DIRECT
    if it.get("direct") is False:
        return instructions.PUBLIC
    return ""


def _shipped_adapter(named) -> bool:
    """Whether this adapter is code Rundesk shipped, not an arbitrary executable."""
    try:
        return program(str(named or "")).parent.resolve() == ADAPTERS.resolve()
    except NotRunnable:
        return False


def parts_of(it: dict) -> dict:
    """The pieces of `where`, as the surface reported them, safe to put in a sentence.

    Same treatment as everything else that came off a platform: one line each and bounded,
    because a room's name is whoever-named-it's text and it is on its way into a prompt.
    """
    said = it.get(PARTS)
    if not isinstance(said, dict):
        return {}
    return {WHERE_IN + str(one): plainly(value)
            for one, value in list(said.items())[:SHAPES_MOST]
            if re.fullmatch(r"[a-z][a-z0-9_]{0,23}", str(one))}


def wrong_with_instructions(said, fills=()) -> str:
    """Why these standing instructions cannot be stored, or empty if they can (R-CH-22).

    Said when an owner writes them, never when a turn runs. A name misspelled here is an
    instruction that would have gone quietly blank every time from then on, and the moment
    to find out is the moment it is written — which is the same rule adding a channel
    already follows.
    """
    if not isinstance(said, str):
        return "what an agent is told has to be written as words"
    if len(said) > INSTRUCTIONS_MOST:
        return f"what an agent is told is longer than {INSTRUCTIONS_MOST} characters"
    # What the surface itself supplies, as the adapter declared it when the channel was
    # added. The core never learns that any platform has servers or workspaces; it only
    # holds an adapter to what it said it would fill in.
    known = list(FILLED) + list(LEGACY_VARIABLES) \
        + [WHERE_IN + one for one in fills or ()]
    for found in re.findall(r"\{([a-z_][a-z0-9_.]*)\}", said):
        if found not in known:
            return (f"there is nothing called '{found}' to fill in — there is "
                    + ", ".join(known))
    return ""


def named(secret) -> dict | None:
    """Which variables a credential is read from — never what is in any of them.

    **More than one, because one is not always enough.** A surface that opens its
    connection with one credential and calls its API with another cannot be reached at
    all if only one may be named, and that is the recommended shape for at least one real
    platform. Kept as a list either way, so a second never changes what a reader expects.
    """
    if not isinstance(secret, dict):
        return None
    named_as = secret.get("env")
    if isinstance(named_as, str):
        named_as = [named_as]
    if not isinstance(named_as, list):
        return None
    wanted = [one for one in named_as if isinstance(one, str) and one]
    return {"env": wanted} if wanted else None


def answered(said: object) -> dict:
    """What an adapter made of being pointed at something, as a whole answer.

    Read from whatever came back rather than trusted (R-CAD-9). An adapter that answers
    with a number, a list, or nothing readable at all has failed its check — which is the
    honest reading, because the one thing this question exists to establish is that the
    adapter can be relied on before anything about it is written down.

    `settings` is whatever the adapter wants handed back to it next time, and is never
    read here beyond being an object. `secret` is where it found its credential, never
    what the credential is.
    """
    given = said if isinstance(said, dict) else {}
    settings = given.get("settings")
    secret = given.get("secret")
    return {
        "ok": bool(given.get("ok")),
        "settings": settings if isinstance(settings, dict) else {},
        "secret": named(secret),
        "describes": given.get("describes") if isinstance(given.get("describes"), str) else None,
        "why": given.get("why") if isinstance(given.get("why"), str) else None,
        SHAPES: shaped(given.get(SHAPES)),
    }


def shaped(said) -> list:
    """The kinds of place this surface comes in, as things that can be written down.

    Read from whatever came back rather than trusted, like everything else here. A shape
    that does not name itself, or names itself something that could not be a channel, is
    dropped rather than repaired — a record written under a name nobody can type again is
    worse than one that was never written.

    An adapter reporting none is not a failure. It gets one channel, under the name the
    owner typed, exactly as every adapter did before this existed.
    """
    if not isinstance(said, list):
        return []
    shapes, seen = [], set()
    for one in said[:SHAPES_MOST]:
        if not isinstance(one, dict):
            continue
        at = one.get(SHAPE_AT)
        if not isinstance(at, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,23}", at):
            continue
        if at in seen:
            # Two shapes of one name are one channel written twice, and the second would
            # silently replace the first — including who it said was allowed.
            continue
        seen.add(at)
        settings = one.get("settings")
        # What this shape of place promises to supply, so a `{where.something}` an owner
        # writes can be refused when they write it rather than going quietly blank at
        # every turn after.
        fills = [str(name) for name in (one.get(FILLS) or [])
                 if re.fullmatch(r"[a-z][a-z0-9_]{0,23}", str(name))][:SHAPES_MOST]
        shapes.append({
            SHAPE_AT: at,
            "settings": settings if isinstance(settings, dict) else {},
            "describes": one["describes"] if isinstance(one.get("describes"), str) else None,
            FILLS: fills,
            INSTRUCTIONS: one[INSTRUCTIONS] if isinstance(one.get(INSTRUCTIONS), str) and not wrong_with_instructions(
                one.get(INSTRUCTIONS), fills) else "",
        })
    return shapes


async def checked(at: Path, options, env: dict[str, str] | None = None) -> dict:
    """Ask this adapter whether it can reach what it was pointed at (R-CAD-9).

    Everything after the options rundesk understands is handed over exactly as it was
    typed and is never parsed here, so a platform's own words for its own places stay
    inside the adapter that speaks it (R-CAD-13).

    An adapter that cannot be run, does not understand the question, or says something
    unreadable has not proved anything — and nothing is written down for one that has not.
    A channel that was never added is a better outcome than one that is silently deaf.
    """
    asked = process.Program(
        [str(at), CHECKING, *options],
        env=dict(env or {}),
        errors_apart=True,
        silence=CHECK_SILENCE_SECONDS,
        ceiling=CHECK_CEILING_SECONDS,
    )
    await asked.start()
    heard: list = []
    outcome = await asked.wait(sink=heard.append)
    for said in heard:
        if isinstance(said, bytes):
            try:
                return answered(json.loads(said))
            except ValueError:
                continue
    # Nothing readable came back, so the only thing to report is what became of the
    # program itself — which is all anybody could act on anyway.
    said = answered(None)
    said["why"] = (asked.errors or "").strip() or f"it said nothing, and {outcome.reason}"
    return said


# ------------------------------------------------------------------------------------
# What is written down about a channel lives in what the agent keeps, and is asked for
# through `store.py` — never from here. This module is the seam a *surface* is reached
# through: it frames one record each way and reads what an owner wrote about a channel,
# and a record is handed to it rather than fetched by it.
# ------------------------------------------------------------------------------------


def allowed(record: dict, user: str) -> bool:
    """Whether this person may reach the agent through this channel (R-CH-4).

    **Asked here and never of the adapter.** Being addressed is not the same as being
    authorized, and naming a bot in a shared room is something anyone present can do. An
    adapter that filtered for itself would be one whose author could get it wrong, on a
    machine where the agent runs tools — so a stranger's adapter is safe because of where
    this decision lives rather than because of how carefully it was written.

    A record with nobody allowed authorizes nobody. That is the same answer adding one
    refuses to write, said again at the point it would be acted on.
    """
    who = record.get("allow")
    if not isinstance(who, list):
        return False
    return bool(user) and user in who


def may_configure(record: dict, user: str) -> bool:
    """Whether this channel unambiguously belongs to the one person asking.

    A provider is an agent-wide default, so membership in a shared room's allow-list is
    not authority to change it for every channel and schedule. Until channels keep a
    distinct owner, only a single-user channel can safely carry configuration (R-CH-26).
    """
    who = record.get("allow")
    return isinstance(who, list) and len(who) == 1 and bool(user) and who[0] == user
