"""Handing one gateway to the machine's supervisor, and the four ways of asking whether it is there.

`launchd` is the only thing on a Mac that will start a gateway at login and put it back when it
dies, and it is also the layer this product has been burned by most. What is here is written from
`docs/research/launchd-on-macos.md`, which was established read-only against a real machine; every
decision below is one of that page's findings and is named where it is made.

## The supervisor arrives as an argument, and it is a named type

`Supervising` is passed in, exactly as `lifecycle.release.Asking` and `commands.update.Fetching`
are — and for a stronger reason than either. Those two leave the machine, and a test that forgot to
replace one fails loudly on somebody's network. This one does not leave the machine: **the real
implementation would answer a test perfectly well, against the owner's own login session**, booting
out jobs that keep real work running. There is no closed port to point it at and no failure to
notice. So the seam is the whole of the defence, and it is resolved **inside** the body of every
function that needs one — a default bound in a signature is decided once, when this module is
defined, and nothing can reach past it.

## The label belongs to the person, not to a directory

`RUNDESK_HOME` isolates everything else this product keeps. **It cannot isolate a launchd label.**
A label is a name in one user's login domain, so two installs that derive the same label are two
installs pointing at one job — and the build this replaces recorded exactly that: a second install's
uninstall booted out the live install's gateway, because both had called it `ai.rundesk.gateway`.

So the root is part of the name: `ai.rundesk.<8 hex of a sha256 of the resolved RUNDESK_HOME>.
gateway.<agent>`. A scratch root and a real one derive different labels and cannot reach each
other's jobs. What that does **not** do is make a label private — the override store, the login
domain and Background Task Management are all the owner's, and every one of them outlives this
install.

**Nothing here ever sweeps or prefix-matches `ai.rundesk`.** The label a `Job` carries is checked
against the root that `Job` names on every operation, so a label and a root that disagree is refused
rather than acted on. That check is the whole of the fix for the incident above.

## Bootstrapping is starting, and there is no "install it stopped"

`KeepAlive {"SuccessfulExit": false}` implies `RunAtLoad` — `man 5 launchd.plist`: *the job needs to
run at least once before an exit status can be determined*. So placing the job starts the gateway,
and no command surface above this may imply otherwise.

The other half of that contract belongs to `host`: with `SuccessfulExit: false`, **0 means do not
bring me back and anything else means bring me back**, so a gateway that is refusing to run has to
reach 0 on every path. `host` says why at length; it is repeated here because the plist written
below is what makes it true.

## Every plist write is followed by bootout, then bootstrap

launchd holds an imported copy of a plist and nothing watches the file, so overwriting it changes
nothing. Worse, re-bootstrapping a label from a different path **keeps the existing definition and
does not fail** — `Attempt to re-bootstrap service from different path, will use existing`. A build
that rewrote a plist and bootstrapped over it would go on running the old program for ever with
nothing on the command line saying so. So the cycle is unconditional, `bootout --wait` first, and a
bootout that did not clearly succeed stops the bootstrap rather than racing it.

## The label is enabled unconditionally, every time

The override store is `/var/db/com.apple.xpc.launchd/disabled.<uid>.plist`, it is keyed by label, it
persists across reboots, and **it outlives the plist**: this machine carries a record for
`ai.rundesk.gateway`, whose plist no longer exists anywhere. There is an `enable` verb and a
`disable` verb and nothing that deletes an entry, so the only defence against an override nobody
remembers is to `enable` before every bootstrap. It starts nothing and costs one call.

May depend on `agents`, `core` and `utils`. **`host` may not import this** — see that module.
"""

import hashlib
import os
import plistlib
import re
import shlex
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Protocol

from rundesk.gateways import standing
from rundesk.utils import files, programs

#: The family every rundesk label begins with, the fingerprint of the install it belongs to, and the
#: agent it hosts. Read as one name and never matched as a prefix — see the module docstring.
FAMILY = "ai.rundesk"
GATEWAY = "gateway"

#: How much of the digest goes into the label. Eight hex characters distinguish the handful of
#: installs one person has; this is a name, not a secret, and nothing anywhere is decided by it
#: being hard to guess.
FINGERPRINT = 8

#: What an agent's name may be **in a label**, which is narrower than what it may be as a directory.
#: `launchd` cannot persist the disable state of a label holding a character outside this set, so an
#: agent named outside it would be one that cannot be enabled again once anything disables it.
IN_A_LABEL = re.compile(r"^[A-Za-z0-9._-]+$")

