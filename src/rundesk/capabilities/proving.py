"""What this machine really lets rundesk do, settled one probe at a time.

Every answer here comes from **running something and reading what happened**, which is what makes
this a different kind of module from `skills.doctor` — that one states, in its first paragraph, that
it reads no value and runs no program, so that it can be run on a machine somebody is worried about.
This one has no such option: a permission is not a fact on disk, and the only way to know is to try.

## Prove it by doing it, not only by asking about the grant

The rule this package earned the hard way, written up in
`docs/research/2026-08-08-what-this-mac-lets-a-process-do.md` §3. A preflight answers *may I*, and
running the thing answers *did it work*, and **they can disagree**: `/usr/sbin/screencapture` is an
Apple-signed binary with a TCC identity of its own, so shelling out to it captures the screen whether
or not the caller holds Screen Recording. An ungranted process was measured taking a byte-identical
picture of the menu bar to a granted one.

Both answers are true and they are about different things — one about what an agent shelling out will
get, one about whether this process could capture in-process — so **both are probed and each says
what it covers.** Reporting either alone is a wrong answer to somebody.

## Nothing here may prompt

A consent dialog raised by a background gateway is a dialog on somebody's desktop with no context,
and the wrong button on it writes a **denial** that persists. Every query below is a preflight or a
read. Where no non-prompting query exists the probe answers `UNPROVEN`, and that is deliberate: an
honest silence beats a guess that costs the owner a grant they then have to find and undo.

## Everything is a child process, even what could have been a call

A TCC-gated read blocks on a consent dialog with **no way to interrupt it**, and
`utils.programs.run`'s ceiling has no in-process equivalent — `os.listdir` cannot be given one. So
the file probes shell out to an interpreter, the preflights shell out to an interpreter, and the one
thing every probe has in common is that it cannot hang the command.

May depend on `core` and `utils`.
"""

import struct
import sys
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple

from rundesk.capabilities import lineage
from rundesk.utils import programs

# ── The verdicts ──────────────────────────────────────────────────────────────────────────────

#: It works. The only verdict that is not something for somebody to do.
READY = "ready"

#: The machine refused. There is one pane to open, and `fix` names it.
BLOCKED = "blocked"

#: The machine has never been asked, so it is asking whoever is at the desktop **now**. Its own
#: verdict rather than a kind of `BLOCKED`, because a client that has never been prompted **does not
#: appear in that pane at all** — sending somebody there is advice they cannot follow.
UNASKED = "unasked"

#: What it would drive is on this machine and is not running. A probe may not open a window on
#: somebody's desktop to satisfy itself, so this is answered rather than worked around.
CLOSED = "closed"

#: What it would drive is not here at all. There is nothing to grant.
ABSENT = "absent"

#: The program that settles it is not on this machine, or would not start. **Never `BLOCKED`**: a
#: program that was never there refused nothing, which is the distinction `utils.programs` exists to
#: keep and the one every `except Exception: return 1` destroys.
UNRUNNABLE = "unrunnable"

#: It could not be settled either way. **The third state**, and never a quiet form of `READY`.
UNPROVEN = "unproven"

#: Which verdicts mean somebody has work. `UNPROVEN` is among them on purpose: a check that proved
#: nothing has proved nothing, and a command exiting zero on one is a command nobody can gate on.
TROUBLE = (BLOCKED, UNASKED, CLOSED, ABSENT, UNRUNNABLE, UNPROVEN)


# ── How long each kind of thing is given ──────────────────────────────────────────────────────

#: A preflight is a library call in a child interpreter. Anything past this is a machine in trouble.
A_PREFLIGHT_WITHIN = 15.0

#: An Apple Event round trip, to an application that may be busy.
AN_EVENT_WITHIN = 20.0

#: A screen capture, which on a machine with several large displays is really doing work.
A_CAPTURE_WITHIN = 30.0

#: A directory listing or a one-byte read, in a child interpreter.
A_READ_WITHIN = 15.0


# ── The programs a probe settles itself with ──────────────────────────────────────────────────
#
# Written as `-c` sources in the shape `gateways/job.py:HOSTING` already establishes. A child
# interpreter rather than an in-process call for two reasons: a ceiling, per the module docstring,
# and a bad ctypes call is then an exit code rather than a dead command — nothing catches a
# segfault, and being runnable on a machine somebody is worried about is the whole job.

