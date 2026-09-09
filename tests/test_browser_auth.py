from types import SimpleNamespace

import pytest

from notesvault.browser_auth import BrowserSession, session_from_response
from notesvault.models import AppError
from notesvault.providers import ICloudProvider

URL = "https://setup.icloud.com/setup/ws/1/accountLogin"
ACCOUNT = "synthetic@example.invalid"


def response(account=ACCOUNT, trusted=True):
    return {"dsInfo": {"appleId": account}, "hsaTrustedBrowser": trusted}


def test_accept_trusted_matching_account():
    session = session_from_response(URL, 200, {"dsWebAuthToken": "synthetic-token"}, response(), ACCOUNT.upper())
    assert session.account == ACCOUNT
    assert session.token == "synthetic-token"
    assert "synthetic-token" not in repr(session)


@pytest.mark.parametrize("url,status,data", [
    (URL.replace("https:", "http:"), 200, response()),
    (URL.replace("setup.icloud.com", "setup.icloud.com.attacker.invalid"), 200, response()),
    (URL, 401, response()),
    (URL, 200, response(trusted=False)),
    (URL, 200, {}),
])
def test_reject_untrusted_responses(url, status, data):
    assert session_from_response(url, status, {"dsWebAuthToken": "synthetic"}, data, ACCOUNT) is None


def test_wrong_account_is_rejected():
    with pytest.raises(AppError, match="different account"):
        session_from_response(URL, 200, {"dsWebAuthToken": "synthetic"}, response("other@example.invalid"), ACCOUNT)


class Session:
    def __init__(self):
        from requests.cookies import RequestsCookieJar
        self.data = {"session_token": "synthetic"}
        self.cookies = RequestsCookieJar()
        self.cleared = False

    def clear_persistence(self, remove_files=True):
        self.cleared = True
        self.data.clear()


class API:
    requires_2fa = False
    requires_2sa = False
    is_trusted_session = True
    notes = object()

    def __init__(self):
        self.data = response()
        self.session = Session()

    def authenticate(self):
        pass

    def logout(self):
        pass


@pytest.fixture
def fake_api(monkeypatch):
    import pyicloud
    api = API()
    def create(account, **kwargs):
        assert kwargs["authenticate"] is False
        assert "password" not in kwargs
        return api
    monkeypatch.setattr(pyicloud, "PyiCloudService", create)
    return api


def test_browser_login_and_logout_without_password(tmp_path, monkeypatch, fake_api):
    monkeypatch.setattr("notesvault.browser_auth.sign_in", lambda _: BrowserSession(ACCOUNT, "synthetic-browser-token"))
    provider = ICloudProvider(tmp_path)
    provider.login_browser(ACCOUNT)
    assert provider.connected
    assert fake_api.session.data["session_token"] == "synthetic-browser-token"
    provider.logout()
    assert not provider.connected
    assert not fake_api.session.data


def test_invalid_handoff_clears_persisted_session(tmp_path, monkeypatch, fake_api):
    monkeypatch.setattr("notesvault.browser_auth.sign_in", lambda _: BrowserSession(ACCOUNT, "synthetic"))
    fake_api.data = response("other@example.invalid")
    provider = ICloudProvider(tmp_path)
    with pytest.raises(AppError):
        provider.login_browser(ACCOUNT)
    assert not provider.connected
    assert not fake_api.session.data


def test_restore_expired_session_and_disconnect(tmp_path, fake_api):
    fake_api.requires_2fa = True
    provider = ICloudProvider(tmp_path)
    assert not provider.restore_session(ACCOUNT)
    assert not provider.connected
    provider.logout()
    assert fake_api.session.cleared


def test_restore_valid_browser_session(tmp_path, fake_api):
    provider = ICloudProvider(tmp_path)
    assert provider.restore_session(ACCOUNT)
    assert provider.connected


