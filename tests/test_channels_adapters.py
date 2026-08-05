"""Finding the program behind a channel, and the two questions asked of it before it is trusted.

Real programs on disk, never a stand-in for one. The whole point of the seam is that an adapter is
something the operating system runs rather than something Python imports, and a fake would prove
nothing about the part that matters — that a bare name resolves, that a program which dies without
answering is told apart from one that answered no, and that nothing of this process's environment
reaches it.

Run directly: `python3 tests/test_channels_adapters.py`
"""

import json
import os
import unittest

import support
from rundesk.channels import adapters
from rundesk.core import paths

#: An adapter that answers both questions and reaches what it was pointed at.
A_WORKING_ADAPTER = """#!/bin/sh
case "$1" in
  --capabilities) echo '{"stream": true, "max_text": 2000}' ;;
  --check) echo '{"ok": true, "describes": "a bot, reaching somebody", "notify_place": "1180",
                  "settings": {"guild": "9930"}, "secret": {"env": ["A_TOKEN"]},
                  "invite": "https://example.invalid/invite"}' ;;
esac
exit 0
"""

#: One that connects and is told no. It still exits 0 — what is read is the answer, not the code.
AN_ADAPTER_THAT_REFUSES = """#!/bin/sh
[ "$1" = "--check" ] && echo '{"ok": false, "why": "that token is not a bot"}'
exit 0
"""

#: One that dies without saying anything, which is a different thing from refusing.
AN_ADAPTER_THAT_DIES = """#!/bin/sh
echo 'Traceback (most recent call last):' >&2
echo 'ModuleNotFoundError: No module named discord' >&2
exit 1
"""

#: One that says something before its answer. The answer is still the last line.
A_CHATTY_ADAPTER = """#!/bin/sh
echo 'warning: this adapter is old'
echo '{"ok": true, "describes": "still fine", "secret": {"env": "ONE_TOKEN"}}'
exit 0
"""

#: One that reports what it was actually handed, so a case can see what reached it.
AN_ADAPTER_THAT_TELLS_ON_ITS_ENVIRONMENT = """#!/bin/sh
[ "$1" = "--check" ] && printf '{"ok": true, "describes": "%s", "settings": {}}\\n' "${SEEN:-nothing}"
exit 0
"""


class Adapters(support.Isolated):
    """A scratch install with somewhere for adapters to stand."""

    def setUp(self):
        super().setUp()
        # **`app/src` is stood up first, and that is not decoration.** `paths.code()` answers with
        # the *checkout* when the scratch root has no installed program tree — so without this, a
        # case writing a shipped adapter writes it into the repository somebody is working in.
        # Found the hard way: two fixture programs landed in `src/channels/` beside real source.
        (paths.home() / "app" / "src").mkdir(parents=True, exist_ok=True)
        self.shipped = paths.code() / adapters.SHIPPED_IN
        self.given = paths.data() / adapters.GIVEN_IN
        for at in (self.shipped, self.given):
            at.mkdir(parents=True, exist_ok=True)
        self.assertTrue(support.CHECKOUT not in self.shipped.parents,
                        "a case was about to write an adapter into the checkout")

    def an_adapter(self, kind="discord", body=A_WORKING_ADAPTER, among=None, runnable=True):
        at = (among if among is not None else self.shipped) / kind
        at.write_text(body, encoding="utf-8")
        at.chmod(0o755 if runnable else 0o644)
        return at


class FindingTheProgram(Adapters):

    def test_a_bare_name_finds_the_one_that_ships(self):
        made = self.an_adapter("discord")
        self.assertEqual(made, adapters.where("discord"))

    def test_a_bare_name_finds_one_this_install_was_given(self):
        made = self.an_adapter("my-thing", among=self.given)
        self.assertEqual(made, adapters.where("my-thing"))

    def test_a_release_adapter_is_the_one_a_bare_name_gets(self):
        # An install may add adapters and may not quietly shadow one that ships: somebody typing
        # `discord` gets the release's own, whatever else is standing under that name.
        shipped = self.an_adapter("discord")
        self.an_adapter("discord", among=self.given)
        self.assertEqual(shipped, adapters.where("discord"))

    def test_anything_with_a_separator_is_used_as_a_path(self):
        # So an adapter being written right now needs nothing installed anywhere.
        elsewhere = self.home / "work"
        elsewhere.mkdir()
        made = self.an_adapter("thing", among=elsewhere)
        self.assertEqual(made, adapters.where(str(made)))

    def test_a_name_nothing_stands_under_says_where_it_looked(self):
        with self.assertRaises(adapters.NotRunnable) as refused:
            adapters.where("nowhere")
        self.assertIn(str(self.shipped), str(refused.exception))
        self.assertIn(str(self.given), str(refused.exception))

    def test_a_file_that_is_not_executable_is_not_a_program(self):
        # Told apart from missing, because somebody sent there to install it would be looking in
        # entirely the wrong place.
        self.an_adapter("discord", runnable=False)
        with self.assertRaises(adapters.NotRunnable):
            adapters.where("discord")

    def test_every_adapter_is_found_by_looking_rather_than_listed(self):
        self.an_adapter("discord")
        self.an_adapter("slack")
        self.an_adapter("my-thing", among=self.given)
        self.assertEqual(["discord", "my-thing", "slack"], adapters.known())

    def test_an_install_with_nowhere_for_them_yet_says_none_rather_than_failing(self):
        for at in (self.shipped, self.given):
            at.rmdir()
        self.assertEqual([], adapters.known())


