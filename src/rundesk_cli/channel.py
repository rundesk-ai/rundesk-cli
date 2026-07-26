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

The contract is written for a stranger in `.knowledge/guides/write-a-channel-adapter.md`.
**That guide is the specification and this file is an implementation of it** — where the
two disagree, the guide is right.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from rundesk_cli import gateway, process, provider

#: Where the adapters that ship with rundesk stand. Read by looking rather than listed, so
#: one added later is reachable the day it lands and no second copy of the list can come to
#: disagree with the directory.
ADAPTERS = Path(__file__).resolve().parent / "channels"

#: What an adapter reports, and the whole of it (R-CAD-1). Four, because there are four
#: things a surface has to say: it is connected, somebody spoke, somebody made a gesture at
#: a conversation rather than speaking into it, and it is no longer connected.
ARRIVING = ("ready", "arrived", "control", "gone")

#: What each of those must carry to mean anything. A record missing one of them is not a
#: partial record to be patched up — it is one nothing can be done with, and passing it on
#: would put the decision about what it meant somewhere further from the adapter that
#: knows. Whole records or nothing, in both directions.
NEEDED = {
    "ready": (),
    "arrived": ("conversation", "user", "text"),
    "control": ("conversation", "user", "control"),
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

#: What an owner has this agent told about its situation, before it reads a word of what
#: somebody typed (R-CH-22). Three keys and no more: `any` is used every time, and then
#: whichever of `direct` or `room` this conversation is. They compose rather than override,
#: so what is true everywhere is written once.
#:
#: Closed, and deliberately not a language. A condition an owner can write is a condition
#: rundesk has to explain, get right, and keep right — and what was actually asked for was
#: "say something different in a room than in a direct message", which is three keys.
SAYS = "says"
ANY, DIRECT, ROOM = "any", "direct", "room"
SITUATIONS = (ANY, DIRECT, ROOM)

#: What an owner may write `{like this}` and have filled in. Closed, because a name that is
#: not here is a typo, and a typo that silently becomes empty is an instruction that quietly
#: stopped saying what it said. Refused when it is written, not when a turn runs.
FILLED = ("agent", "channel", "surface", "where", "called", "user", "conversation")

#: How much of a preface is carried. Standing instructions are the owner's own words and
#: nobody is trying to defend against them — but a turn whose preface is longer than the
#: conversation is one nobody meant to write, and a record is not somewhere to put a book.
SAYS_MOST = 4000

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
TELLING = ("state", "think", "tool", "result", "usage", "said", "answer")

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
    """One line, as one of the four records we know — or nothing, if it is not one.

    Nothing is refused here and nothing raises (R-CAD-1). A line we cannot read, a line
    that is not an object, a line of a kind we have never heard of, and a line of a kind we
    know that is missing what that kind means all come back the same way: `None`, meaning
    "keep it, act on nothing". The caller keeps the raw line either way, which is what
    makes an adapter's drift show up as something readable rather than as a silent gap.

    A `control` naming a gesture that does not exist is refused for the same reason a
    missing field is: acting on it would mean guessing which of two things somebody meant,
    and one of them ends a turn.
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
    if kind == "arrived":
        it[ATTACHED] = attached(it.get(ATTACHED))
        # A message is words, or something attached, or both — and a photograph sent with
        # nothing typed is the most ordinary message there is. Text was required to be
        # non-empty, so an adapter that dutifully reported one had it refused here and
        # said nothing, which is the worst of the three possible outcomes.
        if not it["text"] and not it[ATTACHED]:
            return None
        it[WHERE], it[CALLED] = plainly(it.get(WHERE)), plainly(it.get(CALLED))
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


def preface(record: dict, agent: str, name: str, it: dict) -> str:
    """What this agent is told about its situation, for this arrival (R-CH-22).

    `any` then the one that fits, joined — so what is true everywhere is written once and
    what is true only in a room is written where it belongs. An owner who has written
    nothing gets the sentence rundesk would have said anyway, which is the only default:
    something that says where it is beats something that says nothing, and an owner who
    disagrees says so by writing their own.
    """
    says = record.get(SAYS)
    said = []
    if isinstance(says, dict):
        said = [str(says.get(one) or "").strip()
                for one in (ANY, DIRECT if it.get("direct") else ROOM)]
    said = [one for one in said if one]
    if not said:
        said = [_by_default(record, it)]
    filling = {
        "agent": agent, "channel": name, "surface": str(record.get("kind") or ""),
        "where": plainly(it.get(WHERE)), "called": plainly(it.get(CALLED)),
        "user": str(it.get("user") or ""), "conversation": str(it.get("conversation") or ""),
    }
    return _fill("\n\n".join(one for one in said if one), filling)[:SAYS_MOST]


def _by_default(record: dict, it: dict) -> str:
    """The one line rundesk says when an owner has said nothing (R-CH-21).

    **Not the channel's name.** That is the label an owner gave this connection when they
    set it up — `dms`, `ops`, `the-loud-one` — and it means nothing to a brain except that
    the word "channel" now appears twice in one sentence saying two different things. One
    named `dms`, pointing at a room, had an agent announce it was in "DMs in #development":
    it reconciled the two the only way the sentence allowed. It is a `{channel}` an owner
    can write if they want it, and not something rundesk volunteers.
    """
    kind = str(record.get("kind") or "").strip()
    if not kind:
        return ""
    said = f"This reached you over {kind}"
    for word, got in ((", in ", plainly(it.get(WHERE))), (", from ", plainly(it.get(CALLED)))):
        if got:
            said += word + got
    return said + ". What you answer is posted straight back there for them to read."


def _fill(said: str, filling: dict) -> str:
    """Put what is known in place of each `{name}`, and leave the rest of the text alone.

    Done by hand rather than with `str.format`, which would read a brace an owner wrote
    for its own sake — in a snippet of JSON, or a shell expansion — as a name it did not
    recognise, and raise in the middle of a turn. What is here is filled in; anything else
    is characters, and stays characters.
    """
    for name in FILLED:
        if "{" + name + "}" in said:
            said = said.replace("{" + name + "}", filling.get(name, ""))
    return said


def wrong_with_says(says) -> str:
    """Why these standing instructions cannot be stored, or empty if they can (R-CH-22).

    Said when an owner writes them, never when a turn runs. A name misspelled here is an
    instruction that would have gone quietly blank every time from then on, and the moment
    to find out is the moment it is written — which is the same rule adding a channel
    already follows.
    """
    if not isinstance(says, dict):
        return "what an agent is told has to be written as a set of named situations"
    for situation, said in says.items():
        if situation not in SITUATIONS:
            return (f"'{situation}' is not a situation — it is one of "
                    + ", ".join(SITUATIONS))
        if not isinstance(said, str):
            return f"what is said in {situation} has to be written as words"
        if len(said) > SAYS_MOST:
            return f"what is said in {situation} is longer than {SAYS_MOST} characters"
        for found in re.findall(r"\{([a-z_]+)\}", said):
            if found not in FILLED:
                return (f"there is nothing called '{found}' to fill in — there is "
                        + ", ".join(FILLED))
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
    }


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
# What is written down about a channel. Beside the agent's other working state, never
# inside the home it loads: which surfaces an agent is reachable on is rundesk's record
# about the agent, not knowledge the agent reads.
# ------------------------------------------------------------------------------------

#: What the record is called, beside `agent.json` and the book of conversations. One file
#: per agent rather than one per channel: they are read together every time — a gateway
#: coming up opens all of them — and a listing that had to walk a directory would be a
#: second way of finding out what exists.
BOOK = "channels.json"


def book(directory: Path) -> Path:
    """Where this agent's channels are written down."""
    return directory / BOOK


def known(directory: Path) -> dict:
    """Every channel this agent is reachable on, by the name it was added under.

    Read rather than changed, so nothing here writes an empty record over one that was
    merely unreadable. An entry that is not an object is passed over rather than being
    allowed to stop the rest: one hand-edited channel must not make an agent deaf on
    every other.
    """
    try:
        said = json.loads(book(directory).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(said, dict):
        return {}
    return {name: how for name, how in said.items() if isinstance(how, dict)}


def of(directory: Path, name: str) -> dict | None:
    """One channel, or nothing if this agent has no such channel."""
    return known(directory).get(name)


def remember(directory: Path, name: str, kind: str, allow, settings=None,
             secret=None, describes=None, now=None) -> bool:
    """Write down a channel that has already proved it works (R-CAD-9).

    Read, decided and written under one hold, because two channels being added together
    each write the whole record back and the later one would erase the other with both
    reporting success.

    **What is kept is a reference to the credential and never the credential** (R-CAD-12).
    `secret` is the name of a variable the adapter itself said it read, so what shows a
    channel can say a secret is present without anything here ever having held one.

    `settings` is whatever the adapter asked to have handed back, kept exactly as it gave
    it and never read — which is what keeps every word of every platform out of here.
    """
    if not allow:
        # Refused here as well as at the command, because this is the last place before
        # the disk and an agent that answers whoever speaks to it, on a machine where it
        # runs tools, is a misconfiguration rather than a mode (R-CAD-10).
        return False
    try:
        with gateway.changing(book(directory), {}, "the channels this agent is on") as kept:
            kept[name] = {
                "kind": kind,
                "allow": sorted({one for one in allow if one}),
                "settings": dict(settings or {}),
                "secret": dict(secret) if secret else None,
                "describes": describes,
                "added": (now or _stamped)(),
            }
    except (gateway.Unreadable, OSError):
        return False
    return True


def tell(directory: Path, name: str, says: dict) -> bool | None:
    """Change what this agent is told about a situation, leaving the rest of it alone
    (R-CH-22).

    Under the same one hold everything else here writes under, and merged rather than
    replaced: an owner setting what is said in a room must not silently drop what they
    wrote for a direct message a week ago. A situation set to nothing is removed, which is
    how one is taken back off.

    `None` when there is no channel by that name, so the difference between "changed
    nothing because it is not there" and "changed nothing because it could not be written"
    survives all the way out to what the owner is told.
    """
    try:
        with gateway.changing(book(directory), {}, "the channels this agent is on") as kept:
            it = kept.get(name)
            if it is None:
                return None
            standing = dict(it.get(SAYS) or {})
            for situation, said in says.items():
                if said:
                    standing[situation] = said
                else:
                    standing.pop(situation, None)
            if standing:
                it[SAYS] = standing
            else:
                it.pop(SAYS, None)
            kept[name] = it
    except (gateway.Unreadable, OSError):
        return False
    return True


def forget(directory: Path, name: str) -> bool:
    """Take this agent off one channel, leaving every other one alone."""
    try:
        with gateway.changing(book(directory), {}, "the channels this agent is on") as kept:
            if name not in kept:
                return False
            kept.pop(name)
    except (gateway.Unreadable, OSError):
        return False
    return True


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


def _stamped() -> str:
    """When a channel was added, for a person reading the record. Never what anything is
    ordered by — the record is a mapping, and one channel's time says nothing about
    another's."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
