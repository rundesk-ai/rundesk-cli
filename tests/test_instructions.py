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
            "user_id", "conversation_id", "schedule",
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
            "Before your first reply in a conversation, read `/agents/ava/home/AGENTS.md`.",
            built,
        )
        for placeholder in ("{agent}", "{agent_slug}", "{agent_home}", "{workspace}"):
            self.assertNotIn(placeholder, built)

    def test_standing_instruction_keeps_its_paragraph_boundaries(self):
        self.assertIn(
            "\n\nYou are {agent}, an agent running inside rundesk. "
            "Operate Rundesk with `rundesk`.\n\n",
            instructions.RUNDESK_INSTRUCTIONS,
        )
        self.assertIn(
            "\n\n- Your persistent home is `{agent_home}`;",
            instructions.RUNDESK_INSTRUCTIONS,
        )

    def test_core_instructions_prohibit_git_at_home_and_workspace_roots(self):
        """R-AGT-45 — an operational root must never be guessed into a repository."""
        built = instructions.build(variables=CORE)
        self.assertIn(
            "Never initialize them or run any Git command from either root",
            built,
        )
        self.assertIn(
            "Do not report either root's Git status.",
            built,
        )

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

    def test_every_agent_is_told_how_to_attach_a_local_file(self):
        """R-CH-31 — one portable final-answer convention reaches every brain."""
        built = instructions.build(variables=CORE)
        self.assertIn("Any Markdown link to an absolute local file path", built)
        self.assertIn("whether inline or on its own line", built)
        self.assertIn("optional `<` and `>` delimiters", built)
        self.assertIn("only when the file exists, is small enough, and sits inside", built)
        self.assertIn("removes the private path", built)
        self.assertIn("rundesk-attach: [LABEL](</absolute/path>)", built)
        self.assertIn("explicit form", built)
        self.assertIn("opening bracket with `\\`", built)

    def test_every_agent_is_told_where_an_attachment_may_come_from(self):
        """R-CH-31 — containment is a rule a brain can follow, not one it discovers by failing.

        The rejection is logged and never reaches the turn, so an agent whose file sits in a
        project directory sees an answer that simply arrives without it. Told only that a
        file "passes its safety checks", it rewrites the link — the one part that was right.
        """
        built = instructions.build(variables=CORE)
        self.assertIn("sits inside `/agents/ava/home` or this agent's own Rundesk log directory",
                      built)
        self.assertIn("A file anywhere else is never attached, and nothing tells you so", built)
        self.assertIn("a project directory you work in is outside", built)
        self.assertIn("copy the file under `/agents/ava/home/workspace`", built)
        self.assertIn("rather than rewriting the link", built)

    def test_core_instructions_keep_rundesk_operations_exact(self):
        built = instructions.build(variables=CORE)
        for command in (
            "rundesk messages ava --conversation <id>",
            "rundesk messages ava --source schedule",
            "rundesk messages ava",
            "rundesk schedules ava",
            "rundesk --help",
        ):
            with self.subTest(command=command):
                self.assertIn(f"`{command}`", built)
        self.assertIn("read it before answering", built)
        self.assertIn("only after running `rundesk schedules ava`", built)
        self.assertIn("Never substitute another scheduler.", built)
        self.assertIn("Treat `rundesk --help` as authoritative.", built)
        self.assertIn("`managing-rundesk` or applicable skill", built)

    def test_core_instructions_require_applicable_skills_before_work(self):
        """R-AGT-52 — granted procedures govern work instead of waiting to be named."""
        built = instructions.build(variables=CORE)
        self.assertIn(
            "Before starting work, review your available skills and follow every one that applies.",
            built,
        )

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

    def test_scheduled_run_instructions_define_unattended_outcomes(self):
        built = schedule.by_default("nightly")
        for rule in (
            "Treat the schedule's own task text as the request.",
            "Never infer additional work from earlier conversations or past runs.",
            "Never ask a question, request approval, or wait for a reply.",
            "Write nothing until the work is finished.",
            "Deliver exactly one report as that final message.",
            "When you found nothing worth acting on, say that in a short direct response.",
            "stop before that action and report `blocked`",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, built)

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
        built = instructions.build(
            variables={
                **CORE, "channel_kind": "discord", "user": "Tim",
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
    def test_the_onboarding_layer_names_the_agent_and_invents_no_work(self):
        """R-CH-33 — a new agent has no projects, no goals and no focus, and this is the
        one turn where a brain has nothing but rundesk's words to go on."""
        built = instructions.build(
            variables={"agent": "Ava", "agent_home": "/agents/ava/home"},
            trigger=instructions.ONBOARDING)
        self.assertIn("you are Ava", built)
        self.assertIn("very short", built)
        self.assertIn("Invite them to reach out", built)
        self.assertIn("Never invent, assume, or offer a project, goal, focus, or "
                      "specialty", built)
        self.assertIn("Write only the message itself", built)
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
