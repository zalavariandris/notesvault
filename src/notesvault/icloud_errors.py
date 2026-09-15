"""Translate provider failures without exposing response bodies or credentials."""
from pyicloud import exceptions as cloud
from pyicloud.services.notes.client import NotesAuthError, NotesRateLimited
from requests.exceptions import ConnectionError, Timeout

from .models import AppError


class ReconnectRequired(AppError):
    """The active iCloud session can no longer fetch notes."""


class TermsAcceptanceRequired(AppError):
    """Apple requires an account action before another sign-in can succeed."""


def authentication_required(exc):
    if isinstance(exc, (NotesAuthError, cloud.PyiCloudFailedLoginException,
                        cloud.PyiCloudAuthRequiredException, cloud.PyiCloud2FARequiredException,
                        cloud.PyiCloud2SARequiredException, cloud.TokenException)):
        return True
    response = getattr(exc, "response", None)
    return (str(getattr(exc, "code", "")) in {"401", "421", "450", "AUTHENTICATION_FAILED"}
            or getattr(response, "status_code", None) in {401, 421, 450})


def login_error(exc):
    if isinstance(exc, cloud.PyiCloudAcceptTermsException):
        return TermsAcceptanceRequired(
            "Apple reports that updated iCloud terms need your acceptance. "
            "Open https://www.icloud.com in a browser, sign in with the same Apple Account, "
            "and review the updated terms. After accepting them, return here and sign in again.")
    if isinstance(exc, cloud.PyiCloudServiceNotActivatedException):
        return AppError("Enable iCloud Notes and access Notes at iCloud.com, then try again.")
    if isinstance(exc, (ConnectionError, Timeout)):
        return AppError("Could not reach iCloud. Check your internet connection and try again.")
    if isinstance(exc, (NotesRateLimited, cloud.PyiCloudServiceUnavailable)):
        return AppError("iCloud is temporarily unavailable or limiting requests. Wait a few minutes, then try again.")
    if authentication_required(exc) or isinstance(exc, cloud.PyiCloudPasswordException):
        return AppError("iCloud did not accept the sign-in. Check your Apple Account email and password, then try again.")
    return AppError("Could not sign in to iCloud. Check your connection and account access at iCloud.com, then try again.")
