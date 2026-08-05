"""Why a skill an agent holds cannot be used.

Every verdict here is reached by really making that state on disk — a value left unset, a copy left
behind a catalog bump, a skill deleted out of a catalog, a script left without its executable bit.
A diagnosis proved by a stubbed-out fact is a diagnosis that agrees with itself.

Run directly: `python3 tests/test_skills_doctor.py`
"""

import unittest

from fixtures_skills import a_published_catalog, a_skill

import support
from rundesk.agents import directory
from rundesk.core import secrets
from rundesk.skills import catalogs, doctor, grants, library, needs

A_JIRA = {
    "JIRA_BASE_URL": "your Jira site, e.g. https://acme.atlassian.net",
    "JIRA_EMAIL": "the account the token belongs to",
    "JIRA_API_TOKEN": "an API token from id.atlassian.com",
}


class Doctor(support.Isolated):
    """A scratch install with one agent and a catalog holding a plain skill and a Jira one."""

    def setUp(self) -> None:
        super().setUp()
        library.where().mkdir(parents=True, exist_ok=True)
        self.published = self.home / "published"
        self.install("acme")
        directory.made("alan", "claude")

    def install(self, name: str, skills=("writing-plans", "jira")) -> None:
        source = a_published_catalog(self.published / name, name=name, skills=())
        for one in skills:
            a_skill(source / library.INSIDE / one,
                    needs=dict(A_JIRA) if one == "jira" else None,
                    scripts=("search.py",) if one == "jira" else ())
        with catalogs.brought(str(source)) as coming:
            if name in library.known():
                return
            catalogs.installed(coming)

    def grant(self, address: str, alias: str = "") -> grants.Grant:
        return grants.granted("alan", library.look_up(address), alias)

    def a_site(self, profile: str = "", **only: str) -> None:
        wanted = only or {one: f"value for {one}" for one in A_JIRA}
        for env, said in wanted.items():
            secrets.stated(needs.named(env, profile), said)

    def verdict(self, skill: str) -> doctor.Finding:
        return next(one for one in doctor.looked_at("alan") if one.skill == skill)


class WhatAHealthyInstallLooksLike(Doctor):
    def test_an_agent_holding_nothing_has_nothing_wrong_with_it(self):
        self.assertEqual([], doctor.looked_at("alan"))
        self.assertEqual([], doctor.counted(doctor.looked_over()))

    def test_a_skill_that_needs_nothing_is_ready_and_says_so(self):
        self.grant("acme/writing-plans")
        found = self.verdict("writing-plans")
        self.assertEqual(doctor.READY, found.verdict)
        self.assertFalse(found.trouble)
        self.assertIn("needs nothing", found.said)

    def test_a_skill_with_every_value_set_is_ready(self):
        self.grant("acme/jira")
        self.a_site()
        self.assertEqual(doctor.READY, self.verdict("jira").verdict)

    def test_a_ready_install_has_nothing_to_type(self):
        self.grant("acme/writing-plans")
        self.assertEqual([], doctor.fixes(doctor.counted(doctor.looked_over())))


class WhenNoProfileIsUsable(Doctor):
    def setUp(self) -> None:
        super().setUp()
        self.grant("acme/jira")

    def test_a_skill_with_nothing_set_is_blocked(self):
        found = self.verdict("jira")
        self.assertEqual(doctor.BLOCKED, found.verdict)
        self.assertTrue(found.trouble)

    def test_it_says_what_to_type(self):
        self.assertEqual("rundesk skills configure acme/jira", self.verdict("jira").fix)

    def test_a_half_configured_default_is_still_blocked_and_names_what_is_missing(self):
        self.a_site(JIRA_BASE_URL="https://acme.atlassian.net")
        found = self.verdict("jira")
        self.assertEqual(doctor.BLOCKED, found.verdict)
        said = "\n".join(doctor.readable(found))
        self.assertIn("JIRA_API_TOKEN", said)
        self.assertIn("JIRA_EMAIL", said)
        self.assertNotIn("JIRA_BASE_URL", said)

    def test_the_reason_a_value_is_needed_is_carried_through(self):
        # What makes this readable by an agent that has never seen the skill: it explains the
        # integration rather than reciting variable names.
        self.assertIn("id.atlassian.com", "\n".join(doctor.readable(self.verdict("jira"))))


