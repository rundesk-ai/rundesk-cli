"""Where agents meet the lifecycle that shipped before them, in the places no suite owns.

The lifecycle of the command — install, update, removal, the copies — was written and proved before
`data/` held an agent, and every suite that covers it was written then too. The cases here are the
ones that fall between those suites: they are about a command that already existed meeting a
directory that did not, and there is no file either of them belongs in.

Carrying agents on an update lives in `test_update.py`, beside the command that does it, and copies
that hold an agent live in `test_backups.py`. What is left, and what is here, is **removal**.

Nothing here places a launchd job or runs `launchctl`, and nothing reaches the network.

Run directly: `python3 tests/test_seam.py`
"""

import unittest
from pathlib import Path

import support
from rundesk.agents import directory
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.lifecycle import backups, migration


class AnInstallWithAgentsInIt(support.Isolated):
    """A scratch install of the real product, with real agents standing in its data directory."""

    def setUp(self):
        super().setUp()
        support.a_real_tree(paths.app())
        paths.data().mkdir(parents=True, exist_ok=True)
        config.write_fresh(paths.data())
        migration.stamp_without_running(paths.data())
        self.agents = [self.an_agent("alpha"), self.an_agent("beta")]

    def an_agent(self, name: str) -> Path:
        """A real agent, built the way `agents add` builds one."""
        return directory.made(name, "anthropic")

    def uninstall(self, *argv):
        """Removal driven exactly as a person runs it — **nothing is redirected**.

        The search for the command link is left alone for `test_install.py`'s reason: `tree.unlink`
        only removes a link that resolves into *this* install's own `app/`, and this install stands
        under a temporary root, so nothing on a real PATH is ever a candidate. Redirecting it would
        make these cases agree with a bug rather than with the product.
        """
        return support.run(["uninstall", "--confirm", *argv])

    def still_there(self):
        return sorted(one.name for one in self.agents if one.is_dir())


class RemovingAnInstallThatHasAgents(AnInstallWithAgentsInIt):
    """What `uninstall` does today with agents present, and only what it does today.

    Deliberately narrow. Whether a removal should first take away the jobs that host those agents is
    being wired elsewhere, and a case that asserted the finished behaviour here would be a case that
    claims a guarantee nothing has built yet — which is the one thing this product refuses to do.
    """

    def test_a_purge_takes_every_agent_away_with_the_data(self):
        # `data/` is what the owner accumulated, and an agent is the largest thing in it.
        code, _, err = self.uninstall("--purge")
        self.assertEqual(OK, code, err)
        self.assertEqual([], self.still_there())
        self.assertFalse(paths.agents().exists())

    def test_a_purge_leaves_no_records_behind_anywhere_under_the_root(self):
        # Named rather than swept is the rule the removal is written to, and a database keeps two
        # sidecars — so "the agent directory is gone" and "nothing of that agent is left" are two
        # different claims and this is the second one.
        self.uninstall("--purge")
        self.assertEqual([], sorted(paths.home().rglob(directory.RECORDS)))

    def test_a_removal_that_keeps_the_data_keeps_every_agent(self):
        code, out, err = self.uninstall()
        self.assertEqual(OK, code, err)
        self.assertEqual(["alpha", "beta"], self.still_there())
        self.assertIn(str(paths.data()), out)

    def test_nothing_confirming_takes_no_agent(self):
        code, _, err = support.run(["uninstall", "--purge"])
        self.assertEqual(FAILED, code)
        self.assertEqual(["alpha", "beta"], self.still_there())
        self.assertIn("nothing was removed", err)

    def test_a_copy_holding_agents_survives_a_purge(self):
        # A copy is worth nothing if the thing that takes the product away takes the copies too, and
        # now the thing a copy holds is somebody's agents.
        name = backups.save(paths.data(), paths.backups())

        self.uninstall("--purge")

        self.assertEqual([name], backups.kept(paths.backups()))
        self.assertTrue((paths.backups() / name / "agents" / "alpha" / directory.RECORDS).is_file(),
                        "a purge took the agents inside the copies with it")

    def test_a_purge_says_it_took_the_data_and_kept_the_copies(self):
        backups.save(paths.data(), paths.backups())
        _, out, _ = self.uninstall("--purge")
        self.assertIn(f"took   {paths.data()}", out)
        self.assertIn(str(paths.backups()), out)


if __name__ == "__main__":
    unittest.main()
