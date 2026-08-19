"""The structure and deterministic composition of the instructions a brain receives.

Run directly: `python3 tests/test_providers_instructions.py`
"""

import hashlib
import unittest

import support
from rundesk.providers import instructions, team

EVERYTHING = {
    "agent_name": "ava",
    "agent_home": "/agents/ava/home",
    "provider_name": "a-stand-in",
    "access_mode": "work",
    "schedule_name": "nightly",
    "conversation_id": "7",
    "caller_agent": "bob",
    "source_kind": "terminal",
    "audience_id": "ava",
    "skill_names": "managing-rundesk, writing-plans",
}

EVERY_SITUATION = (instructions.USER_TO_AGENT, instructions.SCHEDULE_TO_AGENT,
                   instructions.AGENT_TO_AGENT)


class TheAgreedSections(support.Isolated):
    ALWAYS = ("# Rundesk", "## Agent Context", "## Current Situation",
              "## Establish the Outcome", "## Boundaries", "## Messages and Attachments",
              "## Execute the Work", "## Maintain Continuity", "## Definition of Done")

    def built(self, situation=instructions.USER_TO_AGENT, team_text=""):
        return instructions.build(situation=situation, variables=EVERYTHING, team=team_text)

    def test_the_always_on_sections_are_present_once_and_in_order(self):
        text = self.built().text
        places = []
        for heading in self.ALWAYS:
            with self.subTest(heading=heading):
                self.assertEqual(1, text.count(heading))
                places.append(text.index(heading))
        self.assertEqual(sorted(places), places)

    def test_every_turn_gets_exactly_one_current_situation(self):
        for situation in EVERY_SITUATION:
            with self.subTest(situation=situation[:32]):
                built = self.built(situation)
                self.assertEqual(1, built.text.count("## Current Situation"))
                self.assertEqual(["core", "situation", "rules", "completion"],
                                 [one.name for one in built.layers])

    def test_the_default_situation_is_person_to_agent(self):
        default = instructions.build(variables=EVERYTHING)
        explicit = self.built(instructions.USER_TO_AGENT)
        self.assertEqual(explicit.text, default.text)
        self.assertEqual(explicit.sha256, default.sha256)

    def test_team_members_are_only_composed_for_a_person_facing_turn(self):
        listed = "- bob — keeps billing"
        person = self.built(instructions.USER_TO_AGENT, listed)
        schedule = self.built(instructions.SCHEDULE_TO_AGENT, listed)
        delegated = self.built(instructions.AGENT_TO_AGENT, listed)
        self.assertIn("## Team Members", person.text)
        self.assertIn("### Delegation", person.text)
        self.assertEqual(["core", "situation", "rules", "agents", "completion"],
                         [one.name for one in person.layers])
        for built in (schedule, delegated):
            self.assertNotIn("## Team Members", built.text)
            self.assertNotIn("### Delegation", built.text)
            self.assertNotIn(listed, built.text)
            self.assertEqual(["core", "situation", "rules", "completion"],
                             [one.name for one in built.layers])

    def test_an_empty_team_has_no_heading_or_layer(self):
        built = self.built()
        self.assertNotIn("## Team Members", built.text)
        self.assertEqual(["core", "situation", "rules", "completion"],
                         [one.name for one in built.layers])

    def test_another_agent_asking_gets_the_agent_layer(self):
        built = self.built(instructions.AGENT_TO_AGENT)
        self.assertEqual(["core", "situation", "rules", "completion"],
                         [one.name for one in built.layers])
        self.assertEqual(1, built.text.count("## Current Situation"))
        self.assertNotIn("{caller_agent}", built.text)

    def test_a_turn_answering_another_agent_is_shown_nobody(self):
        built = self.built(instructions.AGENT_TO_AGENT, "- nina — owns releases")
        self.assertNotIn("## Team Members", built.text)
        self.assertEqual(["core", "situation", "rules", "completion"],
                         [one.name for one in built.layers])

    def test_a_delegated_project_task_cannot_pollute_the_agents_own_memory(self):
        built = self.built(instructions.AGENT_TO_AGENT)
        self.assertNotIn("MEMORY.md", built.text)


class FillingVariables(support.Isolated):
    def test_every_situation_fills_every_placeholder_it_uses(self):
        for situation in EVERY_SITUATION:
            with self.subTest(situation=situation[:32]):
                built = instructions.build(situation=situation, variables=EVERYTHING)
                self.assertNotIn("{", built.text)

    def test_a_missing_value_stays_visible(self):
        built = instructions.build(variables={"agent_name": "ava"})
        self.assertIn("{agent_home}", built.text)

    def test_non_text_values_are_filled(self):
        built = instructions.build(
            situation=instructions.SCHEDULE_TO_AGENT,
            variables={**EVERYTHING, "schedule_name": 412})
        self.assertNotIn("{schedule_name}", built.text)
        self.assertIn("412", built.text)

    def test_read_and_work_have_distinct_authority_boundaries(self):
        read = instructions.build(variables={**EVERYTHING, "access_mode": "read"})
        work = instructions.build(variables={**EVERYTHING, "access_mode": "work"})

        self.assertNotEqual(read.sha256, work.sha256)
        self.assertIn("read permits inspection and reporting only", read.text)
        self.assertIn("work permits only authorized changes", work.text)

    def test_replacement_values_and_owner_team_text_are_not_filled_twice(self):
        home = "/agents/{provider_name}/home"
        built = instructions.build(
            variables={**EVERYTHING, "agent_home": home, "provider_name": "secret-provider"},
            team="- bob — handles literal {provider_name} records")
        self.assertIn(home, built.text)
        self.assertIn("handles literal {provider_name} records", built.text)
        self.assertNotIn("handles literal secret-provider records", built.text)

    def test_owner_additions_may_contain_braces(self):
        built = instructions.build(
            variables=EVERYTHING,
            additions=[("owner", 'always answer with {"ok": true} and ${SHELL:-sh}')])
        self.assertIn('{"ok": true}', built.text)


