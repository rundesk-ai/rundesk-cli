"""Which name a channel's credential stands under, and what happens when nothing does.

Two properties are worth this file, and neither is visible from the command suite driving `channels`
end to end.

**No agent name is ever mangled into another agent's name.** Sanitising is the obvious way to turn
an agent into an environment variable and it collides: `a-b` and `a_b` both fold to `A_B`, and the
symptom is two agents quietly answering as one bot with nothing anywhere saying so. So the cases
below are mostly punctuation and case, which is where a fold would show.

**There is one name, and no second one to fall through to.** A plain `A_TOKEN` is not read at all,
so an agent whose own name holds nothing is an agent with no credential — said plainly rather than
quietly started as somebody else's bot. Set, not set, and set-but-unreadable are still three
answers, and the third is still never read past.

Run directly: `python3 tests/test_channels_credentials.py`
"""

import json
import unittest

import support
from rundesk.agents import directory
from rundesk.channels import credentials
from rundesk.core import paths, secrets
from rundesk.skills import needs

A_TOKEN = "MTIzNDU2Nzg5-a-real-looking-bot-token"
ANOTHER_TOKEN = "OTg3NjU0MzIx-a-second-real-looking-bot-token"


class WhatAnAgentsOwnNameIs(support.Isolated):
    """The map from an agent to the suffix its credentials stand under."""

    def test_an_ordinary_name_becomes_the_only_case_a_secret_may_have(self):
        self.assertEqual("ALAN", credentials.suffix_for("alan"))
        self.assertEqual("A_TOKEN__ALAN", credentials.scoped_name("A_TOKEN", "alan"))

    def test_case_is_the_one_thing_that_changes_and_nothing_else_is_touched(self):
        for said in ("alan", "Alan", "ALAN", "aLaN"):
            with self.subTest(agent=said):
                self.assertEqual("ALAN", credentials.suffix_for(said))
        self.assertEqual("A_B", credentials.suffix_for("a_b"))
        self.assertEqual("BOT9", credentials.suffix_for("bot9"))

    def test_a_name_a_profile_cannot_have_gets_no_suffix_rather_than_a_folded_one(self):
        # Every one of these would fold onto some other agent's name under any sanitising, and the
        # first two would fold onto each other.
        for said in ("a-b", "a.b", "a b", "a/b", "9bot", "_bot", "", "  ", "a+b", "über"):
            with self.subTest(agent=said):
                self.assertEqual("", credentials.suffix_for(said))
                self.assertEqual("", credentials.scoped_name("A_TOKEN", said))

    def test_two_agents_that_would_collide_under_folding_do_not_collide_here(self):
        self.assertNotEqual(credentials.suffix_for("a_b"), credentials.suffix_for("a-b"))
        self.assertEqual("", credentials.suffix_for("a-b"),
                         "a name a profile cannot have was given one anyway")

    def test_every_agent_this_install_can_hold_has_a_suffix_of_its_own_or_none(self):
        # The injectivity claim, asked of real agents rather than of the regex. `directory.taken`
        # refuses a name differing from an existing one only by case, so at most one agent on an
        # install can fold to any given suffix — and an agent that cannot have one has none.
        paths.agents().mkdir(parents=True, exist_ok=True)
        for name in ("alan", "cole", "a_b", "a-b", "a.b", "bot9", "9bot"):
            directory.made(name, "a-stand-in")
        suffixes = [credentials.suffix_for(one) for one in directory.known()]
        named = [one for one in suffixes if one]
        self.assertEqual(sorted(set(named)), sorted(named),
                         "two agents on this install share one credential suffix")
        self.assertIn("", suffixes, "no case here covered an agent that cannot have a suffix")

    def test_it_is_spelled_the_way_a_skills_profile_is_spelled(self):
        # The research settled this as *no new naming rule*: a channel's credential is a profile of
        # the adapter, named for the agent. Two layers that may not import each other build it, so
        # the one that would drift is checked against the one that shipped first.
        self.assertEqual(needs.named("A_TOKEN", "alan"),
                         credentials.scoped_name("A_TOKEN", "alan"))
        self.assertEqual(secrets.PROFILED_BY, needs.BETWEEN)


