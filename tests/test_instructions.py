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


class InstructionBuilder(unittest.TestCase):
    """R-AGT-35 — one builder owns the core layers, variables, overrides, and appends."""

    def test_standard_variables_use_agent_and_user(self):
        self.assertEqual((
            "agent", "channel_kind", "channel_config_name", "channel_name", "channel_id",
            "channel_parent_name", "channel_parent_id", "channel_thread_name",
            "channel_thread_id", "channel_where", "user", "user_id",
            "conversation_id", "schedule",
        ), instructions.STANDARD_VARIABLES)

    def test_rundesk_instructions_are_always_first_and_fill_agent(self):
        built = instructions.build(variables={"agent": "ava"})
        self.assertEqual(agent.standing("ava"), built)
        self.assertTrue(built.startswith("You are ava, an agent running inside rundesk."))
        self.assertNotIn("{agent}", built)

    def test_standing_instruction_keeps_its_paragraph_boundaries(self):
        self.assertIn("\n\nAlways read the AGENTS.md", instructions.RUNDESK_INSTRUCTIONS)
        self.assertIn("\n\nWhen you reply to the user", instructions.RUNDESK_INSTRUCTIONS)

    def test_schedule_and_owner_instructions_append_in_order(self):
        built = instructions.build(
            variables={"agent": "ava", "schedule": "nightly"},
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

    def test_schedule_instructions_require_a_name(self):
        for missing in ("", "   ", None):
            with self.assertRaisesRegex(ValueError, "schedule name"):
                schedule.by_default(missing)

    def test_direct_message_uses_standard_channel_variables(self):
        built = instructions.build(
            variables={"agent": "ava", "channel_kind": "discord", "user": "Tim"},
            trigger=instructions.DIRECT,
        )
        self.assertIn(
            "You are responding through discord in a private conversation with Tim.",
            built,
        )

    def test_public_room_uses_standard_channel_variables(self):
        built = instructions.build(
            variables={
                "agent": "ava", "channel_kind": "discord", "user": "Tim",
                "channel_where": "#ops on Acme",
            },
            trigger=instructions.PUBLIC,
        )
        self.assertIn(
            "You are responding to Tim through discord in #ops on Acme.",
            built,
        )
        for safety in (
            "Anyone in that room can read what you write.",
            "Keep replies short",
            "never paste a credential, a private path",
            "other direct messages",
        ):
            self.assertIn(safety, built)

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
            record, "ava", "discord-dms", arrived, append="Agent addition."
        )
        self.assertTrue(built.startswith("You are ava"))
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
        )
        self.assertNotIn("Old adapter default.", built)
        self.assertIn("Adapter trigger for Tim.", built)
        self.assertLess(built.index("Adapter trigger"), built.index("Adapter addition."))
        self.assertTrue(built.endswith("Agent addition."))

    def test_only_trigger_prompt_text_lives_in_this_module(self):
        for use_case in (
            "ATTACHMENTS", "INTERRUPTED_RECOVERY", "AFTER_EXTERNAL_UPDATE",
            "MID_TURN_STEERING", "ANTIGRAVITY_STANDING_WRAPPER",
        ):
            self.assertFalse(hasattr(instructions, use_case), use_case)


if __name__ == "__main__":
    unittest.main()