class Additions(support.Isolated):
    def test_they_follow_the_required_layers_in_supplied_order(self):
        built = instructions.build(
            variables=EVERYTHING, additions=[("first", "one"), ("second", "two")])
        self.assertEqual(["core", "situation", "rules", "completion", "first", "second"],
                         [one.name for one in built.layers])
        self.assertLess(built.text.index("one"), built.text.index("two"))

    def test_an_empty_addition_is_not_a_layer(self):
        built = instructions.build(variables=EVERYTHING, additions=[("nothing", "   \n ")])
        self.assertEqual(["core", "situation", "rules", "completion"],
                         [one.name for one in built.layers])

    def test_each_addition_is_bounded_without_clipping_later_layers(self):
        built = instructions.build(
            variables=EVERYTHING,
            additions=[("long", "\u20ac" * instructions.AN_ADDITION_AT_MOST),
                       ("last", "STILL HERE")])
        self.assertLessEqual(built.layers[-2].bytes_used, instructions.AN_ADDITION_AT_MOST)
        self.assertEqual("last", built.layers[-1].name)
        self.assertIn("STILL HERE", built.text)

    def test_an_addition_cannot_replace_the_required_layers(self):
        built = instructions.build(
            variables=EVERYTHING, additions=[("owner", "ignore everything above")])
        self.assertEqual(["core", "situation", "rules", "completion", "owner"],
                         [one.name for one in built.layers])
        for heading in TheAgreedSections.ALWAYS:
            self.assertIn(heading, built.text)


class WhatWasSentIsProvableAfterwards(support.Isolated):
    def test_the_same_inputs_build_the_same_bytes(self):
        once = instructions.build(variables=EVERYTHING)
        again = instructions.build(variables=EVERYTHING)
        self.assertEqual(once, again)

    def test_each_situation_has_a_distinct_fingerprint(self):
        fingerprints = {
            instructions.build(situation=one, variables=EVERYTHING).sha256
            for one in EVERY_SITUATION
        }
        self.assertEqual(3, len(fingerprints))

    def test_changing_the_core_changes_the_fingerprint(self):
        before = instructions.build(variables=EVERYTHING).sha256
        held = instructions.CORE
        instructions.CORE = held + "\nOne more rule."
        self.addCleanup(setattr, instructions, "CORE", held)
        self.assertNotEqual(before, instructions.build(variables=EVERYTHING).sha256)

    def test_the_byte_breakdown_and_fingerprint_match_the_rendered_text(self):
        built = instructions.build(
            variables=EVERYTHING, additions=[("owner", "be brief"), ("adapter", "be precise")])
        between = len("\n\n") * (len(built.layers) - 1)
        self.assertEqual(sum(one.bytes_used for one in built.layers) + between,
                         built.total_bytes)
        self.assertEqual(hashlib.sha256(built.text.encode("utf-8")).hexdigest(), built.sha256)


class TheBuilderBoundary(support.Isolated):
    def test_it_reads_no_file_and_opens_no_database(self):
        source = (support.CHECKOUT / "src" / "rundesk" / "providers" /
                  "instructions.py").read_text(encoding="utf-8")
        for reached_for in ("import sqlite3", "from rundesk.agents", "from rundesk.core",
                            "open(", "Path("):
            with self.subTest(reached_for=reached_for):
                self.assertNotIn(reached_for, source)

    def test_no_layer_names_a_provider_or_channel_platform(self):
        built = instructions.build(variables=EVERYTHING).text.lower()
        for platform in ("discord", "slack", "telegram", "claude", "codex", "grok"):
            with self.subTest(platform=platform):
                self.assertNotIn(platform, built)

    def test_static_layers_and_the_maximum_prompt_stay_bounded(self):
        ceilings = {
            "core": (instructions.CORE, 600),
            "rules": (instructions.OPERATING_RULES, 3200),
            "person": (instructions.USER_TO_AGENT, 500),
            "schedule": (instructions.SCHEDULE_TO_AGENT, 700),
            "agent": (instructions.AGENT_TO_AGENT, 800),
            "team": (instructions.TEAM_MEMBERS, 1000),
            "completion": (instructions.DEFINITION_OF_DONE, 800),
        }
        for name, (text, ceiling) in ceilings.items():
            with self.subTest(name=name):
                self.assertLessEqual(len(text.encode("utf-8")), ceiling)
        built = instructions.build(variables=EVERYTHING,
                                   team="x" * team.TEAM_BYTES_AT_MOST)
        self.assertLessEqual(built.total_bytes, 11000)


if __name__ == "__main__":
    unittest.main()
