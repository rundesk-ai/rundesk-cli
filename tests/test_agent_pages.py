"""The files an agent lives by, and how they get into its home.

Every case here is about one of two promises: that a new agent really has its rules, and that a
release never rewrites the ones it has. The second is the one worth breaking the code over — an
owner's edited `AGENTS.md` quietly replaced by an update is a change of behaviour nobody is told
about, and it would look exactly like the model having a bad day.

Run directly: `python3 tests/test_agent_pages.py`
"""

import shutil
import unittest
from unittest import mock

import support
from rundesk.agents import directory, pages
from rundesk.core import paths


def a_release_with_no_pages() -> None:
    """Leave this case's install shipping no `templates/` at all — a broken checkout, or one cut
    short partway through installing.

    Done by making `app/src` really exist and be empty, which is how `paths.code()` comes to answer
    the install rather than the checkout it was run from. **Never by replacing `pages.shipped`**:
    what these cases are about is the files not being there, and a stubbed resolver would prove
    only that the stub was called.

    Nothing to undo — the scratch root goes with the case.
    """
    (paths.home() / "app" / "src").mkdir(parents=True, exist_ok=True)


class WhatIsShipped(support.Isolated):
    """The release's own pages, read out of the tree this is running from."""

    def test_there_is_something_to_place(self):
        # A check that finds its own work fails when it finds none: pointed at a directory that had
        # moved, every case below would pass having placed nothing.
        self.assertTrue(pages.shipped().is_dir(), f"nothing ships at {pages.shipped()}")
        self.assertTrue(pages.PAGES)

    def test_every_page_comes_from_a_file_that_is_really_there(self):
        said = pages.read_shipped()
        for name, source in pages.PAGES.items():
            with self.subTest(name=name):
                self.assertTrue(said[source].strip(), f"{source} is empty, and {name} comes from it")

    def test_the_rules_are_one_file_placed_twice(self):
        """Two files kept in step by anybody remembering is two files that disagree, and each brain
        reads only the one it looks for — so the drift would be two agents wearing one name."""
        self.assertEqual(pages.PAGES["AGENTS.md"], pages.PAGES["CLAUDE.md"])

    def test_where_it_looks_is_answered_every_time_and_never_bound_at_import(self):
        """On a machine with a real install `~/.rundesk/app/src` exists, so a constant resolved at
        import would answer out of the owner's live install before any case set `RUNDESK_HOME`."""
        self.assertEqual(paths.code() / pages.SHIPPED_IN, pages.shipped())


