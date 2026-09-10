# Notes Vault

## Goal

Build a desktop app that backs up Apple Notes from iCloud
into a local Git repository. Backups stay local; publishing is not supported.
This is a one-way backup; two-way synchronization is outside the current scope.

## Agent workflow and project records

- At the start of each task, read this guide, [todo.md](todo.md), and
  [changelog.md](changelog.md) before making changes. Use README.md for current
  user-facing setup and behavior.
- Treat todo.md as the source of truth for outstanding work. Update relevant
  entries when scope, blockers, or completion changes; add concrete follow-up
  work discovered during a task. Do not implement unrelated backlog items unless
  the user requests them.
- Before finishing a task that changes behavior, dependencies, configuration,
  exports, or project workflow, update the Unreleased section of changelog.md.
  Describe the final completed change and any migration impact. Do not record
  proposed work as complete or invent release versions or dates.
- Check off TODO items only after the work and appropriate verification are
  complete. Keep incomplete verification explicit. Avoid duplicate entries and
  keep these records consistent with README.md and this guide.
- Documentation-only changes need a link and consistency check; run tests when
  the implementation changes require them. Never include secrets or real notes
  in project records.

## User flow

Launch opens the PyEdifice dashboard. Login uses saved credentials or opens an
in-app sign-in and verification form. Fetch prompts for a missing backup folder
and resumes after prerequisites are completed. Account and backup-folder forms stay in
the GUI; there are no Rich or terminal prompts. Demo, checks, and `--once` remain
noninteractive. Cancel clears pending credentials while preserving saved steps.

1. Connect iCloud with Apple Account email and password, including code-based
   two-factor authentication when required. Store passwords in the OS credential store.
2. Choose a local backup folder; initialize Git if needed.
3. Open the dashboard: account status, backup folder, last result, next scheduled
   fetch, and **Fetch now**. Returning users start here.
4. Show the active operation in Tasks and fetch progress in Logs, then
   added/updated/deleted/skipped counts and local commit status. Offer retries for failures.

The iCloud card provides login/logout. Folder and automatic fetch interval edits
in the Disk card save automatically after a short typing pause.
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
- Handle commit failures and conflicts without discarding data.

## Credentials

- Ignore `.env`; keep `.env.example` free of secrets. Never commit credentials
  or sessions to either repository. Prefer the OS credential store in the app.
- Keep real notes out of application source control, logs, screenshots, and tests.
  Use synthetic test data.

## Development
- Python 3.12+, PyEdifice dashboard, PyiCloud 2.7.0 Notes adapter, and system Git.
- Run `.venv/Scripts/python.exe -m pytest`; try `--demo` for synthetic data.
- Keep automated tests focused on logic, without Qt widgets or GUI interaction
  tests. Use a synthetic demo smoke check for desktop changes. Packaging uses
  PySide6 Qt hooks.
- See README.md for setup, exports, limitations, and Windows executable builds.
- On Windows, use `uv sync --extra dev` and
  `.venv/Scripts/python.exe -m notesvault --check` with uv and Git on PATH.
- Current exports preserve text and metadata in Markdown with YAML frontmatter,
  plus downloadable attachments. Per-note JSON sidecars are no longer written. Rich
  formatting, locked notes, and separate shared zones are not fully supported.
- Scheduling runs only while the GUI window is open; `--once` supports external schedulers.
- Separate authentication, retrieval, export, Git, application workflows, and desktop UI.
- Dashboard uses PyEdifice components and hooks with immutable state snapshots.
  The Qt-independent controller owns a single background executor and one named
  active task. Deliver progress and task completions through queued Qt signals;
  only the owner thread applies state updates and resumes pending fetches.
  Never update Qt widgets from a worker thread. Verification codes may be visible
  in GUI forms; passwords stay hidden and must never be logged.
- Test completeness, filenames, attachments, repeat backups, and failure recovery.
- Update this guide as decisions are made; document setup and installer commands.
- See [todo.md](todo.md) for outstanding work and [changelog.md](changelog.md)
  for completed changes.
