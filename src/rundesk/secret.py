"""The values this install keeps, and hands to every program it starts.

One set for the whole install — there is no whose. A value placed here reaches every brain,
every adapter, every schedule and every integration command rundesk runs, which is the
point: an owner places a credential once and everything that needs it finds it, with nobody
having exported anything in a shell a gateway will never see.

**Nothing here ever gives a whole value back.** Not to an agent, not to the owner. A value
is identified by the last few characters of it and by a mark taken with a key of this
install's, which together answer "which one is this" and "did it change" and answer nothing
else. There is no flag for the rest, because a value that can be read back off a machine is
one an owner has to assume has been.

**What is kept stands outside `data_home()`**, and that is the whole reason it is here
rather than beside everything else an owner keeps: `backup.py` copies `data_home()` and
nothing else, so a copy of this install is structurally incapable of holding a credential
rather than careful not to. The same trick `backups_home()` plays with removal.

Two ways a value is kept, and the module knows no others. It is **held** here, in a file
only its owner can read; or it is **fetched** by a command somebody else wrote — `op read`,
`pass show`, `gpg -d` — which rundesk keeps the words of and runs again each time a program
starts, so the value itself is never on this disk at all.

Imports nothing of rundesk's but `durable`, and reaches `process` lazily and only to ask
what names it decides — so the whole module is exercised with no vault, no keeper and no
gateway anywhere near it.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import hashlib
import hmac
import os
import re
import subprocess
from pathlib import Path

from rundesk import durable


#: The shape this file is written in. Not a migration table — `src/migrations/` is the
#: agent store's and does not reach here — but a release that changes the shape has to be
#: able to tell one it wrote from one it did not, and a file with no version in it can
#: only be guessed at.
VERSION = 1

REGISTRY = "registry.json"
VALUES = "values"
KEY = "key"

#: What a value is kept as. `HELD` is in a file here; `FETCHED` is a command rundesk runs
#: each time a program starts, and no value of it is ever written down.
HELD = "here"
FETCHED = "command"
KEPT_AS = (HELD, FETCHED)

#: How long a command that fetches a value has to answer. Above every honest keeper — an
#: unlocked vault answers in well under a second — and below anything a person waiting at a
#: terminal reads as a hang.
COMMAND_SECONDS = 10.0

#: How much of one value is carried, and how much of the whole set. **Not a tidiness
#: limit.** The kernel refuses `execve` once the environment block passes `ARG_MAX`, so one
#: keeper that goes wrong and prints a megabyte would stop every brain, adapter, schedule
#: and integration command on this machine from starting at all — and the failure names
#: nothing, because there is no program left to say anything.
VALUE_LIMIT_BYTES = 64 * 1024
SET_LIMIT_BYTES = 128 * 1024

#: How much of somebody else's error message is carried back. It is shown at a terminal and
#: never written down: a keeper that fails routinely prints the thing it was reading.
WHY_CHARACTERS = 200

#: How many characters of a value are ever shown. Enough to tell two apart at a glance, and
#: never a meaningful fraction of a credential worth keeping.
HINT_CHARACTERS = 4

#: Below this, none are shown. Four characters of a twelve-character value is a third of
#: it — and a hint whose length varied would report the length, which is the one fact about
#: a credential that is both worth having and free to read off.
HINT_MINIMUM = 12
HINT_MASK = "·" * HINT_CHARACTERS

#: How much of the mark is shown. Enough that two values on one install never collide, and
#: far too little to be worth attacking.
MARK_CHARACTERS = 8

#: What a name may be at all. Uppercase-first is not decoration: it refuses `path`, `Path`
#: and `BASH_FUNC_x%%` before any policy is consulted, because none of them is a shape a
#: variable an owner means to set has.
NAME_IS = re.compile(r"[A-Z][A-Z0-9_]{0,63}")

#: Families a value may never land in, whatever it is called inside one. **The dynamic
#: loader ones are why this exists**: a value in `DYLD_INSERT_LIBRARIES` or `LD_PRELOAD`
#: runs somebody's code inside every brain, adapter, integration command and schedule this
#: install starts, for ever, with no agent, gateway or adapter involved in the decision —
#: and an agent may place a value. `RUNDESK_` covers every name this install decides that
#: `placed()` cannot see because it is conditional, and every one a later release adds.
FAMILIES = (
    ("RUNDESK_", "rundesk decides every name beginning RUNDESK_ for the programs it starts"),
    ("DYLD_", "a name beginning DYLD_ decides what code a program loads"),
    ("LD_", "a name beginning LD_ decides what code a program loads"),
    ("PYTHON", "a name beginning PYTHON makes a program run code before its own arguments"),
    ("BASH_FUNC_", "a name beginning BASH_FUNC_ puts a function into every shell that starts"),
    ("XDG_", "a name beginning XDG_ decides where a program looks for its own configuration"),
    # npm maps every `NPM_CONFIG_<KEY>` onto its own configuration, so this one family
    # carries both halves of what the list above refuses: `NPM_CONFIG_SCRIPT_SHELL` is the
    # interpreter every `package.json` lifecycle script runs under, and `NPM_CONFIG_CAFILE`
    # and `NPM_CONFIG_CA` are who the registry is trusted on. A prefix rather than three
    # names, because `userconfig` and `globalconfig` point at a file that can set the rest.
    # Measured on this machine against npm and pnpm; a coding-agent gateway runs `npm` from
    # a brain's own tool shell as an ordinary thing, so the reach is not hypothetical.
    ("NPM_CONFIG_", "a name beginning NPM_CONFIG_ changes what code npm and pnpm run or trust"),
)

#: Names outside those families that decide what a program *is*, or who it trusts, rather
#: than what it is told. This list has no other home, so it cannot come apart from one — what
#: could is the set of names rundesk itself decides, and that is asked rather than restated.
NEVER = frozenset({
    # **`ZDOTDIR` is the one this list was nearly shipped without.** zsh sources
    # `$ZDOTDIR/.zshenv` on *every* invocation — non-interactive and non-login included,
    # unlike bash, which reads `BASH_ENV` only in narrower cases — and zsh is the default
    # shell on the platform this product is for. Measured: `env ZDOTDIR=<dir> zsh -c true`
    # runs whatever that directory's `.zshenv` says.
    #
    # An agent can already run code this turn, so the escalation is not execution: it is
    # **persistence and reach**. A value kept here outlives the turn, survives restarts and
    # updates, and is handed to every program started for every agent — so one placed once
    # runs inside all of them for ever, which is a different thing from a command that ends
    # when the turn does. That is the argument for every name below.
    "ZDOTDIR", "FPATH",
    "SHELL", "IFS", "ENV", "BASH_ENV", "CDPATH", "PROMPT_COMMAND", "TMPDIR",
    "NODE_OPTIONS", "NODE_PATH", "NODE_EXTRA_CA_CERTS",
    "PERL5LIB", "PERL5OPT", "RUBYOPT", "GCONV_PATH",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
    "GIT_SSH", "GIT_SSH_COMMAND", "GIT_EXTERNAL_DIFF", "GIT_PAGER",
    "PAGER", "EDITOR", "VISUAL", "BROWSER",
})


class NotAName(Exception):
    """Not a shape a variable an owner means to set has."""


class Refused(Exception):
    """A name that decides what a program runs, loads or trusts, rather than what it is told."""


class Unknown(Exception):
    """Nothing is kept under that name."""


class Exists(Exception):
    """Something is already kept under that name, and replacing it was not asked for."""


class Unreadable(Exception):
    """What is kept is there and could not be read. Never treated as nothing being kept."""


class NotKept(Exception):
    """A value that cannot be kept, or a command that gave nothing back to keep."""


@dataclasses.dataclass(frozen=True)
class Kept:
    """One name this install keeps a value for — and never the value.

    `command` is empty for a held value. `last_seen` is when a fetched value was last
    actually produced, which is what makes its hint honest: a hint with no date beside it
    is a claim about a value nobody has asked for in a month.
    """

    name: str
    kept_as: str
    hint: str
    mark: str
    kept_at: str
    kept_from: str
    command: tuple = ()
    last_seen: str = ""


@dataclasses.dataclass(frozen=True)
class Ran:
    """What a command that fetches a value answered — including that it could not answer.

    **Three outcomes, never two.** `answered=False` means the probe itself failed — it timed
    out, or the machine would not fork — and is never read as "there is no value": the value
    may exist and be perfectly good. The same shape `supervisor.Spoke` keeps for the machine's
    own answers, and for the same reason.
    """

    answered: bool
    ok: bool
    value: str = ""
    why: str = ""


@dataclasses.dataclass(frozen=True)
class Trouble:
    """One name a program was not given, and which kind of not-given it was."""

    name: str
    kept_as: str
    answered: bool
    why: str


@dataclasses.dataclass(frozen=True)
class Resolved:
    """What every program started from here is given, and what could not be produced.

    `unreadable` is the whole set failing rather than one name: what is kept is there and
    could not be read. It is said rather than swallowed, and nothing is written back over
    it — a file that cannot be parsed still holds everything in it as recoverable text.
    """

    values: dict
    trouble: tuple = ()
    unreadable: str = ""


@dataclasses.dataclass(frozen=True)
class Change:
    """What one `remember` did, decided under the lock rather than guessed at either side.

    `before` is what stood there, so the command can say which value it replaced without
    reading the registry twice and reporting on a state that no longer holds.
    """

    kept: Kept
    before: object = None
    unchanged: bool = False


def home() -> Path:
    """Where this install keeps what no copy of it may carry.

    **Outside `data_home()` on purpose** — see the module docstring. The variable is read
    here and nowhere else, and the fallback follows the XDG base directory specification,
    which every integration command this feature exists to serve already follows.

    `XDG_CONFIG_HOME` is honoured only when it is absolute, because the specification says
    a relative value is to be ignored — and honouring one would resolve this against
    whatever directory a gateway happened to be started in, which is a directory nobody
    chose.

    Resolved on every call and never cached, exactly as `data_home()` is: where an owner
    keeps things is machine state, and binding it once at import is how a suite comes to
    write into the real one.
    """
    said = os.environ.get("RUNDESK_SECRETS_DIR")
    if said:
        return Path(said).expanduser()
    config = os.environ.get("XDG_CONFIG_HOME") or ""
    base = Path(config) if config.startswith("/") else Path.home() / ".config"
    return base / "rundesk" / "secrets"


def registry_path(where: Path | None = None) -> Path:
    """What is kept, by name — and never what any of it is."""
    return (where or home()) / REGISTRY


def values_home(where: Path | None = None) -> Path:
    """Where a held value stands, one file each."""
    return (where or home()) / VALUES


def key_path(where: Path | None = None) -> Path:
    """This install's own key, which the mark beside every value is taken with."""
    return (where or home()) / KEY


