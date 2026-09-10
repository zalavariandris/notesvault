"""Bounded activity history without a dependency on the desktop UI."""
from dataclasses import dataclass
from datetime import datetime

MAX_ENTRIES = 200


@dataclass(frozen=True)
class LogEntry:
    time: str
    message: str


def append_entry(entries: tuple[LogEntry, ...], message: str, now: datetime) -> tuple[LogEntry, ...]:
    return (*entries, LogEntry(now.strftime("%H:%M:%S"), message))[-MAX_ENTRIES:]


def log_text(entries: tuple[LogEntry, ...]) -> str:
    return "\n\n".join(f"{entry.time}  {entry.message}" for entry in entries)
