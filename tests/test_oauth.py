"""Provider-neutral OAuth state, concurrency, declarations, callbacks and token confinement.

Every case here is offline. Consent, the token endpoint and the identity endpoint are all seams
that are passed in, and the one case that opens a socket opens it to `127.0.0.1` and to itself.

Run directly: `python3 tests/test_oauth.py`
"""

import contextlib
import dataclasses
import http.client
import io
import json
import os
import socket
import struct
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from argparse import Namespace
from pathlib import Path
from unittest import mock

import support
from rundesk.commands import login
from rundesk.commands import oauth as bridge
from rundesk.core import oauth, secrets
from rundesk.skills import oauth as declarations


def provider(fingerprint="descriptor-one"):
    return oauth.Provider("example", "Example", "https://id.example/authorize",
                          "https://id.example/token", "https://id.example/me",
                          ("identity",), "subject", "mail", "verified", {"prompt": "consent"},
                          True, {"reports": "reports.read", "sales": "sales.read"}, fingerprint)


def authorization(subject="immutable-a", email="a@example.test", refresh="refresh-a",
                  scopes=("identity",), before=None):
    """A consent seam that can also do something *while consent is open*.

    `before` is what makes the concurrency cases real rather than simulated: it runs at exactly the
    moment a person is in a browser, which is the window every compare-and-set here exists for.
    """
    def authorize(request):
        if before is not None:
            before(request)
        return oauth.Tokens("exchange-token", refresh, 3600, tuple(scopes)), \
            oauth.Identity(subject, email)
    return authorize


def refreshing(**answer):
    """A token endpoint that hands back exactly what a case says it does."""
    said = {"access_token": "short", "expires_in": 60}
    said.update(answer)
    return lambda *_args: said


#: The client an owner places before ever running `login`, under the names the grammar derives
#: from the provider ID. `example` gives `EXAMPLE_OAUTH_CLIENT_ID`; no case spells one out.
ID_NAME, SECRET_NAME = "EXAMPLE_OAUTH_CLIENT_ID", "EXAMPLE_OAUTH_CLIENT_SECRET"


def seeded(client_id="client-id", client_secret="client-secret", profile=""):
    """Place an app client the way an owner does: `rundesk env set`, before any login."""
    names = oauth.client_names(provider(), profile)
    if client_id is not None:
        secrets.stated(names[0], client_id)
    if client_secret is not None:
        secrets.stated(names[1], client_secret)


def stored(profile="default"):
    """The sealed grant document, as the store really holds it."""
    return json.loads(secrets.value(oauth.STATE))["providers"]["example"]["applications"][profile]


def rewrite(changing):
    """Change the sealed document out from under whatever is running, as another terminal would."""
    def changed(before):
        held = json.loads(before[oauth.STATE])
        changing(held["providers"]["example"]["applications"]["default"])
        return {oauth.STATE: json.dumps(held, sort_keys=True, separators=(",", ":"))}
    secrets.changed((oauth.STATE,), changed)