def placed() -> frozenset:
    """Every name rundesk itself puts in a program's environment — asked, never listed.

    A name written down here as well would be a list that disagrees with the builder the
    first time somebody adds a key without reading this far, and the disagreement would be
    a value silently overriding something rundesk decided.

    Built with every optional part supplied, so the answer does not depend on how this
    machine happens to be pointed: a name refused on a machine with `RUNDESK_AGENTS_DIR`
    set and accepted on one without it is worse than no rule at all.

    Imported here rather than at the top because `process` is the layer below and asking it
    a question is all this module wants of it.
    """
    from rundesk import process

    nowhere = Path(os.devnull)
    return frozenset(process.environment(nowhere, path="", agents=nowhere))


def refused(name: str) -> str:
    """Why a value may never be kept under that name, or an empty string.

    Asked at three moments, each for its own reason: when a value is placed, so the person
    standing there is told why; when one is resolved, because what is kept is a file
    somebody can edit and because a name that becomes refused in a later release must stop
    being given out without anyone re-running a command; and once more inside the builder,
    which is the only place that can be sure.
    """
    if not name or not NAME_IS.fullmatch(name):
        return ("a name begins with a capital letter, and the rest is capital letters, "
                "digits and underscores")
    if name in placed():
        return f"rundesk decides {name} for every program it starts"
    for family, why in FAMILIES:
        if name.startswith(family):
            return why
    if name in NEVER:
        return f"{name} decides what a program runs or who it trusts, rather than what it is told"
    return ""


