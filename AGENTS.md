# Notes Vault

## Goal

Build a desktop app that backs up Apple Notes from iCloud
into a local Git repository. Backups stay local; publishing is not supported.
This is a one-way backup; two-way synchronization is outside the current scope.

## Agent workflow and project records

- At the start of each task, read this guide, [todo.md](todo.md). Use README.md for current
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

Launch opens a tall, scrolling PyEdifice dashboard. Login uses saved credentials or
opens a focused sign-in and verification popup. Fetch prompts for a missing backup folder
and resumes after prerequisites are completed. Account and backup-folder forms stay in
the GUI; there are no Rich or terminal prompts. Demo, checks, and `--once` remain
noninteractive. Cancel clears pending credentials while preserving saved steps.

1. Connect iCloud with Apple Account email and password, including code-based
   two-factor authentication when required. Store passwords in the OS credential store.
2. Choose a local backup folder; initialize Git if needed.
3. Open the dashboard: account status, backup folder, last result, next scheduled
   fetch, and **Fetch now**. Returning users start here.
4. Show the active operation and its latest progress in Tasks, retain progress in Logs, then
   added/updated/deleted/skipped counts and local commit status. Offer retries for failures.

The iCloud card provides login/logout. Folder and automatic fetch interval edits
in the Backup card save automatically after a short typing pause, with save status.
Expired sessions require reconnection; iCloud logout pauses fetching without
removing backups. Prevent overlapping fetches.

Tasks provides Pause/Resume and Cancel for an active fetch. Pause retains buffered exports and downloads
in the current process; cancellation discards the unfinished fetch. Check controls
between requests and attachment chunks, and atomically stop accepting cancellation
before applying the snapshot. Never interrupt local Git writes. Closing during a
fetch requests cancellation and closes automatically after worker cleanup, or after
an already-started local save finishes. An in-flight request must return first.

## Backup rules

- Export all accessible notes into readable files; report unsupported or
  inaccessible content. Decide formatting, metadata, and attachment handling.
- Use safe, readable filenames and stable IDs where available, for example
  `YYYY-MM-DD-<TITLE>-[<ID>].md`. Use UTC modification dates (naive means UTC),
  `0000-00-00` when unavailable, and stable ID hashes. Preserve IDs on rename;
  avoid duplicates and empty commits.
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
- Current exports preserve supported rich text and metadata in Markdown with YAML
  frontmatter, plus optional downloadable attachments (disabled by default).
  Per-note JSON sidecars are no longer written. Complex formatting can lose
  fidelity; plain-text fallback is reported. Locked notes and separate shared zones
  are unsupported. The fixed Notes-zone adapter retains unconfirmed absences;
  only explicit tombstones from complete, unskipped fetches permit deletions.
- Scheduling runs only while the GUI window is open; `--once` supports external schedulers.
- Separate authentication, retrieval, export, backup workflows, and desktop UI.
  `icloud_authentication_controller.py` owns sessions and credentials;
  `disk_vault_controller.py` owns folder configuration, repository safety, files,
  and Git history, with distinct validation, snapshot planning, and save methods;
  `backup_controller.py` owns fetch orchestration, optional download lifetime, and
  recording results. `fetch_cache.py` owns disposable cursor persistence and
  validation. Providers retrieve/convert notes; `provider_utils.py` constructs
  exports without writing Markdown. Data models live in `models.py`.
- New Markdown stays in a 64 MiB buffer of rendered bytes until the protected
  save phase, then writes directly to `notes/<folder>/` within the vault. Optional
  attachments stream to temporary files under `.git` without a second staging
  copy. No old-vault migration is required for the empty-vault implementation.
- Keep `.git/notesvault-save.json` and recovery copies if a process interruption
  or failed rollback leaves a save unfinished. Block new fetches until manual
  recovery is reviewed; see README. Never discard recovery copies on failed
  restoration or reset unrelated files/index entries.
- Dashboard creates its state with local `ed.use_state` hooks, grouped into account,
  disk drafts, and fetch/scheduling responsibilities. There is no external dashboard
  state object. The saved `ConfigModel` is separate from drafts and runtime state;
  `BackupStatusStore` persists results in `backup-status.json` and preserves legacy
  results from settings before their next save.
- `ui/authentication.py` provides a reusable `AuthenticationComponent` with display
  props and callbacks. It owns account/password/code drafts and has no access to
  application state, stores, or controllers. Dashboard supplies iCloud-specific labels.
- `ui/components.py` owns shared cards, actions, and plain-text labels;
  `ui/cards.py` contains account, backup, Tasks, and Logs presentation components.
  Dashboard retains workflow state; components receive props and callbacks.
  `activity_log.py` provides bounded timestamped log entries and search without Qt.
  Logs shows the latest 200 messages, newest first, with Search, Copy, and Clear;
  clearing logs never clears the persisted backup result. Render user data as plain
  text, including account names, errors, and logs.
- `ui/sign_in.py` hosts the authentication form in a modal WindowPopView. Success
  unmounts it without cancelling completed authentication; Cancel, Escape, and
  window close cancel pending setup when idle. Closing is blocked during an active
  authentication request. Block configuration edits and scheduling while it is open.
  Enter submits the password/code fields. Recheck controller connection status
  before a fetch so expired sessions route through reconnection.
- Keep one named active operation and reserve it before the next render to prevent
  overlapping actions. `task_manager.py` owns the single executor, reservation,
  completion, and shutdown independently of Qt. `ui/tasks.py` adapts it to hooks,
  delivers progress/results through the Qt/asyncio loop, and exposes the active task
  for the Tasks card.
  `fetch_control.py` owns cooperative pause/cancel checkpoints and the local-save
  boundary. Paused fetches retain the task reservation and repository lock.
  Never update hooks or Qt widgets from worker threads. A Qt event filter requests
  safe fetch shutdown on close; other active operations still block closing.
  Unmount cancels paused/running fetches, waits for workers, and clears credentials.
  Verification codes may be visible in GUI forms; passwords stay hidden and must
  never be logged.
- Test completeness, filenames, attachments, repeat backups, and failure recovery.
- Update this guide as decisions are made; document setup and installer commands.
- See [todo.md](todo.md) for outstanding work and [changelog.md](changelog.md)
  for completed changes.
