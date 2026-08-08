"""Whose grants an answer about this machine would be a fact about.

macOS does not attribute a permission to the process that asks for it. It walks up to the nearest
**application bundle** and makes that the *responsible process*, which is why everything started from
a terminal inherits whatever the owner once granted that terminal, and why a launchd job — which has
no application anywhere above it — is its own responsible process and holds nothing.

That was measured rather than reasoned, and the measurement is the reason this module exists:

    a shim run from iTerm      responsible = iTerm.app       screen recording: yes
    the same shim under launchd responsible = itself          screen recording: no

**So a probe run from `rundesk ask` at a terminal reports that a gateway can capture the screen when
it cannot.** Nothing else in this package is allowed to hand back an answer without saying which of
those two it measured.

## The responsible process is asked for, not inferred

`responsibility_get_pid_responsible_for_pid` is the question TCC itself answers, and it was measured
giving the right answer in both lineages. Walking the parent chain and guessing from it would be
re-deriving, badly, something the platform will simply say — and the guess and the truth would
diverge on exactly the machines nobody tests on.

The parent chain is still read, for two things the responsible pid cannot say: **which agent's shim
this is** (the chain is where the name survives, because the shim `exec`s the interpreter and its own
name is gone from the running image), and **whether this is an ssh session**, where no dialog can
appear at all. So: identity from the platform, classification from the chain.

## Five answers, and the last two are not the same

A chain read whole that matched nothing is **not** a chain nobody could read. `UNKNOWN` is a
machine arranged in a way this release has not met; `CANNOT_TELL` is no information. Folding them
gives a command that reports a definite answer about a machine it could not look at, which is the
one thing this package exists not to do.

May depend on `core` and `utils`.
"""

import ctypes
import ctypes.util
import plistlib
import re
from pathlib import Path
from typing import Callable, List, NamedTuple, Optional, Tuple

from rundesk.utils import programs

#: A descendant of one agent's gateway shim — the gateway itself, a scheduled firing, or a turn.
#: What every answer an agent actually needs is about.
GATEWAY = "gateway"

#: A descendant of an application bundle, named by its bundle identifier. Everything run by hand.
TERMINAL = "terminal"

#: A descendant of `sshd`. There is no login session, so **no consent dialog can appear at all** —
#: which is a different situation from a denial and gets different advice.
REMOTE = "remote"

#: The chain was read whole and matched none of the above.
UNKNOWN = "unknown"

#: The chain could not be read. **Never folded into `UNKNOWN`** — see the module docstring.
CANNOT_TELL = "cannot tell"

#: Which lineages a consent dialog can appear in front of somebody in. The whole reason it matters:
#: the same unanswered probe is a dialog waiting on a desktop in one lineage and a flat refusal in
#: another, and those are two different things for a person to do.
CAN_BE_ASKED = (TERMINAL,)

#: How far up the parent chain to walk before giving up. A ceiling rather than a trust in the tree
#: being a tree: a pid that reports itself as its own parent is a loop, and this is read on a
#: machine somebody is already worried about.
AS_FAR_AS = 24

#: What an executable inside an application bundle looks like. The `.app` is what macOS attributes
#: to, so this is the pattern that decides whether a terminal is lending its grants.
INSIDE_A_BUNDLE = re.compile(r"^(?P<bundle>.*\.app)/Contents/MacOS/[^/]+$")

#: How long `ps` is given. It is being asked one question about one pid; a wait beyond this is a
#: machine in trouble, and the honest answer then is `CANNOT_TELL`.
PS_WITHIN = 5.0


class Lineage(NamedTuple):
    """Whose grants an answer about this machine would be a fact about.

    `how` is the field to read first. `named` is **the TCC client** — what the owner will actually
    find in a System Settings row — and it is deliberately not the agent: the shim `exec`s the
    interpreter, so `rundesk-gateway-marcus` is gone from the running image before anything gated is
    called, and a fix line naming it would send somebody looking for a row that is not there.

    `agent` is carried anyway, because it is what makes a heading readable, and is never what a fix
    line points at.

    `said` is how it was decided, in words, including when the decision was a fallback rather than
    an answer.
    """

    how: str
    named: str
    agent: Optional[str]
    chain: List[str]
    said: str

    @property
    def can_be_asked(self) -> bool:
        """Whether a consent dialog could appear in front of somebody in this lineage."""
        return self.how in CAN_BE_ASKED

    @property
    def certain(self) -> bool:
        """Whether anything may be proved at all. Nothing is, when nobody can say whose it would be."""
        return self.how != CANNOT_TELL


