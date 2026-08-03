"""What rundesk guarantees about a program it runs — every row of platform-process.

Nothing here runs a provider or reaches the network: the program under test is the Python
already running the suite, which is also the one program guaranteed to be present on any
machine this can run on.

The waits are shortened rather than real. A test that spent the true silence window would
take half an hour, and one that spent the true grace period would take five seconds per
program ended — so both are turned down in `setUp` and the behavior, not the duration, is
what is asserted.
"""

import asyncio
import os
import shutil
import signal
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk import process  # noqa: E402

PY = sys.executable


def script(*lines: str) -> list[str]:
    """A program, spelled out, located rather than named (R-PROC-2)."""
    return [PY, "-c", "\n".join(lines)]


def forever() -> list[str]:
    """A program with no end of its own — still running whenever a test acts on it."""
    return script("import time; time.sleep(300)")


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


async def gone_within(pid: int, seconds: float = 10.0) -> bool:
    """Wait for a pid to really be gone, giving the loop its turn while waiting.

    Awaited, not slept through. A program we started is our own child, so it stays a
    zombie — and `os.kill(pid, 0)` still finds it — until something reaps it, and the
    only thing that does is the `wait()` running on this loop. Blocking here starves
    that reaper, so this would report every ended program as still running and only
    pass when the reaping happened to land before the check.
    """
    deadline = time.time() + seconds
    while time.time() < deadline:
        if not alive(pid):
            return True
        await asyncio.sleep(0.05)
    return not alive(pid)


class Quickened(unittest.IsolatedAsyncioTestCase):
    """Every case here, with the real-world waits turned down."""

    GRACE = 0.5
    DRAIN = 0.5

    def setUp(self):
        for name, value in (("GRACE_SECONDS", self.GRACE), ("DRAIN_SECONDS", self.DRAIN)):
            self.addCleanup(setattr, process, name, getattr(process, name))
            setattr(process, name, value)

    def scratch(self) -> Path:
        made = Path(tempfile.mkdtemp(prefix="rundesk-test-"))
        self.addCleanup(shutil.rmtree, made, True)
        return made


class TheEnvironmentAProgramIsGiven(Quickened):
    async def test_what_it_is_given_is_what_it_sees(self):
        """R-PROC-1"""
        result = await process.run(
            script("import os; print(os.environ.get('RUNDESK_TEST', 'absent'))"),
            env={"RUNDESK_TEST": "chosen"},
        )
        self.assertEqual("chosen", result.output.strip())

    async def test_what_it_is_not_given_it_does_not_see(self):
        """R-PROC-1 — the environment is built, not inherited, so the machine's own
        variables are absent unless rundesk put them there."""
        os.environ["RUNDESK_LEAK_CHECK"] = "leaked"
        self.addCleanup(os.environ.pop, "RUNDESK_LEAK_CHECK", None)
        result = await process.run(
            script("import os; print(os.environ.get('RUNDESK_LEAK_CHECK', 'absent'))"),
            env={},
        )
        self.assertEqual("absent", result.output.strip())

    def test_the_environment_carries_what_a_program_needs_to_find_itself(self):
        """R-PROC-1"""
        # `clear=True` is the whole point, not tidiness: an agent runs this suite from
        # inside rundesk, which hands every program it starts the live install's
        # `RUNDESK_SCRIPTS` — read before the data directory this case sets, so without
        # it the owner's own paths come back and three cases fail for nobody but an agent.
        with unittest.mock.patch.dict(
                os.environ, {"RUNDESK_DATA_DIR": "/tmp/rundesk-data"}, clear=True):
            built = process.environment(Path("/tmp/rundesk-home"), path="/usr/bin")
        self.assertEqual("/tmp/rundesk-home", built["RUNDESK_HOME"])
        self.assertEqual("/tmp/rundesk-data/scripts:/usr/bin", built["PATH"])
        # The two reasons this is a function rather than a literal: a provider that
        # believes a person is watching renders for one, and a program told nothing
        # about text falls back to ASCII and dies on the first accented character.
        self.assertEqual("dumb", built["TERM"])
        self.assertIn("UTF-8", built["LANG"])

    def test_an_owner_command_is_first_on_every_programs_path(self):
        """R-PROC-22 — a provider and every shell it starts inherit one stable command
        name, independent of the directory the agent happens to be working in."""
        # Cleared for the reason above: an agent's own RUNDESK_SCRIPTS would win.
        with unittest.mock.patch.dict(
                os.environ, {"RUNDESK_DATA_DIR": "/tmp/rundesk-data"}, clear=True):
            built = process.environment(Path("/tmp/rundesk-home"), path="/usr/bin:/bin")
        self.assertEqual(
            ["/tmp/rundesk-data/scripts", "/usr/bin", "/bin"],
            built["PATH"].split(os.pathsep))

    def test_a_program_is_told_where_owner_commands_stand(self):
        """R-PROC-23 — a skill can locate support files without hard-coding where this
        install keeps its data."""
        # Cleared for the reason above: an agent's own RUNDESK_SCRIPTS would win.
        with unittest.mock.patch.dict(
                os.environ, {"RUNDESK_DATA_DIR": "/tmp/rundesk-data"}, clear=True):
            built = process.environment(Path("/tmp/rundesk-home"), path="/usr/bin")
        self.assertEqual("/tmp/rundesk-data/scripts", built["RUNDESK_SCRIPTS"])
        self.assertEqual("/tmp/rundesk-data/skills", built["RUNDESK_SKILL_LIBRARY"])

    def test_a_nested_rundesk_keeps_the_script_library_it_was_given(self):
        """R-PROC-22, R-PROC-23 — redirects survive more than one agent turn."""
        with unittest.mock.patch.dict(
                os.environ, {"RUNDESK_SCRIPTS": "/tmp/redirected/scripts"}, clear=True):
            built = process.environment(Path("/tmp/rundesk-home"), path="/usr/bin")
        self.assertEqual("/tmp/redirected/scripts", built["RUNDESK_SCRIPTS"])
        self.assertEqual("/tmp/redirected/scripts", built["PATH"].split(os.pathsep)[0])

    def test_a_nested_rundesk_keeps_the_skill_library_it_was_given(self):
        """R-AGT-30, R-PROC-23 — companion skills land in the active library."""
        with unittest.mock.patch.dict(
                os.environ, {"RUNDESK_SKILL_LIBRARY": "/tmp/redirected/skills"}, clear=True):
            built = process.environment(Path("/tmp/rundesk-home"), path="/usr/bin")
        self.assertEqual("/tmp/redirected/skills", built["RUNDESK_SKILL_LIBRARY"])

    def test_the_environment_says_where_agents_are_kept(self):
        """R-SCH-27 — a program rundesk starts may itself be rundesk, and everything of an
        agent's is derived from this one root. Left out, a scheduled `rundesk ask ava`
        answered NO SUCH AGENT while the gateway that started it was running ava."""
        built = process.environment(Path("/tmp/rundesk-home"), path="/usr/bin",
                                    agents=Path("/tmp/somewhere/agents"))
        self.assertEqual("/tmp/somewhere/agents", built["RUNDESK_AGENTS_DIR"])

    def test_where_agents_are_kept_is_carried_on_when_it_was_not_passed(self):
        """R-SCH-27 — forwarded rather than defaulted, so the default lives in one place.
        A caller that knows where agents are says so; one that does not passes on what it
        was itself given."""
        os.environ["RUNDESK_AGENTS_DIR"] = "/tmp/handed-down/agents"
        self.addCleanup(os.environ.pop, "RUNDESK_AGENTS_DIR", None)
        built = process.environment(Path("/tmp/rundesk-home"), path="/usr/bin")
        self.assertEqual("/tmp/handed-down/agents", built["RUNDESK_AGENTS_DIR"])

    def test_nothing_is_said_about_agents_when_nothing_knows_where_they_are(self):
        """R-PROC-1 — with the variable unset, a program and whatever started it resolve
        the same root through the same code, so inventing a third copy of that default
        here would be one more thing to keep true rather than an answer."""
        was = os.environ.pop("RUNDESK_AGENTS_DIR", None)
        if was is not None:
            self.addCleanup(os.environ.__setitem__, "RUNDESK_AGENTS_DIR", was)
        built = process.environment(Path("/tmp/rundesk-home"), path="/usr/bin")
        self.assertNotIn("RUNDESK_AGENTS_DIR", built)

    def test_a_program_is_told_what_this_install_calls_its_jobs(self):
        """R-INS-18 — a program rundesk starts may itself be rundesk, and `rundesk update`
        inside a turn is a supported path. A launchd label belongs to the *person* rather
        than to an install, so nothing a directory is pointed at moves it: a child that
        resolved the default would ask after the first install's gateway and boot out the
        first install's update worker, from a turn the second install started."""
        with unittest.mock.patch.dict(
                os.environ, {"RUNDESK_JOB_PREFIX": "ai.rundesk-station"}, clear=True):
            built = process.environment(Path("/tmp/rundesk-home"), path="/usr/bin")
        self.assertEqual("ai.rundesk-station", built["RUNDESK_JOB_PREFIX"])

    def test_nothing_is_said_about_job_names_when_this_install_uses_the_ones_that_ship(self):
        """R-PROC-1 — forwarded rather than defaulted, for the reason above: unset already
        resolves to what rundesk ships, through the same code."""
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            built = process.environment(Path("/tmp/rundesk-home"), path="/usr/bin")
        self.assertNotIn("RUNDESK_JOB_PREFIX", built)

    def test_every_program_is_given_every_value_this_install_keeps(self):
        """R-SEC-1 — an integration command finds its credential because the shell it runs
        in descends from a program started with this, and that is the whole delivery."""
        built = process.environment(Path("/tmp/rundesk-home"), path="/usr/bin",
                                    secrets={"GITHUB_TOKEN": "gh-x", "LINEAR_KEY": "ln-y"})
        self.assertEqual("gh-x", built["GITHUB_TOKEN"])
        self.assertEqual("ln-y", built["LINEAR_KEY"])

    def test_a_value_rundesk_was_not_allowed_to_keep_is_left_out(self):
        """R-SEC-14 — the refusal that is true whatever is in the file an owner or an agent
        writes, including after a hand-edit. Everything rundesk decided about this program
        must survive contact with a value that claims the same name."""
        mine = process.environment(Path("/tmp/rundesk-home"), path="/usr/bin",
                                   agents=Path("/tmp/somewhere/agents"))
        built = process.environment(
            Path("/tmp/rundesk-home"), path="/usr/bin", agents=Path("/tmp/somewhere/agents"),
            secrets={name: "taken" for name in mine} | {"GITHUB_TOKEN": "gh-x"})

        for name, value in mine.items():
            self.assertEqual(value, built[name], f"a kept value took {name}")
        self.assertEqual("gh-x", built["GITHUB_TOKEN"])

    def test_a_program_is_given_nothing_of_its_own_when_this_install_keeps_nothing(self):
        """R-PROC-1 — the set is what it always was, so an install with nothing kept starts
        programs in byte-identical environments to the ones that shipped."""
        bare = process.environment(Path("/tmp/rundesk-home"), path="/usr/bin")
        for nothing in (None, {}):
            with self.subTest(secrets=nothing):
                self.assertEqual(
                    bare, process.environment(Path("/tmp/rundesk-home"), path="/usr/bin",
                                              secrets=nothing))


