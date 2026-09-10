from .models import AppError


class SecretStoreController:
    """Use only an OS-backed keyring, never pyicloud's plaintext fallback."""

    def __init__(self):
        self._backend = None

    def backend(self):
        if self._backend is None:
            import sys
            if sys.platform == "win32":
                from keyring.backends.Windows import WinVaultKeyring
                self._backend = WinVaultKeyring()
            elif sys.platform == "darwin":
                from keyring.backends.macOS import Keyring
                self._backend = Keyring()
            else:
                from keyring.backends.SecretService import Keyring
                self._backend = Keyring()
        return self._backend

    def get(self, name: str) -> str | None:
        try:
            return self.backend().get_password("NotesVault", name)
        except Exception as exc:
            raise AppError("OS credential storage is unavailable. Unlock or configure your credential store.") from exc

    def set(self, name: str, value: str) -> None:
        try:
            self.backend().set_password("NotesVault", name, value)
        except Exception as exc:
            raise AppError("Could not save the credential in the OS credential store.") from exc

    def delete(self, name: str) -> None:
        if self.get(name) is not None:
            try:
                self.backend().delete_password("NotesVault", name)
            except Exception as exc:
                raise AppError("Could not remove the saved credential.") from exc