class ANewAgent(support.Isolated):
    """What `rundesk agents add` really leaves in a home."""

    def setUp(self):
        super().setUp()
        directory.made("ava", "a-stand-in")
        self.home = directory.home("ava")

    def test_it_has_every_page(self):
        self.assertEqual([], pages.wanted(self.home))
        for name in pages.PAGES:
            with self.subTest(name=name):
                self.assertTrue((self.home / name).is_file())

    def test_it_starts_with_named_places_for_durable_work(self):
        self.assertEqual(
            {"plans", "research", "scripts", "retros"},
            {one.name for one in self.home.iterdir() if one.is_dir()},
        )
        for area in pages.AREAS:
            with self.subTest(area=area):
                self.assertTrue((self.home / area / "README.md").is_file())

    def test_each_work_area_explains_use_maintenance_and_safety(self):
        for area in pages.AREAS:
            with self.subTest(area=area):
                note = (self.home / area / "README.md").read_text(encoding="utf-8").lower()
                self.assertIn(area, note)
                self.assertIn("keep", note)
                self.assertTrue(
                    any(word in note for word in ("remove", "revise", "update", "retire")),
                    f"{area} does not explain how its contents stay maintained",
                )
                self.assertTrue(
                    any(word in note for word in ("project", "secret", "evidence", "owner")),
                    f"{area} does not name a safety boundary",
                )

    def test_the_rules_it_got_are_byte_identical_under_both_names(self):
        self.assertEqual((self.home / "AGENTS.md").read_bytes(),
                         (self.home / "CLAUDE.md").read_bytes())

    def test_the_pages_say_what_they_are(self):
        rules = (self.home / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("MEMORY.md", rules)
        self.assertIn("# MEMORY", (self.home / "MEMORY.md").read_text(encoding="utf-8"))

    def test_the_rules_distinguish_named_agents_from_same_turn_subagents(self):
        rules = (self.home / "AGENTS.md").read_text(encoding="utf-8").lower()
        for phrase in ("named rundesk agent", "asynchronously", "provider-local subagent",
                       "same turn", "verify", "parent task done"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rules)
        self.assertIn("`asked say` guides working work", rules)
        self.assertIn("steers its active turn", rules)
        self.assertIn("falls back to its next turn", rules)
        self.assertIn("`asked resume` continues answered work", rules)
        self.assertIn("continue independent useful work", rules)
        self.assertIn("result reaches this turn", rules)
        self.assertIn("wakes a review turn", rules)
        self.assertIn("request's done criteria pass", rules)

    def test_the_rules_do_not_claim_the_two_rule_files_synchronize_after_placement(self):
        rules = (self.home / "AGENTS.md").read_text(encoding="utf-8")
        self.assertNotIn("editing one means editing both", rules)
        self.assertNotIn("CLAUDE.md", rules)

    def test_the_standing_rules_have_a_context_budget(self):
        rules = (self.home / "AGENTS.md").read_bytes()
        self.assertLessEqual(len(rules), 4500)

    def test_the_complete_standing_context_has_a_budget(self):
        total = sum(len((self.home / name).read_bytes()) for name in ("AGENTS.md", "MEMORY.md"))
        self.assertLessEqual(total, 4800)

    def test_the_rules_defer_question_policy_to_the_turn_situation(self):
        rules = (self.home / "AGENTS.md").read_text(encoding="utf-8")
        self.assertNotIn("Ask about goals", rules)
        self.assertIn("situation rules", rules)

    def test_start_still_orients_routes_skills_context_and_existing_work(self):
        rules = " ".join((self.home / "AGENTS.md").read_text(encoding="utf-8").split())
        for phrase in ("## Start", "requested outcome, limits, and proof of completion",
                       "Review the available skills", "description covers the work",
                       "Search recorded messages", "context you do not have",
                       "Inspect existing files, commands, and tools",
                       "Do setup silently unless it blocks you"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rules)

    def test_finish_does_not_leave_a_task_process_behind(self):
        rules = (self.home / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("temporary process", rules)

    def test_finish_validates_after_the_last_change_and_keeps_active_handoffs_pending(self):
        rules = " ".join((self.home / "AGENTS.md").read_text(encoding="utf-8").split())
        for phrase in ("After final changes and cleanup", "validate each deliverable yourself",
                       "named delegated work is still active", "task is explicitly pending",
                       "Never call pending work complete"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rules)

    def test_finish_is_short_and_readable_on_a_phone_or_discord(self):
        rules = " ".join((self.home / "AGENTS.md").read_text(encoding="utf-8").lower().split())
        for phrase in ("summary first", "concise on phones/discord", "short bullets",
                       "no markdown tables", "purpose/proof"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rules)

    def test_native_rules_do_not_tell_the_brain_to_open_themselves_again(self):
        rules = (self.home / "AGENTS.md").read_text(encoding="utf-8")
        self.assertNotIn("Read this", rules)
        self.assertIn("Read `MEMORY.md` before your first reply", rules)

    def test_memory_keeps_a_project_index_without_becoming_a_project_log(self):
        rules = " ".join((self.home / "AGENTS.md").read_text(encoding="utf-8").split())
        for phrase in ("durable context useful next run", "active-project pointers",
                       "owner preferences", "role and responsibilities", "cross-project process",
                       "name, stable location, purpose, role, authoritative overview",
                       "Project commands, deliverable paths, status, decisions, conventions",
                       "task methods/checks/done criteria",
                       "working paths, report formats, dates, and supersession/retirement history",
                       "stay in the project or a shared index",
                       "one shared purpose-named index", "never one note per project",
                       "Keep only current facts", "never narrate or date a correction",
                       "Merge, do not append", "superseded fact or closed loop",
                       "If nothing durable changed, do not edit"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rules)

    def test_ordinary_work_pays_only_for_current_task_hygiene(self):
        rules = " ".join((self.home / "AGENTS.md").read_text(encoding="utf-8").split())
        for phrase in ("## Workspace", "canonical files", "project state in its project",
                       "disposable work temporary",
                       "Delete each task-created temporary file and directory before ending, wherever it is",
                       "Preserve deliverables", "pre-existing or uncertain files",
                       "files of uncertain ownership/value",
                       "Do not inspect unrelated home files or inventory, reorganize, or prune home unless maintenance is the task"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rules)
        self.assertNotIn("Inspect home loose files and scratch contents", rules)

    def test_the_memory_scaffold_is_a_small_adaptable_index_not_a_log(self):
        raw = (self.home / "MEMORY.md").read_text(encoding="utf-8")
        memory = " ".join(raw.split())
        for heading in ("## Owner", "## Role and responsibilities", "## Response preferences",
                        "## Cross-project process and gotchas", "## Active project pointers",
                        "## Open loops"):
            with self.subTest(heading=heading):
                self.assertIn(heading, memory)
        self.assertIn("canonical purpose-named home indexes", memory)
        self.assertIn("read and prune when relevant", memory)
        self.assertIn("Adapt headings to your role", memory)
        self.assertLessEqual(len(raw.encode("utf-8")), 400)

    def test_nothing_is_left_staged_beside_them(self):
        """Each is written aside and renamed, because a brain may be reading the directory while an
        update fills one in — and a half-written `AGENTS.md` reads as a complete smaller one."""
        left = [one.name for one in self.home.iterdir() if one.name.startswith(".")
                and one.name.endswith(".incoming")]
        self.assertEqual([], left)


class WhatIsNeverReplaced(support.Isolated):
    """The promise an owner's own editing rests on."""

    def setUp(self):
        super().setUp()
        directory.made("ava", "a-stand-in")
        self.home = directory.home("ava")

    def test_a_page_that_is_there_is_left_exactly_as_it_is(self):
        (self.home / "AGENTS.md").write_text("what the owner wrote", encoding="utf-8")
        self.assertEqual([], pages.place(self.home, "ava"))
        self.assertEqual("what the owner wrote",
                         (self.home / "AGENTS.md").read_text(encoding="utf-8"))

    def test_an_empty_page_is_still_an_answer(self):
        """Somebody who emptied their rules on purpose meant it. Absent and empty are different."""
        (self.home / "MEMORY.md").write_text("", encoding="utf-8")
        pages.place(self.home, "ava")
        self.assertEqual("", (self.home / "MEMORY.md").read_text(encoding="utf-8"))

    def test_an_unreadable_page_is_not_a_missing_one(self):
        """A file nobody can read is still standing there, and writing over it because it could not
        be read is the failure this product refuses everywhere else."""
        page = self.home / "AGENTS.md"
        page.chmod(0o000)
        self.addCleanup(page.chmod, 0o644)
        self.assertNotIn("AGENTS.md", pages.wanted(self.home))
        self.assertEqual([], pages.place(self.home, "ava"))

    def test_a_link_the_owner_made_is_left_alone_even_when_it_points_at_nothing(self):
        """An owner who linked their rules at a file they keep elsewhere has said where those rules
        live. Judged by following the link, an unmounted volume makes it read as missing — and the
        sweep would land a regular file on top of it, losing the link permanently, because that is
        what every run afterwards would find standing there."""
        page = self.home / "AGENTS.md"
        page.unlink()
        page.symlink_to(self.home / "not-mounted-yet" / "AGENTS.md")
        self.assertEqual([], pages.wanted(self.home))
        self.assertEqual([], pages.place(self.home, "ava"))
        self.assertTrue(page.is_symlink(), "the owner's link was replaced by a file")

    def test_only_what_is_missing_comes_back(self):
        (self.home / "MEMORY.md").unlink()
        self.assertEqual(["MEMORY.md"], pages.wanted(self.home))
        self.assertEqual(["MEMORY.md"], pages.place(self.home, "ava"))
        self.assertEqual([], pages.wanted(self.home))

    def test_a_missing_work_area_comes_back_without_touching_the_others(self):
        scripts_note = self.home / "scripts" / "README.md"
        scripts_note.write_text("keep this exact note", encoding="utf-8")
        shutil.rmtree(self.home / "plans")

        self.assertEqual(["plans/README.md"], pages.wanted(self.home))
        self.assertEqual(["plans/README.md"], pages.place(self.home, "ava"))
        self.assertTrue((self.home / "plans" / "README.md").is_file())
        self.assertEqual("keep this exact note", scripts_note.read_text(encoding="utf-8"))

    def test_an_area_note_the_owner_changed_is_left_exactly_as_it_is(self):
        note = self.home / "research" / "README.md"
        note.write_text("the owner's research rules", encoding="utf-8")
        self.assertEqual([], pages.place(self.home, "ava"))
        self.assertEqual("the owner's research rules", note.read_text(encoding="utf-8"))

    def test_a_linked_area_is_never_followed_to_fill_a_note(self):
        elsewhere = self.home.parent / "somebody-elses-research"
        elsewhere.mkdir()
        shutil.rmtree(self.home / "research")
        (self.home / "research").symlink_to(elsewhere)

        self.assertEqual([], pages.place(self.home, "ava"))
        self.assertEqual([], list(elsewhere.iterdir()))


class TheSweepEveryUpdateRuns(support.Isolated):
    """`everybody_has_theirs` — what reaches an agent made before any page shipped."""

    def setUp(self):
        super().setUp()
        for name in ("ava", "cole"):
            directory.made(name, "a-stand-in")

    def test_an_agent_missing_a_page_is_given_it_and_it_is_said(self):
        (directory.home("ava") / "AGENTS.md").unlink()
        said = []
        self.assertEqual([], pages.everybody_has_theirs(
            directory.known(), directory.home, said.append))
        self.assertEqual([], pages.wanted(directory.home("ava")))
        self.assertTrue([one for one in said if "ava" in one and "AGENTS.md" in one], said)

    def test_an_agent_that_has_them_all_is_not_mentioned(self):
        said = []
        pages.everybody_has_theirs(directory.known(), directory.home, said.append)
        self.assertEqual([], said)

    def test_one_home_that_cannot_be_written_never_stops_the_others(self):
        """This runs inside an update that has already carried the install forward. Taking the whole
        sweep down for one agent would leave every other one short for the sake of the first."""
        (directory.home("ava") / "MEMORY.md").unlink()
        (directory.home("cole") / "MEMORY.md").unlink()
        directory.home("ava").chmod(0o500)
        self.addCleanup(directory.home("ava").chmod, 0o755)
        left = pages.everybody_has_theirs(directory.known(), directory.home, lambda _line: None)
        self.assertEqual(["ava"], [name for name, _why in left])
        self.assertEqual([], pages.wanted(directory.home("cole")))

    def test_a_release_shipping_none_is_said_once_and_nothing_is_attempted(self):
        said = []
        a_release_with_no_pages()
        self.assertEqual([], pages.everybody_has_theirs(
            directory.known(), directory.home, said.append))
        self.assertEqual(1, len(said), said)


class WhenTheReleaseShipsNone(support.Isolated):
    """A broken checkout is a broken tree, and never a reason to be unable to make an agent."""

    def test_an_agent_is_still_made_and_what_it_lacks_is_said(self):
        a_release_with_no_pages()
        directory.made("ava", "a-stand-in")
        self.assertEqual(sorted(pages.PAGES), pages.wanted(directory.home("ava")))
        self.assertTrue(directory.records("ava").is_file())

    def test_a_home_that_cannot_be_written_makes_no_agent_at_all(self):
        """**The opposite expectation from the update sweep, and the two are easy to conflate.**
        The sweep tolerates one home it cannot write because the install is already carried and the
        other agents must still be reached. Creation may not: `_built` is inside the staging, so an
        `OSError` there has to come back out and take the staged directory with it. Swallowed, the
        rename would put a half-populated home under the agent's own name — which is the "half an
        agent is worse than none" failure the module exists to make impossible.
        """
        with mock.patch.object(pages, "place", side_effect=OSError("the disk is full")):
            with self.assertRaises(OSError):
                directory.made("ava", "a-stand-in")
        self.assertEqual([], sorted(paths.agents().iterdir()),
                         "a staged or renamed directory was left behind")
        self.assertEqual([], directory.known())

    def test_the_command_says_which_are_missing_rather_than_reporting_a_plain_success(self):
        a_release_with_no_pages()
        code, out, err = self.rundesk("agents", "add", "ava", "--provider", "a-stand-in")
        self.assertEqual(0, code, err)
        self.assertIn("AGENTS.md", out)
        self.assertIn("rundesk update", out)


if __name__ == "__main__":
    unittest.main()
