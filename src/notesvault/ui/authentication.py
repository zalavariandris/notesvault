"""Reusable account form: receives display values and emits user actions only."""
from typing import Callable, Literal

import edifice as ed
from PySide6.QtCore import Qt

from .password_input import PasswordInput
from .components import Text, Action, INPUT


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
    account_ref = ed.use_ref()
    code_ref = ed.use_ref()

    ed.use_effect(lambda: set_account(account), (account,))

    def clear_secrets():
        set_password("")
        set_code("")

    ed.use_effect(clear_secrets, (phase,))

    def focus_field():
        if phase == "verify" and code_ref():
            code_ref().underlying.setFocus()
        elif phase == "login" and not account and account_ref():
            account_ref().underlying.setFocus()

    ed.use_effect(focus_field, (phase,))

    def login(_):
        if enabled and account_draft.strip() and on_login(account_draft, password):
            clear_secrets()

    def verify(_):
        if enabled and code.strip() and on_verify(code):
            clear_secrets()

    def cancel(_):
        if on_cancel():
            clear_secrets()

    with ed.VBoxView():
        Text(account or disconnected_text)
        if phase == "verify":
            Text("Enter the verification code from your trusted device or phone.")
            ed.TextInput(code, on_change=set_code, placeholder_text="Verification code", enabled=enabled,
                         style=INPUT, on_key_up=lambda event: verify(event) if event.key() in
                         (Qt.Key.Key_Return, Qt.Key.Key_Enter) else None).register_ref(code_ref)
            Action("Verify", verify, enabled=enabled and bool(code.strip()), primary=True)
        elif phase == "login":
            Text("Apple Account email")
            ed.TextInput(account_draft, on_change=set_account,
                         placeholder_text=account_placeholder, enabled=enabled, style=INPUT).register_ref(account_ref)
            Text("Password", style={"margin-top": 10})
            PasswordInput(password, on_change=set_password, enabled=enabled, on_submit=login, focus=bool(account))
            Text("Your password is saved in your computer's credential store after verification.")
            Action("Sign in", login, enabled=enabled and bool(account_draft.strip()), primary=True)
        elif phase == "connected":
            Action(logout_text, lambda _: on_logout(), enabled=enabled)
        else:
            Action("Login", lambda _: on_connect(), enabled=enabled)
        if phase in ("login", "verify"):
            Action("Cancel setup", cancel, enabled=enabled)