class FindingTheProgram(Quickened):
    async def test_a_program_named_rather_than_located_is_refused(self):
        """R-PROC-2 — a bare name resolves in a shell and nowhere else."""
        with self.assertRaises(process.NotAbsolute):
            await process.run(["python3", "-c", "pass"])

    async def test_naming_no_program_at_all_is_refused(self):
        """R-PROC-2"""
        with self.assertRaises(process.NotAbsolute):
            await process.run([])


class WhatAProgramSays(Quickened):
    async def test_everything_it_writes_out_is_passed_on(self):
        """R-PROC-3 — both of the two ways a program speaks, in the order it spoke."""
        result = await process.run(
            script(
                "import sys",
                "print('first')",
                "sys.stdout.flush()",
                "print('second', file=sys.stderr)",
                "sys.stderr.flush()",
                "print('third')",
            )
        )
        self.assertEqual(["first", "second", "third"], result.output.split())

    async def test_what_it_says_arrives_while_it_is_still_running(self):
        """R-PROC-3 — a turn is watched as it happens, not read afterwards.

        Asserted by when the first line lands, not by what was collected at the end: a
        version that held everything and replayed it once the program exited would leave
        exactly the same list behind.
        """
        seen: list[str] = []
        first = asyncio.Event()

        def note(line: str) -> None:
            seen.append(line)
            first.set()

        program = process.Program(
            script(
                "import sys, time",
                "print('early'); sys.stdout.flush()",
                "time.sleep(30)",
            ),
            silence=30.0,
        )
        await program.start()
        waiting = asyncio.ensure_future(program.wait(note))
        await asyncio.wait_for(first.wait(), 5.0)  # long before the program is done
        self.assertEqual(["early"], seen)
        await program.end()
        await waiting

    async def test_one_enormous_line_is_passed_on_whole(self):
        """R-PROC-3 — a brain reporting a large tool result writes one very long line,
        and asking a stream for 'a line' is what breaks on exactly that."""
        size = process.READ_BYTES * 3
        seen: list[str] = []
        result = await process.run(
            script(f"print('x' * {size})"),
            on_line=seen.append,
        )
        self.assertTrue(result.ok)
        self.assertEqual([size], [len(line) for line in seen])

    async def test_what_it_says_survives_being_split_mid_character(self):
        """R-PROC-3 — a chunk boundary can fall inside a multi-byte character, and the
        text either side of it is still the text the program wrote.

        Three bytes per character, not two, and that is the whole test. A read size that
        divides evenly by the width of a character puts every boundary between characters
        by luck, so a version with no incremental decoding at all passes — which is what
        this test did before, with an accented letter.
        """
        wide, many = "€", 40000
        self.assertTrue(process.READ_BYTES % len(wide.encode()) != 0, "pick a width that splits")
        result = await process.run(script(f"print({wide!r} * {many})"))
        self.assertNotIn("�", result.output, "a character was cut in half by a read")
        self.assertEqual(many, result.output.count(wide))

    async def test_only_a_tail_is_kept_however_much_it_says(self):
        """R-PROC-3 — everything is passed on as it arrives; a session of hours is not
        also accumulated to be handed back at the end."""
        seen: list[str] = []
        said = process.RETAINED_LINES * 3
        result = await process.run(
            script(f"[print(i) for i in range({said})]"),
            on_line=seen.append,
        )
        self.assertEqual(said, len(seen))
        self.assertEqual(process.RETAINED_LINES, len(result.output.splitlines()))
        self.assertEqual(str(said - 1), result.output.splitlines()[-1])


class HowLongAProgramMayTake(Quickened):
    async def test_a_program_that_keeps_talking_is_left_to_run(self):
        """R-PROC-6 — the guarantee a session of hours rests on: what ends a program is
        going quiet, never how long it has been going."""
        silence = 0.4
        result = await process.run(
            script(
                "import sys, time",
                "for _ in range(12):",
                "    print('working'); sys.stdout.flush(); time.sleep(0.1)",
            ),
            silence=silence,
        )
        self.assertTrue(result.ok, "a program that never went quiet was ended anyway")
        self.assertEqual(12, len(result.output.splitlines()))

    async def test_a_program_that_never_stops_talking_is_still_ended_eventually(self):
        """R-PROC-13 — the shape silence cannot see: wedged in a loop that keeps
        announcing itself. Nothing would ever end it, and it would run until a person
        noticed."""
        program = process.Program(
            script("import sys, time", "while True: print('retrying'); sys.stdout.flush(); time.sleep(0.05)"),
            silence=30.0,
            ceiling=0.5,
        )
        await program.start()
        pid = program.pid
        result = await asyncio.wait_for(program.wait(), 20)
        self.assertEqual(process.OVERRAN, result.reason)
        self.assertTrue(await gone_within(pid))

    async def test_running_a_long_time_is_not_by_itself_a_reason_to_be_ended(self):
        """R-PROC-13 — the ceiling is a backstop, never the instrument. A session that
        runs for hours and finishes is not what it is for."""
        result = await process.run(
            script("import sys, time", "for _ in range(6): print('working'); sys.stdout.flush(); time.sleep(0.05)"),
            silence=5.0,
            ceiling=30.0,
        )
        self.assertTrue(result.ok, "a program well inside the ceiling was ended anyway")

    async def test_a_program_may_be_allowed_to_run_without_any_ceiling(self):
        """R-PROC-13"""
        result = await process.run(script("print('done')"), ceiling=None)
        self.assertTrue(result.ok)

    async def test_overrunning_is_told_apart_from_going_quiet(self):
        """R-PROC-8 — wedged-and-talking and wedged-and-silent are different faults and
        send a reader somewhere different."""
        talking = process.Program(
            script("import sys, time", "while True: print('.'); sys.stdout.flush(); time.sleep(0.05)"),
            silence=30.0, ceiling=0.5,
        )
        await talking.start()
        self.assertEqual(process.OVERRAN, (await asyncio.wait_for(talking.wait(), 20)).reason)
        quiet = process.Program(forever(), silence=0.3, ceiling=30.0)
        await quiet.start()
        self.assertEqual(process.SILENT, (await asyncio.wait_for(quiet.wait(), 20)).reason)

    async def test_a_program_that_closes_its_output_is_still_held_to_the_ceiling(self):
        """R-PROC-13 — the ceiling is checked while a program is talking, and a program
        that closes what it writes out stops being read at all. Bounding what follows by
        the silence alone loses the ceiling there, and a program allowed to be quiet
        indefinitely is then waited on forever — the one thing the ceiling prevents."""
        for silence in (None, 30.0):
            with self.subTest(silence=silence):
                program = process.Program(
                    script("import os, time", "os.close(1)", "os.close(2)", "time.sleep(300)"),
                    silence=silence, ceiling=0.5,
                )
                await program.start()
                pid = program.pid
                result = await asyncio.wait_for(program.wait(), 20)
                self.assertEqual(process.OVERRAN, result.reason)
                self.assertTrue(await gone_within(pid))

    async def test_a_program_that_closes_its_output_and_goes_quiet_is_told_apart(self):
        """R-PROC-8 — silence running out first is a different answer from the ceiling
        running out first, even when the program stopped being readable in both."""
        program = process.Program(
            script("import os, time", "os.close(1)", "os.close(2)", "time.sleep(300)"),
            silence=0.4, ceiling=30.0,
        )
        await program.start()
        result = await asyncio.wait_for(program.wait(), 20)
        self.assertEqual(process.SILENT, result.reason)

    async def test_a_program_that_goes_quiet_is_ended(self):
        """R-PROC-7 — reported as silent *and* actually gone: saying so without ending
        it would leave a wedged session running with nothing watching it."""
        program = process.Program(forever(), silence=0.3)
        await program.start()
        pid = program.pid
        result = await program.wait()
        self.assertEqual(process.SILENT, result.reason)
        self.assertFalse(program.alive)
        self.assertTrue(await gone_within(pid))

    async def test_pauses_do_not_add_up_across_the_things_it_says(self):
        """R-PROC-6 — the case a long session actually looks like: quiet while each tool
        call runs, a word when it finishes, for hours. Those quiet stretches must be
        measured one at a time, because summed they pass any window you pick.
        """
        pause, allowed = process.POLL_SECONDS * 1.2, process.POLL_SECONDS * 1.5
        result = await process.run(
            script(
                "import sys, time",
                "for _ in range(3):",
                f"    time.sleep({pause}); print('tool call done'); sys.stdout.flush()",
            ),
            silence=allowed,
        )
        self.assertTrue(
            result.ok,
            "quiet stretches were added together, so a working session was ended",
        )
        self.assertEqual(3, len(result.output.splitlines()))

    async def test_going_quiet_is_measured_from_the_last_thing_it_said(self):
        """R-PROC-7 — not from when it started, or a long session would end mid-turn."""
        started = time.monotonic()
        result = await process.run(
            script(
                "import sys, time",
                "for _ in range(4):",
                "    print('.'); sys.stdout.flush(); time.sleep(0.1)",
                "time.sleep(300)",
            ),
            silence=0.4,
        )
        self.assertEqual(process.SILENT, result.reason)
        self.assertGreater(time.monotonic() - started, 0.4)


