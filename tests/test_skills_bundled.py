"""The skills rundesk ships, held to the rules they teach.

Two things are checked here and the second is the one that matters. Every shipped skill has to be a
skill every brain will load — which is what the library already enforces for anybody else's catalog,
and there is no reason ours should be exempt. And **no shipped skill may name a verb this build does
not have**: `AGENTS.md` forbids offering an operation that is not built, and a skill is the one place
that rule can be broken without any command going wrong. It is read by an agent, on every turn, and
what it teaches is acted on.

The build this replaces shipped skills for roles and schedules long after both worked, which was
fine — and shipped a skill teaching an invocation path nothing set, which was not.

Run directly: `python3 tests/test_skills_bundled.py`
"""

import argparse
import re
import shutil
import unittest

import support
from rundesk import cli
from rundesk.skills import catalogs, library, needs

#: Where a skill really tells somebody to type something: a fenced block, or an inline code span.
#: Prose is deliberately not read — "rundesk is the thing running you" names no verb, and a check
#: that took it for one is a check nobody can keep green and everybody learns to work around.
_FENCED = re.compile(r"^```.*?^```", re.M | re.S)
_INLINE = re.compile(r"`([^`\n]+)`")

#: A verb, at the start of what somebody would type — spelled either way a skill may write it.
#:
#: **`"$RUNDESK_COMMAND"` is read too, and leaving it out would be this check going quietly blind.**
#: A skill that tells an agent to type the reachable form is telling it to type a verb, and a pattern
#: that only knew the bare word would go on passing while every command in the skill went unchecked —
#: which is this guard's own documented failure mode, arrived at by adding a spelling rather than by
#: removing a rule.
_TYPED = re.compile(r'^(?:rundesk|"\$RUNDESK_COMMAND") (--?[a-z][a-z-]*|[a-z][a-z-]*)', re.M)


def verbs_named(said: str):
    """Every `rundesk <verb>` this text tells somebody to type, in the order they appear.

    Read out of code only. A skill is prose with commands in it, and the two have to be told apart
    by something other than hope — this product's own name appears in ordinary sentences all through
    the skills that are about it.
    """
    found = []
    for block in _FENCED.findall(said):
        found.extend(_TYPED.findall(block))
    for span in _INLINE.findall(_FENCED.sub("", said)):
        found.extend(_TYPED.findall(span))
    return found


def verbs_of(parser: argparse.ArgumentParser):
    """Every verb this build really has, read off the parser rather than listed here.

    Read off the command so that a skill naming something that has just landed passes the day it
    lands, and a skill naming something that has just been taken away fails the same day. A list
    kept here is a list that disagrees with the product.
    """
    found = set()
    for action in parser._actions:
        if isinstance(action, cli.Subcommands):
            found.update(action.choices)
        for one in action.option_strings:
            found.add(one)
    return found


class Bundled(support.Isolated):
    """The skills standing in this release, and the catalog they are installed as."""

    def setUp(self) -> None:
        super().setUp()
        # **Not skipped when they are missing.** They are a shipped asset beside `src/providers/`,
        # which nothing skips over, so a release that lost them goes red here rather than green with
        # a skip nobody reads — `OK` and `OK (skipped=14)` are the same word in a summary.
        library.where().mkdir(parents=True, exist_ok=True)
        # The catalog the release ships: its manifest, and one directory per skill beside it.
        # Not the shape it is installed in — `place_bundled` puts the skills a level down, into the
        # `skills/` a catalog on disk keeps them in.
        self.skills = catalogs.shipped()

    def named(self):
        """Every skill this release ships, in name order."""
        return sorted(one.name for one in self.skills.iterdir()
                      if (one / library.DECLARED).is_file())


