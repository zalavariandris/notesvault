
from typing import Callable

import edifice as ed
from PySide6.QtWidgets import QFileDialog


@ed.component
def FolderInput(self, folder: str, on_change: Callable[[str], None], enabled: bool = True):
    window_ref = ed.use_ref()

    def browse(_):
        selected = QFileDialog.getExistingDirectory(window_ref().underlying, "Choose backup folder", folder)
        if selected:
            on_change(selected)

    with ed.HBoxView().register_ref(window_ref):
        ed.TextInput(folder, on_change=on_change, enabled=enabled)
        ed.Button("Browse...", on_click=browse, enabled=enabled)
