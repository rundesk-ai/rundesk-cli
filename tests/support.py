"""What every suite here needs, in one place: the import path, and a root that is not the owner's.

The build this replaces had no shared helper. Thirty-five of its thirty-six suites carried their own
`sys.path.insert(... "src")` and their own environment dance, which had two consequences worth
avoiding a second time. Moving the source tree meant editing thirty-five files. And because each
suite isolated itself by hand, each isolated a slightly different set of the dozen locations the
product read — so a suite that looked careful still resolved one of them to the live install, and the
failure showed up as a real agent appearing on somebody's machine.

Both are fixed by the same thing: one root, isolated in one place.

Run a suite directly — `python3 tests/test_cli.py`. No runner to install, and nothing here reaches
the network.
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from unittest import mock

#: The checkout, and the one place the source tree is named. Everything imports through here.
CHECKOUT = Path(__file__).resolve().parent.parent

#: The provider adapter every suite that needs a brain runs. A path rather than a name, so a case
#: does not depend on where an install keeps the ones it was given — and **one path**, because six
#: suites had spelled it out and a sample that moved would have moved in six places or in five.
A_STAND_IN = str(CHECKOUT / "tests" / "samples" / "a-stand-in")

if str(CHECKOUT / "src") not in sys.path:
    sys.path.insert(0, str(CHECKOUT / "src"))

from rundesk import cli  # noqa: E402  — the insert above is what makes these importable
from rundesk.agents import directory, records  # noqa: E402
from rundesk.core import paths  # noqa: E402
from rundesk.gateways import job  # noqa: E402
from rundesk.utils import programs  # noqa: E402

#: Where anything a suite starts is sent instead of the internet: port 9 is discard, and nothing is
#: listening on this machine's own. A refused connection rather than a black hole, so a case that
#: reaches for the network fails in milliseconds instead of hanging until somebody's timeout.
NOWHERE = {
    "http_proxy": "http://127.0.0.1:9",
    "https_proxy": "http://127.0.0.1:9",
    "HTTP_PROXY": "http://127.0.0.1:9",
    "HTTPS_PROXY": "http://127.0.0.1:9",
    "ALL_PROXY": "http://127.0.0.1:9",
}

#: Taken out of the environment before `NOWHERE` goes in, so a machine that exempts GitHub from its
#: own proxy does not exempt it from this one.
_CLOSED_OFF = (*NOWHERE, "no_proxy", "NO_PROXY")

#: Variables that are not rundesk's, which is exactly what makes them dangerous: any shell may carry
#: one and an agent's usually does, so a suite that left them alone would pass or fail on whose
#: terminal it ran in.
#:
#: `XDG_CONFIG_HOME` because anything deriving a directory from it would quietly follow it out of the
#: scratch root. `NO_COLOR` and `FORCE_COLOR` because they decide whether output carries escape
#: sequences — a developer who exports `FORCE_COLOR` would otherwise turn every case that asserts on
#: what was printed red, on their machine only.
_NOT_OURS = ("XDG_CONFIG_HOME", "NO_COLOR", "FORCE_COLOR")

#: A migration step that cannot finish, for proving a failure is reported rather than passed over.
#: Here rather than in each suite: two of them needed it and copied it, which is the small form of
#: exactly what this module exists to stop.
A_STEP_THAT_FAILS = """
def carry(data):
    raise RuntimeError("this step could not finish")