#: Where a user's agent plists stand. Resolved in the body of `job` rather than bound anywhere a
#: caller cannot reach: a suite that wrote here would be writing into the owner's real login items.
LAUNCH_AGENTS = ("Library", "LaunchAgents")

#: The supervisor itself, by absolute path — nothing here depends on a PATH.
LAUNCHCTL = "/bin/launchctl"

#: How long each kind of call is given. `take_back` is the long one on purpose: `bootout --wait`
#: blocks for the whole of `ExitTimeOut` when a gateway is slow to go, and `launchctl help bootout`
#: warns in as many words that it *may block indefinitely*.
ASK_SECONDS = 10.0
TAKE_BACK_SECONDS = 40.0

#: How long launchd waits between `SIGTERM` and `SIGKILL`, and therefore how long a `bootout --wait`
#: can block. Written into the plist explicitly because both of those follow from it.
EXIT_TIMEOUT = 25

#: The shortest gap between two spawns of this job. **Ten is the documented default and buys
#: nothing**; a gateway that dies inside ten seconds is broken rather than busy, and the value is
#: here to keep a crash loop from writing a traceback into `gateway.err` three times a minute.
THROTTLE = 30

#: The whole of the environment a launchd job inherits is `PATH=/usr/bin:/bin:/usr/sbin:/sbin`
#: — measured. No `HOME`, no `USER`, no `LANG`, no shell rc file, no Homebrew and no `~/.local/bin`,
#: which is the exact reason the build this replaces lost a provider that its owner's login shell
#: found instantly. So the whole of `PATH` is written down, ours first.
ALSO_ON_PATH = (".local/bin",)
BREW_AND_LOCAL = ("/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin")
LAUNCHD_PATH = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")

#: A locale, because the job is given none and Python 3.9 mishandles non-ASCII under `POSIX`.
#: `TMPDIR` is deliberately **not** carried: it is a per-session path belonging to whoever placed
#: the job, and `tempfile` falls back correctly without it.
LANG = "en_US.UTF-8"

#: What launchd answers with. Named rather than written at the branch that reads them, because these
#: are the whole of the conversation and each one was paid for by a real failure.
ALREADY_THERE = (17, 37)                 #: bootstrap: this label is already loaded
GO_AND_READ_THE_LOG = 5                  #: bootstrap: launchd's catch-all — the reason is in the log
NO_GUI_SESSION = (112, 125)              #: no login domain for this uid: over SSH, or logging out
NOT_KNOWN = 113                          #: launchd has no record of this label — ambiguous, see `stands`
ALREADY_GONE = (3, 113)                  #: bootout: it was not there, which is the state asked for
IS_DISABLED = 119                        #: the override store says no

#: Where the only account of a Login Items denial is. World-readable, an `NSKeyedArchiver` archive,
#: and **undocumented** — so every read of it is guarded and answers `None` rather than a guess.
BTM = Path("/var/db/com.apple.backgroundtaskmanagement/BackgroundItems-v16.btm")

#: The bit of a BTM row's `disposition` that is set while the owner has the item switched on.
#: Consistent with every agent on the machine this was read from, which is not proof — hence `None`.
BTM_ENABLED = 0x1

#: How `stands` answers, in three words for the reason `standing` has three: a job nobody can ask
#: about is not a job that is not there, and `launchctl print` says 113 for at least four different
#: situations that cannot be told apart from each other.
PLACED = "placed"
NOT_PLACED = "not placed"
CANNOT_TELL = "cannot tell"

#: What runs the gateway. A shim rather than a `#!` line on a Python file, and a handoff rather than
#: a subcommand: settling and hosting are steps of running rundesk rather than operations anybody
#: performs, and `commands.update` already establishes the shape.
HOSTING = (
    "import sys;"
    "sys.path.insert(0, sys.argv[1]);"
    "from rundesk.gateways.host import run;"
    "raise SystemExit(run(sys.argv[2]))"
)

_SHIM = """\
#!/bin/sh
# Written by rundesk when this gateway's job was placed, and rewritten every time it is placed
# again. Nothing here is yours to edit: the job that runs it is derived from the same values.
#
# **This file exists in order to be named.** macOS lists a background item by its executable's
# basename, so a job pointed straight at an interpreter shows the owner an anonymous `python` row
# in Login Items & Extensions — several identical ones, once there are several agents — and one
# careless toggle takes them all away. A denial there removes the service from launchd outright,
# `print` then answers 113, and there is no command of any kind that puts it back.
exec {python} -c {hosting} {src} {name}
"""


