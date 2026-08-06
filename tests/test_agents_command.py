"""`rundesk agents` — what a person types, and what a person is shown.

Driven through `self.rundesk(...)`, so the real parser and the real dispatch answer every case. A
case that called `cmd_agents` directly would prove the module and not the command: the sub-verb it
registered, the flag it spelled, and the exit code the shell reads are exactly the parts a direct
call skips.

Every assertion is on what somebody sees or on the number a script reads. Nothing here looks at the
agents layer's internals except to break something on purpose, because a test that asserts on a
private shape goes green while the sentence a person reads goes wrong.

Run directly: `python3 tests/test_agents_command.py`
"""

import fcntl
import json
import os
import unittest
from unittest import mock

import support
from rundesk.agents import directory
from rundesk.channels import hosting
from rundesk.channels import kept as channels
from rundesk.core import paths
from rundesk.exits import FAILED, OK, USAGE
from rundesk.schedules import firing, kept
from rundesk.skills import catalogs, grants, library


class Listing(support.Isolated):
    """`rundesk agents`, and the same thing spelled `rundesk agents list`."""

    def test_an_install_with_no_agents_says_so_and_says_what_to_type(self):
        # `as_table` prints nothing at all when there are no rows, headings included — so a listing
        # that leant on it here would print the directory and then stop, and "no agents" would be
        # something the reader had to infer from silence.
        code, out, _ = self.rundesk("agents")
        self.assertEqual(OK, code)
        self.assertIn("no agents yet", out)
        self.assertIn("rundesk agents add <agent> --provider <provider>", out)

    def test_where_they_stand_is_said_even_when_there_are_none(self):
        # "No agents" and "no agents *here*" are different things to learn.
        _, out, _ = self.rundesk("agents")
        self.assertIn(str(paths.agents()), out)

    def test_it_lists_the_agent_and_what_is_behind_it(self):
        self.rundesk("agents", "add", "cole", "--provider", "claude")
        code, out, _ = self.rundesk("agents")
        self.assertEqual(OK, code)
        self.assertIn("AGENT", out)
        self.assertIn("PROVIDER", out)
        self.assertIn("cole", out)
        self.assertIn("claude", out)

    def test_the_bare_verb_and_the_named_one_answer_the_same(self):
        self.rundesk("agents", "add", "cole", "--provider", "claude")
        self.assertEqual(self.rundesk("agents"), self.rundesk("agents", "list"))

    def test_every_agent_is_listed_in_name_order(self):
        for name in ("zoe", "cole", "ada"):
            self.rundesk("agents", "add", name, "--provider", "claude")
        _, out, _ = self.rundesk("agents")
        listed = [line.split()[0] for line in out.splitlines()[2:] if line.strip()]
        self.assertEqual(["ada", "cole", "zoe"], listed)

    def test_records_that_cannot_be_read_are_said_rather_than_left_out(self):
        # Leaving the agent out would say it is not there, which is a different and worse thing to
        # be told: the directory is on the disk and something has to be done about it.
        self.rundesk("agents", "add", "cole", "--provider", "claude")
        directory.records("cole").write_bytes(b"not a database at all")

        code, out, _ = self.rundesk("agents")

        self.assertEqual(OK, code)
        self.assertIn("cole", out)
        self.assertIn("cannot be read", out)

    def test_records_that_went_away_are_told_apart_from_records_that_cannot_be_read(self):
        # The two ways a provider cannot be answered are different situations, and this is the one
        # a case cannot reach by hand: records taken away between the listing and the reading of
        # them. Telling somebody with a corrupt database that their agent is simply missing sends
        # them to make a new one over what survived, so the sentences must not be the same one.
        with mock.patch.object(directory, "known", return_value=["ghost"]):
            code, out, _ = self.rundesk("agents")
        self.assertEqual(OK, code)
        self.assertIn("ghost", out)
        self.assertIn("records are not there", out)

    def test_a_directory_that_is_not_an_agent_is_not_listed_as_one(self):
        # An agent is a directory holding `state.db`. A listing that counted anything else would
        # offer somebody an agent that cannot answer.
        (paths.agents() / "half-made").mkdir(parents=True)
        _, out, _ = self.rundesk("agents")
        self.assertNotIn("half-made", out)