class State(support.Isolated):
    def setUp(self):
        super().setUp()
        seeded()

    def test_multiple_accounts_survive_and_email_is_unambiguous(self):
        oauth.authorize(provider(), authorizing=authorization())
        oauth.authorize(provider(), authorizing=authorization("immutable-b", "b@example.test",
                                                              "refresh-b"))
        self.assertEqual(["a@example.test", "b@example.test"], oauth.emails(provider()))
        self.assertEqual(2, oauth.account_count(provider()))
        with self.assertRaisesRegex(oauth.Refused, "choose --email"):
            oauth.access(provider(), "reports", None)

    def test_an_account_is_filed_under_its_subject_so_a_renamed_address_is_not_a_second_one(self):
        oauth.authorize(provider(), authorizing=authorization())
        oauth.authorize(provider(), authorizing=authorization(email="renamed@example.test"))
        self.assertEqual(["renamed@example.test"], oauth.emails(provider()))

    def test_scope_extension_persists_only_after_verified_same_identity(self):
        oauth.authorize(provider(), authorizing=authorization())
        answer = oauth.access(provider(), "reports", "a@example.test",
                              authorizing=authorization(scopes=("identity", "reports.read")),
                              posting=refreshing())
        self.assertEqual("short", answer.token)
        self.assertIn("reports.read", stored()["accounts"]["immutable-a"]["scopes"])

    def test_a_different_account_coming_back_from_consent_changes_nothing(self):
        oauth.authorize(provider(), authorizing=authorization())
        before = secrets.value(oauth.STATE)
        with self.assertRaisesRegex(oauth.Refused, "different account"):
            oauth.access(provider(), "reports", "a@example.test",
                         authorizing=authorization("immutable-b", "b@example.test",
                                                   scopes=("identity", "reports.read")),
                         posting=refreshing())
        self.assertEqual(before, secrets.value(oauth.STATE))

    def test_concurrent_extensions_same_account_refuse_stale_loser(self):
        oauth.authorize(provider(), authorizing=authorization())
        barrier, outcomes = threading.Barrier(2), []

        def extend(capability, scope):
            def consenting(_request):
                barrier.wait()
                return oauth.Tokens("exchange", "refresh-" + capability, 60,
                                    ("identity", scope)), oauth.Identity(
                                        "immutable-a", "a@example.test")
            try:
                oauth.access(provider(), capability, "a@example.test", authorizing=consenting,
                             posting=refreshing())
                outcomes.append("ok")
            except oauth.Refused:
                outcomes.append("conflict")

        threads = [threading.Thread(target=extend, args=("reports", "reports.read")),
                   threading.Thread(target=extend, args=("sales", "sales.read"))]
        for one in threads:
            one.start()
        for one in threads:
            one.join()
        self.assertCountEqual(["ok", "conflict"], outcomes)

    def test_a_client_replaced_while_consent_was_open_refuses_the_grant(self):
        """The fingerprint is *enforced on the write*, not only recorded on it."""
        def rotate(_request):
            secrets.stated(ID_NAME, "somebody-elses-id")

        with self.assertRaisesRegex(oauth.Refused, "replaced while authorization was open"):
            oauth.authorize(provider(), authorizing=authorization(before=rotate))
        self.assertIsNone(secrets.value(oauth.STATE))

    def test_a_declaration_changed_while_consent_was_open_refuses_the_grant(self):
        oauth.authorize(provider(), authorizing=authorization())

        def drift(_request):
            rewrite(lambda app: app.update({"descriptor_fingerprint": "descriptor-two"}))

        with self.assertRaisesRegex(oauth.Refused, "declaration changed while"):
            oauth.authorize(provider(), authorizing=authorization("immutable-b", "b@example.test",
                                                                  before=drift))

    def test_a_grant_left_by_a_previous_client_is_refused_rather_than_used(self):
        oauth.authorize(provider(), authorizing=authorization())
        secrets.stated(ID_NAME, "rotated-elsewhere")
        with self.assertRaisesRegex(oauth.Refused, "different app client"):
            oauth.access(provider(), "reports", "a@example.test", posting=refreshing())

    def test_a_rotated_refresh_token_is_kept(self):
        oauth.authorize(provider(), authorizing=authorization(scopes=("identity", "reports.read")))
        oauth.access(provider(), "reports", "a@example.test",
                     posting=refreshing(refresh_token="rotated-once"))
        self.assertEqual("rotated-once",
                         stored()["accounts"]["immutable-a"]["refresh_token"])

    def test_a_rotation_that_lost_a_race_still_releases_the_token_it_earned(self):
        oauth.authorize(provider(), authorizing=authorization(scopes=("identity", "reports.read")))

        def answering(*_args):
            rewrite(lambda app: app["accounts"]["immutable-a"].update(
                {"refresh_token": "somebody-elses-newer"}))
            return {"access_token": "short", "expires_in": 60, "refresh_token": "rotated-late"}

        answer = oauth.access(provider(), "reports", "a@example.test", posting=answering)
        self.assertEqual("short", answer.token)
        self.assertEqual("somebody-elses-newer",
                         stored()["accounts"]["immutable-a"]["refresh_token"])

    def test_a_revoked_grant_says_so_and_names_the_command_that_fixes_it(self):
        oauth.authorize(provider(), authorizing=authorization(scopes=("identity", "reports.read")))
        with self.assertRaises(oauth.Revoked) as caught:
            oauth.access(provider(), "reports", "a@example.test",
                         posting=lambda *_: {"error": "invalid_grant"})
        self.assertIn("rundesk login example", str(caught.exception))

    def test_another_provider_error_is_refused_without_repeating_what_it_said(self):
        oauth.authorize(provider(), authorizing=authorization(scopes=("identity", "reports.read")))
        for said, expected in (({"error": "invalid_client",
                                 "error_description": "must-not-echo"}, "invalid_client"),
                               ({"error": "bad[31mcode"}, "an unrecognised error")):
            with self.subTest(said=said):
                with self.assertRaises(oauth.Refused) as caught:
                    oauth.access(provider(), "reports", "a@example.test",
                                 posting=lambda *_a, said=said: said)
                self.assertNotIsInstance(caught.exception, oauth.Revoked)
                self.assertIn(expected, str(caught.exception))
                self.assertNotIn("must-not-echo", str(caught.exception))

    def test_a_lifetime_may_be_an_integral_string_and_may_never_be_a_boolean(self):
        oauth.authorize(provider(), authorizing=authorization(scopes=("identity", "reports.read")))
        answer = oauth.access(provider(), "reports", "a@example.test",
                              posting=refreshing(expires_in="3600"))
        self.assertGreater(answer.expires_at, int(time.time()) + 3000)
        for wrong in (True, False, "later", 0, -1, 1.5, None):
            with self.subTest(wrong=wrong), \
                    self.assertRaisesRegex(oauth.Refused, "usable access token"):
                oauth.access(provider(), "reports", "a@example.test",
                             posting=refreshing(expires_in=wrong))

    def test_an_unknown_capability_is_refused_before_anything_is_read(self):
        with self.assertRaisesRegex(oauth.Refused, "no OAuth capability"):
            oauth.access(provider(), "invented", None)

    def test_no_account_and_no_such_address_are_told_apart(self):
        with self.assertRaisesRegex(oauth.Refused, "no Example account is connected"):
            oauth.access(provider(), "reports", None)
        oauth.authorize(provider(), authorizing=authorization())
        with self.assertRaisesRegex(oauth.Refused, "no connected Example account uses"):
            oauth.access(provider(), "reports", "nobody@example.test")

    def test_descriptor_drift_is_refused(self):
        oauth.authorize(provider(), authorizing=authorization())
        with self.assertRaisesRegex(oauth.Refused, "declaration for Example changed"):
            oauth.emails(provider("descriptor-two"))

    def test_a_display_name_is_not_part_of_what_a_grant_is_pinned_to(self):
        """Fingerprints come from `skills.oauth`, and it takes them over behaviour only."""
        oauth.authorize(provider(), authorizing=authorization())
        renamed = Declaration().value()
        renamed["display_name"] = "Example, Inc."
        with tempfile.TemporaryDirectory() as raw:
            at = Path(raw)
            at.joinpath(declarations.DECLARED).write_text(json.dumps(renamed), encoding="utf-8")
            first = declarations.read(at).fingerprint
            renamed["capabilities"] = {"reports": "everything.read"}
            at.joinpath(declarations.DECLARED).write_text(json.dumps(renamed), encoding="utf-8")
            self.assertNotEqual(first, declarations.read(at).fingerprint)
        plain = Declaration().value()
        with tempfile.TemporaryDirectory() as raw:
            at = Path(raw)
            at.joinpath(declarations.DECLARED).write_text(json.dumps(plain), encoding="utf-8")
            self.assertEqual(first, declarations.read(at).fingerprint)

    def test_failed_client_replacement_preserves_state_byte_for_byte(self):
        oauth.authorize(provider(), authorizing=authorization())
        before = secrets.value(oauth.STATE)
        with self.assertRaisesRegex(oauth.Refused, "complete reusable"):
            oauth.replace_client(provider(), "", "new-id", "new-secret",
                                 authorization(refresh=None))
        self.assertEqual(before, secrets.value(oauth.STATE))

    def test_successful_client_replacement_discards_only_that_profile_grants(self):
        oauth.authorize(provider(), authorizing=authorization())
        seeded("work-id", "work-secret", "work")
        oauth.authorize(provider(), "work", authorization("work-sub", "work@example.test",
                                                          "work-refresh"))
        oauth.replace_client(provider(), "", "new-id", "new-secret",
                             authorization("new-sub", "new@example.test", "new-refresh"))
        self.assertEqual(["new@example.test"], oauth.emails(provider()))
        self.assertEqual(["work@example.test"], oauth.emails(provider(), "work"))

    def test_configure_will_not_quietly_replace_a_client_an_owner_already_placed(self):
        with self.assertRaisesRegex(oauth.Refused, "already set"):
            oauth.configure(provider(), "", "another-id", None)
        self.assertEqual("client-id", secrets.value(ID_NAME))

    def test_an_empty_client_value_is_refused(self):
        for wrong in ("", "   "):
            with self.subTest(wrong=wrong), self.assertRaises(oauth.Refused):
                oauth.configure(provider(), "spare", wrong, "secret")

    def test_an_unreadable_stored_document_is_a_refusal_rather_than_a_traceback(self):
        """Every one of these raises something that is *not* a `Refused` if a guard is removed."""
        for broken in ('{"version":2,"providers":{}}', "not json at all", '{"version":1}',
                       '["not", "an", "object"]', '{"version":1,"providers":5}',
                       '{"version":1,"providers":{"example":"a string"}}',
                       '{"version":1,"providers":{"example":{"applications":'
                       '{"default":{"descriptor_fingerprint":"descriptor-one",'
                       '"accounts":"nope"}}}}}',
                       '{"version":1,"providers":{"example":{"applications":'
                       '{"default":{"descriptor_fingerprint":"descriptor-one",'
                       '"accounts":{"immutable-a":{"email":7}}}}}}}'):
            with self.subTest(broken=broken):
                secrets.changed((oauth.STATE,),
                                lambda _before, broken=broken: {oauth.STATE: broken})
                with self.assertRaises(oauth.Refused):
                    oauth.emails(provider())

    def test_a_profile_name_that_could_collide_with_the_separator_is_refused(self):
        self.assertEqual("default", oauth.profile_key(""))
        self.assertEqual("WORK", oauth.profile_key("work"))
        for wrong in ("a b", "1st", "a__b", "-", ""):
            if not wrong:
                continue
            with self.subTest(wrong=wrong), self.assertRaisesRegex(oauth.Refused, "not a valid"):
                oauth.profile_key(wrong)