class Refused(Exception):
    """Something that may not be asked of launchd, named with why.

    Raised rather than reported, because every one of these is a caller error about identity — a
    label from another install, or an agent named something a label cannot carry — and carrying on
    would act on somebody else's job.
    """


class Job(NamedTuple):
    """One gateway's job: which agent, which install, and the name launchd knows it by.

    Built by `job`, which is the one place the label is derived and the one place the directory
    plists are kept in is resolved. **The label is carried rather than re-derived at each call, and
    checked against `root` before every operation** — a `Job` whose label does not fingerprint to
    its own root is exactly the shape of the incident this module exists to have removed, and it is
    refused rather than acted on.

    `at` is the agent's own directory and `root` is the install's, both handed in: nothing in this
    package derives a location, so a job can be written and read entirely inside a scratch tree.
    """

    name: str
    at: Path
    root: Path
    into: Path
    label: str


class Placed(NamedTuple):
    """How placing a job went, in the three answers launchd's exit codes actually support.

    `how` is `PLACED`, `NOT_PLACED` or `CANNOT_TELL`, and the third is not a polite form of the
    second: no login session for this uid, or launchd's catch-all `5`, are both states where the
    honest report is that nobody can say, and `why` is where the person is told what to read next.
    """

    how: str
    why: str


class Stands(NamedTuple):
    """Where a job stands, read from four independent places because no one of them can answer.

    `how` first, and it is one of three words. `NOT_PLACED` is the **only** safe "no" and it needs
    two of the four sources to agree; everything else ambiguous is `CANNOT_TELL`.

    `disabled` is the override store's answer and `allowed` is Background Task Management's, and
    both are `Optional[bool]` because both can fail to be read at all — a `False` invented for
    either would be a report of health that nothing measured. `plist` is whether the file this
    install would write is on disk, which is what turns one of launchd's four different 113s into
    an answer.
    """

    how: str
    disabled: Optional[bool]
    allowed: Optional[bool]
    plist: bool
    why: str


class Supervising(Protocol):
    """The machine's supervisor, as the operations a job has of it: place, take back, kick, ask.

    A `Protocol` rather than a base class, so the real one and a test's stand-in have nothing in
    common but the shape — and so nothing in this module can accidentally reach a method the seam
    does not name.

    Every one of these hands back `utils.programs.Ran`, which keeps the distinction that decides
    everything here: a `launchctl` that ran and answered `113` and a `launchctl` that was not on the
    machine are different facts, and an implementation that collapsed them would have this module
    report "not installed" for a broken PATH.

    **Nothing here may pipe `launchctl` through anything.** A pipeline's exit status is the last
    command's, so a `launchctl` that really answered 113 reads as 0 — an hour of the research went
    to that, and it would have cost a wrong answer here.
    """

    def allow(self, label: str) -> programs.Ran:
        """`enable` — clear any override on this label. Starts nothing."""

    def take_back(self, label: str) -> programs.Ran:
        """`bootout --wait` — unload the job and wait for the process to actually be gone."""

    def place(self, plist: Path) -> programs.Ran:
        """`bootstrap` — hand this plist to the login domain, which also starts it."""

    def kick(self, label: str) -> programs.Ran:
        """`kickstart -kp` — start it now, past whatever throttle it is sitting behind.

        **Nothing in this module calls it yet**, and saying so is better than implying otherwise:
        placing a job with this plist already starts it, and the state `kick` answers is a gateway
        that is crash-looping behind an exponential backoff. It is named and implemented now
        because the first verb that has to start a job already placed is the verb that would
        otherwise invent its own way of doing it — the same reason `utils.files.name_trouble`
        shipped before anything called it.
        """

    def asked_about(self, label: str) -> programs.Ran:
        """`print` — what launchd knows about this label, if anything."""

    def refusals(self) -> programs.Ran:
        """`print-disabled` — the whole override store for this domain, which `print` never shows."""