#: Ask CoreGraphics or ApplicationServices one boolean. **The preflight, never the request**:
#: `CGRequestScreenCaptureAccess` and `AXIsProcessTrustedWithOptions` raise a dialog, and these do
#: not. Measured non-prompting in both lineages.
A_PREFLIGHT = (
    "import ctypes,sys\n"
    "lib=ctypes.CDLL(sys.argv[1])\n"
    "fn=getattr(lib,sys.argv[2])\n"
    "fn.restype=ctypes.c_bool\n"
    "print('yes' if fn() else 'no')\n"
)

#: Read a directory, and say **which** refusal it was. `errno` is the whole point: `EPERM` is TCC
#: and `EACCES` is the filesystem's own mode, and they have entirely different fixes.
A_LISTING = (
    "import os,sys\n"
    "try:\n"
    "    os.listdir(sys.argv[1])\n"
    "except OSError as why:\n"
    "    print(f'{type(why).__name__} {why.errno}'); raise SystemExit(1)\n"
    "print('read')\n"
)

#: Open one byte of one file, and nothing else. Used where the canary is a file rather than a
#: directory — the byte is discarded and never printed.
A_TASTE = (
    "import sys\n"
    "try:\n"
    "    open(sys.argv[1],'rb').read(1)\n"
    "except OSError as why:\n"
    "    print(f'{type(why).__name__} {why.errno}'); raise SystemExit(1)\n"
    "print('read')\n"
)

CORE_GRAPHICS = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
APPLICATION_SERVICES = ("/System/Library/Frameworks/ApplicationServices.framework"
                        "/ApplicationServices")

#: `EPERM`. What TCC answers when it refuses a read — measured, from a launchd job holding nothing.
REFUSED_BY_TCC = 1

#: `EACCES`. What the filesystem's own permissions answer, which is a different thing to fix.
REFUSED_BY_THE_FILESYSTEM = 13


# ── Where a fix is ────────────────────────────────────────────────────────────────────────────

#: The System Settings panes, as the deep links a person can be handed. **Unverified on 26.5.1** —
#: `docs/research/2026-08-08-what-this-mac-lets-a-process-do.md` §8.2 records that opening one to
#: check would put a window on the owner's desktop, so this is the one table here that is recalled
#: rather than measured, and it is marked as such where it is printed.
PANE = "open \"x-apple.systempreferences:com.apple.preference.security?Privacy_{which}\""

AUTOMATION = PANE.format(which="Automation")
ACCESSIBILITY = PANE.format(which="Accessibility")
SCREEN_RECORDING = PANE.format(which="ScreenCapture")
INPUT_MONITORING = PANE.format(which="ListenEvent")
FULL_DISK = PANE.format(which="AllFiles")
FILES_AND_FOLDERS = PANE.format(which="FilesAndFolders")
DEVELOPER_TOOLS = PANE.format(which="DevTools")


class Probe(NamedTuple):
    """One thing a machine either lets rundesk do or does not.

    `touches` is what settling it does to the owner's machine, in words, and it is printed **before
    anything runs**. A check whose side effects are only discoverable by running it is a check
    somebody runs once.

    `needed` is set by one question: *is this required to operate the machine?* The agent owns the
    Mac it runs on, so the answer is yes for driving the UI, seeing the screen, scripting what is
    installed and reaching the disk. It is no for the owner's private data — a camera, an address
    book — which is about them rather than about the computer.
    """

    group: str
    name: str
    about: str
    touches: str
    needed: bool
    settle: Callable[["Probe", lineage.Lineage, Path, "Running"], Tuple[str, str, str]]

    @property
    def address(self) -> str:
        return f"{self.group}/{self.name}"


class Proof(NamedTuple):
    """What one probe found, and whose grants that is a fact about.

    **`lineage` is never absent and never dropped.** The same probe run from a terminal and from a
    gateway is two different questions with two different answers, so a `Proof` that did not carry
    which one it was would be a claim about a process nobody named — this command's one way of
    reporting a success it did not earn.

    `fix` is the exact line to type, and `""` where there is nothing to type.
    """

    probe: Probe
    lineage: lineage.Lineage
    verdict: str
    said: str
    fix: str
    ran: Optional[programs.Ran] = None

    @property
    def trouble(self) -> bool:
        return self.verdict in TROUBLE