class WhatIsShipped(Bundled):
    def test_there_is_something_to_check(self):
        # A check that discovers its own work fails when it discovers none: a walk pointed at a
        # directory that had moved would otherwise pass having read nothing.
        self.assertTrue(self.named(), f"no skills found under {self.skills}")

    def test_the_manifest_is_one_this_release_can_read(self):
        # It stands beside the skills it describes, and is read by the same reader every published
        # catalog's is — so a manifest this release would refuse from anybody else is one it refuses
        # from itself, here, rather than on somebody's machine.
        manifest = library.read_manifest(self.skills)
        self.assertEqual(library.BUNDLED, manifest.name)
        self.assertEqual(library.SCHEMA, manifest.schema)

    def test_it_holds_only_what_is_coupled_to_this_version(self):
        # The reason this catalog exists at all. A skill about writing pull requests does not change
        # when rundesk does, so shipping it here would tie a correction to it to a rundesk release —
        # it belongs in the catalog that is fetched. Everything here is about *this* rundesk.
        self.assertEqual(["delegating-work", "managing-rundesk", "writing-skills"], self.named())

    def test_it_holds_the_skill_every_agent_is_required_to_have(self):
        # **This release must not ship a floor it does not satisfy.** Every agent is given
        # `library.REQUIRED` when it is made and again on every update; a release whose own catalog
        # stopped holding it would strip the grant from every agent, quietly, and the reconciliation
        # is deliberately silent about a skill it cannot find — because the alternative is every
        # `rundesk update` on that release reporting a failure nobody can repair. This is where that
        # is caught instead: once, before the release is cut.
        self.assertIn(library.REQUIRED_SKILL, self.named())

    def test_every_shipped_skill_is_one_a_brain_would_load(self):
        # The same check any other catalog is held to on the way in. Ours is not exempt, and the
        # cost of it being wrong is higher: it is on every machine.
        for name in self.named():
            with self.subTest(skill=name):
                self.assertEqual("", library.trouble_with(self.skills / name))

    def test_every_shipped_skill_declares_its_credentials_readably(self):
        for name in self.named():
            with self.subTest(skill=name):
                self.assertEqual("", needs.trouble_with(self.skills / name))

    def test_every_command_a_shipped_skill_ships_can_be_run(self):
        # A script that is present and not executable looks exactly like one that works, right up
        # until something tries — and this one would be shipped that way to every machine.
        for name in self.named():
            for one in needs.ships(self.skills / name):
                with self.subTest(skill=name, script=one.shown):
                    self.assertTrue(one.runnable, f"{name}/{one.shown} is not executable")

    def test_the_whole_catalog_installs(self):
        # Driven through the real install rather than checked file by file, because that is what
        # every machine does with it and it is the check that would have caught a catalog whose
        # parts are each fine.
        self.assertTrue(catalogs.place_bundled())
        self.assertIn(library.BUNDLED, library.known())
        self.assertTrue(library.held(library.BUNDLED))

    def test_a_skill_edited_in_place_is_put_back_by_the_sweep_every_install_and_update_runs(self):
        # **Through `refresh`, which is the one path both `rundesk install` and `rundesk update`
        # take**, rather than through `place_bundled` on its own. The case below drives the direct
        # call and would stay green if the sweep stopped calling it — which is the way this
        # guarantee would really be lost, because nobody invokes `place_bundled` by hand.
        catalogs.refresh()
        drifted = (library.tree(library.BUNDLED) / library.INSIDE / "managing-rundesk"
                   / library.DECLARED)
        was = drifted.read_text(encoding="utf-8")
        drifted.write_text("---\nname: managing-rundesk\ndescription: edited\n---\n",
                           encoding="utf-8")
        # A skill somebody deleted outright is put back too: the whole tree is replaced, so what is
        # standing afterwards is what the release ships and not what was left of it.
        gone = library.tree(library.BUNDLED) / library.INSIDE / "writing-skills"
        shutil.rmtree(gone)

        catalogs.refresh()

        self.assertEqual(was, drifted.read_text(encoding="utf-8"))
        self.assertTrue((gone / library.DECLARED).is_file())
        self.assertEqual(self.named(), library.found(library.inside(library.BUNDLED)))

    def test_it_is_replaced_out_of_the_release_rather_than_left_as_it_was(self):
        # Version-coupled: an install that moved forward and kept the previous release's copy would
        # be handing every agent instructions for a rundesk it is no longer running.
        catalogs.place_bundled()
        drifted = (library.tree(library.BUNDLED) / library.INSIDE / "managing-rundesk"
                   / library.DECLARED)
        was = drifted.read_text(encoding="utf-8")
        drifted.write_text("---\nname: managing-rundesk\ndescription: edited\n---\n",
                           encoding="utf-8")
        self.assertFalse(catalogs.place_bundled())
        self.assertEqual(was, drifted.read_text(encoding="utf-8"))

    def test_it_is_never_fetched_from_anywhere(self):
        catalogs.place_bundled()
        self.assertFalse(catalogs.may_be_fetched(library.BUNDLED))

    def test_neither_dependency_may_be_removed(self):
        for name in (library.BUNDLED, library.DEPENDED):
            with self.subTest(catalog=name):
                self.assertFalse(catalogs.may_be_removed(name))
                self.assertNotEqual("", catalogs.what_stays(name))