class Launchd:
    """`launchctl` itself, run through `utils.programs` with a ceiling on every call.

    The domain is `gui/<uid>`, which exists only while that uid owns a live GUI session — over SSH
    into a machine nobody has logged into at the desktop, every call here answers `112`, and that is
    reported as *cannot tell* rather than as *not running*.
    """

    def __init__(self, uid: Optional[int] = None) -> None:
        # Resolved in the body, like everything else here. A uid bound at import is a uid a test
        # cannot replace, and the whole point of this class is that a test never reaches it at all.
        self.uid = os.getuid() if uid is None else uid

    @property
    def domain(self) -> str:
        return f"gui/{self.uid}"

    def target(self, label: str) -> str:
        return f"{self.domain}/{label}"

    def allow(self, label: str) -> programs.Ran:
        """`enable`, falling back to the user domain when the login one refuses the verb.

        `man launchctl` says `enable` may only target the system domain or the user and user-login
        domains. `gui/<uid>` is a user-login domain and is the right one; `125` means this launchd
        disagrees, and `user/<uid>` is the same override store reached by its other name.
        """
        said = self._ran(["enable", self.target(label)], ASK_SECONDS)
        if said.code == 125:
            return self._ran(["enable", f"user/{self.uid}/{label}"], ASK_SECONDS)
        return said

    def take_back(self, label: str) -> programs.Ran:
        """`bootout --wait`, which is the service-target form because `--wait` requires one.

        Without `--wait` this is asynchronous and **reports success while the label is still
        registered and the process still running** — measured, on a real gateway. A build that read
        rc 0 as "it is gone" and bootstrapped next met launchd's I/O error and ended with no job.
        """
        return self._ran(["bootout", "--wait", self.target(label)], TAKE_BACK_SECONDS)

    def place(self, plist: Path) -> programs.Ran:
        """`bootstrap`, which takes a domain and a path and never a service target."""
        return self._ran(["bootstrap", self.domain, str(plist)], ASK_SECONDS)

    def kick(self, label: str) -> programs.Ran:
        """`kickstart -kp` — kill whatever is there and start it now, past any throttle."""
        return self._ran(["kickstart", "-kp", self.target(label)], ASK_SECONDS)

    def asked_about(self, label: str) -> programs.Ran:
        return self._ran(["print", self.target(label)], ASK_SECONDS)

    def refusals(self) -> programs.Ran:
        return self._ran(["print-disabled", self.domain], ASK_SECONDS)

    def _ran(self, verb: List[str], waiting: float) -> programs.Ran:
        """One `launchctl`, captured whole. Never through a shell and never through a pipe."""
        return programs.run([LAUNCHCTL, *verb], waiting)


def fingerprint(root: Path) -> str:
    """Which install this is, in eight hex characters of a digest of its resolved root.

    **Resolved**, because a root reached through a symlink or spelled with a `..` segment is the
    same directory and must be the same install: two spellings that fingerprinted differently would
    give one install two jobs for one agent, both of which would start.
    """
    settled = Path(root).expanduser().resolve()
    return hashlib.sha256(str(settled).encode("utf-8")).hexdigest()[:FINGERPRINT]


def label_for(name: str, root: Path) -> str:
    """The one name launchd knows this gateway by. See the module docstring for why the root is in it."""
    trouble = name_trouble(name)
    if trouble:
        raise Refused(trouble)
    return f"{FAMILY}.{fingerprint(root)}.{GATEWAY}.{name}"


def name_trouble(said: str) -> str:
    """Why this agent's name may not go into a label, or `""` when it may.

    Narrower than `agents.directory.name_trouble` on purpose, and this is the only place that
    knows why: launchd cannot persist the disable state of a label carrying a character outside
    `[A-Za-z0-9._-]`, so such an agent would be one that could never be enabled again after
    anything disabled it — including a stale `unload -w` from a troubleshooting session years ago.
    """
    if not said or not IN_A_LABEL.match(said):
        return (f"{said!r} cannot be part of a launchd label — an agent hosted by one is named with "
                "letters, digits, a dot, a dash or an underscore")
    return ""


def job(name: str, at: Path, root: Path, into: Optional[Path] = None) -> Job:
    """Everything one gateway's job is, with its label derived once.

    `into` is where this user's agent plists stand and is resolved **here**, in a body, rather than
    defaulted in any signature a caller might not pass: the real answer is the owner's own
    `~/Library/LaunchAgents`, and a suite that reached it would be editing their real login items.
    """
    where = Path(into) if into is not None else Path.home().joinpath(*LAUNCH_AGENTS)
    return Job(name, Path(at), Path(root), where, label_for(name, root))