class AppClient(support.Isolated):
    """The client is the owner's value, placed before login and used without asking again."""

    def test_the_names_come_from_the_provider_id_and_the_default_profile_is_unsuffixed(self):
        self.assertEqual((ID_NAME, SECRET_NAME), oauth.client_names(provider()))
        self.assertEqual((ID_NAME, SECRET_NAME), oauth.client_names(provider(), ""))
        self.assertEqual((f"{ID_NAME}__WORK", f"{SECRET_NAME}__WORK"),
                         oauth.client_names(provider(), "work"))
        hyphenated = dataclasses.replace(provider(), provider="some-provider")
        self.assertEqual(("SOME_PROVIDER_OAUTH_CLIENT_ID", "SOME_PROVIDER_OAUTH_CLIENT_SECRET"),
                         oauth.client_names(hyphenated))

    def test_a_preseeded_client_is_used_without_asking_for_anything(self):
        seeded()
        self.assertTrue(oauth.configured(provider()))
        code, out, err = self.logged_in([], asking=lambda prompt: self.fail(f"asked {prompt!r}"))
        self.assertEqual(0, code, err)
        self.assertIn("Connected a@example.test", out)

    def test_a_preseeded_profile_client_is_found_under_its_own_suffix(self):
        seeded("work-id", "work-secret", "work")
        self.assertFalse(oauth.configured(provider()))
        self.assertTrue(oauth.configured(provider(), "work"))
        code, out, err = self.logged_in(["--profile", "work"],
                                        asking=lambda prompt: self.fail(f"asked {prompt!r}"))
        self.assertEqual(0, code, err)
        self.assertIn("Connected a@example.test", out)
        self.assertEqual(["a@example.test"], oauth.emails(provider(), "work"))
        # The default profile is untouched: a profile is a second app, not a second account.
        with self.assertRaisesRegex(oauth.Refused, "no OAuth app client is configured"):
            oauth.emails(provider())

    def test_only_the_missing_half_is_asked_for(self):
        secrets.stated(ID_NAME, "already-placed")
        asked = []

        def ask(prompt):
            asked.append(prompt)
            return "typed-secret"

        code, _, err = self.logged_in([], asking=ask)
        self.assertEqual(0, code, err)
        self.assertEqual(1, len(asked))
        self.assertIn(SECRET_NAME, asked[0])
        self.assertEqual("already-placed", secrets.value(ID_NAME))
        self.assertEqual("typed-secret", secrets.value(SECRET_NAME))

    def test_nothing_placed_names_both_values_and_keeps_what_was_typed(self):
        code, _, err = self.logged_in([], asking=lambda _prompt: "typed")
        self.assertEqual(0, code, err)
        self.assertEqual("typed", secrets.value(ID_NAME))
        self.assertEqual("typed", secrets.value(SECRET_NAME))

    def test_a_client_this_install_can_no_longer_open_is_not_reported_as_absent(self):
        """Unreadable and never-placed are different situations with different answers.

        Told "set this value", somebody types a new client over one they may still want back — and
        on this store an unreadable value means the key is gone or the file was edited, which is
        worth knowing rather than papering over.
        """
        seeded()
        held = json.loads(secrets.where().read_text(encoding="utf-8"))
        held[ID_NAME] = held[ID_NAME][:-8] + "AAAAAAAA"
        secrets.where().write_text(json.dumps(held), encoding="utf-8")
        with self.assertRaises(oauth.Refused) as caught:
            oauth.emails(provider())
        self.assertIn("cannot be read", str(caught.exception))
        self.assertNotIn("rundesk env set", str(caught.exception))

    def test_an_unconfigured_client_is_refused_by_name_rather_than_guessed_at(self):
        with self.assertRaises(oauth.Refused) as caught:
            oauth.emails(provider())
        self.assertIn(f"rundesk env set {ID_NAME}", str(caught.exception))
        self.assertIn(f"rundesk env set {SECRET_NAME}", str(caught.exception))

    def test_a_secret_never_reaches_output_or_a_process_argument(self):
        seeded(client_secret="unmistakable-secret-value")
        code, out, err = self.logged_in([], asking=lambda _prompt: "unmistakable-secret-value")
        self.assertEqual(0, code, err)
        for said in (out, err):
            self.assertNotIn("unmistakable-secret-value", said)
        # Nothing in this command takes a value: no flag on the parser accepts one, so there is no
        # spelling of `rundesk login` that puts a secret in `argv` for `ps` to show.
        code, _, refused = support.run(["login", "example", "--client-secret", "x"])
        self.assertNotEqual(0, code)
        self.assertIn("unrecognized arguments", refused)

    def logged_in(self, extra, asking):
        out, err = io.StringIO(), io.StringIO()
        args = Namespace(provider="example", profile="", replace_client=False, confirm=False)
        if extra[:1] == ["--profile"]:
            args.profile = extra[1]
        with mock.patch.object(declarations, "named", return_value=provider()), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = login.cmd_login(args, authorizing=authorization(), asking=asking)
        return code, out.getvalue(), err.getvalue()


class ClientNames(unittest.TestCase):
    """The grammar is narrow: it must catch a client and miss an ordinary value beside it."""

    def test_what_is_an_oauth_client_name(self):
        for name in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET",
                     "GOOGLE_OAUTH_CLIENT_ID__WORK", "GOOGLE_OAUTH_CLIENT_SECRET__WORK",
                     "SOME_PROVIDER_OAUTH_CLIENT_ID", "A_OAUTH_CLIENT_SECRET"):
            with self.subTest(name=name):
                self.assertTrue(secrets.an_oauth_client(name))
                self.assertTrue(secrets.withheld(name))

    def test_what_is_an_ordinary_owner_value_beside_one(self):
        for name in ("OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT", "GOOGLE_OAUTH_CLIENT_IDENTITY",
                     "GOOGLE_OAUTH_CLIENT_SECRET_EXTRA", "GOOGLE_ANALYTICS_CLIENT_ID",
                     "GOOGLE_ANALYTICS_REFRESH_TOKEN", "CLIENT_ID", "OAUTH_TOKEN",
                     "GOOGLE_OAUTH_CLIENT_ID__A__B", "GOOGLE_OAUTH_CLIENT_ID__",
                     "MY_OAUTH_CLIENT_ID_SUFFIX", "A_TOKEN"):
            with self.subTest(name=name):
                self.assertFalse(secrets.an_oauth_client(name))
                self.assertFalse(secrets.withheld(name))


class Reservation(support.Isolated):
    """`RUNDESK_OAUTH_STATE` is rundesk's, and four ordinary verbs must not reach it."""

    def setUp(self):
        super().setUp()
        seeded()
        oauth.authorize(provider(), authorizing=authorization())
        secrets.stated("AN_ORDINARY_TOKEN", "an ordinary value")

    def test_it_is_never_handed_to_a_provider_turn(self):
        from rundesk.providers import environment
        given = environment.owners_own()
        self.assertIn("AN_ORDINARY_TOKEN", given)
        self.assertNotIn(oauth.STATE, given)
        self.assertNotIn("refresh-a", "".join(given.values()))

    def test_an_app_client_is_the_owners_to_see_and_set_but_never_a_turns_to_read(self):
        """Two different rules for two different things, and the difference is deliberate."""
        from rundesk.providers import environment
        secrets.stated(ID_NAME, "a-client-id")
        secrets.stated(SECRET_NAME, "a-client-secret")
        secrets.stated("GOOGLE_ANALYTICS_CLIENT_ID", "an ordinary near miss")
        given = environment.owners_own()
        self.assertNotIn(ID_NAME, given)
        self.assertNotIn(SECRET_NAME, given)
        self.assertIn("GOOGLE_ANALYTICS_CLIENT_ID", given)
        self.assertNotIn("a-client-secret", "".join(given.values()))
        code, out, _ = self.run_command(["env", "list"])
        self.assertEqual(0, code)
        # Visible to the owner at their own terminal, as a hint, because they placed it.
        self.assertIn(ID_NAME, out)
        self.assertNotIn("a-client-id", out)
        code, out, _ = self.run_command(["env", "check", SECRET_NAME])
        self.assertEqual(0, code)
        self.assertNotIn("a-client-secret", out)

    def test_env_list_does_not_show_it(self):
        code, out, _ = self.run_command(["env", "list"])
        self.assertEqual(0, code)
        self.assertIn("AN_ORDINARY_TOKEN", out)
        self.assertNotIn(oauth.STATE, out)

    def test_env_set_unset_and_check_all_refuse_it_by_name(self):
        for verb in ("check", "set", "unset"):
            with self.subTest(verb=verb):
                code, _, err = self.run_command(["env", verb, oauth.STATE])
                self.assertNotEqual(0, code)
                self.assertIn("kept by rundesk itself", err)

    def test_the_grants_survive_an_attempt_to_empty_them(self):
        self.run_command(["env", "unset", oauth.STATE])
        self.assertEqual(["a@example.test"], oauth.emails(provider()))

    def test_the_store_itself_refuses_a_whole_value_replacement(self):
        for act in (lambda: secrets.stated(oauth.STATE, "anything"),
                    lambda: secrets.cleared(oauth.STATE)):
            with self.subTest(act=act), self.assertRaisesRegex(secrets.Refused, "kept by rundesk"):
                act()

    def run_command(self, argv):
        with mock.patch.object(login.env.sys, "stdin", io.StringIO("typed\n")):
            return support.run(argv)