class WhatAShippedSkillMayClaim(Bundled):
    def test_writing_skills_routes_reusable_automation_and_keeps_artifacts_distinct(self):
        skill = self.skills / "writing-skills"
        main = " ".join((skill / library.DECLARED).read_text(encoding="utf-8").split())
        workflow = " ".join((skill / "references" / "workflow-scripts.md").read_text(
            encoding="utf-8").split())

        for phrase in ("reusable workflow scripts and external integrations",
                       "[Reusable workflow scripts](references/workflow-scripts.md)",
                       "instruction boundary", "deterministic mechanism",
                       "external-service boundary", "do not inspect or change the live library",
                       "script contracts when no catalog test area owns them",
                       "Inspect existing skill catalogs before creating a package",
                       "Extend the existing owner",
                       "distinct routing, judgment, authority, or proof"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, main)
        for phrase in ("same input produces the same output", "partial output",
                       "safe to repeat", "bounded output", "working directory",
                       "unsupported input", "temporary files",
                       "Add the script to the existing skill"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, workflow)

    def test_writing_skills_requires_routing_and_script_edge_cases(self):
        skill = self.skills / "writing-skills"
        main = " ".join((skill / library.DECLARED).read_text(encoding="utf-8").split())
        workflow = " ".join((skill / "references" / "workflow-scripts.md").read_text(
            encoding="utf-8").split())

        for phrase in ("direct request", "indirect request", "close near-miss",
                       "without the skill", "different fresh turn"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, main)

        for phrase in ("Aim for two short sentences", "Include only concepts needed to route",
                       "Omit steps, tests, benefit claims, and implementation detail",
                       "only when it determines whether the skill should trigger",
                       "shortest description that still routes correctly",
                       "ceiling, not a target", "# Bad: embeds implementation",
                       "# Good: states intent"):
            with self.subTest(description_rule=phrase):
                self.assertIn(phrase, main)
        for phrase in ("empty input", "malformed input", "missing and unreadable files",
                       "interrupted writes", "large input",
                       "semantic unit", "same resolved input", "Empty input or a no-op",
                       "every data-dependent section", "adversarial oracle",
                       "swapping which values share a record",
                       "complete bounded output", "collection cardinality",
                       "truncating each label does not bound a list of inputs",
                       "privacy and redaction promises", "errors, name collisions",
                       "full-path fallback"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, workflow)

        for phrase in ("generated writing separately from executable correctness",
                       "routing precision", "useful judgment", "concision",
                       "duplication", "reference discipline",
                       "Green script tests do not prove", "factual promises",
                       "Source or observe factual promises", "test executable claims",
                       "narrow partial truths", "adversarial counterexample",
                       "mutation checks cannot repair a wrong test oracle",
                       "empty success", "duplicate evidence", "data-dependent output section"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, main)

    def test_live_agent_verification_keeps_the_edge_matrix_and_evidence_contract(self):
        guide = (support.CHECKOUT / "docs" / "live-agent-verification.md").read_text(
            encoding="utf-8")
        index = (support.CHECKOUT / "docs" / "README.md").read_text(encoding="utf-8")

        self.assertIn("[live-agent-verification.md](./live-agent-verification.md)", index)
        for phrase in ("A convincing answer alone is not a pass",
                       "A mock proves the harness",
                       "Use a fresh provider conversation",
                       "Use stable case IDs", "Critical", "Conditional critical", "Extended",
                       "LIVE-U01", "LIVE-U08", "LIVE-RD", "LIVE-IN", "LIVE-SK", "LIVE-PV",
                       "LIVE-SK07-large-output", "Selected cases",
                       "Direct positive", "Indirect positive", "Close near-miss",
                       "Forbidden access", "Failure after progress", "Completion boundary",
                       "fresh baseline without the skill",
                       "LIVE-SK11", "existing-capability reuse",
                       "catalog surfaces before writing",
                       "skill body and every conditionally required reference load",
                       "Review the generated writing separately from runtime correctness",
                       "pass`, `fail`, `partial`, `blocked`, or `not applicable",
                       "Preserve failed natural cases",
                       "Cleanup and restored state", "Preserved verification status"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, guide)

    def test_writing_skills_publishing_and_integrations_keep_their_safety_boundaries(self):
        skill = self.skills / "writing-skills" / "references"
        publishing = " ".join((skill / "publishing.md").read_text(encoding="utf-8").split())
        integrations = " ".join((skill / "integrations.md").read_text(
            encoding="utf-8").split())

        for phrase in ("catalog is the release boundary", "repository rules",
                       "preview is validation, not publication", "breaking change",
                       "acme-skills/", "├── manifest.json", "└── skills/",
                       "├── rundesk.json", "└── search.py"):
            with self.subTest(reference="publishing", phrase=phrase):
                self.assertIn(phrase, publishing)
        for phrase in ("least privilege", "timeouts", "rate limits", "pagination",
                       "redacted error", "offline contract tests"):
            with self.subTest(reference="integrations", phrase=phrase):
                self.assertIn(phrase, integrations)

    def test_managing_rundesk_teaches_the_default_app_and_demotes_the_profile(self):
        """The owner's UX decision, checked rather than remembered.

        `--profile` selects a second OAuth *app*, and an install with one app should never be told
        to type it. A guide that leads with it teaches the wrong mental model on the first read,
        and the first read is the one that sticks.
        """
        root = self.skills / "managing-rundesk"
        skill = root.joinpath(library.DECLARED).read_text(encoding="utf-8")
        reference = root.joinpath("references", "oauth-login.md").read_text(encoding="utf-8")
        compact = " ".join(reference.split())
        self.assertIn("[OAuth login](references/oauth-login.md)", skill)
        self.assertIn('"$RUNDESK_COMMAND" login <provider>', reference)
        self.assertIn('"$RUNDESK_COMMAND" env set <PROVIDER>_OAUTH_CLIENT_ID', reference)
        self.assertIn("rarely needed", compact)
        self.assertIn("different OAuth *app client*, not a different account", compact)
        self.assertIn("`--email` to choose between them", compact)
        self.assertIn("127.0.0.1", compact)
        self.assertIn("Manual copy-and-paste of a *code* is not supported", compact)
        # The fallback URL is described by what it does and does not carry, not by a claim that
        # nothing is ever printed — which the fallback itself would make false.
        self.assertIn("never a client secret, authorization code, refresh token, or access token",
                      compact)
        # The app client is placed before the sign-in, so the guide has to say so before it.
        self.assertLess(reference.index("env set"), reference.index("login <provider>"))

    def test_managing_rundesk_chooses_the_narrowest_relevant_command(self):
        said = (self.skills / "managing-rundesk" / library.DECLARED).read_text(encoding="utf-8")
        self.assertIn("narrowest", said)
        self.assertNotIn("Start with the essentials", said)
        self.assertNotIn("Use listing commands before mutations", said)

    def test_managing_rundesk_forbids_raw_database_and_lock_access(self):
        said = (self.skills / "managing-rundesk" / library.DECLARED).read_text(encoding="utf-8")
        self.assertIn("Never open or edit Rundesk databases, conversation records, or lock files directly", said)

    def test_managing_rundesk_routes_optional_first_party_catalogs(self):
        skills = (self.skills / "managing-rundesk" / "references" / "skills.md").read_text(
            encoding="utf-8")
        for repository in ("https://github.com/rundesk-ai/rundesk-skills-apple",
                           "https://github.com/rundesk-ai/rundesk-skills-integrations"):
            with self.subTest(repository=repository):
                preview = f'"$RUNDESK_COMMAND" skills install {repository}'
                self.assertIn(preview, skills)
                self.assertIn(f"{preview} --confirm", skills)

    def test_delegation_work_is_separate_from_install_management(self):
        managing = self.skills / "managing-rundesk"
        references = managing / "references"
        main = " ".join((managing / library.DECLARED).read_text(encoding="utf-8").split())
        agents = " ".join((references / "agents.md").read_text(encoding="utf-8").split())
        instructions = " ".join(
            (references / "agent-instructions.md").read_text(encoding="utf-8").split())
        delegation_root = self.skills / "delegating-work"
        delegating = " ".join(
            (delegation_root / library.DECLARED).read_text(encoding="utf-8").split())
        operations = " ".join(
            (delegation_root / "references" / "operations.md").read_text(encoding="utf-8").split())
        examples = " ".join(
            (delegation_root / "references" / "brief-examples.md").read_text(
                encoding="utf-8").split())
        for phrase in ("routing contract, not a biography", "durable responsibility it owns",
                       "Do not use transient assignments", "Update the description when"):
            with self.subTest(reference="managing-rundesk/agents", phrase=phrase):
                self.assertIn(phrase, agents)
        for phrase in ("Choose the target from its description", "Do not infer ownership"):
            with self.subTest(reference="delegating-work", phrase=phrase):
                self.assertIn(phrase, delegating)
        for phrase in ("Recover context before acting", "read each selected `SKILL.md` completely",
                       "Availability alone is not a reason to delegate", "Task:", "Why:",
                       "Evidence required:", "Definition of done:", "Complete", "Continue",
                       "Blocked", "not a continuation path"):
            with self.subTest(reference="delegating-work", phrase=phrase):
                self.assertIn(phrase, delegating)
        self.assertIn("deciding whether to delegate work to another Rundesk agent", delegating)
        self.assertIn("preparing or reviewing a handoff", delegating)
        self.assertIn("continuing delegated work to a verified outcome", delegating)
        self.assertIn("Do not use for ordinary Rundesk operations", delegating)
        self.assertIn("[Delegation operations](references/operations.md)", delegating)
        self.assertIn("[Brief examples](references/brief-examples.md)", delegating)
        for phrase in ("List or `show`", "`say` to steer", "`stop` to request",
                       "`resume` to continue", "`working`", "`stopping`", "`stopped`",
                       "`answered`"):
            with self.subTest(reference="delegating-work", phrase=phrase):
                self.assertIn(phrase, delegating)
        for phrase in ("--provider <provider>", "asked --agent <delegator>",
                       "guidance was stored", "same delegation, conversation, provider selection",
                       "steered turn may answer the new guidance", "original brief",
                       "resume the same delegation", "Do not poll"):
            with self.subTest(reference="delegating-work/operations", phrase=phrase):
                self.assertIn(phrase, operations)
        for phrase in ("## Coding implementation", "## Code or design review",
                       "## Research or comparison", "Return format:"):
            with self.subTest(reference="delegating-work/brief-examples", phrase=phrase):
                self.assertIn(phrase, examples)
        self.assertNotIn("### Coding implementation", delegating)
        self.assertIn("Do not use for ordinary project work or for deciding, performing, or reviewing delegation", main)
        self.assertNotIn("whether and how to delegate", main)
        self.assertNotIn("delegation decisions", main)
        self.assertNotIn("Ask an agent from this terminal", main)
        self.assertIn("`delegating-work` skill's handoff lifecycle", instructions)
        self.assertNotIn("delegations.md", instructions)
        self.assertFalse((references / "delegations.md").exists())

    def test_agent_instruction_guidance_is_routed_and_has_each_required_section(self):
        skill = self.skills / "managing-rundesk"
        main = (skill / library.DECLARED).read_text(encoding="utf-8")
        agents = (skill / "references" / "agents.md").read_text(encoding="utf-8")
        agent_instructions = (skill / "references" / "agent-instructions.md").read_text(
            encoding="utf-8")

        link = "[Agent instructions](references/agent-instructions.md)"
        self.assertIn(link, main)
        self.assertIn("[Agent instructions](agent-instructions.md)", agents)
        headings = ("# Agent instructions", "## Keep each rule with its owner",
                    "## Review the agent before writing",
                    "## Write a focused behavior contract", "### Shape the agent's behavior",
                    "#### Domain behavior", "#### Specialist behavior",
                    "##### Coding and code-investigation behavior",
                    "## Change instructions safely")
        places = []
        for heading in headings:
            with self.subTest(heading=heading):
                self.assertEqual(1, agent_instructions.count(heading))
                places.append(agent_instructions.index(heading))
        self.assertEqual(sorted(places), places)

    def guidance(self):
        """The whole agent-instruction reference, whitespace-normalized."""
        return " ".join(
            (self.skills / "managing-rundesk" / "references" / "agent-instructions.md").read_text(
                encoding="utf-8").split())

    def design_step(self):
        """The behavior-shaping step, from its heading to the change procedure that follows it."""
        return self.guidance().split("### Shape the agent's behavior", 1)[1].split(
            "## Change instructions safely", 1)[0]

    def test_the_design_step_grants_the_skills_the_durable_role_needs(self):
        # Grants are a design decision, not a runtime one: the turn can only load what the role was
        # granted, and every ungranted-but-needed skill becomes work done off a description. The
        # opposite cost is just as real, so both ends are taught in the step that shapes the role
        # rather than in one of the two behaviors below it.
        design = self.design_step()
        for phrase in ("Grant the skills that role needs on an ordinary turn",
                       "leave the rest ungranted",
                       "a description every turn pays for",
                       "a body the agent should never open"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, design)

    def test_the_universal_loading_procedure_is_named_once_and_never_copied(self):
        # One source of truth. Rundesk injects the preflight into every turn, so an agent's durable
        # contract that restates it carries a second copy that goes stale on the next release —
        # and the fenced contract is the part an author copies verbatim.
        design = self.design_step()
        self.assertIn("Do not restate the loading procedure in the contract", design)
        self.assertIn("read the applicable project rules in full, load every skill that applies "
                      "to the work, and only then act", design)
        contract, _ = self.coding_step()
        for copied in ("skill body", "skill descriptions", "already loaded", "no others"):
            with self.subTest(copied=copied):
                self.assertNotIn(copied, contract)

    def test_validation_inspects_the_order_a_fresh_turn_actually_took(self):
        # A granted skill, a named skill and a loaded skill look identical in a listing, and a body
        # loaded after the work began governed none of it. Validation therefore reads load
        # evidence and its order; the near-miss case stays, because accepting the wrong work is a
        # different failure from loading the wrong skill.
        guidance = self.guidance()
        procedure = guidance.split("## Change instructions safely", 1)[1]
        for phrase in ("one representative assignment and one close near-miss",
                       "inspect whatever load evidence the provider supports",
                       "confirm the order the turn actually took",
                       "project's own rules read in full first",
                       "then every skill applicable to the assignment loaded with the references "
                       "its body requires, then the remaining work",
                       "close but irrelevant granted skill stayed unloaded",
                       "body already loaded earlier in the session was not loaded again",
                       "not evidence that its body was read",
                       "body loaded after the work began did not govern it"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, procedure)

    def coding_step(self):
        """The example contract inside its fence, then the read-only delta after it.

        Read apart rather than as one section, because an author copies the fenced contract and
        reads the delta as what to leave out. A required sentence that drifts into the surrounding
        rationale is no longer in the thing being copied, and a check over the whole section could
        not tell the two apart. Whitespace is normalized so a hand-wrapped line decides nothing.
        """
        step = self.guidance().split("#### Specialist behavior", 1)[1].split(
            "## Change instructions safely", 1)[0]
        contract, _, delta = step.partition("```markdown")[2].partition("```")
        return contract, delta

    def test_a_coding_specialist_contract_is_specific_about_the_checkout(self):
        # An agent home is an operational workspace, and the rules governing a repository live in
        # that repository. The design step has to ask for them by requirement: copying a project's
        # rules into durable agent instructions is the failure the ownership split already forbids,
        # and the copy goes stale at the first commit nobody told the agent about.
        #
        # One example contract carries these behaviors, and this reads that contract out of its
        # fence: a rule the author would not copy has not been taught, however well the section
        # around it explains itself.
        contract, _ = self.coding_step()
        for behavior, phrase in (
                ("project rules", "read the target repository's `AGENTS.md` in full and follow it"),
                ("authoritative state",
                 "Establish the authoritative base, its remotes, the current branch, existing "
                 "worktrees, and uncommitted changes before acting"),
                ("not the checked-out branch", "not authoritative because it is checked out"),
                ("isolated workspace", "Work in an isolated task worktree on a topic branch cut "
                                       "from that base"),
                ("named exception", "unless the assignment names another safe workspace"),
                ("home is not a checkout", "operational workspace, never the project checkout"),
                ("preserve other work", "Never reset, discard, overwrite, or fold somebody else's "
                                        "work into the task"),
                ("shared checkout untouched", "Leave the shared checkout unchanged as found"),
                ("owned worktree clean", "Leave your own task worktree clean with coherent commits "
                                         "on its topic branch"),
                ("asked-for dirty state", "leave it uncommitted and report that exact dirty state"),
                ("proportionate verification",
                 "Run the verification the project defines, proportionate to the risk of the "
                 "change, and report every gate that did not run"),
                ("no external state", "Do not push, use a code-hosting service, merge, release, or "
                                      "change external state without authority"),
                ("handback", "Return the exact checkout or worktree path, branch, commit or dirty "
                             "files, verification and results, limitations, and remaining work")):
            with self.subTest(behavior=behavior):
                self.assertIn(phrase, contract)

    def test_a_read_only_investigator_creates_no_worktree_branch_or_commit(self):
        # Read-only work that opens a worktree has already exceeded its authority. The delta is
        # read from the prose after the fence, because a read-only rule inside the implementation
        # contract is a rule an author copies into an implementer.
        _, delta = self.coding_step()
        for phrase in ("read-only code investigator or reviewer",
                       "creates no worktree, branch, or commit",
                       "returns findings and evidence instead of changes"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, delta)

    def test_managing_rundesk_routes_desk_cli_catalog_and_binary_separately(self):
        skills = (self.skills / "managing-rundesk" / "references" / "skills.md").read_text(
            encoding="utf-8")
        repository = "https://github.com/rundesk-ai/desk-cli"
        preview = f'"$RUNDESK_COMMAND" skills install {repository}'
        address = "desk-cli/managing-your-desk"

        self.assertIn(preview, skills)
        self.assertIn(f"{preview} --confirm", skills)
        self.assertIn(f'"$RUNDESK_COMMAND" skills grant <agent> {address}', skills)
        self.assertIn(f'"$RUNDESK_COMMAND" skills profiles {address}', skills)
        self.assertIn(
            f'"$RUNDESK_COMMAND" skills configure {address} --profile <name>', skills)
        self.assertIn('"$RUNDESK_COMMAND" skills doctor <agent>', skills)
        self.assertIn("does not install the `desk` binary", skills)
        contract_text = " ".join(skills.split())
        for contract in ("desk-bound identity", "desk user-mentions", "API-token actor",
                         "Owner and Admin", "Member is limited to its assigned visible desk",
                         "deskless Member retains human mentions"):
            with self.subTest(contract=contract):
                self.assertIn(contract, contract_text)

    def test_focused_maintenance_is_detailed_only_in_its_reference(self):
        skill = self.skills / "managing-rundesk"
        said = (skill / library.DECLARED).read_text(encoding="utf-8")
        maintenance = " ".join((skill / "references" / "maintenance.md").read_text(
            encoding="utf-8").split())
        self.assertIn("[Maintenance](references/maintenance.md)", said)
        for phrase in ("retain an unavailable active mapping",
                       "durable role and responsibilities", "confirmed agent-created",
                       "files of uncertain ownership",
                       "## Tidy versus cluttered", "A tidy home", "A cluttered home",
                       "not deletion authority", "working or draft paths",
                       "commands or deliverable paths", "supersession history",
                       "report formatting",
                       "Preserve a still-open owner commitment", "canonical `OPEN_ITEMS.md`",
                       "never one home note per project",
                       "Combined upkeep contract", "maintenance runs first",
                       "never open the link or target",
                       "Preserve and list `retros/`, but do not open its entries",
                       "short final required by the combined contract"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, maintenance)

    def test_self_improvement_is_evidence_based_and_detailed_only_in_its_reference(self):
        skill = self.skills / "managing-rundesk"
        said = (skill / library.DECLARED).read_text(encoding="utf-8")
        improving = " ".join((skill / "references" / "self-improvement.md").read_text(
            encoding="utf-8").split())
        self.assertIn("[Self-improvement](references/self-improvement.md)", said)
        self.assertIn("[Retrospective](references/retrospective.md)", said)
        for phrase in ("focused review, not ordinary task overhead",
                       "Maintenance preservation remains in force",
                       "never open a symlink or its target",
                       "recent messages and turns", "repeated friction", "owner corrections",
                       "failed or blocked outcomes", "public Rundesk commands",
                       "previous `weekly-self-improve-upkeep` scheduled runs", "what went well",
                       "what did not", "already resolved",
                       'messages AGENT --source schedule --limit 10',
                       "select the `(schedule weekly-self-improve-upkeep)` conversation",
                       "project-specific evidence in that project's own files",
                       '"$RUNDESK_COMMAND" agents', '"$RUNDESK_COMMAND" gateways',
                       "compare only the relevant available and granted skills",
                       "active gateway", "Exclude yourself",
                       "gateway state only to determine delegation availability",
                       "Never open another agent's home, memory, or records",
                       "Never infer another agent's focus from its name",
                       "named agent", "provider-local research helper",
                       "recurring capability gap", "Skills do not replace delegation",
                       "Before recommending a skill", "why neither route covers",
                       "Non-use alone is not evidence", "Revocation is rare",
                       "Do not change grants", "explicit authority",
                       "Apply a safe local improvement",
                       "post-edit fixture matrix from every documented input type and error branch",
                       "a skipped input is reported, never called clean",
                       "exact owner decision",
                       "## Combined upkeep contract", "weekly-self-improve-upkeep",
                       "maintenance reference first", "retrospective reference second",
                       "self-improvement reference last",
                       "Do not open the next reference until the current phase is verified",
                       "exactly one sentence", "very short and attention-first",
                       "Definition of done for each firing",
                       "full bounded evidence window", "superficial scan",
                       "error branch, and stated safety limit",
                       "material independent research question uses a provider-local helper",
                       "every claimed change and preservation",
                       "at most two repeated frictions", "50 messages or 20 turns",
                       "at most three full turns", "record the reason before expanding",
                       "Never exceed 100 messages, 40 turns, or five full turns",
                       "make no durable behavioral improvement from the unresolved evidence",
                       "Use the attention result only when a specific owner action can resolve a required blocker",
                       "One owner correction", "explicitly states a durable preference",
                       "another durable behavior change",
                       "provider-local helpers are unavailable, record the unavailable route and "
                       "continue only with bounded local evidence",
                       "without further helper analysis",
                       "does not count as self-improvement",
                       "known operational failure", "Unrelated tracked work",
                       "Upkeep completed — improved <specific behavior>",
                       "Upkeep completed — no durable change was justified",
                       "During combined upkeep use the exact short final below"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, improving)
        self.assertNotIn("Upkeep completed — no owner action is needed.", improving)
        self.assertNotIn("schedules add AGENT weekly-self-improve-upkeep", improving)
        self.assertNotIn("--disabled", improving)

    def test_weekly_retrospective_is_bounded_evidence_not_owner_mind_reading(self):
        skill = self.skills / "managing-rundesk"
        retro = " ".join((skill / "references" / "retrospective.md").read_text(
            encoding="utf-8").split())
        for phrase in ("previous entry first", "retros/YYYY-MM-DD.md",
                       "## What went well", "## What did not go well",
                       "## What to improve", "explicit owner correction",
                       "dissatisfaction or distrust", "Never diagnose the owner's mood",
                       "three evidence-backed bullets per section", "Keep every entry",
                       "Never delete an older retrospective merely because of age",
                       "update the same file", "no secrets", "candidate action",
                       "Do not promote a lesson from one correction",
                       "explicit durable owner preference", "corroborates earlier evidence",
                       "leave it byte-identical",
                       "Would an existing named agent", "Would a provider-local research helper",
                       "available, granted, or new skill",
                       "exact evidence interval and diary date supplied by the initiator",
                       "Never calculate or shift that interval yourself"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, retro)

    def test_the_protected_upkeep_policy_is_taught_as_per_agent_configuration(self):
        skill = self.skills / "managing-rundesk" / "references"
        schedules = " ".join((skill / "schedules.md").read_text(encoding="utf-8").split())
        configuration = " ".join(
            (skill / "configuration.md").read_text(encoding="utf-8").split())
        for said in (schedules, configuration):
            with self.subTest(reference=said[:20]):
                self.assertIn("weekly-self-improve-upkeep", said)
                self.assertIn("agents configure <agent> --self-improve <true|false>", said)
        self.assertIn("seven distinct usage dates", schedules)
        self.assertIn("do not try to add, update, run, disable, or remove it", schedules)

    def test_schedules_are_taught_as_bounded_proactive_verification(self):
        skill = self.skills / "managing-rundesk"
        main = " ".join((skill / "SKILL.md").read_text(encoding="utf-8").split())
        schedules = " ".join(
            (skill / "references" / "schedules.md").read_text(encoding="utf-8").split())
        self.assertIn("proactive verification check-ins", main)
        for phrase in ("outcome can only be confirmed later", "one `--at` check",
                       "name what to inspect", "perform the check",
                       "within the original authority", "notified channel"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, schedules)

    def test_no_shipped_skill_names_a_verb_this_build_does_not_have(self):
        # `AGENTS.md`: a verb rundesk cannot perform is a verb rundesk does not have. A skill is the
        # one place that can be broken with nothing going red — it is read by an agent, on every
        # turn, and acted on. The build this replaces shipped one teaching an invocation path
        # nothing set.
        there = verbs_of(cli.build_parser())
        self.assertTrue(there, "the parser answered no verbs at all")
        for name in self.named():
            said = (self.skills / name / library.DECLARED).read_text(encoding="utf-8")
            for verb in sorted(set(verbs_named(said))):
                with self.subTest(skill=name, verb=verb):
                    self.assertIn(verb, there,
                                  f"{name} tells an agent to type `rundesk {verb}`, and this "
                                  "build has no such verb")

    def test_the_check_would_notice_a_verb_that_went_away(self):
        # The guard on the guard. A pattern that matched nothing, or a verb set that answered
        # everything, would leave the case above green for ever — and this is exactly the check
        # whose failure mode is silence.
        # Re-pointed when `schedules` landed, again when `channels` did, and again when `providers`
        # did — exactly as intended: it has to name a verb this build really does not have, so the
        # next one to arrive moves it again, and the person moving it is the person who can see what
        # is still absent.
        #
        # What is still absent is delegation. An agent can be asked something by a person, by the
        # clock and by a channel; being asked by *another agent* is reserved throughout — the
        # conversation records already hold `agent` and `role` as sources, and the prompt builder
        # keeps a layer for each — and nothing produces one, so `rundesk delegations` is a verb
        # rundesk does not have.
        self.assertNotIn("delegations", verbs_of(cli.build_parser()))
        self.assertEqual(["gateways"], verbs_named("run `rundesk gateways logs alan` to see"))
        self.assertEqual(["env"], verbs_named("```sh\nrundesk env set NAME\n```"))
        self.assertEqual(["--help"], verbs_named("`rundesk --help` is generated"))
        # And prose naming the product is read as prose, whether it opens a line or not.
        self.assertEqual([], verbs_named("rundesk is the thing running you"))
        self.assertEqual([], verbs_named("Nothing else here is rundesk itself, whatever it says"))
        # **The reachable spelling is read as a command too.** A skill tells an agent to type
        # `"$RUNDESK_COMMAND" <verb>`, because a bare `rundesk` is not on every brain's path — and a
        # pattern that only knew the bare word would leave every one of those commands unchecked
        # while the case above went on passing, which is silence rather than a failure.
        self.assertEqual(["status"], verbs_named('```sh\n"$RUNDESK_COMMAND" status\n```'))
        self.assertEqual(["skills"], verbs_named('`"$RUNDESK_COMMAND" skills list alan`'))