def plist_of(one: Job) -> Path:
    """The file this job's definition is written to. **Named for the label**, which `man` requires."""
    return one.into / f"{one.label}.plist"


def shim_of(one: Job) -> Path:
    """The named program launchd is pointed at, inside the agent's own directory.

    Inside the agent's directory rather than under `app/`, which an update replaces whole: a job
    whose program vanished mid-update spawns, fails, and is **removed by launchd** — after which
    `print` answers 113 and nothing on the command line says the job was ever there.
    """
    return one.at / f"rundesk-{GATEWAY}-{one.name}"


def document(one: Job) -> Dict[str, object]:
    """The plist this job is, as a value — so a test reads what launchd would read.

    Every decision in here is a finding from the research, and the ones that are absent are as
    deliberate as the ones that are present:

    **No `RunAtLoad`.** `KeepAlive {"SuccessfulExit": false}` implies it, so writing it as well
    would suggest there is a way to place this job without starting it. There is not.

    **`ThrottleInterval` is meaningful or it is not written.** Ten is the documented default.

    **`ExitTimeOut` is explicit**, because it is the window `bootout --wait` blocks for and the
    window `host` has to shut down inside. Two things depend on it, so neither may guess.

    **Every value in `EnvironmentVariables` is a `str`.** `man 5 launchd.plist`: *values other than
    strings will be ignored* — silently, so an accidental `int` is a variable the gateway simply
    never gets, and the first symptom is a gateway resolving somewhere else entirely.
    """
    out, err = standing.captured(one.at)
    return {
        "Label": one.label,
        # A named per-install shim, never a bare interpreter — see `_SHIM` and §4 of the research.
        "ProgramArguments": [str(shim_of(one))],
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": THROTTLE,
        "ExitTimeOut": EXIT_TIMEOUT,
        "WorkingDirectory": str(one.at),
        "StandardOutPath": str(out),
        "StandardErrorPath": str(err),
        "EnvironmentVariables": _the_environment(one),
    }


def place(one: Job, supervising: Optional[Supervising] = None) -> Placed:
    """Put this gateway under launchd, and start it — because with this plist those are one act.

    The order is the research's, and none of it is optional:

    1. The agent's `logs/` is made, at `0700`, **before** anything is handed over. launchd does
       create the parent of a capture path, but that behaviour is undocumented, and a spawn that
       cannot open `StandardErrorPath` fails with the reason going only to the unified log — which
       is how a correctly-installed gateway turns into a `113`.
    2. The shim and the plist are written, the plist at `0600` and never over a symlink.
    3. The label is **enabled unconditionally**, because the override store outlives every plist and
       this machine is carrying a record for an install that no longer exists.
    4. `bootout --wait`, always — never a bootstrap over a live job.
    5. `bootstrap`, and only if the bootout clearly succeeded. A bootout that answered anything else
       may have left the old definition loaded, and bootstrapping onto that **keeps the old one and
       does not fail**.
    """
    by = supervising or Launchd()
    _only_ours(one)
    _laid_down(one)
    written = _written(one)

    by.allow(one.label)

    gone = by.take_back(one.label)
    if gone.trouble is not None:
        return Placed(CANNOT_TELL, f"the supervisor could not be asked to take back {one.label} "
                                   f"({gone.trouble}) — nothing was placed")
    if gone.code != 0 and gone.code not in ALREADY_GONE:
        return Placed(CANNOT_TELL, _why(f"{one.label} could not be taken back first", gone))

    return _how_it_landed(one, by.place(written))


