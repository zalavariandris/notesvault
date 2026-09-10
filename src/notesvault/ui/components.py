"""Shared visual primitives. Content is always rendered as plain text."""
import edifice as ed
from PySide6.QtCore import Qt

INPUT = {"padding": 6, "min-width": 0}


@ed.component
def Text(self, text, style=None):
    ed.Label(str(text), word_wrap=True, selectable=True, text_format=Qt.TextFormat.PlainText,
             style={"font-size": 13, "margin-bottom": 5,
                    "min-width": 0, **(style or {})})


@ed.component
def Card(self, title, subtitle="", children: tuple[ed.Element, ...] = ()):
    with ed.VBoxView(style={"padding": 16, "margin-bottom": 10, "align": "top"}):
        Text(title, style={"font-size": 16, "font-weight": "bold"})
        if subtitle:
            Text(subtitle)
        for child in children:
            ed.child_place(child)


@ed.component
def Action(self, text, on_click, enabled=True, primary=False):
    ed.Button(text, on_click=on_click, enabled=enabled,
              style={"padding": 9, "margin-top": 4, **({"font-weight": "bold"} if primary else {})})
