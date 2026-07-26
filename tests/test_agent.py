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

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rundesk import agent, gateway, store  # noqa: E402


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
        for said, at in (("RUNDESK_AGENTS_DIR", self.where),
                         ("RUNDESK_RUN_DIR", self.before / "run"),
                         ("RUNDESK_LOG_DIR", self.before / "logs"),
                         ("RUNDESK_SCHEDULES_DIR", self.before / "schedules"),
                         ("RUNDESK_JOBS_DIR", self.before / "jobs")):
            self.addCleanup(os.environ.pop, said, None)
            os.environ[said] = str(at)
            # Made rather than left to whatever writes there first: `gateway.note` appends
            # to a log without making the directory and swallows the failure, so a case
            # that arranges a log in scratch gets silence instead of a log.
            at.mkdir(parents=True, exist_ok=True)

    def made(self, name: str = "ava") -> str:
        agent.add(name, self.where)
        return name


class AnAgentIsMade(WithSomewhereToKeepAgents):
    def test_an_agent_is_made_with_the_files_it_loads(self):
        """R-AGT-2"""
        agent.add("ava", self.where)
        for called in agent.knowledge():
            self.assertTrue((agent.home("ava", self.where) / called).is_file(),
                            f"a new agent has no {called} to load")
        self.assertTrue(agent.workspace("ava", self.where).is_dir())
        self.assertTrue(agent.skills("ava", self.where).is_dir())

    def test_what_an_agent_loads_holds_nothing_rundesk_keeps(self):
        """R-AGT-2 — the home is what the agent loads. A provider reading its own rules
        must not be reading rundesk's lock, log and schedules, which is what putting them
        in one directory would have meant."""
        agent.add("ava", self.where)
        standing = {path.name for path in agent.home("ava", self.where).iterdir()}
        self.assertEqual(standing, set(agent.knowledge()) | set(agent.WORKING))

    def test_the_file_every_provider_loads_names_the_ones_none_of_them_do(self):
        """R-AGT-2 — the two files that are loaded because of where they stand are the only
        way the other three are reached at all: no provider follows a link for free, and
        only one of them expands an import. Drop the reference and an agent quietly loses
        its character with nothing else failing, which is why this is asserted and not
        merely written."""
        agent.add("ava", self.where)
        for called in ("AGENTS.md", "CLAUDE.md"):
            says = (agent.home("ava", self.where) / called).read_text()
            for reached in ("SOUL.md", "USER.md", "MEMORY.md"):
                self.assertIn(reached, says, f"{called} no longer reaches {reached}")

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

    def test_making_an_agent_again_leaves_the_records_it_already_had(self):
        """R-AGT-4 — making one that exists is the repair, and a repair that rebuilt the
        records would be the command an owner runs to fix an agent losing its history."""
        agent.add("ava", self.where)
        kept = store.Store(store.path_for(agent.directory("ava", self.where)))
        kept.made()
        kept.remember_agent(provider="codex")

        self.assertNotIn(store.NAME, agent.add("ava", self.where))
        self.assertEqual("codex", kept.agent()["provider"])

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
        self.assertNotIn(agent.NAMED, says, "a template reached the home unsubstituted")

    def test_an_install_with_nothing_to_make_an_agent_from_says_so(self):
        """R-AGT-11 — a home with no files in it and nothing to have copied there would
        otherwise be diagnosed as a working agent."""
        agent.add("ava", self.where)
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
        (agent.home("ava", self.where) / "USER.md").unlink()
        shutil.rmtree(agent.skills("ava", self.where))

        self.assertEqual(agent.add("ava", self.where), ["USER.md", "skills/"])

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
        """R-AGT-6 — a gateway named `foo` writes `foo.ran.json`, which is the file an
        agent called `foo.ran` would want for itself."""
        for said in ("ava.ran", "ava.seen", "ava.interrupted", "ava.log", "ava.lock",
                     "ava.json", "ava.out", "ava.err", "ava.changing", "ava.writing"):
            with self.assertRaises(agent.NotAnAgentName, msg=f"'{said}' was accepted"):
                agent.checked(said)

    def test_a_name_that_merely_has_a_dot_in_it_is_still_a_name(self):
        """R-AGT-6 — the refusal is of the words a gateway writes, not of the punctuation."""
        self.assertEqual(agent.checked("ava.two"), "ava.two")

    def test_what_a_gateway_writes_is_asked_of_it_rather_than_listed(self):
        """R-AGT-6 — the teeth. A sidecar added later is covered the day it lands, because
        this fails when a path helper writes a suffix nothing declared."""
        writes = (gateway.log_path, gateway.schedules_path, gateway.ran_path,
                  gateway.seen_path, gateway.interrupted_path)
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
                               schedules=agent.schedules_home(name, self.where),
                               root=self.root)
        self.addCleanup(made.release)
        return made

    def test_making_an_agent_makes_the_gateway_that_runs_it(self):
        """R-AGW-1 — the gateway is the three directories beside the home, so there is no
        second step and no way to end up with one and not the other."""
        self.made()
        for at in (agent.run_home("ava", self.where), agent.logs_home("ava", self.where),
                   agent.schedules_home("ava", self.where)):
            self.assertTrue(at.is_dir(), f"{at} was not made with the agent")

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
        with gateway.changing_schedules("ava", agent.schedules_home("ava", self.where)) as kept:
            kept.append({"name": "tidy", "when": "0 3 * * *", "run": ["/bin/echo", "hi"]})

        agent.forget("ava", self.where)
        agent.add("ava", self.where)
        self.assertEqual(gateway.written_schedules("ava", agent.schedules_home("ava", self.where)), [])

    def test_taking_an_agent_away_takes_what_its_schedules_did(self):
        """R-AGW-5 — what is scheduled and what each schedule last did sat side by side,
        and only the first went. The second was then inherited by whoever took the name
        next, which is a new agent reading an old one's account of itself."""
        self.made()
        kept = agent.schedules_home("ava", self.where)
        gateway.ran_path("ava", kept).write_text('{"tidy": {"outcome": "ok"}}', encoding="utf-8")
        with gateway.changing_schedules("ava", kept) as scheduled:
            scheduled.append({"name": "tidy", "when": "0 3 * * *", "run": ["/bin/echo", "hi"]})

        agent.forget("ava", self.where)
        self.assertFalse(gateway.schedules_path("ava", kept).exists(), "the work was inherited")
        self.assertFalse(gateway.ran_path("ava", kept).exists(), "the account was inherited")

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
        from rundesk import session

        self.made()
        whose = agent.directory("ava", self.where)
        session.remember(whose, "codex", "terminal", "abc-123")
        agent.remember("ava", self.where, provider="codex")

        agent.forget("ava", self.where)
        agent.add("ava", self.where)
        self.assertIsNone(session.of(agent.directory("ava", self.where), "codex", "terminal"))
        self.assertIsNone(agent.chosen("ava", self.where)["provider"],
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
        self.assertEqual(said.schedules, agent.schedules_home("ava", self.where))

    def test_a_name_with_no_agent_keeps_things_where_it_always_did(self):
        """R-AGT-9 — a gateway that has no agent yet goes on being reached exactly as it
        was, so nothing already running has to be adopted before it works."""
        said = agent.resolved("gateway", self.where)
        self.assertEqual((said.run, said.logs, said.schedules), (None, None, None))

    def test_taking_an_agent_away_takes_the_account_of_what_it_did(self):
        """R-AGW-5 — one outcome, not two. What was kept behind a second flag was left for
        whoever took the name next, and an account nobody can name an agent for is an
        account nobody reads."""
        self.made()
        gateway.note("ava", "something happened", agent.logs_home("ava", self.where))

        agent.forget("ava", self.where)
        self.assertFalse(agent.logs_home("ava", self.where).exists())
        self.assertFalse(agent.directory("ava", self.where).exists())


class AGatewayThatHasNoAgentYet(WithSomewhereToKeepAgents):
    def wrote(self, name: str = "gateway") -> None:
        """A gateway of this name, with a log and schedules, kept the way they were kept
        before there were agents to own them."""
        gateway.note(name, "before there were agents", self.before / "logs")
        with gateway.changing_schedules(name, self.before / "schedules") as kept:
            kept.append({"name": "tidy", "when": "0 3 * * *", "run": ["/bin/echo", "hi"]})

    def test_adopting_a_gateway_moves_what_it_wrote_into_the_agents_own(self):
        """R-AGW-1 — nothing moves on its own, and this is what an owner typing the name
        asks for: one place afterwards, rather than two that disagree."""
        self.wrote()
        agent.add("gateway", self.where)

        agent.adopt("gateway", self.where, logs=self.before / "logs",
                    schedules=self.before / "schedules")

        self.assertIn("before there were agents",
                      gateway.log_path("gateway", agent.logs_home("gateway", self.where)).read_text())
        kept = gateway.written_schedules("gateway", agent.schedules_home("gateway", self.where))
        self.assertEqual([one["name"] for one in kept], ["tidy"])
        self.assertFalse((self.before / "schedules" / "gateway.json").exists(),
                         "what was adopted is still where it was, so two places now disagree")

    def test_adopting_a_gateway_brings_what_its_log_rotated_into_along(self):
        """R-AGW-5 — the part just before something happened is the part worth having, and
        it is the part a rotation moved out of the file everyone reads."""
        self.wrote()
        (self.before / "logs" / "gateway.log.1").write_text("older still", encoding="utf-8")
        agent.add("gateway", self.where)

        agent.adopt("gateway", self.where, logs=self.before / "logs",
                    schedules=self.before / "schedules")

        self.assertEqual((agent.logs_home("gateway", self.where) / "gateway.log.1").read_text(),
                         "older still")

    def test_nothing_is_adopted_while_a_gateway_of_that_name_is_running(self):
        """R-AGT-9 — a gateway binds the directory it reads schedules from once, when it
        starts, and never looks again. Moving those files out from under a live one leaves
        it reading an empty directory for the rest of its life while every command reads
        the new one, and a schedule it was going to run silently never runs.

        The name is held across the move rather than asked about before it, because asking
        and then moving is two decisions with a gap, and a gateway can claim the name
        inside that gap."""
        self.wrote()
        agent.add("gateway", self.where)
        running = gateway.Gateway("gateway", where=self.before / "run",
                                  logs=self.before / "logs",
                                  schedules=self.before / "schedules", root=self.root)
        running.claim()
        self.addCleanup(running.release)

        with self.assertRaises(agent.InUse):
            agent.adopt("gateway", self.where, logs=self.before / "logs",
                        schedules=self.before / "schedules", run=self.before / "run")

        self.assertTrue(gateway.schedules_path("gateway", self.before / "schedules").exists(),
                        "it moved what a running gateway is reading")

    def test_what_a_stopped_gateway_wrote_is_adopted_once_it_lets_the_name_go(self):
        """R-AGT-9 — the other half, so refusing cannot pass by never adopting anything."""
        self.wrote()
        agent.add("gateway", self.where)
        running = gateway.Gateway("gateway", where=self.before / "run",
                                  logs=self.before / "logs",
                                  schedules=self.before / "schedules", root=self.root)
        running.claim()
        running.release()

        agent.adopt("gateway", self.where, logs=self.before / "logs",
                    schedules=self.before / "schedules", run=self.before / "run")
        self.assertFalse(gateway.schedules_path("gateway", self.before / "schedules").exists())

    def test_adopting_a_gateway_that_wrote_nothing_moves_nothing(self):
        """R-AGW-1"""
        agent.add("fresh", self.where)
        self.assertEqual(agent.adopt("fresh", self.where, logs=self.before / "logs",
                                     schedules=self.before / "schedules"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
