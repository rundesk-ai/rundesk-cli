"""Copies of what the owner keeps: what one holds, what it leaves out, and what it says.

Offline and complete. Nothing here starts a gateway, reaches a network or touches the
owner's own install: every case builds a data directory of its own in a temporary place and
backs that up, because the one thing a backup suite must never do is practise on real data.
"""

from __future__ import annotations

import datetime
import json
import copy
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk import backup, config, migration, store

#: A fixed moment, so a name and a manifest are the same in every run and on every machine.
AT = datetime.datetime(2026, 7, 27, 4, 0, 0, tzinfo=datetime.timezone.utc)

#: A durable timestamp in the shape the store writes them.
SAID_AT = "2026-07-27 04:00:00"


def complete_skill(data: Path) -> Path:
    """One skill package with every standard resource and one runnable command."""
    made = data / "skills" / "tidying"
    (made / "scripts").mkdir(parents=True)
    (made / "references").mkdir()
    (made / "assets").mkdir()
    (made / "SKILL.md").write_text("---\nname: tidying\n---\n")
    command = made / "scripts" / "tidying"
    command.write_text("#!/bin/sh\nprintf 'tidy\\n'\n")
    command.chmod(0o751)
    (made / "references" / "usage.md").write_text("# Usage\n")
    (made / "assets" / "report.txt").write_text("{{ result }}\n")
    return made


