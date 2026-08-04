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
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Callable, List, Tuple

#: The checkout, and the one place the source tree is named. Everything imports through here.
CHECKOUT = Path(__file__).resolve().parent.parent

if str(CHECKOUT / "src") not in sys.path:
    sys.path.insert(0, str(CHECKOUT / "src"))

from rundesk import cli  # noqa: E402  — the insert above is what makes these importable
from rundesk.core import paths  # noqa: E402

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

    `XDG_CONFIG_HOME` goes too. It is not rundesk's variable, which is exactly why it is dangerous:
    any shell may carry one, an agent's does, and anything deriving a config directory from it would
    quietly follow it out of the scratch root.

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
             if name.startswith("RUNDESK_") or name in _CLOSED_OFF or name == "XDG_CONFIG_HOME"}
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


def run_with(argv: List[str], **collaborators) -> Tuple[int, str, str]:
    """Drive the command as somebody typing it would, and hand back what happened.

    Returns `(exit code, stdout, stderr)`. A `SystemExit` — which is how argparse refuses a command
    line — is caught and reported as its code, so a suite can assert that a typo exits differently
    from a command that ran and failed.

    `collaborators` are handed to `cli.main`: `asking=` replaces the lookup of what version is
    published, `fetching=` replaces the download. Nothing here reaches the network, and a case that
    forgets to pass one gets the real thing rather than a silent stub — which is the right way round,
    because a test that accidentally reaches GitHub fails loudly on somebody's laptop.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
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
        self.home = Path(tempfile.mkdtemp(prefix="rundesk-home-")).resolve()
        self.addCleanup(shutil.rmtree, str(self.home), ignore_errors=True)
        self.addCleanup(scrub_and_point(self.home))
        self.assert_isolated()

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

    def rundesk(self, *argv: str) -> Tuple[int, str, str]:
        """Drive the command inside this case's scratch root.

        Named for the command rather than `run`, which is the method a runner calls to execute the
        case — overriding that would leave every suite here unrunnable by a mechanism that looks
        nothing like the cause.
        """
        return run(list(argv))