def remove(one: Job, supervising: Optional[Supervising] = None) -> str:
    """Take this gateway's job away, and the two files behind it. `""` when it is gone.

    **The override is left enabled**, and that is a decision rather than tidying. There is an
    `enable` verb and a `disable` verb and nothing that deletes a record, so an uninstall cannot
    clear the store — what it can do is make sure the entry it leaves behind is inert. Leaving a
    `disabled` record is how the *next* install inherits a decision nobody remembers making, which
    is a live example on the machine this was researched against.

    A bootout answering `3` or `113` is success: it was not there, which is the state asked for.

    **Whether the record was made inert is checked, and `place` is why it looks like it need not be.**
    There, the same call's answer may be thrown away safely, because everything after it goes back to
    the same `launchctl` and will itself report `CANNOT_TELL` or a disabled label if it really
    failed. Here nothing follows it: the plist and the shim come off the disk and the function
    returns. So an `enable` that quietly did not happen would leave exactly the poisoned record this
    docstring says the decision exists to avoid — left by the uninstall itself rather than inherited
    from an older one — and the caller would be told the job was gone.
    """
    by = supervising or Launchd()
    _only_ours(one)

    gone = by.take_back(one.label)
    if gone.trouble is not None:
        return f"the supervisor could not be asked to take back {one.label} ({gone.trouble})"
    if gone.code != 0 and gone.code not in ALREADY_GONE:
        return _why(f"{one.label} could not be taken back", gone)

    inert = by.allow(one.label)
    for one_of_ours in (plist_of(one), shim_of(one)):
        try:
            files.remove_one(one_of_ours)
        except OSError as why:
            return f"{one_of_ours} could not be removed ({why})"

    # Said last, because the files really are gone and the job really was taken back — this is the
    # one thing left that somebody may have to finish by hand, and naming the command is the whole
    # of the answer.
    if inert.trouble is not None:
        return (f"{one.label} was taken back and its files removed, but the supervisor could not be "
                f"asked to make the record of it inert ({inert.trouble}) — a record left disabled "
                f"is one the next install under this name would inherit. Clear it with: "
                f"launchctl enable gui/$(id -u)/{one.label}")
    if inert.code != 0:
        return _why(f"{one.label} was taken back and its files removed, but the record of it could "
                    f"not be made inert — clear it with "
                    f"launchctl enable gui/$(id -u)/{one.label}", inert)
    return ""


def stands(one: Job, supervising: Optional[Supervising] = None) -> Stands:
    """Where this job stands, asked of four places because no one of them answers on its own.

    `launchctl print` returning **113 is ambiguous at least four ways** — proven byte-identical for
    a plist that was never bootstrapped, a label with only a stale override record, a label that
    never existed, and a job launchd installed and then threw away on a spawn failure or a Login
    Items denial. And a *disabled* job prints as a perfectly healthy one: `disabled` is not among
    the property words launchd renders at all.

    So: the bootstrap check, the plist on disk, the override store, and — guarded, and degrading to
    `None` rather than guessing — Background Task Management. `NOT_PLACED` is the only safe "no" and
    needs both of the first two to agree.

    **`112` is never reported as "not running".** Over SSH into a machine nobody has logged into at
    the desktop, every gateway on it would otherwise look absent.
    """
    by = supervising or Launchd()
    _only_ours(one)

    plist = plist_of(one)
    there = plist.is_file()
    disabled = _override_says(by.refusals(), one.label)
    allowed = allowed_by_the_owner(one.label)
    asked = by.asked_about(one.label)

    if asked.trouble is not None:
        return Stands(CANNOT_TELL, disabled, allowed, there,
                      f"the supervisor could not be asked about {one.label} ({asked.trouble})")
    if asked.code in NO_GUI_SESSION:
        return Stands(CANNOT_TELL, disabled, allowed, there,
                      f"there is no login session for this user to ask about {one.label} — this is "
                      "not the same as the gateway not running")
    if asked.code == 0:
        return Stands(PLACED, disabled, allowed, there, _running_something_else(asked, plist)
                      or _but_disabled(disabled))
    if asked.code == NOT_KNOWN and not there:
        # The one safe no: launchd has never heard of it and there is nothing on disk to load.
        return Stands(NOT_PLACED, disabled, allowed, there, "")
    if asked.code == NOT_KNOWN and allowed is False:
        return Stands(CANNOT_TELL, disabled, allowed, there,
                      f"{plist} is on disk and launchd has thrown the job away — this machine's "
                      "background item store says the owner has switched it off, and **no command "
                      "puts it back**: System Settings > General > Login Items & Extensions")
    if asked.code == NOT_KNOWN:
        return Stands(CANNOT_TELL, disabled, allowed, there,
                      f"{plist} is on disk and launchd has no record of it — it was never "
                      f"bootstrapped, or it was thrown away on a failed spawn. Read: "
                      f"log show --last 10m --predicate 'process == \"launchd\"' | grep {one.label}")
    return Stands(CANNOT_TELL, disabled, allowed, there, _why(f"{one.label} could not be read", asked))