class Adding(support.Isolated):
    """`rundesk agents add <agent> --provider <provider>`."""

    def test_it_makes_an_agent_and_says_what_was_made(self):
        code, out, _ = self.rundesk("agents", "add", "cole", "--provider", "claude")
        self.assertEqual(OK, code)
        self.assertIn("agent cole added", out)
        self.assertIn("claude", out)
        for one in ("home", "logs", "state.db"):
            self.assertIn(one, out, f"the line naming {one} is not there")

    def test_it_is_given_the_skill_it_operates_this_install_with(self):
        # Shipped, undeletable as a catalog, and held by nobody was the state this closes: an agent
        # that cannot operate the install running it answers questions about this machine by
        # guessing, and that reads as a model being unhelpful rather than as a skill nobody granted.
        catalogs.place_bundled()
        code, out, _ = self.rundesk("agents", "add", "cole", "--provider", "claude")
        self.assertEqual(OK, code)
        self.assertIn(library.REQUIRED, out)
        self.assertIsNotNone(grants.holding("cole", library.REQUIRED_SKILL))
        # And where a brain looks, not merely in the agent's own directory.
        self.assertTrue((directory.home("cole") / ".claude" / "skills"
                         / library.REQUIRED_SKILL).is_symlink())

    def test_an_install_with_no_catalog_still_makes_the_agent_and_says_what_gives_it_one(self):
        # The grant is best-effort and may never fail the agent. An install whose catalogs have not
        # been placed yet has no such skill to grant, and refusing to make an agent over that would
        # be refusing the thing that always works because of the thing that sometimes does not.
        code, out, _ = self.rundesk("agents", "add", "cole", "--provider", "claude")
        self.assertEqual(OK, code)
        self.assertIn("agent cole added", out)
        self.assertTrue(directory.records("cole").is_file())
        self.assertIn("rundesk update", out)

    def test_what_was_made_is_really_there_afterwards(self):
        self.rundesk("agents", "add", "cole", "--provider", "claude")
        self.assertTrue(directory.records("cole").is_file())
        self.assertTrue(directory.home("cole").is_dir())
        self.assertTrue(directory.logs("cole").is_dir())

    def test_it_says_out_loud_that_the_provider_is_not_proven(self):
        # **Adding an agent checks nothing about its brain**, and it must not look as though it
        # did. Nothing here runs the adapter, asks it what it can do, or finds out whether anybody
        # is signed in — an agent added with a provider nobody has ever spelled correctly looks
        # exactly like one that works. Now that a turn *can* run, the sentence has to send somebody
        # to the verb that would actually tell them.
        _, out, _ = self.rundesk("agents", "add", "cole", "--provider", "claude")
        self.assertIn("recorded and not proven", out)
        self.assertIn("rundesk providers check", out)

    def test_a_name_no_launchd_label_can_carry_is_warned_about_where_it_is_chosen(self):
        # `agents` allows any name a directory may have; a launchd label is narrower. Such an agent
        # is one no job can ever be placed for — nothing starts its gateway at login and nothing
        # brings it back when it stops. Said here, at the moment the name is picked and while adding
        # it again under another is free, rather than weeks later when somebody wonders why it never
        # came back. The gateway can still be run and stopped by hand, so the note says how.
        _, out, _ = self.rundesk("agents", "add", "my agent", "--provider", "claude")
        self.assertIn("no job can ever be placed for it", out)
        self.assertIn("rundesk gateways run", out)
        self.assertIn("rundesk gateways stop", out)

    def test_an_ordinary_name_is_not_warned_about(self):
        # The note has to stay rare to stay read. A name launchd is perfectly happy with must not
        # carry a warning about supervision it is going to get.
        _, out, _ = self.rundesk("agents", "add", "cole", "--provider", "claude")
        self.assertNotIn("no job can ever be placed", out)

    def test_a_provider_is_required_and_the_refusal_says_what_to_type(self):
        code, out, err = self.rundesk("agents", "add", "cole")
        self.assertEqual(FAILED, code)
        self.assertEqual("", out, "a refusal on stdout is a failure a script reads as the answer")
        self.assertIn("nothing said which provider", err)
        self.assertIn("rundesk agents add cole --provider <provider>", err)
        self.assertIn("nothing was made", err)

    def test_nothing_is_made_when_no_provider_was_given(self):
        self.rundesk("agents", "add", "cole")
        self.assertNotIn("cole", directory.known())

    def test_a_provider_with_nothing_in_it_is_refused(self):
        # Usually a shell variable that was not set, which is the case where being told to type the
        # flag again does not help — so it gets its own sentence.
        code, _, err = self.rundesk("agents", "add", "cole", "--provider", "  ")
        self.assertEqual(FAILED, code)
        self.assertIn("an agent with nothing behind it cannot answer", err)
        self.assertNotIn("cole", directory.known())

    def test_a_name_already_taken_is_refused_and_the_refusal_names_the_one_there(self):
        self.rundesk("agents", "add", "cole", "--provider", "claude")
        code, _, err = self.rundesk("agents", "add", "cole", "--provider", "openai")
        self.assertEqual(FAILED, code)
        self.assertIn("cole is already an agent", err)
        self.assertIn("nothing was made", err)

    def test_a_name_already_taken_leaves_the_agent_that_is_there_alone(self):
        self.rundesk("agents", "add", "cole", "--provider", "claude")
        self.rundesk("agents", "add", "cole", "--provider", "openai")
        _, out, _ = self.rundesk("agents")
        self.assertIn("claude", out)
        self.assertNotIn("openai", out)

    def test_a_name_that_could_never_be_a_directory_is_refused(self):
        code, _, err = self.rundesk("agents", "add", "a/b", "--provider", "claude")
        self.assertEqual(FAILED, code)
        self.assertIn("nothing was made", err)

    def test_it_needs_a_name(self):
        code, _, _ = self.rundesk("agents", "add", "--provider", "claude")
        self.assertEqual(USAGE, code)


