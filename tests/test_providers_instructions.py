"""The structure and deterministic composition of the instructions a brain receives.

Run directly: `python3 tests/test_providers_instructions.py`
"""

import hashlib
import shlex
import unittest

import support
from rundesk.providers import instructions, team

EVERYTHING = {
    "agent_name": "ava",
    "agent_home": "/agents/ava/home",
    "install_root": "/rundesk/root",
    "provider_name": "a-stand-in",
    "access_mode": "work",
    "schedule_name": "nightly",
    "conversation_id": "7",
    "caller_agent": "bob",
    "source_kind": "terminal",
    "audience_id": "ava",
    "skill_names": "managing-rundesk, writing-plans",
}

#: Every situation the module defines, discovered by the shape of a situation block rather than
#: listed here. A listing is a second place to keep in step: a fourth block would be composed by
#: `build` and skipped by every universal case below, which is a gap that reports green.
#: `TheSituationsUnderTest` fails when this discovers nothing, because a loop over nothing passes.
EVERY_SITUATION = tuple(
    block for _, block in sorted(vars(instructions).items())
    if isinstance(block, str) and block.startswith("## Current Situation"))


class TheSituationsUnderTest(support.Isolated):
    """The set every universal case loops over, and the proof that it found anything."""

    def test_discovery_finds_the_situation_blocks_the_module_defines(self):
        # An empty discovery turns every loop over it into a green no-op, so the empty case fails
        # once here instead of silently weakening each universal boundary.
        self.assertTrue(EVERY_SITUATION, "no situation blocks were discovered")
        for named in (instructions.USER_TO_AGENT, instructions.SCHEDULE_TO_AGENT,
                      instructions.AGENT_TO_AGENT):
            with self.subTest(situation=named[:32]):
                self.assertIn(named, EVERY_SITUATION)
        self.assertEqual(len(set(EVERY_SITUATION)), len(EVERY_SITUATION))


