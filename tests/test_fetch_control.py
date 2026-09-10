from concurrent.futures import ThreadPoolExecutor
import asyncio
from threading import Event

import pytest

from notesvault.fetch_control import FetchCancelled, FetchControl
from notesvault.task_manager import TaskManager


def test_pause_waits_at_checkpoint_and_resume_continues():
    paused = Event()
    passed = Event()
    control = FetchControl(lambda state: paused.set() if state == "paused" else None)
    control.pause()
    def work():
        control.checkpoint()
        passed.set()
    with ThreadPoolExecutor() as executor:
        future = executor.submit(work)
        try:
            assert paused.wait(5)
            assert not passed.is_set()
            assert control.state == "paused"
            assert control.resume()
            future.result(timeout=5)
            assert passed.is_set()
            assert control.state == "running"
        finally:
            control.cancel()


def test_cancelling_paused_worker_wakes_it_and_releases_on_close():
    paused = Event()
    control = FetchControl(lambda state: paused.set() if state == "paused" else None)
    control.pause()
    manager = TaskManager()
    task = manager.start("Fetch", lambda progress: control.checkpoint(), lambda _: None, control=control)
    try:
        assert paused.wait(5)
        manager.request_close()
        assert manager.start("New task", lambda progress: None, lambda _: None) is None
        with pytest.raises(FetchCancelled):
            task.future.result(timeout=5)
    finally:
        manager.close()
    assert not manager.busy


def test_forced_unmount_also_cancels_paused_fetch():
    control = FetchControl()
    control.pause()
    manager = TaskManager()
    task = manager.start("Fetch", lambda progress: control.checkpoint(), lambda _: None, control=control)
    manager.close()
    with pytest.raises(FetchCancelled):
        task.future.result()


def test_cancelled_async_wait_cancels_paused_worker_without_unhandled_exception():
    manager = TaskManager()
    control = FetchControl()
    control.pause()
    errors = []
    async def scenario():
        asyncio.get_running_loop().set_exception_handler(lambda loop, context: errors.append(context))
        task = manager.start("Fetch", lambda progress: control.checkpoint(), lambda _: None, control=control)
        waiting = asyncio.create_task(manager.wait(task))
        await asyncio.sleep(0)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        assert task.future.done()
        assert isinstance(task.future.exception(), FetchCancelled)
        manager.finish(task)
        await asyncio.sleep(0)
        assert not errors
    try:
        asyncio.run(scenario())
    finally:
        manager.close()


def test_cancel_before_save_blocks_writes_and_cannot_be_resumed():
    control = FetchControl()
    assert control.cancel()
    assert not control.resume()
    assert not control.pause()
    with pytest.raises(FetchCancelled):
        control.begin_save()


def test_save_boundary_rejects_cancellation_and_pause():
    control = FetchControl()
    control.begin_save()
    assert control.state == "saving"
    assert not control.cancel()
    assert not control.pause()
    assert not control.resume()
    control.checkpoint()


def test_iteration_checks_cancel_before_consuming_another_chunk():
    control = FetchControl()
    consumed = []
    def chunks():
        consumed.append(1)
        yield b"first"
        consumed.append(2)
        yield b"second"
    iterator = control.iterate(chunks())
    assert next(iterator) == b"first"
    control.cancel()
    with pytest.raises(FetchCancelled):
        next(iterator)
    assert consumed == [1]