class Configuring(support.Isolated):
    """`rundesk agents configure <agent> --provider <provider>`."""

    def setUp(self):
        super().setUp()
        self.rundesk("agents", "add", "cole", "--provider", "claude")

    def test_it_changes_what_is_behind_an_agent(self):
        code, out, _ = self.rundesk("agents", "configure", "cole", "--provider", "openai")
        self.assertEqual(OK, code)
        self.assertIn("cole: provider is now openai", out)

    def test_the_change_is_what_the_listing_shows_afterwards(self):
        self.rundesk("agents", "configure", "cole", "--provider", "openai")
        _, out, _ = self.rundesk("agents")
        self.assertIn("openai", out)
        self.assertNotIn("claude", out)

    def test_it_says_out_loud_that_the_provider_is_not_proven(self):
        _, out, _ = self.rundesk("agents", "configure", "cole", "--provider", "openai")
        self.assertIn("recorded and not proven", out)

    def test_naming_nothing_to_change_is_refused_rather_than_called_a_success(self):
        # A command that reports success having changed nothing teaches somebody that it worked,
        # and the next thing they do rests on a change that never happened. `configure` one layer
        # up makes the same decision for the same reason.
        code, out, err = self.rundesk("agents", "configure", "cole")
        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("nothing was named to change about cole", err)
        self.assertIn("rundesk agents configure cole --provider <provider>", err)
        self.assertIn("nothing was changed", err)

    def test_an_agent_that_is_not_there_is_refused(self):
        code, _, err = self.rundesk("agents", "configure", "nobody", "--provider", "openai")
        self.assertEqual(FAILED, code)
        self.assertIn("nobody is not an agent on this install", err)
        self.assertIn("nothing was changed", err)

    def test_a_directory_that_is_not_an_agent_is_not_configurable(self):
        (paths.agents() / "half-made").mkdir(parents=True)
        code, _, err = self.rundesk("agents", "configure", "half-made", "--provider", "openai")
        self.assertEqual(FAILED, code)
        self.assertIn("is not an agent on this install", err)

    def test_a_provider_with_nothing_in_it_is_refused(self):
        code, _, err = self.rundesk("agents", "configure", "cole", "--provider", "")
        self.assertEqual(FAILED, code)
        self.assertIn("an agent with nothing behind it cannot answer", err)
        _, out, _ = self.rundesk("agents")
        self.assertIn("claude", out, "the agent was changed by a refusal")


