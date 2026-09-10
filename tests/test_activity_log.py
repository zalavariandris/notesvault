from datetime import datetime

from notesvault.activity_log import append_entry, log_text, MAX_ENTRIES


def test_history_is_bounded_and_preserves_order():
    entries = ()
    for number in range(MAX_ENTRIES + 3):
        entries = append_entry(entries, f"Fetch {number}", datetime(2026, 9, 10, 12, 30, 5))
    assert len(entries) == MAX_ENTRIES
    assert entries[0].message == "Fetch 3"
    assert entries[-1].message == "Fetch 202"


def test_log_format_preserves_literal_text_and_multiline_messages():
    entries = append_entry((), "<synthetic>\nSecond line", datetime(2026, 9, 10, 8, 9, 10))
    assert log_text(entries) == "08:09:10  <synthetic>\nSecond line"
    assert log_text(()) == ""