class WhichNameAnswers(support.Isolated):
    """`standing` and `handed`, which have to agree because a diagnosis and a gateway ask them."""

    def scoped(self):
        return credentials.standing("alan", ["A_TOKEN"])[0]

    def test_with_nothing_kept_the_one_name_is_named_and_nothing_answers(self):
        one = self.scoped()
        self.assertEqual(("A_TOKEN", "A_TOKEN__ALAN", "", ""), tuple(one))
        self.assertEqual({}, credentials.handed("alan", ["A_TOKEN"]))

    def test_a_plain_install_wide_value_is_not_read_at_all(self):
        # The removed fallback, asserted as an absence. A release that read this would connect two
        # agents as one bot, which is the accident the whole shape exists to prevent.
        secrets.stated("A_TOKEN", A_TOKEN)
        self.assertEqual("", self.scoped().holding)
        self.assertEqual({}, credentials.handed("alan", ["A_TOKEN"]))

    def test_this_agents_own_name_is_the_one_that_answers(self):
        secrets.stated("A_TOKEN", ANOTHER_TOKEN)
        secrets.stated("A_TOKEN__ALAN", A_TOKEN)
        self.assertEqual("A_TOKEN__ALAN", self.scoped().holding)
        self.assertEqual({"A_TOKEN": A_TOKEN}, credentials.handed("alan", ["A_TOKEN"]))

    def test_the_value_arrives_under_the_name_the_adapter_declared(self):
        # The half that does not change. The adapter publishes `A_TOKEN` and reads `A_TOKEN`; where
        # rundesk found the value is rundesk's business and never crosses the seam.
        secrets.stated("A_TOKEN__ALAN", A_TOKEN)
        handed = credentials.handed("alan", ["A_TOKEN"])
        self.assertEqual(["A_TOKEN"], list(handed))
        self.assertNotIn("A_TOKEN__ALAN", handed)

    def test_an_agent_that_can_hold_no_credential_says_so_and_reads_nothing(self):
        # Truthfully refused rather than quietly downgraded. With the fallback gone there is no
        # plain name to fall back to, and folding `a-b` would be the collision itself.
        secrets.stated("A_TOKEN", A_TOKEN)
        one = credentials.standing("a-b", ["A_TOKEN"])[0]
        self.assertEqual("", one.scoped)
        self.assertEqual("", one.holding)
        self.assertIn("cannot hold a credential of its own", one.trouble)
        self.assertEqual({}, credentials.handed("a-b", ["A_TOKEN"]))

    def test_the_refusal_says_why_folding_is_not_the_answer(self):
        # The sentence has to carry the reason, or the next person to read it makes it "helpful".
        trouble = credentials.name_trouble("a-b")
        self.assertIn("a-b", trouble)
        self.assertIn("a_b", trouble)
        self.assertEqual("", credentials.name_trouble("a_b"))

    def test_a_cleared_name_of_this_agents_own_is_simply_unset(self):
        # Emptying this agent's own name switches its bot off, and that is the whole answer: there
        # is nowhere to fall through to, so nothing can start it as a different bot.
        secrets.stated("A_TOKEN", A_TOKEN)
        secrets.stated("A_TOKEN__ALAN", ANOTHER_TOKEN)
        secrets.cleared("A_TOKEN__ALAN")
        one = self.scoped()
        self.assertEqual("", one.holding)
        self.assertEqual("", one.trouble)
        self.assertEqual({}, credentials.handed("alan", ["A_TOKEN"]))

    def test_an_unreadable_name_of_this_agents_own_is_never_answered_from_anywhere_else(self):
        # The third state. A plain value standing beside it changes nothing at all now, which is
        # the strongest form of the guarantee.
        secrets.stated("A_TOKEN", A_TOKEN)
        self.a_value_nothing_can_open("A_TOKEN__ALAN")
        one = self.scoped()
        self.assertEqual("", one.holding)
        self.assertIn("A_TOKEN__ALAN", one.trouble)
        self.assertEqual({}, credentials.handed("alan", ["A_TOKEN"]))

    def test_an_unreadable_scoped_name_is_said_rather_than_read_as_unset(self):
        self.a_value_nothing_can_open("A_TOKEN__ALAN")
        one = self.scoped()
        self.assertEqual("", one.holding)
        self.assertIn("A_TOKEN__ALAN", one.trouble)

    def test_several_credentials_are_each_answered_on_their_own(self):
        # An adapter may name more than one, and nothing here is written for a list of exactly one.
        secrets.stated("ONE__ALAN", A_TOKEN)
        secrets.stated("TWO__ALAN", ANOTHER_TOKEN)
        secrets.stated("THREE", A_TOKEN)            # plain, and therefore not read
        found = credentials.standing("alan", ["ONE", "TWO", "THREE"])
        self.assertEqual(["ONE__ALAN", "TWO__ALAN", ""], [one.holding for one in found])
        self.assertEqual({"ONE": A_TOKEN, "TWO": ANOTHER_TOKEN},
                         credentials.handed("alan", ["ONE", "TWO", "THREE"]))

    def a_value_nothing_can_open(self, name: str) -> None:
        """Leave a sealed value under `name` that this install's key will not verify."""
        secrets.stated(name, A_TOKEN)
        where = secrets.where()
        said = json.loads(where.read_text(encoding="utf-8"))
        said[name] = "v2:AAAAAAAAAAAAAAAAAAAAAA==:AAAA:AAAA"
        where.write_text(json.dumps(said), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
