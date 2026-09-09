# TODO immediatelly:
- [x] make sure 'notesvault' naming is consistent everywhere.
- [x] create a setup.bat file


# Notes Vault

## Goal

Build a terminal app that backs up Apple Notes from iCloud
into a local Git repository. Publishing to a private GitHub repository is optional.
This is a one-way backup; two-way synchronization is outside the current scope.

## User flow

1. Connect iCloud, including two-factor authentication when required.
2. Choose a local backup folder; initialize Git if needed.
3. Connect a private GitHub repository or skip; setup remains available later.
4. Open the dashboard: account status, backup folder, last result, next scheduled
   fetch, and **Fetch now**. Returning users start here.
5. Show fetch progress, then added/updated/deleted/skipped counts, local commit
   status, and optional push status. Offer retries for failures.

Settings provide account login/logout and the automatic fetch interval.
Expired sessions require reconnection; iCloud logout pauses fetching without
removing backups. Prevent overlapping fetches.

## Backup rules

- Export all accessible notes into readable files; report unsupported or
  inaccessible content. Decide formatting, metadata, and attachment handling.
- Use safe, readable filenames and stable IDs where available, for example
  `<TITLE>_[<ID>].md`. Preserve IDs on rename; avoid duplicates and empty commits.
- Commit changed backups locally. Preserve earlier versions in Git history;
- Ensure existing exports are committed before replacement or removal. Apply
  deletions only after a complete, successful fetch confirms absence; errors or
  inaccessible notes must never imply deletion.
- Preserve user edits and unrelated files; commit only app-managed backup files.
  Keep the backup repository separate from this application's source repository.
- Verify GitHub destinations are private. Push failures must not undo local
  backups. Handle commit failures and conflicts without discarding data.

## Credentials

- Ignore `.env`; keep `.env.example` free of secrets. Never commit credentials
  or sessions to either repository. Prefer the OS credential store in the app.
- Keep real notes out of application source control, logs, screenshots, and tests.
  Use synthetic test data and minimal GitHub permissions.

## Development
- Python 3.12+, Textual dashboard, PyiCloud 2.7.0 Notes adapter, and system Git.
- Run `.venv/Scripts/python.exe -m pytest`; try `--demo` for synthetic data.
- See README.md for setup, exports, limitations, and Windows executable builds.
- On Windows, run `setup.bat` with uv and Git on PATH to install and check the app.
- Current exports preserve text, metadata, and downloadable attachments. Rich
  formatting, locked notes, and separate shared zones are not fully supported.
- Scheduling runs only while the terminal app is open; `--once` supports external schedulers.
- Separate authentication, retrieval, export, Git, publishing, and terminal UI.
- Test completeness, filenames, attachments, repeat backups, and failure recovery.
- Update this guide as decisions are made; document setup and installer commands.
- Open work: live-account verification, richer exports, shared/locked notes,
  other platforms, and an interactive Git history recovery screen.