class Removing(support.Isolated):
    """`rundesk agents remove <agent> --confirm`."""

    def setUp(self):
        super().setUp()
        self.rundesk("agents", "add", "cole", "--provider", "claude")

    def test_it_takes_the_agent_away_and_says_what_it_took(self):
        code, out, _ = self.rundesk("agents", "remove", "cole", "--confirm")
        self.assertEqual(OK, code)
        self.assertIn("agent cole removed", out)
        self.assertIn("state.db", out)
        self.assertIn("home", out)
        self.assertIn("logs", out)

    def test_what_it_says_it_took_is_really_gone(self):
        self.rundesk("agents", "remove", "cole", "--confirm")
        self.assertFalse((paths.agents() / "cole").exists())
        self.assertEqual([], directory.known())

    def test_without_confirming_it_says_what_it_would_take_and_takes_none_of_it(self):
        code, out, err = self.rundesk("agents", "remove", "cole")
        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("this would take the agent cole", err)
        self.assertIn("nothing was removed. To go ahead:", err)
        self.assertIn("rundesk agents remove cole --confirm", err)

    def a_schedule_that_is_running(self, name="slow"):
        """A real `flock` on a schedule's lock, taken by this case the way a firing takes it.

        The kernel is what the guard asks, so a stand-in would prove nothing. Taken on a descriptor
        of the case's own, and let go by a cleanup registered the moment it is held.
        """
        kept.added("cole", name, {"cron": "0 2 * * *", "command": "/bin/echo hi"})
        at = firing.lock_of("cole", name)
        at.parent.mkdir(parents=True, exist_ok=True)
        held = os.open(at, os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, held)
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return name

    def test_it_refuses_while_a_schedule_of_that_agents_is_still_running(self):
        # **A schedule run by hand holds only its own lock, never `gateway.lock`** — so an agent with
        # no gateway anywhere reads as free to the gateway check and can still have a program
        # running. Removing it here unlinks `schedules/` including that held lock, which hands the
        # name away: a later agent and schedule of the same names then claim a *fresh* inode and lock
        # that, while the original child still holds the old one. Two firings of one schedule,
        # running at once, which is the one thing the whole locking design exists to prevent.
        self.a_schedule_that_is_running()

        code, _out, err = self.rundesk("agents", "remove", "cole", "--confirm")

        self.assertEqual(FAILED, code)
        self.assertIn("has work still running: slow", err)
        self.assertIn("nothing was removed", err)
        self.assertTrue((paths.agents() / "cole").is_dir(), "the agent was taken away anyway")

    def a_channel_that_is_connected(self, kind="discord"):
        """A real `flock` on a channel's lock, taken the way an adapter takes it: and held.

        The kernel is what the guard asks, so a stand-in would prove nothing — and an adapter's
        claim really is a descriptor somebody is holding, which is why it survives the gateway that
        started it. Let go by a cleanup registered the moment it is held.
        """
        channels.added("cole", kind, {"describes": kind, "allowed": json.dumps(["2207"]),
                                      "settings": "{}"})
        at = hosting.lock_of("cole", kind)
        at.parent.mkdir(parents=True, exist_ok=True)
        held = os.open(at, os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, held)
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return kind

    def test_it_refuses_while_an_adapter_of_that_agents_is_still_connected(self):
        # **The third way an agent can have a program running.** An adapter holds its channel's own
        # lock and never `gateway.lock`, and one adopted from a gateway that is gone outlives every
        # gateway there has been — so an agent that reads as free to both checks above can still be
        # connected to a platform. Removing it here unlinks `channels/` including that held lock,
        # which hands the name away: a later agent and channel of the same names then claim a fresh
        # inode and lock that, while the original adapter goes on answering as this agent.
        #
        # Watched go the other way round with the check taken out: the removal exits `0`, names
        # every path it took, and the lock somebody is still holding is one of them.
        self.a_channel_that_is_connected()

        code, _out, err = self.rundesk("agents", "remove", "cole", "--confirm")

        self.assertEqual(FAILED, code)
        self.assertIn("is still connected: discord", err)
        self.assertIn("nothing was removed", err)
        self.assertTrue((paths.agents() / "cole").is_dir(), "the agent was taken away anyway")
        self.assertTrue(hosting.lock_of("cole", "discord").exists(),
                        "the lock an adapter was holding was unlinked, which hands the name away")

    def test_a_channel_nobody_can_ask_about_is_refused_rather_than_read_as_free(self):
        # The third answer, kept as a third answer. `hosting.still_running` re-raises anything that
        # is not ordinary contention — a permission problem, a filesystem that will not lock — and
        # reading that as "nothing is connected" is how a live adapter gets orphaned by a removal.
        channels.added("cole", "discord", {"describes": "discord",
                                           "allowed": json.dumps(["2207"]), "settings": "{}"})
        hosting.at("cole", "discord").mkdir(parents=True, exist_ok=True)

        with mock.patch.object(hosting, "still_running",
                               side_effect=OSError("this filesystem will not lock")):
            code, _out, err = self.rundesk("agents", "remove", "cole", "--confirm")

        self.assertEqual(FAILED, code)
        self.assertIn("nobody can tell whether cole is still connected", err)
        self.assertIn("this filesystem will not lock", err)
        self.assertTrue((paths.agents() / "cole").is_dir(), "the agent was taken away anyway")

    def test_it_goes_ahead_once_nothing_is_connected(self):
        # The refusal is about an adapter that is running and not about having channels at all: a
        # channel whose adapter is not hosted is a row and a directory, and neither holds anything.
        channels.added("cole", "discord", {"describes": "discord",
                                           "allowed": json.dumps(["2207"]), "settings": "{}"})
        code, _out, err = self.rundesk("agents", "remove", "cole", "--confirm")
        self.assertEqual(OK, code, err)

    def test_what_it_would_take_names_the_channels_directory(self):
        # Everything that ever arrived through a channel is inside it, and `forgotten` really takes
        # it — so a preview that left it out would describe a smaller removal than the one about to
        # happen, which is the one thing that list exists not to do.
        channels.added("cole", "discord", {"describes": "discord",
                                           "allowed": json.dumps(["2207"]), "settings": "{}"})
        # What a channel that has been hosted leaves standing: the row is in the records and the
        # directory is on disk, and it is the directory this removal takes.
        hosting.at("cole", "discord").mkdir(parents=True, exist_ok=True)

        _code, _out, err = self.rundesk("agents", "remove", "cole")

        self.assertIn(str(directory.where("cole") / directory.CHANNELS), err)
        self.assertIn("what arrived through each", err)

    def test_it_goes_ahead_once_that_work_has_finished(self):
        # The refusal is about work in flight and not about having schedules at all.
        kept.added("cole", "nightly", {"cron": "0 2 * * *", "command": "/bin/echo hi"})
        code, _out, err = self.rundesk("agents", "remove", "cole", "--confirm")
        self.assertEqual(OK, code, err)

    def test_what_it_would_take_names_the_schedules_directory(self):
        # The preview is what somebody checks before agreeing, so a removal that takes `schedules/`
        # and does not say so describes a smaller removal than the one about to happen.
        kept.added("cole", "nightly", {"cron": "0 2 * * *", "command": "/bin/echo hi"})
        _code, _out, err = self.rundesk("agents", "remove", "cole")
        self.assertIn("schedules", err)
        self.assertIn("1 schedule(s)", err)

    def test_a_removal_that_did_not_happen_is_reported_as_a_failure(self):
        # The whole point of the flag. Exiting 0 here would tell a script the agent was gone.
        code, _, _ = self.rundesk("agents", "remove", "cole")
        self.assertEqual(FAILED, code)
        self.assertTrue(directory.records("cole").is_file())
        self.assertIn("cole", directory.known())

    def test_what_it_would_take_is_named_one_thing_at_a_time(self):
        _, _, err = self.rundesk("agents", "remove", "cole")
        for one in ("state.db", "home", "logs"):
            self.assertIn(one, err, f"the line naming {one} is not there")

    def test_an_agent_that_is_not_there_is_refused_before_the_confirmation_is_asked_for(self):
        # Somebody who mistyped the name finds out now rather than after typing `--confirm`.
        code, _, err = self.rundesk("agents", "remove", "nobodie")
        self.assertEqual(FAILED, code)
        self.assertIn("nobodie is not an agent on this install", err)
        self.assertNotIn("--confirm", err)

    def test_an_agent_that_is_not_there_is_refused_with_the_confirmation_too(self):
        code, _, err = self.rundesk("agents", "remove", "nobody", "--confirm")
        self.assertEqual(FAILED, code)
        self.assertIn("nobody is not an agent on this install", err)
        self.assertIn("nothing was removed", err)

    def test_what_the_owner_left_in_there_is_kept_and_said(self):
        # Taking an agent away is not a licence to sweep, and a directory that survives has to be
        # reported — otherwise "removed" is a word the disk disagrees with.
        (paths.agents() / "cole" / "notes.md").write_text("mine", encoding="utf-8")
        code, out, _ = self.rundesk("agents", "remove", "cole", "--confirm")
        self.assertEqual(OK, code)
        self.assertIn("something you put in there is still there", out)
        self.assertTrue((paths.agents() / "cole" / "notes.md").is_file())

    def test_it_needs_a_name(self):
        code, _, _ = self.rundesk("agents", "remove", "--confirm")
        self.assertEqual(USAGE, code)


