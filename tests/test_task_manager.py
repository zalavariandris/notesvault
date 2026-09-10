import asyncio
import threading

import pytest

from notesvault.task_manager import TaskManager


def test_reservation_lasts_until_result_consumed_and_runs_off_thread():
    manager = TaskManager()
    release = threading.Event()
    caller = threading.get_ident()

    def operation(progress):
        assert release.wait(5)
        return threading.get_ident()

    try:
        task = manager.start("Synthetic backup", operation, lambda _: None)
        assert manager.active.name == "Synthetic backup"
        assert manager.start("Overlapping task", operation, lambda _: None) is None
        manager.finish(task)
        assert manager.busy
        release.set()
        assert asyncio.run(manager.wait(task)) != caller
        assert manager.busy
        assert manager.start("Unconsumed result", operation, lambda _: None) is None
        manager.finish(task)
        assert not manager.busy
    finally:
        release.set()
        manager.close()
    assert manager.start("After close", operation, lambda _: None) is None


def test_failure_is_delivered_and_next_task_can_run():
    manager = TaskManager()
    def fail(progress):
        raise ValueError("synthetic failure")
    try:
        task = manager.start("Failing", fail, lambda _: None)
        with pytest.raises(ValueError, match="synthetic failure"):
            asyncio.run(manager.wait(task))
        manager.finish(task)
        task = manager.start("Retry", lambda progress: 42, lambda _: None)
        assert asyncio.run(manager.wait(task)) == 42
        manager.finish(task)
    finally:
        manager.close()


def test_cancelled_wait_keeps_worker_reserved_until_it_finishes():
    manager = TaskManager()
    release = threading.Event()
    def operation(progress):
        assert release.wait(5)
        return "saved"

    async def scenario():
        task = manager.start("Saving", operation, lambda _: None)
        waiting = asyncio.create_task(manager.wait(task))
        await asyncio.sleep(0)
        waiting.cancel()
        await asyncio.sleep(0)
        assert not waiting.done()
        manager.finish(task)
        assert manager.busy
        assert manager.start("Too early", operation, lambda _: None) is None
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        assert task.future.result() == "saved"
        manager.finish(task)
        assert not manager.busy

    try:
        asyncio.run(scenario())
    finally:
        release.set()
        manager.close()


def test_close_waits_for_pending_writes():
    manager = TaskManager()
    release = threading.Event()
    saved = threading.Event()
    def operation(progress):
        assert release.wait(5)
        saved.set()
    manager.start("Saving", operation, lambda _: None)
    timer = threading.Timer(0.05, release.set)
    timer.start()
    try:
        manager.close()
        assert saved.is_set()
        assert not manager.busy and manager.closed
    finally:
        release.set()
        timer.join()