def allowed_by_the_owner(label: str, store: Optional[Path] = None) -> Optional[bool]:
    """Whether Background Task Management still allows this job. `None` when it cannot be told.

    This is the one lockout with no way out from a command line: a denial here **removes the service
    from launchd**, `print` then answers 113, `print-disabled` says the label is enabled, and only
    the owner can undo it in System Settings. Detecting it is the difference between saying "not
    installed" and telling somebody the one thing they can do.

    The store is world-readable and is an `NSKeyedArchiver` archive: `$objects` holds the rows, a
    row is a dict with a `disposition`, its `identifier` is a `UID` pointing at a string shaped
    `<n>.<label>`, and bit `0x1` of the disposition is set while the item is on.

    **The format is undocumented and every part of that is guarded.** `None` — cannot tell — is a
    first-class answer here rather than a fallback, because the alternative is telling somebody
    their gateway is switched off on the strength of a bit nobody published.
    """
    where = BTM if store is None else store
    try:
        with open(where, "rb") as reading:
            archive = plistlib.load(reading)
        objects = archive["$objects"]
        for row in objects:
            if not isinstance(row, dict) or "disposition" not in row:
                continue
            named = objects[row["identifier"].data]
            if not isinstance(named, str) or named.split(".", 1)[-1] != label:
                continue
            return bool(int(row["disposition"]) & BTM_ENABLED)
    except Exception:                     # noqa: BLE001 — see the docstring: an undocumented
        # archive read out of a system file this product does not own. Every shape it could
        # have changed into has to answer "cannot tell", and naming the exceptions would be a
        # list that goes stale the first time Apple renames a key.
        return None
    return None


def _only_ours(one: Job) -> None:
    """Refuse a job whose label does not fingerprint to its own root.

    **This is the whole of the fix for the recorded incident.** A second install's uninstall booted
    out the live install's gateway, because a label is a name in the *person's* login domain and
    `RUNDESK_HOME` cannot reach it. Nothing here ever sweeps or prefix-matches the family name; it
    acts on the one full label this root derives, and refuses anything else out loud.
    """
    wanted = label_for(one.name, one.root)
    if one.label != wanted:
        raise Refused(
            f"{one.label} is not this install's label for {one.name} — {one.root} derives {wanted}, "
            "and acting on another install's job is how one uninstall took away another's gateway")


def _laid_down(one: Job) -> None:
    """Make the agent's directory and its `logs/`, the second explicitly `0700`.

    `mkdir`'s mode argument is masked by the umask, so a directory holding what a gateway said —
    every line of its work, and whatever its agent handed it — would land `0755` under an ordinary
    one. Made and then set, rather than trusted to be created right.
    """
    one.at.mkdir(parents=True, exist_ok=True)
    where = standing.logs_at(one.at)
    where.mkdir(parents=True, exist_ok=True)
    os.chmod(where, 0o700)


def _written(one: Job) -> Path:
    """Write the shim and the plist, and hand back where the plist landed."""
    shim = shim_of(one)
    _written_privately(shim, _the_shim(one).encode("utf-8"), 0o700)

    plist = plist_of(one)
    plist.parent.mkdir(parents=True, exist_ok=True)
    _written_privately(plist, plistlib.dumps(document(one)), files.ONLY_MINE)
    return plist


def _written_privately(where: Path, said: bytes, mode: int) -> None:
    """Write one file at exactly `mode`, and never through a symlink.

    **`O_CREAT`'s mode is masked by the umask**, so the mode is asked for again with `fchmod` once
    the descriptor is open — a permissive umask otherwise lands `0664`, and launchd refuses a plist
    that allows group or world writes with error 122.

    `O_NOFOLLOW` because there is no upside to following a link here: agent plists *must be owned
    by the user loading them*, and whether launchd resolves a symlinked one could not be established
    read-only. A real file leaves nobody a question to answer.
    """
    opened = os.open(where, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode)
    try:
        os.fchmod(opened, mode)
        os.write(opened, said)
    finally:
        os.close(opened)


def _the_shim(one: Job) -> str:
    """The named program launchd starts, which hands off to `host` in this install's release.

    `sys.executable` rather than a `#!/usr/bin/env python3`: which interpreter that resolves to
    depends on the PATH of whoever ran the command, and the job's PATH is not that person's.
    `commands.update` settles an install the same way and for the same reason.

    Every value is quoted for the shell, because this is the one place in this product where a
    value somebody typed becomes shell text.
    """
    return _SHIM.format(
        python=shlex.quote(sys.executable),
        hosting=shlex.quote(HOSTING),
        src=shlex.quote(str(one.root / "app" / "src")),
        name=shlex.quote(one.name),
    )


