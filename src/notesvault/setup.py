"""Authentication operations shared by the graphical setup forms."""
from dataclasses import replace

from .models import AppError


class AccountSetup:
    def __init__(self, store, secrets, provider):
        self.store, self.secrets, self.provider = store, secrets, provider
        self.account = ""
        self._password = None

    def login(self, account, password):
        account = account.strip().lower()
        if not account:
            raise AppError("Enter your Apple Account email.")
        self._password = None
        password = password or self.secrets.get(f"icloud:{account}")
        if not password:
            raise AppError("Enter your iCloud password.")
        old = self.store.load().apple_id
        if old and old != account:
            self.provider.logout()
        self.account = account
        ready = self.provider.login(account, password)
        self._password = password
        if not ready:
            return False
        self._save()
        return True

    def verify(self, code):
        if not self._password:
            raise AppError("Sign in again to request a verification code.")
        if not code.strip():
            raise AppError("Enter the verification code.")
        self.provider.verify(code.strip())
        self._save()

    def _save(self):
        try:
            settings = self.store.load()
            self.secrets.set(f"icloud:{self.account}", self._password)
            self.store.save(replace(settings, apple_id=self.account))
            if settings.apple_id and settings.apple_id != self.account:
                self.secrets.delete(f"icloud:{settings.apple_id}")
        finally:
            self._password = None

    def cancel(self):
        pending = self._password is not None
        self._password = None
        if pending:
            self.provider.logout()

    def clear(self):
        self._password = None
