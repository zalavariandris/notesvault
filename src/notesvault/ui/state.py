from dataclasses import dataclass
from datetime import datetime
from ..config import Settings

@dataclass(frozen=True)
class DashboardState:
    settings: Settings
    connected: bool
    busy: bool = False
    next_fetch: datetime | None = None
    logs: tuple[str, ...] = ()
    setup_step: str = ""
    setup_error: str = ""