class WithSomethingToBackUp(unittest.TestCase):
    """A data directory furnished the way an owner's is, and a place to put copies."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-backup-"))
        self.addCleanup(shutil.rmtree, self.where, ignore_errors=True)
        self.data = self.where / "install" / "data"
        self.into = self.where / "install" / "backups"
        self.data.mkdir(parents=True)

    def an_agent(self, name: str = "ava", said: str = "remember the sandwich") -> Path:
        """One agent with real records, made the way `store` really makes them."""
        home = self.data / "agents" / name
        (home / "home").mkdir(parents=True)
        (home / "logs").mkdir(parents=True)
        kept = store.Store(store.path_for(home))
        kept.made()
        kept.opened("c1", "terminal", "terminal", "terminal", SAID_AT)
        kept.arrived("c1", SAID_AT, said)
        return home

    def taken(self, why: str = "asked", now=None):
        return backup.take(self.data, self.into, now=now or AT, why=why)

    def inside(self, at: Path) -> list:
        with zipfile.ZipFile(at) as opened:
            return opened.namelist()


class WhatABackupHolds(WithSomethingToBackUp):
    def test_a_backup_holds_what_the_owner_keeps(self):
        """R-BKP-1 — the agents, their homes and their records. Everything below turns on
        this one being true, so it is asserted directly rather than implied by a round trip."""
        self.an_agent()
        (self.data / "agents" / "ava" / "home" / "SOUL.md").write_text("be useful\n")
        held = self.inside(self.taken())
        self.assertIn("data/agents/ava/state.db", held)
        self.assertIn("data/agents/ava/home/SOUL.md", held)

    def test_a_backup_holds_a_roles_definition_and_a_retained_runs_locked_context(self):
        """R-BKP-1 — a role definition is an owner's, and a retained run's locked bytes
        are what makes it resumable. A copy that brought the run's record back without
        them would bring back a run nothing can carry on."""
        home = self.an_agent()
        roles = self.data / "agents" / ".roles" / "development"
        roles.mkdir(parents=True)
        (roles / "role.json").write_text(
            '{"description": "d", "skills": ["tidying"], "posture": "work"}')
        (roles / "AGENTS.md").write_text("# Development\n")
        bundle = home / "role-runs" / "rol-1-aaaa"
        (bundle / "home").mkdir(parents=True)
        (bundle / "home" / "AGENTS.md").write_text("# Development\n")
        (bundle / "brief.md").write_text("Outcome: make it work.\n")
        held = self.inside(self.taken())
        self.assertIn("data/agents/.roles/development/AGENTS.md", held)
        self.assertIn("data/agents/.roles/development/role.json", held)
        self.assertIn("data/agents/ava/role-runs/rol-1-aaaa/home/AGENTS.md", held)
        self.assertIn("data/agents/ava/role-runs/rol-1-aaaa/brief.md", held)

    def test_a_backup_holds_the_skills_library_and_this_installs_own_configuration(self):
        """R-BKP-1 — what belongs to no single agent is still the owner's, and a restore
        that brought agents back without their skills would bring back agents that cannot
        do what they could."""
        self.an_agent()
        (self.data / "skills" / "tidying").mkdir(parents=True)
        (self.data / "skills" / "tidying" / "SKILL.md").write_text("---\nname: tidying\n---\n")
        (self.data / config.NAMED).write_text('{"backups": {"keep_days": 90}}')
        held = self.inside(self.taken())
        self.assertIn("data/skills/tidying/SKILL.md", held)
        self.assertIn(f"data/{config.NAMED}", held)

    def test_a_backup_holds_a_complete_skill_package(self):
        """R-AGT-44, R-BKP-1 — a backup of only SKILL.md would leave the restored agent
        knowing about an integration whose executable capability was gone."""
        complete_skill(self.data)
        held = self.inside(self.taken())
        self.assertIn("data/skills/tidying/SKILL.md", held)
        self.assertIn("data/skills/tidying/scripts/tidying", held)
        self.assertIn("data/skills/tidying/references/usage.md", held)
        self.assertIn("data/skills/tidying/assets/report.txt", held)

    def test_a_backup_holds_nothing_of_the_program(self):
        """R-BKP-2 — an update replaces the program and a reinstall fetches it again, so a
        copy of it is a copy of something already published. Nothing outside the data
        directory is reachable from a backup at all."""
        self.an_agent()
        app = self.where / "install" / "app"
        app.mkdir(parents=True)
        (app / "rundesk").write_text("#!/usr/bin/env python3\n")
        held = self.inside(self.taken())
        self.assertEqual([], [one for one in held if "app" in one.split("/")])
        self.assertTrue(all(one == backup.MANIFEST or one.startswith(f"{backup.INSIDE}/")
                            for one in held),
                        "something outside the data directory reached the archive")


class WhatABackupLeavesOut(WithSomethingToBackUp):
    def test_a_backup_leaves_out_what_a_gateway_is_using_right_now(self):
        """R-BKP-3 — locks and run records describe a process that is running. Put back,
        they describe one that is not, and every command that reads them is then wrong
        about whether an agent is up."""
        self.an_agent()
        (self.data / "run").mkdir(parents=True)
        (self.data / "run" / "ava.lock").write_text("")
        (self.data / "run" / "ava.json").write_text("{}")
        held = self.inside(self.taken())
        self.assertEqual([], [one for one in held if one.startswith("data/run/")])

    def test_a_backup_leaves_out_the_copy_an_update_is_holding(self):
        """R-BKP-3 — it belongs to the update that took it, not to the owner, and anything
        walking the agents directory reads it as an agent of its own."""
        self.an_agent()
        aside = self.data / "agents" / migration.ROLLBACK / "ava"
        aside.mkdir(parents=True)
        (aside / store.NAME).write_bytes(b"an older copy")
        held = self.inside(self.taken())
        self.assertEqual([], [one for one in held if migration.ROLLBACK in one])

    def test_a_backup_leaves_out_what_belongs_beside_a_database_and_not_to_it(self):
        """R-BKP-3 — the snapshot already holds what a write-ahead log says. Put back next
        to a database it was not written for, it is read as that database's most recent
        truth, which is how a restore invents records nobody wrote."""
        home = self.an_agent()
        (home / (store.NAME + "-wal")).write_bytes(b"not ours to keep")
        (home / (store.NAME + "-shm")).write_bytes(b"nor this")
        held = self.inside(self.taken())
        self.assertIn("data/agents/ava/state.db", held)
        self.assertEqual([], [one for one in held if one.endswith(("-wal", "-shm"))])

    def test_a_backup_says_what_it_left_out_and_why(self):
        """R-BKP-4 — what is missing is the half somebody assumes is there on the day they
        need it, so it is written down inside the archive rather than being merely absent."""
        self.an_agent()
        (self.data / "run").mkdir(parents=True)
        said = backup.manifest_of(self.taken())
        self.assertIn("run", said["excluded"])
        self.assertIn("gateway", said["excluded"]["run"])


class WhatABackupSaysAboutItself(WithSomethingToBackUp):
    def test_a_backup_says_which_rundesk_took_it_and_what_shape_each_agent_was_in(self):
        """R-BKP-5 — every refusal a restore makes is decided from this, and two agents are
        never at the same version, so one number for the whole of the data would be a number
        that is wrong about somebody."""
        self.an_agent("ava")
        self.an_agent("winston")
        said = backup.manifest_of(self.taken())
        self.assertEqual({"ava": store.VERSION, "winston": store.VERSION}, said["records"])
        self.assertEqual(store.VERSION, said["understands"])
        self.assertTrue(said["rundesk"], "it never said which rundesk took it")

    def test_a_backup_says_why_it_was_taken(self):
        """R-BKP-5 — a directory of copies where every one looks the same cannot be reasoned
        about after trouble: the one taken just before a restore is the one somebody wants."""
        self.an_agent()
        self.assertEqual("before-restore",
                         backup.manifest_of(self.taken(why="before-restore"))["why"])

    def test_what_a_backup_says_is_read_without_putting_any_of_it_on_disk(self):
        """R-BKP-5 — every refusal a restore makes is decided from this, and it decides
        before it has moved anything. Reading it must therefore cost nothing and leave
        nothing: an archive that had to be unpacked to be asked about would mean a restore
        that has already written somewhere by the time it knows it should not."""
        self.an_agent()
        at = self.taken()
        settled = sorted(one.name for one in self.into.iterdir())
        said = backup.manifest_of(at)
        self.assertEqual(store.VERSION, said["understands"])
        self.assertEqual(settled, sorted(one.name for one in self.into.iterdir()),
                         "reading what a backup says left something behind")

    def test_an_agent_with_no_records_yet_is_still_named(self):
        """R-BKP-5 — an agent made and never run has a home and no database, and a manifest
        that omitted it would say a restore brings back fewer agents than it does."""
        (self.data / "agents" / "fresh" / "home").mkdir(parents=True)
        self.assertEqual({"fresh": 0}, backup.manifest_of(self.taken())["records"])


class WhatTheFilesystemKnows(WithSomethingToBackUp):
    def test_a_file_an_owner_made_runnable_is_still_runnable(self):
        """R-BKP-6 — zip stores no mode unless it is told to. A workspace hook restored
        without its executable bit is an install that looks complete and cannot run."""
        home = self.an_agent()
        hook = home / "home" / "hook.sh"
        hook.write_text("#!/bin/sh\necho hi\n")
        os.chmod(hook, 0o755)
        with zipfile.ZipFile(self.taken()) as opened:
            mode = opened.getinfo("data/agents/ava/home/hook.sh").external_attr >> 16
        self.assertEqual(0o755, mode & 0o777)

    def test_a_granted_skill_is_kept_as_the_link_it_is(self):
        """R-BKP-6 — a grant is a link into the one shared library. Followed instead of
        stored, every agent's copy becomes a real directory, the library is duplicated once
        per agent, and revoking one stops meaning anything."""
        home = self.an_agent()
        (self.data / "skills" / "tidying").mkdir(parents=True)
        (self.data / "skills" / "tidying" / "SKILL.md").write_text("---\nname: tidying\n---\n")
        (home / "home" / "skills").mkdir()
        os.symlink("../../../../skills/tidying", home / "home" / "skills" / "tidying")
        with zipfile.ZipFile(self.taken()) as opened:
            one = opened.getinfo("data/agents/ava/home/skills/tidying")
            self.assertTrue(stat.S_ISLNK(one.external_attr >> 16),
                            "the link was followed and stored as a copy")
            self.assertEqual("../../../../skills/tidying", opened.read(one).decode())


class HowOneIsWritten(WithSomethingToBackUp):
    def test_a_backup_is_named_so_that_sorting_by_name_sorts_by_time(self):
        """R-BKP-7 — `ls` is the listing somebody reaches for first, and a name that sorted
        differently from the moment it was taken would put the newest copy anywhere."""
        self.an_agent()
        earlier = backup.named_at(AT)
        later = backup.named_at(AT + datetime.timedelta(hours=3))
        much_later = backup.named_at(AT + datetime.timedelta(days=400))
        self.assertEqual([earlier, later, much_later],
                         sorted([much_later, later, earlier]))

    def test_a_backup_is_named_in_one_clock_so_an_hour_that_happens_twice_still_sorts(self):
        """R-BKP-7 — a local time goes backwards for an hour once a year, which would order
        two copies wrongly and silently. The name is UTC and says so."""
        self.an_agent()
        self.assertTrue(backup.named_at(AT).endswith("Z" + backup.SUFFIX))

    def test_nothing_is_under_its_final_name_until_it_is_whole(self):
        """R-BKP-8 — the directory may sync to a cloud, so an archive that appeared under
        its real name while still being written would be uploaded half finished and would
        then look exactly like a backup to everything that reads the directory."""
        self.an_agent()
        watched = []
        real = backup._add

        def watching(archive, at, under, when):
            watched.append(sorted(one.name for one in self.into.iterdir()))
            return real(archive, at, under, when)

        backup._add = watching
        self.addCleanup(setattr, backup, "_add", real)
        at = self.taken()
        self.assertTrue(watched, "nothing was written at all")
        for seen in watched:
            self.assertEqual([], [one for one in seen if not one.endswith(backup.PARTIAL)],
                             "a name that was not finished was already the final one")
        self.assertEqual([at.name], sorted(one.name for one in self.into.iterdir()))

    def test_a_backup_that_could_not_be_finished_leaves_nothing_behind(self):
        """R-BKP-8 — a part written archive left in the directory is one a listing shows and
        a restore could reach for."""
        self.an_agent()
        real = backup._add

        def refusing(archive, at, under, when):
            raise OSError("the disk went away")

        backup._add = refusing
        self.addCleanup(setattr, backup, "_add", real)
        with self.assertRaises(OSError):
            self.taken()
        self.assertEqual([], sorted(one.name for one in self.into.iterdir()))

    def test_backing_up_where_there_is_nothing_says_so_rather_than_writing_an_empty_one(self):
        """R-BKP-8 — an archive of a directory that is not there is an archive of nothing,
        and it is indistinguishable afterwards from one taken of an install that was empty."""
        with self.assertRaises(backup.Refused):
            backup.take(self.where / "not here", self.into, now=AT)


class ADatabaseBeingWrittenTo(WithSomethingToBackUp):
    """Why a backup snapshots a database instead of copying the file it is in."""

    def holding_the_log_open(self, home: Path):
        """A reader that stops the write-ahead log being retired, as a live gateway does.

        What makes this deterministic rather than a race: while any reader is open, a commit
        stays in the log beside the database rather than being folded into it. So the newest
        truth is provably *not* in `state.db` at the moment the copy is taken, which is
        exactly the state a running gateway keeps its agent in all day.
        """
        held = sqlite3.connect(f"file:{store.path_for(home)}?mode=ro", uri=True)
        self.addCleanup(held.close)
        held.execute("BEGIN")
        held.execute("SELECT count(*) FROM message").fetchone()
        return held

    def test_a_backup_of_a_database_in_use_holds_what_was_written_to_it(self):
        """R-BKP-9 — the whole reason a backup does not copy the file. A plain copy taken
        while a gateway holds the database opens, reports the right version, and is missing
        whatever had not been folded in yet — so it is not discovered to be wrong until the
        day it is put back, which is the worst day for it."""
        home = self.an_agent(said="first")
        self.holding_the_log_open(home)
        store.Store(store.path_for(home)).arrived(
            "c1", SAID_AT, "second, which is not in the database file yet")
        self.assertTrue(Path(str(store.path_for(home)) + "-wal").exists(),
                        "nothing was left outside the database, so this proves nothing")

        out = self.where / "out"
        with zipfile.ZipFile(self.taken()) as opened:
            opened.extract("data/agents/ava/state.db", out)
        copy = store.Store(out / "data" / "agents" / "ava" / store.NAME)
        self.assertEqual(store.VERSION, copy.version())
        self.assertEqual(["first", "second, which is not in the database file yet"],
                         [one["text"] for one in copy.messages("c1")])

    def test_a_database_too_damaged_to_copy_consistently_is_kept_exactly_as_it_is(self):
        """R-BKP-15 — refusing the whole backup over one ruined database would leave every
        healthy agent uncopied too, for as long as the damage lasted. The bytes are what
        somebody wants in that case, and the manifest says which ones got them, because a
        copy that is not a consistent copy must never be indistinguishable from one."""
        self.an_agent()
        hurt = self.data / "agents" / "broken"
        (hurt / "home").mkdir(parents=True)
        (hurt / store.NAME).write_bytes(b"this was a database once")
        at = self.taken()
        said = backup.manifest_of(at)
        self.assertEqual(["agents/broken/state.db"], said["copied_whole"])
        self.assertEqual([], said["copied_whole"][1:])
        with zipfile.ZipFile(at) as opened:
            self.assertEqual(b"this was a database once",
                             opened.read("data/agents/broken/state.db"))
            self.assertIn("data/agents/ava/state.db", opened.namelist())


class ReadingTheDirectory(WithSomethingToBackUp):
    def test_every_backup_there_is_reads_back_oldest_first(self):
        """R-BKP-10 — the listing somebody scans after trouble, in the order the names are."""
        self.an_agent()
        first = self.taken()
        second = self.taken(now=AT + datetime.timedelta(hours=1))
        self.assertEqual([first.name, second.name],
                         [one.at.name for one in backup.every(self.into)])

    def test_a_directory_with_no_backups_in_it_is_empty_rather_than_an_error(self):
        """R-BKP-10 — an install that has never taken one is the ordinary case."""
        self.assertEqual([], backup.every(self.into))

    def test_something_that_is_not_a_backup_is_listed_rather_than_passed_over(self):
        """R-BKP-10 — a file that is there and cannot be read is exactly what somebody has
        to be told about. Passed over, a listing says an owner has fewer copies than they
        have, or none at all on the day it matters."""
        self.an_agent()
        good = self.taken()
        self.into.mkdir(parents=True, exist_ok=True)
        (self.into / "rundesk-data-2020-01-01-000000Z.zip").write_bytes(b"not a zip at all")
        found = backup.every(self.into)
        self.assertEqual(2, len(found))
        unreadable = [one for one in found if not one.readable]
        self.assertEqual(1, len(unreadable))
        self.assertTrue(unreadable[0].why, "it never said why it could not be read")
        self.assertTrue([one for one in found if one.at == good][0].readable)

    def test_a_zip_that_says_nothing_about_itself_is_not_a_backup(self):
        """R-BKP-11 — refusing is the difference between saying so and quietly putting back
        nothing at all."""
        self.into.mkdir(parents=True)
        at = self.into / "rundesk-data-2026-01-01-000000Z.zip"
        with zipfile.ZipFile(at, "w") as opened:
            opened.writestr("data/agents/ava/state.db", b"")
        with self.assertRaises(backup.Unreadable):
            backup.manifest_of(at)

    def test_a_backup_that_is_not_on_this_disk_says_so_rather_than_failing_obscurely(self):
        """R-BKP-12 — a synced directory may keep a file in the cloud and leave a
        placeholder. It is in the listing, it cannot be read, and the thing to do about it
        is not the thing somebody would guess from a read that came up short."""
        self.into.mkdir(parents=True)
        gone = self.into / "rundesk-data-2026-01-01-000000Z.zip"
        (self.into / f".{gone.name}.icloud").write_bytes(b"")
        with self.assertRaises(backup.Refused) as refused:
            backup.manifest_of(gone)
        self.assertIn("not on this disk", str(refused.exception))

    def test_asking_for_a_backup_that_was_never_there_says_which_one(self):
        """R-BKP-11 — a name somebody typed wrongly is the ordinary case, and it is a
        different answer from one the cloud has taken away."""
        self.into.mkdir(parents=True)
        with self.assertRaises(backup.Refused) as refused:
            backup.manifest_of(self.into / "rundesk-data-1999-01-01-000000Z.zip")
        self.assertIn("no backup called", str(refused.exception))


class TwoInOneSecond(WithSomethingToBackUp):
    def test_a_second_backup_in_the_same_second_never_writes_over_the_first(self):
        """R-BKP-8 — a name is to the second and two can happen inside one. That is not
        contrived: taking a copy immediately before putting one back is what the safest path
        through this does every time, and without this the second archive is renamed over the
        first — destroying a backup, reporting success, and in that case destroying the very
        one being put back."""
        self.an_agent()
        first = self.taken(why="asked")
        second = self.taken(why="before-restore")
        self.assertNotEqual(first, second)
        self.assertTrue(first.exists(), "the first backup was written over")
        self.assertEqual("asked", backup.manifest_of(first)["why"])
        self.assertEqual("before-restore", backup.manifest_of(second)["why"])

    def test_two_in_one_second_still_sort_by_the_moment_they_were_taken(self):
        """R-BKP-7 — a disambiguator that broke the ordering would be a cure worse than the
        problem: the newest copy is the one somebody reaches for."""
        self.an_agent()
        first = self.taken()
        second = self.taken()
        later = self.taken(now=AT + datetime.timedelta(seconds=1))
        self.assertEqual([first.name, second.name, later.name],
                         sorted([later.name, second.name, first.name]))


class WhatARestoreRefuses(WithSomethingToBackUp):
    """Every refusal is decided before anything moves, and proved by what is still there."""

    def unchanged(self, before):
        return before == sorted(str(one.relative_to(self.data))
                                for one in self.data.rglob("*"))

    def standing(self):
        return sorted(str(one.relative_to(self.data)) for one in self.data.rglob("*"))

    def test_records_written_by_a_newer_rundesk_are_refused_and_nothing_is_moved(self):
        """R-BKP-18 — exactly what `store.TooNew` exists for. This code cannot know what it
        is missing, so reading them would be reading a partial truth and writing over the
        rest — and it is said before anything moves rather than after."""
        self.an_agent()
        at = self.taken()
        _rewrite_manifest(at, records={"ava": store.VERSION + 3})
        before = self.standing()
        why = backup.restore(at, self.data, self.into, keep_one_first=False)
        self.assertIn("newer than this rundesk understands", why)
        self.assertIn(f"version {store.VERSION + 3}", why)
        self.assertTrue(self.unchanged(before), "something moved after a refusal")

    def test_a_backup_taken_by_a_newer_rundesk_is_refused_and_nothing_is_moved(self):
        """R-BKP-18 — the release is the other way an archive can be ahead of this code, and
        an archive can be ahead by it while every version number inside it looks ordinary."""
        self.an_agent()
        at = self.taken()
        _rewrite_manifest(at, rundesk="99.0.0")
        before = self.standing()
        why = backup.restore(at, self.data, self.into, keep_one_first=False)
        self.assertIn("99.0.0", why)
        self.assertTrue(self.unchanged(before), "something moved after a refusal")

    def test_a_backup_at_the_shape_installed_is_put_back_rather_than_refused(self):
        """R-BKP-18 — the guard on the two above. A refusal that fired on every archive
        would pass both of those cases and make the feature useless."""
        self.an_agent()
        at = self.taken()
        self.assertEqual([], backup.refusals(backup.manifest_of(at)))

    def test_putting_one_back_while_work_is_in_flight_is_refused(self):
        """R-BKP-20 — a turn in progress is work an owner is waiting on, and replacing the
        records under it loses whatever it was in the middle of writing."""
        self.an_agent()
        at = self.taken()
        before = self.standing()
        why = backup.restore(at, self.data, self.into, keep_one_first=False,
                             busy=lambda: ["ava/run-3"])
        self.assertIn("ava/run-3", why)
        self.assertTrue(self.unchanged(before), "something moved while work was in flight")

    def test_a_gateway_that_will_not_stand_down_stops_the_restore(self):
        """R-BKP-20 — restoring under a running gateway is data loss, so the same window an
        update opens is reused rather than a second one being invented, including its
        refusal."""
        self.an_agent()
        at = self.taken()
        before = self.standing()
        why = backup.restore(at, self.data, self.into, keep_one_first=False,
                             pause=lambda: ([], "'ava' would not stop"))
        self.assertEqual("'ava' would not stop", why)
        self.assertTrue(self.unchanged(before), "something moved under a running gateway")

    def test_an_archive_that_would_write_outside_where_it_is_put_is_refused(self):
        """R-BKP-11 — nothing stops an archive saying its entries go somewhere else, and a
        restore is the most privileged thing here. The floor version of Python this runs on
        does not refuse it on our behalf."""
        self.into.mkdir(parents=True)
        at = self.into / "rundesk-data-2026-07-27-040000Z.zip"
        with zipfile.ZipFile(at, "w") as opened:
            opened.writestr(backup.MANIFEST,
                            json.dumps({"records": {}, "rundesk": "0.0.1", "taken_at": "x"}))
            opened.writestr(f"{backup.INSIDE}/../../escaped.txt", b"got out")
        why = backup.restore(at, self.data, self.into, keep_one_first=False)
        self.assertIn("outside", why)
        self.assertFalse((self.where / "escaped.txt").exists(), "an entry escaped")


class PuttingOneBack(WithSomethingToBackUp):
    def test_an_agent_and_its_history_are_whole_again_after_a_restore(self):
        """R-BKP-16 — the claim the whole feature rests on. A backup nobody has restored is
        not a backup, so this drives the real thing: records, a home, the shared library, and
        an agent that reads back everything it was told."""
        home = self.an_agent(said="remember the sandwich")
        store.Store(store.path_for(home)).arrived("c1", SAID_AT, "and the pickle")
        (home / "home" / "SOUL.md").write_text("be useful\n")
        (self.data / "skills" / "tidying").mkdir(parents=True)
        (self.data / "skills" / "tidying" / "SKILL.md").write_text("---\nname: tidying\n---\n")
        at = self.taken()

        shutil.rmtree(home)
        self.assertIsNone(backup.restore(at, self.data, self.into, keep_one_first=False))

        back = store.Store(store.path_for(self.data / "agents" / "ava"))
        self.assertEqual(store.VERSION, back.version())
        self.assertEqual(["remember the sandwich", "and the pickle"],
                         [one["text"] for one in back.messages("c1")])
        self.assertEqual("be useful\n",
                         (self.data / "agents" / "ava" / "home" / "SOUL.md").read_text())
        self.assertTrue((self.data / "skills" / "tidying" / "SKILL.md").is_file())

    def test_a_restored_skill_package_keeps_its_executable_command(self):
        """R-AGT-44, R-BKP-6 — the package coming back is not enough if the command the
        instructions name can no longer run."""
        complete_skill(self.data)
        at = self.taken()
        shutil.rmtree(self.data / "skills" / "tidying")
        self.assertIsNone(backup.restore(at, self.data, self.into, keep_one_first=False))
        package = self.data / "skills" / "tidying"
        self.assertEqual(0o751, (package / "scripts" / "tidying").stat().st_mode & 0o777)
        self.assertTrue((package / "references" / "usage.md").is_file())
        self.assertTrue((package / "assets" / "report.txt").is_file())

    def test_putting_one_back_brings_back_what_was_removed_and_takes_away_what_was_added(self):
        """R-BKP-16 — a restore replaces everything the owner keeps rather than merging, so
        an agent removed since it was taken comes back and one made since it goes. Said
        plainly because it is the half nobody expects."""
        self.an_agent("ava")
        at = self.taken()
        shutil.rmtree(self.data / "agents" / "ava")
        self.an_agent("scratch")
        said = backup.manifest_of(at)
        self.assertEqual({"comes_back": ["ava"], "goes_away": ["scratch"], "stays": []},
                         backup.what_changes(said, self.data))
        self.assertIsNone(backup.restore(at, self.data, self.into, keep_one_first=False))
        self.assertTrue((self.data / "agents" / "ava").is_dir())
        self.assertFalse((self.data / "agents" / "scratch").exists())

    def test_a_restore_takes_a_copy_of_what_is_there_first(self):
        """R-BKP-17 — a restore is otherwise the one irreversible thing an owner can do to
        themselves, and the moment they discover that is the moment it has happened."""
        self.an_agent("ava")
        at = self.taken()
        shutil.rmtree(self.data / "agents" / "ava")
        self.an_agent("scratch")
        self.assertIsNone(backup.restore(at, self.data, self.into))
        kept = [one for one in backup.every(self.into)
                if (one.said or {}).get("why") == "before-restore"]
        self.assertEqual(1, len(kept), "nothing was kept before the data was replaced")
        self.assertEqual(["scratch"], sorted(kept[0].said["records"]),
                         "what was kept is not what was there")

    def test_what_was_there_survives_a_restore_that_fails_part_way(self):
        """R-BKP-21 — the guarantee the order exists for. Everything that can fail happens
        while the owner's own data is still sitting untouched where it always was, so a
        migration that will not run has touched nothing but a directory about to be deleted."""
        home = self.an_agent(said="the one that must survive")
        (home / "home" / "SOUL.md").write_text("still here\n")
        at = self.taken()
        before = sorted(str(one.relative_to(self.data)) for one in self.data.rglob("*"))

        why = backup.restore(at, self.data, self.into, keep_one_first=False,
                             carry=lambda incoming: "002.py did not finish")
        self.assertEqual("002.py did not finish", why)
        self.assertEqual(before,
                         sorted(str(one.relative_to(self.data)) for one in self.data.rglob("*")))
        self.assertEqual(["the one that must survive"],
                         [one["text"] for one in
                          store.Store(store.path_for(home)).messages("c1")])
        self.assertEqual([], [one for one in self.data.parent.iterdir()
                              if one.name.endswith((".incoming", ".outgoing"))],
                         "a half finished restore left its working directories behind")

    def test_what_was_there_survives_the_swap_itself_going_wrong(self):
        """R-BKP-21 — the other half, and the one a migration failing never reaches. Once the
        old tree has been moved aside the restore is past every check it can make, so what
        protects the owner from here is that it was *moved* and not deleted. Nothing caught
        this until the swap was made to fail: a restore that cleared the old tree instead of
        renaming it passed every other case in this file."""
        home = self.an_agent(said="the one that must survive")
        at = self.taken()
        before = sorted(str(one.relative_to(self.data)) for one in self.data.rglob("*"))

        real = os.rename
        fired = []

        def refusing(src, dst):
            # The move that puts the unpacked tree in place, named rather than counted: by
            # the time it runs, what was there has already been set aside and nothing but
            # that guards it. Counting instead would stop firing the moment the number of
            # moves changed, and would pass while proving nothing.
            #
            # **Once, not for ever.** Putting the old tree back is a move to that same name,
            # so refusing every one of them models a machine where nothing can be renamed at
            # all — under which no design could recover, and the case would prove nothing
            # about this one.
            if Path(dst).name == self.data.name and not fired:
                fired.append(dst)
                raise OSError("the disk filled up half way through the swap")
            return real(src, dst)

        os.rename = refusing
        self.addCleanup(setattr, os, "rename", real)
        with self.assertRaises(OSError):
            backup.restore(at, self.data, self.into, keep_one_first=False)
        os.rename = real

        self.assertTrue(self.data.is_dir(), "the data directory is gone altogether")
        self.assertEqual(before,
                         sorted(str(one.relative_to(self.data)) for one in self.data.rglob("*")))
        self.assertEqual(["the one that must survive"],
                         [one["text"] for one in
                          store.Store(store.path_for(home)).messages("c1")])
        self.assertEqual([], [one for one in self.data.parent.iterdir()
                              if one.name.endswith((".incoming", ".outgoing"))],
                         "a failed swap left its working directories behind")

    def test_a_restore_brings_records_forward_before_it_swaps_anything_in(self):
        """R-BKP-19 — a copy taken at an older shape is brought forward on the way in, and
        the bringing-forward happens against the unpacked copy rather than against what the
        owner is still using."""
        self.an_agent()
        at = self.taken()
        seen = []

        def carrying(incoming):
            seen.append(incoming)
            # What it is handed must be a real tree, and must not be the live one.
            assert (incoming / "agents" / "ava" / store.NAME).is_file()
            return None

        self.assertIsNone(backup.restore(at, self.data, self.into, keep_one_first=False,
                                         carry=carrying))
        self.assertEqual(1, len(seen))
        self.assertNotEqual(self.data.resolve(), seen[0].resolve(),
                            "records were brought forward in the live directory")

    def test_a_backup_from_an_older_shape_is_brought_forward_as_it_is_put_back(self):
        """R-BKP-19 — a backup that has been sitting in a drawer was written by whatever
        rundesk was installed then, and putting it back onto a later one has to bring it
        forward or hand back records nothing can open.

        **The older world is built here rather than committed as an archive.** A zip in the
        repository is a fixture nobody can read, review or regenerate when the shape moves;
        this takes a real backup at the shape that ships and then moves the *code* on, which
        is the same arrangement from the records' point of view and stays true as steps land.
        """
        home = self.an_agent(said="written before the step existed")
        at = self.taken()
        was = backup.manifest_of(at)["records"]["ava"]

        # A world one step ahead of the archive: a step of this suite's own, in a directory
        # of its own, so nothing that ships is touched and the number cannot collide.
        steps = self.where / "steps"
        steps.mkdir()
        (steps / f"{was + 1:03d}.py").write_text(
            "def up(conn, home):\n"
            "    conn.execute('ALTER TABLE agent ADD COLUMN carried TEXT')\n"
            "    conn.execute(\"UPDATE agent SET carried = 'yes'\")\n"
            "    return []\n")
        ahead = was + 1

        shutil.rmtree(home)
        why = backup.restore(
            at, self.data, self.into, keep_one_first=False, want=ahead,
            carry=lambda incoming: migration.carry_every_or_put_back(
                incoming / "agents", ahead, aside=incoming / ".carrying", where=steps))
        self.assertIsNone(why, "an older backup would not go back")

        back = store.path_for(self.data / "agents" / "ava")
        conn = sqlite3.connect(str(back))
        self.addCleanup(conn.close)
        self.assertEqual(ahead, conn.execute("PRAGMA user_version").fetchone()[0],
                         "it went back at the version it was taken at")
        self.assertEqual("yes", conn.execute("SELECT carried FROM agent").fetchone()[0])
        self.assertEqual([("written before the step existed",)],
                         conn.execute("SELECT text FROM message ORDER BY id").fetchall(),
                         "what it held did not survive being brought forward")

    def test_a_restore_stands_gateways_down_and_starts_them_again(self):
        """R-BKP-20 — the window an update already opens, reused rather than reinvented,
        including putting back what it stood down."""
        self.an_agent()
        at = self.taken()
        started = []
        self.assertIsNone(backup.restore(
            at, self.data, self.into, keep_one_first=False,
            pause=lambda: (["ava"], None),
            resume=lambda names: started.extend(names) or []))
        self.assertEqual(["ava"], started)

    def test_a_gateway_that_does_not_come_back_is_said_rather_than_passed_over(self):
        """R-BKP-20 — the data is back and something is still down, which is a different
        outcome from both success and failure and has to read as its own."""
        self.an_agent()
        at = self.taken()
        why = backup.restore(at, self.data, self.into, keep_one_first=False,
                             pause=lambda: (["ava"], None),
                             resume=lambda names: ["ava"])
        self.assertIn("ava", why)
        self.assertIn("did not start again", why)

    def test_what_was_runnable_and_what_was_a_link_are_still_that_after_a_restore(self):
        """R-BKP-6 — the other half of keeping them in the archive. Restored as plain files,
        a granted skill stops being a grant and a hook stops being runnable."""
        home = self.an_agent()
        (self.data / "skills" / "tidying").mkdir(parents=True)
        (self.data / "skills" / "tidying" / "SKILL.md").write_text("---\nname: tidying\n---\n")
        (home / "home" / "skills").mkdir()
        os.symlink("../../../../skills/tidying", home / "home" / "skills" / "tidying")
        hook = home / "home" / "hook.sh"
        hook.write_text("#!/bin/sh\necho hi\n")
        os.chmod(hook, 0o755)
        at = self.taken()
        shutil.rmtree(home)
        self.assertIsNone(backup.restore(at, self.data, self.into, keep_one_first=False))

        link = self.data / "agents" / "ava" / "home" / "skills" / "tidying"
        self.assertTrue(link.is_symlink(), "a grant came back as a copied directory")
        self.assertEqual("../../../../skills/tidying", os.readlink(link))
        self.assertTrue(link.resolve().is_dir(), "the link does not reach the library")
        self.assertEqual(
            0o755,
            (self.data / "agents" / "ava" / "home" / "hook.sh").stat().st_mode & 0o777)


def _rewrite_manifest(at: Path, **said) -> None:
    """The same archive with its manifest changed — an archive from another rundesk.

    Built rather than committed, because a zip in the repository is a fixture nobody can
    read, review or regenerate when the shape moves.
    """
    with zipfile.ZipFile(at) as opened:
        held = [(one, opened.read(one.filename)) for one in opened.infolist()]
    was = json.loads(dict((one.filename, body) for one, body in held)[backup.MANIFEST])
    was.update(said)
    with zipfile.ZipFile(at, "w") as opened:
        for one, body in held:
            opened.writestr(one, json.dumps(was) if one.filename == backup.MANIFEST else body)


class WhenSomethingWasInterrupted(WithSomethingToBackUp):
    """What is on disk after a restore that never finished, and what the next one does with it."""

    def a_swap_that_was_interrupted(self, said: str = "the only copy there is"):
        """The exact state a machine losing power between the two renames leaves behind.

        Built rather than caused, because the window is one syscall pair wide and no
        exception can be raised inside it: what a crash leaves is `data/` gone and everything
        the owner has sitting under the set-aside name.
        """
        home = self.an_agent(said=said)
        at = self.taken()
        outgoing = self.data.with_name(backup.OUTGOING.format(name=self.data.name))
        os.rename(self.data, outgoing)
        self.assertFalse(self.data.exists())
        return at, outgoing

    def test_a_restore_after_one_that_was_interrupted_puts_back_what_was_set_aside(self):
        """R-BKP-21 — the retry is the dangerous moment, not the crash. Running the command
        again is the obvious thing to do and used to be the thing that destroyed the data:
        both leftovers were cleared before any other check, so the only copy of what the
        owner had went first, silently, and the restore then reported success."""
        at, outgoing = self.a_swap_that_was_interrupted()
        why = backup.restore(at, self.data, self.into, keep_one_first=False)
        self.assertIsNone(why)
        self.assertTrue(self.data.is_dir(), "the data directory never came back")
        self.assertEqual(["the only copy there is"],
                         [one["text"] for one in store.Store(
                             store.path_for(self.data / "agents" / "ava")).messages("c1")])
        self.assertFalse(outgoing.exists(), "what was set aside was left lying about")

    def test_what_was_set_aside_is_put_back_before_anything_else_is_decided(self):
        """R-BKP-21 — it goes back even when the restore that follows refuses. The data
        being whole cannot depend on the archive somebody happened to name afterwards."""
        at, outgoing = self.a_swap_that_was_interrupted()
        _rewrite_manifest(at, rundesk="99.0.0")
        why = backup.restore(at, self.data, self.into, keep_one_first=False)
        self.assertIn("99.0.0", why, "it did not refuse the newer archive")
        self.assertTrue(self.data.is_dir(),
                        "a refusal left the owner with no data directory at all")
        self.assertEqual(["the only copy there is"],
                         [one["text"] for one in store.Store(
                             store.path_for(self.data / "agents" / "ava")).messages("c1")])

    def test_what_was_set_aside_by_a_swap_that_did_finish_is_only_cleanup(self):
        """R-BKP-21 — the other leftover, which is not the same situation. With the data
        directory there, the rename that mattered already happened and what is set aside is
        the superseded copy. Treating it as the live data would put yesterday back."""
        home = self.an_agent(said="what is there now")
        at = self.taken()
        outgoing = self.data.with_name(backup.OUTGOING.format(name=self.data.name))
        shutil.copytree(self.data, outgoing)
        store.Store(store.path_for(home)).arrived("c1", SAID_AT, "and this, which is newer")

        self.assertIsNone(backup.restore(at, self.data, self.into, keep_one_first=False))
        self.assertFalse(outgoing.exists())
        self.assertEqual(["what is there now"],
                         [one["text"] for one in store.Store(
                             store.path_for(self.data / "agents" / "ava")).messages("c1")],
                         "the archive was not what went back")


class TwoAtOnce(WithSomethingToBackUp):
    def test_two_backups_running_at_once_never_write_to_one_anothers_file(self):
        """R-BKP-27 — the machine's daily job firing while somebody types `backups add` is
        this, and it is not rare. Both writers used to derive the same part-written name from
        the same second, so one of them died on a file the other had already moved — reported
        as a disk that could not be written to, which sends an owner to look at the disk."""
        self.an_agent()
        made, trouble = [], []
        #: One party per worker **and one for this thread**, which waits with them so they
        #: are all inside `take()` at once. Counting only the workers leaves this one waiting
        #: for a party that never arrives, and the suite hangs rather than fails.
        hands = []
        ready = threading.Barrier(5)

        def taking():
            ready.wait()
            try:
                made.append(self.taken())
            except BaseException as why:      # noqa: BLE001 — the case is what escapes
                trouble.append(why)

        hands = [threading.Thread(target=taking) for _ in range(4)]
        for hand in hands:
            hand.start()
        ready.wait()
        for hand in hands:
            hand.join()

        self.assertEqual([], [repr(one) for one in trouble],
                         "a backup failed because another was running")
        self.assertEqual(4, len(set(made)), "two backups were given one name")
        self.assertEqual(4, len(backup.every(self.into)), "a backup was written over")
        for one in backup.every(self.into):
            self.assertTrue(one.readable, f"{one.at.name} is not a whole archive")

    def test_nothing_part_written_is_left_behind_when_several_run_at_once(self):
        """R-BKP-8 — a part-written file left in the directory is one a listing shows and a
        restore could reach for, and several writers is exactly when one gets forgotten."""
        self.an_agent()
        ready = threading.Barrier(4)          # three workers, and this thread waiting with them

        def taking():
            ready.wait()
            self.taken()

        hands = [threading.Thread(target=taking) for _ in range(3)]
        for hand in hands:
            hand.start()
        ready.wait()
        for hand in hands:
            hand.join()
        self.assertEqual([], [one.name for one in self.into.iterdir()
                              if one.name.endswith(backup.PARTIAL)])


class KeepingOnlySoMany(WithSomethingToBackUp):
    """Pruning by age, and the one copy age may never take."""

    def older(self, days: int, why: str = "daily") -> Path:
        return self.taken(why=why, now=AT - datetime.timedelta(days=days))

    def test_copies_past_the_stated_age_are_taken_away(self):
        """R-BKP-22 — a directory that only ever grows is a disk that fills, and the whole
        point of stating an age is that something acts on it."""
        self.an_agent()
        old = self.older(90)
        recent = self.older(2)
        newest = self.taken()
        gone = backup.prune(self.into, days=30, now=AT)
        self.assertEqual([old.name], gone)
        self.assertEqual([recent.name, newest.name],
                         [one.at.name for one in backup.every(self.into)])

    def test_the_only_copy_there_is_is_never_taken_away_by_age(self):
        """R-BKP-23 — a machine off for a month has nothing recent, and pruning it to nothing
        would leave an owner with no copy at all on the day they most need one.

        Named for what it proves: with one copy there is nothing to compare, and the case is
        answered before any age is looked at. The newest-of-several rule is the one below —
        keeping both, because they are different code and the first hid the second."""
        self.an_agent()
        only = self.older(400)
        self.assertEqual([], backup.prune(self.into, days=30, now=AT))
        self.assertEqual([only.name], [one.at.name for one in backup.every(self.into)])

    def test_every_copy_being_old_still_leaves_the_newest_one(self):
        """R-BKP-23 — the case that empties the directory if the newest is exempted by date
        rather than by being the newest: a machine left off for a year has nothing recent."""
        self.an_agent()
        self.older(400)
        self.older(380)
        newest = self.older(360)
        backup.prune(self.into, days=30, now=AT)
        self.assertEqual([newest.name], [one.at.name for one in backup.every(self.into)])

    def test_a_copy_whose_age_cannot_be_read_is_never_the_one_removed(self):
        """R-BKP-22 — deciding to delete something on the strength of not understanding it is
        the one thing pruning must not do."""
        self.an_agent()
        self.taken()
        self.into.mkdir(parents=True, exist_ok=True)
        odd = self.into / "rundesk-data-1999-01-01-000000Z.zip"
        odd.write_bytes(b"not a zip at all")
        self.assertEqual([], backup.prune(self.into, days=30, now=AT))
        self.assertTrue(odd.exists(), "something unreadable was deleted by age")


class TakingOneAway(WithSomethingToBackUp):
    def test_one_copy_is_removed_by_the_name_it_is_listed_under(self):
        """R-BKP-24 — "always kept" plus "no way to be rid of them" is a disk that fills, so
        there is a way, and it is a separate act rather than a flag on something else."""
        self.an_agent()
        first = self.taken()
        second = self.taken()
        backup.remove(self.into, first.name)
        self.assertEqual([second.name], [one.at.name for one in backup.every(self.into)])

    def test_removing_one_that_is_not_there_says_so(self):
        """R-BKP-24 — a name typed wrongly is the ordinary case, and reporting success would
        leave somebody believing they had freed space they had not."""
        self.an_agent()
        self.taken()
        with self.assertRaises(backup.Refused):
            backup.remove(self.into, "rundesk-data-1999-01-01-000000Z.zip")

    def test_removing_cannot_reach_outside_the_directory_copies_are_kept_in(self):
        """R-BKP-24 — a name is a name and not a path. A command whose whole job is deleting
        is the wrong one to be relaxed about what it is handed."""
        self.an_agent()
        self.taken()
        # One directory up from where copies are kept, so that `../precious.zip` really does
        # name it. Anywhere else and the refusal fires because the file is not there at all,
        # which passes the case while proving nothing about the guard — as it did.
        elsewhere = self.into.parent / "precious.zip"
        elsewhere.write_bytes(b"not rundesk's")
        with self.assertRaises(backup.Refused):
            backup.remove(self.into, "../precious.zip")
        self.assertTrue(elsewhere.exists(), "a name reached out of the directory")


class HowThisInstallIsConfigured(unittest.TestCase):
    """`config.json` — install-wide backup and update behavior."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-config-"))
        self.addCleanup(shutil.rmtree, self.where, ignore_errors=True)
        config.ensure(self.where)

    def wrote(self, said) -> Path:
        at = self.where / config.NAMED
        if isinstance(said, str):
            at.write_text(said)
            return at
        complete = copy.deepcopy(config.INITIAL)
        for section, values in said.items():
            if isinstance(values, dict) and isinstance(complete.get(section), dict):
                complete[section].update(values)
            else:
                complete[section] = values
        at.write_text(json.dumps(complete))
        return at

    def test_an_install_reads_backup_values_from_its_configuration(self):
        """R-BKP-13 — the ordinary case is the complete file the install wrote."""
        self.assertEqual(config.INITIAL["backups"],
                         config.backups(self.where))

    def test_how_long_backups_are_kept_is_the_owners_to_state(self):
        """R-BKP-13 — the default is a default and not a law."""
        self.wrote({"backups": {"keep_days": 90}})
        self.assertEqual(90, config.backups(self.where)["keep_days"])

    def test_configuration_that_cannot_be_understood_is_refused_rather_than_ignored(self):
        """R-BKP-14 — treating it as absent means running on defaults an owner believes they
        overrode, which they find out about when a copy they thought was kept has gone."""
        self.wrote("{ this is not json")
        with self.assertRaises(config.Unreadable):
            config.backups(self.where)

    def test_a_length_of_time_that_would_keep_nothing_is_refused(self):
        """R-BKP-14 — an owner who wrote zero meant something, and neither reading it as the
        default nor as a single day is what they meant."""
        for said in (0, -1, "thirty", True, 1.5):
            self.wrote({"backups": {"keep_days": said}})
            with self.assertRaises(config.Unreadable, msg=f"{said!r} was accepted"):
                config.backups(self.where)

    def test_a_time_of_day_that_is_not_one_is_refused(self):
        """R-BKP-14 — a job handed a time the machine cannot read is a daily backup that
        never runs, and nothing would say so."""
        for said in ("half past four", "25:00", "04:70", 4):
            self.wrote({"backups": {"at": said}})
            with self.assertRaises(config.Unreadable, msg=f"{said!r} was accepted"):
                config.backups(self.where)

    def test_a_time_of_day_is_read_the_way_a_person_writes_one(self):
        """R-BKP-13 — stated as a person states it, and settled into one spelling here so
        that whatever is given to the machine does not depend on how it was typed."""
        self.wrote({"backups": {"at": "4:05"}})
        self.assertEqual("04:05", config.backups(self.where)["at"])

    def test_the_automatic_update_time_is_the_owners_to_state(self):
        """R-UPD-42"""
        self.assertEqual(config.INITIAL["updates"], config.updates(self.where))
        self.wrote({"updates": {"at": "2:30"}})
        self.assertEqual({"at": "02:30"}, config.updates(self.where))

    def test_an_unreadable_automatic_update_time_is_refused(self):
        """R-UPD-42 — silently retaining the old calendar would make config.json untrue."""
        for said in ("after lunch", "24:00", "03:75", 3):
            self.wrote({"updates": {"at": said}})
            with self.assertRaises(config.Unreadable, msg=f"{said!r} was accepted"):
                config.updates(self.where)


if __name__ == "__main__":
    unittest.main()
