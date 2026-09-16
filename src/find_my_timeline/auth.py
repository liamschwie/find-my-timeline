"""Apple account authentication via the findmy library."""

from pathlib import Path

from findmy import (
    AppleAccount,
    LocalAnisetteProvider,
    LoginState,
    SmsSecondFactorMethod,
    TrustedDeviceSecondFactorMethod,
)


class AuthenticationError(Exception):
    """Raised when authentication fails or no session is available."""


STORE_DIR = Path.home() / ".find-my-timeline"
ACCOUNT_PATH = STORE_DIR / "account.json"
ANISETTE_LIBS_PATH = STORE_DIR / "ani_libs.bin"


def _handle_2fa(account: AppleAccount) -> None:
    """Prompt for and submit a 2FA code on stdin."""
    methods = account.get_2fa_methods()

    print("Two-factor authentication required. Available methods:")
    for index, method in enumerate(methods):
        if isinstance(method, TrustedDeviceSecondFactorMethod):
            print(f"  {index}: Trusted Device")
        elif isinstance(method, SmsSecondFactorMethod):
            print(f"  {index}: SMS ({method.phone_number})")
        else:
            print(f"  {index}: {type(method).__name__}")

    choice = int(input("Select method: ").strip())
    method = methods[choice]
    method.request()

    code = input("Enter the verification code: ").strip()
    method.submit(code)


def login(username: str, password: str) -> AppleAccount:
    """Authenticate with Apple and persist the session. Returns the logged-in account."""
    STORE_DIR.mkdir(parents=True, exist_ok=True)

    anisette = LocalAnisetteProvider(libs_path=str(ANISETTE_LIBS_PATH))
    account = AppleAccount(anisette)

    state = account.login(username, password)
    if state == LoginState.REQUIRE_2FA:
        _handle_2fa(account)

    ACCOUNT_PATH.parent.mkdir(parents=True, exist_ok=True)
    account.to_json(str(ACCOUNT_PATH))
    ACCOUNT_PATH.chmod(0o600)

    return account


def load_session() -> AppleAccount:
    """Restore a previously saved session.

    Raises AuthenticationError if no session has been saved yet.
    """
    if not ACCOUNT_PATH.exists():
        raise AuthenticationError(
            "No saved session found. Run 'find-my-timeline auth' first."
        )

    return AppleAccount.from_json(
        str(ACCOUNT_PATH), anisette_libs_path=str(ANISETTE_LIBS_PATH)
    )