class EndingAProgram(Quickened):
    async def test_a_program_is_ended_whenever_rundesk_decides(self):
        """R-PROC-4"""
        program = process.Program(forever())
        await program.start()
        waiting = asyncio.ensure_future(program.wait())
        await program.end()
        result = await waiting
        self.assertEqual(process.ENDED, result.reason)
        self.assertFalse(program.alive)

    async def test_a_program_that_will_not_leave_is_ended_anyway(self):
        """R-PROC-4 — the polite signal is asked for, never waited on indefinitely.

        It says when it is deaf, and is not signalled until it has: signalled any sooner
        and the signal lands before the program is ignoring anything, so it dies politely
        and the case this test exists for never runs.
        """
        deaf = self.scratch() / "ignoring.now"
        program = process.Program(
            script(
                "import signal, time, pathlib",
                "signal.signal(signal.SIGTERM, signal.SIG_IGN)",
                f"pathlib.Path({str(deaf)!r}).write_text('ignoring')",
                "time.sleep(300)",
            ),
            # Bounded, so that a broken escalation fails this in seconds rather than
            # falling through to the real half-hour silence window — which in CI reads
            # as a stuck build rather than as the regression this test exists to catch.
            silence=5.0,
        )
        await program.start()
        waiting = asyncio.ensure_future(program.wait())
        self.assertIsNotNone(await self._reported(deaf), "it never got as far as ignoring us")
        await program.end()
        result = await waiting
        self.assertEqual(process.ENDED, result.reason)
        self.assertFalse(program.alive)

    async def test_ending_a_program_ends_what_it_started(self):
        """R-PROC-5 — a brain runs tools of its own, and they go with it.

        The grandchild reports itself through a file rather than the pipe: `wait()` is
        already reading that pipe, and a second reader on it would race for the line.
        """
        told = self.scratch() / "grandchild.pid"
        program = process.Program(
            script(
                "import subprocess, time, pathlib",
                f"child = subprocess.Popen({forever()!r})",
                f"pathlib.Path({str(told)!r}).write_text(str(child.pid))",
                "time.sleep(300)",
            )
        )
        await program.start()
        waiting = asyncio.ensure_future(program.wait())
        grandchild = await self._reported_pid(told)
        self.assertIsNotNone(grandchild, "the program never reported what it started")
        self.assertTrue(alive(grandchild))
        await program.end()
        await waiting
        self.assertTrue(await gone_within(grandchild), "what it started outlived it")

    async def test_what_a_finished_program_left_behind_is_ended_anyway_if_it_will_not_go(self):
        """R-PROC-11 — the leftover of a program that finished on its own, which does not
        take a hint. A tool a brain spawned is as free to ignore a polite signal as the
        brain is, and nothing else in this suite makes the second signal load-bearing.
        """
        told = self.scratch() / "grandchild.pid"
        program = process.Program(
            script(
                "import subprocess, pathlib, sys",
                "child = subprocess.Popen([{!r}, '-c', {!r}])".format(
                    PY,
                    "import signal, time, sys\n"
                    "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                    "time.sleep(300)\n",
                ),
                f"pathlib.Path({str(told)!r}).write_text(str(child.pid))",
            ),
            silence=30.0,
        )
        await program.start()
        waiting = asyncio.ensure_future(program.wait())
        grandchild = await self._reported_pid(told)
        self.assertIsNotNone(grandchild)
        await asyncio.wait_for(waiting, 30.0)
        self.assertTrue(await gone_within(grandchild), "a leftover that ignored the first signal survived")

    async def test_ending_waits_for_the_whole_tree_not_just_the_one_we_started(self):
        """R-PROC-5, R-PROC-11 — the one we started leaving is not the tree leaving. A
        child that closed the output it inherited and ignores the polite signal outlives
        its own parent, so returning when the parent goes reports a shutdown that ended
        nothing — and the gateway then deletes its record and exits reporting success."""
        told = self.scratch() / "grandchild.pid"
        deaf = (
            "import os, signal, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "os.close(1); os.close(2)\n"
            "time.sleep(300)\n"
        )
        program = process.Program(
            script(
                "import subprocess, pathlib, time",
                f"child = subprocess.Popen([{PY!r}, '-c', {deaf!r}])",
                f"pathlib.Path({str(told)!r}).write_text(str(child.pid))",
                "time.sleep(300)",
            ),
            silence=30.0,
        )
        await program.start()
        waiting = asyncio.ensure_future(program.wait())
        grandchild = await self._reported_pid(told)
        self.assertIsNotNone(grandchild)
        await program.end()
        self.assertFalse(
            alive(grandchild),
            "ending returned while a child that ignores the polite signal was still running",
        )
        await waiting

    async def test_giving_up_on_ending_a_program_still_ends_it(self):
        """R-PROC-5, R-PROC-11 — a shutdown that runs out of patience cancels this
        part-way through, having asked politely and not yet insisted. Unwinding there
        leaves running exactly the tree it was hurrying to end, which is how a gateway
        that reported it was out of time also left an orphan behind."""
        deaf = self.scratch() / "ignoring.now"
        program = process.Program(
            script(
                "import signal, time, pathlib",
                "signal.signal(signal.SIGTERM, signal.SIG_IGN)",
                f"pathlib.Path({str(deaf)!r}).write_text('ignoring')",
                "time.sleep(300)",
            ),
            silence=30.0,
        )
        await program.start()
        pid = program.pid
        waiting = asyncio.ensure_future(program.wait())
        self.assertIsNotNone(await self._reported(deaf), "it never got as far as ignoring us")
        ending = asyncio.ensure_future(program.end())
        await asyncio.sleep(0.1)          # it has asked politely and is still waiting
        ending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await ending
        self.assertTrue(await gone_within(pid), "giving up on ending it left it running")
        await asyncio.wait_for(waiting, 20)

    async def test_a_first_signal_that_does_not_land_is_not_the_end_of_it(self):
        """R-PROC-4 — being unable to ask politely is not a reason to stop asking. Giving
        up on the first refusal left the program running and said nothing about it."""
        attempts: list[int] = []
        real = os.killpg

        def awkward(pgid: int, sig: int) -> None:
            attempts.append(sig)
            if len(attempts) == 1:
                raise PermissionError("not that way")
            real(pgid, sig)

        self.addCleanup(setattr, process.os, "killpg", real)
        process.os.killpg = awkward
        program = process.Program(forever())
        await program.start()
        pid = program.pid
        waiting = asyncio.ensure_future(program.wait())
        await program.end()
        await waiting
        self.assertIn(signal.SIGKILL, attempts, "it never tried harder than the signal that failed")
        self.assertTrue(await gone_within(pid))

    async def test_what_a_finished_program_left_behind_does_not_outlive_it(self):
        """R-PROC-11 — a program that exits cleanly does not take its children with it:
        they are reparented, carry on, and keep holding the pipe we were reading."""
        told = self.scratch() / "grandchild.pid"
        program = process.Program(
            script(
                "import subprocess, pathlib",
                f"child = subprocess.Popen({forever()!r})",
                f"pathlib.Path({str(told)!r}).write_text(str(child.pid))",
            ),
            silence=30.0,
        )
        await program.start()
        waiting = asyncio.ensure_future(program.wait())
        grandchild = await self._reported_pid(told)
        self.assertIsNotNone(grandchild)
        result = await asyncio.wait_for(waiting, 20.0)
        self.assertEqual(process.FINISHED, result.reason)
        self.assertTrue(await gone_within(grandchild), "what it left behind outlived it")

    async def test_a_finished_program_is_not_waited_on_for_the_whole_silence(self):
        """R-PROC-6 — a leftover holding the pipe must not make a finished turn look
        like a session still in progress."""
        told = self.scratch() / "grandchild.pid"
        program = process.Program(
            script(
                "import subprocess, pathlib",
                f"child = subprocess.Popen({forever()!r})",
                f"pathlib.Path({str(told)!r}).write_text(str(child.pid))",
            ),
            silence=3600.0,  # an hour: if exiting is not noticed, this test hangs
        )
        started = time.monotonic()
        await program.start()
        result = await asyncio.wait_for(program.wait(), 20.0)
        self.assertEqual(process.FINISHED, result.reason)
        self.assertLess(time.monotonic() - started, 20.0)

    async def test_a_talkative_leftover_does_not_hold_the_drain_open_forever(self):
        """R-PROC-11, R-PROC-13 — the drain is a deadline, not a per-read timeout.

        Spent per read, a child that inherited the pipe and keeps writing more often than
        the drain allows completes every read, and the loop goes round again with nothing
        ever deciding it has drained. The wait then ran on to the 48-hour ceiling holding
        the name against a restart of that work. Anything talkative does it — a dev
        server, a language server, a log being followed.
        """
        told = self.scratch() / "grandchild.pid"
        program = process.Program(
            script(
                "import subprocess, pathlib, sys",
                # Writes every 0.05s: far more often than the drain, and it inherits the
                # pipe, so every read of ours comes back with something.
                "child = subprocess.Popen([sys.executable, '-c',",
                "    'import time,sys\\nwhile True:\\n print(\"still here\"); "
                "sys.stdout.flush(); time.sleep(0.05)'])",
                f"pathlib.Path({str(told)!r}).write_text(str(child.pid))",
            ),
            silence=3600.0,   # an hour, so nothing but the drain can end this
            ceiling=3600.0,   # and an hour again: reaching either means the drain failed
        )
        await program.start()
        waiting = asyncio.ensure_future(program.wait())
        grandchild = await self._reported_pid(told)
        self.assertIsNotNone(grandchild)
        # Bounded well under both, so a drain that never decides fails here rather than
        # turning a regression into a build that appears to hang.
        result = await asyncio.wait_for(waiting, 25.0)
        self.assertEqual(process.FINISHED, result.reason)
        self.assertTrue(await gone_within(grandchild), "the leftover outlived the drain")

    async def test_ending_says_whether_the_group_really_went(self):
        """R-PROC-5, R-GW-17 — both signals can go out, the grace period can pass, and
        the group can still be there. Saying nothing about it meant a shutdown could not
        tell 'ended' from 'asked twice and it is still there': it saw no timeout, called
        itself drained, and deleted the record naming the survivors."""
        program = process.Program(forever(), silence=30.0)
        await program.start()
        pid = program.pid
        waiting = asyncio.ensure_future(program.wait())
        self.assertTrue(await program.end(), "it ended the program and would not say so")
        self.assertTrue(await gone_within(pid))
        await asyncio.wait_for(waiting, 20)

    async def test_ending_something_that_will_not_go_says_it_did_not(self):
        """R-PROC-5, R-GW-17 — the answer that matters, since it is the one that decides
        whether anything is left behind for a successor to find."""
        program = process.Program(forever(), silence=30.0)
        await program.start()
        waiting = asyncio.ensure_future(program.wait())
        # Every signal lands nowhere, so the group is exactly as alive at the end as at
        # the start — the shape of a process that cannot be killed from here.
        self.addCleanup(setattr, os, "killpg", os.killpg)
        real = os.killpg
        os.killpg = lambda pgid, sig: None if sig else real(pgid, 0)
        self.assertFalse(await program.end(), "it could not end the group and said it had")
        self.assertFalse(await process.end_all([program]), "end_all reported them all gone")
        os.killpg = real
        await program.end()
        await asyncio.wait_for(waiting, 20)

    async def test_ending_nothing_at_all_is_a_success(self):
        """R-PROC-5 — a program that was never started has left nothing out there, and a
        shutdown that treated that as a failure would report an orphan on every start it
        got as far as registering and no further."""
        self.assertTrue(await process.Program(forever()).end())
        self.assertTrue(await process.end_all([]))

    async def _reported(self, told: Path, seconds: float = 10.0):
        """Whatever the program wrote to `told`, once it has written it."""
        deadline = time.time() + seconds
        while time.time() < deadline:
            if told.exists() and told.read_text().strip():
                return told.read_text().strip()
            await asyncio.sleep(0.05)
        return None

    async def _reported_pid(self, told: Path, seconds: float = 10.0):
        said = await self._reported(told, seconds)
        return int(said) if said else None

    async def test_giving_up_on_a_program_does_not_leave_it_running(self):
        """R-PROC-4 — whoever was waiting going away is not a way for a program to survive."""
        program = process.Program(forever())
        await program.start()
        pid = program.pid
        waiting = asyncio.ensure_future(program.wait())
        await asyncio.sleep(0.1)
        waiting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiting
        self.assertTrue(await gone_within(pid))

    async def test_everything_still_running_is_ended_together(self):
        """R-PROC-11 — what the gateway reaches for when it is told to stop."""
        programs = [process.Program(forever()) for _ in range(3)]
        for program in programs:
            await program.start()
        pids = [p.pid for p in programs]
        waiting = [asyncio.ensure_future(p.wait()) for p in programs]
        await process.end_all(programs)
        await asyncio.gather(*waiting)
        for pid in pids:
            self.assertTrue(await gone_within(pid))