class Machine(NamedTuple):
    """What the process table will say, as two questions.

    **Handed in, never imported** — the rule `cli.main` applies to `asking` and `fetching`, for a
    sharper reason than either: a case that reached the real process table would be a case whose
    answer depends on how the suite was started, and this whole module exists because that changes
    the answer.

    Each answers `None` for a pid nobody could be told about, which is a third answer and not a
    root: a process whose parent cannot be read has not reached the top of the tree.
    """

    responsible: Callable[[int], Optional[int]]
    image: Callable[[int], Optional[str]]
    parent: Callable[[int], Optional[Tuple[int, str]]]


def read(pid: int, *, shim: str, machine: Optional[Machine] = None,
         agent: Optional[str] = None) -> Lineage:
    """Say whose grants anything measured by this process would be a fact about.

    `shim` is the prefix a gateway's launchd program is named with, and `agent` the name this process
    was started for. **Both are passed in**: this package may not import `gateways`, and spelling
    `rundesk-gateway-` a second time here is the drift `tests/test_layers.py` already guards against
    for `standing.LOCK` and `directory.GATEWAY_LOCK`.

    Resolved in the body rather than bound in the signature, so a case can replace it.
    """
    machine = machine if machine is not None else by_the_platform()
    mine = machine.image(pid)
    if mine is None:
        return Lineage(CANNOT_TELL, "", agent, [], f"nothing could be read about process {pid}")

    chain, whole = _walked(pid, machine)
    named_by_the_chain = _named_in(chain, shim)

    # The platform's own answer, asked for rather than inferred. A pid it will not answer about is
    # not a pid that is its own responsible process — that is the distinction the third state keeps.
    answered = machine.responsible(pid)
    if answered is None:
        return Lineage(CANNOT_TELL, "", agent or named_by_the_chain, chain,
                       "the platform would not say which process is responsible for this one")
    responsible = machine.image(answered)
    if responsible is None:
        return Lineage(CANNOT_TELL, "", agent or named_by_the_chain, chain,
                       f"process {answered} is responsible for this one and could not be read")

    # Asked in this order, and the order is the answer to "which of several true things do I say".
    #
    # **Something *else* has to be responsible for this to be a lent grant**, and that clause is
    # load-bearing rather than tidy. Homebrew's interpreter lives at
    # `…/Python.framework/…/Python.app/Contents/MacOS/Python` — it is itself inside an application
    # bundle — so a gateway, which is its own responsible process, matches the bundle pattern
    # exactly as a terminal does. Without this, every gateway on a Homebrew Python would be reported
    # as a terminal, the lineage would read as one a dialog can appear in, and the whole
    # distinction this module exists for would invert on the commonest install there is.
    found = INSIDE_A_BUNDLE.match(responsible) if answered != pid else None
    if found:
        told, guessed = _bundle_identity(Path(found.group("bundle")))
        return Lineage(TERMINAL, told, agent or named_by_the_chain, chain,
                       f"{responsible} is responsible for this process"
                       + (" — its identifier could not be read, so this is its name on disk"
                          if guessed else ""))

    if named_by_the_chain is not None:
        return Lineage(GATEWAY, responsible, named_by_the_chain, chain,
                       "this process is its own responsible process, below the gateway shim "
                       f"for {named_by_the_chain}")

    if any(Path(one).name == "sshd" for one in chain):
        return Lineage(REMOTE, responsible, agent, chain,
                       "this process descends from sshd, so there is no desktop for a consent "
                       "dialog to appear on")

    if not whole:
        return Lineage(CANNOT_TELL, "", agent, chain,
                       "the parent chain could not be read to the top, so what this descends from "
                       "is unknown rather than nothing")

    return Lineage(UNKNOWN, responsible, agent, chain,
                   "the parent chain was read whole and matched no lineage this release knows")


