"""PyEdifice adapter for task results, progress, and window lifetime."""
import asyncio
from dataclasses import dataclass
from typing import Callable

import edifice as ed
from PySide6.QtCore import QEvent, QObject

from ..models import AppError
from ..fetch_control import FetchCancelled, FetchControl
from ..task_manager import TaskManager


@dataclass(frozen=True)
class FetchActions:
    state: str
    pause: Callable[[], bool]
    resume: Callable[[], bool]
    cancel: Callable[[], bool]


def use_tasks(window_ref, log_output, cleanup):
    manager = ed.use_memo(TaskManager, ())
    active_task, set_active_task = ed.use_state("")
    task_progress, set_task_progress = ed.use_state("")
    control_state, set_control_state = ed.use_state("")

    def on_mount():
        window = window_ref().underlying

        class CloseGuard(QObject):
            def eventFilter(self, watched, event):
                if event.type() == QEvent.Type.Close and manager.busy:
                    if manager.active.control:
                        manager.request_close()
                        log_output("Closing after the fetch stops safely. Any local save already in progress will finish.")
                    else:
                        log_output("Wait for the current task to finish before closing.")
                    event.ignore()
                    return True
                return False

        guard = CloseGuard(window)
        window.installEventFilter(guard)

        def on_unmount():
            manager.close()
            cleanup()
            window.removeEventFilter(guard)
            guard.deleteLater()
            window.hide()
            window.deleteLater()

        return on_unmount

    ed.use_effect(on_mount, ())

    async def consume(task, on_success, on_error, on_cancel):
        try:
            result = await manager.wait(task)
            if not manager.closed:
                on_success(result)
        except asyncio.CancelledError:
            raise
        except FetchCancelled as exc:
            if not manager.closed:
                log_output(str(exc))
                if on_cancel:
                    on_cancel()
        except Exception as exc:
            if not manager.closed:
                message = str(exc) if isinstance(exc, AppError) else (
                    "Operation failed. Check the connection, folder permissions, and settings, then retry."
                )
                log_output(message)
                on_error(message)
        finally:
            manager.finish(task)
            if not manager.closed:
                set_active_task("")
                set_task_progress("")
                set_control_state("")
                if manager.closing:
                    # The worker has stopped and released staging/repository locks.
                    asyncio.get_running_loop().call_soon(window_ref().underlying.close)

    consume_task, _ = ed.use_async_call(consume)

    def start_task(name, operation, on_success, on_error, *, cancellable=False, on_cancel=None):
        if manager.closed or manager.closing or manager.busy:
            return False
        loop = asyncio.get_running_loop()

        def deliver(message):
            if not manager.closed:
                log_output(message)
                # A queued update from an earlier task must not label a new task.
                if manager.active is task:
                    set_task_progress(message)

        def progress(message):
            if not manager.closed:
                loop.call_soon_threadsafe(deliver, message)

        def deliver_state(state):
            if not manager.closed and manager.active is task:
                set_control_state(state)

        control = FetchControl(lambda state: loop.call_soon_threadsafe(deliver_state, state)) if cancellable else None
        worker = (lambda progress: operation(progress, control)) if control else operation
        task = manager.start(name, worker, progress, control=control)
        if task is None:
            return False
        set_active_task(name)
        set_task_progress("")
        set_control_state("running" if control else "")
        consume_task(task, on_success, on_error, on_cancel)
        return True

    def control_action(action):
        task = manager.active
        if not task or not task.control or task.future.done() or manager.closed or manager.closing:
            return False
        return getattr(task.control, action)()

    controls = FetchActions(control_state, lambda: control_action("pause"),
                            lambda: control_action("resume"), lambda: control_action("cancel"))
    return (active_task, task_progress, start_task,
            lambda: manager.busy or manager.closed or manager.closing, controls)
