"""Convert PyiCloud's rendered note fragments to local, readable Markdown."""
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import quote, urlsplit


@dataclass
class Element:
    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    children: list = field(default_factory=list)


class FragmentParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Element(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in {"br", "hr", "img", "input", "meta", "link", "source", "wbr", "embed"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def escape_text(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\r\n", "\n")
    text = re.sub(r"([\\`*_{}\[\]<>|])", r"\\\1", text)
    return re.sub(r"(?m)^(\s*)([#>+-]|\d+[.)])(?=\s)", r"\1\\\2", text)


def code_fence(text: str) -> str:
    return "`" * max(3, 1 + max((len(m[0]) for m in re.finditer(r"`+", text)), default=0))


def to_markdown(fragment: str) -> str:
    parser = FragmentParser()
    parser.feed(fragment)
    parser.close()

    def render(node, *, raw=False):
        if isinstance(node, str):
            return node if raw else escape_text(node)
        tag, attrs = node.tag, node.attrs
        if tag in {"script", "style", "head"}:
            return ""
        # Never persist remote media URLs, which may contain temporary access tokens.
        if tag in {"img", "object", "video", "audio", "iframe", "embed"} or (
            "attachment" in (attrs.get("class") or "").split() and tag != "table"
        ):
            return "[Attachment]"
        if tag == "input":
            if attrs.get("type") == "checkbox":
                return "[x] " if "checked" in attrs else "[ ] "
            return ""
        if tag == "br":
            return "\n" if raw else "  \n"
        if tag == "hr":
            return "\n\n---\n\n"
        if tag == "pre":
            content = "".join(render(child, raw=True) for child in node.children).rstrip("\n")
            fence = code_fence(content)
            return f"\n\n{fence}\n{content}\n{fence}\n\n"
        if tag in {"ul", "ol"}:
            items = []
            try:
                start = int(attrs.get("start") or "1")
            except ValueError:
                start = 1
            for child in node.children:
                if isinstance(child, str) or child.tag != "li":
                    continue
                prefix = f"{start}. " if tag == "ol" else "- "
                content = "".join(render(part) for part in child.children).strip()
                lines = content.splitlines() or [""]
                items.append(prefix + lines[0] + "".join("\n" + " " * len(prefix) + line for line in lines[1:]))
                start += 1
            return "\n\n" + "\n".join(items) + "\n\n"
        if tag == "table":
            rows = []
            def find_rows(element):
                for child in element.children:
                    if isinstance(child, str):
                        continue
                    if child.tag == "tr":
                        rows.append([render(cell).strip().replace("\n", "<br>") for cell in child.children
                                     if isinstance(cell, Element) and cell.tag in {"td", "th"}])
                    elif child.tag in {"thead", "tbody", "tfoot"}:
                        find_rows(child)
            find_rows(node)
            if not rows:
                return ""
            width = max(map(len, rows))
            rows = [row + [""] * (width - len(row)) for row in rows]
            rows.insert(1, ["---"] * width)
            return "\n\n" + "\n".join("| " + " | ".join(row) + " |" for row in rows) + "\n\n"
        content = "".join(render(child, raw=raw or tag == "code") for child in node.children)
        if raw:
            return content
        if tag == "code":
            content = content.replace("\n", " ")
            fence = "`" * (1 + max((len(m[0]) for m in re.finditer(r"`+", content)), default=0))
            return f"{fence} {content} {fence}"
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return "\n\n" + "#" * int(tag[1]) + " " + content.strip() + "\n\n"
        if tag == "blockquote":
            return "\n\n" + "\n".join("> " + line for line in content.strip().splitlines()) + "\n\n"
        if tag == "a":
            href = attrs.get("href") or ""
            try:
                url = urlsplit(href)
                safe = url.scheme.lower() in {"https", "http", "mailto"} and not url.username and not url.password
            except ValueError:
                safe = False
            if safe:
                return f"[{content}]({quote(href, safe=':/?#@!$&=+%,;~')})"
            return content
        styles = dict(part.strip().lower().split(":", 1) for part in (attrs.get("style") or "").split(";") if ":" in part)
        styles = {key.strip(): value.strip() for key, value in styles.items()}
        markers = []
        if tag in {"strong", "b"} or styles.get("font-weight") in {"bold", "700", "800", "900"}:
            markers.append("**")
        if tag in {"em", "i"} or styles.get("font-style") == "italic":
            markers.append("*")
        if tag in {"s", "del", "strike"} or "line-through" in styles.get("text-decoration", ""):
            markers.append("~~")
        if content.strip():
            stripped = content.strip()
            left = content[:len(content) - len(content.lstrip())]
            right = content[len(content.rstrip()):]
            for marker in markers:
                stripped = marker + stripped + marker
            if tag == "u" or "underline" in styles.get("text-decoration", ""):
                stripped = "<u>" + stripped + "</u>"
            if tag in {"sup", "sub"}:
                stripped = f"<{tag}>" + stripped + f"</{tag}>"
            content = left + stripped + right
        if tag in {"p", "div", "section"}:
            return "\n\n" + content.strip() + "\n\n"
        return content

    # Preserve blank lines and code whitespace supplied by the note.
    output = render(parser.root).strip()
    return output + "\n" if output else ""