class ManyAtOnce(Quickened):
    HOW_MANY = 5

    async def test_programs_run_at_the_same_time_rather_than_in_turn(self):
        """R-PROC-10 — a gateway serving several agent sessions dispatches them all;
        one taking its time is not the others waiting."""
        each = 0.5
        started = time.monotonic()
        results = await asyncio.gather(
            *(
                process.run(script(f"import time; time.sleep({each}); print({i})"))
                for i in range(self.HOW_MANY)
            )
        )
        elapsed = time.monotonic() - started
        self.assertTrue(all(r.ok for r in results))
        self.assertLess(elapsed, each * self.HOW_MANY, "they ran one after another")

    async def test_what_each_says_reaches_only_its_own_caller(self):
        """R-PROC-10 — many sessions streaming at once, and no line lands in the wrong one."""
        seen: dict[int, list[str]] = {i: [] for i in range(self.HOW_MANY)}
        await asyncio.gather(
            *(
                process.run(
                    script(
                        "import sys, time",
                        f"for n in range(5): print('agent-{i}', n); sys.stdout.flush(); time.sleep(0.02)",
                    ),
                    on_line=seen[i].append,
                )
                for i in range(self.HOW_MANY)
            )
        )
        for i, lines in seen.items():
            self.assertEqual(5, len(lines))
            self.assertTrue(all(line.startswith(f"agent-{i} ") for line in lines))

    async def test_one_program_ending_badly_leaves_the_others_running(self):
        """R-PROC-10 — one agent session wedging is not the gateway's other sessions."""
        doomed = process.Program(forever(), silence=0.3)
        healthy = process.Program(
            script("import sys, time", "for _ in range(15): print('.'); sys.stdout.flush(); time.sleep(0.05)"),
            silence=5.0,
        )
        await doomed.start()
        await healthy.start()
        doomed_result, healthy_result = await asyncio.gather(doomed.wait(), healthy.wait())
        self.assertEqual(process.SILENT, doomed_result.reason)
        self.assertTrue(healthy_result.ok)
        self.assertEqual(15, len(healthy_result.output.splitlines()))


