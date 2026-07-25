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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk_cli import process  # noqa: E402

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


def gone_within(pid: int, seconds: float = 10.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if not alive(pid):
            return True
        time.sleep(0.05)
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
        built = process.environment(Path("/tmp/rundesk-home"), path="/usr/bin")
        self.assertEqual("/tmp/rundesk-home", built["RUNDESK_HOME"])
        self.assertEqual("/usr/bin", built["PATH"])
        # The two reasons this is a function rather than a literal: a provider that
        # believes a person is watching renders for one, and a program told nothing
        # about text falls back to ASCII and dies on the first accented character.
        self.assertEqual("dumb", built["TERM"])
        self.assertIn("UTF-8", built["LANG"])


class FindingTheProgram(Quickened):
    async def test_a_program_named_rather_than_located_is_refused(self):
        """R-PROC-2 — a bare name resolves in a shell and nowhere else."""
        with self.assertRaises(process.NotAbsolute):
            await process.run(["python3", "-c", "pass"])

    async def test_naming_no_program_at_all_is_refused(self):
        """R-PROC-2"""
        with self.assertRaises(process.NotAbsolute):
            await process.run([])

    def test_a_program_is_located_once_so_nothing_looks_again(self):
        """R-PROC-2"""
        self.assertEqual(PY, process.resolve(PY))
        self.assertIsNotNone(process.resolve("python3"))

    def test_a_program_that_is_not_there_resolves_to_nothing(self):
        """R-PROC-2"""
        self.assertIsNone(process.resolve("rundesk-no-such-program"))
        self.assertIsNone(process.resolve("/nonexistent/rundesk-no-such-program"))


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
        self.assertTrue(gone_within(pid))

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

    async def test_a_program_that_goes_quiet_is_ended(self):
        """R-PROC-7 — reported as silent *and* actually gone: saying so without ending
        it would leave a wedged session running with nothing watching it."""
        program = process.Program(forever(), silence=0.3)
        await program.start()
        pid = program.pid
        result = await program.wait()
        self.assertEqual(process.SILENT, result.reason)
        self.assertFalse(program.alive)
        self.assertTrue(gone_within(pid))

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
            )
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
        self.assertTrue(gone_within(grandchild), "what it started outlived it")

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
        self.assertTrue(gone_within(grandchild), "a leftover that ignored the first signal survived")

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
        self.assertTrue(gone_within(pid))

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
        self.assertTrue(gone_within(grandchild), "what it left behind outlived it")

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
        self.assertTrue(gone_within(pid))

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
            self.assertTrue(gone_within(pid))


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

    async def test_ending_nothing_at_all_is_allowed(self):
        """R-PROC-11 — the gateway stopping with no programs running is the ordinary case."""
        await process.end_all([])

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
        self.assertTrue(gone_within(pid))

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
        self.assertTrue(gone_within(pid))

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
        await program.end()  # returns rather than escalating against nothing
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


if __name__ == "__main__":
    unittest.main()
