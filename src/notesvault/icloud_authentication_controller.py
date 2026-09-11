"""Own iCloud authentication, saved credentials, and the active session."""
from dataclasses import replace

from .models import AppError
from .provider_utils import stable_id
from .config_store import ConfigStoreController
from .icloud_secret_store import SecretStoreController


class ICloudAuthenticationController:
    def __init__(self, store: ConfigStoreController, secrets: SecretStoreController):
        self.store = store
        self.secrets = secrets
        self.session_directory = store.directory / "sessions"
        self.account = ""
        self._api = None
        self._password = None
        self._ready = False

    @property
    def connected(self) -> bool:
        return (self._ready and self._api is not None
                and not self._api.requires_2fa and not self._api.requires_2sa)

    @property
    def session(self):
        if not self.connected:
            raise AppError("Reconnect iCloud before fetching.")
        return self._api

    def login(self, account: str, password: str = "", *, interactive=True) -> bool:
        from pyicloud import PyiCloudService

        account = account.strip().lower()
        if not account:
            raise AppError("Enter your Apple Account email.")
        self._password = None
        password = password or self.secrets.get(f"icloud:{account}")
        if not password:
            raise AppError("Enter your iCloud password.")
        previous = self.account or self.store.load().apple_id
        if previous and previous != account:
            self._close_session(previous)
        self.clear()
        self.account = account
        try:
            self._api = PyiCloudService(account, password,
                cookie_directory=str(self.session_directory / stable_id(account)),
                with_family=False, accept_terms=False)
            if self._api.requires_2fa:
                if self._api.security_key_names:
                    raise AppError("This account requires a hardware security key; this version supports code-based 2FA only.")
                if not interactive:
                    self.clear()
                    return False
                self._api.request_2fa_code()
                self._password = password
                return False
            if self._api.requires_2sa:
                raise AppError("Legacy two-step authentication is not supported in this version.")
            self._api.notes
            self._password = password
            self._save()
            return True
        except AppError:
            self.clear()
            raise
        except Exception as exc:
            self.clear()
            raise exc

    def login_saved(self) -> None:
        """Reconnect for --once without requesting a verification code or prompting."""
        account = self.store.load().apple_id
        if not account:
            raise AppError("Open the desktop or --tui to connect iCloud and choose a backup folder.")
        if not self.login(account, interactive=False):
            raise AppError("Reconnect iCloud in the desktop or --tui before running --once.")

    def verify(self, code: str) -> None:
        if self._api is None or not self._password:
            raise AppError("Sign in again to request a verification code.")
        if not code.strip():
            raise AppError("Enter the verification code.")
        try:
            if not self._api.validate_2fa_code(code.strip()):
                raise AppError("The verification code was not accepted. Try again.")
            self._api.trust_session()
            self._api.notes
        except AppError:
            raise
        except Exception as exc:
            raise AppError("Could not verify iCloud. Reconnect and request a new code.") from exc
        self._save()

    def _save(self):
        try:
            settings = self.store.load()
            self.secrets.set(f"icloud:{self.account}", self._password)
            self.store.save(replace(settings, apple_id=self.account))
            if settings.apple_id and settings.apple_id != self.account:
                self.secrets.delete(f"icloud:{settings.apple_id}")
            self._ready = True
        except Exception:
            self.clear()
            raise
        finally:
            self._password = None

    def _close_session(self, account: str):
        try:
            if self._api is None and account:
                from pyicloud import PyiCloudService
                self._api = PyiCloudService(account,
                    cookie_directory=str(self.session_directory / stable_id(account)),
                    with_family=False, accept_terms=False, authenticate=False)
            if self._api is not None:
                try:
                    self._api.logout()
                except Exception:
                    # Remote logout is best effort; local persistence must be removed.
                    pass
                self._api.session.clear_persistence(remove_files=True)
        except Exception as exc:
            raise AppError("Could not clear the local iCloud session. Check folder permissions and retry.") from exc
        finally:
            self.clear()

    def logout(self) -> None:
        settings = self.store.load()
        self._close_session(self.account or settings.apple_id)
        if settings.apple_id:
            self.secrets.delete(f"icloud:{settings.apple_id}")
        self.store.save(replace(settings, apple_id=""))
        self.account = ""

    def cancel(self) -> None:
        if self._password is not None:
            self._close_session(self.account)

    def clear(self) -> None:
        """Release in-memory credentials/session while preserving saved login data."""
        self._password = None
        self._api = None
        self._ready = False
