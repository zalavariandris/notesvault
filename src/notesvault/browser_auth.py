"""Experimental iCloud web-session handoff from an isolated browser context."""
from dataclasses import dataclass, field
from time import monotonic
from urllib.parse import urlparse

from .models import AppError


@dataclass(repr=False)
class BrowserSession:
    account: str
    token: str
    country: str = ""
    trust_token: str = ""
    cookies: list[dict] = field(default_factory=list)


def session_from_response(url, status, request, response, account):
    """Accept only a successful, trusted Apple setup response for this account."""
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname != "setup.icloud.com"
            or parsed.path != "/setup/ws/1/accountLogin" or status != 200):
        return None
    if not isinstance(request, dict) or not isinstance(response, dict):
        return None
    info = response.get("dsInfo")
    if not isinstance(info, dict) or response.get("hsaTrustedBrowser") is not True:
        return None
    signed_in = info.get("appleId", "")
    if not isinstance(signed_in, str) or signed_in.strip().lower() != account.strip().lower():
        raise AppError("The browser signed in to a different account. Retry with the Apple Account entered in Settings.")
    token = request.get("dsWebAuthToken")
    if not isinstance(token, str) or not token:
        return None
    return BrowserSession(account.strip().lower(), token,
        request.get("accountCountryCode", ""), request.get("trustToken", ""))


def sign_in(account: str, timeout: float = 300) -> BrowserSession:
    try:
        from playwright.sync_api import sync_playwright, Error
    except ImportError:
        raise AppError("Browser sign-in needs Playwright. Run uv sync --extra dev --extra browser; see README.md.") from None
    try:
        with sync_playwright() as playwright:
            browser = None
            for channel in ("msedge", "chrome", None):
                try:
                    browser = playwright.chromium.launch(headless=False, channel=channel)
                    break
                except Error:
                    continue
            if browser is None:
                raise AppError("No supported browser could launch. Install Edge or Chrome, or run python -m playwright install chromium.")
            try:
                context = browser.new_context()
                page = context.new_page()
                result = None
                failure = None

                def receive(response):
                    nonlocal result, failure
                    parsed = urlparse(response.url)
                    if (parsed.scheme != "https" or parsed.hostname != "setup.icloud.com"
                            or parsed.path != "/setup/ws/1/accountLogin" or response.status != 200):
                        return
                    try:
                        candidate = session_from_response(response.url, response.status,
                            response.request.post_data_json, response.json(), account)
                        if candidate:
                            result = candidate
                    except AppError as exc:
                        failure = exc
                    except (ValueError, Error):
                        pass

                page.on("response", receive)
                page.goto("https://www.icloud.com/", wait_until="domcontentloaded", timeout=60000)
                deadline = monotonic() + timeout
                while result is None and failure is None:
                    if page.is_closed() or not browser.is_connected():
                        raise AppError("Browser sign-in cancelled. You can retry in Settings.")
                    if monotonic() >= deadline:
                        raise AppError("Browser sign-in timed out. Retry and complete sign-in and Trust this browser within five minutes.")
                    page.wait_for_timeout(200)
                if failure:
                    raise failure
                result.cookies = [cookie for cookie in context.cookies()
                    if cookie["domain"].lstrip(".") == "icloud.com"
                    or cookie["domain"].lstrip(".").endswith(".icloud.com")]
                return result
            finally:
                browser.close()
    except AppError:
        raise
    except Exception:
        raise AppError("Browser sign-in did not complete. Retry in Settings; keep the browser open until sign-in finishes.") from None
