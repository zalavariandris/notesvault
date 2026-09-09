# Apple Notes Vault

A Python terminal dashboard that exports iCloud Notes to a local Git repository.
GitHub publishing is optional. The app never edits your notes in iCloud.

## Run

Requires Python 3.12+ and Git on PATH. From this project folder:

```powershell
uv venv
uv pip install -e ".[dev]"
.venv\Scripts\notes-vault.exe
```

Try the dashboard without an account:

```powershell
.venv\Scripts\notes-vault.exe --demo
```

Demo notes and Git history live in a temporary folder removed when the app exits.
`--demo --once` exercises a complete local backup without the UI or credentials.
`--check` verifies runtime imports and Git availability without accessing an account.

## Use

1. Open **Settings** (`s`), enter your Apple Account and password, and choose a
   separate backup folder. Credentials are saved in the OS credential store.
2. Leave GitHub empty for local backups, or supply `owner/repository` and a
   fine-grained token with repository Contents read/write access to a private repo.
   Use an empty remote initially; conflicting remote history requires manual reconciliation.
3. Complete Apple's verification-code prompt, then select **Fetch now** (`f`).
4. Review note counts, local commit status, and optional push status. **Retry push**
   publishes an existing backup without downloading notes again. Quit with `q`.

Automatic fetching runs only while the terminal app is open. Set the interval to
0 for manual backups. For an external scheduler, use `notes-vault --once`
after connecting in the dashboard; expired sessions require interactive reconnection.

## Export and recovery

Notes are saved as readable `.md` text with `.json` metadata under `notes/`.
Original downloadable attachments are stored under `attachments/` and linked from
the note. Filenames include a stable hash of the iCloud ID. Folder names and IDs
are retained, but nested folder hierarchy is flattened in this version.

Each changed backup creates a local Git commit. Unchanged backups create no commit.
Deleted files remain in earlier commits; use `git log --all -- notes` to browse
history, then `git show <commit>:<path>` to read an earlier version. Export recovered
content outside the managed backup before the next fetch.

Local edits, staged changes, and incomplete exports block destructive replacement.
Skipped notes retain their previous backups and defer all deletions. Downloads
finish in temporary staging before local files change. GitHub push failures do not
undo local commits; pushes never force overwrite remote history.

## Current limitations

- Uses [PyiCloud 2.7.0](https://github.com/timlaing/pyicloud#notes), an unofficial
  integration with iCloud web services. Live account access needs verification on
  your account; Apple may change these interfaces.
- Plain text and available original attachments are exported; rich formatting,
  drawings, tables, and other embedded objects are not guaranteed to round-trip.
- Locked notes and attachments without an original download URL are skipped.
  The provider scans the library's Notes zone; separate shared zones, on-device
  notes, and notes in other accounts are not discovered.
- Code-based 2FA is supported. Hardware security keys and legacy two-step
  authentication are not yet implemented. Accept Apple terms in iCloud itself.
- Deletions require an uninterrupted full scan with an unchanged source cursor.
  A changing library requires retrying the fetch.
- Git must be installed separately. Windows is the initial target.

## Configuration and development

Settings and iCloud sessions live in the per-user `NotesVault` data directory
(on Windows, normally `%LOCALAPPDATA%\NotesVault`). Sessions contain sensitive
authentication data and are never stored in the backup repository. `--data-dir`
overrides this location. Passwords and tokens use OS credential storage, never
plaintext keyring fallbacks. Logout clears the app's saved credential/session.

`.env` is optional and ignored by Git. It supplies initial Apple Account, local
folder, and optional GitHub repository defaults; use the UI for secrets.

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m build --wheel --no-isolation
```

Create a standalone Windows console executable on Windows:

```powershell
uv pip install -e ".[exe]"
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm notes-vault.spec
```

Output: `dist/notes-vault.exe`. Keep this a console executable: the UI runs
inside a terminal. The executable still requires Git on PATH.