class Prompting(support.Isolated):
    """Nothing typed is a refusal, and a refusal is not a traceback."""

    def test_a_closed_or_ended_stdin_refuses_without_storing_a_client(self):
        args = Namespace(provider="example", profile="", replace_client=False, confirm=False)
        for nothing in (None, "", "   "):
            said = io.StringIO()
            with self.subTest(nothing=nothing), \
                    mock.patch.object(declarations, "named", return_value=provider()), \
                    contextlib.redirect_stderr(said):
                code = login.cmd_login(args, asking=lambda _prompt, given=nothing: given)
            self.assertNotEqual(0, code)
            # The refusal is about what was not typed, not a downstream complaint about an empty
            # value: those read as different problems to whoever has to fix one.
            self.assertIn("no OAuth client ID was given", said.getvalue())
            self.assertIsNone(secrets.value(oauth.STATE))
            self.assertIsNone(secrets.value(ID_NAME))

    def test_a_value_longer_than_a_value_could_be_comes_back_as_nothing(self):
        from rundesk.commands import env
        with mock.patch.object(env.sys, "stdin", io.StringIO("x" * (env.MOST + 5) + "\n")):
            self.assertIsNone(env.typed("say: "))
        with mock.patch.object(env.sys, "stdin", io.StringIO("x" * 10 + "\n")):
            self.assertEqual("x" * 10, env.typed("say: "))

    def test_no_stdin_at_all_is_nothing_rather_than_an_attribute_error(self):
        from rundesk.commands import env
        with mock.patch.object(env.sys, "stdin", None):
            self.assertIsNone(env.typed("say: "))


class Replacement(support.Isolated):
    def setUp(self):
        super().setUp()
        seeded()
        oauth.authorize(provider(), authorizing=authorization())

    def test_two_confirmed_replacements_at_once_leave_exactly_one_client_and_its_grant(self):
        """Last-writer-wins here loses a whole client and its grant, and reports success twice."""
        barrier, outcomes = threading.Barrier(2), []

        def replace(mark):
            def consenting(_request):
                barrier.wait()
                return oauth.Tokens("exchange", f"refresh-{mark}", 60, ("identity",)), \
                    oauth.Identity(f"subject-{mark}", f"{mark}@example.test")
            try:
                oauth.replace_client(provider(), "", f"id-{mark}", f"secret-{mark}", consenting)
                outcomes.append(mark)
            except oauth.Refused:
                outcomes.append("conflict")

        threads = [threading.Thread(target=replace, args=(one,)) for one in ("first", "second")]
        for one in threads:
            one.start()
        for one in threads:
            one.join()
        self.assertEqual(1, outcomes.count("conflict"), outcomes)
        won = next(one for one in outcomes if one != "conflict")
        # The client that is stored and the grant that is stored are the *same* replacement's.
        self.assertEqual(f"id-{won}", secrets.value(ID_NAME))
        self.assertEqual(f"secret-{won}", secrets.value(SECRET_NAME))
        self.assertEqual([f"{won}@example.test"], oauth.emails(provider()))
        self.assertEqual(f"refresh-{won}",
                         stored()["accounts"][f"subject-{won}"]["refresh_token"])

    def test_a_client_changed_during_a_replacement_refuses_and_replaces_nothing(self):
        def interfere(_request):
            secrets.stated(ID_NAME, "somebody-elses-id")

        with self.assertRaisesRegex(oauth.Refused, "client changed while the replacement"):
            oauth.replace_client(provider(), "", "new-id", "new-secret",
                                 authorization("new-sub", "new@example.test", "new-refresh",
                                               before=interfere))
        self.assertEqual("somebody-elses-id", secrets.value(ID_NAME))
        self.assertEqual("client-secret", secrets.value(SECRET_NAME))
        self.assertEqual(["a@example.test"], oauth.emails(provider()))

    def test_a_secret_changed_during_a_replacement_refuses_and_replaces_nothing(self):
        def interfere(_request):
            secrets.stated(SECRET_NAME, "somebody-elses-secret")

        with self.assertRaisesRegex(oauth.Refused, "client changed while the replacement"):
            oauth.replace_client(provider(), "", "new-id", "new-secret",
                                 authorization("new-sub", "new@example.test", "new-refresh",
                                               before=interfere))
        self.assertEqual("client-id", secrets.value(ID_NAME))
        self.assertEqual(["a@example.test"], oauth.emails(provider()))

    def test_an_account_connected_during_a_replacement_is_not_silently_discarded(self):
        """Somebody connecting an account in another terminal must not have it thrown away."""
        def connect(_request):
            oauth.authorize(provider(), authorizing=authorization("immutable-b",
                                                                  "b@example.test", "refresh-b"))

        with self.assertRaisesRegex(oauth.Refused, "connected or changed under this app client"):
            oauth.replace_client(provider(), "", "new-id", "new-secret",
                                 authorization("new-sub", "new@example.test", "new-refresh",
                                               before=connect))
        self.assertEqual("client-id", secrets.value(ID_NAME))
        self.assertEqual(["a@example.test", "b@example.test"], oauth.emails(provider()))

    def test_replacements_of_two_profiles_do_not_conflict_with_one_another(self):
        """A profile is a separate app: two of them have nothing to be stale about."""
        seeded("work-id", "work-secret", "work")
        oauth.authorize(provider(), "work", authorization("work-sub", "work@example.test",
                                                          "work-refresh"))
        oauth.replace_client(provider(), "", "fresh-default", "fresh-default-secret",
                             authorization("new-a", "new-a@example.test", "new-refresh-a"))
        oauth.replace_client(provider(), "work", "fresh-work", "fresh-work-secret",
                             authorization("new-b", "new-b@example.test", "new-refresh-b"))
        self.assertEqual("fresh-default", secrets.value(ID_NAME))
        self.assertEqual("fresh-work", secrets.value(f"{ID_NAME}__WORK"))
        self.assertEqual(["new-a@example.test"], oauth.emails(provider()))
        self.assertEqual(["new-b@example.test"], oauth.emails(provider(), "work"))

    def test_unreadable_state_refuses_before_anybody_is_sent_to_a_browser(self):
        """Refusing after consent is still safe and still wastes a person's trip to a browser."""
        held = json.loads(secrets.where().read_text(encoding="utf-8"))
        held[oauth.STATE] = held[oauth.STATE][:-8] + "AAAAAAAA"
        secrets.where().write_text(json.dumps(held), encoding="utf-8")
        with self.assertRaisesRegex(oauth.Refused, "cannot be read"):
            oauth.replace_client(provider(), "", "new-id", "new-secret",
                                 lambda _request: self.fail("consent was opened anyway"))

    def test_the_preview_counts_the_grants_and_does_not_prompt_or_change_state(self):
        before = secrets.value(oauth.STATE)
        args = Namespace(provider="example", profile="", replace_client=True, confirm=False)
        shown = io.StringIO()
        with mock.patch.object(declarations, "named", return_value=provider()), \
                contextlib.redirect_stderr(shown):
            code = login.cmd_login(args, asking=lambda _prompt: self.fail("prompted"))
        self.assertNotEqual(0, code)
        self.assertIn("1 connected account grant(s)", shown.getvalue())
        self.assertIn("--confirm", shown.getvalue())
        self.assertEqual(before, secrets.value(oauth.STATE))

    def test_confirm_without_replace_client_is_refused(self):
        args = Namespace(provider="example", profile="", replace_client=False, confirm=True)
        shown = io.StringIO()
        with mock.patch.object(declarations, "named", return_value=provider()), \
                contextlib.redirect_stderr(shown):
            code = login.cmd_login(args, asking=lambda _prompt: self.fail("prompted"))
        self.assertNotEqual(0, code)
        self.assertIn("only used with --replace-client", shown.getvalue())

    def test_confirmed_replacement_prompts_signs_in_and_replaces_both_together(self):
        args = Namespace(provider="example", profile="", replace_client=True, confirm=True)
        with mock.patch.object(declarations, "named", return_value=provider()), \
                contextlib.redirect_stdout(io.StringIO()):
            code = login.cmd_login(args, authorizing=authorization("new-sub", "new@example.test",
                                                                   "new-refresh"),
                                   asking=lambda _prompt: "new-value")
        self.assertEqual(0, code)
        self.assertEqual("new-value", secrets.value(ID_NAME))
        self.assertEqual("new-value", secrets.value(SECRET_NAME))
        self.assertEqual(["new@example.test"], oauth.emails(provider()))


