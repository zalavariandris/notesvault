from notesvault.markdown_export import to_markdown


def test_headings_inline_styles_links_and_quotes():
    text = to_markdown('<h1>Title</h1><p><span style="font-weight:bold; font-style:italic">Both</span> '
                       '<u>under</u> <s>gone</s> <a href="https://example.invalid/a(b)">link</a></p>'
                       '<blockquote>Quoted<br>Second line</blockquote>')
    assert "# Title" in text
    assert "***Both***" in text
    assert "<u>under</u>" in text
    assert "~~gone~~" in text
    assert "[link](https://example.invalid/a%28b%29)" in text
    assert "> Quoted" in text and "> Second line" in text


def test_nested_lists_numbering_and_checkboxes():
    text = to_markdown('<ol start="3"><li>One<ul><li>Nested</li></ul></li><li>Two</li></ol>'
                       '<ul><li><input type="checkbox" checked> Done</li>'
                       '<li><input type="checkbox"> Next</li></ul>')
    assert "3. One" in text and "4. Two" in text
    assert "   - Nested" in text
    assert "- [x]" in text and "- [ ]" in text


def test_tables_escape_cell_pipes():
    text = to_markdown('<table><tbody><tr><th>A</th><th>B</th></tr>'
                       '<tr><td>a|b</td><td><b>bold</b></td></tr></tbody></table>')
    assert "| A | B |\n| --- | --- |" in text
    assert r"a\|b" in text and "**bold**" in text


def test_code_preserves_spacing_and_backticks():
    text = to_markdown('<pre>  first\n\n\n```\nlast &lt;value&gt;</pre><p><code>a`b</code></p>')
    assert "````\n  first\n\n\n```\nlast <value>\n````" in text
    assert "`` a`b ``" in text


def test_media_tokens_and_unsafe_html_are_never_exported():
    text = to_markdown('<p>Text *literal* &lt;tag&gt;</p><script>private-script</script>'
                       '<img src="https://example.invalid/image?token=secret">'
                       '<a class="attachment file" href="https://example.invalid/file?token=secret">file</a>'
                       '<object data="https://example.invalid/pdf?token=secret">fallback</object>'
                       '<a href="javascript:alert(1)">Label</a>')
    assert "secret" not in text and "javascript" not in text and "private-script" not in text
    assert "[Attachment]" in text
    assert r"\*literal\*" in text and r"\<tag\>" in text
    assert "Label" in text