def checked(name: str) -> str:
    """That name, or a refusal in our own words."""
    if not name or not NAME_IS.fullmatch(name):
        raise NotAName("a name begins with a capital letter, and the rest is capital "
                       "letters, digits and underscores")
    why = refused(name)
    if why:
        raise Refused(why)
    return name


def normalised(value: str) -> str:
    """One value as a program will actually receive it.

    **Exactly one trailing newline goes, and nothing else.** Every keeper worth using adds
    one — `op read` and `pass show` both do — while a passphrase ending in a space and a
    key ending in several newlines are both legitimate, and a bare `.strip()` quietly
    breaks them. This is deliberately not what `commands/channels.py` does with a token
    typed by hand, where trimming what a person pasted is the kinder answer.

    A value with a null byte in it is refused rather than carried: `execve` cannot hold
    one, so it would be truncated on the way to the program with nothing saying so.
    """
    if "\0" in value:
        raise NotKept("a value cannot hold a null byte, and no program could be given one")
    if value.endswith("\n"):
        value = value[:-1]
    if value.endswith("\r"):
        value = value[:-1]
    return value


def carried(name: str, value: str) -> str:
    """That value, once it is known to be one a program could actually be given."""
    value = normalised(value)
    if not value:
        raise NotKept("nothing was given, and an empty value is not a value")
    if len(value.encode("utf-8")) > VALUE_LIMIT_BYTES:
        raise NotKept(f"{name} is larger than a value may be, and would stop programs starting")
    return value