class ReplacingWithNothingThereYet(support.Isolated):
    """`--replace-client` on a profile that has no client, which is a legitimate starting point."""

    def test_it_places_the_client_and_its_first_grant_together(self):
        self.assertFalse(oauth.configured(provider()))
        self.assertEqual(0, oauth.account_count(provider()))
        email = oauth.replace_client(provider(), "", "first-id", "first-secret",
                                     authorization("first-sub", "first@example.test", "first-r"))
        self.assertEqual("first@example.test", email)
        self.assertEqual("first-id", secrets.value(ID_NAME))
        self.assertEqual(["first@example.test"], oauth.emails(provider()))

    def test_a_client_appearing_during_consent_refuses_rather_than_overwriting_it(self):
        """Absent is a state to be stale about too, and `env set` is how it stops being absent."""
        def interfere(_request):
            secrets.stated(ID_NAME, "placed-meanwhile")
            secrets.stated(SECRET_NAME, "placed-meanwhile-secret")

        with self.assertRaisesRegex(oauth.Refused, "client changed while the replacement"):
            oauth.replace_client(provider(), "", "first-id", "first-secret",
                                 authorization("first-sub", "first@example.test", "first-r",
                                               before=interfere))
        self.assertEqual("placed-meanwhile", secrets.value(ID_NAME))
        self.assertIsNone(secrets.value(oauth.STATE))


class Bridge(support.Isolated):
    """The private socket surface, driven the way an integration really drives it."""

    def setUp(self):
        super().setUp()
        seeded()
        oauth.authorize(provider(), authorizing=authorization(scopes=("identity",
                                                                      "reports.read")))

    def answered(self, args, **seams):
        theirs, ours = socket.socketpair()
        try:
            args.response_fd = ours.fileno()
            with mock.patch.object(bridge.declarations, "named", return_value=provider()), \
                    contextlib.redirect_stderr(io.StringIO()):
                code = bridge.cmd_oauth(args, **seams)
            return code, oauth.read_frame(theirs.fileno())
        finally:
            theirs.close()
            ours.close()

    def test_accounts_lists_addresses_and_nothing_else(self):
        code, frame = self.answered(Namespace(oauth_action="accounts", provider="example",
                                              profile=""))
        self.assertEqual(0, code)
        self.assertEqual({"version": 1, "ok": True, "accounts": ["a@example.test"]}, frame)

    def test_access_returns_a_short_lived_token_and_never_the_refresh_token(self):
        code, frame = self.answered(
            Namespace(oauth_action="access", provider="example", capability="reports",
                      email="a@example.test", profile=""), posting=refreshing())
        self.assertEqual(0, code)
        self.assertEqual("short", frame["access_token"])
        self.assertEqual("Bearer", frame["token_type"])
        self.assertNotIn("refresh-a", json.dumps(frame))

    def test_a_refusal_comes_back_as_a_frame_as_well_as_a_failing_exit(self):
        code, frame = self.answered(
            Namespace(oauth_action="access", provider="example", capability="invented",
                      email=None, profile=""))
        self.assertNotEqual(0, code)
        self.assertIs(False, frame["ok"])
        self.assertIn("no OAuth capability", frame["error"])


class Protocol(unittest.TestCase):
    def test_frame_uses_anonymous_socket_and_version(self):
        reader, writer = socket.socketpair()
        try:
            oauth.write_frame(writer.fileno(), {"ok": True})
            self.assertTrue(oauth.read_frame(reader.fileno())["ok"])
        finally:
            reader.close()
            writer.close()

    def test_regular_file_is_refused(self):
        with tempfile.TemporaryFile() as held, self.assertRaisesRegex(oauth.Refused, "socket"):
            oauth.write_frame(held.fileno(), {"ok": True})

    def test_stdio_is_refused_even_when_it_really_is_an_anonymous_socket(self):
        """The one arrangement where only the stdio rule can refuse: the socket *is* fd 1.

        A caller that answered on 1 or 2 would write a frame into whatever is reading this
        command's output, and one that answered on 0 would write into its own input. Checked with
        the descriptor genuinely replaced, because against an ordinary terminal or pipe the
        anonymous-socket rule refuses first and this rule is never reached.
        """
        reader, writer = socket.socketpair()
        for standard in (0, 1, 2):
            kept = os.dup(standard)
            try:
                os.dup2(writer.fileno(), standard)
                with self.assertRaisesRegex(oauth.Refused, "stdin, stdout, or stderr"):
                    oauth.write_frame(standard, {"ok": True})
            finally:
                os.dup2(kept, standard)
                os.close(kept)
        reader.close()
        writer.close()

    def test_a_negative_descriptor_is_refused(self):
        with self.assertRaises(oauth.Refused):
            oauth.write_frame(-1, {"ok": True})

    def test_a_named_socket_and_a_fifo_are_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            fifo = Path(raw) / "named"
            os.mkfifo(str(fifo))
            descriptor = os.open(str(fifo), os.O_RDWR | os.O_NONBLOCK)
            try:
                with self.assertRaisesRegex(oauth.Refused, "socket"):
                    oauth.write_frame(descriptor, {"ok": True})
            finally:
                os.close(descriptor)
        with tempfile.TemporaryDirectory() as raw:
            at = str(Path(raw) / "listening")
            listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listening.bind(at)
            try:
                with self.assertRaisesRegex(oauth.Refused, "anonymous"):
                    oauth.write_frame(listening.fileno(), {"ok": True})
            finally:
                listening.close()

    def test_an_unknown_version_a_truncated_frame_and_an_oversize_length_are_refused(self):
        for body, message in ((b'{"version":9}', "version"), (b"{", "ended early")):
            reader, writer = socket.socketpair()
            try:
                writer.sendall(struct.pack(">I", len(body) + (1 if body == b"{" else 0)) + body)
                writer.shutdown(socket.SHUT_WR)
                with self.assertRaisesRegex(oauth.Refused, message):
                    oauth.read_frame(reader.fileno())
            finally:
                reader.close()
                writer.close()
        reader, writer = socket.socketpair()
        try:
            writer.sendall(struct.pack(">I", oauth.MAX_FRAME + 1))
            with self.assertRaisesRegex(oauth.Refused, "too large"):
                oauth.read_frame(reader.fileno())
        finally:
            reader.close()
            writer.close()

    def test_an_answer_larger_than_a_frame_is_refused_before_it_is_sent(self):
        reader, writer = socket.socketpair()
        try:
            with self.assertRaisesRegex(oauth.Refused, "too large"):
                oauth.write_frame(writer.fileno(), {"value": "x" * (oauth.MAX_FRAME + 1)})
        finally:
            reader.close()
            writer.close()

    def test_a_peer_that_never_writes_does_not_hold_the_reader_for_ever(self):
        """The read has a deadline of its own; without one this case never returns."""
        reader, writer = socket.socketpair()
        try:
            began = time.monotonic()
            with self.assertRaisesRegex(oauth.Refused, "before its deadline"):
                oauth.read_frame(reader.fileno(), timeout=0.05)
            self.assertLess(time.monotonic() - began, 5)
        finally:
            reader.close()
            writer.close()

    def test_a_peer_that_stops_reading_does_not_hold_the_writer_for_ever(self):
        reader, writer = socket.socketpair()
        writer.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024)
        try:
            with self.assertRaisesRegex(oauth.Refused, "deadline"):
                oauth.write_frame(writer.fileno(), {"value": "x" * 65000}, timeout=.01)
        finally:
            reader.close()
            writer.close()

    def test_a_frame_that_arrives_a_byte_at_a_time_cannot_extend_the_deadline(self):
        reader, writer = socket.socketpair()

        def dribble():
            body = b'{"version":1,"ok":true}'
            for one in struct.pack(">I", len(body)) + body:
                try:
                    writer.send(bytes([one]))
                except OSError:
                    return
                time.sleep(0.02)

        thread = threading.Thread(target=dribble)
        thread.start()
        try:
            with self.assertRaisesRegex(oauth.Refused, "before its deadline"):
                oauth.read_frame(reader.fileno(), timeout=0.05)
        finally:
            reader.close()
            thread.join()
            writer.close()


