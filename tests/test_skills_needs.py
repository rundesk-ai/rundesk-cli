"""What a skill declares, which profiles it has, and whether each of them is whole.

The case this suite exists for is three Jira sites. A Jira account is a URL, an address and a token
that only mean anything together, so the thing that has to be right is that a profile is reasoned
about as a set — and that a half-configured one is told apart both from a working one and from one
nobody has started.

No case here prints or asserts on a credential's value, and nothing in `skills/` can read one —
`tests/test_layers.py` holds that.

Run directly: `python3 tests/test_skills_needs.py`
"""

import unittest

from fixtures_skills import a_skill, written

import support
from rundesk.core import secrets
from rundesk.skills import needs

#: What one Jira site takes. Three names that are worthless apart, which is the whole point.
A_JIRA = {
    "JIRA_BASE_URL": "your Jira site, e.g. https://acme.atlassian.net",
    "JIRA_EMAIL": "the account the token belongs to",
    "JIRA_API_TOKEN": "an API token from id.atlassian.com",
}


class Needs(support.Isolated):
    """A scratch install with one skill standing in it."""

    def setUp(self) -> None:
        super().setUp()
        self.at = a_skill(self.home / "jira", needs=dict(A_JIRA))
        self.needs = needs.declared(self.at)

    def given(self, **values: str) -> None:
        for key, said in values.items():
            secrets.stated(key, said)

    def a_site(self, profile: str = "", **only: str) -> None:
        """A whole Jira site under one profile, or the named part of one."""
        wanted = only or {one: f"value for {one}" for one in A_JIRA}
        self.given(**{needs.named(one, profile): said for one, said in wanted.items()})


class WhatASkillDeclares(Needs):
    def test_a_skill_with_nothing_beside_it_declares_nothing(self):
        bare = a_skill(self.home / "writing-plans")
        self.assertEqual([], needs.declared(bare))
        self.assertEqual("", needs.trouble_with(bare))

    def test_each_name_carries_why_it_is_needed(self):
        # The one thing that turns a name somebody has to guess at into an instruction they can
        # follow, and the only part of a diagnosis that says what the integration actually is.
        self.assertEqual(dict(A_JIRA), {one.env: one.about for one in self.needs})

    def test_they_come_back_in_the_order_the_author_wrote_them(self):
        # `configure` asks in this order, and somebody setting up a Jira site expects to be asked
        # for the site, then the account, then the token — which is what an author writes and is not
        # what sorts. Sorting replaced their judgement with the alphabet.
        self.assertEqual(list(A_JIRA), [one.env for one in self.needs])

    def test_a_declaration_that_cannot_be_read_is_refused_rather_than_read_as_empty(self):
        # The case where "this skill needs nothing" is exactly wrong: it needs something, and the
        # thing that was supposed to say so is broken.
        (self.at / needs.WANTS).write_text("{not json", encoding="utf-8")
        with self.assertRaises(needs.Refused) as refused:
            needs.declared(self.at)
        # And it says which of the two it is. "There and unreadable" and "not there" send somebody
        # to different places, and a message that collapsed them would send them to neither.
        self.assertIn("not readable", str(refused.exception))

    def test_a_name_with_no_reason_beside_it_is_refused(self):
        written(self.at / needs.WANTS, {"needs": {"JIRA_API_TOKEN": ""}})
        self.assertIn("JIRA_API_TOKEN", needs.trouble_with(self.at))

    def test_a_name_no_program_could_be_given_is_refused(self):
        for said in ("jira token", "1TOKEN", "jira-token", ""):
            with self.subTest(said=said):
                written(self.at / needs.WANTS, {"needs": {said: "why"}})
                self.assertNotEqual("", needs.trouble_with(self.at))

    def test_a_declared_name_may_not_carry_the_profile_separator(self):
        # `JIRA_TOKEN__ACME` declared as a need is indistinguishable from the ACME profile of a
        # need called `JIRA_TOKEN`, and every profile found from then on is one nobody made.
        written(self.at / needs.WANTS, {"needs": {"JIRA_TOKEN__ACME": "why"}})
        self.assertIn(needs.BETWEEN, needs.trouble_with(self.at))

    def test_needs_that_is_not_a_map_is_refused(self):
        written(self.at / needs.WANTS, {"needs": ["JIRA_API_TOKEN"]})
        self.assertNotEqual("", needs.trouble_with(self.at))


