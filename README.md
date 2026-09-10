# Notes Vault

A PyEdifice desktop GUI that backs up iCloud Notes to a local Git repository.
Backups stay on your disk with local Git history. iCloud notes are never modified.

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
Rich is also installed because PyiCloud 2.7.0 imports it in its Notes renderer.

The dashboard owns local hook state and groups actions around authentication, disk
configuration, and fetching. Reusable account, backup, Tasks, and Logs cards receive
display props and callbacks; shared visual components keep their styling consistent.
A separate sign-in popup hosts the reusable authentication form. `TaskManager` runs one background operation at a time; its UI hook
delivers progress/results and shows the operation in Tasks. Authentication, disk/Git
management, and backup orchestration have separate controllers. Run logic tests with
`.venv/Scripts/python.exe -m pytest` and use synthetic desktop smoke checks for UI changes.
The app does not use terminal authentication prompts.

Providers retrieve notes and convert their formatting; `provider_utils.py` builds
export bytes without writing Markdown files. `BackupController` owns the fetch/save
sequence and optional download lifetime; `FetchCache` validates and persists cursors.
`DiskVaultController` separates existing-backup validation, snapshot planning, and
local file/Git writes. Authentication, dashboard state, and task lifecycle remain
separate from these operations.

## Build a Windows executable

Run on Windows:

```powershell
uv sync --extra dev --extra exe
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm notesvault.spec
```

Output: `dist\notesvault.exe`. Git must still be on PATH. The dashboard opens in a separate native Qt window.

## Use

The window opens tall, with one scrolling column that also fits narrower windows.

1. Open the dashboard and select **Login** in the iCloud card. Saved credentials
   are tried first; a focused popup opens when your Apple Account email, password,
   or verification code is needed.
2. Select **Fetch now** in the Backup card. If the backup folder is missing,
   choose it in the Backup card or native folder picker. The backup resumes after setup;
   if iCloud is disconnected, sign-in is requested as well.
3. Change the folder or interval in the Backup card. Edits save automatically after
   a short typing pause; a status line shows pending/saved preferences. Invalid
   values leave the saved settings intact.
   **Download attachments** is off by default and saves automatically too. Enabling
   it downloads available originals; disabling it removes managed attachment files
   on re-export while preserving earlier downloads in Git history.
4. Tasks shows the current operation, latest progress, an activity indicator, and
   the last backup result. Fetch failures offer **Retry fetch**. Logs retains the
   latest 200 timestamped messages, newest first. Search activity, select text,
   **Copy logs**, or **Clear logs**; clearing the viewer preserves the last result.
   Use **Pause fetch**, **Resume fetch**, or **Cancel fetch** in Tasks to control a download.
   Closing during a fetch cancels it and closes the window automatically after cleanup.

Pause and cancellation take effect between requests and attachment chunks; a request
already in progress must return first. Pause retains the current download so Resume
can continue it while the window stays open. Cancel discards the unfinished fetch,
preserving existing exports, Git history, the download cache, and the last result.
You can start another fetch afterward; automatic fetching resumes at the next interval.
Once the local save starts, Pause and Cancel are disabled so Git writes can finish
safely. A close request waits for that save, then closes automatically. Other active
operations, such as sign-in and settings saves, must finish before closing.

Automatic fetching runs while the GUI window is open; set the interval to `0` for manual
backups. Use `--once` with an external scheduler after connecting in the dashboard.
Expired sessions require reconnection.

## iCloud sign-in

Account setup uses a separate popup with sign-in and verification steps. Errors
appear beside the form; Enter in the password or code field submits it. Password
fields are masked; verification codes are visible. Passwords are stored in the OS
credential store only after successful verification.
**Cancel setup**, Escape, or closing the popup returns to the dashboard and clears
pending authentication. A request already in progress must finish before the popup
can close. Configuration edits and scheduled fetches pause while sign-in is open.
Successful sign-in closes the popup and resumes any pending fetch. Expired sessions
are checked again before starting a fetch and routed through reconnection.
Completed settings are retained. **Disconnect iCloud** removes the saved password
and local session, pauses fetching, and preserves backups.

There are no terminal prompts. `--demo`, `--check`, and `--once` remain available;
`--once` requires saved credentials and reports when interactive reconnection is needed.

## Backups and limitations

- Exports Markdown and YAML metadata frontmatter to `notes/<folder>/*.md`, and
  optional downloadable attachments to `attachments/`. Note names use
  `YYYY-MM-DD-<TITLE>-[<ID>].md`: UTC modification date, a safe title, and a stable
  ID hash. Missing/invalid dates use `0000-00-00`; naive timestamps are treated as
  UTC. Folder names include stable hashes; nested folder hierarchy is flattened.
  Existing managed JSON sidecars are removed when their notes are re-exported;
  earlier versions remain in Git history. The internal backup manifest stays JSON.
