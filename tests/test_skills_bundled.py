"""The skills rundesk ships, held to the rules they teach.

Two things are checked here and the second is the one that matters. Every shipped skill has to be a
skill every brain will load — which is what the library already enforces for anybody else's catalog,
and there is no reason ours should be exempt. And **no shipped skill may name a verb this build does
not have**: `AGENTS.md` forbids offering an operation that is not built, and a skill is the one place
that rule can be broken without any command going wrong. It is read by an agent, on every turn, and
what it teaches is acted on.

The build this replaces shipped skills for roles and schedules long after both worked, which was
fine — and shipped a skill teaching an invocation path nothing set, which was not.

Run directly: `python3 tests/test_skills_bundled.py`
"""

import argparse
import re
import shutil
import unittest

import support
from rundesk import cli
from rundesk.skills import catalogs, library, needs

#: Where a skill really tells somebody to type something: a fenced block, or an inline code span.
#: Prose is deliberately not read — "rundesk is the thing running you" names no verb, and a check
#: that took it for one is a check nobody can keep green and everybody learns to work around.
_FENCED = re.compile(r"^```.*?^```", re.M | re.S)
_INLINE = re.compile(r"`([^`\n]+)`")

#: A verb, at the start of what somebody would type — spelled either way a skill may write it.
#:
#: **`"$RUNDESK_COMMAND"` is read too, and leaving it out would be this check going quietly blind.**
#: A skill that tells an agent to type the reachable form is telling it to type a verb, and a pattern
#: that only knew the bare word would go on passing while every command in the skill went unchecked —
#: which is this guard's own documented failure mode, arrived at by adding a spelling rather than by
#: removing a rule.
_TYPED = re.compile(r'^(?:rundesk|"\$RUNDESK_COMMAND") (--?[a-z][a-z-]*|[a-z][a-z-]*)', re.M)


def verbs_named(said: str):
    """Every `rundesk <verb>` this text tells somebody to type, in the order they appear.

    Read out of code only. A skill is prose with commands in it, and the two have to be told apart
    by something other than hope — this product's own name appears in ordinary sentences all through
    the skills that are about it.
    """
    found = []
    for block in _FENCED.findall(said):
        found.extend(_TYPED.findall(block))
    for span in _INLINE.findall(_FENCED.sub("", said)):
        found.extend(_TYPED.findall(span))
    return found


def verbs_of(parser: argparse.ArgumentParser):
    """Every verb this build really has, read off the parser rather than listed here.

    Read off the command so that a skill naming something that has just landed passes the day it
    lands, and a skill naming something that has just been taken away fails the same day. A list
    kept here is a list that disagrees with the product.
    """
    found = set()
    for action in parser._actions:
        if isinstance(action, cli.Subcommands):
            found.update(action.choices)
        for one in action.option_strings:
            found.add(one)
    return found


class Bundled(support.Isolated):
    """The skills standing in this release, and the catalog they are installed as."""

    def setUp(self) -> None:
        super().setUp()
        # **Not skipped when they are missing.** They are a shipped asset beside `src/providers/`,
        # which nothing skips over, so a release that lost them goes red here rather than green with
        # a skip nobody reads — `OK` and `OK (skipped=14)` are the same word in a summary.
        library.where().mkdir(parents=True, exist_ok=True)
        # The catalog the release ships: its manifest, and one directory per skill beside it.
        # Not the shape it is installed in — `place_bundled` puts the skills a level down, into the
        # `skills/` a catalog on disk keeps them in.
        self.skills = catalogs.shipped()

    def named(self):
        """Every skill this release ships, in name order."""
        return sorted(one.name for one in self.skills.iterdir()
                      if (one / library.DECLARED).is_file())


