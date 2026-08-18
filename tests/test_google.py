"""Google OAuth profiles, grant replacement, and the token confinement boundary."""

import contextlib
import io
import json
import os
import socket
import struct
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

import support
from rundesk.core import google, secrets

REFRESH_A = "refresh-secret-account-a"
REFRESH_B = "refresh-secret-account-b"
ACCESS = "short-lived-access-secret"


class Google(support.Isolated):
    def client(self, profile=""):
        suffix = profile.upper()
        secrets.stated(secrets.profiled(google.CLIENT_ID, suffix), "client-id" + suffix)
        secrets.stated(secrets.profiled(google.CLIENT_SECRET, suffix), "client-secret" + suffix)

    def authorizer(self, sub="sub-a", email="a@example.com", refresh=REFRESH_A, scopes=None):
        def authorized(request):
            granted = tuple(scopes or request.scopes)
            return (google.Tokens("exchange-access", refresh, 3600, granted),
                    google.Identity(sub, email))
        return authorized


class Login(Google):
    def test_public_login_prints_only_the_verified_email(self):
        self.client()
        code, out, err = support.run_with(
            ["login", "google"], google_authorizing=self.authorizer())
        self.assertEqual(0, code)
        self.assertEqual("Connected a@example.com\n", out)
        self.assertEqual("", err)
        self.assertNotIn(REFRESH_A, out + err)

    def test_refresh_token_and_all_metadata_are_inside_the_sealed_value(self):
        self.client()
        google.authorize(authorizing=self.authorizer())
        on_disk = secrets.where().read_text()
        for plain in (REFRESH_A, "a@example.com", "sub-a", "analytics.readonly"):
            self.assertNotIn(plain, on_disk)

    def test_two_accounts_share_one_app_profile_and_are_selected_by_email(self):
        self.client()
        google.authorize(authorizing=self.authorizer())
        google.authorize(authorizing=self.authorizer("sub-b", "b@example.com", REFRESH_B))
        self.assertEqual(["a@example.com", "b@example.com"], google.emails())
        with self.assertRaisesRegex(google.Refused, "choose --email"):
            google.access("analytics", None)

    def test_app_profiles_have_separate_clients_and_accounts(self):
        self.client("work")
        google.authorize("work", authorizing=self.authorizer())
        self.assertEqual(["a@example.com"], google.emails("WORK"))
        self.assertEqual(["a@example.com"], google.emails(), "the sole app profile was not selected")

    def test_duplicate_authorization_replaces_only_the_same_sub(self):
        self.client()
        google.authorize(authorizing=self.authorizer())
        google.authorize(authorizing=self.authorizer("sub-b", "b@example.com", REFRESH_B))
        google.authorize(authorizing=self.authorizer(refresh="new-refresh-for-a"))
        document = json.loads(secrets.value(google.GRANTS))
        accounts = document["applications"]["default"]["accounts"]
        self.assertEqual("new-refresh-for-a", accounts["sub-a"]["refresh_token"])
        self.assertEqual(REFRESH_B, accounts["sub-b"]["refresh_token"])

    def test_concurrent_accounts_survive_one_atomic_grant_document(self):
        self.client()
        count = 8
        ready = threading.Barrier(count)
        failures = []

        def connect(number):
            def authorizer(request):
                ready.wait()
                return self.authorizer(f"sub-{number}", f"user{number}@example.com",
                                       f"refresh-{number}")(request)
            try:
                google.authorize(authorizing=authorizer)
            except (google.Refused, secrets.Refused, secrets.Stuck,
                    threading.BrokenBarrierError) as trouble:
                failures.append(trouble)

        workers = [threading.Thread(target=connect, args=(number,)) for number in range(count)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(5)
        self.assertEqual([], failures)
        self.assertEqual(count, len(google.emails()))

    def test_app_profile_key_cannot_change_while_the_browser_is_open(self):
        self.client()

        def mutating(request):
            secrets.cleared(google.CLIENT_ID)
            secrets.cleared(google.CLIENT_SECRET)
            self.client("work")
            return self.authorizer()(request)

        google.authorize(authorizing=mutating)
        document = json.loads(secrets.value(google.GRANTS))
        self.assertIn("default", document["applications"])
        self.assertNotIn("WORK", document["applications"])

    def test_missing_refresh_token_changes_nothing(self):
        self.client()
        google.authorize(authorizing=self.authorizer())
        before = secrets.value(google.GRANTS)
        with self.assertRaisesRegex(google.Refused, "no refresh token"):
            google.authorize(authorizing=self.authorizer(refresh=None))
        self.assertEqual(before, secrets.value(google.GRANTS))


class ScopeExtension(Google):
    def setUp(self):
        super().setUp()
        self.client()
        google.authorize(authorizing=self.authorizer())

    def test_missing_scope_reconsents_same_identity_then_refreshes(self):
        asked = []

        def authorize(request):
            asked.append(request.scopes)
            return self.authorizer(scopes=request.scopes)(request)

        answer = google.access(
            "analytics", "a@example.com", authorizing=authorize,
            posting=lambda _url, _fields: {"access_token": ACCESS, "expires_in": 60})
        self.assertEqual(ACCESS, answer.token)
        self.assertIn(google.CAPABILITIES["analytics"], asked[0])

    def test_wrong_account_during_scope_extension_changes_nothing(self):
        before = secrets.value(google.GRANTS)
        with self.assertRaisesRegex(google.Refused, "different account"):
            google.access("merchant", "a@example.com",
                          authorizing=self.authorizer("sub-b", "b@example.com", REFRESH_B))
        self.assertEqual(before, secrets.value(google.GRANTS))

    def test_client_rotation_requires_login_again(self):
        secrets.stated(google.CLIENT_ID, "rotated-client")
        with self.assertRaisesRegex(google.Refused, "client changed"):
            google.access("analytics", "a@example.com")

    def test_concurrent_scope_extensions_preserve_the_winner_and_refuse_the_stale_one(self):
        ready = threading.Barrier(2)
        successes = []
        failures = []

        def extend(capability, refresh):
            def authorizer(request):
                ready.wait()
                return self.authorizer(refresh=refresh, scopes=request.scopes)(request)
            try:
                google.access(capability, "a@example.com", authorizing=authorizer,
                              posting=lambda _url, _fields: {
                                  "access_token": ACCESS, "expires_in": 60})
                successes.append(capability)
            except google.Refused as trouble:
                failures.append((capability, str(trouble)))

        workers = [threading.Thread(target=extend, args=("analytics", "refresh-analytics")),
                   threading.Thread(target=extend, args=("merchant", "refresh-merchant"))]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(5)

        self.assertEqual(1, len(successes))
        self.assertEqual(1, len(failures))
        self.assertIn("changed while consent was open", failures[0][1])
        account = json.loads(secrets.value(google.GRANTS))["applications"]["default"][
            "accounts"]["sub-a"]
        winner, loser = successes[0], failures[0][0]
        self.assertIn(google.CAPABILITIES[winner], account["scopes"])
        self.assertNotIn(google.CAPABILITIES[loser], account["scopes"])
        self.assertEqual(f"refresh-{winner}", account["refresh_token"])


class AnonymousResponse(Google):
    def test_hidden_accounts_operation_returns_only_through_the_socket(self):
        self.client()
        writer, reader = socket.socketpair()
        try:
            code, out, err = support.run_with(
                ["_google", "accounts", "--response-fd", str(writer.fileno())])
            response = google.read_frame(reader.fileno())
        finally:
            writer.close()
            reader.close()
        self.assertEqual((0, "", ""), (code, out, err))
        self.assertEqual([], response["accounts"])

    def test_frame_is_length_prefixed_versioned_and_bounded(self):
        writer, reader = socket.socketpair()
        try:
            google.write_frame(writer.fileno(), {"ok": True, "access_token": ACCESS})
            size = struct.unpack(">I", reader.recv(4))[0]
            body = json.loads(reader.recv(size))
        finally:
            writer.close()
            reader.close()
        self.assertEqual(1, body["version"])
        self.assertEqual(ACCESS, body["access_token"])

    def test_stdio_and_regular_files_are_refused(self):
        with self.assertRaises(google.Refused):
            google.write_frame(1, {"ok": True})
        with tempfile.NamedTemporaryFile() as held:
            with self.assertRaisesRegex(google.Refused, "socket"):
                google.write_frame(held.fileno(), {"ok": True})

    def test_a_named_fifo_is_not_an_anonymous_response_socket(self):
        with tempfile.TemporaryDirectory() as root:
            fifo = os.path.join(root, "named-fifo")
            os.mkfifo(fifo)
            descriptor = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
            try:
                with self.assertRaisesRegex(google.Refused, "socket"):
                    google.write_frame(descriptor, {"ok": True})
            finally:
                os.close(descriptor)

    def test_socket_is_an_allowed_anonymous_boundary(self):
        one, other = socket.socketpair()
        try:
            google.write_frame(one.fileno(), {"ok": True})
            self.assertEqual(1, struct.unpack(">I", other.recv(4))[0] > 0)
        finally:
            one.close()
            other.close()

    def test_reader_rejects_an_unknown_protocol_version(self):
        writer, reader = socket.socketpair()
        body = b'{"version":9,"ok":true}'
        try:
            writer.sendall(struct.pack(">I", len(body)) + body)
            with self.assertRaisesRegex(google.Refused, "version"):
                google.read_frame(reader.fileno())
        finally:
            writer.close()
            reader.close()

    def test_a_nonreading_peer_cannot_block_the_writer_past_its_deadline(self):
        writer, reader = socket.socketpair()
        writer.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024)
        try:
            with self.assertRaisesRegex(google.Refused, "deadline"):
                google.write_frame(writer.fileno(), {"value": "x" * 65000}, timeout=0.02)
        finally:
            writer.close()
            reader.close()