def hint(value: str) -> str:
    """The last few characters of a long enough value, and nothing of a short one.

    Taken from the value as it will be given to a program, so what the hint describes is
    what a program actually receives.
    """
    if len(value) < HINT_MINIMUM:
        return HINT_MASK
    return HINT_MASK + value[-HINT_CHARACTERS:]


def mark(value: str, key: bytes) -> str:
    """A short stable mark, which no amount of the value can be read out of.

    **Taken with a key of this install's, never a bare digest.** A bare one is an oracle:
    anybody holding what is kept can test a guess against it, and for a fetched value the
    mark is the only derived thing on this disk at all. It is shown to agents by design, so
    it leaves the directory routinely.

    Two names holding one value carry one mark, which is the whole use of it — that is how
    an owner sees at a glance that a value reached them by two routes. The same value on
    another install marks differently, which is not a loss: a mark answers "which of mine
    is this" and was never meant to answer anything about somebody else's machine.
    """
    said = hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()
    return said[:MARK_CHARACTERS]


def _made(where: Path | None = None) -> Path:
    """Where things are kept, standing and readable by nobody else."""
    at = where or home()
    at.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        at.chmod(0o700)
    return at


def write_private(at: Path, text: str) -> None:
    """Put a value where only its owner can read it, from the moment it exists.

    **Created with the mode, never narrowed to it afterwards.** `Path.write_text` creates at
    `0666 & ~umask` and a `chmod` after it leaves a window in which anybody on the machine
    can read the file. Every other durable write in this tree already opens with the mode;
    this is the shared form of it, and `commands/channels.py` uses it too.

    `O_NOFOLLOW` for the same reason `agent._write_pending` uses it: a link planted at this
    path would otherwise make rundesk write a credential wherever it points. Written beside
    and renamed into place, so a reader never sees half a value.
    """
    at.parent.mkdir(parents=True, exist_ok=True)
    beside = at.with_name(f".{at.name}.{os.getpid()}.writing")
    with contextlib.suppress(OSError):
        beside.unlink()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    opened = os.open(beside, flags, 0o600)
    try:
        with os.fdopen(opened, "w", encoding="utf-8") as handle:
            handle.write(text)
    except BaseException:
        with contextlib.suppress(OSError):
            beside.unlink()
        raise
    os.replace(beside, at)


def _standing(name: str, where: Path | None = None) -> Path:
    """Where a held value by that name stands, checked before it is joined to anything.

    `Path("/a/b") / "/elsewhere"` is `/elsewhere` — the left side is discarded outright — so
    a name that reached here unchecked would be a way to name any file on the machine, and
    `forget` then unlinks it. `checked` has already refused anything with a separator in it;
    this is the guard that does not depend on that having happened.
    """
    separators = [os.sep] + ([os.altsep] if os.altsep else [])
    if not name or name in (".", "..") or any(one in name for one in separators):
        raise NotAName(f"'{name}' is not a name a value can be kept under")
    return values_home(where) / name


def _read(where: Path | None = None) -> dict:
    """What is kept, or a refusal — never an install with nothing kept.

    A file that is there and will not parse is the state most worth telling apart: reading
    it as nothing kept is how every value an owner placed silently stops reaching anything,
    and writing that reading back is how the record of them is lost as well.
    """
    at = registry_path(where)
    state, said = durable.read(at)
    if state == durable.MISSING:
        return {}
    if state == durable.UNREADABLE or not isinstance(said, dict):
        raise Unreadable(f"{at} is there and could not be read")
    kept = said.get("secrets")
    return kept if isinstance(kept, dict) else {}