class TheAwkwardCases(Quickened):
    """The paths a program only takes when something is already going wrong."""

    async def test_output_with_no_line_ending_is_not_held_forever(self):
        """R-PROC-3 — a program that never ends a line must not be able to grow rundesk
        without bound, and what it said must not wait on a newline that never comes."""
        self.addCleanup(setattr, process, "MAX_LINE_CHARS", process.MAX_LINE_CHARS)
        process.MAX_LINE_CHARS = 1000
        arrived = asyncio.Event()
        seen: list[str] = []

        def note(line: str) -> None:
            seen.append(line)
            arrived.set()

        program = process.Program(
            script(
                "import sys, time",
                "sys.stdout.write('x' * 2000); sys.stdout.flush()",
                "time.sleep(30)",
            ),
            silence=30.0,
        )
        await program.start()
        waiting = asyncio.ensure_future(program.wait(note))
        # Passed on while the program is still running: without the cap this waits for
        # the program to exit, which is 30 seconds away.
        await asyncio.wait_for(arrived.wait(), 5.0)
        self.assertEqual(2000, len("".join(seen)))
        await program.end()
        await waiting

    async def test_the_last_thing_it_says_is_not_lost_for_want_of_a_newline(self):
        """R-PROC-3 — the final chunk of a stream often has no line ending."""
        result = await process.run(
            script("import sys; sys.stdout.write('the last word')")
        )
        self.assertTrue(result.ok)
        self.assertEqual("the last word", result.output)

    async def test_a_program_may_be_allowed_to_be_quiet_indefinitely(self):
        """R-PROC-6 — the longest-running case of all: no limit on silence at all."""
        result = await process.run(script("import time; time.sleep(0.2); print('done')"), silence=None)
        self.assertTrue(result.ok)
        self.assertEqual("done", result.output.strip())

    async def test_ending_a_program_that_already_finished_does_nothing(self):
        """R-PROC-4 — the gateway stopping ends everything it has, including whatever
        finished a moment before it was asked to."""
        program = process.Program(script("pass"))
        await program.start()
        result = await program.wait()
        self.assertEqual(process.FINISHED, result.reason)
        await program.end()  # no exception, and it stays finished
        await program.end()
        self.assertFalse(program.alive)

    async def test_ending_a_program_that_never_started_does_nothing(self):
        """R-PROC-4"""
        program = process.Program(script("pass"))
        await program.end()
        self.assertFalse(program.alive)
        self.assertIsNone(program.pid)

    async def test_a_handler_that_raises_does_not_leave_the_program_running(self):
        """R-PROC-11 — the caller's own line handler failing is an ordinary thing: it is
        writing each line on to somewhere that can refuse. Whatever goes wrong in here,
        the program does not get to outlive it."""
        program = process.Program(
            script("import sys, time", "print('a line'); sys.stdout.flush()", "time.sleep(300)"),
            silence=30.0,
        )
        await program.start()
        pid = program.pid

        def refuses(_line: str) -> None:
            raise RuntimeError("the handler could not take that")

        with self.assertRaises(RuntimeError):
            await program.wait(refuses)
        self.assertFalse(program.alive, "it survived its own reader failing")
        self.assertTrue(await gone_within(pid))

    async def test_the_last_character_is_not_lost_for_being_half_written(self):
        """R-PROC-3 — a program killed mid-write leaves part of a character behind, and
        a decoder holding those bytes back drops them silently when nothing asks again."""
        result = await process.run(
            script("import sys", "sys.stdout.buffer.write(b'said' + bytes([0xC3]))")
        )
        self.assertTrue(result.output.startswith("said"))
        self.assertGreater(len(result.output), len("said"), "the half-written character vanished")

    async def test_a_program_is_given_nothing_unless_rundesk_says_otherwise(self):
        """R-PROC-1 — the default is the guarantee. Inheriting whatever rundesk happens
        to hold would hand every secret it has to every program it runs."""
        os.environ["RUNDESK_SECRET_CHECK"] = "a token"
        self.addCleanup(os.environ.pop, "RUNDESK_SECRET_CHECK", None)
        result = await process.run(
            script(
                "import os",
                "print(os.environ.get('RUNDESK_SECRET_CHECK', 'absent'), os.environ.get('PATH', 'absent'))",
            )
        )
        self.assertEqual("absent absent", result.output.strip())

    async def test_a_program_that_stops_talking_but_keeps_running_is_not_waited_on_forever(self):
        """R-PROC-7 — the pipe closing is not the program dying. Anything that puts
        itself into the background closes what it writes out and carries on, and waiting
        on it with the silence window already spent is a wedge nothing recovers from:
        the work's name stays held against ever restarting it."""
        program = process.Program(
            script(
                "import os, sys, time",
                "os.close(1)",
                "os.close(2)",
                "time.sleep(300)",
            ),
            silence=1.0,
        )
        await program.start()
        pid = program.pid
        result = await asyncio.wait_for(program.wait(), 20)
        self.assertEqual(process.SILENT, result.reason)
        self.assertTrue(await gone_within(pid))

    async def test_a_group_that_vanishes_while_being_ended_is_not_chased(self):
        """R-PROC-4 — the program can go between deciding to end it and saying so, and
        there is then nothing to escalate to."""
        program = process.Program(forever())
        await program.start()
        pid = program.pid
        real = os.killpg

        def vanished(_pgid, _sig):
            raise ProcessLookupError("it went by itself")

        self.addCleanup(setattr, process.os, "killpg", real)
        process.os.killpg = vanished
        # Returns rather than escalating against nothing — and says the group is gone,
        # which is what a shutdown then decides on. Asserting only that it returned let
        # this pass whatever it answered.
        self.assertTrue(await program.end(), "a group that had already gone was not reported gone")
        process.os.killpg = real
        real(pid, signal.SIGKILL)

    async def test_reading_a_program_that_was_never_started_is_refused(self):
        """R-PROC-4 — a mistake in rundesk's own wiring says so rather than waiting on
        a program that does not exist."""
        program = process.Program(script("pass"))
        with self.assertRaises(RuntimeError):
            await program.wait()


class WhatBecameOfAProgram(Quickened):
    async def test_finishing_is_told_apart_from_being_ended(self):
        """R-PROC-8"""
        finished = await process.run(script("pass"))
        self.assertEqual(process.FINISHED, finished.reason)
        self.assertTrue(finished.ok)

        program = process.Program(forever())
        await program.start()
        waiting = asyncio.ensure_future(program.wait())
        await program.end()
        self.assertEqual(process.ENDED, (await waiting).reason)

    async def test_being_ended_is_told_apart_from_going_quiet(self):
        """R-PROC-8 — rundesk deciding, and rundesk giving up, are different answers."""
        quiet = await process.run(forever(), silence=0.3)
        self.assertEqual(process.SILENT, quiet.reason)

    async def test_failing_is_told_apart_from_finishing(self):
        """R-PROC-9"""
        result = await process.run(script("import sys; sys.exit(3)"))
        self.assertEqual(process.FAILED, result.reason)
        self.assertEqual(3, result.code)
        self.assertFalse(result.ok)

    async def test_dying_is_told_apart_from_finishing(self):
        """R-PROC-9 — a program the machine killed did not finish."""
        result = await process.run(script("import os, signal; os.kill(os.getpid(), signal.SIGKILL)"))
        self.assertEqual(process.FAILED, result.reason)
        self.assertNotEqual(0, result.code)


def echoes() -> list[str]:
    """A program that answers what it is written, a record at a time.

    Unbuffered on purpose: a program left to buffer answers only once it has gone, and
    what is being asserted is that an answer arrives while it is still running.
    """
    return script(
        "import sys",
        "for line in sys.stdin:",
        "    sys.stdout.write('heard ' + line)",
        "    sys.stdout.flush()",
    )


class Collected:
    """A receiver that keeps what it is handed, the way a real one would not."""

    def __init__(self):
        self.taken: list = []

    def __call__(self, record) -> None:
        self.taken.append(record)

    @property
    def records(self) -> list:
        return [one for one in self.taken if not isinstance(one, process.Gap)]

    @property
    def gaps(self) -> list:
        return [one for one in self.taken if isinstance(one, process.Gap)]

    async def until(self, many: int, seconds: float = 10.0) -> bool:
        deadline = time.time() + seconds
        while time.time() < deadline:
            if len(self.records) >= many:
                return True
            await asyncio.sleep(0.02)
        return len(self.records) >= many


class WritingToAProgramWhileItRuns(Quickened):
    async def test_a_program_is_written_to_while_it_is_running(self):
        """R-PROC-14 — the whole point: an answer comes back while it is still there."""
        program = process.Program(echoes(), takes_input=True, errors_apart=True, silence=None)
        await program.start()
        taken = Collected()
        reading = asyncio.ensure_future(program.wait(sink=taken))
        await program.send(b'{"say":"one"}')
        self.assertTrue(await taken.until(1), "nothing came back while it was running")
        self.assertEqual([b'heard {"say":"one"}'], taken.records)
        await program.send(b'{"say":"two"}')
        self.assertTrue(await taken.until(2))
        self.assertEqual(b'heard {"say":"two"}', taken.records[1])
        await program.end()
        await asyncio.wait_for(reading, 15)

    async def test_what_is_written_arrives_in_the_order_it_was_written(self):
        """R-PROC-14 — one record is one write, so two of them cannot interleave."""
        program = process.Program(echoes(), takes_input=True, errors_apart=True, silence=None)
        await program.start()
        taken = Collected()
        reading = asyncio.ensure_future(program.wait(sink=taken))
        await asyncio.gather(*(program.send(f"n{n}") for n in range(20)))
        self.assertTrue(await taken.until(20))
        self.assertEqual([f"heard n{n}".encode() for n in range(20)], taken.records[:20])
        await program.end()
        await asyncio.wait_for(reading, 15)

    async def test_two_writes_that_have_to_wait_still_arrive_whole_and_in_order(self):
        """R-PROC-14 — the case the small-record ordering test never reaches.

        A write only waits when what it is writing is past what the pipe will hold, and
        the wait is where the trouble was: on the oldest Python this supports, the
        transport keeps a single waiter and asserts nobody else is already there, so the
        second concurrent record raised `AssertionError` instead of arriving — and with
        assertions off it replaced the first waiter, which is a hang rather than an
        error. Two channel messages arriving together is this product's ordinary case."""
        big = 256 * 1024  # comfortably past any pipe buffer, so both sends must wait
        program = process.Program(
            script(
                "import sys, time",
                # Nothing is read for a moment, so both writes are still waiting when the
                # second one starts — which is the whole point of the case.
                "time.sleep(0.5)",
                "data = sys.stdin.buffer.read()",
                f"shape = data.replace(b'a' * {big}, b'A').replace(b'b' * {big}, b'B')",
                "sys.stdout.write(shape.decode('utf-8', 'replace').replace('\\n', '.') + '\\n')",
                "sys.stdout.flush()",
            ),
            takes_input=True, errors_apart=True, silence=None,
        )
        await program.start()
        taken = Collected()
        reading = asyncio.ensure_future(program.wait(sink=taken))
        await asyncio.gather(program.send(b"a" * big), program.send(b"b" * big))
        await program.close_input()
        await asyncio.wait_for(reading, 30)
        self.assertIn(taken.records[0], (b"A.B.", b"B.A."),
                      "two records that had to wait interleaved with each other")

    async def test_a_program_that_has_gone_is_not_written_to_forever(self):
        """R-PROC-14 — writing alone never raises, and on a program that has gone it
        silently discards what it was given. Waiting is the only place the truth arrives,
        so a write that skipped it would report every failed send as a success."""
        program = process.Program(script("import sys; sys.exit(0)"), takes_input=True)
        await program.start()
        result = await program.wait()
        self.assertTrue(result.ok)
        with self.assertRaises(process.NotListening):
            for _ in range(200):  # the transport notices the far end at its own pace
                await program.send(b"anyone there")
                await asyncio.sleep(0.01)

    async def test_a_program_not_started_to_be_written_to_says_so(self):
        """R-PROC-14 — input is closed unless rundesk said otherwise, and asking to write
        to one that has none is a mistake to report rather than a silent no-op."""
        program = process.Program(forever())
        await program.start()
        self.addCleanup(lambda: None)
        with self.assertRaises(process.NotListening):
            await program.send(b"hello")
        await program.end()

    async def test_writing_to_a_program_that_never_started_is_refused(self):
        """R-PROC-14 — mirrors `wait() before start()`."""
        with self.assertRaises(RuntimeError):
            await process.Program(forever()).send(b"hello")

    async def test_a_program_is_told_there_is_no_more_coming_without_being_ended(self):
        """R-PROC-20 — a program that reads its input to the end before it answers at all
        is waiting for exactly this, and ending it instead takes it away mid-answer."""
        program = process.Program(
            script(
                "import sys",
                "said = sys.stdin.buffer.read()",   # answers nothing until the end
                "sys.stdout.write('took %d\\n' % len(said)); sys.stdout.flush()",
            ),
            takes_input=True, errors_apart=True, silence=None,
        )
        await program.start()
        taken = Collected()
        reading = asyncio.ensure_future(program.wait(sink=taken))
        await program.send(b"four")
        self.assertFalse(await taken.until(1, 1.0), "it answered before it was told to")
        await program.close_input()
        self.assertTrue(await taken.until(1), "being told there was no more did not reach it")
        self.assertEqual([b"took 5"], taken.records)
        result = await asyncio.wait_for(reading, 15)
        self.assertTrue(result.ok, "it was ended rather than left to finish")

    async def test_writing_after_there_is_no_more_coming_is_refused(self):
        """R-PROC-20 — said once, and it stays said."""
        program = process.Program(forever(), takes_input=True)
        await program.start()
        await program.close_input()
        await program.close_input()  # asking twice is allowed
        with self.assertRaises(process.NotListening):
            await program.send(b"more")
        await program.end()

    async def test_telling_a_program_with_no_input_there_is_no_more_does_nothing(self):
        """R-PROC-20 — mirrors ending a program that never started."""
        await process.Program(forever()).close_input()
        program = process.Program(forever())
        await program.start()
        await program.close_input()
        self.assertTrue(program.alive)
        await program.end()


