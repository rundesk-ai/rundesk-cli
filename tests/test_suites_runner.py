"""The runner itself: what it starts first, and what it must never do to a run.

`scripts/suites` is the one piece of this repository that no suite could reach, because it is the
thing that runs the suites. So it went untested — and it had grown a durations file, an ordering and
a fallback, none of which anything would have noticed breaking.

**What is proved here is the ordering's safety, not its speed.** Whether starting the longest suite
first is faster is a measurement, and a measurement does not belong in a suite that has to pass on
somebody else's machine. What belongs here is everything that must stay true whatever the timings
say: that ordering is never a filter, that an unmeasured suite is never assumed quick, and that a
durations file which is missing, corrupt, or left over from an older set of suites cannot change a
result — only an order.

Run directly: `python3 tests/test_suites_runner.py`
"""

import importlib.machinery
import importlib.util
import json
import unittest
from pathlib import Path

import support


def the_runner():
    """`scripts/suites` as a module. It has no `.py`, so it is loaded by path rather than imported."""
    at = support.CHECKOUT / "scripts" / "suites"
    loader = importlib.machinery.SourceFileLoader("suites_under_test", str(at))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


class WhatItStartsFirst(support.Isolated):
    """The order suites are handed to the pool in."""

    def setUp(self):
        super().setUp()
        self.runner = the_runner()
        self.suites = [Path(f"tests/test_{name}.py") for name in ("a", "b", "c")]

    def test_the_slowest_measured_suite_is_started_first(self):
        """The whole point: a long suite starting last runs alone with every other worker idle."""
        order = self.runner._running_order(
            self.suites, {"test_a.py": 1.0, "test_b.py": 90.0, "test_c.py": 9.0})
        self.assertEqual(["test_b.py", "test_c.py", "test_a.py"], [one.name for one in order])

    def test_a_suite_nobody_has_timed_is_started_before_every_suite_that_has_been(self):
        """It may be the new slowest one. Guessing it is quick is the guess that costs something."""
        order = self.runner._running_order(self.suites, {"test_a.py": 90.0, "test_c.py": 9.0})
        self.assertEqual("test_b.py", order[0].name)

    def test_ordering_is_never_a_filter(self):
        """**The property that keeps this from being able to reintroduce an empty run.** A hint that
        drops a suite would drop it from the run, and a run that discovered nothing proves nothing."""
        for described, hint in (("nothing measured", {}),
                                ("one measured", {"test_a.py": 3.0}),
                                ("naming suites that no longer exist", {"test_gone.py": 900.0})):
            with self.subTest(hint=described):
                order = self.runner._running_order(self.suites, hint)
                self.assertEqual(sorted(one.name for one in self.suites),
                                 sorted(one.name for one in order))


class WhatItRemembers(support.Isolated):
    """The durations file — read without ceremony, because nothing about a result rests on it."""

    def setUp(self):
        super().setUp()
        self.runner = the_runner()
        self.runner.REMEMBERED = self.home / "suite-seconds.json"

    def test_what_it_wrote_is_what_it_reads_back(self):
        self.runner._remember({"test_a.py": 12.5})
        self.assertEqual({"test_a.py": 12.5}, self.runner._remembered())

    def test_a_file_that_is_not_there_is_no_measurements_rather_than_a_failure(self):
        """A cold checkout — CI, or a first run here — has none, and must run exactly as before."""
        self.assertFalse(self.runner.REMEMBERED.exists())
        self.assertEqual({}, self.runner._remembered())

    def test_an_unreadable_or_nonsensical_file_is_read_as_no_measurements(self):
        """Corrupt, half-written, or holding something that is not a number: all the same answer.

        Anything else would let a damaged scratch file take down a run it cannot affect the result
        of, which is the opposite of why it is allowed to exist.
        """
        for described, written in (("truncated json", "{ not json"),
                                   ("a value that is not a number", '{"test_a.py": "soon"}'),
                                   ("not an object at all", '["test_a.py"]')):
            with self.subTest(file=described):
                self.runner.REMEMBERED.write_text(written, encoding="utf-8")
                self.assertEqual({}, self.runner._remembered())

    def test_it_does_not_fail_a_run_it_cannot_write_for(self):
        """The timings are for the next run. Losing them is not this run's result."""
        self.runner.REMEMBERED = self.home / "not-a-directory" / "deeper" / "seconds.json"
        (self.home / "not-a-directory").write_text("a file stands where the directory would go")
        self.runner._remember({"test_a.py": 1.0})  # must not raise

    def test_what_it_writes_is_json_a_person_can_read(self):
        self.runner._remember({"test_b.py": 2.0, "test_a.py": 1.0})
        said = self.runner.REMEMBERED.read_text(encoding="utf-8")
        self.assertEqual({"test_a.py": 1.0, "test_b.py": 2.0}, json.loads(said))
        self.assertLess(said.index("test_a.py"), said.index("test_b.py"), "not written in order")


class ARunThatDiscoveredNothing(support.Isolated):
    """The guard this script exists for, proven to be in front of the pool and not behind it."""

    def test_it_fails_rather_than_reporting_a_clean_run_over_no_suites(self):
        runner = the_runner()
        runner.TESTS = self.home / "there-are-no-suites-here"
        self.assertEqual([], runner.found())
        self.assertEqual(1, runner.main([]), "a run that found nothing reported success")


if __name__ == "__main__":
    unittest.main()