def _as_kept(name: str, said: dict) -> Kept:
    """One row as this release understands it, reading past anything it does not."""
    command = said.get("command")
    return Kept(
        name=name,
        kept_as=said.get("kept_as") if said.get("kept_as") in KEPT_AS else HELD,
        hint=said.get("hint") or HINT_MASK,
        mark=said.get("mark") or "",
        kept_at=said.get("kept_at") or "",
        kept_from=said.get("kept_from") or "",
        command=tuple(command) if isinstance(command, list) else (),
        last_seen=said.get("last_seen") or "",
    )


def listed(where: Path | None = None) -> list:
    """Everything kept, by name — and **nothing is fetched to answer this**.

    A listing that unlocked a vault is a listing nobody runs, and one that ran every keeper
    an install has would make simply looking at the surface expensive and, on a machine
    asking for a fingerprint, impossible to run unattended.
    """
    return [_as_kept(name, said) for name, said in sorted(_read(where).items())
            if isinstance(said, dict)]


def described(name: str, where: Path | None = None) -> Kept:
    """One kept value, by name."""
    said = _read(where).get(name)
    if not isinstance(said, dict):
        raise Unknown(f"nothing is kept under {name}")
    return _as_kept(name, said)


def _key(where: Path | None = None) -> bytes:
    """This install's own key, made the first time one is wanted and never again.

    **Never rotated.** A new key would change every mark at once, so "did this value
    change" would answer yes for everything — which is the one question a mark exists to
    answer. A key file that is there and cannot be read is a refusal, never a reason to
    make a second one.
    """
    at = key_path(where)
    try:
        said = at.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        said = ""
    except OSError as why:
        raise Unreadable(f"{at} is there and could not be read: {why}") from why
    if said:
        try:
            return bytes.fromhex(said)
        except ValueError as why:
            raise Unreadable(f"{at} is there and could not be understood: {why}") from why
    _made(where)
    fresh = os.urandom(32)
    write_private(at, fresh.hex() + "\n")
    return fresh


def _changing(where: Path | None = None):
    """The read, the decision and the write, under one hold nobody else has."""
    _made(where)
    return durable.changing(registry_path(where), {"version": VERSION, "secrets": {}},
                            "what this install keeps")


def _row(kept: Kept) -> dict:
    said = {
        "kept_as": kept.kept_as,
        "hint": kept.hint,
        "mark": kept.mark,
        "kept_at": kept.kept_at,
        "kept_from": kept.kept_from,
    }
    if kept.command:
        said["command"] = list(kept.command)
    if kept.last_seen:
        said["last_seen"] = kept.last_seen
    return said


def remember(name: str, value: str, *, now: str, kept_from: str,
             where: Path | None = None, replace: bool = False) -> Change:
    """Hold this value under that name, and say what that did to what stood there.

    The value is written before the record of it. A machine that dies between the two
    leaves a file nothing names, which the next `remember` or `forget` overwrites and
    nothing ever reads; the other order leaves a name whose value does not exist, which
    every program then reports as missing.
    """
    checked(name)
    value = carried(name, value)
    standing = _standing(name, where)
    with _changing(where) as keeping:
        kept = keeping.setdefault("secrets", {})
        was = kept.get(name)
        before = _as_kept(name, was) if isinstance(was, dict) else None
        if before is not None and not replace:
            raise Exists(f"{name} is already kept")
        values_home(where).mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            values_home(where).chmod(0o700)
        write_private(standing, value + "\n")
        now_kept = Kept(name=name, kept_as=HELD, hint=hint(value),
                        mark=mark(value, _key(where)), kept_at=now, kept_from=kept_from)
        unchanged = bool(before) and before.kept_as == HELD and before.mark == now_kept.mark
        if unchanged:
            # Nothing about it moved, so the moment it was placed did not either — saying
            # it was replaced when the same value went back would make the one date an
            # owner has for a credential meaningless.
            now_kept = dataclasses.replace(now_kept, kept_at=before.kept_at,
                                           kept_from=before.kept_from)
        kept[name] = _row(now_kept)
        keeping["version"] = VERSION
    return Change(kept=now_kept, before=before, unchanged=unchanged)


