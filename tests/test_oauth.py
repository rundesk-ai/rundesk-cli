"""Provider-neutral OAuth state, concurrency, declarations, and token confinement."""

import contextlib
import http.client
import io
import json
import os
import socket
import struct
import tempfile
import threading
import unittest
import urllib.request
from argparse import Namespace
from pathlib import Path
from unittest import mock

import support
from rundesk.commands import login
from rundesk.core import oauth, secrets
from rundesk.skills import oauth as declarations


def provider(fingerprint="descriptor-one"):
    return oauth.Provider("example", "Example", "https://id.example/authorize",
                          "https://id.example/token", "https://id.example/me",
                          ("identity",), "subject", "mail", "verified", {"prompt": "consent"},
                          True, {"reports": "reports.read", "sales": "sales.read"}, fingerprint)


def authorization(subject="immutable-a", email="a@example.test", refresh="refresh-a",
                  scopes=("identity",)):
    def authorize(request):
        return oauth.Tokens("exchange-token", refresh, 3600, tuple(scopes)), \
            oauth.Identity(subject, email)
    return authorize


class State(support.Isolated):
    def setUp(self):
        super().setUp()
        oauth.configure(provider(), "", "client-id", "client-secret")

    def test_multiple_accounts_survive_and_email_is_unambiguous(self):
        oauth.authorize(provider(), authorizing=authorization())
        oauth.authorize(provider(), authorizing=authorization("immutable-b", "b@example.test",
                                                               "refresh-b"))
        self.assertEqual(["a@example.test", "b@example.test"], oauth.emails(provider()))
        with self.assertRaisesRegex(oauth.Refused, "choose --email"):
            oauth.access(provider(), "reports", None)

    def test_scope_extension_persists_only_after_verified_same_identity(self):
        oauth.authorize(provider(), authorizing=authorization())
        answer = oauth.access(provider(), "reports", "a@example.test",
                              authorizing=authorization(scopes=("identity", "reports.read")),
                              posting=lambda *_: {"access_token": "short", "expires_in": 60})
        self.assertEqual("short", answer.token)
        document = json.loads(secrets.value(oauth.STATE))
        account = document["providers"]["example"]["applications"]["default"]["accounts"][
            "immutable-a"]
        self.assertIn("reports.read", account["scopes"])

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
                             posting=lambda *_: {"access_token": "short", "expires_in": 60})
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

    def test_descriptor_drift_is_refused(self):
        with self.assertRaisesRegex(oauth.Refused, "declaration.*changed"):
            oauth.emails(provider("descriptor-two"))

    def test_failed_client_replacement_preserves_state_byte_for_byte(self):
        oauth.authorize(provider(), authorizing=authorization())
        before = secrets.value(oauth.STATE)
        with self.assertRaisesRegex(oauth.Refused, "complete reusable"):
            oauth.replace_client(provider(), "", "new-id", "new-secret",
                                 authorization(refresh=None))
        self.assertEqual(before, secrets.value(oauth.STATE))

    def test_successful_client_replacement_discards_only_that_profile_grants(self):
        oauth.authorize(provider(), authorizing=authorization())
        oauth.configure(provider(), "work", "work-id", "work-secret")
        oauth.authorize(provider(), "work", authorization("work-sub", "work@example.test",
                                                            "work-refresh"))
        oauth.replace_client(provider(), "", "new-id", "new-secret",
                             authorization("new-sub", "new@example.test", "new-refresh"))
        self.assertEqual(["new@example.test"], oauth.emails(provider()))
        self.assertEqual(["work@example.test"], oauth.emails(provider(), "work"))

    def test_client_replacement_preview_does_not_prompt_or_change_state(self):
        oauth.authorize(provider(), authorizing=authorization())
        before = secrets.value(oauth.STATE)
        args = Namespace(provider="example", profile="", replace_client=True, confirm=False)
        with mock.patch.object(declarations, "named", return_value=provider()):
            result = login.cmd_login(args, asking=lambda _prompt: self.fail("prompted"),
                                     asking_secret=lambda _prompt: self.fail("prompted"))
        self.assertNotEqual(0, result)
        self.assertEqual(before, secrets.value(oauth.STATE))


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

    def test_stdio_fifo_unknown_version_truncation_oversize_and_deadline_are_refused(self):
        with self.assertRaises(oauth.Refused):
            oauth.write_frame(1, {"ok": True})
        with tempfile.TemporaryDirectory() as raw:
            fifo = Path(raw) / "named"
            os.mkfifo(str(fifo))
            descriptor = os.open(str(fifo), os.O_RDWR | os.O_NONBLOCK)
            try:
                with self.assertRaisesRegex(oauth.Refused, "socket"):
                    oauth.write_frame(descriptor, {"ok": True})
            finally:
                os.close(descriptor)
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
        reader, writer = socket.socketpair()
        writer.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024)
        try:
            with self.assertRaisesRegex(oauth.Refused, "deadline"):
                oauth.write_frame(writer.fileno(), {"value": "x" * 65000}, timeout=.01)
        finally:
            reader.close()
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
                "capabilities": {"reports": "reports.read"}}

    def test_strict_declarative_schema(self):
        with tempfile.TemporaryDirectory() as raw:
            at = Path(raw)
            at.joinpath(declarations.DECLARED).write_text(json.dumps(self.value()), encoding="utf-8")
            self.assertEqual("example", declarations.read(at).provider)

    def test_insecure_endpoint_and_mechanic_override_are_refused(self):
        for mutation in ({"token_endpoint": "http://id.example/token"},
                         {"authorization_parameters": {"scope": "injected"}}):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as raw:
                value = self.value()
                value.update(mutation)
                at = Path(raw)
                at.joinpath(declarations.DECLARED).write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(declarations.Refused):
                    declarations.read(at)

    def test_missing_unknown_wrong_typed_empty_and_duplicate_values_are_refused(self):
        mutations = []
        missing = self.value()
        missing.pop("identity")
        mutations.append(missing)
        unknown = self.value()
        unknown["surprise"] = True
        mutations.append(unknown)
        wrong = self.value()
        wrong["client_secret"] = "yes"
        mutations.append(wrong)
        empty = self.value()
        empty["capabilities"] = {}
        mutations.append(empty)
        duplicate = self.value()
        duplicate["base_scopes"] = ["identity", "identity"]
        mutations.append(duplicate)
        for value in mutations:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as raw:
                at = Path(raw)
                at.joinpath(declarations.DECLARED).write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(declarations.Refused):
                    declarations.read(at)

    def test_zero_one_and_duplicate_provider_discovery(self):
        with mock.patch.object(declarations.library, "every", return_value=[]):
            self.assertEqual([], declarations.every())
        with tempfile.TemporaryDirectory() as raw:
            at = Path(raw)
            at.joinpath(declarations.DECLARED).write_text(json.dumps(self.value()), encoding="utf-8")
            one = declarations.library.Skill("catalog-a", "one", at, "one")
            two = declarations.library.Skill("catalog-b", "two", at, "two")
            with mock.patch.object(declarations.library, "every", return_value=[one]):
                self.assertEqual(["example"], [item.provider for item in declarations.every()])
            with mock.patch.object(declarations.library, "every", return_value=[one, two]), \
                    self.assertRaisesRegex(declarations.Refused, "both"):
                declarations.every()