#: What runs a program. **Handed in, with no default of its own**, for a sharper reason than the
#: rule usually has: there is no closed port for `osascript`. A case that forgot this would not
#: merely reach the machine — it could put a consent dialog on a developer's screen, and one wrong
#: click there denies a grant on their Mac permanently.
Running = Callable[[Sequence[str], float], programs.Ran]


def by_the_machine() -> Running:
    """The real one. Resolved in a body, never bound in a signature."""
    def running(argv: Sequence[str], waiting: float) -> programs.Ran:
        return programs.run(list(argv), waiting)
    return running


# ── Settling one probe ────────────────────────────────────────────────────────────────────────

def _unanswered(whose: lineage.Lineage, ran: programs.Ran) -> Optional[Tuple[str, str, str]]:
    """The two answers every probe shares, or `None` when the program actually said something.

    Shared because getting either wrong is the same mistake in every probe: a program that was never
    on the machine did not refuse anything, and a probe that timed out in a lineage where a dialog
    could be waiting is a different situation from one that timed out where none can appear.
    """
    if ran.trouble is None:
        return None
    if ran.trouble.startswith(programs.DID_NOT_START):
        return UNRUNNABLE, f"the program that settles this is not on this machine ({ran.trouble})", ""
    if whose.can_be_asked:
        return (UNASKED,
                "no answer — the machine is asking whoever is at the desktop, and this cannot "
                "answer for them", "")
    return (UNPROVEN,
            "no answer, and in this lineage no consent dialog can appear to explain why", "")


def _a_preflight(library: str, symbol: str, blocked: str, fix: str):
    """Settle a probe with one non-prompting boolean out of a system framework."""
    def settle(probe: Probe, whose: lineage.Lineage, into: Path, running: Running):
        ran = running([sys.executable, "-c", A_PREFLIGHT, library, symbol], A_PREFLIGHT_WITHIN)
        unanswered = _unanswered(whose, ran)
        if unanswered:
            return unanswered
        said = ran.out.strip()
        if said == "yes":
            return READY, probe.about, ""
        if said == "no":
            return BLOCKED, blocked, fix
        # A framework that would not answer is not a framework that said no. Saying otherwise sends
        # somebody to a pane to fix a grant that may be perfectly in order.
        return UNPROVEN, f"{symbol} answered nothing this release understands", ""
    return settle


def _a_reading(what: Callable[[], Path], source: str, blocked: str, fix: str, missing: str):
    """Settle a probe by reading something, and classify on `errno` rather than on failure."""
    def settle(probe: Probe, whose: lineage.Lineage, into: Path, running: Running):
        where = what()
        ran = running([sys.executable, "-c", source, str(where)], A_READ_WITHIN)
        unanswered = _unanswered(whose, ran)
        if unanswered:
            return unanswered
        said = ran.out.strip()
        if said == "read":
            return READY, f"{where} can be read", ""
        kind, _, number = said.partition(" ")
        errno = int(number) if number.isdigit() else None
        if errno == REFUSED_BY_TCC:
            return BLOCKED, blocked, fix
        if errno == REFUSED_BY_THE_FILESYSTEM:
            # Not a grant at all. Sending somebody to a privacy pane for a mode bit is advice that
            # cannot work, so this says which of the two it is and names the real fix.
            return BLOCKED, f"{where} refuses this by its own permissions, which is not a grant", \
                f"chmod u+rx {where}"
        if kind == "FileNotFoundError":
            return (ABSENT, missing, "") if missing else \
                (UNPROVEN, f"{where} is not on this machine, so nothing can be said either way", "")
        return UNPROVEN, ran.err.strip().splitlines()[0] if ran.err.strip() else said, ""
    return settle