class HowAProfileIsWritten(Needs):
    def test_the_default_profile_is_the_plain_name(self):
        self.assertEqual("JIRA_API_TOKEN", needs.named("JIRA_API_TOKEN", ""))

    def test_a_named_profile_is_the_name_and_the_profile(self):
        self.assertEqual("JIRA_API_TOKEN__ACME", needs.named("JIRA_API_TOKEN", "acme"))

    def test_one_profile_is_one_profile_however_it_is_typed(self):
        # `acme` and `ACME` join into the same environment variable, so treating them as two would
        # produce a second half-configured set that looks like the first.
        self.assertEqual(needs.named("JIRA_API_TOKEN", "acme"),
                         needs.named("JIRA_API_TOKEN", "ACME"))

    def test_a_name_no_program_could_be_given_is_not_a_profile(self):
        for said in ("", "  ", "one two", "1acme", "acme-two"):
            with self.subTest(said=said):
                self.assertNotEqual("", needs.profile_trouble(said))
        self.assertEqual("", needs.profile_trouble("acme"))
        self.assertEqual("", needs.profile_trouble("acme_two"))


class WhichProfilesThereAre(Needs):
    def test_profiles_are_found_rather_than_declared(self):
        # A fourth site is four `rundesk env set` lines and nothing else: no edit to the skill, to
        # its catalog, or to any configuration on this machine.
        self.a_site("acme")
        self.a_site("beta")
        self.assertEqual(["ACME", "BETA"], needs.profiles(self.needs))

    def test_one_value_under_a_new_suffix_is_enough_to_find_it(self):
        # Which is what makes a half-configured site visible at all rather than invisible until it
        # is complete.
        self.given(JIRA_BASE_URL__GAMMA="https://gamma.atlassian.net")
        self.assertEqual(["GAMMA"], needs.profiles(self.needs))

    def test_the_default_is_not_among_them(self):
        self.a_site()
        self.assertEqual([], needs.profiles(self.needs))

    def test_a_value_belonging_to_another_skill_is_not_a_profile_of_this_one(self):
        self.given(CLOUDFLARE_API_TOKEN__WORK="x")
        self.assertEqual([], needs.profiles(self.needs))

    def test_a_name_that_merely_shares_a_prefix_is_not_a_profile_of_this_one(self):
        # `secrets` refuses a name ending in the separator, so the shape this really has to survive
        # is a longer name that happens to start the same way. Reading one as a profile would
        # invent a site nobody configured and then report it half-configured for ever.
        self.given(JIRA_BASE_URL_EXTRA="x")
        self.assertEqual([], needs.profiles(self.needs))


class WhetherAProfileIsWhole(Needs):
    def test_a_profile_with_every_value_is_whole(self):
        self.a_site("acme")
        held = needs.standing(self.needs, "acme")
        self.assertEqual((True, True, []), (held.exists, held.whole, held.missing))

    def test_a_profile_missing_one_value_names_exactly_that_one(self):
        self.a_site("gamma", JIRA_BASE_URL="https://gamma.atlassian.net",
                    JIRA_EMAIL="ops@gamma.example")
        held = needs.standing(self.needs, "gamma")
        self.assertTrue(held.exists)
        self.assertFalse(held.whole)
        self.assertEqual(["JIRA_API_TOKEN__GAMMA"], held.missing)

    def test_a_profile_nobody_has_started_exists_no_more_than_it_is_whole(self):
        # A profile nobody has touched is not a broken one. Only the half-configured one is worth a
        # sentence at three in the morning.
        held = needs.standing(self.needs, "nothing")
        self.assertFalse(held.exists)
        self.assertFalse(held.whole)

    def test_a_named_profile_never_borrows_a_value_from_the_default(self):
        # **The rule this whole module is shaped around.** Falling back is how one site's URL comes
        # to be used with another site's token, and the request succeeds against the wrong company.
        self.a_site()
        self.given(JIRA_BASE_URL__ACME="https://acme.atlassian.net",
                   JIRA_EMAIL__ACME="ops@acme.example")
        held = needs.standing(self.needs, "acme")
        self.assertFalse(held.whole)
        self.assertEqual(["JIRA_API_TOKEN__ACME"], held.missing)

    def test_the_default_never_borrows_from_a_named_profile_either(self):
        self.a_site("acme")
        held = needs.standing(self.needs, "")
        self.assertFalse(held.exists)
        self.assertEqual(sorted(A_JIRA), sorted(held.missing))

    def test_a_skill_that_declares_nothing_has_no_profiles_and_needs_none(self):
        bare = needs.declared(a_skill(self.home / "writing-plans"))
        self.assertEqual([], needs.every(bare))
        self.assertEqual([], needs.usable(bare))


