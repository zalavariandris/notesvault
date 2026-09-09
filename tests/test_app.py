from textual.widgets import Button, Input

from notesvault.app import NotesVaultApp, SetupScreen
from notesvault.config import ConfigStore


async def wait_for_backup(app, pilot):
    for _ in range(100):
        await pilot.pause(0.05)
        if not app.busy and app.settings.last_backup != "Never":
            return
    raise AssertionError("Backup did not finish")


async def test_demo_dashboard_fetch_and_repeat(tmp_path):
    app = NotesVaultApp(ConfigStore(tmp_path), demo=True)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.click("#fetch")
        await wait_for_backup(app, pilot)
        assert "3 added" in app.settings.last_result
        assert (tmp_path / "backups" / ".git").exists()
        await pilot.click("#fetch")
        await pilot.pause(0.5)
        await app.workers.wait_for_complete()
        assert "No changes" in app.settings.last_result
        await pilot.press("s")
        assert isinstance(app.screen, SetupScreen)
        app.screen.query_one("#interval", Input).value = "0"
        app.screen.query_one("#save", Button).scroll_visible(animate=False)
        await pilot.pause()
        await pilot.click("#save")
        await pilot.pause(0.2)
        await app.workers.wait_for_complete()
        assert app.settings.interval_minutes == 0


async def test_first_launch_setup_and_cancel(tmp_path):
    app = NotesVaultApp(ConfigStore(tmp_path))
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, SetupScreen)
        await pilot.press("escape")
        assert not isinstance(app.screen, SetupScreen)
        assert not app.provider.connected


async def test_saved_session_two_factor_and_logout(tmp_path):
    from notesvault.app import CodeScreen
    from notesvault.config import Settings
    class Secrets:
        values = {"icloud:synthetic@example.invalid": "synthetic-password"}
        def get(self, key):
            return self.values.get(key)
        def set(self, key, value):
            self.values[key] = value
        def delete(self, key):
            self.values.pop(key, None)
    class Provider:
        connected = False
        def login(self, account, password):
            return False
        def verify(self, code):
            assert code == "123456"
            self.connected = True
        def logout(self):
            self.connected = False
    store = ConfigStore(tmp_path)
    store.save(Settings(apple_id="synthetic@example.invalid", backup_folder=str(tmp_path / "backup")))
    secrets = Secrets()
    app = NotesVaultApp(store, secrets=secrets)
    app.provider = Provider()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause(0.2)
        assert isinstance(app.screen, CodeScreen)
        app.screen.query_one("#code", Input).value = "123456"
        await pilot.click("#verify")
        await app.workers.wait_for_complete()
        assert app.provider.connected
        assert app.next_fetch is not None
        await pilot.click("#logout-icloud")
        await app.workers.wait_for_complete()
        assert not app.provider.connected
        assert not secrets.values
        assert app.next_fetch is None


async def test_schedule_starts_fetch_without_a_click(tmp_path):
    from datetime import datetime, timedelta
    app = NotesVaultApp(ConfigStore(tmp_path), demo=True)
    async with app.run_test(size=(100, 40)) as pilot:
        app.next_fetch = datetime.now() - timedelta(seconds=1)
        app.tick()
        await wait_for_backup(app, pilot)
        assert "3 added" in app.settings.last_result


async def test_primary_action_visible_in_small_terminal(tmp_path):
    app = NotesVaultApp(ConfigStore(tmp_path), demo=True)
    async with app.run_test(size=(80, 24)) as pilot:
        assert await pilot.click("#fetch")
        await wait_for_backup(app, pilot)
        assert "3 added" in app.settings.last_result
