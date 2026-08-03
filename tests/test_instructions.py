#!/usr/bin/env python3
"""The builder for every instruction Rundesk sends to an agent brain."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rundesk import agent, channel, instructions, schedule  # noqa: E402

CORE = {
    "agent": "ava",
    "agent_slug": "ava",
    "agent_home": "/agents/ava/home",
    "workspace": "/agents/ava/home/workspace",
}


class InstructionBuilder(unittest.TestCase):
    """R-AGT-38 — one builder owns the core layers, variables, overrides, and appends."""

    def test_standard_variables_use_agent_and_user(self):
        self.assertEqual((
            "agent", "agent_slug", "agent_home", "workspace", "channel_kind", "channel_config_name",
            "channel_name", "channel_id", "channel_parent_name", "channel_parent_id",
            "channel_thread_name", "channel_thread_id", "channel_where", "user",
            "user_id", "conversation_id", "schedule", "roles",
        ), instructions.STANDARD_VARIABLES)

    def test_rundesk_instructions_are_always_first_and_fill_agent_locations(self):
        agents = Path("/agents")
        variables = agent.instruction_variables("ava", agents)
        built = instructions.build(variables=variables)
        self.assertEqual(agent.standing("ava", agents), built)
        self.assertIn("You are ava, an agent running inside rundesk.", built)
        self.assertIn("`/agents/ava/home`", built)
        self.assertIn("`/agents/ava/home/workspace`", built)
        self.assertIn(
            "Before your first reply in a conversation, read your three home files.",
            built,
        )
        for placeholder in ("{agent}", "{agent_slug}", "{agent_home}", "{workspace}"):
            self.assertNotIn(placeholder, built)

    def test_standing_instruction_keeps_its_paragraph_boundaries(self):
        """R-AGT-38 — the source is owner-readable, and what a brain reads is the shape
        that was written. What the paragraphs *say* is the owner's and moves whenever he
        edits it; that they survive filling is Rundesk's, so only that is held here."""
        paragraphs = instructions.RUNDESK_INSTRUCTIONS.split("\n\n")
        self.assertGreater(len(paragraphs), 2)
        for one in paragraphs:
            with self.subTest(paragraph=one[:40]):
                self.assertTrue(one.strip())
                self.assertEqual(one.strip(), one)
        self.assertTrue(paragraphs[0].startswith("# "))
        # Filling variables is a substitution and never a reflow: a layer collapsed into
        # one block on the way out is a different document from the one an owner edited.
        self.assertEqual(len(paragraphs),
                         len(instructions.build(variables=CORE).split("\n\n")))

    def test_core_instructions_keep_internal_routing_checks_silent(self):
        """R-AGT-46 — a self-created route miss is not progress or owner-facing friction."""
        built = instructions.build(variables=CORE)
        for rule in (
            "context recovery, routing, and repository discovery silently",
            "Mention routing only when the confirmed route is unavailable",
            "and blocks the requested outcome",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, built)

    def test_the_core_instructions_name_all_three_home_files(self):
        """R-AGT-56 — the layer nothing replaces names every file a home keeps. Naming
        them only in the home itself puts identity two hops from anything guaranteed to be
        read: a provider that loads its bootstrap page late, or not at all, then produces
        an agent with rules and no voice.

        The filenames are the guarantee; the sentence around each one is the owner's and
        moves when he rewrites it. This is the mirror of the leak check below, and the two
        are written the same way on purpose."""
        built = instructions.build(variables=CORE)
        for named in ("AGENTS.md", "SOUL.md", "MEMORY.md"):
            with self.subTest(home_file=named):
                self.assertIn(f"{CORE['agent_home']}/{named}", built)

    def test_the_roles_layer_lands_after_the_standing_rules_and_before_the_trigger(self):
        """An agent is told what it may hand work to without asking for the list, and it
        is told before anything about the turn it is in."""
        built = instructions.build(
            variables={**CORE, "roles": "- **research** (read) — Answer one question.",
                       "schedule": "nightly"},
            trigger=instructions.SCHEDULE,
            append="Owner addition.",
        )
        self.assertLess(built.index("You are ava"),
                        built.index("## Roles you may hand heavy work to"))
        self.assertLess(built.index("## Roles you may hand heavy work to"),
                        built.index("## Scheduled run"))
        self.assertLess(built.index("## Scheduled run"), built.index("Owner addition."))
        self.assertIn("- **research** (read) — Answer one question.", built)

    def test_the_roles_layer_is_filled_from_the_same_variables_as_the_rest(self):
        """The one layer that varies with the install is still rendered rather than
        pasted, so an agent is never shown a brace where its own slug should be."""
        variables = {**CORE, "roles": "- **research** (read) — Answer one question."}
        built = instructions.build(variables=variables)
        self.assertIn(
            instructions.render(instructions.ROLES_AVAILABLE, variables).strip(), built)
        self.assertIn("- **research** (read) — Answer one question.", built)
        for name in instructions.STANDARD_VARIABLES:
            with self.subTest(variable=name):
                self.assertNotIn("{" + name + "}", built)

    def test_an_install_with_no_roles_is_given_no_heading_at_all(self):
        """A heading with nothing under it is an agent told it has a capability and then
        shown none, which costs a turn to find out."""
        for listed in (None, "", "   "):
            with self.subTest(roles=listed):
                variables = dict(CORE) if listed is None else {**CORE, "roles": listed}
                built = instructions.build(variables=variables)
                self.assertNotIn("## Roles you may hand heavy work to", built)
                self.assertNotIn("delegating-to-roles", built)
                self.assertEqual(instructions.build(variables=CORE), built)

    def test_schedule_and_owner_instructions_append_in_order(self):
        built = instructions.build(
            variables={**CORE, "schedule": "nightly"},
            trigger=instructions.SCHEDULE,
            append=("Agent rules.", "Only inspect failures."),
        )
        self.assertLess(built.index("You are ava"), built.index("schedule 'nightly'"))
        self.assertLess(built.index("schedule 'nightly'"), built.index("Agent rules."))
        self.assertLess(built.index("Agent rules."), built.index("Only inspect failures."))
        self.assertEqual(
            instructions.render(
                instructions.SCHEDULE_INSTRUCTIONS, {"schedule": "nightly"}
            ),
            schedule.by_default("nightly"),
        )

    def test_scheduled_run_instructions_apply_only_to_schedule_triggers(self):
        variables = {**CORE, "schedule": "nightly"}
        core = instructions.build(variables=variables)
        scheduled = instructions.build(
            variables=variables,
            trigger=instructions.SCHEDULE,
        )
        schedule_layer = instructions.render(
            instructions.SCHEDULE_INSTRUCTIONS,
            variables,
        ).strip()
        self.assertEqual(f"{core}\n\n{schedule_layer}", scheduled)
        for trigger in ("", instructions.DIRECT, instructions.PUBLIC):
            with self.subTest(trigger=trigger):
                built = instructions.build(variables=variables, trigger=trigger)
                self.assertNotIn("## Scheduled run", built)
                self.assertNotIn("No user request started it", built)

    def test_schedule_instructions_require_a_name(self):
        for missing in ("", "   ", None):
            with self.assertRaisesRegex(ValueError, "schedule name"):
                schedule.by_default(missing)

    def test_direct_message_uses_standard_channel_variables(self):
        built = instructions.build(
            variables={**CORE, "channel_kind": "discord", "user": "Tim"},
            trigger=instructions.DIRECT,
        )
        self.assertIn(
            "You are responding through discord in a private conversation with Tim.",
            built,
        )

    def test_public_room_uses_standard_channel_variables(self):
        """R-AGT-38 — the public layer is one layer, filled from the standard names. What
        it warns a room about is the owner's sentence; that every name he wrote resolves
        to the value this turn actually has is what a test can hold."""
        variables = {
            **CORE, "channel_kind": "discord", "user": "Tim",
            "channel_where": "#ops on Acme",
        }
        built = instructions.build(variables=variables, trigger=instructions.PUBLIC)
        layer = instructions.render(instructions.PUBLIC_ROOM, variables).strip()
        self.assertEqual(f"{instructions.build(variables=variables)}\n\n{layer}", built)
        for value in ("discord", "Tim", "#ops on Acme"):
            with self.subTest(value=value):
                self.assertIn(value, layer)
        for name in instructions.STANDARD_VARIABLES:
            with self.subTest(variable=name):
                self.assertNotIn("{" + name + "}", built)

    def test_adapter_override_replaces_only_its_layer_and_append_follows(self):
        record = {"kind": "discord", channel.INSTRUCTIONS: ""}
        arrived = {
            "direct": True,
            "user": "2207",
            "conversation": "1180",
            "called": "Tim",
            channel.PROMPT_OVERRIDE: "Private adapter instruction for {user}.",
            channel.PROMPT_APPEND: "Adapter addition for {channel_config_name}.",
        }
        built = channel.preface(
            record, "ava", "discord-dms", arrived,
            core_variables={
                "agent_home": "/agents/ava/home",
                "workspace": "/agents/ava/home/workspace",
            },
            append="Agent addition.",
        )
        self.assertTrue(built.startswith("# Rundesk agent operating rules"))
        self.assertIn("You are ava", built)
        self.assertNotIn("private conversation", built)
        self.assertIn("Private adapter instruction for Tim.", built)
        self.assertLess(
            built.index("Private adapter instruction"),
            built.index("Adapter addition for discord-dms."),
        )
        self.assertTrue(built.endswith("Agent addition."))

    def test_adapter_prompt_hooks_survive_the_json_protocol_boundary(self):
        arrived = channel.understood(json.dumps({
            "type": "arrived",
            "conversation": "1180",
            "user": "2207",
            "text": "hello",
            "direct": True,
            "called": "Tim",
            channel.PROMPT_OVERRIDE: "Adapter trigger for {user}.",
            channel.PROMPT_APPEND: "Adapter addition.",
            channel.PROMPT_REPLACES: "Old adapter default.",
        }))
        self.assertIsNotNone(arrived)
        built = channel.preface(
            {"kind": "discord", channel.INSTRUCTIONS: "Old adapter default."},
            "ava", "discord-dms", arrived,
            append="Agent addition.",
            core_variables={
                "agent_home": "/agents/ava/home",
                "workspace": "/agents/ava/home/workspace",
            },
        )
        self.assertNotIn("Old adapter default.", built)
        self.assertIn("Adapter trigger for Tim.", built)
        self.assertLess(built.index("Adapter trigger"), built.index("Adapter addition."))
        self.assertTrue(built.endswith("Agent addition."))

    def test_a_role_execution_is_never_told_the_named_agent_core_rules(self):
        """R-ROL-5 — the floor is what cannot be replaced, and it is small. A worker told
        it has a home, a memory and a Rundesk to operate goes looking for an identity it
        does not have."""
        built = instructions.for_role(
            variables={"role": "Development", "parent_agent": "elena",
                       "role_run": "rol-1-aaaa", "target": "/projects/exporter",
                       "workspace": "/agents/elena/role-runs/rol-1-aaaa/home/workspace"},
            rules="# Development\n\nRun the tests.\n",
        )
        self.assertNotIn(instructions.RUNDESK_INSTRUCTIONS.split("\n")[0], built)
        for absent in ("MEMORY.md", "SOUL.md", "rundesk schedules", "rundesk messages",
                       "Operate Rundesk", "managing-rundesk"):
            self.assertNotIn(absent, built, absent)
        self.assertIn("on behalf of the named agent elena", built)
        self.assertIn("rol-1-aaaa", built)
        self.assertIn("/projects/exporter", built)

    def test_a_role_execution_is_never_told_which_files_a_home_keeps(self):
        """R-AGT-56, R-ROL-5 — naming the three files at the floor is what makes them
        unskippable for a named agent, and the same move is exactly what must not leak into
        an execution that has no home. `for_role` never calls `build`, so this is the guard
        on that separation staying real rather than incidental."""
        built = instructions.for_role(
            variables={"role": "Development", "parent_agent": "elena",
                       "role_run": "rol-1-aaaa", "target": "/projects/exporter",
                       "agent_home": "/agents/elena/home"},
            rules="# Development\n\nRun the tests.\n",
        )
        for named in ("SOUL.md", "MEMORY.md"):
            with self.subTest(home_file=named):
                self.assertNotIn(named, built)
        # Read off the core layer rather than quoted from it, so the guard holds whatever
        # the owner rewrites it to say. A line of the named agent's floor reaching an
        # execution is the leak, whichever line it turns out to be.
        for line in instructions.RUNDESK_INSTRUCTIONS.splitlines():
            if len(line.strip()) < 20:
                continue
            with self.subTest(line=line.strip()[:40]):
                self.assertNotIn(line.strip(), built)

    def test_a_role_execution_is_never_offered_roles_of_its_own(self):
        """R-ROL-5 — one role may not put another on, so an execution told which roles
        this install has is being shown a door it is refused at."""
        built = instructions.for_role(
            variables={"role": "Development", "parent_agent": "elena",
                       "role_run": "rol-1-aaaa", "target": "/projects/exporter",
                       "roles": "- **research** (read) — Answer one question."},
            rules="# Development\n\nRun the tests.\n",
        )
        self.assertNotIn("## Roles you may hand heavy work to", built)
        self.assertNotIn("- **research** (read)", built)
        self.assertNotIn("delegating-to-roles", built)

    def test_a_roles_own_rules_reach_the_brain_exactly_as_they_were_written(self):
        """R-ROL-10 — a run resumes with byte-identical rules, and a substitution is a
        difference. Nothing is filled into what the owner wrote."""
        built = instructions.for_role(
            variables={"parent_agent": "elena", "role": "Development"},
            rules="Keep {agent_home} and {role} literally.",
        )
        self.assertIn("Keep {agent_home} and {role} literally.", built)

    def test_the_role_layers_are_the_floor_then_the_rules_then_the_task(self):
        """R-ROL-5 — one stable order, so what a brain reads first is Rundesk's."""
        built = instructions.for_role(
            variables={"parent_agent": "elena", "role": "Development",
                       "role_run": "rol-1-aaaa"},
            rules="# Mine",
        )
        self.assertLess(built.index("# Role execution"), built.index("# Mine"))
        self.assertLess(built.index("# Mine"), built.index("## This execution"))
    def test_the_onboarding_layer_is_filled_with_the_agent_it_introduces(self):
        """R-CH-33 — this is the one turn where a brain has nothing but rundesk's words to
        go on, so what those words ask for is the owner's to write. What must hold is that
        the layer arrives whole and knows which agent it is introducing: an onboarding
        message that greets `{agent}` is the failure a name reaching it prevents."""
        variables = {"agent": "Ava", "agent_home": "/agents/ava/home"}
        built = instructions.build(variables=variables,
                                   trigger=instructions.ONBOARDING)
        self.assertIn(
            instructions.render(instructions.ONBOARDING_INSTRUCTIONS, variables).strip(),
            built)
        self.assertIn("Ava", built)
        self.assertNotIn("{agent}", built)

    def test_the_onboarding_layer_never_displaces_rundesks_own_rules(self):
        """R-AGT-38 — nothing replaces the core layer, and a trigger is one layer."""
        built = instructions.build(variables={"agent": "Ava"},
                                   trigger=instructions.ONBOARDING,
                                   append="Owner addition.")
        self.assertTrue(built.startswith(
            instructions.render(instructions.RUNDESK_INSTRUCTIONS,
                                {"agent": "Ava"}).strip().splitlines()[0]))
        self.assertLess(built.index("First message to a new owner"),
                        built.index("Owner addition."))
        self.assertNotIn("First message to a new owner",
                         instructions.build(variables={"agent": "Ava"}))

    def test_only_trigger_prompt_text_lives_in_this_module(self):
        for use_case in (
            "ATTACHMENTS", "INTERRUPTED_RECOVERY", "AFTER_EXTERNAL_UPDATE",
            "MID_TURN_STEERING", "ANTIGRAVITY_STANDING_WRAPPER",
        ):
            self.assertFalse(hasattr(instructions, use_case), use_case)


if __name__ == "__main__":
    unittest.main()