class TheTwoStreamsKeptApart(Quickened):
    async def test_the_two_streams_are_kept_apart(self):
        """R-PROC-15 — the opposite guarantee to `everything it writes out is passed on`,
        and deliberately so: anything not part of the structure corrupts what is parsed."""
        program = process.Program(
            script(
                "import sys",
                "sys.stderr.write('a warning\\n'); sys.stderr.flush()",
                "sys.stdout.write('{\"real\":1}\\n'); sys.stdout.flush()",
            ),
            errors_apart=True, silence=None,
        )
        await program.start()
        taken = Collected()
        result = await asyncio.wait_for(program.wait(sink=taken), 15)
        self.assertEqual([b'{"real":1}'], taken.records,
                         "what went wrong reached what is meant to be parsed")
        self.assertIn("a warning", program.errors)
        self.assertTrue(result.ok)

    async def test_a_program_is_not_held_up_by_a_stream_nobody_reads(self):
        """R-PROC-16 — the deadlock, and the reason keeping the streams apart is not free.

        A pipe nobody reads fills, and a program blocked writing to a full one stops
        reading what we write to it. Nothing here consumes what went wrong, because
        nothing is meant to have to: rundesk reads it whether or not anyone wants it.
        Bounded so a regression fails in seconds rather than reading as a stuck suite.
        """
        program = process.Program(
            script(
                "import sys",
                "sys.stderr.write('x' * 4000000)",   # far past any pipe
                "sys.stderr.flush()",
                "sys.stdout.write('done\\n'); sys.stdout.flush()",
            ),
            errors_apart=True, silence=None,
        )
        await program.start()
        taken = Collected()
        result = await asyncio.wait_for(program.wait(sink=taken), 20)
        self.assertEqual([b"done"], taken.records, "it never got past shouting")
        self.assertTrue(result.ok)

    async def test_a_conversation_larger_than_the_pipes_completes(self):
        """R-PROC-16 — neither side can finish unless the other is being drained, which
        is the classic deadlock in the one shape that actually reproduces it."""
        program = process.Program(
            script(
                "import sys",
                "sys.stdout.write('x' * 1000000 + '\\n'); sys.stdout.flush()",
                "said = sys.stdin.buffer.read()",
                "sys.stdout.write('took %d\\n' % len(said)); sys.stdout.flush()",
            ),
            takes_input=True, errors_apart=True, silence=None,
        )
        await program.start()
        taken = Collected()
        reading = asyncio.ensure_future(program.wait(sink=taken))
        await asyncio.wait_for(program.send(b"y" * 1000000), 20)
        program._proc.stdin.close()   # there is no more coming
        self.assertTrue(await taken.until(2, 20), "the conversation wedged")
        self.assertEqual(b"took 1000001", taken.records[1])
        await asyncio.wait_for(reading, 20)

    async def test_a_long_run_does_not_shrink_the_tail_it_is_keeping(self):
        """R-PROC-12 — the bound must not eat what it is there to preserve.

        Counting bytes beside a deque that also evicts on its own count is a byte total
        that only ever climbs: the deque drops the oldest silently, nothing subtracts it,
        and once the phantom total passes the bound the newest lines start being thrown
        away to chase it. A chatty program holding well under the byte cap collapsed to a
        single retained line — the one thing an operator needs when it goes wrong.
        """
        frame = process._Lines(None)
        for _ in range(300):
            frame.feed(b"x" * 200 + b"\n")        # settle past both bounds
        smallest = process.RETAINED_LINES
        for _ in range(5000):
            frame.feed(b"x" * 200 + b"\n")
            smallest = min(smallest, len(frame._tail))
        self.assertGreaterEqual(smallest, process.RETAINED_LINES - 1,
                                "the tail shrank while holding far less than it is allowed")
        self.assertLessEqual(frame._held_bytes, process.TAIL_BYTES)
        # And what it thinks it holds is what it holds.
        self.assertEqual(sum(len(one) for one in frame._tail), frame._held_bytes,
                         "the byte total drifted away from what is actually kept")

    async def test_a_tail_of_enormous_lines_is_bounded_by_bytes_not_by_count(self):
        """R-PROC-12 — two hundred of anything says nothing about how much that is."""
        frame = process._Lines(None)
        for _ in range(20):
            frame.feed(b"z" * 100000 + b"\n")
        self.assertLess(len(frame._tail), 20, "it kept every enormous line")
        self.assertLessEqual(frame._held_bytes, process.TAIL_BYTES + 100001)
        self.assertEqual(sum(len(one) for one in frame._tail), frame._held_bytes)

    async def test_what_went_wrong_is_not_held_against_the_machine(self):
        """R-PROC-12 — read whether or not anyone wants it is not read without bound."""
        program = process.Program(
            script(
                "import sys",
                "for n in range(20000): sys.stderr.write('line %d\\n' % n)",
                "sys.stderr.flush()",
                "sys.stdout.write('done\\n'); sys.stdout.flush()",
            ),
            errors_apart=True, silence=None,
        )
        await program.start()
        await asyncio.wait_for(program.wait(sink=Collected()), 20)
        self.assertLessEqual(len(program.errors.splitlines()), process.RETAINED_LINES)
        self.assertIn("line 19999", program.errors, "it kept the beginning, not the end")


