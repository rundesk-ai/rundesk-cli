#!/usr/bin/env python3
"""What an agent is, where it keeps things, and the one gateway that runs it.

Answers for `agent-home` (R-AGT-n) and the part of `agent-gateway` (R-AGW-n) that is
decided without a command being typed. Nothing here starts a provider, reaches the network
or touches the machine's own directories: every case is given scratch of its own, and any
gateway it builds is given a scratch `root` so it asks whether *that* fits rather than
whether the developer's checkout does.

Run: python3 tests/test_agent.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rundesk import agent, config, gateway, skill, store, updater  # noqa: E402


#: The two files SQLite keeps beside a database, which are its bookkeeping and not the
#: agent's. **Merely reading a database in WAL brings them into being**, and a read-only
#: connection cannot take them away again — only the last writer to close checkpoints. So a
#: command that promises to change nothing about an agent still leaves these, and a case
#: about what changed must compare what is the agent's own.
BESIDE = ("state.db-wal", "state.db-shm")


def tree(where: Path) -> dict[str, bytes | None]:
    """Everything of the agent's standing under here, and what is in it.

    Directories are carried as `None` so that one appearing or going is a difference too,
    and the whole thing is comparable with one assertion.
    """
    found: dict[str, bytes | None] = {}
    for path in sorted(where.rglob("*")):
        if path.name in BESIDE:
            continue
        at = str(path.relative_to(where))
        found[at] = None if path.is_dir() else path.read_bytes()
    return found


class WithSomewhereToKeepAgents(unittest.TestCase):
    """Each case gets a machine of its own to be the only owner on."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-agents-"))
        self.addCleanup(shutil.rmtree, self.where, True)
        # The three a gateway kept things in before there were agents to own them. Pointed
        # at scratch even where a case passes them explicitly, because anything that
        # resolves one of these from the environment would otherwise reach the owner's own.
        self.before = Path(tempfile.mkdtemp(prefix="rundesk-before-"))
        self.addCleanup(shutil.rmtree, self.before, True)
        self.root = Path(tempfile.mkdtemp(prefix="rundesk-root-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        # **The data root as well, and it is not optional.** Everything else here
        # falls back to it, so a fixture that isolates the four and forgets this
        # one still reaches the owner's real library — `add` grants what the
        # release ships, and would link a scratch agent at what they actually have.
        for said, at in (("RUNDESK_DATA_DIR", self.before / "data"),
                         ("RUNDESK_AGENTS_DIR", self.where),
                         ("RUNDESK_RUN_DIR", self.before / "run"),
                         ("RUNDESK_LOG_DIR", self.before / "logs"),
                         ("RUNDESK_JOBS_DIR", self.before / "jobs")):
            self.addCleanup(os.environ.pop, said, None)
            os.environ[said] = str(at)
            # Made rather than left to whatever writes there first: `gateway.note` appends
            # to a log without making the directory and swallows the failure, so a case
            # that arranges a log in scratch gets silence instead of a log.
            at.mkdir(parents=True, exist_ok=True)
        config.ensure(self.before / "data")

    def made(self, name: str = "ava") -> str:
        """An agent as an owner actually has one: with a brain (R-AGT-18).

        Named here rather than in each case, because an agent without one is now a fault
        every diagnosis reports — so a fixture that left it out would put that complaint into
        every case about something else.
        """
        agent.add(name, self.where)
        agent.remember(name, self.where, provider="codex")
        return name


class NamingANewAgent(unittest.TestCase):
    def test_spaces_and_punctuation_become_one_dash(self):
        """R-AGT-39"""
        self.assertEqual("agent-name", agent.slug("  Agent -- Name  "))

    def test_a_new_agents_name_is_lowercase(self):
        """R-AGT-39"""
        self.assertEqual("winston", agent.slug("Winston"))

    def test_an_accented_name_has_a_stable_ascii_slug(self):
        """R-AGT-39"""
        self.assertEqual("echo", agent.slug("Écho"))

    def test_a_name_with_no_letters_or_digits_is_refused(self):
        """R-AGT-39"""
        with self.assertRaises(agent.NotAnAgentName):
            agent.slug(" -- ")

    def test_an_existing_legacy_spelling_keeps_its_directory(self):
        """R-AGT-40"""
        self.assertEqual(
            "Agent_Name", agent.creation_name("Agent Name", ["Agent_Name"]))

    def test_exact_case_wins_when_legacy_agents_differ_only_by_case(self):
        """R-AGT-40 — exact supervisor invocations remain unambiguous on Linux."""
        existing = ["Winston", "winston"]
        self.assertEqual("Winston", agent.creation_name("Winston", existing))
        self.assertEqual("winston", agent.creation_name("winston", existing))
        with self.assertRaises(agent.NotAnAgentName):
            agent.creation_name("WINSTON", existing)

    def test_an_unmatched_command_preserves_a_legacy_gateway_name(self):
        """R-AGT-13 — a pre-agent supervisor command must not change identity."""
        self.assertEqual("Winston", agent.command_name("Winston"))

    def test_ambiguous_legacy_spellings_are_refused(self):
        """R-AGT-40"""
        with self.assertRaises(agent.NotAnAgentName):
            agent.creation_name("Agent Name", ["Agent_Name", "Agent.Name"])

    def test_a_legacy_unicode_name_stays_reachable(self):
        """R-AGT-40 — older releases admitted Unicode names with no ASCII spelling."""
        self.assertEqual("代理", agent.creation_name("代理", ["代理"]))

    def test_a_legacy_unicode_name_does_not_block_an_unrelated_new_agent(self):
        """R-AGT-40 — resolving the existing population skips only the legacy name
        that cannot itself be represented as today's slug."""
        self.assertEqual("new-agent", agent.creation_name("New Agent", ["代理"]))


class ResolvingLegacyGatewayNames(WithSomewhereToKeepAgents):
    def test_shared_history_preserves_the_gateway_spelling_during_adoption(self):
        """R-AGW-1, R-AGT-13 — pre-agent history is an existing identity."""
        (self.before / "logs" / "Winston.log").write_text("kept")
        names = agent.identities(self.where, self.before / "run", self.before / "logs")
        self.assertIn("Winston", names)
        self.assertEqual("Winston", agent.creation_name("winston", names))

    def test_rotated_history_alone_preserves_the_gateway_spelling(self):
        """R-AGW-5 — rotation may be the only surviving artifact."""
        (self.before / "logs" / "Agent_Name.log.1").write_text("kept")
        names = agent.identities(self.where, self.before / "run", self.before / "logs")
        self.assertIn("Agent_Name", names)
        self.assertEqual("Agent_Name", agent.creation_name("Agent Name", names))

    def test_machine_error_output_alone_preserves_the_gateway_spelling(self):
        """R-GW-36 — a gateway may fail before its own logger ever starts."""
        (self.before / "logs" / "Winston.err").write_text("failed before logger")
        names = agent.identities(self.where, self.before / "run", self.before / "logs")
        self.assertIn("Winston", names)
        self.assertEqual("Winston", agent.creation_name("winston", names))


class TemplatesAnOwnerMadeTheirOwn(WithSomewhereToKeepAgents):
    """The files a new agent's home is copied from, and an owner's right to replace them.

    **No case here reads the owner's real override directory.** It is derived from where
    agents are kept, which `setUp` already points at scratch, so isolating one isolates the
    other — but `own()` asserts that rather than trusting it, because `MEMORY.md` records
    what the same mistake one level down cost: five variables redirected, and real agents
    written into `~/.rundesk/agents` while `rundesk add` reported success.
    """

    def own(self, called: str = "", says: str = "") -> Path:
        """A template of this owner's, in the directory derived from where agents are kept."""
        where = agent.templates_home()
        # **Below the directory this case redirected**, not beside it. Hung off the parent
        # it resolved to whatever the scratch directory happened to sit in — the shared
        # temp root — so every case wrote into one place and one case's template turned up
        # in another's agent. Asserted rather than trusted, because that is exactly the
        # class of mistake `MEMORY.md` records at the level below this one.
        self.assertEqual(self.where, where.parent.parent,
                         f"the owner's own templates would be read from {where}")
        where.mkdir(parents=True, exist_ok=True)
        if called:
            (where / called).write_text(says, encoding="utf-8")
        return where

    def held(self, name: str = "ava") -> dict:
        home = agent.home(name, self.where)
        return {page.name: page.read_text(encoding="utf-8")
                for page in sorted(home.iterdir()) if page.is_file()}

    def test_a_home_made_with_no_overrides_is_what_the_install_ships(self):
        """R-AGT-22 — the floor everything else is measured from. An owner who has made no
        template of their own gets the factory set, byte for byte but for the one name."""
        self.made()
        for called, says in self.held().items():
            self.assertEqual(agent._copied(called, "ava"),
                             says, f"{called} is not what the install ships")

    def test_one_overridden_page_is_the_owners_and_the_rest_are_shipped(self):
        """R-AGT-22 — per page, not per set. Taking on all four to change one would mean
        never getting an improvement to any of them, which is a choice worth avoiding."""
        self.own("SOUL.md", "# {{agent}} answers only in haiku\n")
        self.made()

        held = self.held()
        self.assertEqual("# ava answers only in haiku\n", held["SOUL.md"])
        self.assertEqual(
            [], agent.records("ava", self.where).pending_update_turns(),
            "a fresh owner-customized home was mistaken for an old agent",
        )
        for called in ("AGENTS.md", "CLAUDE.md", "MEMORY.md"):
            self.assertEqual(agent._copied(called, "ava"),
                             held[called], f"{called} stopped being the install's")

    def test_a_legacy_name_placeholder_still_names_the_agent(self):
        """R-AGT-41 — existing owner templates survive the clearer placeholder name."""
        self.own("SOUL.md", "# {{name}} answers only in haiku\n")
        self.made()
        self.assertEqual("# ava answers only in haiku\n", self.held()["SOUL.md"])

    def test_an_owner_template_uses_the_agent_placeholder(self):
        """R-AGT-41 — the current placeholder says what value it represents."""
        self.own("SOUL.md", "# {{agent}} answers only in haiku\n")
        self.made()
        self.assertEqual("# ava answers only in haiku\n", self.held()["SOUL.md"])

    def test_an_override_that_never_names_the_agent_still_makes_a_working_agent(self):
        """R-AGT-25 — the substitution is the whole contract an override has to honour, and
        honouring it is optional. A template with no placeholder is one every agent gets
        verbatim, which is a legitimate thing to want."""
        self.own("SOUL.md", "# be terse\n")
        self.made()
        self.assertEqual("# be terse\n", self.held()["SOUL.md"])
        self.assertEqual([], agent.diagnosed("ava", self.where, root=self.root,
                                             runnable=lambda one: None))

    def test_an_override_directory_that_is_empty_changes_nothing(self):
        self.own()
        self.made()
        self.assertEqual(set(agent.shipped()), set(self.held()))

    def test_an_override_directory_that_cannot_be_read_is_not_a_half_made_agent(self):
        """Unreadable is an owner who has made none, not a failure: a diagnosis is what
        somebody runs *because* something is wrong, and an agent they cannot make is worse
        than one made from the words that ship."""
        where = self.own()
        where.chmod(0o000)
        self.addCleanup(where.chmod, 0o755)
        self.made()
        self.assertEqual(set(agent.shipped()), set(self.held()))

    def test_a_page_the_install_does_not_ship_reaches_a_new_agent(self):
        """R-AGT-24 — an override may add, not only replace."""
        self.own("RULES.md", "# {{agent}} never force-pushes\n")
        self.made()
        self.assertEqual("# ava never force-pushes\n", self.held()["RULES.md"])

    def test_a_legacy_user_override_does_not_restore_the_retired_page(self):
        """R-AGT-43 — an owner may still have an override from an older release. It is not
        copied into new homes, while unrelated owner-added pages remain supported."""
        where = self.own("USER.md", "# old separate context\n")
        (where / "RULES.md").write_text("# keep this addition\n", encoding="utf-8")

        self.made()

        self.assertNotIn("USER.md", self.held())
        self.assertEqual("# keep this addition\n", self.held()["RULES.md"])

    def test_an_agent_made_before_a_page_was_added_is_not_reported_as_missing_it(self):
        """R-AGT-24 — the reason this decision is not cosmetic, and it only shows up once
        somebody has agents. What an agent is judged against is what the install ships; if
        it were the whole set, adding one page would report every agent ever made as
        missing a file it loads — a customisation retroactively breaking the reading of
        agents it never touched."""
        self.made("older")
        self.own("RULES.md", "# added afterwards\n")

        found = agent.diagnosed("older", self.where, root=self.root,
                                runnable=lambda one: None)
        self.assertEqual([], found, f"an agent made earlier was reported broken: {found}")
        self.assertNotIn("RULES.md", self.held("older"),
                         "a page added later was written into an agent that already existed")

    def test_an_override_added_afterwards_changes_nothing_in_an_existing_home(self):
        """R-AGT-4 — what makes running `add` again a repair rather than a reset. An owner
        who overrides a template and wants an existing agent to have it edits that agent's
        home; rundesk never rewrites words a person may have changed."""
        self.made()
        (agent.home("ava", self.where) / "SOUL.md").write_text("# what I wrote myself\n")
        self.own("SOUL.md", "# the owner's template\n")

        agent.add("ava", self.where)
        self.assertEqual("# what I wrote myself\n", self.held()["SOUL.md"])

    def test_an_update_replaces_the_shipped_templates_and_leaves_every_override(self):
        """R-AGT-23 — the claim this phase exists for, and it is a property of *where* the
        overrides live rather than of anything the update does.

        `updater._copy_over` stages each top-level item of the release and swaps it in, and
        `_swap` renames what was there aside and lets go of it once the update is proved —
        so anything under a path the release ships is replaced wholesale. The release ships
        `src/`, and the shipped templates are inside it. An owner's are not under any path
        it ships, and are not under the program at all.

        Driven against the real `_copy_over` rather than reasoned about: the whole point is
        that nothing in the updater knows this directory exists, so nothing in the updater
        can be relied on to leave it alone on purpose.
        """
        mine = self.own("SOUL.md", "# what I wrote\n")
        install = Path(tempfile.mkdtemp(prefix="rundesk-install-"))
        self.addCleanup(shutil.rmtree, install, True)
        (install / "src" / "templates" / "agent").mkdir(parents=True)
        (install / "src" / "templates" / "agent" / "SOUL.md").write_text("# the old shipped one\n")

        release = Path(tempfile.mkdtemp(prefix="rundesk-release-"))
        self.addCleanup(shutil.rmtree, release, True)
        (release / "src" / "templates" / "agent").mkdir(parents=True)
        (release / "src" / "templates" / "agent" / "SOUL.md").write_text("# the new shipped one\n")

        updater._copy_over(release, install)

        self.assertEqual("# the new shipped one\n",
                         (install / "src" / "templates" / "agent" / "SOUL.md").read_text(),
                         "the update did not replace what the release ships")
        self.assertEqual("# what I wrote\n", (mine / "SOUL.md").read_text(),
                         "an update took a template its owner wrote")

    def test_what_an_owner_wrote_is_not_under_anything_a_release_ships(self):
        """R-AGT-23 — said as a shape rather than only as an outcome, because the outcome
        holds by accident the day somebody moves the directory. What an update lays down is
        the release's own top-level items; an owner's templates are under none of them."""
        self.own("SOUL.md", "# mine\n")
        theirs = agent.templates_home().resolve()
        self.assertNotIn(agent.TEMPLATES.resolve().parent, theirs.parents,
                         "an owner's templates stand inside what a release ships")
        self.assertNotIn(ROOT.resolve(), theirs.parents,
                         "an owner's templates stand inside the program")

    def test_a_diagnosis_says_which_pages_are_the_owners_and_where_from(self):
        """R-AGT-26 — "why does my new agent not have my rules" answered without reading
        source, and said for every page rather than only the overridden ones: an owner who
        misspelled a filename needs the four still saying "install" to notice the fifth."""
        where = self.own("SOUL.md", "# mine\n")
        from_each = dict((called, (whose, at))
                         for called, whose, at in agent.where_each_page_comes_from())

        self.assertEqual(("owner", where / "SOUL.md"), from_each["SOUL.md"])
        self.assertEqual(("install", agent.TEMPLATES / "AGENTS.md"), from_each["AGENTS.md"])
        self.assertEqual(set(agent.shipped()), set(from_each),
                         "a page was left out of what a diagnosis reports")


class AnAgentIsMade(WithSomewhereToKeepAgents):
    def test_an_agent_is_made_with_the_files_it_loads(self):
        """R-AGT-2"""
        agent.add("ava", self.where)
        for called in agent.knowledge():
            self.assertTrue((agent.home("ava", self.where) / called).is_file(),
                            f"a new agent has no {called} to load")
        self.assertTrue(agent.workspace("ava", self.where).is_dir())
        self.assertTrue(agent.plans("ava", self.where).is_dir())
        self.assertTrue(agent.skills("ava", self.where).is_dir())

    def test_a_new_home_has_no_separate_user_page(self):
        """R-AGT-43 — personal facts and response preferences now live in MEMORY. The
        factory home has one continuity page for them, not a second page that can disagree
        with it."""
        agent.add("ava", self.where)
        self.assertEqual(
            {"AGENTS.md", "CLAUDE.md", "MEMORY.md", "SOUL.md"},
            {path.name for path in agent.home("ava", self.where).iterdir() if path.is_file()},
        )
        memory = (agent.home("ava", self.where) / "MEMORY.md").read_text()
        self.assertIn("## Who you work for", memory)
        self.assertIn("## How they want to be answered", memory)

    def test_what_an_agent_loads_holds_nothing_rundesk_keeps(self):
        """R-AGT-2 — the home is what the agent loads. A provider reading its own rules
        must not be reading rundesk's lock, log and schedules, which is what putting them
        in one directory would have meant."""
        agent.add("ava", self.where)
        standing = {path.name for path in agent.home("ava", self.where).iterdir()}
        self.assertEqual(standing, set(agent.knowledge()) | set(agent.WORKING))

    #: The files a provider loads because of *where they stand*, rather than because
    #: something pointed at them. Everything else in a home is reached only by being named
    #: from one of these, directly or through another that is.
    LOADED = ("AGENTS.md", "CLAUDE.md")

    def test_provider_bootstrap_requires_complete_agent_rules_before_action(self):
        """R-AGT-42 — the shipped provider bootstrap makes the shared agent rules the
        first action rather than optional reading after a response has begun."""
        says = (agent.TEMPLATES / "CLAUDE.md").read_text()
        self.assertIn("Before you respond to the user, do any task, or any action", says)
        self.assertIn("[AGENTS.md](./AGENTS.md) completely.", says)
        self.assertIn("your next step must be to read it first, always.", says)

    def test_the_file_every_provider_loads_names_the_ones_none_of_them_do(self):
        """R-AGT-2 — the two files loaded because of where they stand are the only way the
        other three are reached at all: no provider follows a Markdown link for free, and
        only one of them expands an import. So each of the three has to be *named*, from a
        loaded file or from one a loaded file names.

        Walked rather than asserted file by file, because how the home chains is the
        template's business and not this case's: `CLAUDE.md` naming only `AGENTS.md`, and
        `AGENTS.md` naming the three, is as good as both naming all of them. What must not
        happen is one of the three becoming unreachable from either starting point — an
        agent that quietly loses its character, with nothing else failing.

        **What this cannot see, and no case can:** that the sentence around the name is an
        instruction to read it. `SOUL.md` mentioned only in a prohibition still counts here.
        The name being present is the part a test can hold; whether the wording works is
        what a probe against a real brain is for."""
        agent.add("ava", self.where)
        home = agent.home("ava", self.where)
        for start in self.LOADED:
            reached, walking = set(), [start]
            while walking:
                called = walking.pop()
                if called in reached:
                    continue
                reached.add(called)
                says = (home / called).read_text()
                walking += [one for one in agent.knowledge() if one in says]
            for wanted in ("SOUL.md", "MEMORY.md"):
                self.assertIn(wanted, reached,
                              f"nothing an agent loads reaches {wanted} from {start} — "
                              f"only {sorted(reached)} is reachable")

    def test_what_an_agent_loads_is_reached_by_being_told_rather_than_by_a_link(self):
        """R-AGT-2 — a home that routed by Markdown link would be inert, and nothing would
        fail to say so."""
        agent.add("ava", self.where)
        says = (agent.home("ava", self.where) / "AGENTS.md").read_text()
        self.assertNotIn("](SOUL.md)", says, "the home routes by a link no provider follows")

    def test_every_directory_an_agent_is_made_of_is_made_and_looked_for(self):
        """R-AGT-2, R-AGT-11 — the teeth on both. Making an agent and diagnosing one each
        wrote out their own copy of this list, so a directory added to what an agent
        resolves and forgotten in one of them is one a new agent silently never gets, or
        one whose absence is reported as ready. Read off the list itself, so the day a new
        one lands it is made and looked for without either being edited."""
        agent.add("ava", self.where)
        # A brain, so the only complaint a diagnosis has is the directory this case took
        # away — an agent without one is its own fault now (R-AGT-18).
        agent.remember("ava", self.where, provider="codex")
        wanted = agent.made_of("ava", self.where)
        self.assertIn("home", wanted, "an agent is made of nothing at all")

        for what, at in wanted.items():
            self.assertTrue(at.is_dir(), f"making an agent did not make its {what}")

        for what, at in wanted.items():
            if what == "home":
                continue
            moved = at.with_name(at.name + ".moved")
            at.rename(moved)
            said = agent.diagnosed("ava", self.where, root=self.root)
            at.parent.mkdir(parents=True, exist_ok=True)
            moved.rename(at)
            self.assertEqual([one.about for one in said], [str(at)],
                             f"an agent with no {what} was not reported as missing it")

    def test_an_agent_is_made_with_the_records_it_keeps(self):
        """R-MIG-9, R-STO-11 — built by walking the steps from nothing rather than by
        writing the tables here, so the migration path is exercised by every agent anybody
        makes and a fresh install cannot drift from an upgraded one."""
        made = agent.add("ava", self.where)
        self.assertIn(store.NAME, made, "making an agent never said it made its records")

        kept = store.Store(store.path_for(agent.directory("ava", self.where)))
        kept.made()
        self.assertEqual(store.VERSION, kept.version())
        self.assertEqual({"provider": None, "model": None, "instructions": None,
                          "settings": {}}, kept.agent())

    def test_a_new_agent_needs_no_update_migration_turn(self):
        """The templates and the records arrive together for a new agent. A migration turn
        exists to reconcile homes from an older release, not to rewrite a home just made."""
        agent.add("ava", self.where)
        self.assertEqual([], agent.records("ava", self.where).pending_update_turns())

    def test_an_existing_home_without_records_still_gets_the_update_migration(self):
        """An agent from before records existed is not a fresh home. Repairing it creates
        records but must retain the release request that reconciles its old continuity."""
        loaded = agent.home("ava", self.where)
        loaded.mkdir(parents=True)
        (loaded / "AGENTS.md").write_text("# old rules\n", encoding="utf-8")
        (loaded / "MEMORY.md").write_text("# old memory\n", encoding="utf-8")
        (loaded / "SOUL.md").write_text("# old soul\n", encoding="utf-8")
        (loaded / "CLAUDE.md").write_text("# old bootstrap\n", encoding="utf-8")
        (loaded / "USER.md").write_text("# durable user fact\n", encoding="utf-8")

        agent.add("ava", self.where)

        self.assertEqual([5], [
            one["migration"]
            for one in agent.records("ava", self.where).pending_update_turns()
        ])

    def test_making_an_agent_again_leaves_the_records_it_already_had(self):
        """R-AGT-4 — making one that exists is the repair, and a repair that rebuilt the
        records would be the command an owner runs to fix an agent losing its history."""
        agent.add("ava", self.where)
        kept = store.Store(store.path_for(agent.directory("ava", self.where)))
        kept.made()
        kept.remember_agent(provider="codex")

        self.assertNotIn(store.NAME, agent.add("ava", self.where))
        self.assertEqual("codex", kept.agent()["provider"])

    def test_changing_a_brain_preserves_everything_the_agent_already_owns(self):
        """R-AGT-31 — configuration is one row, not a replacement agent."""
        agent.add("ava", self.where)
        kept = agent.records("ava", self.where)
        kept.remember_agent(provider="codex", model="o3", settings={"effort": "high"})
        kept.remember_channel(
            "ops", "discord", ["2207"], "2026-07-26T09:00:00Z")
        kept.remember_schedule(
            "nightly", "0 3 * * *", "2026-07-26T09:00:00Z",
            command=["/bin/echo", "hi"])
        conversation = store.conversation_id("ops", "thread")
        kept.opened(
            conversation, "ops", "discord", "thread", "2026-07-26T09:00:00Z")
        message = kept.arrived(
            conversation, "2026-07-26T09:01:00Z", "please remember", who="owner")
        run = kept.began(
            "channel", "codex", "safe", "2026-07-26T09:01:01Z",
            conversation_id=conversation, trigger_message_id=message,
            model="o3", settings={"effort": "high"})
        kept.recorded(
            run, 1, "2026-07-26T09:01:02Z", "think",
            event={"type": "think", "text": "working"})
        kept.answered(
            conversation, run, "2026-07-26T09:01:03Z", "remembered")
        kept.remember_session(conversation, "codex", "session-123")
        library = self.where / "skill-library"
        page = library / "kept-skill" / "SKILL.md"
        page.parent.mkdir(parents=True)
        page.write_text(
            "---\nname: kept-skill\ndescription: Use when proving preservation.\n---\n",
            encoding="utf-8")
        skill.grant(agent.skills("ava", self.where), "kept-skill", library)
        grant = agent.skills("ava", self.where) / "kept-skill"
        note = agent.home("ava", self.where) / "MEMORY.md"
        note.write_text("remember this\n", encoding="utf-8")
        before = {
            "channels": kept.channels(),
            "schedules": kept.schedules(),
            "conversations": kept.conversations(),
            "skills": sorted(path.name for path in agent.skills("ava", self.where).iterdir()),
            "skill-target": grant.readlink(),
            "memory": note.read_text(encoding="utf-8"),
            "directory": agent.directory("ava", self.where),
            "messages": kept.messages(conversation),
            "runs": kept.runs(conversation_id=conversation),
            "records": kept.records(run),
            "session": kept.session(conversation, "codex"),
        }

        agent.remember(
            "ava", self.where, provider="claude", replace_brain=True)

        self.assertEqual(before, {
            "channels": kept.channels(),
            "schedules": kept.schedules(),
            "conversations": kept.conversations(),
            "skills": sorted(path.name for path in agent.skills("ava", self.where).iterdir()),
            "skill-target": grant.readlink(),
            "memory": note.read_text(encoding="utf-8"),
            "directory": agent.directory("ava", self.where),
            "messages": kept.messages(conversation),
            "runs": kept.runs(conversation_id=conversation),
            "records": kept.records(run),
            "session": kept.session(conversation, "codex"),
        })
        self.assertEqual(
            {"provider": "claude", "model": None, "instructions": None, "settings": {}},
            kept.agent())

    def test_what_a_home_holds_is_what_there_is_a_template_for(self):
        """R-AGT-2 — a template added later lands in a new agent's home without anything
        being added to a list kept in code beside it."""
        agent.add("ava", self.where)
        copied = {path.name for path in agent.home("ava", self.where).iterdir()
                  if path.is_file()}
        self.assertEqual(copied, set(agent.knowledge()))
        self.assertTrue(copied, "this install has no templates to make an agent from")

    def test_a_template_is_copied_with_the_agents_own_name_in_it(self):
        """R-AGT-2"""
        agent.add("ava", self.where)
        says = (agent.home("ava", self.where) / "SOUL.md").read_text()
        self.assertIn("ava", says)
        self.assertNotIn(agent.AGENT, says, "a template reached the home unsubstituted")
        self.assertNotIn(agent.NAMED, says, "a legacy placeholder reached the home unsubstituted")

    def test_a_template_keeps_the_human_name_separate_from_its_slug(self):
        """R-AGT-39"""
        agent.add("ios-helper", self.where, display_name="iOS Helper")
        says = (agent.home("ios-helper", self.where) / "SOUL.md").read_text()
        self.assertIn("iOS Helper", says)
        self.assertEqual("iOS Helper", agent.display_name("ios-helper", self.where))

    def test_retry_repairs_display_name_after_interrupted_first_creation(self):
        """R-AGT-39 — a failed final write cannot permanently lose owner spelling."""
        with mock.patch.object(
            store.Store, "remember_display_name", side_effect=RuntimeError("interrupted")
        ):
            with self.assertRaises(RuntimeError):
                agent.add("ios-helper", self.where, display_name="iOS Helper")
        agent.add("ios-helper", self.where, display_name="IOS HELPER")
        self.assertEqual("iOS Helper", agent.display_name("ios-helper", self.where))
        self.assertEqual(
            [],
            agent.records("ios-helper", self.where).pending_update_turns(),
            "an interrupted fresh creation was mistaken for an existing-user migration",
        )

    def test_retry_before_database_creation_preserves_the_first_spelling(self):
        """R-AGT-39 — publishing pending identity state is exclusive and durable."""
        at = agent.directory("ios-helper", self.where)
        at.mkdir(parents=True)
        agent._write_pending(at / agent.DISPLAY_PENDING, "iOS Helper")
        agent.add("ios-helper", self.where, display_name="IOS HELPER")
        self.assertEqual("iOS Helper", agent.display_name("ios-helper", self.where))
        self.assertEqual(
            [],
            agent.records("ios-helper", self.where).pending_update_turns(),
            "a staged fresh creation was mistaken for an existing-user migration",
        )

    def test_retry_publishes_a_complete_staged_first_spelling(self):
        """R-AGT-39 — interruption after fsync but before link keeps the first name."""
        at = agent.directory("ios-helper", self.where)
        at.mkdir(parents=True)
        pending = at / agent.DISPLAY_PENDING
        pending.with_name(f"{pending.name}.writing").write_bytes(
            agent._display_record("iOS Helper")
        )
        agent.add("ios-helper", self.where, display_name="IOS HELPER")
        self.assertEqual("iOS Helper", agent.display_name("ios-helper", self.where))
        self.assertIn(
            "iOS Helper",
            (agent.home("ios-helper", self.where) / "SOUL.md").read_text(),
        )
        self.assertEqual(
            [],
            agent.records("ios-helper", self.where).pending_update_turns(),
            "a recovered fresh creation was mistaken for an existing-user migration",
        )

    def test_pending_staging_never_follows_an_owners_symlink(self):
        """R-AGT-4 — recovery state cannot overwrite another owner file."""
        at = agent.directory("ios-helper", self.where)
        at.mkdir(parents=True)
        owner = at / "owner-kept.txt"
        owner.write_text("KEEP ME")
        pending = at / agent.DISPLAY_PENDING
        pending.with_name(f"{pending.name}.writing").symlink_to(owner)
        with self.assertRaises(store.Unreadable):
            agent._write_pending(pending, "iOS Helper")
        self.assertEqual("KEEP ME", owner.read_text())

    def test_pending_staging_never_overwrites_an_owners_hard_link(self):
        """R-AGT-4 — an existing linked inode is owner data, not scratch space."""
        at = agent.directory("ios-helper", self.where)
        at.mkdir(parents=True)
        owner = at / "owner-kept.txt"
        owner.write_text("KEEP ME")
        pending = at / agent.DISPLAY_PENDING
        os.link(owner, pending.with_name(f"{pending.name}.writing"))
        with self.assertRaises(store.Unreadable):
            agent._write_pending(pending, "iOS Helper")
        self.assertEqual("KEEP ME", owner.read_text())

    def test_interruption_before_marker_does_not_make_a_stranded_agent(self):
        """R-AGT-39 — no `home/` exists until display recovery is durable."""
        with mock.patch.object(
            agent, "_write_pending", side_effect=RuntimeError("interrupted")
        ):
            with self.assertRaises(RuntimeError):
                agent.add("ios-helper", self.where, display_name="iOS Helper")
        self.assertFalse(agent.exists("ios-helper", self.where))
        agent.add("ios-helper", self.where, display_name="iOS Helper")
        self.assertEqual("iOS Helper", agent.display_name("ios-helper", self.where))

    def test_repair_alias_does_not_rewrite_a_completed_display_name(self):
        """R-AGT-4, R-AGT-39 — repair leaves the owner's existing identity alone."""
        agent.add("winston", self.where, display_name="winston")
        agent.add("winston", self.where, display_name="WINSTON")
        self.assertEqual("winston", agent.display_name("winston", self.where))

    def test_removing_an_interrupted_agent_removes_pending_identity_state(self):
        """R-AGW-2, R-AGW-4 — removal leaves no hidden name for a later agent."""
        with mock.patch.object(
            store.Store, "remember_display_name", side_effect=RuntimeError("interrupted")
        ):
            with self.assertRaises(RuntimeError):
                agent.add("ios-helper", self.where, display_name="iOS Helper")
        self.assertTrue(agent.creation_pending("ios-helper", self.where))
        pending = agent.directory("ios-helper", self.where) / agent.DISPLAY_PENDING
        pending.with_name(f"{pending.name}.writing").write_text("stale")
        agent.forget("ios-helper", self.where)
        self.assertFalse(agent.directory("ios-helper", self.where).exists())

    def test_an_install_with_nothing_to_make_an_agent_from_says_so(self):
        """R-AGT-11 — a home with no files in it and nothing to have copied there would
        otherwise be diagnosed as a working agent."""
        agent.add("ava", self.where)
        agent.remember("ava", self.where, provider="codex")   # R-AGT-18, as above
        nowhere = self.where / "no-templates"
        self.addCleanup(setattr, agent, "TEMPLATES", agent.TEMPLATES)
        agent.TEMPLATES = nowhere

        said = agent.diagnosed("ava", self.where, root=self.root)
        self.assertEqual([one.about for one in said], [str(nowhere)])

    def test_an_agent_is_named_by_the_one_who_made_it(self):
        """R-AGT-1"""
        agent.add("ava", self.where)
        agent.add("bo", self.where)
        self.assertEqual(agent.known(self.where), ["ava", "bo"])

    def test_two_agents_never_stand_in_one_place(self):
        """R-AGT-1"""
        self.assertNotEqual(agent.directory("ava", self.where), agent.directory("bo", self.where))

    def test_making_an_agent_again_leaves_what_was_written_in_it(self):
        """R-AGT-4 — making one that exists is how an owner repairs one they half deleted,
        and it must not be how they lose the rules they spent a month writing."""
        agent.add("ava", self.where)
        mine = agent.home("ava", self.where) / "SOUL.md"
        mine.write_text("what ava is for, in my own words", encoding="utf-8")
        before = tree(agent.directory("ava", self.where))

        self.assertEqual(agent.add("ava", self.where), [])
        self.assertEqual(tree(agent.directory("ava", self.where)), before,
                         "making an agent again wrote over what was already in its home")

    def test_making_an_agent_again_puts_back_only_what_is_missing(self):
        """R-AGT-4"""
        agent.add("ava", self.where)
        (agent.home("ava", self.where) / "MEMORY.md").unlink()
        shutil.rmtree(agent.skills("ava", self.where))

        self.assertEqual(agent.add("ava", self.where), ["MEMORY.md", "skills/"])

    def test_an_agent_is_only_one_that_has_a_home(self):
        """R-AGT-2 — a directory standing where agents are kept is not by itself an agent.
        Anything may leave one there; what makes one an agent is the home it loads from."""
        agent.add("ava", self.where)
        agent.forget("ava", self.where)
        agent.directory("ava", self.where).mkdir(parents=True, exist_ok=True)

        self.assertEqual(agent.known(self.where), [])
        self.assertFalse(agent.exists("ava", self.where))


class ANameThatCannotBeAnAgents(WithSomewhereToKeepAgents):
    def test_a_name_that_is_a_path_is_refused(self):
        """R-AGT-5"""
        for said in ("ava/bo", "../ava", "/ava", "..", "."):
            with self.assertRaises(agent.NotAnAgentName, msg=f"'{said}' was accepted"):
                agent.checked(said)

    def test_a_name_that_is_no_name_at_all_is_refused(self):
        """R-AGT-5"""
        for said in ("", "   ", "a b", "ava;bo", "..."):
            with self.assertRaises(agent.NotAnAgentName, msg=f"'{said}' was accepted"):
                agent.checked(said)

    def test_a_name_standing_on_a_link_out_of_where_agents_are_kept_is_refused(self):
        """R-AGT-5 — the character check cannot see this one: the name is a plain word, and
        what it reaches is decided by a link already standing under it."""
        somewhere_else = Path(tempfile.mkdtemp(prefix="rundesk-elsewhere-"))
        self.addCleanup(shutil.rmtree, somewhere_else, True)
        os.symlink(somewhere_else, self.where / "sneaky")

        with self.assertRaises(agent.NotAnAgentName):
            agent.home("sneaky", self.where)

    def test_a_name_a_gateway_would_take_for_something_it_wrote_is_refused(self):
        """R-AGT-6 — a gateway named `foo` writes `foo.log`, which is the file an agent
        called `foo.log` would want for itself. The list is what the path helpers actually
        write today, and it has shrunk: `foo.ran.json` and `foo.seen.json` are not among them
        any more, because what a schedule last did and when a gateway was last up are rows.
        So `foo.ran` and `foo.seen` are ordinary names again."""
        for said in ("ava.interrupted", "ava.log", "ava.lock",
                     "ava.json", "ava.out", "ava.err", "ava.changing", "ava.writing"):
            with self.assertRaises(agent.NotAnAgentName, msg=f"'{said}' was accepted"):
                agent.checked(said)

    def test_a_name_that_merely_has_a_dot_in_it_is_still_a_name(self):
        """R-AGT-6 — the refusal is of the words a gateway writes, not of the punctuation."""
        self.assertEqual(agent.checked("ava.two"), "ava.two")

    def test_what_a_gateway_writes_is_asked_of_it_rather_than_listed(self):
        """R-AGT-6 — the teeth. A sidecar added later is covered the day it lands, because
        this fails when a path helper writes a suffix nothing declared."""
        writes = (gateway.log_path, gateway.interrupted_path)
        for helper in writes:
            added = helper(gateway._PROBE, Path(os.sep)).name[len(gateway._PROBE):]
            self.assertIn(added, gateway.reserved_suffixes(),
                          f"{helper.__name__} writes '{added}', which no name is refused for")


class OneAgentIsKeptFromAnother(WithSomewhereToKeepAgents):
    def test_no_two_agents_resolve_to_one_workspace(self):
        """R-AGT-7"""
        self.assertNotEqual(agent.workspace("ava", self.where), agent.workspace("bo", self.where))

    def test_no_two_agents_share_the_private_home_a_provider_is_given(self):
        """R-AGT-8"""
        self.assertNotEqual(agent.provider_home("ava", "claude", self.where),
                            agent.provider_home("bo", "claude", self.where))

    def test_one_agent_keeps_two_providers_apart(self):
        """R-AGT-8"""
        self.assertNotEqual(agent.provider_home("ava", "claude", self.where),
                            agent.provider_home("ava", "codex", self.where))

    def test_the_private_home_a_provider_is_given_stands_outside_what_the_agent_loads(self):
        """R-AGT-8 — a provider's configuration and sign-in are rundesk's state about a
        pair, not knowledge the agent loads."""
        given = agent.provider_home("ava", "claude", self.where)
        self.assertNotIn(agent.home("ava", self.where), given.parents)


class WhatStandsBetweenAnAgentAndATurn(WithSomewhereToKeepAgents):
    def test_an_agent_that_has_everything_is_diagnosed_with_nothing(self):
        """R-AGT-11"""
        self.made()
        self.assertEqual(agent.diagnosed("ava", self.where, root=self.root), [])

    def test_an_agent_missing_what_it_loads_says_which_file(self):
        """R-AGT-11"""
        self.made()
        (agent.home("ava", self.where) / "SOUL.md").unlink()

        said = agent.diagnosed("ava", self.where, root=self.root)
        self.assertEqual([one.about for one in said],
                         [str(agent.home("ava", self.where) / "SOUL.md")])

    def test_an_agent_that_was_never_made_is_said_to_be_missing(self):
        """R-AGT-11"""
        said = agent.diagnosed("ava", self.where, root=self.root)
        self.assertEqual(len(said), 1)
        self.assertIn("no agent", said[0].said)

    def test_an_agent_that_cannot_be_written_to_says_so(self):
        """R-AGT-11"""
        self.made()
        held = agent.workspace("ava", self.where)
        was = held.stat().st_mode
        held.chmod(0o500)
        self.addCleanup(held.chmod, was)

        if os.access(held, os.W_OK):
            self.skipTest("running as someone every mode lets through")
        said = agent.diagnosed("ava", self.where, root=self.root)
        self.assertEqual([one.about for one in said], [str(held)])

    def test_an_install_that_does_not_fit_stands_between_an_agent_and_a_turn(self):
        """R-AGT-11 — asked of the install rather than of the agent, because the agent is
        fine and nothing it is asked to do will work."""
        (self.root / ".venv" / "lib" / "python3.0").mkdir(parents=True)
        self.made()

        said = agent.diagnosed("ava", self.where, root=self.root)
        self.assertEqual([one.about for one in said], ["this install"])

    def test_diagnosing_an_agent_changes_nothing_about_it(self):
        """R-AGT-12 — an owner asking what is wrong is usually asking because something
        already is, and a check that repaired what it found would answer a different
        question the next time it was asked. What a diagnosis reads is asked of a read-only
        connection, so nothing it finds is written back and no records are built."""
        self.made()
        (agent.home("ava", self.where) / "MEMORY.md").unlink()
        before = tree(self.where)

        agent.diagnosed("ava", self.where, root=self.root)
        self.assertEqual(tree(self.where), before, "diagnosing an agent wrote something")

    def test_diagnosing_an_agent_never_builds_the_records_it_reads(self):
        """R-AGT-12, R-STO-13 — asking what shape records are in through anything that may
        also *make* them turns the one command an owner runs when an agent is broken into
        the one that quietly repairs it. Records written partway are the case: they are not
        absent, so a diagnosis reports them and leaves them exactly as they are for somebody
        to look at."""
        self.made()
        at = store.path_for(agent.directory("ava", self.where))
        for gone in store.removes(agent.directory("ava", self.where)):
            if gone.exists():
                gone.unlink()
        at.write_bytes(b"")

        said = agent.diagnosed("ava", self.where, root=self.root)
        self.assertEqual(b"", at.read_bytes(), "a diagnosis rebuilt the records it read")
        self.assertIn(str(at), [one.about for one in said],
                      "records that cannot be read were passed over in silence")

    def test_diagnosing_an_agent_that_is_not_there_changes_nothing(self):
        """R-AGT-12"""
        before = tree(self.where)
        agent.diagnosed("ava", self.where, root=self.root)
        self.assertEqual(tree(self.where), before, "diagnosing a missing agent made one")


class TheGatewayThatRunsIt(WithSomewhereToKeepAgents):
    def gateway_for(self, name: str) -> gateway.Gateway:
        made = gateway.Gateway(name, where=agent.run_home(name, self.where),
                               logs=agent.logs_home(name, self.where),
                               root=self.root)
        self.addCleanup(made.release)
        return made

    def test_making_an_agent_makes_the_gateway_that_runs_it(self):
        """R-AGW-1 — the gateway is the two directories beside the home and the records
        beside those, so there is no second step and no way to end up with one and not the
        other."""
        self.made()
        for at in (agent.run_home("ava", self.where), agent.logs_home("ava", self.where)):
            self.assertTrue(at.is_dir(), f"{at} was not made with the agent")
        self.assertTrue(store.path_for(agent.directory("ava", self.where)).exists(),
                        "the agent was made with nowhere to keep its schedules")

        running = self.gateway_for("ava")
        running.claim()
        self.assertTrue(gateway.standing("ava", agent.run_home("ava", self.where)).running)

    def test_a_gateway_keeps_what_it_is_doing_where_its_agent_does(self):
        """R-AGW-1 — an agent supervised by the machine and one asked about from a terminal
        have to resolve one place, and the way they come apart is two of them."""
        self.made()
        running = self.gateway_for("ava")
        running.claim()

        kept = agent.run_home("ava", self.where)
        self.assertTrue((kept / "ava.lock").exists())
        self.assertEqual(sorted(it.name for it in gateway.every(kept)), ["ava"])

    def test_taking_an_agent_away_takes_the_gateway_that_ran_it(self):
        """R-AGW-2"""
        self.made()
        agent.forget("ava", self.where)
        self.assertFalse(agent.directory("ava", self.where).exists())

    def test_taking_an_agent_away_takes_the_schedules_that_were_its_own(self):
        """R-AGW-4 — otherwise adding the name back inherits work nobody asked for, from an
        agent that no longer exists."""
        self.made()
        agent.records("ava", self.where).remember_schedule(
            "tidy", "0 3 * * *", "2026-07-26T09:00:00Z", command=["/bin/echo", "hi"])

        agent.forget("ava", self.where)
        agent.add("ava", self.where)
        self.assertEqual([], agent.records("ava", self.where).schedules())

    def test_taking_an_agent_away_takes_what_its_schedules_did(self):
        """R-AGW-5 — what is scheduled and what each schedule last did sat in two files side
        by side, and only the first went. The second was then inherited by whoever took the
        name next, which is a new agent reading an old one's account of itself. They are one
        row now, so the two cannot come apart."""
        self.made()
        kept = agent.records("ava", self.where)
        kept.remember_schedule("tidy", "0 3 * * *", "2026-07-26T09:00:00Z",
                               command=["/bin/echo", "hi"])
        kept.schedule_fired("tidy", "2026-07-26 03:00", "finished")

        agent.forget("ava", self.where)
        self.assertFalse(store.path_for(agent.directory("ava", self.where)).exists(),
                         "the work and its account were inherited")

    def test_taking_an_agent_away_takes_the_channels_it_was_reachable_on(self):
        """R-AGW-4, R-CAD-10 — the worst thing a name can inherit. An agent added back
        under a name that was on somebody's server would be on it again, answering
        whoever was allowed then, without anybody having asked for either."""
        self.made()
        agent.records("ava", self.where).remember_channel(
            "ops", "discord", ["2207"], "2026-07-26T09:00:00Z")
        agent.channel_home("ava", "ops", self.where).mkdir(parents=True, exist_ok=True)

        agent.forget("ava", self.where)
        agent.add("ava", self.where)
        self.assertEqual([], agent.reading("ava", self.where).channels(),
                         "a new agent inherited who was allowed to reach the old one")
        self.assertFalse(agent.channel_home("ava", "ops", self.where).exists())

    def test_taking_an_agent_away_takes_what_its_conversations_got_to(self):
        """R-AGW-4 — the same rule, and the reason it is a rule rather than a list of
        names: where each conversation had got to outlived the agent and was handed to
        the next one to take the name, because nothing had thought to name that file."""
        self.made()
        where_it_is = store.conversation_id("terminal", "terminal")
        kept = agent.records("ava", self.where)
        kept.opened(where_it_is, "terminal", "terminal", "terminal", "2026-07-26T09:00:00Z")
        kept.remember_session(where_it_is, "codex", "abc-123")
        agent.remember("ava", self.where, provider="codex")

        agent.forget("ava", self.where)
        agent.add("ava", self.where)
        back = agent.reading("ava", self.where)
        self.assertIsNone(back.session(where_it_is, "codex"),
                          "a new agent carried on from the old one's conversation")
        self.assertIsNone(back.agent()["provider"],
                          "a new agent inherited the brain the old one reached for")

    def test_nothing_of_an_agents_records_is_left_behind(self):
        """R-AGW-5, R-STO-14 — `state.db` is named rather than swept up: the removal takes
        `*.json` and `*.changing`, which is none of the three files a database is while it
        is in WAL, so all three survived every removal and the two beside it are the
        database's own rather than ours to leave lying about."""
        self.made()
        stands = agent.directory("ava", self.where)
        for beside in store.removes(stands):
            beside.write_bytes(b"")

        agent.forget("ava", self.where)
        self.assertEqual([], [one.name for one in store.removes(stands) if one.exists()])

    def test_where_an_agent_keeps_things_is_its_own(self):
        """R-AGT-9 — asked once and handed on, because a command working these out for
        itself in three places is how a gateway comes to write where nothing reads."""
        self.made()
        said = agent.resolved("ava", self.where)
        self.assertEqual(said.run, agent.run_home("ava", self.where))
        self.assertEqual(said.logs, agent.logs_home("ava", self.where))

    def test_a_name_with_no_agent_keeps_things_where_it_always_did(self):
        """R-AGT-9 — a gateway that has no agent yet goes on being reached exactly as it
        was, so nothing already running has to be adopted before it works."""
        said = agent.resolved("gateway", self.where)
        self.assertEqual((said.run, said.logs), (None, None))

    def test_taking_an_agent_away_takes_the_account_of_what_it_did(self):
        """R-AGW-5 — one outcome, not two. What was kept behind a second flag was left for
        whoever took the name next, and an account nobody can name an agent for is an
        account nobody reads."""
        self.made()
        gateway.note("ava", "something happened", agent.logs_home("ava", self.where))

        agent.forget("ava", self.where)
        self.assertFalse(agent.logs_home("ava", self.where).exists())
        self.assertFalse(agent.directory("ava", self.where).exists())


class WhatEveryTurnForThisAgentIsTold(WithSomewhereToKeepAgents):
    """R-AGT-16 — every applicable instruction is appended in one stable order.

    Rundesk's trigger context, the agent owner's instructions, and the turn's own
    instructions answer different questions. None silently displaces another.
    """

    def situation(self, said: str) -> str:
        """What a turn was told *after* rundesk's own words, which always come first.

        Every case below is about which situation wins; that ours is there at all is
        R-AGT-17's, tested on its own. Asserted here rather than assumed, so a change that
        dropped the standing words would fail every one of these rather than none.
        """
        standing = agent.standing("ava", self.where)
        self.assertTrue(said.startswith(standing),
                        "rundesk's own words did not come first")
        return said[len(standing):].strip()

    def test_turn_instructions_append_after_agent_instructions(self):
        """R-AGT-16 — a command adds instructions without displacing either earlier layer."""
        self.made()
        agent.remember("ava", self.where, instructions="what the agent says")
        self.assertEqual("what rundesk would say\n\nwhat the agent says\n\nwhat this turn says",
                         self.situation(agent.told("ava", self.where, said="what this turn says",
                                    regardless="what rundesk would say")))

    def test_agent_instructions_append_after_rundesk_context(self):
        """R-AGT-16 — the stored owner layer follows, rather than replacing, core context."""
        self.made()
        agent.remember("ava", self.where, instructions="what the agent says")
        self.assertEqual("what rundesk would say\n\nwhat the agent says",
                         self.situation(agent.told("ava", self.where,
                                                   regardless="what rundesk would say")))

    def test_rundesks_own_line_is_last(self):
        """R-AGT-16 — something that says what the situation is beats something that says
        nothing, and an owner who disagrees says so by writing their own."""
        self.made()
        self.assertEqual("what rundesk would say",
                         self.situation(agent.told("ava", self.where,
                                                   regardless="what rundesk would say")))

    def test_nothing_anywhere_is_nothing_rather_than_a_guess(self):
        """R-AGT-16 — a person at a terminal is watching, so there is nothing to tell them
        about the situation and nothing is what they get."""
        self.made()
        self.assertEqual("", self.situation(agent.told("ava", self.where)))

    def test_what_an_agent_is_told_is_kept_and_read_back(self):
        """R-AGT-16 — written where an agent's brain is written, because `add` is what an
        owner types to say what an agent *is* (R-AGT-4)."""
        self.made()
        agent.remember("ava", self.where, instructions="be brief")
        self.assertEqual("be brief", agent.chosen("ava", self.where)["instructions"])
        agent.remember("ava", self.where, model="fast-1")
        self.assertEqual("be brief", agent.chosen("ava", self.where)["instructions"],
                         "naming a model quietly forgot what the agent is told")

    def test_taking_what_an_agent_is_told_off_leaves_nothing_behind(self):
        """R-AGT-16 — an owner clearing it has said something, and reading that as silence
        would leave the old text in place for ever."""
        self.made()
        agent.remember("ava", self.where, instructions="be brief")
        agent.remember("ava", self.where, instructions="")
        self.assertEqual("what rundesk would say",
                         self.situation(agent.told("ava", self.where,
                                                   regardless="what rundesk would say")))

    def test_a_turn_the_clock_started_is_told_nobody_is_watching(self):
        """R-SCH-30 — the first trigger with no person at the other end. The fact that matters
        most is that a question will not be answered: a brain that asks one into an empty room
        is a turn that ends waiting."""
        from rundesk import schedule
        said = schedule.by_default("nightly")
        self.assertIn("nightly", said, "it never said which schedule started this")
        self.assertIn("No user request started it", said)
        self.assertIn("Nothing will answer", said)
        self.assertIn("recorded", said, "it never said what becomes of what it says")

    def test_a_turn_the_clock_started_is_told_what_it_delivers(self):
        """R-SCH-30 — the one fact here a brain cannot find out for itself. Measured: two
        schedules that displaced nothing were told nobody was watching and narrated anyway,
        because the sentence answered *whether to ask a question* and said nothing about
        *when to speak* — so three paragraphs of orientation reached the owner with the
        report underneath them."""
        from rundesk import schedule
        said = schedule.by_default("nightly")
        self.assertIn("last complete message you write is delivered", said,
                      "it never said what becomes of everything before the last")
        self.assertIn("Write nothing until the work is finished", said,
                      "a brain cannot tell which thought will be its last, so the rule it "
                      "can actually follow has to be the one it is given")

    def test_a_backend_update_turn_gets_only_its_truthful_delivery_rule(self):
        """R-MIG-24 — an update turn is schedule-scoped but reports only to the account.
        The ordinary promise that Rundesk posts its final message must not contradict that."""
        from rundesk import schedule

        self.made()
        captured = {}

        async def carrying(_name, _prompt, _provider, **held):
            captured.update(held)
            return object()

        one = schedule.Schedule(
            name="rundesk-update-5",
            at="2026-07-30 12:00",
            ran_at="2026-07-30 12:00",
            prompt="migrate",
            instructions="recorded only in this agent's account; never posted",
            backend=True,
        )
        asyncio.run(agent.asking("ava", self.where, carry=carrying)(one))

        preface = self.situation(captured["preface"])
        self.assertEqual(
            "recorded only in this agent's account; never posted",
            preface,
        )
        self.assertNotIn("## Scheduled run", captured["preface"])

    def test_what_rundesk_says_about_a_scheduled_turn_is_there_whatever_the_owner_wrote(self):
        """R-AGT-34 — the tier this moved out of. As the situation tier's last resort, an
        owner writing anything at all deleted it: a schedule told to focus on high-priority
        issues was no longer told that nobody was watching or what it delivers."""
        self.made()
        agent.remember("ava", self.where, instructions="what the agent says")
        for said in ("", "focus on the high-priority issues"):
            told = self.situation(agent.told("ava", self.where, said=said,
                                             regardless="nobody is watching"))
            self.assertTrue(told.startswith("nobody is watching"),
                            f"what rundesk says was displaced by {said!r}: {told!r}")

    def test_what_an_owner_says_about_a_scheduled_turn_is_added_to_rundesks_own(self):
        """R-AGT-34 — added, not replaced, and in that order: they answer different
        questions. Rundesk's says what the situation *is* and the owner's says what to *do*
        about it, and a turn needs both."""
        self.made()
        agent.remember("ava", self.where, instructions="what the agent says")
        self.assertEqual("nobody is watching\n\nwhat the agent says\n\n"
                         "focus on the high-priority issues",
                         self.situation(agent.told(
                             "ava", self.where, said="focus on the high-priority issues",
                             regardless="nobody is watching")))
        self.assertEqual("nobody is watching\n\nwhat the agent says",
                         self.situation(agent.told("ava", self.where,
                                                   regardless="nobody is watching")),
                         "the agent's own tier stopped being reached")

    def test_what_rundesk_always_says_is_nothing_where_there_is_nothing_to_say(self):
        """R-AGT-34 — a person at a terminal is watching, so nothing is added and the turn is
        told exactly what it was told before this existed."""
        self.made()
        agent.remember("ava", self.where, instructions="what the agent says")
        self.assertEqual("what the agent says",
                         self.situation(agent.told("ava", self.where, regardless="")))


class AGatewayThatHasNoAgentYet(WithSomewhereToKeepAgents):
    def wrote(self, name: str = "gateway") -> None:
        """A gateway of this name, with a log and an account of what it never finished, kept
        the way they were kept before there were agents to own them.

        There is no schedules file here any more, and that is the point: a schedule is a row
        an agent keeps, so a legacy one has nothing to adopt and nothing reads one."""
        gateway.note(name, "before there were agents", self.before / "logs")
        gateway.interrupted_path(name, self.before / "logs").write_text(
            json.dumps({"turn": {"ended": False}}), encoding="utf-8")

    def test_adopting_a_gateway_moves_what_it_wrote_into_the_agents_own(self):
        """R-AGW-1 — nothing moves on its own, and this is what an owner typing the name
        asks for: one place afterwards, rather than two that disagree."""
        self.wrote()
        agent.add("gateway", self.where)

        agent.adopt("gateway", self.where, logs=self.before / "logs")

        into = agent.logs_home("gateway", self.where)
        self.assertIn("before there were agents", gateway.log_path("gateway", into).read_text())
        self.assertTrue(gateway.interrupted_path("gateway", into).exists())
        self.assertFalse(gateway.interrupted_path("gateway", self.before / "logs").exists(),
                         "what was adopted is still where it was, so two places now disagree")

    def test_adopting_a_gateway_brings_what_its_log_rotated_into_along(self):
        """R-AGW-5 — the part just before something happened is the part worth having, and
        it is the part a rotation moved out of the file everyone reads."""
        self.wrote()
        (self.before / "logs" / "gateway.log.1").write_text("older still", encoding="utf-8")
        agent.add("gateway", self.where)

        agent.adopt("gateway", self.where, logs=self.before / "logs")

        self.assertEqual((agent.logs_home("gateway", self.where) / "gateway.log.1").read_text(),
                         "older still")

    def test_nothing_is_adopted_while_a_gateway_of_that_name_is_running(self):
        """R-AGT-9 — a gateway binds the directory it writes in once, when it starts, and
        never looks again. Moving those files out from under a live one leaves it writing
        where nothing reads for the rest of its life.

        The name is held across the move rather than asked about before it, because asking
        and then moving is two decisions with a gap, and a gateway can claim the name
        inside that gap."""
        self.wrote()
        agent.add("gateway", self.where)
        running = gateway.Gateway("gateway", where=self.before / "run",
                                  logs=self.before / "logs", root=self.root)
        running.claim()
        self.addCleanup(running.release)

        with self.assertRaises(agent.InUse):
            agent.adopt("gateway", self.where, logs=self.before / "logs",
                        run=self.before / "run")

        self.assertTrue(gateway.interrupted_path("gateway", self.before / "logs").exists(),
                        "it moved what a running gateway is writing")

    def test_what_a_stopped_gateway_wrote_is_adopted_once_it_lets_the_name_go(self):
        """R-AGT-9 — the other half, so refusing cannot pass by never adopting anything."""
        self.wrote()
        agent.add("gateway", self.where)
        running = gateway.Gateway("gateway", where=self.before / "run",
                                  logs=self.before / "logs", root=self.root)
        running.claim()
        running.release()

        agent.adopt("gateway", self.where, logs=self.before / "logs", run=self.before / "run")
        self.assertFalse(gateway.interrupted_path("gateway", self.before / "logs").exists(),
                         "nothing moved once the name was free")

    def test_adopting_a_gateway_that_wrote_nothing_moves_nothing(self):
        """R-AGW-1"""
        agent.add("fresh", self.where)
        self.assertEqual([], agent.adopt("fresh", self.where, logs=self.before / "logs"))


class AnAgentNeedsABrain(WithSomewhereToKeepAgents):
    """R-AGT-18 — an agent that cannot take a turn is not a thing to have made."""

    def test_an_agent_with_no_brain_is_not_ready(self):
        """`doctor` promises what stands between an agent and a working turn, and answered
        READY for one that refuses every turn it is given. A diagnosis claiming a success it
        has not earned is the one failure this command exists to prevent."""
        self.made()
        agent.remember("ava", self.where, provider="")
        found = agent.diagnosed("ava", self.where, root=self.root)
        self.assertTrue(any("which brain" in one.said for one in found),
                        f"a brainless agent was called ready: {found}")

    def test_what_is_wrong_says_how_to_put_it_right(self):
        """R-AGT-19 — the complaint names the command, because an owner reading NOT READY
        is asking what to type next.

        The command has a field of its own now rather than standing in for the place the
        fault is: `about` is where, `said` is what, and `fix` is what to type. Carried in
        `about`, one complaint's location was a command and every other one's was a path,
        so nothing could be relied on to print them the same way.
        """
        self.made()
        agent.remember("ava", self.where, provider="")
        found = [one for one in agent.diagnosed("ava", self.where, root=self.root)
                 if "which brain" in one.said]
        self.assertIn("--provider", found[0].fix)

    def test_records_behind_what_this_install_expects_are_reported_with_the_way_out(self):
        """R-AGT-20 — where these records stand, said by the command an owner already runs
        to find out what is wrong.

        Read without opening a store, which refuses records it will not read — and refusing
        is the right answer for a turn and the wrong one for the check that exists to
        explain it. This is what an update interrupted before it moved anything leaves
        behind, and it had no way of being seen at all.
        """
        self.made()
        agent.remember("ava", self.where, provider="codex")
        at = store.path_for(agent.directory("ava", self.where))
        conn = sqlite3.connect(str(at), isolation_level=None)
        self.addCleanup(conn.close)
        conn.execute("PRAGMA user_version = 0")

        found = [one for one in agent.diagnosed("ava", self.where, root=self.root)
                 if "expects" in one.said]
        self.assertEqual(1, len(found), "records behind this install were not reported")
        self.assertIn(str(store.VERSION), found[0].said, "it never said what is expected")
        self.assertEqual("rundesk update", found[0].fix)

    def test_every_complaint_says_what_to_type_next(self):
        """R-AGT-19 — and not only the one that happened to be written that way. A
        diagnosis is run *because* something is wrong, so a fault with no way out leaves an
        owner doing the diagnosis a second time themselves."""
        self.made()
        agent.remember("ava", self.where, provider="")
        for one in agent.diagnosed("ava", self.where, root=self.root):
            self.assertTrue(one.fix, f"nothing says what to do about: {one.said}")

    def test_an_agent_with_a_brain_is_not_complained_about(self):
        """The other half: a named brain that runs is nothing to report."""
        self.made()
        agent.remember("ava", self.where, provider="codex")
        found = agent.diagnosed("ava", self.where, root=self.root, runnable=lambda one: None)
        self.assertEqual([], [one for one in found if "which brain" in one.said])


class WhatAChannelMayInspect(WithSomewhereToKeepAgents):
    """R-CAD-17 — the agent layer answers without teaching the gateway about agents."""

    def test_status_names_the_agent_and_its_gateway_state(self):
        self.made()
        said = agent._queried("ava", "status", self.where)
        self.assertIn("ava: STOPPED", said)
        self.assertIn("active turns: 0", said)

    def test_version_tells_installed_code_from_the_running_gateway(self):
        self.made()
        install = self.root / "install"
        package = install / "src" / "rundesk"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text('__version__ = "8.7.6"\n')
        original = agent.ROOT
        agent.ROOT = install
        try:
            said = agent._queried("ava", "version", self.where)
        finally:
            agent.ROOT = original
        self.assertIn("Rundesk installed: 8.7.6", said)
        self.assertIn("ava gateway: not running", said)

    def test_agents_lists_every_configured_agent_in_name_order(self):
        self.made("zebra")
        self.made("ava")
        said = agent._queried("ava", "agents", self.where).splitlines()
        self.assertEqual(["ava: STOPPED (-)", "zebra: STOPPED (-)"], said)

    def test_skills_lists_only_this_agents_grants_as_sorted_bullets(self):
        """R-DIS-36 — the shared library and another agent's grants are not this
        agent's capabilities."""
        self.made("ava")
        self.made("zebra")
        library = self.before / "data" / "skills"
        for called in ("alpha", "only-zebra", "ungranted", "zulu"):
            page = library / called / "SKILL.md"
            page.parent.mkdir(parents=True)
            page.write_text(
                f"---\nname: {called}\ndescription: Use for this test.\n---\n",
                encoding="utf-8",
            )
        skill.grant(agent.skills("ava", self.where), "zulu", library)
        skill.grant(agent.skills("ava", self.where), "alpha", library)
        skill.grant(agent.skills("zebra", self.where), "only-zebra", library)

        said = agent._queried("ava", "skills", self.where).splitlines()

        self.assertEqual(["- alpha", "- zulu"], said)

    def test_skills_says_when_this_agent_has_no_grants(self):
        """R-DIS-36 — an empty answer is not an unexplained blank interaction."""
        self.made()
        self.assertEqual("No skills granted.",
                         agent._queried("ava", "skills", self.where))

    def test_help_names_read_only_conversation_and_agent_commands(self):
        self.made()
        said = agent._queried("ava", "help", self.where)
        self.assertIn("status, version, agents, skills, help", said)
        self.assertIn("stop, forget", said)
        self.assertIn("restart", said)
        self.assertNotIn("/", said, "the agent layer invented a platform's command syntax")


class WhatRundeskItselfTellsEveryTurn(WithSomewhereToKeepAgents):
    """R-AGT-17 — rundesk's own words reach a turn whatever anybody else said."""

    def test_the_agents_own_name_is_filled_in(self):
        """A placeholder that survived would reach the brain as a literal rather than the
        identity and locations Rundesk resolved for this agent."""
        said = agent.standing("ava", self.where)
        self.assertIn("You are ava,", said)
        self.assertIn(str(agent.home("ava", self.where)), said)
        self.assertIn(str(agent.workspace("ava", self.where)), said)
        self.assertNotIn("{", said, "a brace survived into what a brain is given")
        self.assertNotIn("}", said)

    def test_the_human_name_is_shown_while_commands_keep_the_slug(self):
        """R-AGT-39 — identity prose uses the display name; paths and commands remain
        safe because they use the directory slug."""
        agent.add("ios-helper", self.where, display_name="iOS Helper")
        said = agent.standing("ios-helper", self.where)
        self.assertIn("You are iOS Helper,", said)
        self.assertIn("rundesk messages ios-helper", said)

    def test_every_place_the_name_appears_is_filled_in(self):
        """Not just the first: every command must name the agent it will actually query."""
        said = agent.standing("zebra", self.where)
        self.assertEqual(0, said.count("{agent}"))
        self.assertGreater(said.count("zebra"), 1)
        self.assertIn("rundesk messages zebra", said)

    def test_rundesks_own_words_reach_a_turn_that_was_told_nothing_else(self):
        self.made()
        self.assertEqual(agent.standing("ava", self.where), agent.told("ava", self.where))

    def test_what_an_owner_says_is_added_to_rundesks_rather_than_replacing_it(self):
        """The whole point. They answer different questions — ours says what the agent is and
        how to find what it did, theirs says what to do about this situation — so an agent
        whose owner wrote instructions must not lose the first for having the second."""
        self.made()
        agent.remember("ava", self.where, instructions="be brief")
        said = agent.told("ava", self.where)
        self.assertIn("rundesk messages ava", said, "rundesk's own words were replaced")
        self.assertIn("be brief", said, "the owner's words were dropped")

    def test_rundesks_own_words_come_first(self):
        """Ours is the same on every turn and theirs is not, so ours is the part that caches.
        Putting anything that varies in front of it would spend that on every turn."""
        self.made()
        agent.remember("ava", self.where, instructions="be brief")
        said = agent.told("ava", self.where, said="and answer in French")
        self.assertTrue(said.startswith(agent.standing("ava", self.where)))
        self.assertLess(said.index("rundesk messages ava"), said.index("and answer in French"))

    def test_what_rundesk_says_is_the_same_words_every_turn(self):
        """What prompt caching keys on. Two turns for one agent must be byte-for-byte equal
        here, or the front of the prefix moves and every turn pays for it again."""
        self.assertEqual(
            agent.standing("ava", self.where), agent.standing("ava", self.where)
        )
        self.assertNotEqual(
            agent.standing("ava", self.where), agent.standing("bea", self.where)
        )

    def test_a_turn_is_told_how_to_find_what_it_did(self):
        """The core names the history commands and the skill holding broader guidance."""
        said = agent.standing("ava", self.where)
        self.assertIn("rundesk messages ava", said)
        self.assertIn("managing-rundesk", said)


if __name__ == "__main__":
    unittest.main(verbosity=2)
