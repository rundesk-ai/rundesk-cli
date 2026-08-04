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

from rundesk import cli, paths  # noqa: E402  — the insert above is what makes these importable


def scrub_and_point(where: Path) -> Callable[[], None]:
    """Take every rundesk location out of the environment, then point the one that is left at `where`.

    In that order, and the order is the point. Setting the variable first and scrubbing second — the
    shape `RUNDESK_HOME=/tmp/x env -u RUNDESK_HOME ...` — sets it and then takes it away, so the
    default under the owner's home wins while the command reports an ordinary success.

    `XDG_CONFIG_HOME` goes too. It is not rundesk's variable, which is exactly why it is dangerous:
    any shell may carry one, an agent's does, and anything deriving a config directory from it would
    quietly follow it out of the scratch root.

    Hands back what puts the environment as it was found.
    """
    taken = {name: os.environ[name] for name in list(os.environ)
             if name.startswith("RUNDESK_") or name == "XDG_CONFIG_HOME"}
    for name in taken:
        del os.environ[name]
    os.environ[paths.HOME_IS] = str(where)

    def restore() -> None:
        os.environ.pop(paths.HOME_IS, None)
        os.environ.update(taken)

    return restore


def run(argv: List[str]) -> Tuple[int, str, str]:
    """Drive the command as somebody typing it would, and hand back what happened.

    Returns `(exit code, stdout, stderr)`. A `SystemExit` — which is how argparse refuses a command
    line — is caught and reported as its code, so a suite can assert that a typo exits differently
    from an operation that is registered and not built.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(argv)
        except SystemExit as ended:
            code = 0 if ended.code is None else int(ended.code)
    return code, out.getvalue(), err.getvalue()


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
