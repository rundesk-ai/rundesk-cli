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
from rundesk.agents import directory, pages, records
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
        for name in pages.PAGES:
            source = pages.source_for(name)
            with self.subTest(name=name):
                self.assertTrue(
                    said[source].strip(), f"{source} is empty, and {name} comes from it")

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

    def test_it_starts_with_named_places_for_agent_owned_work(self):
        self.assertEqual(
            {"plans", "research", "scripts", "retros", "tasks"},
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

    def test_the_task_area_keeps_only_active_resumable_work(self):
        note = (self.home / "tasks" / "README.md").read_text(encoding="utf-8").lower()
        for phrase in ("multi-turn or delegated", "canonical", "yyyy-mm-dd", "remove the brief"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, note)

    def test_the_rules_it_got_are_byte_identical_under_both_names(self):
        self.assertEqual((self.home / "AGENTS.md").read_bytes(),
                         (self.home / "CLAUDE.md").read_bytes())

    def test_it_uses_the_single_agent_rules(self):
        self.assertEqual(
            (pages.shipped() / "agent" / "AGENTS.md").read_bytes(),
            (self.home / "AGENTS.md").read_bytes())

    def test_the_rules_have_the_required_sections(self):
        rules = (self.home / "AGENTS.md").read_text(encoding="utf-8")
        headings = ("# Agent Instructions", "## Role and Responsibilities", "## Responses",
                    "## Provider Subagents", "## Memory")
        places = []
        for heading in headings:
            with self.subTest(heading=heading):
                self.assertEqual(1, rules.count(heading))
                places.append(rules.index(heading))
        self.assertEqual(sorted(places), places)

    def test_a_person_is_answered_briefly_and_a_calling_agent_in_full(self):
        # The default reply length is a durable agent behavior, not a rule of one assignment, so it
        # ships in the template rather than being asked for again in every turn. The second half is
        # what stops it short of the handback, which is read by an agent that has to verify it.
        rules = (self.home / "AGENTS.md").read_text(encoding="utf-8")
        # Scoped to its own section and normalized, so a re-wrap cannot fail a fragment for a
        # reason that has nothing to do with the requirement.
        responses = " ".join(
            rules.split("## Responses", 1)[1].split("\n## ", 1)[0].split()).lower()
        # Requirement-level: "short", "direct", "outcome" and "verify" are ordinary words the rest
        # of the template already uses, so each fragment carries the clause it proves.
        for term in ("way you would text them", "short, direct", "lead with the outcome",
                     "understand, act on, or verify", "expand when the work",
                     "does not apply to a result you return to a calling agent",
                     "detail and evidence"):
            with self.subTest(term=term):
                self.assertIn(term, responses)

    def test_the_pages_say_what_they_are(self):
        rules = (self.home / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("MEMORY.md", rules)
        self.assertIn("# MEMORY", (self.home / "MEMORY.md").read_text(encoding="utf-8"))

    def test_the_rules_do_not_claim_the_two_rule_files_synchronize_after_placement(self):
        rules = (self.home / "AGENTS.md").read_text(encoding="utf-8")
        self.assertNotIn("editing one means editing both", rules)
        self.assertNotIn("CLAUDE.md", rules)

    def test_the_standing_rules_have_a_context_budget(self):
        rules = (self.home / "AGENTS.md").read_bytes()
        self.assertLessEqual(len(rules), 5050)

    def test_the_complete_standing_context_has_a_budget(self):
        total = sum(len((self.home / name).read_bytes()) for name in ("AGENTS.md", "MEMORY.md"))
        self.assertLessEqual(total, 5350)

    def test_the_memory_scaffold_has_only_durable_context_sections(self):
        raw = (self.home / "MEMORY.md").read_text(encoding="utf-8")
        headings = ("# MEMORY", "## Owner preferences", "## Traps and gotchas",
                    "## Durable facts and lessons", "## Stable references")
        places = []
        for heading in headings:
            with self.subTest(heading=heading):
                self.assertEqual(1, raw.count(heading))
                places.append(raw.index(heading))
        self.assertEqual(sorted(places), places)
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

    def test_an_agent_from_before_the_task_area_is_given_it(self):
        shutil.rmtree(directory.home("ava") / "tasks")
        said = []

        self.assertEqual([], pages.everybody_has_theirs(
            directory.known(), directory.home, said.append))

        self.assertTrue((directory.home("ava") / "tasks" / "README.md").is_file())
        self.assertTrue([one for one in said if "ava" in one and "tasks/README.md" in one], said)

    def test_a_legacy_role_value_does_not_select_a_different_template(self):
        records.stated(directory.records("ava"), {"role": "specialist"})
        for name in ("AGENTS.md", "CLAUDE.md"):
            (directory.home("ava") / name).unlink()

        pages.everybody_has_theirs(directory.known(), directory.home)

        expected = (pages.shipped() / "agent" / "AGENTS.md").read_bytes()
        self.assertEqual(expected, (directory.home("ava") / "AGENTS.md").read_bytes())
        self.assertEqual(expected, (directory.home("ava") / "CLAUDE.md").read_bytes())

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