class WhatIsShipped(Bundled):
    def test_there_is_something_to_check(self):
        # A check that discovers its own work fails when it discovers none: a walk pointed at a
        # directory that had moved would otherwise pass having read nothing.
        self.assertTrue(self.named(), f"no skills found under {self.skills}")

    def test_the_manifest_is_one_this_release_can_read(self):
        # It stands beside the skills it describes, and is read by the same reader every published
        # catalog's is — so a manifest this release would refuse from anybody else is one it refuses
        # from itself, here, rather than on somebody's machine.
        manifest = library.read_manifest(self.skills)
        self.assertEqual(library.BUNDLED, manifest.name)
        self.assertEqual(library.SCHEMA, manifest.schema)

    def test_it_holds_only_what_is_coupled_to_this_version(self):
        # The reason this catalog exists at all. A skill about writing pull requests does not change
        # when rundesk does, so shipping it here would tie a correction to it to a rundesk release —
        # it belongs in the catalog that is fetched. Everything here is about *this* rundesk.
        self.assertEqual(["managing-rundesk", "writing-skills"], self.named())

    def test_every_shipped_skill_is_one_a_brain_would_load(self):
        # The same check any other catalog is held to on the way in. Ours is not exempt, and the
        # cost of it being wrong is higher: it is on every machine.
        for name in self.named():
            with self.subTest(skill=name):
                self.assertEqual("", library.trouble_with(self.skills / name))

    def test_every_shipped_skill_declares_its_credentials_readably(self):
        for name in self.named():
            with self.subTest(skill=name):
                self.assertEqual("", needs.trouble_with(self.skills / name))

    def test_every_command_a_shipped_skill_ships_can_be_run(self):
        # A script that is present and not executable looks exactly like one that works, right up
        # until something tries — and this one would be shipped that way to every machine.
        for name in self.named():
            for one in needs.ships(self.skills / name):
                with self.subTest(skill=name, script=one.shown):
                    self.assertTrue(one.runnable, f"{name}/{one.shown} is not executable")

    def test_the_whole_catalog_installs(self):
        # Driven through the real install rather than checked file by file, because that is what
        # every machine does with it and it is the check that would have caught a catalog whose
        # parts are each fine.
        self.assertTrue(catalogs.place_bundled())
        self.assertIn(library.BUNDLED, library.known())
        self.assertTrue(library.held(library.BUNDLED))

    def test_a_skill_edited_in_place_is_put_back_by_the_sweep_every_install_and_update_runs(self):
        # **Through `refresh`, which is the one path both `rundesk install` and `rundesk update`
        # take**, rather than through `place_bundled` on its own. The case below drives the direct
        # call and would stay green if the sweep stopped calling it — which is the way this
        # guarantee would really be lost, because nobody invokes `place_bundled` by hand.
        catalogs.refresh()
        drifted = (library.tree(library.BUNDLED) / library.INSIDE / "managing-rundesk"
                   / library.DECLARED)
        was = drifted.read_text(encoding="utf-8")
        drifted.write_text("---\nname: managing-rundesk\ndescription: edited\n---\n",
                           encoding="utf-8")
        # A skill somebody deleted outright is put back too: the whole tree is replaced, so what is
        # standing afterwards is what the release ships and not what was left of it.
        gone = library.tree(library.BUNDLED) / library.INSIDE / "writing-skills"
        shutil.rmtree(gone)

        catalogs.refresh()

        self.assertEqual(was, drifted.read_text(encoding="utf-8"))
        self.assertTrue((gone / library.DECLARED).is_file())
        self.assertEqual(self.named(), library.found(library.tree(library.BUNDLED)))

    def test_it_is_replaced_out_of_the_release_rather_than_left_as_it_was(self):
        # Version-coupled: an install that moved forward and kept the previous release's copy would
        # be handing every agent instructions for a rundesk it is no longer running.
        catalogs.place_bundled()
        drifted = (library.tree(library.BUNDLED) / library.INSIDE / "managing-rundesk"
                   / library.DECLARED)
        was = drifted.read_text(encoding="utf-8")
        drifted.write_text("---\nname: managing-rundesk\ndescription: edited\n---\n",
                           encoding="utf-8")
        self.assertFalse(catalogs.place_bundled())
        self.assertEqual(was, drifted.read_text(encoding="utf-8"))

    def test_it_is_never_fetched_from_anywhere(self):
        catalogs.place_bundled()
        self.assertFalse(catalogs.may_be_fetched(library.BUNDLED))

    def test_neither_dependency_may_be_removed(self):
        for name in (library.BUNDLED, library.DEPENDED):
            with self.subTest(catalog=name):
                self.assertFalse(catalogs.may_be_removed(name))
                self.assertNotEqual("", catalogs.what_stays(name))


