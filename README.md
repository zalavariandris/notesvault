# Notes Vault

A PyEdifice desktop GUI and interactive command line that back up iCloud Notes to a local Git repository.
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
.venv\Scripts\python.exe launcher_gui.py
```

With `.venv` activated, the equivalent commands are `python -m notesvault`,
`python launcher_gui.py`, or `notesvault`. In your IDE, select `.venv\Scripts\python.exe`.

Add `--once` for one backup using saved settings, or `--check` to verify runtime
imports, Git, and credential storage. PyEdifice uses PySide6/Qt;
`uv sync --extra dev` installs the desktop dependencies.
Rich provides plain terminal prompts and PyiCloud's Notes renderer.

The dashboard owns local hook state and groups actions around authentication, disk
configuration, and fetching. Reusable account, backup, Tasks, and Logs cards receive
display props and callbacks; shared visual components keep their styling consistent.
A separate sign-in popup hosts the reusable authentication form. `TaskManager` runs one background operation at a time; its UI hook
delivers progress/results and shows the operation in Tasks. Authentication, disk/Git
management, and backup orchestration have separate controllers. Run logic tests with
`.venv/Scripts/python.exe -m pytest` and use synthetic desktop smoke checks for UI changes.
The default desktop app does not use terminal authentication prompts.
`application.py` shares configuration validation, fetch prerequisites, and provider
selection between desktop and terminal adapters. The command line imports no Qt modules;
both interfaces reuse the authentication, backup, disk, and task controllers.
One-shot backups also use the shared application service. The entry point handles
startup and mode routing. Both interfaces create the same `Application`, which loads
settings from the default per-user location. `cli()` parses arguments and passes
the selected mode to the typed `main(mode)` function. Functions in `__main__.py` implement
`--once` backups for external schedulers and `--check` installation diagnostics.
`--check` identifies the failing dependency check; local file-access errors produce
a safe message and a nonzero exit status.

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
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm notesvault-gui.spec
```

Output: `dist\notesvault-gui.exe`. Git must still be on PATH. The dashboard opens in a separate native Qt window.

Build the terminal executable with [notesvault-tui.spec](notesvault-tui.spec):

```powershell
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm notesvault-tui.spec
```

Output: `dist\notesvault-tui.exe`. It opens the interactive command line by default, with no
`--tui` flag required. `launcher_tui.py` provides the same default when run from source.
Git must be on PATH. `--once` and `--check` remain available. Both executables
use the same settings and credential store; run one interface at a time.

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

The desktop has no terminal prompts. `--check` and `--once` remain available;
`--once` requires saved credentials and reports when interactive reconnection is needed.

If sign-in reports updated iCloud terms, open [iCloud.com](https://www.icloud.com)
in a browser with the same Apple Account and review the terms Apple presents.
After accepting them, return to Notes Vault and retry Login (answer **yes** at the
command line's retry prompt). The command line pauses sign-in instead of repeatedly requesting your password; scheduling
stays paused while disconnected. Notes Vault does not accept terms automatically.
This requirement comes from PyiCloud's handling of Apple's `termsUpdateNeeded`
response; see the [PyiCloud authentication documentation](https://pypi.org/project/pyicloud/2.7.0/).
If browser Notes already works and the app still reports terms, report that result
before removing settings or sessions so the remaining cause can be investigated.

## Interactive command line

Run in an interactive terminal:

```powershell
.venv\Scripts\python.exe launcher_tui.py
# Equivalent through the package entry point:
.venv\Scripts\python.exe -m notesvault --tui
```

The existing launcher and `--tui` flag now open a plain command-line conversation.
On launch it prepares the saved backup folder or asks you to choose one, then
tries saved credentials automatically. If needed, it asks for your Apple Account
email, a hidden password, and a verification code. Folder setup is saved even if
sign-in is cancelled or fails.

It prints the backup directory, number of managed notes currently on disk, last
backup result, and automatic-fetch interval, then asks **Fetch now? [y/N/q]**.
Type **yes** and press Enter to fetch, **no** (or Enter) to wait, **settings** to
change the folder/interval/attachment preference, or **quit** to exit.
Only managed notes with a Markdown file still present are counted; unrelated
Markdown files and attachments are excluded. An unreadable manifest reports an
unavailable count instead of zero.

A countdown on the prompt line shows the time until the next automatic fetch.
Fetching starts when the timer expires, even if you have not answered the prompt.
Answering no keeps the current deadline. Each completed fetch attempt starts the
next interval; interval `0` disables automatic fetching. Settings and sign-in
prompts pause scheduling. Use one interface at a time with the shared settings.

Progress and results print as ordinary lines and remain in terminal history.
There are no dashboard panels or hotkey controls. **Ctrl+C** exits; during a fetch
it first requests cancellation and waits for the current request or an already
started local Git save to finish. Expired sessions prompt for reconnection after
worker cleanup. Failed or cancelled sign-in leaves automatic fetching paused;
network failures allow another fetch attempt.

`notesvault-tui.exe` opens this same command line. `--once` and `--check` remain
noninteractive; redirected terminal input/output is rejected with guidance to use
`--once`. No settings or backup migration is required for this interface change.
The previous dashboard design in [INTERFACE_PLAN.md](INTERFACE_PLAN.md) is historical.

## Backups and limitations

- Exports Markdown and YAML metadata frontmatter to `notes/<folder>/*.md`, and
  optional downloadable attachments to `attachments/`. Note names use
  `YYYY-MM-DD-<TITLE>-[<ID>].md`: UTC modification date, a safe title, and a stable
  ID hash. Missing/invalid dates use `0000-00-00`; naive timestamps are treated as
  UTC. Folder names include stable hashes; nested folder hierarchy is flattened.
  Existing managed JSON sidecars are removed when their notes are re-exported;
  earlier versions remain in Git history. The internal backup manifest stays JSON.
  Frontmatter uses readable UTF-8 characters (for example, `Éttermek`) while
  escaping quotes and newlines. The next fetch refreshes cached exports to apply
  this format automatically; earlier versions remain in local Git history.
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

Both interfaces and `--once` use the default per-user `NotesVault` data directory
(`%LOCALAPPDATA%\NotesVault` on Windows). Passwords use OS credential storage.
Configure the account and backup
folder in the GUI or command line; `.env`, `ICLOUD_APPLE_ID`, and `LOCAL_EXPORT_DIR` are no
longer read. Existing saved settings continue to work.

`--data-dir` is no longer supported. If you previously used a custom settings
directory, close the app and copy its `settings.json`, `backup-status.json`, and
`sessions` folder into the default location, preserving any existing settings first.
The backup repository stays at the path stored in `settings.json`.

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
and local Git recovery without Qt widgets.
Run `.venv/Scripts/python.exe scripts/smoke_desktop.py` for the opt-in synthetic,
offscreen popup check, separate from pytest. It uses no real account or OS secrets.

For manual testing from a source checkout, use the separate development launcher:

```powershell
.venv\Scripts\python.exe -m devtools.demo
.venv\Scripts\python.exe -m devtools.demo --tui
.venv\Scripts\python.exe -m devtools.demo --once
```

It supplies synthetic authentication and notes to the ordinary application and
removes its temporary settings and backups on exit. Login/logout and fetching use
the same interface paths as normal operation. The production app has no `--demo`
flag; development helpers are excluded from the installed package and executables.

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
