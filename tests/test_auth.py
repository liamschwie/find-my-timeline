import tempfile
import unittest
from pathlib import Path
from unittest import mock

from findmy import InvalidCredentialsError, TrustedDeviceSecondFactorMethod

from find_my_timeline import auth
from find_my_timeline.auth import AuthenticationError


class FakeAccount:
    def __init__(self, login_state="OK", methods=None):
        self._login_state = login_state
        self._methods = methods or []
        self.saved_to = None

    def login(self, username, password):
        return self._login_state

    def get_2fa_methods(self):
        return self._methods

    def to_json(self, path):
        self.saved_to = Path(path)
        Path(path).write_text("{}")


class FakeMethod(TrustedDeviceSecondFactorMethod):
    def __init__(self, code="123456"):
        # Don't call super().__init__() to avoid constructor requirements
        self.requested = False
        self.submitted_code = None
        self._code = code

    def request(self):
        self.requested = True

    def submit(self, code):
        self.submitted_code = code


class TestLoadSession(unittest.TestCase):
    def test_raises_when_no_session_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(auth, "ACCOUNT_PATH", Path(tmp) / "account.json"):
                with self.assertRaises(AuthenticationError):
                    auth.load_session()

    def test_load_session_returns_account_when_session_exists(self):
        # Fix 4: Test load_session() success path
        with tempfile.TemporaryDirectory() as tmp:
            account_path = Path(tmp) / "account.json"
            account_path.write_text("{}")

            fake_account = FakeAccount()

            with (
                mock.patch.object(auth, "ACCOUNT_PATH", account_path),
                mock.patch.object(auth, "ANISETTE_LIBS_PATH", Path(tmp) / "libs"),
                mock.patch.object(
                    auth, "AppleAccount"
                ) as mock_apple_account,
            ):
                mock_apple_account.from_json.return_value = fake_account
                result = auth.load_session()

            self.assertIs(result, fake_account)
            mock_apple_account.from_json.assert_called_once_with(
                str(account_path), anisette_libs_path=str(Path(tmp) / "libs")
            )


class TestLogin(unittest.TestCase):
    def test_login_without_2fa_saves_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            account_path = Path(tmp) / "account.json"
            fake_account = FakeAccount(login_state=auth.LoginState.LOGGED_IN)

            with (
                mock.patch.object(auth, "ACCOUNT_PATH", account_path),
                mock.patch.object(auth, "STORE_DIR", Path(tmp)),
                mock.patch.object(auth, "LocalAnisetteProvider", return_value=mock.Mock()),
                mock.patch.object(auth, "AppleAccount", return_value=fake_account),
            ):
                result = auth.login("user@example.com", "hunter2")

            self.assertIs(result, fake_account)
            self.assertTrue(account_path.exists())
            # Fix 2: Assert file permissions
            self.assertEqual(account_path.stat().st_mode & 0o777, 0o600)

    def test_login_with_2fa_prompts_and_submits_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            account_path = Path(tmp) / "account.json"
            method = FakeMethod()
            fake_account = FakeAccount(
                login_state=auth.LoginState.REQUIRE_2FA, methods=[method]
            )

            with (
                mock.patch.object(auth, "ACCOUNT_PATH", account_path),
                mock.patch.object(auth, "STORE_DIR", Path(tmp)),
                mock.patch.object(auth, "LocalAnisetteProvider", return_value=mock.Mock()),
                mock.patch.object(auth, "AppleAccount", return_value=fake_account),
                mock.patch("builtins.input", side_effect=["0", "123456"]),
            ):
                auth.login("user@example.com", "hunter2")

            self.assertTrue(method.requested)
            self.assertEqual(method.submitted_code, "123456")

    def test_login_raises_authentication_error_on_invalid_credentials(self):
        # Fix 1: Handle InvalidCredentialsError
        with tempfile.TemporaryDirectory() as tmp:
            fake_account = FakeAccount()
            fake_account.login = mock.Mock(
                side_effect=InvalidCredentialsError("Invalid credentials")
            )

            with (
                mock.patch.object(auth, "STORE_DIR", Path(tmp)),
                mock.patch.object(auth, "LocalAnisetteProvider", return_value=mock.Mock()),
                mock.patch.object(auth, "AppleAccount", return_value=fake_account),
            ):
                with self.assertRaises(AuthenticationError):
                    auth.login("user@example.com", "wrongpassword")


if __name__ == "__main__":
    unittest.main()
