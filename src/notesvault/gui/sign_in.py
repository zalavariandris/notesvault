"""Focused sign-in window; authentication state and operations belong to Dashboard."""
import edifice as ed
from PySide6.QtCore import Qt

from .authentication import AuthenticationComponent
from .components import Text


@ed.component
def SignInWindow(self, account, phase, busy, operation, error, on_login, on_verify, on_cancel):
    ref = ed.use_ref()
    alive = ed.use_memo(lambda: [True], ())

    def configure():
        window = ref().underlying_noparent
        window.setWindowModality(Qt.WindowModality.ApplicationModal)
        window.hide()
        window.show()
        window.raise_()
        def cleanup():
            # WindowPopView invokes on_close during destruction as well.
            alive[0] = False
        return cleanup

    ed.use_effect(configure, ())

    def close(event):
        event.ignore()
        if alive[0] and not busy:
            on_cancel()

    with ed.WindowPopView(title="Connect iCloud", _size_open=(420, 440), on_close=close,
                          on_key_up=lambda event: close(event) if event.key() == Qt.Key.Key_Escape else None,
                          style={"padding": 24, "align": "top"}).register_ref(ref):
        Text("Verify your account" if phase == "verify" else "Connect iCloud",
             style={"font-size": 23, "font-weight": "bold"})
        Text("Step 2 · Verification" if phase == "verify" else "Step 1 · Sign in")
        if error:
            Text(error, style={"font-weight": "bold"})
        AuthenticationComponent(account=account, phase=phase, on_login=on_login, on_verify=on_verify,
                                on_cancel=on_cancel, on_connect=lambda: False, on_logout=lambda: False,
                                enabled=not busy, account_placeholder="name@example.com",
                                disconnected_text="Use the Apple Account that contains your notes.")
        if busy:
            Text(operation or "Working…")
            ed.ProgressBar(0, min_value=0, max_value=0, style={"height": 5})
            Text("Please wait for this request to finish before closing.")
