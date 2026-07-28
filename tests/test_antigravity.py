"""Antigravity CLI provider adapter contract tests.

The parser is driven by a sanitized capture of Google's official ``agy`` 1.1.8
``stream-json`` output. Process tests use a local fake executable and never contact a
model, an account, or the network.

Run: python3 tests/test_antigravity.py
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
AT = ROOT / "src" / "providers" / "antigravity"
SAMPLE = ROOT / "tests" / "samples" / "antigravity-stream.jsonl"


def _adapter():
    loader = importlib.machinery.SourceFileLoader("rundesk_antigravity", str(AT))
    spec = importlib.util.spec_from_loader("rundesk_antigravity", loader)
    made = importlib.util.module_from_spec(spec)
    loader.exec_module(made)
    return made


antigravity = _adapter()

from rundesk import provider  # noqa: E402


def _seen(resume=None):
    return antigravity._new_seen(resume)


class StreamMapping(unittest.TestCase):
    def test_captured_stream_maps_once_and_uses_step_usage(self):
        """R-PRV-5, R-PRV-7, R-PRV-8, R-PRV-9, R-PRV-22, R-USE-3."""
        seen = _seen()
        records = []
        for line in SAMPLE.read_text().splitlines():
            records.extend(antigravity.records(line, seen))

        self.assertEqual(
            ["text", "tool", "result", "text", "text", "usage", "done"],
            [one["type"] for one in records],
        )
        self.assertEqual("I’ll check the README. ", records[0]["text"])
        self.assertNotIn("whole", records[0])
        self.assertEqual(
            {"type": "tool", "id": "agy:2", "name": "view_file", "did": "read"},
            records[1],
        )
        self.assertEqual(
            {"type": "result", "id": "agy:2", "ok": True,
             "summary": "view_file completed"},
            records[2],
        )
        self.assertEqual(
            {"type": "usage", "input": 3390, "output": 380, "cached": 16274,
             "model": "gemini-3.6-flash-low"},
            records[-2],
        )
        self.assertEqual(
            {"type": "done", "ok": True, "session": "conversation-alpha"},
            records[-1],
        )
        joined = "".join(one["text"] for one in records if one["type"] == "text")
        self.assertEqual(
            "I’ll check the README. Pocket Atlas turns place notes into a browsable "
            "HTML page.\n",
            joined,
        )

    def test_resumed_result_total_is_not_counted_again(self):
        """R-USE-3 — result usage is cumulative after --conversation."""
        seen = _seen("conversation-alpha")
        antigravity.records(json.dumps({
            "event": "init", "conversation_id": "conversation-alpha",
            "init": {"model": "gemini-3.6-flash-low"},
        }), seen)
        antigravity.records(json.dumps({
            "event": "step_update",
            "step_update": {
                "step_index": 9, "state": "DONE", "step_type": "agent_response",
                "text_delta": "\n",
                "usage": {"input_tokens": 12, "output_tokens": 3,
                          "cache_read_tokens": 40},
            },
        }), seen)
        records = antigravity.records(json.dumps({
            "event": "result",
            "result": {
                "conversation_id": "conversation-alpha", "status": "SUCCESS",
                "response": "\n",
                "usage": {"input_tokens": 999, "output_tokens": 888,
                          "cache_read_tokens": 777},
            },
        }), seen)
        self.assertEqual(
            {"type": "usage", "input": 12, "output": 3, "cached": 40,
             "model": "gemini-3.6-flash-low"},
            records[-2],
        )

    def test_terminal_response_is_fallback_not_duplicate(self):
        """R-PRV-7, R-PRV-22."""
        seen = _seen()
        records = antigravity.records(json.dumps({
            "event": "result",
            "result": {
                "conversation_id": "only-result", "status": "SUCCESS",
                "response": "One whole answer.",
                "usage": {"input_tokens": 4, "output_tokens": 2,
                          "cache_read_tokens": 1},
            },
        }), seen)
        self.assertEqual(
            {"type": "text", "text": "One whole answer.", "whole": True},
            records[0],
        )
        self.assertEqual("usage", records[1]["type"])
        self.assertTrue(records[2]["ok"])

    def test_permission_denial_corrects_false_success(self):
        """R-PRV-6, R-PRV-18 — agy 1.1.8 can say SUCCESS after a soft denial."""
        seen = _seen()
        error = antigravity.records(json.dumps({
            "event": "step_update",
            "step_update": {
                "step_index": 3, "state": "ERROR", "step_type": "tool",
                "tool_name": "write_to_file",
                "tool_info": {"error": {"type": "TOOL_ERROR",
                                       "message": "User denied permission for write_file(.)"}},
            },
        }), seen)
        self.assertEqual("edit", antigravity.DID["write_to_file"])
        self.assertFalse(error[0]["ok"])
        ended = antigravity.records(json.dumps({
            "event": "result",
            "result": {"conversation_id": "denied", "status": "SUCCESS",
                       "response": "", "usage": {}},
        }), seen)
        self.assertFalse(ended[-1]["ok"])
        self.assertNotIn("session", ended[-1])

    def test_unknown_and_malformed_lines_are_ignored(self):
        """R-PRV-5 — vendor drift remains in raw output, not invented records."""
        seen = _seen()
        self.assertEqual([], antigravity.records("not-json", seen))
        self.assertEqual([], antigravity.records("[]", seen))
        self.assertEqual([], antigravity.records('{"event":"future"}', seen))

    def test_unknown_tool_has_no_invented_verb(self):
        """R-PRV-8."""
        records = antigravity.records(json.dumps({
            "event": "step_update",
            "step_update": {"step_index": 4, "state": "ACTIVE", "step_type": "tool",
                            "tool_name": "future_tool"},
        }), _seen())
        self.assertEqual(
            {"type": "tool", "id": "agy:4", "name": "future_tool"},
            records[0],
        )

    def test_changed_resume_id_is_detected_at_init(self):
        """R-PRV-16 — an unknown id silently becomes a fresh agy conversation."""
        seen = _seen("wanted")
        antigravity.records(json.dumps({
            "event": "init", "conversation_id": "different", "init": {},
        }), seen)
        self.assertTrue(seen["resume_missed"])


class CommandPolicy(unittest.TestCase):
    def test_prompt_is_not_an_argument(self):
        """R-PRV-4 — a prompt belongs on stdin, not in the process list."""
        secret = "private words unique to this turn"
        argv = antigravity.opening("work", None, None, {})
        self.assertNotIn(secret, argv)
        self.assertNotIn("-p", argv)
        self.assertNotIn("--print", argv)
        self.assertEqual("stream-json", argv[argv.index("--output-format") + 1])

    def test_fresh_resume_model_and_postures(self):
        """R-PRV-9, R-PRV-17, R-PRV-18."""
        fresh = antigravity.opening("read", "gemini-3.6-flash-low", None, {})
        self.assertIn("--new-project", fresh)
        self.assertNotIn("--conversation", fresh)
        self.assertEqual("plan", fresh[fresh.index("--mode") + 1])
        self.assertIn("--sandbox", fresh)
        self.assertNotIn("--dangerously-skip-permissions", fresh)

        resumed = antigravity.opening("work", None, "conversation-alpha", {})
        self.assertNotIn("--new-project", resumed)
        self.assertEqual(
            "conversation-alpha", resumed[resumed.index("--conversation") + 1])
        self.assertEqual("accept-edits", resumed[resumed.index("--mode") + 1])
        self.assertIn("--dangerously-skip-permissions", resumed)

    def test_owned_flags_cannot_override_the_seam(self):
        """R-PRV-16, R-PRV-18."""
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            argv = antigravity.opening("read", None, None, {
                "flags": ["--effort", "high", "--mode", "accept-edits",
                          "--dangerously-skip-permissions", "--sandbox"],
            })
        self.assertIn("--effort", argv)
        self.assertIn("high", argv)
        self.assertEqual("plan", argv[argv.index("--mode") + 1])
        self.assertNotIn("--dangerously-skip-permissions", argv)
        self.assertIn("controlled by Rundesk", stderr.getvalue())

    def test_preface_is_added_to_prompt_not_argv(self):
        """R-PRV-14."""
        with mock.patch.dict(os.environ, {"RUNDESK_PREFACE": "Keep answers short."},
                             clear=False):
            prompt = antigravity._prompt("What changed?")
            argv = antigravity.opening("read", None, None, {})
        self.assertIn("Keep answers short.", prompt)
        self.assertTrue(prompt.endswith("What changed?"))
        self.assertFalse(any("Keep answers short." in word for word in argv))

    def test_settings_must_be_an_object_and_flags_strings(self):
        """R-PRV-16."""
        with mock.patch.dict(os.environ, {"RUNDESK_SETTINGS": "[]"}, clear=False):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual({}, antigravity._settings())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual([], antigravity._flags({"flags": ["--effort", 2]}))

    def test_child_environment_keeps_owner_login_and_disables_side_effects(self):
        """R-PRV-3 — authentication stays with the official native-keyring client."""
        child = antigravity._whose({"HOME": "/owner", "PATH": "/bin"})
        self.assertEqual("/owner", child["HOME"])
        self.assertNotIn("GOOGLE_APPLICATION_CREDENTIALS", child)
        self.assertEqual("true", child["AGY_CLI_DISABLE_AUTO_UPDATE"])
        self.assertEqual("true", child["AGY_CLI_HIDE_ACCOUNT_INFO"])


class Skills(unittest.TestCase):
    def test_grants_are_individual_symlinks_and_revoked_links_are_pruned(self):
        """R-PRV-24."""
        with tempfile.TemporaryDirectory() as made:
            base = Path(made)
            home = base / "home"
            granted = home / "skills"
            skill = granted / "one"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("# One\n")
            home.mkdir(exist_ok=True)
            with mock.patch.dict(os.environ, {"RUNDESK_SKILLS": str(granted)},
                                 clear=False):
                antigravity._present(str(home))
            link = home / ".agents" / "skills" / "one"
            self.assertTrue(link.is_symlink())
            self.assertEqual(skill.resolve(), link.resolve())
            self.assertFalse((home / ".agents" / "skills").is_symlink())

            (skill / "SKILL.md").unlink()
            skill.rmdir()
            with mock.patch.dict(os.environ, {"RUNDESK_SKILLS": str(granted)},
                                 clear=False):
                antigravity._present(str(home))
            self.assertFalse(link.exists())
            self.assertFalse(link.is_symlink())

    def test_hand_placed_directory_is_preserved(self):
        """R-PRV-24."""
        with tempfile.TemporaryDirectory() as made:
            home = Path(made) / "home"
            own = home / ".agents" / "skills" / "one"
            own.mkdir(parents=True)
            granted = home / "skills"
            (granted / "one").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"RUNDESK_SKILLS": str(granted)},
                                 clear=False):
                antigravity._present(str(home))
            self.assertTrue(own.is_dir())
            self.assertFalse(own.is_symlink())


class WholeProgram(unittest.TestCase):
    def _fake(self, directory: Path) -> Path:
        fake = directory / "fake-agy"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "args = sys.argv[1:]\n"
            "prompt = sys.stdin.read()\n"
            "capture = os.environ.get('FAKE_CAPTURE')\n"
            "if capture:\n"
            "  open(capture, 'w').write(json.dumps({'args': args, 'prompt': prompt}))\n"
            "session = 'conversation-fake'\n"
            "if '--conversation' in args:\n"
            "  session = args[args.index('--conversation') + 1]\n"
            "events = [\n"
            " {'event':'init','conversation_id':session,"
            "  'init':{'model':'gemini-3.6-flash-low'}},\n"
            " {'event':'step_update','step_update':{'step_index':2,'state':'ACTIVE',"
            "  'step_type':'agent_response','text_delta':'Hello from agy.'}},\n"
            " {'event':'step_update','step_update':{'step_index':2,'state':'DONE',"
            "  'step_type':'agent_response','text_delta':'\\n','usage':"
            "  {'input_tokens':4,'output_tokens':3,'cache_read_tokens':2}}},\n"
            " {'event':'result','result':{'conversation_id':session,'status':'SUCCESS',"
            "  'response':'Hello from agy.\\n','usage':"
            "  {'input_tokens':4,'output_tokens':3,'cache_read_tokens':2}}},\n"
            "]\n"
            "for event in events: print(json.dumps(event), flush=True)\n"
        )
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        return fake

    def test_process_handshake_keeps_prompt_on_stdin_and_raw_stream(self):
        """R-PRV-1, R-PRV-4, R-PRV-6, R-PRV-17."""
        with tempfile.TemporaryDirectory() as made:
            base = Path(made)
            fake = self._fake(base)
            capture = base / "capture.json"
            raw = base / "raw.jsonl"
            env = {
                "PATH": os.environ.get("PATH", ""),
                "HOME": str(base),
                "RUNDESK_ANTIGRAVITY_BIN": str(fake),
                "RUNDESK_CWD": str(base),
                "RUNDESK_RAW": str(raw),
                "RUNDESK_POSTURE": "read",
                "FAKE_CAPTURE": str(capture),
            }
            ran = subprocess.run(
                [sys.executable, str(AT)], input="A private prompt.", text=True,
                capture_output=True, env=env, timeout=10)
            self.assertEqual(0, ran.returncode, ran.stderr)
            records = [json.loads(line) for line in ran.stdout.splitlines()]
            self.assertEqual(["text", "text", "usage", "done"],
                             [one["type"] for one in records])
            self.assertEqual("conversation-fake", records[-1]["session"])
            handed = json.loads(capture.read_text())
            self.assertEqual("A private prompt.", handed["prompt"])
            self.assertNotIn("A private prompt.", handed["args"])
            self.assertIn("--new-project", handed["args"])
            self.assertEqual(4, len(raw.read_text().splitlines()))

    def test_capabilities_are_exact_and_offline(self):
        """R-PRV-15."""
        ran = subprocess.run([sys.executable, str(AT), "--capabilities"],
                             text=True, capture_output=True, timeout=5)
        self.assertEqual(0, ran.returncode)
        answer = json.loads(ran.stdout)
        self.assertEqual(set(provider.CAPABILITIES), set(answer))
        self.assertTrue(all(isinstance(value, bool) for value in answer.values()))
        self.assertEqual(antigravity.CAN, answer)

    def test_missing_binary_and_empty_prompt_end_the_turn(self):
        """R-PRV-6."""
        with tempfile.TemporaryDirectory() as made:
            env = {
                "PATH": "/usr/bin:/bin",
                "HOME": made,
                "RUNDESK_ANTIGRAVITY_BIN": str(Path(made) / "absent"),
                "RUNDESK_CWD": made,
            }
            missing = subprocess.run([sys.executable, str(AT)], input="hello",
                                     text=True, capture_output=True, env=env)
            self.assertNotEqual(0, missing.returncode)
            self.assertFalse(json.loads(missing.stdout)["ok"])

            fake = self._fake(Path(made))
            env["RUNDESK_ANTIGRAVITY_BIN"] = str(fake)
            empty = subprocess.run([sys.executable, str(AT)], input=" \n",
                                   text=True, capture_output=True, env=env)
            self.assertNotEqual(0, empty.returncode)
            self.assertEqual("nothing was asked",
                             json.loads(empty.stdout)["why"])


if __name__ == "__main__":
    unittest.main()