class TheAgreedSections(support.Isolated):
    ALWAYS = ("# Rundesk", "## Agent Context", "## Current Situation",
              "## Establish the Outcome", "## Boundaries", "## Execute the Work",
              "## Outcome and Continuity")

    def built(self, situation=instructions.USER_TO_AGENT, team_text=""):
        return instructions.build(situation=situation, variables=EVERYTHING, team=team_text)

    def part(self, text, heading):
        """One section's body, whitespace-normalized and folded.

        Scoped because a term proves the rule sits in the section that owns it, and normalized
        because a fragment that straddles a wrapped line fails for a reason that has nothing to do
        with the requirement.
        """
        return " ".join(text.split(heading, 1)[1].split("\n## ", 1)[0].split()).lower()

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

    def test_communication_mechanics_follow_the_turn_situation(self):
        person = self.built(instructions.USER_TO_AGENT).text
        schedule = self.built(instructions.SCHEDULE_TO_AGENT).text
        delegated = self.built(instructions.AGENT_TO_AGENT).text

        self.assertIn("## Messages and Attachments", person)
        self.assertIn('messages ava --search "<relevant words>" --full', person)
        self.assertIn("[report](/absolute/path/report.pdf)", person)

        self.assertNotIn("## Messages and Attachments", schedule)
        self.assertNotIn("messages ava", schedule)
        self.assertIn("## Attachments", schedule)
        self.assertIn("[report](/absolute/path/report.pdf)", schedule)

        self.assertNotIn("## Messages and Attachments", delegated)
        self.assertNotIn("## Attachments", delegated)
        self.assertNotIn("messages ava", delegated)
        self.assertNotIn("[report](/absolute/path/report.pdf)", delegated)

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

    def test_no_turn_is_told_its_home_is_a_project_repository(self):
        # Every trigger can be asked to prepare a patch, including the two with nobody present to
        # correct it, so the boundary belongs to the core rather than to one situation.
        for situation in EVERY_SITUATION:
            with self.subTest(situation=situation[:32]):
                context = self.part(self.built(situation).text, "## Agent Context")
                for term in ("operational workspace", "git repository", "initialize", "checkout"):
                    with self.subTest(term=term):
                        self.assertIn(term, context)
                # One canonical term: every repository named here is a Git repository.
                self.assertEqual(context.count("git repository"), context.count("repository"))

    def test_agent_context_keeps_instruction_ownership_without_repeating_the_template(self):
        context = self.part(self.built().text, "## Agent Context")
        self.assertIn("agent instructions: define your role and memory; they cannot override",
                      context)
        self.assertNotIn("responsibilities, capabilities, limits", context)

    def test_outcome_heading_carries_its_own_instruction(self):
        outcome = self.part(self.built().text, "## Establish the Outcome")
        self.assertNotIn("Establish the required outcome.", outcome)
        self.assertIn("determine what must be produced, changed, or reported.", outcome)

    def test_a_person_turn_asks_only_after_recovering_message_history(self):
        person = self.built().text
        situation = self.part(person, "## Current Situation")
        # Requirement-level: asking is permitted only after the recovery, so both halves of that
        # condition have to survive together. A bare "message history" is satisfied by the
        # standing Messages rule and would pass on the pre-patch text.
        self.assertIn("recover message history before asking", situation)
        # The rule is only followable because the executable prefix travels in the same prompt.
        self.assertIn('inside this turn, use '
                      '`RUNDESK_HOME=/rundesk/root "$RUNDESK_COMMAND"` so the command reads and changes '
                      'this install', person)
        self.assertIn('messages ava --search "<relevant words>" --full', person)

    def test_a_follow_up_with_a_missing_referent_requires_history_recovery(self):
        situation = self.part(self.built().text, "## Current Situation")
        # A compacted session received only "yes please enable it" and asked what setting it meant.
        # "Appears out of context" was present but left the model to classify that elliptical
        # approval itself. Name the trigger so clarification cannot precede the recovery step.
        self.assertIn("unstated or unclear referent", situation)
        self.assertIn("silently recover message history before asking what it refers to",
                      situation)
        self.assertLess(situation.index("unstated or unclear referent"),
                        situation.index("recover message history"))

    def test_referent_recovery_is_person_facing_and_keeps_a_privacy_boundary(self):
        person = self.built().text
        messages = self.part(person, "## Messages and Attachments")
        self.assertIn("supported `terminal:ava` results", messages)
        self.assertIn("another agent/audience", messages)
        for other in (instructions.SCHEDULE_TO_AGENT, instructions.AGENT_TO_AGENT):
            with self.subTest(situation=other[:32]):
                self.assertNotIn("unstated or unclear referent",
                                 self.part(self.built(other).text, "## Current Situation"))

    def test_context_recovery_cannot_bypass_supported_audience_records(self):
        messages = self.part(self.built().text, "## Messages and Attachments")
        # A Grok no-history control inspected another fixture agent and its raw conversation after
        # the supported current-audience search returned only the ambiguous follow-up.
        for clause in ('if none, list recent with `messages ava --full`',
                       "still unresolved: clarify or report it",
                       "never inspect conversation files/records",
                       "infer from another agent/audience"):
            with self.subTest(clause=clause):
                self.assertIn(clause, messages)

    def test_clarification_remains_available_when_recovery_cannot_unblock_progress(self):
        situation = self.part(self.built().text, "## Current Situation")
        self.assertIn("clarify only if missing context, scope, authority, or an unresolved decision "
                      "still blocks progress", situation)

    def test_a_stated_change_is_an_instruction_rather_than_a_proposal(self):
        person = self.built().text
        situation = self.part(person, "## Current Situation")
        # Requirement-level: the bare words appear in the pre-patch situation, so each fragment
        # carries the clause it proves.
        for term in ("is your instruction to make it", "within the current scope",
                     "do not merely agree, propose it"):
            with self.subTest(term=term):
                self.assertIn(term, situation)
        # Bounded by the standing scope rule, not widened by a person being there.
        self.assertIn("scope and authority", self.part(person, "## Boundaries"))
        for other in (instructions.SCHEDULE_TO_AGENT, instructions.AGENT_TO_AGENT):
            with self.subTest(situation=other[:32]):
                self.assertNotIn("is your instruction to make it",
                                 self.part(self.built(other).text, "## Current Situation"))

    def test_a_background_process_is_not_a_continuation_path(self):
        # A turn that ends on a running child reports an answer nobody will read: nothing survives
        # settlement to deliver it. It is in the universal rules because every situation can start
        # one, including the two with nobody present to notice the result never arrived.
        for situation in EVERY_SITUATION:
            with self.subTest(situation=situation[:32]):
                continuity = self.part(self.built(situation).text, "## Outcome and Continuity")
                for term in ("background command", "tool session", "monitor", "child process",
                             "not a continuation path", "collect", "blocker",
                             "long-running service"):
                    with self.subTest(term=term):
                        self.assertIn(term, continuity)

    def test_a_person_turn_keeps_routine_internal_recovery_silent(self):
        person = self.built().text
        situation = self.part(person, "## Current Situation")
        # Requirement-level: "memory" and "status" are ordinary words the prompt already uses, so
        # each fragment carries the clause it proves — what is silent, and what still gets said.
        for term in ("routine internal context recovery",
                     "memory, task state, instructions, and prior messages",
                     "silent work", "do not narrate it or report it as progress",
                     "asks for status", "material progress or a result affects them",
                     "blocker, risk, or decision"):
            with self.subTest(term=term):
                self.assertIn(term, situation)
        # Skills are deliberately not silenced: an assignment or a project's rules routinely
        # require stating which guidance governed the work.
        self.assertNotIn("skills", situation)
        # A default, not a gag. Without this clause the rule reads as outranking the instruction
        # that outranks it, which is how a silent default becomes a withheld announcement.
        self.assertIn("never withholds an announcement a higher-priority applicable instruction "
                      "requires", situation)
        # Silence is a person's rule. A schedule's standalone report and a handback to a calling
        # agent are read by somebody who has to verify the work, and neither of those is narration.
        for other in (instructions.SCHEDULE_TO_AGENT, instructions.AGENT_TO_AGENT):
            with self.subTest(situation=other[:32]):
                self.assertNotIn("silent work",
                                 self.part(self.built(other).text, "## Current Situation"))

    def test_no_work_is_reported_complete_before_its_outcome_is_verified(self):
        # Every trigger can take an action whose proof arrives later, including the two with nobody
        # present to notice that the start was reported as the finish, so the gate is universal
        # rather than person-facing.
        for situation in EVERY_SITUATION:
            with self.subTest(situation=situation[:32]):
                done = " ".join(self.part(self.built(situation).text,
                                           "## Outcome and Continuity").split()).lower()
                # Whole clauses, because the relationship is the requirement: separate fragments
                # survive a text that says a started process proves the work, or that a report may
                # stop at what happened. Each of those reversals has to fail here.
                for clause in ("report completion only when",
                               "an accepted command or started process is progress, not proof",
                               "while verification remains, state what happened and what remains "
                               "to check"):
                    with self.subTest(clause=clause):
                        self.assertIn(clause, done)
                # It is about work, not about the one shape of work that made it obvious. A rule
                # narrowed back to rollouts leaves every other unverified claim permitted.
                self.assertNotIn("rollout", done)

    def test_every_turn_must_load_every_applicable_skill_body_before_acting(self):
        # A granted skill and a loaded skill look identical from inside a turn: both arrive as a
        # name and a description. This proves the prompt asks for the load. Nothing here can prove
        # a turn performed it, and no release records what a turn loaded.
        for situation in EVERY_SITUATION:
            with self.subTest(situation=situation[:32]):
                doing = self.part(self.built(situation).text, "## Execute the Work")
                # Requirement-level: "reference", "granted" and "loaded" are ordinary words that
                # a neighbouring bullet can satisfy, so each fragment carries its own clause.
                for term in ("the available skill descriptions",
                             "every reference that body requires",
                             "granted is not a skill that is loaded",
                             "cannot be loaded, stop and report that as a blocker"):
                    with self.subTest(term=term):
                        self.assertIn(term, doing)
                # Whole clauses, because these are relationships rather than words. A text that
                # skims the project's rules, asks for some applicable skills, drops the exclusion,
                # or asks a turn to reload what it already read satisfies every fragment of them
                # separately.
                for clause in ("read the applicable project rules in full",
                               "identify every skill applicable to this request and project, and "
                               "no others",
                               "load each applicable skill body",
                               "before any other substantive action",
                               "one already loaded in this session is not loaded again"):
                    with self.subTest(clause=clause):
                        self.assertIn(clause, doing)
                # The sequence is the requirement. The project's rules decide which skills apply,
                # so a turn that chooses them first chooses from half the evidence; and a turn
                # that starts inspecting or changing anything first has already done the work the
                # bodies were meant to govern. Each rule can be present in the wrong place, so the
                # positions are asserted rather than the words alone.
                self.assertLess(doing.index("read the applicable project rules in full"),
                                doing.index("identify every skill applicable"))
                self.assertLess(doing.index("identify every skill applicable"),
                                doing.index("load each applicable skill body"))
                self.assertLess(doing.index("load each applicable skill body"),
                                doing.index("inspect relevant"))
        # It says when and what, never how: skill bodies stay provider-native.
        self.assertNotIn("SKILL.md", self.built().text)

    def test_the_projects_own_rules_are_the_first_project_access(self):
        # "Before substantive action" was followed as "before changing anything": turns listed the
        # tree, opened task files and loaded project skills, and only then read the rules that
        # decide which skills apply. The clause has to name the access itself and everything it
        # precedes, because a text naming only the file is satisfied by reading it second.
        for situation in EVERY_SITUATION:
            with self.subTest(situation=situation[:32]):
                doing = self.part(self.built(situation).text, "## Execute the Work")
                self.assertIn("your first project access", doing)
                # One whole clause: "listing", "plan" and "change" are ordinary words, and
                # "change" is already a substring of the neighbouring "changing anything".
                self.assertIn("before any other project file, listing, metadata, skill load, "
                              "plan, inspection, change, or verification", doing)
                # Recovering the agent's own context is not project access, or every turn that
                # reads its memory first has broken the rule it was just given.
                self.assertIn("your agent home is not project access", doing)
                # It governs the access, not only the selection that follows it.
                self.assertLess(doing.index("first project access"),
                                doing.index("identify every skill applicable"))

    def test_file_access_alone_does_not_trigger_a_development_skill(self):
        # "And no others" sits beside a positive duty and was read as advice: a granted
        # development workflow was opened because the turn had read one file on the machine.
        # What the rule denies is that trigger, not the possibility — a standalone development
        # task outside any repository can still need the skill it names — so the clause is about
        # file access rather than about a category of work that may never load one.
        for situation in EVERY_SITUATION:
            with self.subTest(situation=situation[:32]):
                doing = self.part(self.built(situation).text, "## Execute the Work")
                for clause in ("leave an unrelated grant unloaded",
                               "non-project work has no project rules",
                               "file access alone does not trigger a development skill"):
                    with self.subTest(clause=clause):
                        self.assertIn(clause, doing)


