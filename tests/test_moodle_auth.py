import os
import tempfile
import unittest
from unittest import mock

from src import profiles as profile_store
from src.moodle_client import MoodleAPIError, MoodleClient


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class MoodleAuthTests(unittest.TestCase):
    def test_from_credentials_uses_mobile_service_and_returns_client(self):
        with mock.patch("src.moodle_client.requests.post", return_value=FakeResponse({"token": "abc123"})) as post:
            with mock.patch.object(MoodleClient, "_test_connection", return_value=None):
                client = MoodleClient.from_credentials(
                    "https://moodle.example.com",
                    "teacher",
                    "secret",
                )

        self.assertEqual(client.base_url, "https://moodle.example.com")
        self.assertEqual(client.token, "abc123")
        self.assertEqual(post.call_args.kwargs["data"]["service"], "moodle_mobile_app")
        self.assertFalse(post.call_args.kwargs["allow_redirects"])
        self.assertEqual(post.call_args.args[0], "https://moodle.example.com/login/token.php")

    def test_from_credentials_surfaces_moodle_error_message(self):
        with mock.patch("src.moodle_client.requests.post", return_value=FakeResponse({"error": "Invalid login"})):
            with self.assertRaises(MoodleAPIError) as ctx:
                MoodleClient.from_credentials("https://moodle.example.com", "teacher", "bad-secret")

        self.assertIn("Invalid login", str(ctx.exception))

    def test_rejects_insecure_remote_urls_before_sending_credentials(self):
        with mock.patch("src.moodle_client.requests.post") as post:
            with self.assertRaisesRegex(MoodleAPIError, "HTTPS"):
                MoodleClient.from_credentials("http://moodle.example.com", "teacher", "secret")
            with self.assertRaisesRegex(MoodleAPIError, "embedded credentials"):
                MoodleClient.from_credentials("https://teacher:secret@moodle.example.com", "teacher", "secret")
        post.assert_not_called()

    def test_allows_loopback_http_for_local_development(self):
        with mock.patch.object(MoodleClient, "_test_connection", return_value=None):
            client = MoodleClient("http://127.0.0.1:8080/moodle/", "token")
        self.assertEqual(client.base_url, "http://127.0.0.1:8080/moodle")

    def test_rejects_token_request_redirects(self):
        with mock.patch(
            "src.moodle_client.requests.post",
            return_value=FakeResponse({}, status_code=307),
        ):
            with self.assertRaisesRegex(MoodleAPIError, "redirected"):
                MoodleClient.from_credentials("https://moodle.example.com", "teacher", "secret")

    def test_profiles_can_store_username_without_password(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(profile_store, "PROFILES_DIR", tmpdir):
                with mock.patch.object(profile_store, "PROFILES_FILE", os.path.join(tmpdir, "profiles.json")):
                    profile_store.upsert_profile(
                        "Campus",
                        "https://moodle.example.com",
                        "",
                        username="teacher",
                    )

                    profile = profile_store.get_profile("Campus")

        self.assertIsNotNone(profile)
        self.assertEqual(profile["username"], "teacher")
        self.assertEqual(profile["token"], "")
        self.assertNotIn("password", profile)


if __name__ == "__main__":
    unittest.main()
