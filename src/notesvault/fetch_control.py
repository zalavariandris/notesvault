"""Cooperative fetch controls, independent of the UI and network provider."""
from threading import Condition
from typing import Callable, Iterable, Iterator, TypeVar

from .models import AppError

T = TypeVar("T")


class FetchCancelled(AppError):
    def __init__(self):
        super().__init__("Fetch cancelled. Existing backups are unchanged.")


class FetchControl:
    def __init__(self, on_change: Callable[[str], None] = lambda state: None):
        self._condition = Condition()
        self._state = "running"
        # May run on either thread; the UI adapter must enqueue notifications.
        self._on_change = on_change

    @property
    def state(self) -> str:
        with self._condition:
            return self._state

    def _change(self, state: str) -> None:
        self._state = state
        self._condition.notify_all()
        self._on_change(state)

    def pause(self) -> bool:
        with self._condition:
            if self._state != "running":
                return False
            self._change("pausing")
            return True

    def resume(self) -> bool:
        with self._condition:
            if self._state not in ("pausing", "paused"):
                return False
            self._change("running")
            return True

    def cancel(self) -> bool:
        with self._condition:
            if self._state in ("saving", "cancelling"):
                return False
            self._change("cancelling")
            return True

    def checkpoint(self) -> None:
        with self._condition:
            while self._state in ("pausing", "paused"):
                if self._state == "pausing":
                    self._change("paused")
                self._condition.wait()
            if self._state == "cancelling":
                raise FetchCancelled()

    def begin_save(self) -> None:
        # Checking cancellation and crossing the write boundary must be atomic.
        with self._condition:
            self.checkpoint()
            self._change("saving")

    def iterate(self, values: Iterable[T]) -> Iterator[T]:
        iterator = iter(values)
        while True:
            self.checkpoint()
            try:
                value = next(iterator)
            except StopIteration:
                return
            self.checkpoint()
            yield value
