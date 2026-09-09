import base64
import os
import re
import subprocess

import requests

from .backup import git
from .models import AppError


def validate_repository(repo: str, token: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise AppError("Enter a GitHub repository as owner/name.")
    if not token or any(c in token for c in "\r\n"):
        raise AppError("Enter a valid GitHub token with access to the selected repository.")
    try:
        response = requests.get(f"https://api.github.com/repos/{repo}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            timeout=30, allow_redirects=False)
        if response.status_code != 200:
            raise AppError("Could not access that GitHub repository. Check its name and token permissions.")
        data = response.json()
        if data.get("private") is not True:
            raise AppError("The GitHub repository must be private before notes can be published.")
        if data.get("permissions", {}).get("push") is not True:
            raise AppError("The GitHub token needs write access to repository contents.")
        branch = data.get("default_branch", "main")
        if not isinstance(branch, str) or not branch:
            raise AppError("GitHub did not return a destination branch.")
        return branch
    except (requests.RequestException, ValueError) as exc:
        raise AppError("GitHub is unavailable. Check your connection and retry.") from exc


def push_repository(root, repo: str, token: str) -> str:
    branch = validate_repository(repo, token)  # Recheck privacy on every push.
    if git(root, "check-ref-format", f"refs/heads/{branch}", check=False).returncode:
        raise AppError("GitHub returned an invalid destination branch.")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    credential = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    # Keep tokens out of URLs, arguments, config files, and command output.
    env.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_COUNT="3",
        GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
        GIT_CONFIG_VALUE_0=f"AUTHORIZATION: basic {credential}",
        GIT_CONFIG_KEY_1="credential.helper", GIT_CONFIG_VALUE_1="",
        GIT_CONFIG_KEY_2="http.followRedirects", GIT_CONFIG_VALUE_2="false")
    try:
        result = subprocess.run(["git", "-c", "core.hooksPath=", "-C", str(root), "push",
            f"https://github.com/{repo}.git", f"HEAD:refs/heads/{branch}"],
            env=env, capture_output=True, timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AppError("Local backup saved; GitHub push could not finish. Retry publishing.") from exc
    if result.returncode:
        raise AppError("Local backup saved; push failed. Check token access or reconcile remote history, then retry. No force-push was attempted.")
    return f"Published to {repo}"