def _the_environment(one: Job) -> Dict[str, str]:
    """What the job is given, since it inherits almost nothing. Every value a `str`."""
    home = Path.home()
    said = {
        "RUNDESK_HOME": one.root,
        "HOME": home,
        "PATH": ":".join([*(str(home / one_of) for one_of in ALSO_ON_PATH),
                          *BREW_AND_LOCAL, *LAUNCHD_PATH]),
        "LANG": LANG,
    }
    # Coerced in one place rather than at each entry: a value that is not a string is dropped by
    # launchd without a word, and the first symptom is a gateway resolving somewhere else.
    return {name: str(value) for name, value in said.items()}


def _how_it_landed(one: Job, landed: programs.Ran) -> Placed:
    """What a `bootstrap` answered, in the words the failure table uses."""
    if landed.trouble is not None:
        return Placed(CANNOT_TELL, f"the supervisor could not be asked to place {one.label} "
                                   f"({landed.trouble})")
    if landed.code == 0:
        return Placed(PLACED, "")
    if landed.code in ALREADY_THERE:
        # It is there, which is what was asked for — and it is there in spite of the `bootout
        # --wait` a moment ago, so what launchd holds may be the definition it already had rather
        # than the one just written. Said out loud instead of counted as an ordinary success.
        return Placed(PLACED, f"{one.label} was already loaded, so launchd may still be running the "
                              "definition it had rather than the one just written")
    if landed.code in NO_GUI_SESSION:
        return Placed(CANNOT_TELL, f"there is no login session for this user to place {one.label} "
                                   "in — a gateway is placed from the desktop, not over SSH")
    if landed.code == GO_AND_READ_THE_LOG:
        return Placed(CANNOT_TELL, f"launchd would not say why it refused {one.label}. Read: "
                                   "log show --last 10m --predicate 'process == \"launchd\" OR "
                                   f"process == \"xpcproxy\"' | grep {one.label}")
    if landed.code == IS_DISABLED:
        return Placed(NOT_PLACED, f"{one.label} is disabled, and was enabled a moment ago — "
                                  "something on this machine is disabling it")
    return Placed(NOT_PLACED, _why(f"{one.label} was not placed", landed))


def _override_says(said: programs.Ran, label: str) -> Optional[bool]:
    """Whether the override store refuses this label. `None` when the store could not be read.

    **Absence from that listing means enabled**, which is why this can answer `False`; what it may
    never do is answer `False` because the question failed.
    """
    if said.trouble is not None or said.code != 0:
        return None
    quoted = f'"{label}"'
    for line in said.out.splitlines():
        if quoted in line:
            return line.rsplit("=>", 1)[-1].strip() == "disabled"
    return False


def _running_something_else(asked: programs.Ran, plist: Path) -> str:
    """Whether launchd is running a plist other than the one on disk. `""` when it is not, or cannot tell.

    launchd keeps the definition it imported, and re-bootstrapping a label from a different path
    **keeps the existing one without failing**. So the path it prints is compared with the path that
    was written, which is the only way that state is ever visible.

    `print`'s output *"is NOT API in any sense at all"*, so a line that is not there is read as
    nothing to say rather than as a mismatch.
    """
    for line in asked.out.splitlines():
        said = line.strip()
        if said.startswith("path = "):
            loaded = said[len("path = "):].strip()
            if loaded and loaded != str(plist):
                return (f"launchd is running {loaded} and this install wrote {plist} — it kept the "
                        "definition it already had, which it does without failing")
            return ""
    return ""


def _but_disabled(disabled: Optional[bool]) -> str:
    """The sentence for a job launchd knows about and will never start."""
    if disabled:
        return ("launchd knows this job and the override store says it is disabled, so it will "
                "never start — `print` shows a disabled job as a perfectly healthy one")
    return ""


def _why(what: str, said: programs.Ran) -> str:
    """One sentence about a `launchctl` that ran and disagreed.

    **The exit code first, and the text second.** launchd's envelopes carry the same number they
    exit with and the words get reworded between releases, so the number is the fact and the text
    is only there for whoever is reading over somebody's shoulder.
    """
    stated = (said.err or said.out).strip().splitlines()
    return f"{what}: launchctl ended {said.code}{' — ' + stated[0] if stated else ''}"