class ThreeJiraSitesWithOneHalfDone(Doctor):
    """The case `PARTIAL` exists for."""

    def setUp(self) -> None:
        super().setUp()
        self.grant("acme/jira")
        self.a_site("acme")
        self.a_site("beta")
        secrets.stated("JIRA_BASE_URL__GAMMA", "https://gamma.atlassian.net")

    def test_two_working_sites_and_one_half_done_is_neither_ready_nor_blocked(self):
        # Collapsed either way this would cry wolf on a working setup, or hide the site that fails
        # at three in the morning.
        found = self.verdict("jira")
        self.assertEqual(doctor.PARTIAL, found.verdict)
        self.assertTrue(found.trouble)
        self.assertIn("2 of 3", found.said)

    def test_only_the_half_done_one_is_named(self):
        said = "\n".join(doctor.readable(self.verdict("jira")))
        self.assertIn("gamma  INCOMPLETE", said)
        self.assertIn("acme  ready", said)
        self.assertIn("beta  ready", said)

    def test_what_to_type_names_the_site_that_is_not_finished(self):
        self.assertEqual("rundesk skills configure acme/jira --profile gamma",
                         self.verdict("jira").fix)

    def test_the_default_nobody_uses_is_not_reported_as_a_problem(self):
        # A skill used entirely through named profiles has no default. Counting that as
        # half-configured would report every such install as broken for ever.
        self.assertNotIn(needs.DEFAULT_SHOWN, "\n".join(doctor.readable(self.verdict("jira"))))

    def test_finishing_the_third_makes_the_whole_thing_ready(self):
        secrets.stated("JIRA_EMAIL__GAMMA", "ops@gamma.example")
        secrets.stated("JIRA_API_TOKEN__GAMMA", "a token")
        found = self.verdict("jira")
        self.assertEqual(doctor.READY, found.verdict)
        self.assertIn("acme, beta, gamma", found.said)

    def test_a_named_profile_is_never_completed_by_the_default(self):
        # The safety rule, seen from the outside: a whole default set does not make a
        # half-configured site usable, because that would pair one site's URL with another's token.
        self.a_site()
        self.assertEqual(doctor.PARTIAL, self.verdict("jira").verdict)


class WhenAGrantPointsAtNothing(Doctor):
    def test_a_skill_whose_catalog_was_removed_is_dangling(self):
        self.grant("acme/writing-plans")
        catalogs.remove("acme")
        found = self.verdict("writing-plans")
        self.assertEqual(doctor.DANGLING, found.verdict)
        self.assertEqual("rundesk skills revoke alan writing-plans", found.fix)

    def test_a_skill_that_left_its_catalog_is_dangling(self):
        self.grant("acme/writing-plans")
        import shutil
        shutil.rmtree(library.tree("acme") / library.INSIDE / "writing-plans")
        self.assertEqual(doctor.DANGLING, self.verdict("writing-plans").verdict)

    def test_dangling_is_told_apart_from_stale(self):
        # One is repaired by `rundesk update` and the other by revoking a grant. Telling somebody
        # the wrong one sends them to a command that cannot help.
        self.grant("acme/writing-plans")
        catalogs.remove("acme")
        self.assertNotEqual(doctor.STALE, self.verdict("writing-plans").verdict)


class WhenACopyHasFallenBehind(Doctor):
    def setUp(self) -> None:
        super().setUp()
        self.install("other", skills=("writing-plans",))
        self.grant("acme/writing-plans")
        self.grant("other/writing-plans", alias="other-plans")

    def test_a_copy_that_matches_its_source_is_ready(self):
        self.assertEqual(doctor.READY, self.verdict("other-plans").verdict)

    def test_a_copy_behind_its_catalog_is_stale_and_says_how_to_repair_it(self):
        source = library.tree("other") / library.INSIDE / "writing-plans" / library.DECLARED
        source.write_text("---\nname: writing-plans\ndescription: Moved on. Use when.\n---\n",
                          encoding="utf-8")
        found = self.verdict("other-plans")
        self.assertEqual(doctor.STALE, found.verdict)
        self.assertEqual("rundesk update", found.fix)
        self.assertIn("other", found.said)

    def test_only_a_copy_can_be_stale(self):
        source = library.tree("acme") / library.INSIDE / "writing-plans" / library.DECLARED
        source.write_text("---\nname: writing-plans\ndescription: Moved on. Use when.\n---\n",
                          encoding="utf-8")
        self.assertEqual(doctor.READY, self.verdict("writing-plans").verdict)

    def test_a_listing_can_tell_a_copy_from_a_link(self):
        self.assertEqual("other (--as)", doctor.where(self.verdict("other-plans")))
        self.assertEqual("acme", doctor.where(self.verdict("writing-plans")))

    def test_making_it_again_clears_the_verdict(self):
        source = library.tree("other") / library.INSIDE / "writing-plans" / library.DECLARED
        source.write_text("---\nname: writing-plans\ndescription: Moved on. Use when.\n---\n",
                          encoding="utf-8")
        grants.refreshed()
        self.assertEqual(doctor.READY, self.verdict("other-plans").verdict)