class AskingWhatItCanDo(Adapters):

    def test_what_it_says_comes_back_as_it_said_it(self):
        self.an_adapter("discord")
        self.assertEqual({"stream": True, "max_text": 2000}, adapters.capabilities("discord"))

    def test_an_adapter_that_would_not_say_can_do_nothing_which_is_a_whole_answer(self):
        # Never guessed from a name, and never an exception: an adapter that does not recognise the
        # flag has answered, and the answer is the least capable one.
        self.an_adapter("discord", AN_ADAPTER_THAT_DIES)
        self.assertEqual({}, adapters.capabilities("discord"))

    def test_it_is_asked_with_no_credential_anywhere_near_it(self):
        # Offline, no account, the same answer every time — so nothing about a particular install
        # can change it.
        self.an_adapter("discord", AN_ADAPTER_THAT_TELLS_ON_ITS_ENVIRONMENT)
        self.assertEqual({}, adapters.capabilities("discord"))


class AskingWhetherItCanConnect(Adapters):

    def test_what_it_reached_comes_back_whole(self):
        self.an_adapter("discord")
        said = adapters.checked("discord", (), {})
        self.assertTrue(said.ok)
        self.assertEqual("a bot, reaching somebody", said.describes)
        self.assertEqual("1180", said.notify_place)
        self.assertEqual({"guild": "9930"}, json.loads(said.settings))
        self.assertEqual(["A_TOKEN"], said.secret_names)
        self.assertEqual("https://example.invalid/invite", said.invite)

    def test_an_adapter_that_connected_and_was_told_no_has_answered(self):
        # `ok: false` and exit 0 is the exact shape of a refusal, and the sentence is the whole of
        # what somebody at a terminal can act on.
        self.an_adapter("discord", AN_ADAPTER_THAT_REFUSES)
        said = adapters.checked("discord", (), {})
        self.assertFalse(said.ok)
        self.assertEqual("that token is not a bot", said.why)

    def test_an_adapter_that_died_without_answering_is_a_different_thing(self):
        self.an_adapter("discord", AN_ADAPTER_THAT_DIES)
        said = adapters.checked("discord", (), {})
        self.assertFalse(said.ok)
        self.assertIn("did not say", said.why)
        self.assertIn("No module named discord", said.why,
                      "what it managed to say was thrown away")

    def test_an_answer_after_a_warning_is_still_an_answer(self):
        self.an_adapter("discord", A_CHATTY_ADAPTER)
        said = adapters.checked("discord", (), {})
        self.assertTrue(said.ok)
        self.assertEqual("still fine", said.describes)

    def test_one_credential_named_alone_is_a_list_of_one(self):
        # Slack needs two, so the list is the real shape; an adapter needing one and saying so
        # plainly is not making a mistake worth refusing.
        self.an_adapter("discord", A_CHATTY_ADAPTER)
        self.assertEqual(["ONE_TOKEN"], adapters.checked("discord", (), {}).secret_names)

    def test_what_the_owner_typed_reaches_the_adapter_exactly(self):
        self.an_adapter("discord", """#!/bin/sh
shift
printf '{"ok": true, "describes": "%s", "settings": {}}\\n' "$*"
exit 0
""")
        said = adapters.checked("discord", ("--guild", "9930"), {})
        self.assertEqual("--guild 9930", said.describes)

    def test_the_credential_it_was_given_reaches_it(self):
        self.an_adapter("discord", AN_ADAPTER_THAT_TELLS_ON_ITS_ENVIRONMENT)
        said = adapters.checked("discord", (), {"SEEN": "a token"})
        self.assertEqual("a token", said.describes)

    def test_nothing_else_of_this_processs_environment_reaches_it(self):
        # An adapter that could read everything here is one that comes to depend on something
        # nobody meant to hand it — and the likeliest such thing is another agent's credential.
        self.addCleanup(os.environ.pop, "SEEN", None)
        os.environ["SEEN"] = "somebody else's token"
        self.an_adapter("discord", AN_ADAPTER_THAT_TELLS_ON_ITS_ENVIRONMENT)
        self.assertEqual("nothing", adapters.checked("discord", (), {}).describes)


if __name__ == "__main__":
    unittest.main()