class WhatAShippedSkillMayClaim(Bundled):
    def test_no_shipped_skill_names_a_verb_this_build_does_not_have(self):
        # `AGENTS.md`: a verb rundesk cannot perform is a verb rundesk does not have. A skill is the
        # one place that can be broken with nothing going red — it is read by an agent, on every
        # turn, and acted on. The build this replaces shipped one teaching an invocation path
        # nothing set.
        there = verbs_of(cli.build_parser())
        self.assertTrue(there, "the parser answered no verbs at all")
        for name in self.named():
            said = (self.skills / name / library.DECLARED).read_text(encoding="utf-8")
            for verb in sorted(set(verbs_named(said))):
                with self.subTest(skill=name, verb=verb):
                    self.assertIn(verb, there,
                                  f"{name} tells an agent to type `rundesk {verb}`, and this "
                                  "build has no such verb")

    def test_the_check_would_notice_a_verb_that_went_away(self):
        # The guard on the guard. A pattern that matched nothing, or a verb set that answered
        # everything, would leave the case above green for ever — and this is exactly the check
        # whose failure mode is silence.
        # Re-pointed when `schedules` landed, again when `channels` did, and again when `providers`
        # did — exactly as intended: it has to name a verb this build really does not have, so the
        # next one to arrive moves it again, and the person moving it is the person who can see what
        # is still absent.
        #
        # What is still absent is delegation. An agent can be asked something by a person, by the
        # clock and by a channel; being asked by *another agent* is reserved throughout — the
        # conversation records already hold `agent` and `role` as sources, and the prompt builder
        # keeps a layer for each — and nothing produces one, so `rundesk delegations` is a verb
        # rundesk does not have.
        self.assertNotIn("delegations", verbs_of(cli.build_parser()))
        self.assertEqual(["gateways"], verbs_named("run `rundesk gateways logs alan` to see"))
        self.assertEqual(["env"], verbs_named("```sh\nrundesk env set NAME\n```"))
        self.assertEqual(["--help"], verbs_named("`rundesk --help` is generated"))
        # And prose naming the product is read as prose, whether it opens a line or not.
        self.assertEqual([], verbs_named("rundesk is the thing running you"))
        self.assertEqual([], verbs_named("Nothing else here is rundesk itself, whatever it says"))
        # **The reachable spelling is read as a command too.** A skill tells an agent to type
        # `"$RUNDESK_COMMAND" <verb>`, because a bare `rundesk` is not on every brain's path — and a
        # pattern that only knew the bare word would leave every one of those commands unchecked
        # while the case above went on passing, which is silence rather than a failure.
        self.assertEqual(["status"], verbs_named('```sh\n"$RUNDESK_COMMAND" status\n```'))
        self.assertEqual(["skills"], verbs_named('`"$RUNDESK_COMMAND" skills list alan`'))


class WhatTheDocumentationClaims(support.Isolated):
    """`docs/commands.md` says it is the complete list of what rundesk can do.

    That page is checked by people, and people are exactly who a stale verb misleads: `AGENTS.md`
    forbids offering an operation that is not built, and a documented verb that does not exist is the
    same promise broken one step further from the code. The shipped skills are already held to this;
    there is no reason the page a person reads should be the one thing that is not.
    """

    def test_every_skills_sub_verb_the_docs_name_is_one_that_exists(self):
        said = (support.CHECKOUT / "docs" / "commands.md").read_text(encoding="utf-8")
        there = _sub_verbs_of("skills")
        self.assertTrue(there, "the parser answered no sub-verbs for skills")
        named = set(re.findall(r"rundesk skills ([a-z][a-z-]*)", said))
        self.assertTrue(named, "the page names no skills sub-verb at all")
        for verb in sorted(named - {"list"}):
            with self.subTest(verb=verb):
                self.assertIn(verb, there,
                              f"docs/commands.md tells somebody to type `rundesk skills {verb}`, "
                              "and this build has no such sub-verb")

    def test_every_sub_verb_that_exists_is_named_by_the_docs(self):
        # The other direction, because the page claims to be *complete*. A verb that shipped without
        # reaching the page is the shape that goes unnoticed for a release.
        said = (support.CHECKOUT / "docs" / "commands.md").read_text(encoding="utf-8")
        for verb in sorted(_sub_verbs_of("skills")):
            with self.subTest(verb=verb):
                self.assertIn(f"rundesk skills {verb}", said,
                              f"`rundesk skills {verb}` exists and docs/commands.md never names it")


def _sub_verbs_of(group: str):
    """Every sub-verb one group really has, read off the parser rather than listed here."""
    for action in cli.build_parser()._actions:
        if isinstance(action, cli.Subcommands) and group in action.choices:
            for one in action.choices[group]._actions:
                if isinstance(one, cli.Subcommands):
                    return set(one.choices)
    return set()


if __name__ == "__main__":
    unittest.main()