class Declaration(unittest.TestCase):
    def value(self):
        return {"schema": 1, "provider": "example", "display_name": "Example",
                "authorization_endpoint": "https://id.example/authorize",
                "token_endpoint": "https://id.example/token",
                "identity_endpoint": "https://id.example/me", "base_scopes": ["identity"],
                "identity": {"subject": "subject", "email": "mail",
                             "email_verified": "verified"},
                "authorization_parameters": {"prompt": "consent"}, "client_secret": True,
                "capabilities": {"reports": "reports.read", "sales": "sales.read"}}

    def written(self, at, value):
        Path(at).joinpath(declarations.DECLARED).write_text(json.dumps(value), encoding="utf-8")
        return Path(at)

    def refuses(self, **mutation):
        value = self.value()
        value.update(mutation)
        with tempfile.TemporaryDirectory() as raw, self.assertRaises(declarations.Refused):
            declarations.read(self.written(raw, value))

    def test_strict_declarative_schema(self):
        with tempfile.TemporaryDirectory() as raw:
            held = declarations.read(self.written(raw, self.value()))
            self.assertEqual("example", held.provider)
            self.assertEqual(("identity",), held.base_scopes)
            self.assertEqual({"prompt": "consent"}, dict(held.authorization_parameters))

    def test_an_endpoint_may_not_carry_credentials_a_query_or_a_fragment(self):
        for wrong in ("http://id.example/authorize", "https://user:pw@id.example/authorize",
                      "https://id.example/authorize?scope=injected",
                      "https://id.example/authorize#part", "https:///authorize", "not a url"):
            with self.subTest(wrong=wrong):
                self.refuses(authorization_endpoint=wrong)

    def test_a_declaration_may_not_override_oauth_mechanics(self):
        for reserved in sorted(oauth.RESERVED_AUTH):
            with self.subTest(reserved=reserved):
                self.refuses(authorization_parameters={reserved: "injected"})

    def test_missing_unknown_wrong_typed_empty_and_duplicate_values_are_refused(self):
        missing = self.value()
        missing.pop("identity")
        with tempfile.TemporaryDirectory() as raw, self.assertRaises(declarations.Refused):
            declarations.read(self.written(raw, missing))
        self.refuses(surprise=True)
        self.refuses(schema=2)
        self.refuses(client_secret="yes")
        self.refuses(capabilities={})
        self.refuses(capabilities={"Reports": "reports.read"})
        self.refuses(base_scopes=["identity", "identity"])
        self.refuses(base_scopes=[])
        self.refuses(base_scopes="identity")
        self.refuses(provider="Example")
        self.refuses(display_name="")
        self.refuses(identity={"subject": "s", "email": "e"})
        self.refuses(authorization_parameters={"prompt": 1})

    def test_every_declared_string_and_collection_is_bounded(self):
        self.refuses(display_name="x" * (declarations.MOST_TEXT + 1))
        self.refuses(base_scopes=[f"scope-{one}" for one in range(declarations.MOST_SCOPES + 1)])
        self.refuses(base_scopes=["x" * (declarations.MOST_TEXT + 1)])
        self.refuses(authorization_parameters={f"p{one}": "v"
                                               for one in range(declarations.MOST_PARAMETERS + 1)})
        self.refuses(capabilities={f"c-{one}": "scope"
                                   for one in range(declarations.MOST_CAPABILITIES + 1)})

    def test_a_declaration_file_larger_than_the_bound_is_refused_unread(self):
        value = self.value()
        value["display_name"] = "Example"
        with tempfile.TemporaryDirectory() as raw:
            at = self.written(raw, value)
            at.joinpath(declarations.DECLARED).write_text(
                " " * (declarations.MOST_BYTES + 1) + json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(declarations.Refused, "larger than"):
                declarations.read(at)

    def test_the_fingerprint_covers_behaviour_and_not_the_display_name(self):
        with tempfile.TemporaryDirectory() as raw:
            plain = declarations.read(self.written(raw, self.value())).fingerprint
            renamed = self.value()
            renamed["display_name"] = "Example, Incorporated"
            self.assertEqual(plain, declarations.read(self.written(raw, renamed)).fingerprint)
            for mutation in ({"token_endpoint": "https://id.example/token2"},
                             {"base_scopes": ["identity", "extra"]},
                             {"capabilities": {"reports": "everything"}},
                             {"client_secret": False},
                             {"authorization_parameters": {}},
                             {"identity": {"subject": "sub", "email": "mail",
                                           "email_verified": "verified"}}):
                with self.subTest(mutation=mutation):
                    changed = self.value()
                    changed.update(mutation)
                    self.assertNotEqual(
                        plain, declarations.read(self.written(raw, changed)).fingerprint)

    def test_zero_one_and_duplicate_provider_discovery(self):
        with mock.patch.object(declarations.library, "every", return_value=[]):
            self.assertEqual([], declarations.every())
        with tempfile.TemporaryDirectory() as raw:
            at = self.written(raw, self.value())
            one = declarations.library.Skill("catalog-a", "one", at, "one")
            two = declarations.library.Skill("catalog-b", "two", at, "two")
            with mock.patch.object(declarations.library, "every", return_value=[one]):
                self.assertEqual(["example"], [item.provider for item in declarations.every()])
            with mock.patch.object(declarations.library, "every", return_value=[one, two]):
                held = declarations.discovered()
            # Both dropped, not the first one kept: which skill owns an ID is not a walk order's
            # question, and a grant made against the wrong one is a credential in the wrong place.
            self.assertEqual([], held.providers)
            self.assertEqual(1, len(held.troubles))
            self.assertIn("both", held.troubles[0])

    def test_one_unusable_declaration_does_not_hide_every_other_provider(self):
        with tempfile.TemporaryDirectory() as good, tempfile.TemporaryDirectory() as bad:
            fine = self.written(good, self.value())
            Path(bad).joinpath(declarations.DECLARED).write_text("{ broken", encoding="utf-8")
            skills = [declarations.library.Skill("catalog-a", "fine", fine, "fine"),
                      declarations.library.Skill("catalog-b", "broken", Path(bad), "broken")]
            with mock.patch.object(declarations.library, "every", return_value=skills):
                self.assertEqual("example", declarations.named("example").provider)
                held = declarations.discovered()
                self.assertEqual(["example"], [one.provider for one in held.providers])
                self.assertEqual(1, len(held.troubles))
                with self.assertRaises(declarations.Refused) as caught:
                    declarations.named("absent")
        self.assertIn("cannot be used", str(caught.exception))
        self.assertIn("catalog-b/broken", str(caught.exception))

    def test_installing_a_broken_declaration_is_still_refused_outright(self):
        with tempfile.TemporaryDirectory() as raw:
            at = Path(raw)
            self.assertIsNone(declarations.trouble_with(at))
            at.joinpath(declarations.DECLARED).write_text("{ broken", encoding="utf-8")
            self.assertIn("not readable JSON", declarations.trouble_with(at))
            self.assertIsNone(declarations.trouble_with(self.written(raw, self.value())))


class CallbackAndTokens(unittest.TestCase):
    def test_token_shape_and_verified_identity_are_strict(self):
        with self.assertRaisesRegex(oauth.Refused, "malformed token"):
            oauth._tokens(provider(), {"access_token": "short", "expires_in": "later"})
        with self.assertRaisesRegex(oauth.Refused, "malformed token"):
            oauth._tokens(provider(), {"access_token": "short", "expires_in": True})
        with self.assertRaisesRegex(oauth.Refused, "malformed refresh"):
            oauth._tokens(provider(), {"access_token": "s", "expires_in": 60, "refresh_token": 7})
        self.assertEqual(3600, oauth._tokens(
            provider(), {"access_token": "s", "expires_in": "3600"}).expires_in)
        for wrong in (oauth.Identity("", "a@example.test"), oauth.Identity("s", ""),
                      oauth.Identity("s", "not-an-email")):
            with self.subTest(wrong=wrong), \
                    self.assertRaisesRegex(oauth.Refused, "verified identity"):
                oauth._valid_identity(provider(), wrong)

    def test_a_stray_local_request_is_answered_and_the_flow_keeps_waiting(self):
        """The measured defect: a favicon request became "your login was declined"."""
        server = oauth._callback_server("/random", "expected")
        answer = {}
        waiting = threading.Thread(
            target=lambda: answer.update(result=oauth._awaited(server, time.monotonic() + 20)))
        waiting.start()
        try:
            self.assertEqual(404, self.asked(server, "/favicon.ico").status)
            self.assertEqual(400, self.asked(server, "/random?state=wrong&code=x").status)
            self.assertEqual(400, self.asked(server, "/random?code=x").status)
            self.assertTrue(waiting.is_alive())
            self.assertEqual(200, self.asked(server, "/random?code=real&state=expected").status)
        finally:
            waiting.join(20)
            server.server_close()
        self.assertEqual({"code": "real", "state": "expected"}, answer["result"])

    def test_the_callback_is_pinned_to_the_loopback_address_with_an_ephemeral_random_path(self):
        """Address, port and path each pinned, and each for its own reason."""
        seen = []
        for _ in range(2):
            request = oauth.Authorization(provider(), "client-id", "client-secret", ("identity",))
            shown = io.StringIO()
            with mock.patch.object(oauth, "_awaited", return_value=None), \
                    mock.patch.object(oauth.webbrowser, "open", return_value=True), \
                    contextlib.redirect_stdout(shown), self.assertRaises(oauth.Refused):
                oauth.browser_authorize(request)
            said = shown.getvalue()
            self.assertIn("Listening for the sign-in callback on http://127.0.0.1:", said)
            self.assertNotIn("localhost", said)
            self.assertNotIn("client-secret", said)
            address = said.split("on ", 1)[1].strip()
            parsed = urllib.parse.urlsplit(address)
            self.assertEqual("127.0.0.1", parsed.hostname)
            self.assertIsNotNone(parsed.port)
            self.assertNotEqual(0, parsed.port)
            self.assertGreaterEqual(parsed.port, 1024)
            self.assertEqual(33, len(parsed.path))
            self.assertRegex(parsed.path, r"^/[A-Za-z0-9_-]{32}$")
            self.assertEqual("", parsed.query)
            seen.append((parsed.port, parsed.path))
        self.assertNotEqual(seen[0][1], seen[1][1])

    def test_two_sign_ins_at_once_each_get_a_port_of_their_own(self):
        """A fixed port could not do this: the second bind would be refused outright.

        Two people, or one person retrying in another terminal, must not have to take turns — and
        a port this product picked is a port something else on the machine may already hold.
        """
        servers = [oauth._callback_server(f"/{one}", "state") for one in range(3)]
        try:
            ports = [one.server_port for one in servers]
            self.assertEqual(3, len(set(ports)))
            self.assertTrue(all(port > 0 for port in ports))
        finally:
            for one in servers:
                one.server_close()

    def test_the_completion_page_is_inert_and_says_to_return_to_the_terminal(self):
        server = oauth._callback_server("/random", "expected")
        thread = threading.Thread(target=lambda: oauth._awaited(server, time.monotonic() + 20))
        thread.start()
        try:
            answered = self.asked(server, "/random?code=c&state=expected")
            body = answered.read().decode()
        finally:
            thread.join(20)
            server.server_close()
        self.assertIn("Return to Rundesk", body)
        self.assertIn("default-src 'none'", answered.headers["Content-Security-Policy"])
        self.assertEqual("no-referrer", answered.headers["Referrer-Policy"])
        self.assertNotIn("<img", body)
        self.assertNotIn("http://", body)
        self.assertNotIn("https://", body)

    def test_only_the_exact_state_is_accepted(self):
        server = oauth._callback_server("/random", "expected-state")
        answer = {}
        waiting = threading.Thread(
            target=lambda: answer.update(result=oauth._awaited(server, time.monotonic() + 20)))
        waiting.start()
        try:
            for wrong in ("", "expected", "expected-stat", "expected-statee", "EXPECTED-STATE"):
                self.assertEqual(400, self.asked(server, f"/random?code=c&state={wrong}").status,
                                 wrong)
                self.assertTrue(waiting.is_alive())
            self.assertEqual(200, self.asked(server, "/random?code=c&state=expected-state").status)
        finally:
            waiting.join(20)
            server.server_close()
        self.assertEqual({"code": "c", "state": "expected-state"}, answer["result"])

    def test_provider_response_metadata_does_not_reject_a_valid_callback(self):
        """Google adds OIDC and UI metadata beside the code; none changes callback authority."""
        server = oauth._callback_server("/random", "expected")
        answer = {}
        waiting = threading.Thread(
            target=lambda: answer.update(result=oauth._awaited(server, time.monotonic() + 20)))
        waiting.start()
        try:
            path = ("/random?state=expected&code=real&scope=openid%20email&authuser=0"
                    "&prompt=consent&iss=https%3A%2F%2Faccounts.google.com")
            self.assertEqual(200, self.asked(server, path).status)
        finally:
            waiting.join(20)
            server.server_close()
        self.assertEqual({"code": "real", "state": "expected"}, answer["result"])

    def test_callback_parameters_remain_unambiguous_and_have_one_terminal_result(self):
        server = oauth._callback_server("/random", "expected")
        answer = {}
        waiting = threading.Thread(
            target=lambda: answer.update(result=oauth._awaited(server, time.monotonic() + 20)))
        waiting.start()
        try:
            refused = (
                "/random?state=expected&code=c&scope=one&scope=two",
                "/random?state=expected&code=c&error=denied",
                "/random?state=expected&scope=openid",
            )
            for path in refused:
                self.assertEqual(400, self.asked(server, path).status)
                self.assertTrue(waiting.is_alive())
            self.assertEqual(200, self.asked(server, "/random?state=expected&code=c").status)
        finally:
            waiting.join(20)
            server.server_close()
        self.assertEqual({"code": "c", "state": "expected"}, answer["result"])

    def test_the_whole_flow_still_gives_up_when_nothing_arrives(self):
        server = oauth._callback_server("/random", "expected")
        try:
            self.assertIsNone(oauth._awaited(server, time.monotonic() - 1))
        finally:
            server.server_close()

    def test_neither_callback_page_echoes_what_the_browser_sent(self):
        server = oauth._callback_server("/random", "expected")
        thread = threading.Thread(target=lambda: oauth._awaited(server, time.monotonic() + 20))
        thread.start()
        try:
            rejected = self.asked(server, "/random?state=wrong&code=must-not-echo")
            rejected_body = rejected.read().decode()
            accepted = self.asked(server, "/random?code=secret&state=expected")
            accepted_body = accepted.read().decode()
        finally:
            thread.join(20)
            server.server_close()
        self.assertIn("Authorization rejected", rejected_body)
        self.assertNotIn("must-not-echo", rejected_body)
        self.assertIn("Authorization received", accepted_body)
        self.assertIn("window.close", accepted_body)
        self.assertNotIn("secret", accepted_body)
        self.assertEqual("no-store", accepted.headers["Cache-Control"])
        self.assertEqual("nosniff", accepted.headers["X-Content-Type-Options"])

    def test_redirect_decline_timeout_and_browser_fallback_are_refused_safely(self):
        with self.assertRaisesRegex(oauth.Refused, "redirected"):
            oauth._NoRedirect().redirect_request(None, None, 302, "found", {}, "https://elsewhere")
        request = oauth.Authorization(provider(), "client-id", "client-secret", ("identity",))
        for result, message in (({"error": "declined"}, "declined"), (None, "timed out"),
                                ({"state": "expected"}, "no authorization code")):
            with self.subTest(result=result):
                with mock.patch.object(oauth, "_callback_server", return_value=_Server()), \
                        mock.patch.object(oauth, "_awaited", return_value=result), \
                        mock.patch.object(oauth.webbrowser, "open", return_value=True), \
                        self.assertRaisesRegex(oauth.Refused, message):
                    oauth.browser_authorize(request)
        shown = io.StringIO()
        with mock.patch.object(oauth, "_callback_server", return_value=_Server()), \
                mock.patch.object(oauth, "_awaited", return_value={"error": "no"}), \
                mock.patch.object(oauth.webbrowser, "open", return_value=False), \
                contextlib.redirect_stdout(shown), self.assertRaises(oauth.Refused):
            oauth.browser_authorize(request)
        self.assertIn(provider().authorization_endpoint, shown.getvalue())
        self.assertIn("code_challenge_method=S256", shown.getvalue())
        self.assertNotIn("client-secret", shown.getvalue())

    def test_what_is_printed_with_and_without_a_browser_is_a_different_claim_each_time(self):
        """The boundary, proven rather than asserted in a comment.

        The always-printed listening line is the address and nothing else. The fallback line, which
        only appears when no browser could be opened, *is* the request a person has to make, so it
        necessarily carries this flow's state and PKCE challenge — and never a client secret, an
        authorization code, a refresh token, or an access token.
        """
        request = oauth.Authorization(provider(), "client-id", "unmistakable-secret", ("identity",))

        def shown(opened):
            said = io.StringIO()
            with mock.patch.object(oauth, "_callback_server", return_value=_Server()), \
                    mock.patch.object(oauth, "_awaited", return_value=None), \
                    mock.patch.object(oauth.webbrowser, "open", return_value=opened), \
                    contextlib.redirect_stdout(said), self.assertRaises(oauth.Refused):
                oauth.browser_authorize(request)
            return said.getvalue()

        opened = shown(True)
        self.assertEqual(1, len(opened.splitlines()))
        self.assertIn("Listening for the sign-in callback on http://127.0.0.1:", opened)
        for absent in ("state=", "code_challenge", "unmistakable-secret", "client_id="):
            self.assertNotIn(absent, opened)

        fallback = shown(False)
        url = next(one for one in fallback.splitlines() if one.startswith("https://"))
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query, strict_parsing=True)
        # Present, because they are the request: short-lived, and meaningful only to the loopback
        # server standing behind them for this one flow.
        for mechanic in ("state", "code_challenge", "code_challenge_method", "client_id",
                         "redirect_uri"):
            self.assertIn(mechanic, query)
        # Absent, and these are the ones that would matter. The secret is a field of a POST this
        # module makes; the code comes back over the loopback socket. Neither reaches a terminal.
        self.assertNotIn("unmistakable-secret", fallback)
        for absent in ("client_secret", "code", "refresh_token", "access_token", "code_verifier"):
            self.assertNotIn(absent, query)

    def test_the_authorization_query_carries_every_security_parameter_exactly_once(self):
        request = oauth.Authorization(provider(), "client-id", "client-secret", ("identity",))
        shown = io.StringIO()
        with mock.patch.object(oauth, "_callback_server", return_value=_Server()), \
                mock.patch.object(oauth, "_awaited", return_value=None), \
                mock.patch.object(oauth.webbrowser, "open", return_value=False), \
                contextlib.redirect_stdout(shown), self.assertRaises(oauth.Refused):
            oauth.browser_authorize(request)
        url = next(one for one in shown.getvalue().splitlines()
                   if one.startswith("https://"))
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query, strict_parsing=True)
        self.assertEqual(sorted(oauth.RESERVED_AUTH | {"prompt"}), sorted(query))
        self.assertTrue(all(len(one) == 1 for one in query.values()))
        self.assertEqual(["S256"], query["code_challenge_method"])
        self.assertTrue(query["redirect_uri"][0].startswith("http://127.0.0.1:"))

    def test_a_verified_email_is_required_before_an_identity_is_believed(self):
        request = oauth.Authorization(provider(), "client-id", "client-secret", ("identity",))
        answers = {"access_token": "a", "expires_in": 60, "refresh_token": "r",
                   "scope": "identity"}
        for who, message in (({"subject": "s", "mail": "a@example.test", "verified": False},
                              "did not verify"),
                             ({"subject": "s", "mail": "a@example.test", "verified": "true"},
                              "did not verify"),
                             ({"subject": "s", "mail": "a@example.test"}, "did not verify"),
                             ({"subject": 7, "mail": "a@example.test", "verified": True},
                              "verified identity"),
                             ({"subject": "s", "mail": None, "verified": True},
                              "verified identity")):
            with self.subTest(who=who):
                with mock.patch.object(oauth, "_callback_server", return_value=_Server()), \
                        mock.patch.object(oauth, "_awaited",
                                          return_value={"code": "c", "state": "s"}), \
                        mock.patch.object(oauth.webbrowser, "open", return_value=True), \
                        self.assertRaisesRegex(oauth.Refused, message):
                    oauth.browser_authorize(request, posting=lambda *_: answers,
                                            getting=lambda *_, said=who: said)

    def test_a_refusal_from_the_token_endpoint_is_read_rather_than_called_a_network_fault(self):
        request = urllib.request.Request("https://id.example/token", b"", method="POST")
        failure = urllib.error.HTTPError(
            "https://id.example/token", 400, "Bad Request", {},
            io.BytesIO(b'{"error":"invalid_grant"}'))
        with mock.patch.object(oauth.urllib.request, "build_opener",
                               return_value=_Opener(failure)):
            self.assertEqual({"error": "invalid_grant"}, oauth._opened(request))
        with mock.patch.object(oauth.urllib.request, "build_opener",
                               return_value=_Opener(urllib.error.URLError("closed"))), \
                self.assertRaisesRegex(oauth.Refused, "could not be completed"):
            oauth._opened(request)

    def asked(self, server, path):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=20)
        connection.request("GET", path)
        return connection.getresponse()


class _Server:
    """A callback server that never listens, for the paths that never reach one."""

    def __init__(self):
        self.server_port, self.result, self.timeout = 12345, None, None

    def handle_request(self):
        return None

    def server_close(self):
        return None


class _Opener:
    """A URL opener that raises exactly what a case says the network did."""

    def __init__(self, raising):
        self.raising = raising

    def open(self, *_args, **_kw):
        raise self.raising


if __name__ == "__main__":
    unittest.main()