def remember_command(name: str, command, *, now: str, kept_from: str, run=None,
                     where: Path | None = None, replace: bool = False,
                     timeout_seconds: float = COMMAND_SECONDS) -> Change:
    """Keep the words of a command that prints this value, and never what it printed.

    **Run once here, before anything is written.** That is what earns the hint and the
    mark, and it is what stops a name being registered on a promise: a command that cannot
    produce a value now is one every program would be told nothing by, quietly, for as long
    as nobody looked.
    """
    checked(name)
    command = tuple(str(one) for one in command)
    if not command:
        raise NotKept("no command was given to fetch it with")
    said = (run if run is not None else ran)(command, timeout_seconds=timeout_seconds)
    if not said.ok:
        raise NotKept(said.why or "it gave nothing back")
    value = carried(name, said.value)
    with _changing(where) as keeping:
        kept = keeping.setdefault("secrets", {})
        was = kept.get(name)
        before = _as_kept(name, was) if isinstance(was, dict) else None
        if before is not None and not replace:
            raise Exists(f"{name} is already kept")
        now_kept = Kept(name=name, kept_as=FETCHED, hint=hint(value),
                        mark=mark(value, _key(where)), kept_at=now, kept_from=kept_from,
                        command=command, last_seen=now)
        unchanged = (bool(before) and before.kept_as == FETCHED
                     and before.command == command and before.mark == now_kept.mark)
        if unchanged:
            now_kept = dataclasses.replace(now_kept, kept_at=before.kept_at,
                                           kept_from=before.kept_from)
        kept[name] = _row(now_kept)
        keeping["version"] = VERSION
    # A name that was held here and is now fetched leaves no value behind on the disk —
    # taken away after the record says it is fetched, for the reason `forget` gives.
    if before is not None and before.kept_as == HELD:
        with contextlib.suppress(OSError):
            _standing(name, where).unlink()
    return Change(kept=now_kept, before=before, unchanged=unchanged)


def forget(name: str, where: Path | None = None) -> Kept:
    """Take one value away, and touch nothing else."""
    standing = _standing(name, where)
    with _changing(where) as keeping:
        kept = keeping.setdefault("secrets", {})
        was = kept.get(name)
        if not isinstance(was, dict):
            raise Unknown(f"nothing is kept under {name}")
        gone = _as_kept(name, was)
        del kept[name]
    # **Outside the change, and that is the whole point of where it stands.** `changing`
    # writes the record when its body returns, so unlinking inside it would put the value
    # beyond reach *before* the record saying so is on disk — and a machine that died in
    # between would leave a name still listed as held with nothing behind it. `remember`
    # states the same principle from the other side: the order that survives an
    # interruption is the one that wastes a file rather than misreporting.
    with contextlib.suppress(OSError):
        standing.unlink()
    return gone