def by_the_platform() -> Machine:
    """The real process table. Resolved in a body, never bound in a signature.

    `proc_pidpath` and `responsibility_get_pid_responsible_for_pid` both live in libSystem and both
    were measured answering correctly from a terminal and from a launchd job. The second is not a
    documented interface; a machine that will not answer it gets `CANNOT_TELL`, which is why the
    caller has a third state rather than a default.
    """
    libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.dylib", use_errno=True)

    def image(pid: int) -> Optional[str]:
        held = ctypes.create_string_buffer(4096)
        try:
            wrote = libc.proc_pidpath(ctypes.c_int(int(pid)), held, ctypes.c_uint32(4096))
        except (AttributeError, OSError, ValueError):
            return None
        return held.value.decode("utf-8", "replace") if wrote > 0 else None

    def responsible(pid: int) -> Optional[int]:
        try:
            asked = libc.responsibility_get_pid_responsible_for_pid
        except AttributeError:
            return None
        asked.restype = ctypes.c_int
        asked.argtypes = [ctypes.c_int]
        try:
            answered = asked(ctypes.c_int(int(pid)))
        except (OSError, ValueError):
            return None
        return None if answered < 0 else int(answered)

    return Machine(responsible=responsible, image=image, parent=by_ps())


def by_ps(waiting: float = PS_WITHIN) -> Callable[[int], Optional[Tuple[int, str]]]:
    """One pid's parent and command, out of `ps`. `None` where it would not say.

    `ps` rather than a second libc structure because the parent is only ever used to *classify* —
    the identity comes from the responsible process — and a text answer a person can read in the
    chain is worth more here than a struct.
    """
    def parent(pid: int) -> Optional[Tuple[int, str]]:
        ran = programs.run(["/bin/ps", "-o", "ppid=,comm=", "-p", str(int(pid))], waiting)
        if ran.trouble is not None or ran.code != 0:
            return None
        said = ran.out.strip().split(None, 1)
        if len(said) != 2 or not said[0].isdigit():
            return None
        return int(said[0]), said[1].strip()

    return parent


def _walked(pid: int, machine: Machine) -> Tuple[List[str], bool]:
    """Every ancestor's command, nearest first, and whether the top was actually reached.

    The second half is the point. A chain that stopped because nothing would answer looks exactly
    like one that stopped at the top, and a caller that could not tell them apart would report
    `UNKNOWN` — a definite claim — about a tree it never saw.
    """
    chain: List[str] = []
    seen = {pid}
    at = pid
    for _ in range(AS_FAR_AS):
        answered = machine.parent(at)
        if answered is None:
            return chain, False
        up, called = answered
        # pid 1 is launchd and is the top; a pid that is its own parent, or one already seen, is a
        # loop rather than a top, and walking it is how a diagnosis hangs on a broken machine.
        if up in seen or up <= 0:
            return chain, True
        chain.append(called)
        seen.add(up)
        at = up
        if up == 1:
            return chain, True
    return chain, False


def _named_in(chain: List[str], shim: str) -> Optional[str]:
    """The agent whose gateway shim stands in this chain, or `None`.

    The chain is where an agent's name survives at all: the shim's last line `exec`s the interpreter,
    so by the time anything gated is called the running image is a Python and the name is gone.
    """
    for one in chain:
        called = Path(one).name
        if shim and called.startswith(shim) and len(called) > len(shim):
            return called[len(shim):]
    return None


def _bundle_identity(bundle: Path) -> Tuple[str, bool]:
    """An application's identifier, and whether that is what it is or only what it is called.

    A bundle whose `Info.plist` will not read is still a real answer about which application is
    responsible — its name on disk says so. **Reported as a guess rather than as an identifier**,
    because a fix line telling somebody to find a row by the wrong name is worse than one that
    admits which it is.
    """
    try:
        with open(bundle / "Contents" / "Info.plist", "rb") as reading:
            said = plistlib.load(reading)
    except (OSError, ValueError, plistlib.InvalidFileException):
        return bundle.stem, True
    told = said.get("CFBundleIdentifier")
    return (str(told), False) if told else (bundle.stem, True)