def _a_capture(probe: Probe, whose: lineage.Lineage, into: Path, running: Running):
    """Settle by taking a real picture and looking at it — not by asking whether it is allowed.

    Eight pixels of the top-left corner, so this reads nothing of what is on the owner's screen, and
    the file is removed whatever happens. What proves it is that the bytes decode as a PNG of the
    size that was asked for: a capture that exited zero and wrote something unreadable has not
    proved a machine can be seen.
    """
    shot = into / "capture.png"
    ran = running(["/usr/sbin/screencapture", "-x", "-t", "png", "-R", "0,0,8,8", str(shot)],
                  A_CAPTURE_WITHIN)
    try:
        unanswered = _unanswered(whose, ran)
        if unanswered:
            return unanswered
        if ran.code != 0:
            # Measured: a display that has gone to sleep answers exactly here, and it is neither
            # allowed nor denied. Calling it a refusal would send somebody to a pane to fix a grant
            # that is already given.
            return (UNPROVEN,
                    f"the capture would not run ({ran.err.strip() or f'exit {ran.code}'}) — this is "
                    "not a refusal; a sleeping display answers the same way", "")
        if not shot.exists():
            return UNPROVEN, "the capture exited cleanly and wrote nothing", ""
        raw = shot.read_bytes()
        told = _a_png(raw)
        if told is None:
            return UNPROVEN, f"the capture wrote {len(raw)} bytes that are not a readable PNG", ""
        wide, high = told
        if (wide, high) != (8, 8):
            return UNPROVEN, f"the capture asked for 8x8 and wrote {wide}x{high}", ""
        return READY, f"the screen can be captured — a readable {wide}x{high} image came back", ""
    finally:
        # Removed on every path. A probe that leaves a picture of somebody's screen behind is a
        # probe that has done something worse than fail.
        if shot.exists():
            shot.unlink()


def _a_scriptable(bundle: str, called: str):
    """Settle Automation to one application: is it here, is it running, will it answer.

    `count windows` is the least invasive Apple Event that still needs the grant — it opens nothing,
    changes nothing, and answers `0` for an application with no windows, where reading a front
    window would fail for a reason that has nothing to do with permission.
    """
    def settle(probe: Probe, whose: lineage.Lineage, into: Path, running: Running):
        here = running(["/usr/bin/osascript", "-e",
                        f'POSIX path of (path to application id "{bundle}")'], AN_EVENT_WITHIN)
        unanswered = _unanswered(whose, here)
        if unanswered:
            return unanswered
        if here.code != 0:
            return ABSENT, f"there is no {called} on this machine", ""

        awake = running(["/usr/bin/pgrep", "-x", called], AN_EVENT_WITHIN)
        if awake.trouble is None and awake.code == 1:
            return (CLOSED, f"{called} is here and is not running, and a probe may not start it",
                    f'open -a "{called}"')

        asked = running(["/usr/bin/osascript", "-e",
                         f'tell application "{called}" to count windows'], AN_EVENT_WITHIN)
        unanswered = _unanswered(whose, asked)
        if unanswered:
            return unanswered
        if asked.code == 0:
            return READY, f"Apple Events reach {called} — {asked.out.strip() or '0'} window(s)", ""
        said = asked.err.strip()
        if "-1743" in said or "Not authorized" in said:
            return (BLOCKED, f"{whose.named or 'this process'} may not send Apple Events to "
                             f"{called}", AUTOMATION)
        if "-600" in said:
            return (CLOSED, f"{called} stopped between being found and being asked",
                    f'open -a "{called}"')
        return UNPROVEN, said.splitlines()[0] if said else f"exit {asked.code}", ""
    return settle


def _system_events(probe: Probe, whose: lineage.Lineage, into: Path, running: Running):
    """Two grants stand in front of one script, and they have two different fixes.

    Being refused Apple Events to System Events at all (`-1743`) is the Automation pane; being
    allowed to talk to it and refused assistive access (`-25211`) is the Accessibility pane. One
    finding covering both would send half the people who read it to the wrong place.
    """
    ran = running(["/usr/bin/osascript", "-e",
                   'tell application "System Events" to get name of first process '
                   'whose frontmost is true'], AN_EVENT_WITHIN)
    unanswered = _unanswered(whose, ran)
    if unanswered:
        return unanswered
    if ran.code == 0:
        return READY, f"System Events answered — {ran.out.strip()} is in front", ""
    said = ran.err.strip()
    if "-1743" in said or "Not authorized" in said:
        return (BLOCKED, f"{whose.named or 'this process'} may not send Apple Events to System "
                         "Events at all, which is a different grant from Accessibility", AUTOMATION)
    if "-25211" in said or "assistive access" in said:
        return (BLOCKED, f"{whose.named or 'this process'} is not trusted for Accessibility",
                ACCESSIBILITY)
    return UNPROVEN, said.splitlines()[0] if said else f"exit {ran.code}", ""