def ran(command, timeout_seconds: float = COMMAND_SECONDS) -> Ran:
    """Run a command that fetches a value once, and say what it answered.

    **Its input is closed, never inherited.** A keeper that decides to ask a question would
    otherwise hold a gateway for as long as the machine is up, and the timeout would be the
    only thing that could ever end it.

    **Its errors are captured, never inherited.** A keeper that fails routinely prints the
    thing it was reading — a vault path, a key's identity, and on a bad wrapper the value —
    and inheriting that would put it into a gateway's log, which rotates, is read out loud
    and is not where any of it goes.
    """
    try:
        done = subprocess.run(list(command), stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired:
        return Ran(answered=False, ok=False,
                   why=f"it did not answer within {timeout_seconds:g} seconds")
    except (FileNotFoundError, PermissionError, NotADirectoryError, IsADirectoryError) as why:
        # A definite answer: there is no such program to run, so there is no value.
        return Ran(answered=True, ok=False, why=str(why))
    except OSError as why:
        # The machine would not start it — a fork that failed, a descriptor limit. Nothing
        # about the value is known, least of all that there is not one.
        return Ran(answered=False, ok=False, why=str(why))
    why = _first_line(done.stderr)
    if done.returncode != 0:
        return Ran(answered=True, ok=False, why=why or "it ended unsuccessfully")
    value = normalised(done.stdout.decode("utf-8", "replace"))
    if not value:
        return Ran(answered=True, ok=False, why=why or "it printed nothing")
    return Ran(answered=True, ok=True, value=value, why="")


def _first_line(said: bytes) -> str:
    """The first thing a keeper said went wrong, bounded — shown, and never written down."""
    text = (said or b"").decode("utf-8", "replace").strip()
    if not text:
        return ""
    first = text.splitlines()[0].strip()
    return first[:WHY_CHARACTERS] + "…" if len(first) > WHY_CHARACTERS else first


def plainly(trouble: Trouble) -> str:
    """Which kind of not-given this was, in words that may be written down.

    **Never `Trouble.why`**, which is the keeper's own output and routinely holds the thing
    it was reading. A gateway's log and a run's account both stand under `data_home()`,
    which a backup copies whole, so this is what goes there — and it lives here rather than
    being spelled out at each of them, because two hand-written copies of one sentence are
    two sentences the day somebody rewords one. What the keeper actually said is shown by
    `rundesk env check`, at a terminal, where nothing writes it down.
    """
    return "it gave nothing back" if trouble.answered else "it could not answer"


def resolve(where: Path | None = None, run=None, timeout_seconds: float = COMMAND_SECONDS,
            exclude=(), only=None) -> Resolved:
    """Every value this install's programs are given, produced now.

    Nothing is remembered between calls. A vault locked at noon means the next program
    started is missing a variable and says so, and the one after it is unlocked has it
    back — with no restart, no state and nothing to invalidate.

    Commands run **in order and never at once**: ten schedules firing together must not put
    ten prompts in front of somebody, and a keyed vault would ask each time.

    `exclude` is what the caller already has an answer for. A channel adapter's own
    credential is the whole of it today: two agents may hold two different bots, and one
    install-wide value would silently make them the same one.

    **`only` narrows it to the names asked after, and asking about one must never run
    anybody else's keeper.** Checking a held credential that answers instantly would
    otherwise fetch every other value in the registry — extra prompts nobody was told
    about, and a keeper with a side effect of its own (a rotation, an audited read) run
    because somebody looked at something unrelated. `None` is every name, which is what a
    program starting wants.
    """
    running = run if run is not None else ran
    already = set(exclude)
    try:
        kept = _read(where)
    except Unreadable as why:
        return Resolved(values={}, unreadable=str(why))
    values: dict = {}
    trouble: list = []
    held = 0
    for name in sorted(kept):
        said = kept[name]
        if not isinstance(said, dict) or name in already:
            continue
        if only is not None and name not in set(only):
            continue
        why = refused(name)
        if why:
            # Written by a hand-edit, or by a release whose rule was narrower than this
            # one's. Refusing on the way out is what makes a name added to the builder
            # tomorrow stop being given out today, with nobody re-running a command.
            trouble.append(Trouble(name=name, kept_as=_as_kept(name, said).kept_as,
                                   answered=True, why=why))
            continue
        one = _as_kept(name, said)
        got = _fetched(one, where, running, timeout_seconds)
        if not got.ok:
            trouble.append(Trouble(name=name, kept_as=one.kept_as,
                                   answered=got.answered, why=got.why))
            continue
        weight = len(name.encode("utf-8")) + len(got.value.encode("utf-8")) + 2
        if held + weight > SET_LIMIT_BYTES:
            trouble.append(Trouble(
                name=name, kept_as=one.kept_as, answered=True,
                why="what is kept is larger than a program can be started with"))
            continue
        held += weight
        values[name] = got.value
    return Resolved(values=values, trouble=tuple(trouble))


def _fetched(one: Kept, where, running, timeout_seconds: float) -> Ran:
    """One value, however it is kept — and the same three answers either way."""
    if one.kept_as == FETCHED:
        if not one.command:
            return Ran(answered=True, ok=False, why="no command is kept to fetch it with")
        return running(one.command, timeout_seconds=timeout_seconds)
    at = _standing(one.name, where)
    try:
        said = at.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Ran(answered=True, ok=False, why="the value it names is not there")
    except OSError as why:
        # There, and the machine would not hand it over. Nothing about it is known.
        return Ran(answered=False, ok=False, why=str(why))
    value = normalised(said)
    if not value:
        return Ran(answered=True, ok=False, why="what is kept under it is empty")
    return Ran(answered=True, ok=True, value=value)


async def resolved(where: Path | None = None, run=None,
                   timeout_seconds: float = COMMAND_SECONDS, exclude=(),
                   only=None) -> Resolved:
    """The same answer, off the event loop.

    A command that fetches a value is a program somebody else wrote and may take seconds.
    Run on the loop it would hold every other turn, channel and schedule the gateway is
    carrying still while it waited — which is the one thing `process.py` exists never to do.
    """
    return await asyncio.to_thread(
        resolve, where=where, run=run, timeout_seconds=timeout_seconds, exclude=exclude,
        only=only)