class WhatAReceiverIsHanded(Quickened):
    async def test_a_receiver_that_fails_neither_stops_nor_ends_the_program(self):
        """R-PROC-17 — the deliberate opposite of `a handler that raises does not leave
        the program running`. For output nobody else holds, a receiver that cannot cope
        is a reason to stop; for a program still owed an answer, it is not."""
        program = process.Program(echoes(), takes_input=True, errors_apart=True, silence=None)
        await program.start()
        reading = asyncio.ensure_future(program.wait(sink=self._always_fails))
        await program.send(b"one")
        self.assertTrue(await self._given_up(program, 1), "the receiver's failure was simply lost")
        self.assertGreater(program.refused, 0)
        self.assertTrue(program.alive, "a receiver failing took the program with it")
        await program.send(b"two")   # and it is still being talked to
        self.assertTrue(await self._given_up(program, 2))
        await program.end()
        await asyncio.wait_for(reading, 15)

    async def test_a_receiver_that_fails_and_recovers_is_given_the_record_it_dropped(self):
        """R-PROC-17 — records are not independent: text arrives in pieces meant to be
        joined, so one skipped because a receiver was briefly rate-limited leaves it
        reading a sentence with a word missing and no way to know. Offered again, before
        anything later, until it is taken."""
        taken: list = []
        failures = [1]  # fails once, then recovers

        def flaky(record):
            if failures:
                failures.pop()
                raise RuntimeError("briefly unavailable")
            taken.append(record)

        program = process.Program(
            script("import sys",
                   "for n in range(3): sys.stdout.write('n%d\\n' % n)",
                   "sys.stdout.flush()"),
            errors_apart=True, silence=None,
        )
        await program.start()
        result = await asyncio.wait_for(program.wait(sink=flaky), 20)
        self.assertEqual([b"n0", b"n1", b"n2"], taken,
                         "the record it failed on was skipped rather than offered again")
        self.assertEqual(1, program.refused)
        self.assertEqual(0, program.undelivered, "a record it did take was written off")
        self.assertTrue(result.ok)

    async def test_a_receiver_given_up_on_is_told_where_the_record_went(self):
        """R-PROC-17 — a record written off silently is worse than one that never
        arrived: everything after it reads as though nothing were missing. The loss is
        handed over in the place it happened, before anything later."""
        taken: list = []

        def refuses_the_first(record):
            if record == b"n0":
                raise RuntimeError("this receiver cannot take that one")
            taken.append(record)

        program = process.Program(
            script("import sys",
                   "for n in range(3): sys.stdout.write('n%d\\n' % n)",
                   "sys.stdout.flush()"),
            errors_apart=True, silence=None,
        )
        await program.start()
        result = await asyncio.wait_for(program.wait(sink=refuses_the_first), 20)
        self.assertEqual([process.Gap(1, "not taken"), b"n1", b"n2"], taken,
                         "the gap did not land where the record was lost")
        self.assertEqual(1, program.undelivered)
        self.assertFalse(result.ok, "a run that lost a record reported that it was fine")

    async def _given_up(self, program, many: int, seconds: float = 10.0) -> bool:
        deadline = time.time() + seconds
        while time.time() < deadline:
            if program.undelivered >= many:
                return True
            await asyncio.sleep(0.02)
        return program.undelivered >= many

    @staticmethod
    def _always_fails(_record):
        raise RuntimeError("this receiver is broken")

    async def test_a_receiver_that_is_slow_does_not_slow_the_program(self):
        """R-PROC-17 — handed straight to a receiver, a slow one stops the reading, and
        for a program rundesk also writes to that is the deadlock above.

        Timed on the *program*, not on the call. Timing the call measured the receiver
        being cut off at the drain and read it as the program running free — so the
        assertion passed precisely because records were being lost."""
        taken = Collected()

        async def dawdles(record):
            await asyncio.sleep(0.2)
            taken(record)

        program = process.Program(
            script(
                "import sys",
                "for n in range(50): sys.stdout.write('n%d\\n' % n)",
                "sys.stdout.flush()",
            ),
            errors_apart=True, silence=None,
        )
        await program.start()
        began = time.monotonic()
        watching = asyncio.ensure_future(self._when_it_goes(program, began))
        result = await asyncio.wait_for(program.wait(sink=dawdles), 40)
        # Fifty records at a fifth of a second each is ten seconds of receiving. The
        # program itself waits for none of it, and every record still arrives.
        self.assertLess(await watching, 8.0, "the receiver held the program up")
        self.assertEqual(50, len(taken.records), "the receiver was cut off")
        self.assertTrue(result.ok)

    @staticmethod
    async def _when_it_goes(program, began: float) -> float:
        """How long the program itself took to exit, whatever the receiver is still doing."""
        while program.alive:
            await asyncio.sleep(0.02)
        return time.monotonic() - began

    async def test_what_a_receiver_never_got_is_counted_rather_than_discarded(self):
        """R-PROC-17 — the receiver's patience is bounded, so a slow enough one will not
        be handed everything. Cancelling delivery and saying nothing meant a run reported
        that it had finished while forty-nine of fifty records had quietly gone."""
        taken = Collected()

        async def dawdles(record):
            await asyncio.sleep(0.2)
            taken(record)

        program = process.Program(
            script("import sys",
                   "for n in range(30): sys.stdout.write('n%d\\n' % n)",
                   "sys.stdout.flush()"),
            errors_apart=True, silence=None, receiving=0.5,
        )
        await program.start()
        result = await asyncio.wait_for(program.wait(sink=dawdles), 20)
        self.assertGreater(program.undelivered, 0, "records went missing with nothing said")
        self.assertEqual(30, len(taken.records) + program.undelivered,
                         "what was framed is neither delivered nor accounted for")
        self.assertFalse(result.ok, "a run that lost most of its records reported success")

    async def test_a_receiver_is_not_cut_off_at_the_pace_a_departed_program_is_drained(self):
        """R-PROC-17 — the two waits are opposites and used to share one constant. A
        receiver spending a fifth of a second on a record, which a rate-limited channel
        post easily does, got nine of fifty while the run reported that it finished."""
        taken = Collected()

        async def dawdles(record):
            await asyncio.sleep(0.05)
            taken(record)

        program = process.Program(
            script("import sys",
                   "for n in range(30): sys.stdout.write('n%d\\n' % n)",
                   "sys.stdout.flush()"),
            errors_apart=True, silence=None,
        )
        await program.start()
        # `DRAIN_SECONDS` is 0.5 in this suite and the receiving alone needs three times
        # that. Shared, this is exactly the run that lost most of its output.
        result = await asyncio.wait_for(program.wait(sink=dawdles), 30)
        self.assertEqual(30, len(taken.records), "the receiver was cut off at the drain")
        self.assertEqual(0, program.undelivered)
        self.assertTrue(result.ok)

    async def test_a_run_that_lost_records_is_told_apart_from_one_that_did_not(self):
        """R-PROC-17 — `ok` is the whole answer most callers read, and a run whose
        account has holes in it is not one anything downstream can act on."""
        self.assertTrue(process.Result(process.FINISHED, 0).ok)
        self.assertFalse(process.Result(process.FINISHED, 0, undelivered=1).ok)
        self.assertFalse(process.Result(process.FAILED, 1).ok)

    async def test_a_receiver_that_never_reads_is_told_what_it_missed(self):
        """R-PROC-17 — what is held is bounded, so a receiver far enough behind loses
        records. Losing them silently would render a wrong answer with nothing to say it
        was wrong, so the loss is handed over in the place it happened."""
        self.addCleanup(setattr, process, "HELD_BYTES", process.HELD_BYTES)
        process.HELD_BYTES = 200
        held = process.Held()
        for n in range(100):
            held.offer(b"record %03d" % n)
        held.close()
        got = []
        while True:
            it = await held.next()
            if it is None:
                break
            got.append(it)
        self.assertIsInstance(got[0], process.Gap, "records went missing with nothing said")
        self.assertEqual("fell behind", got[0].why)
        self.assertEqual(b"record 099", got[-1], "it kept the beginning and lost the end")
        self.assertEqual(100, got[0].records + len(got) - 1)

    async def test_what_is_held_for_a_receiver_is_bounded_in_bytes(self):
        """R-PROC-12 — a bound counted in records bounds nothing, since one record may
        be megabytes. The bound that matters is on what is actually held."""
        self.addCleanup(setattr, process, "HELD_BYTES", process.HELD_BYTES)
        process.HELD_BYTES = 1000
        held = process.Held()
        for _ in range(50):
            held.offer(b"y" * 500)
        self.assertLessEqual(held._bytes, 1000 + 500, "it held more than it is allowed")
        self.assertGreater(held.lost, 0)

    async def test_records_lost_without_ever_being_held_are_bounded_too(self):
        """R-PROC-17 — the bound was one-sided. Saying a record was lost added weight and
        never checked it, so a program emitting nothing but records too large to hold grew
        the queue without limit — the loss markers becoming the thing that overran."""
        held = process.Held(256)
        for _ in range(10000):
            held.lose(1, "too large")
        self.assertLessEqual(held._bytes, 256 + process.HELD_OVERHEAD,
                             "it held more than it is allowed")
        self.assertEqual(10000, held.lost, "the count of what went is no longer exact")

    async def test_losses_of_one_kind_are_folded_together_rather_than_piled_up(self):
        """R-PROC-17 — one queue item per lost record is a queue bounded in bytes being
        filled by things that have none. Folded, the count stays exact and the queue
        stays a handful of items whatever was lost."""
        held = process.Held()
        for _ in range(500):
            held.lose(1, "too large")
        held.offer(b"and then a real one")
        held.lose(3, "too large")
        held.close()
        got = []
        while True:
            it = await held.next()
            if it is None:
                break
            got.append(it)
        self.assertEqual([process.Gap(500, "too large"), b"and then a real one",
                          process.Gap(3, "too large")], got)