class Transport(Google):
    def test_redirects_are_refused(self):
        handler = google._NoRedirect()
        with self.assertRaisesRegex(google.Refused, "redirected"):
            handler.redirect_request(None, None, 302, "found", {}, "https://elsewhere")

    def test_malformed_token_response_is_refused(self):
        with self.assertRaisesRegex(google.Refused, "malformed token"):
            google._tokens({"access_token": ACCESS, "expires_in": "soon"})

    def test_callback_rejects_a_state_mismatch(self):
        server = google._callback_server("/only-this-path", "right-state")
        serving = threading.Thread(target=server.handle_request)
        serving.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/only-this-path?code=x&state=wrong"
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=2)
            serving.join(2)
            self.assertEqual("invalid_callback", server.result["error"])
            body = rejected.exception.read().decode("utf-8")
            self.assertIn("Authorization rejected", body)
            self.assertNotIn("Connected", body)
            self.assertEqual("no-store", rejected.exception.headers["Cache-Control"])
        finally:
            server.server_close()

    def test_valid_callback_page_claims_receipt_not_persisted_success(self):
        server = google._callback_server("/only-this-path", "right-state")
        serving = threading.Thread(target=server.handle_request)
        serving.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/only-this-path?code=secret-code&state=right-state"
            response = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url,
                                                                                       timeout=2)
            body = response.read().decode("utf-8")
            serving.join(2)
            self.assertIn("Authorization received", body)
            self.assertIn("close this tab manually", body)
            self.assertIn("window.close", body)
            self.assertNotIn("Connected", body)
            self.assertNotIn("secret-code", body)
            self.assertNotIn("right-state", body)
            self.assertEqual("text/html; charset=utf-8", response.headers["Content-Type"])
            self.assertEqual("no-store", response.headers["Cache-Control"])
            self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])
        finally:
            server.server_close()

    def test_declined_consent_is_a_token_free_refusal(self):
        server = _Server({"error": "access_denied"})
        request = google.Authorization("client-id", "client-secret", google.BASE_SCOPES)
        with mock.patch.object(google, "_callback_server", return_value=server), \
                mock.patch.object(google.webbrowser, "open", return_value=True), \
                self.assertRaisesRegex(google.Refused, "declined"):
            google.browser_authorize(request)

    def test_callback_timeout_is_a_token_free_refusal(self):
        server = _Server(None)
        request = google.Authorization("client-id", "client-secret", google.BASE_SCOPES)
        with mock.patch.object(google, "_callback_server", return_value=server), \
                mock.patch.object(google.webbrowser, "open", return_value=True), \
                self.assertRaisesRegex(google.Refused, "timed out"):
            google.browser_authorize(request)

    def test_browser_open_failure_prints_a_manual_url_but_no_client_secret(self):
        server = _Server({"error": "access_denied"})
        request = google.Authorization("client-id", "client-secret", google.BASE_SCOPES)
        shown = io.StringIO()
        with mock.patch.object(google, "_callback_server", return_value=server), \
                mock.patch.object(google.webbrowser, "open", return_value=False), \
                contextlib.redirect_stdout(shown), self.assertRaises(google.Refused):
            google.browser_authorize(request)
        self.assertIn(google.AUTHORIZE_AT, shown.getvalue())
        self.assertNotIn("client-secret", shown.getvalue())


class _Server:
    """A listener seam that completes without opening a real socket."""

    def __init__(self, result):
        self.server_port = 12345
        self.result = result
        self.timeout = None

    def handle_request(self):
        return None

    def server_close(self):
        return None


if __name__ == "__main__":
    unittest.main()