def _admin(probe: Probe, whose: lineage.Lineage, into: Path, running: Running):
    """Whether this can become root without anybody typing anything.

    **Reported, never gated, and never requested.** `sudo -n` asks for nothing and waits for nobody;
    an agent that owns the machine but cannot install software should learn that from a verdict
    rather than from a password prompt in a log nobody is watching.
    """
    ran = running(["/usr/bin/sudo", "-n", "true"], A_READ_WITHIN)
    unanswered = _unanswered(whose, ran)
    if unanswered:
        return unanswered
    if ran.code == 0:
        return READY, "this can run a command as root without being asked for a password", ""
    return (BLOCKED, "there is no passwordless sudo here, so anything needing root will stop and "
                     "wait for somebody", "")


# ── What there is to prove ────────────────────────────────────────────────────────────────────

def _control() -> List[Probe]:
    """Driving the machine — **four separate grants**, measured, and each with its own fix.

    Most people expect one switch. An agent granted only Accessibility can read the UI and cannot
    synthesize a keystroke, so a check reporting one line would send somebody to fix one of three
    different things and leave the other two.
    """
    return [
        Probe("control", "accessibility",
              "UI elements can be read and driven",
              "asks whether this process is trusted for Accessibility. Clicks nothing.",
              True,
              _a_preflight(APPLICATION_SERVICES, "AXIsProcessTrusted",
                           "this process is not trusted for Accessibility, so it cannot read or "
                           "drive UI elements", ACCESSIBILITY)),
        Probe("control", "post-events",
              "clicks and keystrokes can be synthesized",
              "asks whether this process may post input events. Posts none.",
              True,
              _a_preflight(CORE_GRAPHICS, "CGPreflightPostEventAccess",
                           "this process may not post input events, so it cannot click or type — "
                           "a separate grant from Accessibility", ACCESSIBILITY)),
        Probe("control", "listen-events",
              "global input can be observed",
              "asks whether this process may observe input events. Observes none.",
              True,
              _a_preflight(CORE_GRAPHICS, "CGPreflightListenEventAccess",
                           "this process may not observe input events (Input Monitoring)",
                           INPUT_MONITORING)),
        Probe("control", "system-events",
              "the scripting bridge most UI automation goes through",
              "asks System Events which application is in front. Clicks nothing, types nothing.",
              True, _system_events),
    ]


def _screen() -> List[Probe]:
    """Seeing the screen — **two probes that measure different things and can disagree.**

    `screencapture` is Apple-signed with a TCC identity of its own, so shelling out to it works
    whether or not this process holds Screen Recording; an ungranted process was measured taking a
    byte-identical picture to a granted one. That is the answer for an agent asked for a
    screenshot. It is not the answer for anything capturing in-process, which needs the real grant.
    """
    return [
        Probe("screen", "capture",
              "a screenshot can actually be taken and read back",
              "captures the top-left eight pixels to a temporary file and deletes it. Nothing of "
              "what is on the screen is kept, printed, or looked at.",
              True, _a_capture),
        Probe("screen", "grant",
              "this process itself holds Screen Recording, for capture that cannot shell out",
              "asks whether this process holds the Screen Recording grant. Captures nothing.",
              True,
              _a_preflight(CORE_GRAPHICS, "CGPreflightScreenCaptureAccess",
                           "this process does not hold Screen Recording — shelling out to "
                           "screencapture still works, but in-process capture and recording do not",
                           SCREEN_RECORDING)),
    ]


def _files() -> List[Probe]:
    """Reaching the disk. Classified on `errno`: EPERM is TCC, EACCES is the filesystem."""
    def under_home(*parts: str) -> Callable[[], Path]:
        return lambda: Path.home().joinpath(*parts)

    folders = [
        ("desktop", "Desktop"), ("documents", "Documents"), ("downloads", "Downloads"),
    ]
    probes = [
        Probe("files", name, f"~/{called} can be listed",
              f"lists the names in ~/{called}. Reads no file and prints no name.", True,
              _a_reading(under_home(called), A_LISTING,
                         f"the machine refuses this process ~/{called}", FILES_AND_FOLDERS,
                         f"there is no ~/{called} on this machine"))
        for name, called in folders
    ]
    probes.append(Probe(
        "files", "full-disk", "Full Disk Access is given",
        "opens one byte of the file macOS keeps grants in, and reads nothing else. The byte is "
        "discarded and never printed.", True,
        _a_reading(under_home("Library", "Application Support", "com.apple.TCC", "TCC.db"),
                   A_TASTE,
                   "Full Disk Access is not given — and there is no prompt for it; the program is "
                   "added by hand", FULL_DISK, "")))
    probes.append(Probe(
        "files", "app-data", "other applications' stored data can be reached",
        "lists one directory under ~/Library/Application Support. Reads no file.", True,
        _a_reading(under_home("Library", "Application Support"), A_LISTING,
                   "the machine refuses this process other applications' stored data", FULL_DISK,
                   "")))
    return probes


