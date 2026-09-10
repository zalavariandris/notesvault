"""Reusable account form: receives display values and emits user actions only."""
from typing import Callable, Literal

import edifice as ed

from .password_input import PasswordInput


@ed.component
def AuthenticationComponent(
    self,
    account: str,
    phase: Literal["idle", "login", "verify", "connected"],
    on_login: Callable[[str, str], bool],
    on_verify: Callable[[str], bool],
    on_connect: Callable[[], bool],
    on_logout: Callable[[], bool],
    on_cancel: Callable[[], bool],
    enabled: bool = True,
    account_placeholder: str = "Account",
    disconnected_text: str = "No account connected",
    logout_text: str = "Disconnect",
):
    account_draft, set_account = ed.use_state(account)
    password, set_password = ed.use_state("")
    code, set_code = ed.use_state("")

    ed.use_effect(lambda: set_account(account), (account,))

    def clear_secrets():
        set_password("")
        set_code("")

    ed.use_effect(clear_secrets, (phase,))

    def login(_):
        if on_login(account_draft, password):
            clear_secrets()

    def verify(_):
        if on_verify(code):
            clear_secrets()

    def cancel(_):
        if on_cancel():
            clear_secrets()

    with ed.VBoxView():
        ed.Label(account or disconnected_text)
        ed.Label("Connected" if phase == "connected" else "Not connected")
        if phase == "verify":
            ed.Label("Enter the verification code from your trusted device or phone.")
            ed.TextInput(code, on_change=set_code, placeholder_text="Verification code", enabled=enabled)
            ed.Button("Verify", on_click=verify, enabled=enabled)
        elif phase == "login":
            ed.TextInput(account_draft, on_change=set_account,
                         placeholder_text=account_placeholder, enabled=enabled)
            PasswordInput(password, on_change=set_password, enabled=enabled)
            ed.Button("Login", on_click=login, enabled=enabled)
        elif phase == "connected":
            ed.Button(logout_text, on_click=lambda _: on_logout(), enabled=enabled)
        else:
            ed.Button("Login", on_click=lambda _: on_connect(), enabled=enabled)
        if phase in ("login", "verify"):
            ed.Button("Cancel setup", on_click=cancel, enabled=enabled)
