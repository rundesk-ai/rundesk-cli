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

#: The agent every case here builds a preface for. Named for the agent rather than for the
#: layer, because `instructions.CORE` is now a layer of its own and two things called the
#: same word in one expression is how a reader stops trusting either.
AVA = {
    "agent": "ava",
    "agent_slug": "ava",
    "agent_home": "/agents/ava/home",
    "workspace": "/agents/ava/home/workspace",
}

#: Every preface rundesk built before the layers were named — captured once, committed, and
#: never regenerated from the code it guards. See `samples/README.md`.
BEFORE = json.loads(
    (ROOT / "tests" / "samples"
     / "instructions-before-the-layers-were-named.json").read_text())


class InstructionBuilder(unittest.TestCase):
    """R-AGT-38 — one builder owns the core layers, variables, overrides, and appends."""

    def test_standard_variables_use_agent_and_user(self):
        self.assertEqual((
            "agent", "agent_slug", "agent_home", "workspace", "channel_kind", "channel_config_name",
            "channel_name", "channel_id", "channel_parent_name", "channel_parent_id",
            "channel_thread_name", "channel_thread_id", "channel_where", "user",
            "user_id", "conversation_id", "schedule", "roles", "caller_agent",
        ), instructions.STANDARD_VARIABLES)

    def test_rundesk_instructions_are_always_first_and_fill_agent_locations(self):
        """R-AGT-38 — rundesk's own words before anybody else's, and the agent's resolved
        locations filled into them. `CORE_INSTRUCTIONS` is what stands first now and the
        agent layer directly after it; both are rundesk's, which is what this is about."""
        agents = Path("/agents")
        variables = agent.instruction_variables("ava", agents)
        built = instructions.build(variables=variables)
        self.assertEqual(agent.standing("ava", agents), built)
        self.assertTrue(built.startswith(instructions.CORE_INSTRUCTIONS))
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
        paragraphs = instructions.AGENT_IDENTITY.split("\n\n")
        self.assertGreater(len(paragraphs), 2)
        for one in paragraphs:
            with self.subTest(paragraph=one[:40]):
                self.assertTrue(one.strip())
                self.assertEqual(one.strip(), one)
        self.assertTrue(paragraphs[0].startswith("# "))
        # Filling variables is a substitution and never a reflow: a layer collapsed into
        # one block on the way out is a different document from the one an owner edited.
        self.assertEqual(
            len(paragraphs),
            len(instructions.render(instructions.AGENT_IDENTITY, AVA).split("\n\n")))

    def test_core_instructions_keep_internal_routing_checks_silent(self):
        """R-AGT-46 — a self-created route miss is not progress or owner-facing friction."""
        built = instructions.build(variables=AVA)
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
        built = instructions.build(variables=AVA)
        for named in ("AGENTS.md", "SOUL.md", "MEMORY.md"):
            with self.subTest(home_file=named):
                self.assertIn(f"{AVA['agent_home']}/{named}", built)

    def test_the_roles_layer_lands_after_the_standing_rules_and_before_the_trigger(self):
        """An agent is told what it may hand work to without asking for the list, and it
        is told before anything about the turn it is in."""
        built = instructions.build(
            variables={**AVA, "roles": "- **research** (read) — Answer one question.",
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
        variables = {**AVA, "roles": "- **research** (read) — Answer one question."}
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
                variables = dict(AVA) if listed is None else {**AVA, "roles": listed}
                built = instructions.build(variables=variables)
                self.assertNotIn("## Roles you may hand heavy work to", built)
                self.assertNotIn("delegating-to-roles", built)
                self.assertEqual(instructions.build(variables=AVA), built)

    def test_schedule_and_owner_instructions_append_in_order(self):
        built = instructions.build(
            variables={**AVA, "schedule": "nightly"},
            trigger=instructions.SCHEDULE,
            append=("Agent rules.", "Only inspect failures."),
        )
        self.assertLess(built.index("You are ava"), built.index("schedule 'nightly'"))
        self.assertLess(built.index("schedule 'nightly'"), built.index("Agent rules."))
        self.assertLess(built.index("Agent rules."), built.index("Only inspect failures."))
        self.assertEqual(
            instructions.render(
                instructions.SCHEDULE_TO_AGENT, {"schedule": "nightly"}
            ),
            schedule.by_default("nightly"),
        )

    def test_scheduled_run_instructions_apply_only_to_schedule_triggers(self):
        """A schedule is its own kind of asking rather than a variant of a person asking,
        so it reaches `SCHEDULE_TO_AGENT` *instead of* `USER_TO_AGENT` — the two person-only
        rules are not true of a run nobody is waiting in."""
        variables = {**AVA, "schedule": "nightly"}
        scheduled = instructions.build(
            variables=variables,
            trigger=instructions.SCHEDULE,
        )
        self.assertEqual("\n\n".join(
            instructions.render(one, variables).strip()
            for one in (instructions.CORE_INSTRUCTIONS, instructions.AGENT_IDENTITY,
                        instructions.SCHEDULE_TO_AGENT)), scheduled)
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
            variables={**AVA, "channel_kind": "discord", "user": "Tim"},
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
            **AVA, "channel_kind": "discord", "user": "Tim",
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
        self.assertTrue(built.startswith(instructions.CORE_INSTRUCTIONS))
        self.assertIn("# Rundesk agent operating rules", built)
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
        self.assertNotIn(instructions.AGENT_IDENTITY.split("\n")[0], built)
        for absent in ("MEMORY.md", "SOUL.md", "rundesk schedules", "rundesk messages",
                       "Operate Rundesk", "managing-rundesk"):
            self.assertNotIn(absent, built, absent)
        self.assertIn("on behalf of the named agent elena", built)
        self.assertIn("rol-1-aaaa", built)
        self.assertIn("/projects/exporter", built)

    def test_a_role_execution_is_never_told_which_files_a_home_keeps(self):
        """R-AGT-56, R-ROL-5 — naming the three files at the floor is what makes them
        unskippable for a named agent, and the same move is exactly what must not leak into
        an execution that has no home. One composer builds both now, so this is the guard on
        that separation being structural rather than incidental (R-ROL-5)."""
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
        for line in instructions.AGENT_IDENTITY.splitlines():
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
        self.assertTrue(built.startswith(instructions.CORE_INSTRUCTIONS))
        self.assertIn(
            instructions.render(instructions.AGENT_IDENTITY,
                                {"agent": "Ava"}).strip().splitlines()[0], built)
        self.assertLess(built.index("First message to a new owner"),
                        built.index("Owner addition."))
        self.assertNotIn("First message to a new owner",
                         instructions.build(variables={"agent": "Ava"}))

    def test_a_delegation_run_is_told_the_agent_that_handed_the_work_over(self):
        """R-DEL-6 — the one thing this agent cannot know for itself. Everything else it
        needs is its own, which is why the layer is this small."""
        variables = {**AVA, "caller_agent": "elena"}
        built = instructions.build(variables=variables,
                                   trigger=instructions.DELEGATION)
        self.assertIn(
            instructions.render(instructions.AGENT_TO_AGENT, variables).strip(),
            built)
        self.assertIn("elena, an agent on your team, handed you this task.", built)
        self.assertNotIn("{caller_agent}", built)

    def test_a_delegation_run_is_told_nobody_is_present_and_how_to_ask(self):
        """R-DEL-6 — a question is legal here and is not a wait.

        Measured on a live station against a real brain: told never to ask, the answering
        agent ended its report with two questions anyway. The rule now shapes the question
        instead of forbidding it — asked as the report, so the run ends and the agent that
        asked resumes it with the answer."""
        built = instructions.build(variables={**AVA, "caller_agent": "elena"},
                                   trigger=instructions.DELEGATION)
        self.assertIn("Not a person, not your owner, and nobody is present while you run.",
                      built)
        self.assertIn("A question is allowed and is never a wait.", built)
        self.assertIn("ask it as your report and stop — elena reads it and resumes you "
                      "with the answer.", built)
        self.assertIn("stop and report `blocked`", built)

    def test_a_delegation_run_is_told_its_answer_goes_to_no_channel(self):
        """R-DEL-5 — this turn happens in a conversation of its own, where nobody is
        reading. An agent that answered as though somebody were has answered nobody."""
        built = instructions.build(variables={**AVA, "caller_agent": "elena"},
                                   trigger=instructions.DELEGATION)
        self.assertIn("Only your last complete message reaches elena", built)
        self.assertIn("nothing goes to any channel or any person", built)

    def test_a_delegation_run_is_told_it_may_not_hand_the_work_on(self):
        """R-DEL-8, R-DEL-9 — said as well as refused. The durable refusal is what holds,
        and an agent that has to meet it to learn the rule has wasted a turn on it."""
        built = instructions.build(variables={**AVA, "caller_agent": "elena"},
                                   trigger=instructions.DELEGATION)
        self.assertIn("Do not hand this work on — no role, no other agent, and never back "
                      "to elena.", built)
        self.assertIn("Use your provider's own subagents within this task.", built)

    def test_a_delegation_run_keeps_another_owners_task_out_of_its_own_memory(self):
        """R-DEL-2 — the answering agent's memory is its own continuity, and this task is
        not its owner's. What it learns for itself still belongs there; what it did for
        somebody else's agent does not."""
        built = instructions.build(variables={**AVA, "caller_agent": "elena"},
                                   trigger=instructions.DELEGATION)
        self.assertIn("Write to `MEMORY.md` only what changes how you act for your own "
                      "owner.", built)
        self.assertIn("This task is elena's, not your continuity.", built)

    def test_a_delegation_run_still_receives_rundesks_own_standing_rules_first(self):
        """R-DEL-2 — the opposite of a role execution, and deliberately: this agent is
        itself, so its home, its memory and its skills are all still its own."""
        variables = {**AVA, "caller_agent": "elena"}
        built = instructions.build(variables=variables, trigger=instructions.DELEGATION)
        self.assertEqual("\n\n".join(
            instructions.render(one, variables).strip()
            for one in (instructions.CORE_INSTRUCTIONS, instructions.AGENT_IDENTITY,
                        instructions.AGENT_TO_AGENT)), built)
        self.assertIn("You are ava, an agent running inside rundesk.", built)
        for named in ("AGENTS.md", "SOUL.md", "MEMORY.md"):
            with self.subTest(home_file=named):
                self.assertIn(f"{AVA['agent_home']}/{named}", built)

    def test_a_delegation_run_is_given_no_rule_that_assumes_somebody_is_waiting(self):
        """R-DEL-6, R-DEL-9 — the two standing bullets that used to contradict this layer.

        One invites exactly the inference the layer forbids — work referred to that this
        turn has no record of — and the other offers the capability it refuses three
        paragraphs later. They belong to `USER_TO_AGENT` now, so this asserts the whole of
        that layer is absent rather than the two sentences somebody remembered."""
        variables = {**AVA, "caller_agent": "elena"}
        built = instructions.build(variables=variables, trigger=instructions.DELEGATION)
        for line in instructions.USER_TO_AGENT.splitlines():
            with self.subTest(line=line[:40]):
                self.assertNotIn(instructions.render(line, variables), built)
        self.assertNotIn("Referred to work you have no record of?", built)
        self.assertNotIn("goes to a role", built)


    def test_a_delegation_run_offered_no_roles_is_given_no_roles_heading(self):
        """R-DEL-9 — the layer forbids putting a role on one paragraph after the roles
        listing would have offered one.

        **The roles are supplied and still do not land**, which is the point: the composer
        leaves them out of `AGENT_TO_AGENT` structurally, so no caller has to remember to
        strip a variable and none can forget."""
        built = instructions.build(
            variables={**AVA, "caller_agent": "elena",
                       "roles": "- **research** (read) — Answer one question."},
            trigger=instructions.DELEGATION)
        self.assertNotIn("## Roles you may hand heavy work to", built)
        self.assertNotIn("- **research** (read)", built)
        self.assertNotIn("delegating-to-roles", built)

    def test_delegation_instructions_apply_only_to_delegation_triggers(self):
        variables = {**AVA, "caller_agent": "elena", "schedule": "nightly"}
        for trigger in ("", instructions.DIRECT, instructions.PUBLIC,
                        instructions.SCHEDULE, instructions.ONBOARDING):
            with self.subTest(trigger=trigger):
                built = instructions.build(variables=variables, trigger=trigger)
                self.assertNotIn("## Answering another agent", built)
                self.assertNotIn("handed you this task", built)

    def test_only_trigger_prompt_text_lives_in_this_module(self):
        for use_case in (
            "ATTACHMENTS", "INTERRUPTED_RECOVERY", "AFTER_EXTERNAL_UPDATE",
            "MID_TURN_STEERING", "ANTIGRAVITY_STANDING_WRAPPER",
        ):
            self.assertFalse(hasattr(instructions, use_case), use_case)


class TheLayersAndWhatEachIsTrueOf(unittest.TestCase):
    """The core layer, then exactly one layer naming who asked — and no turn reads a rule
    that is not true of it. `.knowledge/guides/instruction-layers.md` is the standard."""

    #: The four variables a role layer is filled with here, in one place: every case below
    #: builds the same execution, so what differs between them is what is being asked.
    ROLE = {"role": "Development", "parent_agent": "elena", "role_run": "rol-1-aaaa",
            "target": "/projects/exporter",
            "workspace": "/agents/elena/role-runs/rol-1-aaaa/home/workspace"}

    def test_the_core_layer_carries_no_identity(self):
        """The single rule the whole shape rests on. A role execution reads `CORE`, so a
        variable naming an agent, a home or a workspace in it is handed straight to one —
        which is the leak R-ROL-5 exists to prevent, arriving by the new route."""
        for named in instructions.STANDARD_VARIABLES:
            with self.subTest(variable=named):
                self.assertNotIn("{" + named + "}", instructions.CORE_INSTRUCTIONS)
        for named in instructions.ROLE_VARIABLES:
            with self.subTest(variable=named):
                self.assertNotIn("{" + named + "}", instructions.CORE_INSTRUCTIONS)

    def test_a_role_execution_names_no_home_no_memory_no_channel_and_no_rundesk_command(self):
        """R-ROL-5 — the one test the whole change rests on.

        `build` composes a role execution now, where two orders were written apart on
        purpose so that one could not become the other with layers removed. What makes the
        single composer safe is that there is nothing left to remove: the core carries no
        identity, and a role reaches its own layer *instead of* the agent one rather than by
        stripping it. Asserted by searching the built string for each thing that must not be
        there, never by reading the composition back."""
        built = instructions.for_role(variables={**AVA, **self.ROLE,
                                                 "roles": "- **research** (read)"},
                                      rules="# Development\n\nRun the tests.\n")
        for absent in (
            # A home, and the three files one keeps.
            "/agents/ava/home", "persistent home", "AGENTS.md", "SOUL.md", "MEMORY.md",
            # A voice, and an attachment.
            "voice", "rundesk-attach", "attached",
            # A role of its own to put on.
            "## Roles you may hand heavy work to", "delegating-to-roles",
            # Any `rundesk` command at all.
            "rundesk ", "rundesk`", "managing-rundesk",
        ):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, built)
        # A channel and a schedule, asserted as whole layers rather than as the words:
        # the floor *forbids* operating either, and has to name them to do it, so a bare
        # search for "channel" would fail on the very sentence that protects this.
        for layer in (instructions.DIRECT_MESSAGE, instructions.PUBLIC_ROOM,
                      instructions.SCHEDULE_TO_AGENT, instructions.USER_TO_AGENT,
                      instructions.AGENT_TO_AGENT, instructions.ONBOARDING_INSTRUCTIONS):
            with self.subTest(layer=layer.splitlines()[0][:40]):
                self.assertNotIn(instructions.render(layer, {**AVA, **self.ROLE}), built)
        # Still everything a role execution *is* told, so this is not passing by emptiness.
        self.assertIn("on behalf of the named agent elena", built)
        self.assertIn("rol-1-aaaa", built)
        self.assertIn("Run the tests.", built)

    def test_a_role_execution_reads_its_own_rules_between_the_floor_and_the_task(self):
        """R-ROL-10 — the order that must survive one composer. A role given its own rules
        after the task details, or with a substitution made in them, is a different run from
        the one that was admitted."""
        built = instructions.for_role(
            variables=self.ROLE, rules="# Mine\n\nKeep {agent_home} and {role} literally.")
        self.assertLess(built.index(instructions.CORE_INSTRUCTIONS.splitlines()[0]),
                        built.index("# Role execution"))
        self.assertLess(built.index("# Role execution"), built.index("# Mine"))
        self.assertLess(built.index("# Mine"), built.index("## This execution"))
        self.assertIn("Keep {agent_home} and {role} literally.", built)

    def test_the_agent_identity_is_written_once_and_composed_into_the_three(self):
        """A list written twice is a list that disagrees with itself, and this one is long.
        The three layers that are a named agent share one fragment; the fourth has none."""
        variables = {**AVA, "caller_agent": "elena", "schedule": "nightly"}
        for trigger in ("", instructions.DIRECT, instructions.PUBLIC,
                        instructions.SCHEDULE, instructions.DELEGATION):
            with self.subTest(trigger=trigger or "none"):
                self.assertIn(instructions.render(instructions.AGENT_IDENTITY, variables),
                              instructions.build(variables=variables, trigger=trigger))
        self.assertNotIn(
            instructions.render(instructions.AGENT_IDENTITY, variables),
            instructions.build(variables={**variables, **self.ROLE},
                               trigger=instructions.ROLE))

    def test_a_surface_this_release_never_heard_of_is_a_person_asking(self):
        """The safe way round. What the other layers withhold are the rules that assume
        somebody is waiting, so a trigger nobody classified is given a person's rules and
        one of the others only by being named — never the other way about."""
        variables = {**AVA, "schedule": "nightly", "caller_agent": "elena"}
        for trigger in ("", "some_new_adapter", instructions.DIRECT,
                        instructions.PUBLIC, instructions.ONBOARDING):
            with self.subTest(trigger=trigger or "none"):
                self.assertIn(instructions.render(instructions.USER_TO_AGENT, variables),
                              instructions.build(variables=variables, trigger=trigger))
        for trigger in (instructions.DELEGATION, instructions.SCHEDULE, instructions.ROLE):
            with self.subTest(withheld_from=trigger):
                self.assertNotIn(
                    instructions.render(instructions.USER_TO_AGENT, variables),
                    instructions.build(variables={**variables, **self.ROLE},
                                       trigger=trigger))

    def test_no_turn_anybody_asked_to_leave_alone_reads_a_different_word(self):
        """The acceptance check for the whole restructure, and the reason the expectation is
        a committed capture rather than anything this module can produce.

        Every preface was captured before the layers were named. Each is rebuilt here, and
        the *only* differences allowed are the two the owner asked for: `CORE_INSTRUCTIONS`
        in front, and the two person-only bullets moved out of the shared agent fragment. So
        each new preface is turned back into the old one by undoing exactly those two, and
        compared whole — anything else that moved fails, wherever it moved to.

        A test that assembled its own expectation out of today's constants would agree with
        any change at all, which is precisely the failure this guards against."""
        variables, built = BEFORE["variables"], BEFORE["built"]
        person_only = instructions.render(instructions.USER_TO_AGENT, variables)
        core = instructions.render(instructions.CORE_INSTRUCTIONS, variables)
        for trigger, key, person in (("", "no_trigger", True),
                                     (instructions.DIRECT, "direct_message", True),
                                     (instructions.PUBLIC, "public_room", True),
                                     (instructions.SCHEDULE, "schedule", False),
                                     (instructions.ONBOARDING, "onboarding", True)):
            with self.subTest(trigger=trigger or "none"):
                now = instructions.build(
                    variables=variables, trigger=trigger,
                    append=tuple(BEFORE["append"]) if key != "no_trigger" else ())
                # Undo the core layer, then put the two bullets back where they were.
                self.assertTrue(now.startswith(f"{core}\n\n"))
                was = now[len(core) + 2:].replace(f"\n\n{person_only}", "")
                if person:
                    self.assertIn(person_only, now, "the person-only rules went missing")
                was = was.replace(
                    "- Home and workspace roots are not Git",
                    f"{person_only}\n- Home and workspace roots are not Git")
                self.assertEqual(built[key], was)
        # A role execution gains the core layer and nothing else at all.
        role = instructions.for_role(variables=BEFORE["role_variables"],
                                     rules=BEFORE["role_rules"])
        self.assertEqual(built["role_execution"], role[len(core) + 2:])


if __name__ == "__main__":
    unittest.main()
