"""Serialize background operations without depending on Qt or dashboard state."""
import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from .fetch_control import FetchControl

T = TypeVar("T")


@dataclass(frozen=True)
class Task(Generic[T]):
    name: str
    future: Future[T]
    control: FetchControl | None = None


class TaskManager:
    """Called on the owning event-loop thread; only operations run on the worker."""
    def __init__(self):
        self.active: Task | None = None
        self.closed = False
        self.closing = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="notesvault")

    @property
    def busy(self) -> bool:
        return self.active is not None

    def start(self, name: str, operation: Callable[[Callable[[str], None]], T],
              progress: Callable[[str], None], *, control: FetchControl | None = None) -> Task[T] | None:
        if self.busy or self.closed or self.closing:
            return None
        task = Task(name, self._executor.submit(operation, progress), control)
        # Reserve synchronously, before the UI has rendered the new task name.
        self.active = task
        return task

    async def wait(self, task: Task[T]) -> T:
        future = asyncio.wrap_future(task.future)
        cancelled = False
        # asyncio.wait does not forward coroutine cancellation to the worker.
        # Keep consuming its outcome even if unmount cancels this waiter repeatedly.
        while not future.done():
            try:
                await asyncio.wait((future,))
            except asyncio.CancelledError:
                cancelled = True
                if task.control:
                    task.control.cancel()
        if cancelled:
            if not future.cancelled():
                future.exception()
            raise asyncio.CancelledError()
        return future.result()

    def finish(self, task: Task) -> None:
        if task is self.active and task.future.done():
            self.active = None

    def close(self) -> None:
        self.closed = True
        if self.active and self.active.control:
            self.active.control.cancel()
        self._executor.shutdown(wait=True)
        self.active = None

    def request_close(self) -> None:
        """Prevent new tasks and let an active fetch stop at a safe checkpoint."""
        self.closing = True
        if self.active and self.active.control:
            self.active.control.cancel()