class DelegationRouting(support.Isolated):
    def built(self):
        return instructions.build(
            variables=EVERYTHING,
            team="- forge — implements code\n- trace — reviews risky changes\n- vera — runs QA",
        ).text

    def test_it_names_positive_signals_for_considering_delegation(self):
        text = self.built()
        self.assertIn("stated responsibility makes them materially better suited", text)
        self.assertIn("one bounded outcome", text)
        self.assertIn("coordination is proportionate", text)
        for signal in ("Independent expertise", "parallel work", "required review"):
            with self.subTest(signal=signal):
                self.assertIn(signal, text)

    def test_it_names_when_direct_work_is_better(self):
        text = self.built()
        self.assertIn("Work directly for ordinary conversation", text)
        self.assertIn("simple documentation, formatting, or copy-only changes", text)
        self.assertIn("task is small or mechanical", text)
        self.assertIn("needs your continuing ownership", text)
        self.assertIn("coordination would add more cost than value", text)
        self.assertIn("Availability or skill names alone do not justify delegation", text)

    def test_it_routes_delegation_procedure_to_the_skill(self):
        text = self.built()
        self.assertIn("Apply these signals before loading delegation guidance", text)
        self.assertIn("Do not load `delegating-work` merely because a team member is available", text)
        self.assertIn("When named delegation is a genuine option, that skill is applicable", text)
        self.assertIn("load its body before choosing a target or acting", text)
        self.assertIn("It owns target selection, briefing, the asynchronous lifecycle, steering, "
                      "resuming, and return review", text)
        self.assertNotIn('`"$RUNDESK_COMMAND" ask <agent>', text)
        for repeated in ("Simple documentation or copy work", "Small coding work",
                         "Large, complex, or high-risk work", "include scope, authority"):
            with self.subTest(repeated=repeated):
                self.assertNotIn(repeated, text)