class RecordsWholeOrNotAtAll(Quickened):
    async def test_a_record_is_never_passed_on_in_pieces(self):
        """R-PROC-18 — half a record is not a smaller record, it is a corrupt one, and a
        receiver lenient enough to take it turns a loud failure into a wrong answer."""
        self.addCleanup(setattr, process, "MAX_RECORD_BYTES", process.MAX_RECORD_BYTES)
        process.MAX_RECORD_BYTES = 1000
        program = process.Program(
            script(
                "import sys",
                "sys.stdout.write('y' * 5000 + '\\n')",
                "sys.stdout.write('{\"after\":1}\\n')",
                "sys.stdout.flush()",
            ),
            errors_apart=True, silence=None,
        )
        await program.start()
        taken = Collected()
        await asyncio.wait_for(program.wait(sink=taken), 15)
        self.assertEqual([b'{"after":1}'], taken.records,
                         "the oversize record was passed on in pieces")
        self.assertEqual(1, len(taken.gaps), "a record went missing with nothing said")
        self.assertEqual("too large", taken.gaps[0].why)
        self.assertEqual([b'{"after":1}'], taken.taken[1:],
                         "the framing did not survive the record that was dropped")

    async def test_a_record_at_the_limit_is_still_passed_on_whole(self):
        """R-PROC-18 — the cap drops what is past it, not what reaches it."""
        self.addCleanup(setattr, process, "MAX_RECORD_BYTES", process.MAX_RECORD_BYTES)
        process.MAX_RECORD_BYTES = 200000   # several reads' worth
        program = process.Program(
            script("import sys; sys.stdout.write('y' * 199999 + '\\n'); sys.stdout.flush()"),
            errors_apart=True, silence=None,
        )
        await program.start()
        taken = Collected()
        await asyncio.wait_for(program.wait(sink=taken), 15)
        self.assertEqual([b"y" * 199999], taken.records)
        self.assertEqual([], taken.gaps)

    async def test_a_record_split_across_reads_arrives_whole(self):
        """R-PROC-18 — a record is a unit, and where the reads happened to land is not
        something anything downstream may be made to care about."""
        program = process.Program(
            script("import sys; sys.stdout.write('z' * 300000 + '\\n'); sys.stdout.flush()"),
            errors_apart=True, silence=None,
        )
        await program.start()
        taken = Collected()
        await asyncio.wait_for(program.wait(sink=taken), 15)
        self.assertEqual([b"z" * 300000], taken.records)

    async def test_a_record_the_program_did_not_finish_is_not_passed_on_as_one(self):
        """R-PROC-18 — delivered, it would be indistinguishable from a whole one, and
        nothing downstream could tell a forgotten ending from a program killed
        mid-sentence."""
        program = process.Program(
            script(
                "import os, sys",
                "sys.stdout.write('{\"whole\":1}\\n{\"half\"')",
                "sys.stdout.flush()",
                "os._exit(1)",
            ),
            errors_apart=True, silence=None,
        )
        await program.start()
        taken = Collected()
        result = await asyncio.wait_for(program.wait(sink=taken), 15)
        self.assertEqual([b'{"whole":1}'], taken.records, "half a record was passed on")
        self.assertEqual(["unterminated"], [gap.why for gap in taken.gaps])
        self.assertEqual(process.FAILED, result.reason)

    async def test_bytes_that_are_not_text_survive_whole(self):
        """R-PROC-18 — a record is a unit for a parser, not prose for a person. Decoded,
        a byte it cannot read becomes a question mark nothing can tell from one the
        program meant."""
        program = process.Program(
            script("import sys; sys.stdout.buffer.write(b'\\xff\\xfe\\x00ok\\n'); "
                   "sys.stdout.buffer.flush()"),
            errors_apart=True, silence=None,
        )
        await program.start()
        taken = Collected()
        await asyncio.wait_for(program.wait(sink=taken), 15)
        self.assertEqual([b"\xff\xfe\x00ok"], taken.records)

    async def test_a_carriage_return_before_the_ending_is_not_part_of_the_record(self):
        """R-PROC-18 — one, and only at the end. Anywhere else it is data."""
        program = process.Program(
            script("import sys; sys.stdout.buffer.write(b'{\"a\":1}\\r\\nwith\\rin\\n'); "
                   "sys.stdout.buffer.flush()"),
            errors_apart=True, silence=None,
        )
        await program.start()
        taken = Collected()
        await asyncio.wait_for(program.wait(sink=taken), 15)
        self.assertEqual([b'{"a":1}', b"with\rin"], taken.records)

    async def test_a_record_too_big_before_its_ending_arrives_is_dropped_and_the_rest_kept(self):
        """R-PROC-18 — the shape the dropping exists for, and the one an oversize record
        arriving whole inside a single read never reaches: one so large it must be given
        up on before its ending has been seen at all. What matters is that the framing
        survives it, so the record after it is not swallowed too."""
        self.addCleanup(setattr, process, "MAX_RECORD_BYTES", process.MAX_RECORD_BYTES)
        process.MAX_RECORD_BYTES = 20000       # well under a single read
        program = process.Program(
            script(
                "import sys",
                # No ending for a long time, so it is given up on mid-flight, across
                # several reads — and only then finished.
                "sys.stdout.write('y' * 400000)",
                "sys.stdout.flush()",
                "sys.stdout.write('\\n{\"after\":1}\\n')",
                "sys.stdout.flush()",
            ),
            errors_apart=True, silence=None,
        )
        await program.start()
        taken = Collected()
        await asyncio.wait_for(program.wait(sink=taken), 20)
        self.assertEqual([b'{"after":1}'], taken.records,
                         "the framing did not recover from the record it gave up on")
        self.assertEqual([(1, "too large")], [(g.records, g.why) for g in taken.gaps],
                         "giving up on one record was counted more than once")

    async def test_two_programs_with_receivers_run_at_once_without_crossing(self):
        """R-PROC-10, R-PROC-17 — what is held for a receiver is the first new state this
        module has grown per program, and the whole architecture rests on nothing being
        shared between two of them."""
        programs, takers = [], []
        for tag in ("alpha", "beta"):
            program = process.Program(
                script("import sys",
                       f"for n in range(20): sys.stdout.write('{tag}-%d\\n' % n)",
                       "sys.stdout.flush()"),
                errors_apart=True, silence=None,
            )
            await program.start()
            taken = Collected()
            programs.append(asyncio.ensure_future(program.wait(sink=taken)))
            takers.append((tag, taken))
        await asyncio.wait_for(asyncio.gather(*programs), 20)
        for tag, taken in takers:
            self.assertEqual(20, len(taken.records))
            self.assertTrue(all(one.startswith(tag.encode()) for one in taken.records),
                            f"{tag} received another program's records")

    async def test_a_receiver_that_fails_after_being_awaited_is_survived_too(self):
        """R-PROC-17 — a receiver that does any real work fails from inside what it hands
        back, not from being called. That is the likely shape in practice, and the one a
        tidy-up moving the awaiting out of the guard would silently stop covering."""
        async def fails_later(_record):
            await asyncio.sleep(0)
            raise RuntimeError("this receiver is broken, but only once it gets going")

        program = process.Program(
            script("import sys; sys.stdout.write('{\"a\":1}\\n'); sys.stdout.flush()"),
            errors_apart=True, silence=None,
        )
        await program.start()
        result = await asyncio.wait_for(program.wait(sink=fails_later), 20)
        # The program is not blamed for it. The record is still lost, because this
        # receiver never recovers — which the outcome says separately, and truthfully.
        self.assertEqual(process.FINISHED, result.reason,
                         "the receiver failing was blamed on the program")
        self.assertEqual(0, result.code)
        self.assertEqual(1, program.refused)

    async def test_records_are_refused_from_a_program_whose_streams_are_folded(self):
        """R-PROC-15, R-PROC-18 — folded together, everything the program says went wrong
        arrives in the middle of what is meant to be parsed. The records would be
        corrupted by the very warning that explains why, and nothing downstream could tell
        that apart from the program talking nonsense."""
        program = process.Program(forever(), silence=None)   # streams folded, the default
        await program.start()
        with self.assertRaises(ValueError):
            await program.wait(sink=Collected())
        await program.end()

    async def test_an_empty_record_is_still_a_record(self):
        """R-PROC-18 — a bare ending is a keepalive in more than one protocol, and
        whether it means anything is not this module's to decide."""
        program = process.Program(
            script("import sys; sys.stdout.write('\\n\\nlast\\n'); sys.stdout.flush()"),
            errors_apart=True, silence=None,
        )
        await program.start()
        taken = Collected()
        await asyncio.wait_for(program.wait(sink=taken), 15)
        self.assertEqual([b"", b"", b"last"], taken.records)


class WhereAProgramStartsFrom(Quickened):
    async def test_a_program_starts_where_rundesk_puts_it(self):
        """R-PROC-19 — an agent brain works on a project rather than in the abstract, and
        the gateway is started by the machine in a directory nobody chose."""
        workspace = self.scratch()
        result = await process.run(script("import os; print(os.getcwd())"), cwd=workspace)
        self.assertEqual(workspace.resolve(), Path(result.output.strip()).resolve())

    async def test_a_program_rundesk_gives_no_directory_starts_where_rundesk_did(self):
        """R-PROC-19 — the default is unchanged, so nothing that ran before moves."""
        result = await process.run(script("import os; print(os.getcwd())"))
        self.assertEqual(str(Path.cwd().resolve()), str(Path(result.output.strip()).resolve()))


class WhatAProgramStillGetsByDefault(Quickened):
    async def test_a_program_is_given_no_input_and_one_stream_unless_rundesk_says_otherwise(self):
        """R-PROC-14, R-PROC-15 — the guard on both fields. What rundesk only reads must
        go on getting exactly the treatment it has always had."""
        program = process.Program(forever())
        self.assertFalse(program.takes_input)
        self.assertFalse(program.errors_apart)
        await program.start()
        self.assertIsNone(program._proc.stdin, "input was opened on a program nobody writes to")
        self.assertIsNone(program._proc.stderr, "the streams were kept apart uninvited")
        await program.end()

    async def test_what_went_wrong_still_arrives_in_the_order_it_was_said(self):
        """R-PROC-3 — folded together unless asked otherwise, which is what makes what a
        program said readable in the order it said it."""
        result = await process.run(
            script(
                "import sys",
                "sys.stdout.write('first\\n'); sys.stdout.flush()",
                "sys.stderr.write('second\\n'); sys.stderr.flush()",
            ),
        )
        self.assertEqual(["first", "second"], result.output.splitlines())


if __name__ == "__main__":
    unittest.main()
