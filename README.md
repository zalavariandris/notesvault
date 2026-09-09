# Notes Vault

A PyEdifice desktop GUI that backs up iCloud Notes to a local Git repository.
Publishing to a private GitHub repository is optional. iCloud notes are never modified.

See [todo.md](todo.md) for planned work and [changelog.md](changelog.md) for changes.

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
Demo backups are temporary and removed on exit. PyEdifice uses PySide6/Qt;
`uv sync --extra dev` installs the desktop dependencies.

## Build a Windows executable

Run on Windows:

```powershell
uv sync --extra dev --extra exe
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm notesvault.spec
```

Output: `dist\notesvault.exe`. Git must still be on PATH. The dashboard opens in a separate native Qt window.

## Use

1. Open the dashboard and select **Login** in the iCloud card. Saved credentials
   are used automatically; otherwise an in-app form asks for your Apple Account
   email and password. Complete verification in the GUI when required.
2. Select **Fetch iCloud now** in the Disk card. If the backup folder is missing,
   choose it in the form or native folder picker. The backup resumes after setup;
   if iCloud is disconnected, sign-in is requested as well.
3. Optionally choose **Set up GitHub** and enter a private `owner/repository` plus
   a token with Contents read/write permission. **Publish to GitHub** retries a push.
4. Use Settings to change the folder or interval. Results and errors appear in Logs.
   Close the window to quit; active operations must finish first.

Automatic fetching runs while the GUI window is open; set the interval to `0` for manual
backups. Use `--once` with an external scheduler after connecting in the dashboard.
Expired sessions require reconnection.

## iCloud sign-in

Account setup uses PyEdifice forms inside the same window. Password and GitHub
token fields are masked; verification codes are visible. Passwords and tokens
are stored in the OS credential store only after successful verification.
**Cancel setup** returns to the dashboard and clears pending authentication.
Completed settings are retained. **Disconnect iCloud** removes the saved password
and local session, pauses fetching, and preserves backups.

There are no terminal prompts. `--demo`, `--check`, and `--once` remain available;
`--once` requires saved credentials and reports when interactive reconnection is needed.

## Backups and limitations

- Exports text and YAML metadata frontmatter to `notes/*.md`, and downloadable attachments to
  `attachments/`. Filenames include stable ID hashes; folder hierarchy is flattened.
  Existing managed JSON sidecars are removed when their notes are re-exported;
  earlier versions remain in Git history. The internal backup manifest stays JSON.
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

## Download caching

If the iCloud sync cursor is unchanged since the last complete local backup,
existing exports are reused without downloading. Local edits and Git state are
still checked. Changed cursors trigger a full fetch. The disposable cache in
`.git/notesvault-fetch.json` is updated only after the local backup succeeds;
missing or invalid caches and export-format changes trigger a full fetch.