class SmallestSufficientChange(support.Isolated):
    def test_every_turn_defines_the_smallest_sufficient_change_before_editing(self):
        for situation in EVERY_SITUATION:
            with self.subTest(situation=situation[:32]):
                text = instructions.build(situation=situation, variables=EVERYTHING).text
                self.assertIn("define the smallest sufficient change", text)
                self.assertIn("requested result and required proof", text)
                self.assertIn("safe and effective", text)

    def test_every_turn_forbids_unrequested_refactoring_and_scope_expansion(self):
        for situation in EVERY_SITUATION:
            with self.subTest(situation=situation[:32]):
                text = instructions.build(situation=situation, variables=EVERYTHING).text
                self.assertIn("Make only that change", text)
                self.assertIn("Never refactor, clean up, redesign, or expand it", text)
                self.assertIn("unless the requester asks", text)

    def test_every_turn_stops_when_the_requested_result_and_proof_are_complete(self):
        for situation in EVERY_SITUATION:
            with self.subTest(situation=situation[:32]):
                text = instructions.build(situation=situation, variables=EVERYTHING).text
                self.assertIn("stop when the requested result and proof are complete", text)

    def test_every_turn_cannot_end_without_delivery_or_a_continuation_path(self):
        for situation in EVERY_SITUATION:
            with self.subTest(situation=situation[:32]):
                text = instructions.build(situation=situation, variables=EVERYTHING).text
                continuity = " ".join(
                    text.split("## Outcome and Continuity", 1)[1].split("\n## ", 1)[0].split()
                ).lower()
                self.assertIn("deliver and verify the outcome", continuity)
                self.assertIn("report a blocker with a real continuation path", continuity)
                self.assertIn("never report pending work as complete", continuity)

    def test_broader_scope_requires_approval_with_impact(self):
        for situation in EVERY_SITUATION:
            with self.subTest(situation=situation[:32]):
                text = instructions.build(situation=situation, variables=EVERYTHING).text
                self.assertIn("stop and ask for explicit approval", text)
                self.assertIn("why, the proposed expansion, and its impact", text)


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
        self.assertEqual(len(EVERY_SITUATION), len(fingerprints))

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
    def test_the_prompt_names_the_install_root_for_provider_tool_shells(self):
        built = instructions.build(variables=EVERYTHING).text
        self.assertIn("Use `rundesk ...` when giving a person a command", built)
        self.assertIn('inside this turn, use '
                      '`RUNDESK_HOME=/rundesk/root "$RUNDESK_COMMAND"` so the command reads and changes '
                      'this install', built)
        self.assertNotIn("installed launcher selects", built)
        self.assertEqual(built.count('RUNDESK_HOME=/rundesk/root "$RUNDESK_COMMAND"'), 1)

    def test_the_prompt_shell_quotes_every_install_root_as_one_assignment(self):
        root = "/tmp/a root/with 'quotes' and $(touch nope)"
        built = instructions.build(
            variables={**EVERYTHING, "install_root": root},
        ).text
        assignment = f"RUNDESK_HOME={shlex.quote(root)}"
        self.assertIn(f'`{assignment} "$RUNDESK_COMMAND"`', built)
        self.assertEqual(f"RUNDESK_HOME={root}", shlex.split(assignment)[0])

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

    def test_static_layers_and_the_largest_required_stack_stay_bounded(self):
        ceilings = {
            "core": (instructions.CORE, 650),
            "rules": (instructions.OPERATING_RULES, 2300),
            "person": (instructions.USER_TO_AGENT, 1700),
            "schedule": (instructions.SCHEDULE_TO_AGENT, 700),
            "agent": (instructions.AGENT_TO_AGENT, 800),
            "team": (instructions.TEAM_MEMBERS, 1000),
            "completion": (instructions.OUTCOME_AND_CONTINUITY, 1400),
        }
        for name, (text, ceiling) in ceilings.items():
            with self.subTest(name=name):
                self.assertLessEqual(len(text.encode("utf-8")), ceiling)
        # The required stack at its largest: every discovered situation, each at the largest team
        # listing a caller can supply, so the ceiling is the worst case this release composes on
        # its own rather than the one situation a case happened to name. A situation added
        # oversized fails here instead of arriving unmeasured.
        #
        # **Optional additions are outside this number**, and deliberately: how many a caller
        # supplies is that caller's decision, not this module's. Each one is bounded where it comes
        # in, which `test_each_addition_is_bounded_without_clipping_later_layers` proves.
        largest_required = max(instructions.build(situation=situation, variables=EVERYTHING,
                                                  team="x" * team.TEAM_BYTES_AT_MOST).total_bytes
                               for situation in EVERY_SITUATION)
        # The proportionate-delegation rules add a small fixed cost to person-facing turns so they
        # avoid much larger unnecessary specialist contexts. The other two situations get no team
        # layer and therefore pay nothing for rules they cannot use.
        self.assertLessEqual(largest_required, 13100)


if __name__ == "__main__":
    unittest.main()