@pytest.mark.parametrize("size", [(100, 45), (80, 24)])
async def test_browser_button_connects_without_reading_password(tmp_path, size):
    from textual.widgets import Button, Input
    from notesvault.app import NotesVaultApp
    from notesvault.config import ConfigStore
    class Secrets:
        def get(self, key):
            raise AssertionError("Browser login must not read passwords")
        def set(self, key, value):
            raise AssertionError("Browser login must not save passwords")
        def delete(self, key):
            pass
    class Provider:
        connected = False
        def login_browser(self, account):
            assert account == ACCOUNT
            self.connected = True
    app = NotesVaultApp(ConfigStore(tmp_path), secrets=Secrets())
    app.provider = Provider()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        app.screen.query_one("#apple-id", Input).value = ACCOUNT
        app.screen.query_one("#folder", Input).value = str(tmp_path / "backup")
        app.screen.query_one("#browser-login", Button).scroll_visible(animate=False)
        await pilot.pause()
        assert await pilot.click("#browser-login")
        await app.workers.wait_for_complete()
        assert app.provider.connected
        assert app.settings.auth_method == "browser"
        assert app.store.load().auth_method == "browser"
        assert not app.busy


@pytest.mark.parametrize("missing", ["apple-id", "folder", "interval"])
async def test_browser_button_reveals_validation_error(tmp_path, missing):
    from textual.widgets import Button, Input, Static
    from notesvault.app import NotesVaultApp, SetupScreen
    from notesvault.config import ConfigStore

    app = NotesVaultApp(ConfigStore(tmp_path))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        screen.query_one("#apple-id", Input).value = ACCOUNT
        screen.query_one("#folder", Input).value = str(tmp_path / "backup")
        screen.query_one(f"#{missing}", Input).value = ""
        screen.query_one("#browser-login", Button).scroll_visible(animate=False)
        await pilot.pause()
        assert await pilot.click("#browser-login")
        await pilot.pause()
        assert isinstance(app.screen, SetupScreen)
        error = screen.query_one("#form-error", Static)
        viewport = screen.query_one("#setup-dialog").scrollable_content_region
        assert error.region.height > 0
        assert viewport.contains_region(error.region)
        assert not app.busy
        assert not app.store.path.exists()


@pytest.mark.parametrize("mode", ["success", "closed", "timeout"])
def test_browser_lifecycle(monkeypatch, mode):
    from notesvault.browser_auth import sign_in
    playwright_api = pytest.importorskip("playwright.sync_api")
    class Page:
        def on(self, name, callback):
            self.callback = callback
        def goto(self, url, **kwargs):
            assert url == "https://www.icloud.com/"
            if mode == "success":
                self.callback(SimpleNamespace(url=URL, status=200,
                    request=SimpleNamespace(post_data_json={"dsWebAuthToken": "synthetic"}),
                    json=lambda: response()))
        def is_closed(self):
            return mode == "closed"
        def wait_for_timeout(self, delay):
            raise AssertionError("Timeout must be detected")
    class Context:
        def new_page(self):
            return Page()
        def cookies(self):
            return [{"domain": ".icloud.com"}, {"domain": "attacker.invalid"}]
    class Browser:
        closed = False
        def new_context(self):
            return Context()
        def close(self):
            self.closed = True
        def is_connected(self):
            return True
    browser = Browser()
    class Playwright:
        def __enter__(self):
            return SimpleNamespace(chromium=SimpleNamespace(launch=lambda **kwargs: browser))
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(playwright_api, "sync_playwright", Playwright)
    if mode == "success":
        session = sign_in(ACCOUNT)
        assert session.cookies == [{"domain": ".icloud.com"}]
    else:
        with pytest.raises(AppError, match="cancelled" if mode == "closed" else "timed out"):
            sign_in(ACCOUNT, timeout=-1)
    assert browser.closed


async def test_browser_reconnect_without_opening_browser(tmp_path):
    from notesvault.app import NotesVaultApp
    from notesvault.config import ConfigStore, Settings
    class Secrets:
        def get(self, key):
            raise AssertionError("Browser reconnect must not read passwords")
    class Provider:
        connected = False
        def restore_session(self, account):
            assert account == ACCOUNT
            self.connected = True
            return True
    store = ConfigStore(tmp_path)
    store.save(Settings(apple_id=ACCOUNT, auth_method="browser", backup_folder=str(tmp_path / "backup")))
    app = NotesVaultApp(store, secrets=Secrets())
    app.provider = Provider()
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        assert app.provider.connected
        assert app.next_fetch is not None