"""


def a_real_tree(at: Path, marker: str = "a tree") -> Path:
    """A working copy of this checkout's program, for a case that needs one that really runs.

    Install and update both hand off to the program they just placed — that is the whole point of
    the handoff, since the process doing the placing is running the release being replaced. So a stub
    launcher cannot be used: it would make every case that touches settling pass without the handoff
    ever happening.

    Only the launcher and `src/` are copied, because that is the whole program.
    """
    at.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CHECKOUT / "rundesk", at / "rundesk")
    (at / "rundesk").chmod(0o755)
    if (at / "src").exists():
        shutil.rmtree(at / "src")
    shutil.copytree(CHECKOUT / "src", at / "src", ignore=shutil.ignore_patterns("__pycache__"))
    (at / "README.md").write_text(marker)
    return at


def scrub_and_point(where: Path) -> Callable[[], None]:
    """Take every rundesk location out of the environment, then point the one that is left at `where`.

    In that order, and the order is the point. Setting the variable first and scrubbing second — the
    shape `RUNDESK_HOME=/tmp/x env -u RUNDESK_HOME ...` — sets it and then takes it away, so the
    default under the owner's home wins while the command reports an ordinary success.

    `_NOT_OURS` goes too — variables belonging to nobody in particular, which is exactly what makes
    them dangerous: any shell may carry one and an agent's usually does. Anything deriving a config
    directory from `XDG_CONFIG_HOME` would quietly follow it out of the scratch root, and a developer
    who exports `FORCE_COLOR` would put escape sequences into every line a case asserts on, on their
    machine and nobody else's.

    The network is closed off in the same breath, and for the same reason: **no suite here may leave
    the machine.** A case can drive the product with `asking=` and `fetching=` and still reach GitHub
    through a subprocess it spawned — an install proves the command it placed by running it, and that
    command is a whole rundesk with its own opinion about what to look up. That is not hypothetical:
    it is how `tests/test_install.py` came to spend half its wall clock on GitHub round-trips while
    every case passed. Pointing the proxy variables at a closed port shuts the door for anything a
    case starts, however deep, on a rule that is meant to be absolute.

    Hands back what puts the environment as it was found.
    """
    taken = {name: os.environ[name] for name in list(os.environ)
             if name.startswith("RUNDESK_") or name in _CLOSED_OFF or name in _NOT_OURS}
    for name in taken:
        del os.environ[name]
    os.environ[paths.HOME_IS] = str(where)
    os.environ.update(NOWHERE)

    def restore() -> None:
        os.environ.pop(paths.HOME_IS, None)
        for name in NOWHERE:
            os.environ.pop(name, None)
        os.environ.update(taken)

    return restore


#: How often a wait looks again. Short enough that an ordinary case never notices the granularity,
#: long enough that a case waiting out its whole ceiling is not spinning a core while it does.
LOOKING_AGAIN = 0.02


def waited_until(wanted: Callable[[], bool], patience: float) -> bool:
    """Wait for a condition rather than sleeping a guessed amount. `False` if it never came true.

    **A guessed sleep is wrong in both directions.** Long enough for the slowest machine anybody
    runs this on is a suite that takes minutes to say nothing; short enough to be quick is a case
    that goes red on a loaded laptop for a reason that has nothing to do with the code. Asking is
    both faster and steadier: an ordinary case is through in a couple of hundredths.

    **The ceiling is the caller's**, and it is a real number rather than something to leave out. A
    case that can hang for ever is worse than one that fails, because a run that never ends is a run
    nobody reads — and what is being waited for here is a child process, so how long is too long
    depends entirely on what that child has to do before it can answer.

    Here rather than in each suite: three suites had written this out, with three different
    ceilings, which is how the number stops being a decision and becomes whatever was copied.
    """
    ceiling = time.monotonic() + patience
    while time.monotonic() < ceiling:
        if wanted():
            return True
        time.sleep(LOOKING_AGAIN)
    return False


def not_as_root(case: unittest.TestCase) -> None:
    """Skip this case when it is running as root, because root is refused nothing.

    A case that proves a permission is enforced proves nothing at all as a superuser: an unwritable
    directory is writable, an unreadable one is readable, and the refusal under test never happens.
    Passing there would be worse than skipping, because it would be counted.

    Skipped rather than failed — running a suite as root is a thing somebody may legitimately do,
    and the honest report is that this one could not be answered rather than that it went wrong.
    """
    if os.geteuid() == 0:
        case.skipTest("root is refused nothing, so a permission this case rests on cannot be made")


#: The owner's real login items: **the one location `RUNDESK_HOME` cannot move.** A launchd label
#: is a name in a person's login domain and a plist stands in their home, so pointing the root at a
#: scratch directory isolates everything about an install except this. Read, listed and compared
#: here — never written, and never handed to anything as somewhere to write.
THEIR_LOGIN_ITEMS = Path.home() / "Library" / "LaunchAgents"


def login_items_as_they_stand() -> Optional[List[Tuple[str, int, int]]]:
    """Every entry in the owner's `LaunchAgents`, with enough of each to see a rewrite.

    `None` when it cannot be listed at all, which is a machine that has never had one — told apart
    from an empty list, so a directory appearing during a case is not read as no change.
    """
    try:
        return sorted((one.name, one.stat().st_size, one.stat().st_mtime_ns)
                      for one in THEIR_LOGIN_ITEMS.iterdir())
    except OSError:
        return None


#: What the owner's login items held when this suite process started.
#:
#: **The baseline a case compares against, rather than "there is no rundesk plist anywhere".** That
#: absolute reading was what this asserted, and it made the suite unrunnable for the one workflow
#: this product is developed with: `./dev gateways start <agent>` places a real job, on purpose, in
#: the owner's own login domain — a launchd label belongs to the person and `RUNDESK_HOME` cannot
#: move it. A developer who used the thing they were building could no longer test it.
#:
#: What must be true is that **this run** wrote none, which is a different claim and the one worth
#: making. Read once, at import, so a gateway started by hand before the run is part of the ground
#: rather than part of the evidence.
AS_THE_RUN_BEGAN = login_items_as_they_stand()


def ran(code: Optional[int] = 0, out: str = "", err: str = "",
        trouble: Optional[str] = None) -> programs.Ran:
    """One answer from a supervisor, in the shape `utils.programs` hands back."""
    return programs.Ran(code, out, err, trouble)


#: What a launchd that has never heard of a label answers, which is what a scratch install really
#: is: `print` says 113 — it knows nothing — `bootout` says 3, it was not there to take back, and
#: `kill` says 113, there being no service of that name to signal. Everything else answers `0`,
#: because everything else is a request rather than a question.
AN_EMPTY_MACHINE: Dict[str, programs.Ran] = {
    "print": ran(job.NOT_KNOWN),
    "bootout": ran(3),
    "kill": ran(job.NOT_KNOWN),
}


class ASupervisor:
    """A stand-in for the machine's supervisor: it records what it was asked and answers what a
    case wants.

    Every method hands back `programs.Ran`, which is the whole of the seam: a `launchctl` that ran
    and said `113` and a `launchctl` that was not on the machine are different facts, and a
    stand-in that could not express both would let the commands collapse them.

    Nothing is inherited and nothing is registered — `job.Supervising` is a `Protocol`, so a
    stand-in has nothing in common with the real supervisor but the shape.
    """

    def __init__(self, **answers: programs.Ran) -> None:
        self.asked: List[Tuple[str, str]] = []
        self.answers = dict(AN_EMPTY_MACHINE, **answers)

    def allow(self, label: str) -> programs.Ran:
        return self.answer("enable", label)

    def take_back(self, label: str) -> programs.Ran:
        return self.answer("bootout", label)

    def place(self, plist: Path) -> programs.Ran:
        return self.answer("bootstrap", str(plist))

    def end(self, label: str) -> programs.Ran:
        return self.answer("kill", label)

    def kick(self, label: str) -> programs.Ran:
        return self.answer("kickstart", label)

    def asked_about(self, label: str) -> programs.Ran:
        return self.answer("print", label)

    def refusals(self) -> programs.Ran:
        return self.answer("print-disabled", "")

    def verbs(self) -> List[str]:
        return [verb for verb, _what in self.asked]

    def answer(self, verb: str, what: str) -> programs.Ran:
        """Record what was asked and hand back what this case wants said. Overridden by cases that
        need the world to change while launchd is being talked to — a bootstrap that really starts
        something, for instance."""
        self.asked.append((verb, what))
        return self.answers.get(verb, ran(0))


class NeverTheRealOne:
    """What `job.Launchd` is replaced with while a command runs, so nothing can quietly reach it."""

    def __init__(self, *_args: object, **_kw: object) -> None:
        raise AssertionError(
            "a case reached the real launchctl — every case here drives a stand-in supervisor, "
            "because the real one would answer perfectly well against the owner's own jobs")


#: The real `job.job`, held before anything replaces it.
_A_JOB = job.job


def _in_the_scratch_root(name: str, at: Path, root: Path, into: Optional[Path] = None) -> job.Job:
    """`job.job`, with the plist kept in the scratch root rather than in the owner's login items.

    **The seam `RUNDESK_HOME` cannot be.** `job.job` resolves `into` to `~/Library/LaunchAgents`
    when nobody says otherwise, which is right for the product and catastrophic for a suite: a case
    that ran `gateways start` would write a real plist into what the owner's machine starts at
    login. So the whole of the command is driven with that one answer replaced, and
    `Isolated` then proves the real directory is exactly as it was found.
    """
    return _A_JOB(name, at, root, into if into is not None else paths.home() / "LaunchAgents")


def run_with(argv: List[str], **collaborators) -> Tuple[int, str, str]:
    """Drive the command as somebody typing it would, and hand back what happened.

    Returns `(exit code, stdout, stderr)`. A `SystemExit` — which is how argparse refuses a command
    line — is caught and reported as its code, so a suite can assert that a typo exits differently
    from a command that ran and failed.

    `collaborators` are handed to `cli.main`: `asking=` replaces the lookup of what version is
    published, `fetching=` replaces the download. A case that forgets either of those gets the real
    thing rather than a silent stub — which is the right way round, because the harness has closed
    the network and a test that reached GitHub fails loudly on somebody's laptop.

    **`supervising=` is the exact opposite, and the reversal is the point.** There is no closed port
    for launchd: the real supervisor would answer a case perfectly well, in the owner's own login
    session, booting out jobs that keep real work running — and nothing would go red. So a case
    that does not say gets a stand-in, `job.Launchd` is replaced with something that raises if
    anything constructs it anyway, and every plist a command writes lands in the scratch root. Three
    guards for one hole, because this is the one place a mistake is silent and permanent.
    """
    out, err = io.StringIO(), io.StringIO()
    collaborators.setdefault("supervising", ASupervisor())
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
            mock.patch.object(job, "job", _in_the_scratch_root), \
            mock.patch.object(job, "Launchd", NeverTheRealOne):
        try:
            code = cli.main(argv, **collaborators)
        except SystemExit as ended:
            code = 0 if ended.code is None else int(ended.code)
    return code, out.getvalue(), err.getvalue()


def run(argv: List[str]) -> Tuple[int, str, str]:
    """Drive the command with nothing replaced."""
    return run_with(argv)


class Isolated(unittest.TestCase):
    """A case with a scratch root of its own, proven to be the one the product resolved.

    Every suite here inherits from this. `self.home` is the root; `self.run` drives the command.
    """

    def setUp(self) -> None:
        super().setUp()
        # Registered first so that it runs last: cleanups are unwound in reverse, and this one is
        # the report on everything the case did, including whatever the other cleanups undid.
        self.addCleanup(self.assert_their_login_items_are_untouched, login_items_as_they_stand())
        self.home = Path(tempfile.mkdtemp(prefix="rundesk-home-")).resolve()
        self.addCleanup(shutil.rmtree, str(self.home), ignore_errors=True)
        self.addCleanup(scrub_and_point(self.home))
        self.assert_isolated()

    def assert_their_login_items_are_untouched(self, as_found) -> None:
        """Fail the case if anything in it changed what the owner's machine starts at login.

        **Asserted, not assumed.** `RUNDESK_HOME` moves every location this product reads except
        this one — a launchd label is a name in a person's login domain and a plist stands in their
        home — so it is the one place where a defect in the isolation is invisible until somebody
        notices their real gateway is gone. Every plist a case writes goes to the scratch root; this
        is the proof rather than the intention.
        """
        now = login_items_as_they_stand()
        if now != as_found:
            raise AssertionError(
                f"{THEIR_LOGIN_ITEMS} was changed by this case — it held {as_found} and now "
                f"holds {now}")

    def assert_isolated(self) -> None:
        """Fail before the case runs if the product would resolve anywhere but the scratch root.

        Asserted rather than assumed, and asserted *first*: a case that quietly ran against the live
        install passes just as green as one that did not, and the damage is already done by the time
        anybody reads the result.
        """
        resolved = paths.home()
        if resolved != self.home:
            raise AssertionError(
                f"this case is not isolated: rundesk resolves {resolved}, not {self.home}")
        if Path.home() in resolved.parents and resolved.name == ".rundesk":
            raise AssertionError(f"this case would work on the owner's own install at {resolved}")

    def a_stand_in_told(self, agent: str, **how) -> None:
        """Tell the stand-in adapter what to do, the way an owner's own settings reach one.

        Here rather than in each suite because *how* a setting reaches an adapter is a fact about
        the product — a JSON object in one column — and six copies of it means five that go on
        agreeing with a shape that has changed.
        """
        records.stated(directory.records(agent), {"agent_settings": json.dumps(how)})

    def rundesk(self, *argv: str) -> Tuple[int, str, str]:
        """Drive the command inside this case's scratch root.

        Named for the command rather than `run`, which is the method a runner calls to execute the
        case — overriding that would leave every suite here unrunnable by a mechanism that looks
        nothing like the cause.
        """
        return run(list(argv))
