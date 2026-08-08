"""The compact, skill-aware, online teammate listing injected into eligible turns."""

import contextlib
import unittest
from unittest import mock

import support
from rundesk.agents import directory
from rundesk.gateways import standing
from rundesk.providers import team
from rundesk.skills import grants


class ATeamForOneAgent(support.Isolated):
    def add(self, name, describes=""):
        directory.made(name, support.A_STAND_IN, describes)

    def skill(self, agent, name):
        at = grants.where(agent) / name
        at.mkdir(parents=True, exist_ok=True)
        (at / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Test skill.\n---\n", encoding="utf-8")

    def online(self, *agents):
        held = contextlib.ExitStack()
        for agent in agents:
            held.enter_context(standing.holding(directory.where(agent)))
        return held

    def test_it_lists_each_described_teammate_with_current_skill_names(self):
        self.add("ava", "Coordinates work.")
        self.add("reviewer", "Reviews production risk.")
        self.skill("reviewer", "senior-code-reviewer")
        self.skill("reviewer", "test-coverage-auditor")

        with self.online("reviewer"):
            said = team.for_agent("ava")

        self.assertIn("**reviewer**", said)
        self.assertIn("Reviews production risk.", said)
        self.assertIn("skills: senior-code-reviewer, test-coverage-auditor", said)

    def test_it_reads_grants_at_turn_time_instead_of_caching_them(self):
        self.add("ava", "Coordinates work.")
        self.add("researcher", "Does focused research.")
        with self.online("researcher"):
            self.assertIn("skills: none", team.for_agent("ava"))
            self.skill("researcher", "researching-topics")
            self.assertIn("skills: researching-topics", team.for_agent("ava"))

    def test_it_excludes_self_and_agents_without_a_description(self):
        self.add("ava", "Coordinates work.")
        self.add("unnamed")
        with self.online("ava", "unnamed"):
            self.assertEqual("", team.for_agent("ava"))

    def test_it_excludes_an_offline_described_agent(self):
        self.add("ava", "Coordinates work.")
        self.add("researcher", "Does focused research.")
        self.assertEqual("", team.for_agent("ava"))

    def test_it_does_not_list_an_agent_whose_liveness_cannot_be_verified(self):
        self.add("ava", "Coordinates work.")
        self.add("researcher", "Does focused research.")
        with mock.patch("rundesk.providers.team.locking.is_held", return_value=None):
            said = team.for_agent("ava")
        self.assertNotIn("**researcher**", said)
        self.assertIn("availability could not be verified", said)

    def test_one_unreadable_online_agent_does_not_hide_a_healthy_one(self):
        self.add("ava", "Coordinates work.")
        self.add("healthy", "Performs focused research.")
        self.add("broken", "Cannot be read.")
        directory.records("broken").write_bytes(b"not a database")
        with self.online("healthy", "broken"):
            said = team.for_agent("ava")
        self.assertIn("**healthy**", said)
        self.assertNotIn("**broken**", said)
        self.assertIn("availability could not be verified", said)

    def test_one_unreadable_skill_set_does_not_hide_a_healthy_agent(self):
        self.add("ava", "Coordinates work.")
        self.add("healthy", "Performs focused research.")
        self.add("broken", "Has unreadable grants.")
        actually_held = grants.held

        def held(agent):
            if agent == "broken":
                raise OSError("unreadable")
            return actually_held(agent)

        with self.online("healthy", "broken"), \
                mock.patch("rundesk.providers.team.grants.held", side_effect=held):
            said = team.for_agent("ava")
        self.assertIn("**healthy**", said)
        self.assertNotIn("**broken**", said)
        self.assertIn("availability could not be verified", said)

    def test_skill_names_are_bounded(self):
        self.add("ava", "Coordinates work.")
        self.add("specialist", "Handles a bounded specialty.")
        for number in range(team.SKILLS_AT_MOST + 3):
            self.skill("specialist", f"skill-{number:02d}")
        with self.online("specialist"):
            said = team.for_agent("ava")
        self.assertIn("+3 more", said)
        self.assertNotIn(f"skill-{team.SKILLS_AT_MOST:02d}", said)

    def test_the_number_of_teammates_injected_is_bounded(self):
        self.add("ava", "Coordinates work.")
        for number in range(team.TEAMMATES_AT_MOST + 3):
            self.add(f"specialist-{number:02d}", f"Specialty {number}.")
        specialists = [f"specialist-{number:02d}"
                       for number in range(team.TEAMMATES_AT_MOST + 3)]
        with self.online(*specialists):
            said = team.for_agent("ava")
        self.assertEqual(team.TEAMMATES_AT_MOST, said.count("- **"))
        self.assertNotIn(f"specialist-{team.TEAMMATES_AT_MOST:02d}", said)
        self.assertIn("3 more online agents omitted", said)
        self.assertLessEqual(len(said.encode("utf-8")), team.TEAM_BYTES_AT_MOST)


if __name__ == "__main__":
    unittest.main()