- Changes are committed locally. Local edits and incomplete fetches block destructive
  replacement; skipped notes defer deletions.
- Browse earlier versions with `git log --all -- notes` and
  `git show <commit>:<path>`. Restore files outside the managed backup folder.
- Preserves headings, emphasis, lists/checklists, links, quotes, code, and basic
  tables where PyiCloud supplies rendered content. Underline, superscript, and
  subscript use inline HTML. Complex layouts and merged table cells may lose
  fidelity; unsupported wrappers retain readable text. Media become placeholders
  with separate local attachment links when downloads are enabled. Missing rendered
  content falls back to plain text with a warning.
- Uses unofficial PyiCloud 2.7.0; live-account verification remains open. Locked
  notes, separate shared zones, and on-device notes are unsupported. The adapter
  reports limited zone coverage, retains unconfirmed absences, and applies only
  explicit deletion records from complete successful fetches. Skipped content
  defers all deletions and cursor advancement.
  Code-based 2FA is supported; hardware security keys and legacy two-step auth are not.

Settings and sessions use the per-user `NotesVault` data directory (`--data-dir`
overrides it). Passwords use OS credential storage. Optional `.env`
defaults must not contain secrets or be committed.

`settings.json` stores the account email, backup folder, and fetch interval.
It also stores the `download_attachments` preference, defaulting to `false`.
The last backup timestamp and result are stored separately in `backup-status.json`.
Existing results are read from the old settings file and preserved automatically
before the next settings save. Backup files and Git history need no migration.

GitHub publishing has been removed. Existing settings still load; retired GitHub
options disappear on the next save. Local backups and Git history are preserved.
Any previously saved GitHub token remains unused in the OS credential store and
can be removed there. Existing Git remotes are left untouched.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest
```

Tests cover application workflows, authentication, settings, retrieval, exports,
and local Git recovery without Qt widgets. Use `--demo` for a desktop smoke check.

## Download caching

If the iCloud sync cursor is unchanged since the last complete local backup,
existing exports are reused without downloading. Local edits and Git state are
still checked. Changed cursors download changed/new notes and retain unchanged
exports. Folder changes refresh all note metadata and paths. Expired cursors and
providers without change-feed support fall back to a full scan. The disposable cache in
`.git/notesvault-fetch.json` is updated only after the local backup succeeds;
missing or invalid caches, export-format changes, and attachment-option changes
trigger a full fetch. A cursor changing during retrieval aborts that fetch safely.
The internal `EXPORT_VERSION` in `src/notesvault/provider_utils.py` must be
incremented when export content or supported content changes, so unchanged iCloud
notes are re-exported using the updated format.

## Direct writes and interrupted-save recovery

Markdown is buffered in memory until retrieval succeeds and cancellation is
disabled, then written directly to its final vault paths. No temporary Markdown
exports are created. Retained rendered bytes are limited to 64 MiB per fetch;
exceeding that limit aborts without changing backups. PyiCloud's transient response
memory is separate from this limit. Optional attachments stream to temporary files
inside the vault's `.git` directory and are cleaned up on ordinary completion or
cancellation. Pause retains the buffer and downloads in the current process.

Before changing managed files, the app saves recovery copies and a journal at
`.git/notesvault-save.json`. Ordinary failures restore files and the affected Git
index entries. An interrupted process or failed restoration leaves the journal and
copies intact and blocks further fetches. Recovery is manual to avoid overwriting
edits made after an interruption:

1. Close the app and copy the entire vault, including `.git`, to a safe location.
2. Inspect the journal's `head`, `rollback`, and `before` entries and compare Git
   history and status. `before` maps managed paths to recovery-copy filenames;
   a null entry means the file did not exist before the interrupted save.
3. If the backup commit succeeded, verify its managed files and manifest match
   the working tree. Otherwise restore only the journal's affected paths from
   the recovery copies (or the recorded commit), preserving any later user edits
   separately. Restore those paths' index entries to the recorded commit; for an
   initial backup with no recorded commit, remove only those entries from the index.
   Do not reset unrelated files or the whole working tree.
4. After verifying the recovered files, manifest, and index, remove the journal
   and its referenced rollback directory. The next fetch can then proceed.

The current filename/storage changes target an empty vault; no old-vault migration
is required. Subsequent backups still preserve earlier committed versions.
