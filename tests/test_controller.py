from datetime import datetime, timedelta
from queue import Queue
from threading import Event, get_ident

import pytest

from notesvault.backup import git
from notesvault.config import ConfigStore, Settings
from notesvault.controller import BackupController
from notesvault.models import AppError
from notesvault.providers import DemoProvider


class Secrets:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value

    def delete(self, key):
        self.values.pop(key, None)


class Provider(DemoProvider):
    connected = False

    def login(self, account, password):
        self.account = account
        return False

    def verify(self, code):
        if code != "123456":
            raise AppError("Invalid verification code")
        self.connected = True

    def logout(self):
        self.connected = False


@pytest.fixture
def controller_factory(tmp_path):
    controllers = []

    def create(**kwargs):
        completions = Queue()
        controller = BackupController(ConfigStore(tmp_path / "config"),
                                      secrets=Secrets(), on_change=lambda _: None,
                                      on_progress=lambda _: None, on_completed=completions.put, **kwargs)
        controllers.append(controller)
        return controller, completions

    yield create
    for controller in controllers:
        controller.cleanup()


def finish(controller, completions):
    # Deliver worker results on the calling thread, with no Qt or widgets.
    completion = completions.get(timeout=10)
    controller.finish_task(completion)
    return completion


def test_task_blocks_overlap_until_owner_thread_consumes_completion(controller_factory):
    controller, completions = controller_factory(is_demo=True)
    release = Event()
    owner = get_ident()
    updates = []
    controller.on_change = lambda state: updates.append(get_ident())

    def operation():
        assert get_ident() != owner
        assert release.wait(5)
        return controller.state.settings, ["Done"]

    try:
        assert controller._start_task("Synthetic task", operation)
        assert controller.state.active_task == "Synthetic task"
        assert not controller.fetch_notes()
        assert not controller.save_settings("", "0")
        assert not controller.cancel_setup()
        release.set()
        completion = completions.get(timeout=10)
        assert controller.state.busy
        assert "Done" not in controller.state.logs
        controller.finish_task(completion)
        assert not controller.state.busy
        assert controller.state.logs == ("Done",)
        assert set(updates) == {owner}
        controller.finish_task(completion)
        assert controller.state.logs == ("Done",)
    finally:
        release.set()


@pytest.mark.parametrize("error", [AppError("Synthetic failure"), RuntimeError("sensitive detail")])
def test_task_failure_clears_busy_and_allows_retry(controller_factory, error):
    controller, completions = controller_factory(is_demo=True)

    def fail():
        raise error

    assert controller._start_task("Failing task", fail)
    finish(controller, completions)
    assert not controller.state.busy
    assert controller.state.setup_error
    assert "sensitive detail" not in " ".join(controller.state.logs)
    assert controller.state.next_fetch is not None
    assert controller.fetch_notes()
    finish(controller, completions)
    assert not controller.state.setup_error
    assert "3 added" in controller.state.settings.last_result


def test_folder_login_and_verification_resume_fetch(controller_factory, tmp_path):
    provider = Provider()
    controller, completions = controller_factory(provider=provider)
    assert controller.fetch_notes()
    assert controller.state.setup_step == "folder"
    folder = str(tmp_path / "backup")
    assert controller.save_settings(folder, "0")
    finish(controller, completions)
    assert controller.state.setup_step == "login"
    assert controller.login_to_icloud("synthetic@example.invalid", "synthetic-password")
    finish(controller, completions)
    assert controller.state.setup_step == "verify"
    assert controller.verify_code("wrong")
    finish(controller, completions)
    assert controller.state.setup_step == "verify"
    assert controller.config_store.load().last_backup == "Never"
    assert controller.verify_code("123456")
    finish(controller, completions)
    assert controller.state.active_task == "Fetching iCloud notes"
    finish(controller, completions)
    assert "3 added" in controller.config_store.load().last_result
    assert controller.state.next_fetch is None
    assert git(tmp_path / "backup", "rev-parse", "--verify", "HEAD").returncode == 0


def test_cancel_preserves_saved_folder_and_clears_pending_fetch(controller_factory, tmp_path):
    provider = Provider()
    controller, completions = controller_factory(provider=provider)
    controller.fetch_notes()
    controller.save_settings(str(tmp_path / "backup"), "10")
    finish(controller, completions)
    controller.login_to_icloud("synthetic@example.invalid", "synthetic-password")
    finish(controller, completions)
    controller.cancel_setup()
    finish(controller, completions)
    assert controller.account._password is None
    assert not controller._pending_fetch
    assert not controller.state.setup_step
    assert controller.config_store.load().backup_folder == str(tmp_path / "backup")
    assert controller.config_store.load().last_backup == "Never"


def test_save_before_fetch_and_invalid_settings_preserve_previous_values(controller_factory, tmp_path):
    controller, completions = controller_factory(is_demo=True)
    assert controller.save_settings(str(tmp_path / "backup"), "0", fetch_after=True)
    finish(controller, completions)
    assert controller.state.active_task == "Fetching iCloud notes"
    finish(controller, completions)
    saved = controller.config_store.load()
    assert saved.last_backup != "Never"
    assert controller.save_settings(str(tmp_path / "different"), "invalid")
    finish(controller, completions)
    assert controller.config_store.load() == saved
    assert controller.state.settings == saved
    assert not (tmp_path / "different").exists()


def test_schedule_fetch_and_disconnect_pause(controller_factory, tmp_path):
    provider = Provider()
    provider.connected = True
    controller, completions = controller_factory(provider=provider)
    controller.save_settings(str(tmp_path / "backup"), "1")
    finish(controller, completions)
    controller._set(next_fetch=datetime.now() - timedelta(seconds=1))
    controller.tick()
    assert controller.state.busy
    finish(controller, completions)
    head = git(tmp_path / "backup", "rev-parse", "HEAD").stdout
    assert controller.state.next_fetch > datetime.now()
    controller.disconnect_icloud()
    finish(controller, completions)
    assert not controller.state.connected
    assert controller.state.next_fetch is None
    assert git(tmp_path / "backup", "rev-parse", "HEAD").stdout == head


def test_saved_account_login_and_cleanup(controller_factory):
    controller, completions = controller_factory(provider=Provider())
    settings = Settings(apple_id="synthetic@example.invalid")
    controller.config_store.save(settings)
    controller._set(settings=settings)
    controller.secrets_store.set("icloud:synthetic@example.invalid", "synthetic-password")
    assert controller.login_button()
    finish(controller, completions)
    assert controller.state.setup_step == "verify"
    controller.cleanup()
    assert controller.account._password is None
    assert not controller.login_button()
    assert not controller.fetch_notes()


def test_unrelated_operation_does_not_resume_failed_pending_fetch(controller_factory):
    controller, completions = controller_factory(provider=Provider())
    controller.save_settings("", "invalid", fetch_after=True)
    finish(controller, completions)
    controller.disconnect_icloud()
    finish(controller, completions)
    assert not controller.state.busy
    assert not controller.state.setup_step
    assert controller.state.next_fetch is None