class WhatTheDocumentationClaims(support.Isolated):
    """`docs/commands.md` says it is the complete list of what rundesk can do.

    That page is checked by people, and people are exactly who a stale verb misleads: `AGENTS.md`
    forbids offering an operation that is not built, and a documented verb that does not exist is the
    same promise broken one step further from the code. The shipped skills are already held to this;
    there is no reason the page a person reads should be the one thing that is not.
    """

    def test_every_skills_sub_verb_the_docs_name_is_one_that_exists(self):
        said = (support.CHECKOUT / "docs" / "commands.md").read_text(encoding="utf-8")
        there = _sub_verbs_of("skills")
        self.assertTrue(there, "the parser answered no sub-verbs for skills")
        named = set(re.findall(r"rundesk skills ([a-z][a-z-]*)", said))
        self.assertTrue(named, "the page names no skills sub-verb at all")
        for verb in sorted(named - {"list"}):
            with self.subTest(verb=verb):
                self.assertIn(verb, there,
                              f"docs/commands.md tells somebody to type `rundesk skills {verb}`, "
                              "and this build has no such sub-verb")

    def test_every_sub_verb_that_exists_is_named_by_the_docs(self):
        # The other direction, because the page claims to be *complete*. A verb that shipped without
        # reaching the page is the shape that goes unnoticed for a release.
        said = (support.CHECKOUT / "docs" / "commands.md").read_text(encoding="utf-8")
        for verb in sorted(_sub_verbs_of("skills")):
            with self.subTest(verb=verb):
                self.assertIn(f"rundesk skills {verb}", said,
                              f"`rundesk skills {verb}` exists and docs/commands.md never names it")

    def test_upkeep_overview_matches_the_evidence_based_contract(self):
        said = " ".join((support.CHECKOUT / "docs" / "commands.md").read_text(
            encoding="utf-8").split())
        self.assertIn("honest no-change", said)
        self.assertIn("only when selected friction indicates a capability gap", said)
        self.assertNotIn("and one testable improvement", said)
        self.assertNotIn("The pass compares available and granted skills", said)


def _sub_verbs_of(group: str):
    """Every sub-verb one group really has, read off the parser rather than listed here."""
    for action in cli.build_parser()._actions:
        if isinstance(action, cli.Subcommands) and group in action.choices:
            for one in action.choices[group]._actions:
                if isinstance(one, cli.Subcommands):
                    return set(one.choices)
    return set()


if __name__ == "__main__":
    unittest.main()