class WhenSomethingIsWrongWithTheSkillItself(Doctor):
    def test_a_declaration_that_cannot_be_read_is_broken_rather_than_ready(self):
        # Saying "needs nothing" here would be exactly wrong: it needs something, and the thing
        # that was supposed to say so is broken.
        self.grant("acme/jira")
        (library.tree("acme") / library.INSIDE / "jira" / needs.WANTS).write_text(
            "{not json", encoding="utf-8")
        self.assertEqual(doctor.BROKEN, self.verdict("jira").verdict)

    def test_a_skill_md_no_brain_would_load_is_broken(self):
        self.grant("acme/writing-plans")
        (library.tree("acme") / library.INSIDE / "writing-plans" / library.DECLARED).write_text(
            "no frontmatter at all\n", encoding="utf-8")
        self.assertEqual(doctor.BROKEN, self.verdict("writing-plans").verdict)


class WhatAHealthySkillCanStillBeHiding(Doctor):
    def test_a_command_the_machine_would_not_run_is_its_own_verdict(self):
        # To an agent a script that is present and not executable looks exactly like one that works,
        # right up until it tries. Reported *beside* a READY verdict — which is what an earlier
        # version did, and what the live walkthrough caught — it is a warning nothing can gate on.
        self.grant("acme/jira")
        self.a_site()
        self.assertEqual(doctor.READY, self.verdict("jira").verdict)
        at = library.tree("acme") / library.INSIDE / "jira" / library.SCRIPTS / "search.py"
        at.chmod(0o644)

        found = self.verdict("jira")
        self.assertEqual(doctor.UNRUNNABLE, found.verdict)
        self.assertTrue(found.trouble, "a command that cannot run has to count as something to fix")
        self.assertIn("search.py", found.said)
        # The real file, not the path through alan's own link: six agents holding one skill must
        # print one line, and `fixes` deduplicates on the string.
        self.assertEqual(f"chmod +x {at}", found.fix)

    def test_two_agents_holding_one_unrunnable_command_is_one_thing_to_type(self):
        directory.made("ben", "grok")
        self.grant("acme/jira")
        grants.granted("ben", library.look_up("acme/jira"))
        self.a_site()
        (library.tree("acme") / library.INSIDE / "jira" / library.SCRIPTS
         / "search.py").chmod(0o644)
        found = doctor.counted(doctor.looked_over())
        self.assertEqual(2, len(found))
        self.assertEqual(1, len(doctor.fixes(found)))

    def test_a_missing_credential_is_said_before_an_unrunnable_command(self):
        # Both are true at once and one is more urgent. Naming both would bury the credential, which
        # is the one somebody cannot fix by looking at the skill.
        self.grant("acme/jira")
        (library.tree("acme") / library.INSIDE / "jira" / library.SCRIPTS
         / "search.py").chmod(0o644)
        self.assertEqual(doctor.BLOCKED, self.verdict("jira").verdict)

    def test_a_skill_that_ships_nothing_is_never_unrunnable(self):
        self.grant("acme/writing-plans")
        self.assertEqual(doctor.READY, self.verdict("writing-plans").verdict)


class LookingOverTheWholeInstall(Doctor):
    def setUp(self) -> None:
        super().setUp()
        directory.made("ben", "grok")
        self.grant("acme/jira")
        grants.granted("ben", library.look_up("acme/jira"))

    def test_every_agent_is_looked_at_unless_one_is_named(self):
        self.assertEqual({"alan", "ben"}, {one.agent for one in doctor.looked_over()})
        self.assertEqual({"alan"}, {one.agent for one in doctor.looked_over("alan")})

    def test_one_missing_value_blocking_two_agents_is_one_thing_to_type(self):
        # Six identical lines is a list somebody stops reading.
        found = doctor.counted(doctor.looked_over())
        self.assertEqual(2, len(found))
        self.assertEqual(["rundesk skills configure acme/jira"], doctor.fixes(found))

    def test_setting_the_value_clears_it_for_both(self):
        self.a_site()
        self.assertEqual([], doctor.counted(doctor.looked_over()))


if __name__ == "__main__":
    unittest.main()