class OnTheParser(support.Isolated):
    """The verb as the command line sees it."""

    def test_a_sub_verb_named_wrongly_is_a_usage_error(self):
        code, _, _ = self.rundesk("agents", "ad")
        self.assertEqual(USAGE, code)

    def test_a_flag_it_does_not_have_is_a_usage_error(self):
        code, _, _ = self.rundesk("agents", "add", "cole", "--model", "big")
        self.assertEqual(USAGE, code)

    def test_a_root_that_must_not_be_used_is_refused_rather_than_worked_on(self):
        import os
        os.environ["RUNDESK_HOME"] = "/"
        code, out, err = self.rundesk("agents")
        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("root of the filesystem", err)


class InTheStatus(support.Isolated):
    """The row `status` grew, and the rows it must not have disturbed."""

    def test_it_says_where_the_agents_stand(self):
        _, out, _ = self.rundesk("status")
        self.assertIn(str(paths.agents()), out)

    def test_an_install_with_no_agents_says_none_yet_rather_than_nothing(self):
        self.rundesk("agents", "add", "cole", "--provider", "claude")
        self.rundesk("agents", "remove", "cole", "--confirm")
        _, out, _ = self.rundesk("status")
        self.assertIn("none yet", self._row(out))

    def test_a_root_nothing_stands_in_is_told_apart_from_one_with_no_agents(self):
        _, out, _ = self.rundesk("status")
        self.assertIn("not there yet", self._row(out))

    def test_it_says_how_many_there_are(self):
        self.rundesk("agents", "add", "cole", "--provider", "claude")
        self.assertIn("1 agent", self._row(self.rundesk("status")[1]))
        self.rundesk("agents", "add", "ada", "--provider", "claude")
        self.assertIn("2 agents", self._row(self.rundesk("status")[1]))

    def test_the_rows_that_were_there_still_answer_against_this_root(self):
        # `tests/test_cli.py` rests on these three, and a new row must not have moved them.
        _, out, _ = self.rundesk("status")
        seen = [line for line in out.splitlines() if line.startswith(("home", "data", "backups"))]
        self.assertEqual(3, len(seen), "status lost one of the rows it had")
        for line in seen:
            self.assertIn(str(self.home), line)

    def _row(self, out):
        """The `agents` row of a `status` table, whatever else moved around it."""
        for line in out.splitlines():
            if line.startswith("agents"):
                return line
        raise AssertionError(f"status has no agents row:\n{out}")


if __name__ == "__main__":
    unittest.main()
