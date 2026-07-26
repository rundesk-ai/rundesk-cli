"""The seam a brain is reached through, and nothing about any particular brain.

An adapter is a **program** rundesk runs, never code it loads (R-PRV-1). That is the whole
design: rundesk never puts a stranger's code inside the gateway that runs every other
agent, an adapter can be written in anything, and a brain nobody here has heard of is
reached by exactly the seam a shipped one is.

**Nothing is enumerated here.** There is no list of providers and no list of models. A
provider is a name carried through — a shipped adapter, or a path to a program somebody
wrote — so one rundesk does not recognise is the ordinary case rather than an error, and
the only failure is nothing runnable being there (R-PRV-12). A vendor's flags, session
files, permission modes and usage arithmetic live in that vendor's own adapter and appear
nowhere else; if a vendor's name shows up in this file, the seam has already failed.

What *is* closed is small and deliberate: six kinds of record, and the handful of things
an adapter may say it can do. An open vocabulary would put every vendor's words into every
channel and every reader, which is the thing this seam exists to prevent. Being closed is
also what lets an adapter be ahead of us — a record of a kind we do not know is kept
rather than refused (R-PRV-5), so a brain can grow without waiting for a release here.

The contract is written for a stranger in `.knowledge/guides/write-a-provider-adapter.md`.
**That guide is the specification and this file is an implementation of it** — where the
two disagree, the guide is right.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from rundesk_cli import process

#: Where the adapters that ship with rundesk stand. Read by looking rather than listed,
#: so one added later is reachable the day it lands and no second copy of the list can
#: come to disagree with the directory.
ADAPTERS = Path(__file__).resolve().parent.parent / "providers"

#: What an adapter reports, and the whole of it (R-PRV-4). An eighth is a change to the
#: contract, deliberately.
#:
#: `file` is the seventh, and it was added because the contract could not say a thing
#: brains plainly do: make something. One generated a picture, said "here it is", and
#: there was no way to tell anybody a file existed — so the surface showed the sentence
#: and not the picture. Inferring it from what a tool printed was the alternative, and it
#: would have meant sending anything a brain happened to name, which is a hole rather
#: than a feature. A brain says so or nothing is sent.
RECORDS = ("text", "think", "tool", "result", "usage", "file", "done")

#: What a brain says on a `text` record when the thing it just said is *finished* rather
#: than a piece of something still being written (R-PRV-22).
#:
#: The difference decides whether a person can be shown it while the turn runs. A brain
#: that streams its reply a fragment at a time can only be shown at the end, because a
#: reply that rewrites itself in place is unreadable. A brain that says several complete
#: things as it works — "I will look at the logs", then later the answer — can have each
#: shown as it is said, which is how a person would write in a chat. Absent means a
#: fragment, so a brain that says nothing gets the old behaviour and nothing breaks.
WHOLE = "whole"

#: What a tool *did*, in words no brain owns (R-PRV-8). Closed and short on purpose: a
#: surface that recognised a vendor's own tool names would be carrying that vendor's
#: vocabulary forever, and every reader would need a table per brain.
#:
#: **This is the list, and it lives here** — it was written in the guide as prose and
#: copied by hand into each adapter that used it, which is a list kept in three places
#: and therefore three lists. A brain that did something outside it leaves `did` out
#: rather than stretching one to fit: a reader shown nothing is better than one taught
#: to believe a word that means something else here. Growing it is a release, not a
#: guess an adapter makes on its own.
DID = ("read", "search", "run", "edit", "list", "make")

#: What an adapter may say it can do (R-PRV-15). Absent means no, so an adapter that
#: answers with nothing at all is a whole brain with the work simply absent — which is
#: what makes a plain conversational CLI first class rather than degraded.
#:
#: `steer` is the one that changes how a turn is *run* rather than only what is recorded
#: of it: an adapter that can be sent to mid-turn is given its input as records and has
#: its input held open, and one that cannot is given the prompt and told there is no more.
#: Declared rather than attempted, because holding input open for a brain that will never
#: read again is a turn that never ends.
CAPABILITIES = ("tools", "resume", "model", "usage", "steer")

#: What rundesk sends a brain that can be steered — the prompt, and anything after it.
#: One kind, because there is one thing to say to a running brain: more words.
SAY = "say"

#: How much of the machine a turn may touch, in rundesk's words rather than any vendor's
#: (R-PRV-18). Two, because a posture nobody can act on is not worth carrying: an adapter
#: maps these onto whatever its own brain understands, or ignores them.
READ = "read"
WORK = "work"
POSTURES = (READ, WORK)

#: What is asked of an adapter to find out what it can do. Offline and side-effect-free by
#: contract — but still a program being run, which is why nothing that diagnoses an agent
#: asks it (R-AGT-11) and only admitting a turn does.
ASKING = "--capabilities"

#: How long an adapter may say nothing when asked what it can do (R-PRV-15). A window of
#: silence and not a stopwatch, like everything else rundesk waits on: a machine under
#: load can take a while to start a program at all.
#:
#: **This bounds the answering, never a turn.** A turn is bounded by silence at
#: `process.SILENCE_SECONDS` and nothing shorter is ever imposed on one — an agent that
#: thinks for an hour is working, not stuck, and a clock that ends it is a clock that
#: ends real work (R-PROC-6). This is different because it is a question with an answer
#: the adapter already knows, asked offline and by contract without a network.
ASKING_SILENCE_SECONDS = 60.0

#: The longest the answering may take however much it is saying. Silence cannot see a
#: program wedged in a loop that keeps announcing itself, which is the whole reason a
#: ceiling exists beside it (R-PROC-13) — and this is the one place rundesk runs a program
#: nobody here has vetted *before* a turn is admitted, so switching the backstop off left a
#: chatty or broken adapter able to hang every `rundesk ask` with nothing written down.
#: Generous against a loaded machine, and far short of a turn's, because this is a question
#: whose answer the adapter already knows.
ASKING_CEILING_SECONDS = 300.0


class NotRunnable(Exception):
    """There is nothing runnable where this provider said there would be (R-PRV-12).

    The only way resolving a provider fails. Not recognising a name is not a failure —
    a brain rundesk has never heard of is the case this seam exists for.
    """


def program(named: str, adapters: Path | None = None) -> Path:
    """The program that is this provider, or why there is not one.

    A path is used as it stands and anything else is looked for among the adapters that
    ship. That is the whole rule, and it is deliberately not a lookup table: `codex` and
    `/opt/my-brain` are the same kind of thing here, one of them merely happens to live
    in this repository.
    """
    where = ADAPTERS if adapters is None else adapters
    if not named:
        raise NotRunnable("no brain was named")
    stands = Path(named) if (os.sep in named or named.startswith("~")) else where / named
    stands = stands.expanduser()
    if not stands.is_absolute():
        stands = stands.resolve()
    if not stands.is_file():
        raise NotRunnable(f"there is no brain at {stands}")
    if not os.access(stands, os.X_OK):
        raise NotRunnable(f"{stands} is not something this machine can run")
    return stands


def key(named: str) -> str:
    """One filesystem-safe name for this provider, for the things kept per brain.

    A shipped adapter is its own name. A path is its last part with a little of the whole
    path after it — because two brains called `brain` in two directories are two brains,
    and giving them one private home would hand one's credentials and session files to
    the other. Short and stable rather than pretty: it names a directory, and the name an
    owner reads is the one they typed.
    """
    if os.sep not in named and not named.startswith("~"):
        return named
    stands = Path(named).expanduser()
    marked = hashlib.sha256(str(stands).encode("utf-8")).hexdigest()[:8]
    return f"{_plain(stands.name) or 'brain'}-{marked}"


def _plain(name: str) -> str:
    """What is left of a name once anything that would not stand as one is taken out."""
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in name).strip("-")


def environment(
    home: Path,
    cwd: Path,
    provider_home: Path,
    run: str,
    model: str | None = None,
    resume: str | None = None,
    posture: str = WORK,
    settings: dict | None = None,
    raw: Path | None = None,
    path: str | None = None,
    preface: str | None = None,
) -> dict[str, str]:
    """Everything an adapter is told, and the whole of it (R-PRV-3).

    Built on the environment every program rundesk runs gets, so an adapter is a program
    like any other and is given nothing extra by being one. What is *not* here is as
    deliberate as what is: no vendor variable, because which one a brain wants is that
    brain's adapter's business and putting it here would put the vendor in the core.

    Anything left out is left unset rather than set to nothing. An adapter asked to work
    with a model called empty-string would do something odd with it; one that is told
    nothing falls back to its own default, which is what "or unset" means in the guide.
    """
    if posture not in POSTURES:
        raise ValueError(f"'{posture}' is not how much of a machine a turn may touch")
    said = process.environment(home, path=path)
    said["RUNDESK_CWD"] = str(cwd)
    said["RUNDESK_PROVIDER_HOME"] = str(provider_home)
    said["RUNDESK_RUN"] = run
    said["RUNDESK_POSTURE"] = posture
    if model:
        said["RUNDESK_MODEL"] = model
    if resume:
        said["RUNDESK_RESUME"] = resume
    if settings:
        # Written out sorted, so the same settings are the same bytes every run and a
        # transcript can be compared with another one (R-PRV-16). Never read on the way
        # past: what an owner set is between them and their brain.
        said["RUNDESK_SETTINGS"] = json.dumps(settings, sort_keys=True)
    if preface and preface.strip():
        # What the thing that admitted this turn wants said about the situation, before
        # anything the person typed. Rundesk says what it means and stops there: whether
        # this becomes a real system instruction or a paragraph above the prompt is the
        # brain's own business, and the adapter is the only thing that knows which its
        # brain has. Handed over separately from the prompt for exactly that reason — a
        # brain that cannot tell rundesk's words from the person's weights the owner's
        # standing instructions as though somebody had just typed them.
        said["RUNDESK_PREFACE"] = preface
    if raw is not None:
        # Somewhere to put what the *brain* said, which rundesk never sees: an adapter
        # stands between the two, so a vendor changing its stream shape would otherwise
        # show up as records quietly going missing rather than as drift anyone can read.
        # Offered, never required — an adapter that ignores it is a whole adapter.
        said["RUNDESK_RAW"] = str(raw)
    return said


def spoken(text: str) -> bytes:
    """One thing said *to* a brain, as a record it reads a line at a time (R-PRV-19).

    Records rather than plain text, and only for an adapter that said it can be steered.
    Its input has to stay open for more, so nothing can mean "the prompt ended" any more —
    a brain reading to the end of its input would wait for an end that is not coming. A
    line each, with the text encoded, so a prompt with newlines in it is still one thing.
    """
    return (json.dumps({"type": SAY, "text": text}) + "\n").encode("utf-8")


def understood(said: bytes | str) -> dict | None:
    """One line, as one of the six records we know — or nothing, if it is not one.

    Nothing is refused here and nothing raises (R-PRV-5). A line we cannot read, a line
    that is not an object, and a line of a kind we have never heard of all come back the
    same way: `None`, meaning "keep it, show it to nobody". The caller keeps the raw line
    either way, which is what makes an upstream format change show up as visible drift
    rather than as a silent gap.
    """
    try:
        it = json.loads(said)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(it, dict):
        return None
    return it if it.get("type") in RECORDS else None


def claimed(said: object) -> dict:
    """What an adapter says it can do, as an answer to every question rather than some.

    Absent is no, so a brain that says nothing is not asked to have anything (R-PRV-15).
    Read from whatever came back rather than trusted: an adapter that answers with a
    number, a list, or nothing readable at all is one that can do nothing, which is a
    complete and honest answer and not an error.
    """
    given = said if isinstance(said, dict) else {}
    return {what: bool(given.get(what)) for what in CAPABILITIES}


async def capabilities(at: Path, env: dict[str, str] | None = None) -> dict:
    """Ask this adapter what it can do, before a turn is admitted (R-PRV-15).

    A program is run, so this is never part of diagnosing an agent — that answers "could
    this work at all" without starting anything (R-AGT-11), and the answer here is only
    needed once there is a turn to admit.

    An adapter that does not understand the question, cannot be run, or says something
    unreadable can do nothing. That is the honest reading and it is never an error: the
    smallest legitimate adapter in the guide is a shell script that answers a prompt, and
    telling its author their brain is broken for not knowing this flag would be wrong.
    """
    asked = process.Program(
        [str(at), ASKING],
        env=dict(env or {}),
        errors_apart=True,
        silence=ASKING_SILENCE_SECONDS,
        ceiling=ASKING_CEILING_SECONDS,
    )
    await asked.start()
    heard: list = []
    outcome = await asked.wait(sink=heard.append)
    if not outcome.ok:
        return claimed(None)
    for said in heard:
        if isinstance(said, bytes):
            try:
                return claimed(json.loads(said))
            except ValueError:
                continue
    return claimed(None)