class ThreeJiraSites(Needs):
    """The case that decided the shape: two working sites and one half-configured."""

    def setUp(self) -> None:
        super().setUp()
        self.a_site("acme")
        self.a_site("beta")
        self.given(JIRA_BASE_URL__GAMMA="https://gamma.atlassian.net")

    def test_the_two_that_work_are_usable_and_the_third_is_not(self):
        self.assertEqual(["acme", "beta"], [one.shown for one in needs.usable(self.needs)])

    def test_the_half_configured_one_is_named_and_the_working_ones_are_not(self):
        started = {one.shown: one for one in needs.started(self.needs)}
        self.assertEqual(["acme", "beta", "gamma"], sorted(started))
        self.assertFalse(started["gamma"].whole)
        self.assertEqual(["JIRA_API_TOKEN__GAMMA", "JIRA_EMAIL__GAMMA"],
                         sorted(started["gamma"].missing))

    def test_a_site_nobody_started_is_not_reported_at_all(self):
        self.assertNotIn("delta", [one.shown for one in needs.started(self.needs)])

    def test_the_unused_default_is_offered_but_never_counted_as_started(self):
        # A skill used entirely through named profiles has no default, and saying so is how
        # somebody sets one up. Counting it as half-configured would report every such install as
        # broken for ever.
        every = {one.shown: one for one in needs.every(self.needs)}
        self.assertIn(needs.DEFAULT_SHOWN, every)
        self.assertFalse(every[needs.DEFAULT_SHOWN].exists)
        self.assertNotIn(needs.DEFAULT_SHOWN, [one.shown for one in needs.started(self.needs)])

    def test_finishing_the_third_makes_it_usable_and_touches_neither_other(self):
        self.given(JIRA_EMAIL__GAMMA="ops@gamma.example",
                   JIRA_API_TOKEN__GAMMA="a token")
        self.assertEqual(["acme", "beta", "gamma"],
                         [one.shown for one in needs.usable(self.needs)])

    def test_the_default_is_shown_first_and_the_rest_in_name_order(self):
        self.assertEqual([needs.DEFAULT_SHOWN, "acme", "beta", "gamma"],
                         [one.shown for one in needs.every(self.needs)])


class WhatASkillShips(Needs):
    def test_a_skill_with_no_scripts_ships_none(self):
        self.assertEqual([], needs.ships(self.at))

    def test_the_commands_are_found_rather_than_listed(self):
        at = a_skill(self.home / "cloudflare", scripts=("zones.py", "purge.py"))
        self.assertEqual(["scripts/purge.py", "scripts/zones.py"],
                         [one.shown for one in needs.ships(at)])

    def test_a_command_that_the_machine_would_not_run_is_told_apart(self):
        # To an agent a script that is present and not executable looks exactly like one that
        # works, right up until it tries.
        at = a_skill(self.home / "cloudflare", scripts=("zones.py",))
        found = needs.ships(at)[0]
        self.assertTrue(found.runnable)
        found.at.chmod(0o644)
        self.assertFalse(needs.ships(at)[0].runnable)

    def test_what_a_command_reaches_for_is_not_offered_as_a_command(self):
        # Anything deeper than `scripts/` is a library, a template or a fixture that a command of
        # its own reaches for, and offering those would be telling an agent to run files nobody
        # meant to be run.
        at = a_skill(self.home / "cloudflare", scripts=("zones.py",))
        (at / "scripts" / "lib").mkdir()
        (at / "scripts" / "lib" / "shared.py").write_text("x", encoding="utf-8")
        self.assertEqual(["scripts/zones.py"], [one.shown for one in needs.ships(at)])


if __name__ == "__main__":
    unittest.main()
