# Notes Vault

A terminal dashboard that backs up iCloud Notes to a local Git repository.
Publishing to a private GitHub repository is optional. iCloud notes are never modified.

## Development setup

Requires Python 3.12+, uv, and Git on PATH. In the project folder, run:

```powershell
uv sync --extra dev
```

This creates `.venv` and installs the package in editable mode with development
 dependencies. Rerun after moving or renaming the project folder.

## Run

From the project folder:

```powershell
.venv\Scripts\python.exe -m notesvault
```

Or launch through the script:

```powershell
.venv\Scripts\python.exe launcher.py
```

With `.venv` activated, the equivalent commands are `python -m notesvault`,
`python launcher.py`, or `notesvault`. In your IDE, select `.venv\Scripts\python.exe`.

Add `--demo` to try synthetic notes without an account, `--demo --once` to test a
single backup, or `--check` to verify runtime imports, Git, and credential storage.
Demo backups are temporary and removed on exit.

## Build a Windows executable

Run on Windows:

```powershell
uv sync --extra dev --extra exe --extra browser
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm notesvault.spec
```

Output: `dist\notesvault.exe`. Run it in a terminal; Git must still be on PATH.

## Use

1. Open **Settings** (`s`), connect your Apple Account, complete 2FA, and choose a
   backup folder separate from this source repository.
2. Optionally enter a private GitHub `owner/repository` and a token with repository
   Contents read/write permission. Start with an empty remote.
3. Select **Fetch now** (`f`). Review the result and use **Retry push** if needed.
   Quit with `q`.

Automatic fetching runs while the app is open; set the interval to `0` for manual
backups. Use `--once` with an external scheduler after connecting in the dashboard.
Expired sessions require reconnection.

## Browser sign-in (experimental)

```powershell
uv sync --extra dev --extra browser
```

Install Microsoft Edge or Google Chrome, or run
`.venv\Scripts\python.exe -m playwright install chromium`.
In **Settings**, enter your Apple Account email and backup folder, then choose
**Save & sign in via browser**. Complete login and 2FA on iCloud.com and choose
**Trust**. Close the browser to cancel; sign-in expires after five minutes.

The app opens a separate browser session, without using your existing browser
profile. It saves the iCloud session for reconnecting and `--once`, without saving
your Apple password. Disconnect clears the app's saved session. Expired sessions
require browser sign-in again. This unofficial session handoff needs live-account
verification; password sign-in remains available. China mainland endpoints are
not supported by this browser flow. Executable users also need Edge or Chrome.

## Backups and limitations

- Exports text to `notes/*.md`, metadata to JSON, and downloadable attachments to
  `attachments/`. Filenames include stable ID hashes; folder hierarchy is flattened.
- Changes are committed locally. Local edits and incomplete fetches block destructive
  replacement; skipped notes defer deletions. Push failures preserve local backups.
- Browse earlier versions with `git log --all -- notes` and
  `git show <commit>:<path>`. Restore files outside the managed backup folder.
- Uses unofficial PyiCloud 2.7.0; live-account verification remains open. Rich formatting,
  locked notes, separate shared zones, and on-device notes are not fully supported.
  Code-based 2FA is supported; hardware security keys and legacy two-step auth are not.

Settings and sessions use the per-user `NotesVault` data directory (`--data-dir`
overrides it). Passwords and tokens use OS credential storage. Optional `.env`
defaults must not contain secrets or be committed.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest
```