def _shell() -> List[Probe]:
    """The half of operating a Mac that TCC has nothing to do with."""
    return [
        Probe("shell", "admin", "software can be installed without somebody typing a password",
              "asks sudo whether it would run without a password. Runs `true` and nothing else.",
              False, _admin),
    ]


#: Every group there is, as the functions that build them. **A probe set is found rather than
#: listed**, the way migration steps, skills and suites already are here — and `every()` refuses an
#: empty discovery for the reason `scripts/suites` does: a set that quietly shrank would report a
#: clean machine.
GROUPS: Tuple[Callable[[], List[Probe]], ...] = (_control, _screen, _files, _shell)


class Empty(Exception):
    """Nothing was found to prove, which is never an answer about a machine."""


def every() -> List[Probe]:
    """Every probe there is, in the order they are worth reading. Fails on an empty discovery."""
    found: List[Probe] = []
    for group in GROUPS:
        found.extend(group())
    if not found:
        raise Empty("no probes were found at all, so nothing about this machine can be said")
    return found


def groups() -> List[str]:
    """Every group name, in order, without repeating one."""
    seen: List[str] = []
    for one in every():
        if one.group not in seen:
            seen.append(one.group)
    return seen


def needed() -> List[Probe]:
    """What a bare check proves: everything required to operate the machine."""
    return [one for one in every() if one.needed]


def named(what: Sequence[str]) -> List[Probe]:
    """The probes a person named, by group or by address. Empty when nothing matched.

    Empty is handed back rather than raised, because *what to say about a name nobody has* is the
    caller's — and what it says is a refusal listing what there is, never a clean empty table.
    """
    wanted = [one.strip() for one in what if one.strip()]
    if not wanted:
        return []
    return [one for one in every()
            if one.address in wanted or one.group in wanted]


def proved(probe: Probe, whose: lineage.Lineage, into: Path,
           running: Optional[Running] = None) -> Proof:
    """Settle one probe now. Never raises for anything the machine did.

    `into` is handed in and never chosen here: `RUNDESK_HOME` is the only location this product
    reads, and a probe's scratch file is not below it.
    """
    running = running if running is not None else by_the_machine()
    try:
        verdict, said, fix = probe.settle(probe, whose, into, running)
    except Exception as why:  # noqa: BLE001 — a probe that broke is a probe that proved nothing.
        return Proof(probe, whose, UNPROVEN, f"this probe could not be run ({why})", "")
    return Proof(probe, whose, verdict, said, fix)


def looked_over(probes: Sequence[Probe], whose: lineage.Lineage, into: Path,
                running: Optional[Running] = None) -> List[Proof]:
    """Settle each of these, in order."""
    return [proved(one, whose, into, running) for one in probes]


def counted(found: Sequence[Proof]) -> List[Proof]:
    """The ones somebody has work to do about."""
    return [one for one in found if one.trouble]


def fixes(found: Sequence[Proof]) -> List[str]:
    """Every distinct thing to type, in the order it is first needed.

    Deduplicated, because six probes blocked on one pane is one thing to go and do, and printing it
    six times is how a summary stops being read.
    """
    seen: List[str] = []
    for one in found:
        if one.fix and one.fix not in seen:
            seen.append(one.fix)
    return seen


def _a_png(raw: bytes) -> Optional[Tuple[int, int]]:
    """The width and height of a PNG, or `None` if these bytes are not one.

    The signature and `IHDR` are the first 24 bytes, so this reads a header rather than decoding an
    image — the question is whether a picture came back, not what is in it.
    """
    if len(raw) < 24 or raw[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    try:
        wide, high = struct.unpack(">II", raw[16:24])
    except struct.error:
        return None
    return int(wide), int(high)


def as_written(found: Proof) -> Dict[str, str]:
    """One proof as the columns a person reads. Kept beside the verdicts so they stay in step."""
    return {"probe": found.probe.address, "verdict": found.verdict, "said": found.said}
