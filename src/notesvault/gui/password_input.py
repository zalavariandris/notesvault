import edifice as ed
from PySide6.QtWidgets import QLineEdit
from PySide6.QtCore import Qt
from .components import INPUT

@ed.component
def PasswordInput(self, text, on_change, enabled=True, on_submit=None, focus=False):
    ref = ed.use_ref()

    def configure():
        ref().underlying.setEchoMode(QLineEdit.EchoMode.Password)
        if focus:
            ref().underlying.setFocus()

    ed.use_effect(configure, ())
    ed.TextInput(text, placeholder_text="Password (blank uses saved password)",
                 on_change=on_change, enabled=enabled, style=INPUT,
                 on_key_up=lambda event: on_submit(event) if enabled and on_submit and
                 event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) else None).register_ref(ref)
