import edifice as ed
from PySide6.QtWidgets import QLineEdit

@ed.component
def PasswordInput(self, text, on_change, enabled=True):
    ref = ed.use_ref()

    def configure():
        ref().underlying.setEchoMode(QLineEdit.EchoMode.Password)

    ed.use_effect(configure, ())
    ed.TextInput(text, placeholder_text="Password (blank uses saved password)",
                 on_change=on_change, enabled=enabled).register_ref(ref)