class CallbackAndTokens(unittest.TestCase):
    def test_token_shape_and_verified_identity_are_strict(self):
        with self.assertRaisesRegex(oauth.Refused, "malformed token"):
            oauth._tokens(provider(), {"access_token": "short", "expires_in": "later"})
        with self.assertRaisesRegex(oauth.Refused, "verified identity"):
            oauth._valid_identity(provider(), oauth.Identity("", "not-an-email"))

    def test_callback_page_does_not_echo_credentials_and_invalid_state_fails(self):
        server = oauth._callback_server("/random", "expected")
        thread = threading.Thread(target=server.handle_request)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        connection.request("GET", "/random?state=wrong&code=must-not-echo")
        response = connection.getresponse()
        body = response.read().decode()
        thread.join()
        server.server_close()
        self.assertEqual(400, response.status)
        self.assertIn("Authorization rejected", body)
        self.assertNotIn("must-not-echo", body)

    def test_valid_callback_is_safe_html(self):
        server = oauth._callback_server("/random", "expected")
        thread = threading.Thread(target=server.handle_request)
        thread.start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        response = opener.open(f"http://127.0.0.1:{server.server_port}/random?code=secret&state=expected")
        body = response.read().decode()
        thread.join()
        server.server_close()
        self.assertIn("Authorization received", body)
        self.assertIn("window.close", body)
        self.assertNotIn("secret", body)
        self.assertEqual("no-store", response.headers["Cache-Control"])

    def test_redirect_decline_timeout_and_browser_fallback_are_refused_safely(self):
        with self.assertRaisesRegex(oauth.Refused, "redirected"):
            oauth._NoRedirect().redirect_request(None, None, 302, "found", {}, "https://elsewhere")
        request = oauth.Authorization(provider(), "client-id", "client-secret", ("identity",))
        for result, message in (({"error": "declined"}, "declined"), (None, "timed out")):
            server = _Server(result)
            with mock.patch.object(oauth, "_callback_server", return_value=server), \
                    mock.patch.object(oauth.webbrowser, "open", return_value=True), \
                    self.assertRaisesRegex(oauth.Refused, message):
                oauth.browser_authorize(request)
        shown = io.StringIO()
        with mock.patch.object(oauth, "_callback_server", return_value=_Server({"error": "no"})), \
                mock.patch.object(oauth.webbrowser, "open", return_value=False), \
                contextlib.redirect_stdout(shown), self.assertRaises(oauth.Refused):
            oauth.browser_authorize(request)
        self.assertIn(provider().authorization_endpoint, shown.getvalue())
        self.assertNotIn("client-secret", shown.getvalue())


class _Server:
    def __init__(self, result):
        self.server_port, self.result, self.timeout = 12345, result, None

    def handle_request(self):
        return None

    def server_close(self):
        return None


if __name__ == "__main__":
    unittest.main()
