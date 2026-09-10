# Changelog

Record completed, meaningful changes here. Keep upcoming changes under
`Unreleased`; add release versions and dates only when a release actually occurs.
Outstanding work is tracked in [todo.md](todo.md).

## Unreleased

- Added Pause/Resume and Cancel fetch controls to Tasks. Fetch workers stop at
  cooperative checkpoints during listing, note downloads, and attachment streaming.
  Pause retains staging for continuation; cancellation discards unfinished staging
  while preserving exports, Git history, cursor cache, and the last backup result.
- Closing during a fetch now requests cancellation and closes automatically after
  cleanup. Paused workers also wake on cancellation or unmount. Requests already in
  flight must return before stopping; an atomic boundary protects local saves from
  interruption, and closing waits for those saves to finish. Other active operations
  retain close protection. No configuration or backup migration is required.
- Verified 77 logic tests and synthetic desktop workflows for pause/resume,
  cancel/retry, and closing during running, paused, and saving stages. Async cleanup
  consumes cancelled worker outcomes without an unhandled-exception traceback.

- Tasks now shows live progress beneath the active operation, including the note
  number during downloads and the local Git stage. Progress remains in Logs and
  clears from Tasks when an operation finishes or fails. Updates stay on the UI
  thread and are scoped to the originating task. Verified four task-manager tests
  and a synthetic desktop progress/lifecycle smoke check. No migration is required.

- Separated background task execution from Dashboard into a Qt-independent
  `TaskManager` and a UI hook that handles progress, results, close protection, and
  shutdown. Tasks displays the active operation; reservations prevent overlapping
  actions before the next render and remain held until results are consumed.
- Replaced the iCloud-specific form with `AuthenticationComponent`, which owns its
  input drafts and receives only display props and callbacks. Dashboard owns local
  hooks grouped by account, disk configuration, and fetching responsibilities.
- Limited `ConfigModel` to saved preferences and moved last-backup results to
  `backup-status.json`. Legacy results remain readable and are preserved before
  the next settings save. Backup exports and Git history need no migration.
- Split folder configuration and local Git operations (`DiskVaultController`) from
  fetch orchestration and cursor caching (`BackupController`). Repaired imports
  after the module moves and restored `--demo`, `--once`, `--check`, and `--data-dir`.
  GUI and CLI share the backup workflow and result persistence.
- Verified 63 logic tests and runtime imports, plus synthetic desktop checks for
  active tasks, overlap prevention, close protection, repeat backups, autosave,
  saved login, password masking, verification retries, cancellation, setup
  continuation, logout, and worker cleanup. Live iCloud verification remains open.

- Consolidated repository operations, fetch orchestration, and cursor caching into
  `controllers/backup_controller.py` and its `BackupController` class. Updated
  dashboard, CLI, and tests; removed the separate repository and service modules.
  Repaired stale imports after the model/controller moves, including the standard
  library datetime import in `models.py`. All 38 logic tests, runtime checks, and a
  synthetic desktop backup passed. Backup files need no migration.

- Renamed the authentication workflow class to `ICloudAccountSetup` and updated
  controller and test references. No user configuration migration is required.

- Removed GitHub publishing, its account form and tests, and publishing status
  from backup results. Existing settings discard retired options on save while
  preserving local backup configuration and history. Previously stored GitHub
  tokens remain unused in OS storage; existing Git remotes are unchanged.
- Moved controller workflows and all dashboard cards into one `Dashboard`
  component. State and form values use `ed.use_state`; actions are nested
  functions, with hooks managing autosave, scheduling, background results, and
  cleanup. Removed the controller class and its obsolete tests. Kept overlap
  prevention, setup continuation, and protection against closing during a task.
  Verified 38 logic tests, runtime imports, a one-shot demo backup, and synthetic
  desktop workflow and lifecycle smoke checks. No user migration is required.
- Added a Tasks viewer and automatic saving of folder/interval edits after a
  typing pause. Invalid settings preserve saved values. Fixed the native folder
  picker reference and restored saved-account login, verification, cancellation,
  and disconnect controls inside the iCloud card.
- Removed an unused account form, stale imports, obsolete UI interaction tests,
  pytest-asyncio, and credential-printing debug output. Repaired demo exports and
  retained migration, backup recovery, and authentication logic coverage.
- Shared local backup result formatting between the CLI and dashboard; `--once`
  loads no desktop modules. Empty and dot backup paths now fail with a safe error.
- Declared Rich as a runtime dependency because PyiCloud 2.7.0's Notes renderer
  imports it without the CLI extra. Authentication remains in the GUI. Rerun
  `uv sync --extra dev` to refresh dependencies.
- Verified the refactor and second review with 47 passing logic tests, the runtime
  and dependency lock checks, a one-shot demo backup, and synthetic desktop fetch
  and automatic-save smoke checks. Live iCloud verification remains outstanding.

- Reviewed and retained `EXPORT_VERSION` for cache invalidation when export content
  or support changes. Documented when to increment it and repaired the regression
  test's outdated patch target. All five cache service tests pass; no migration
  is required.

### 2026-09-09

- iCloud and Disk cards reactively use a red-bordered Danger class when iCloud
  is unauthenticated or no backup folder is specified.

- Replaced Rich authentication with in-window PyEdifice login, verification,
  folder, and private GitHub forms. Removed the direct Rich dependency.
- Redesigned the iCloud card around Login and connection status. Login uses saved
  credentials or requests them. Fetch prompts for missing prerequisites and resumes
  the backup after setup; cancel preserves saved steps without starting a backup.
- Added GUI coverage for masked passwords, visible verification codes, retries,
  saved-credential login, and folder selection followed by automatic fetching.

- Replaced the Textual dashboard with a PyEdifice/PySide6 desktop GUI. iCloud,
  Disk, GitHub, Settings, and Logs render from reactive state snapshots. Blocking
  work runs in a background executor; active operations prevent window closure.
- Added a native backup-folder picker and retained Rich account setup, scheduling,
  local backup, optional publishing, and account disconnection.
- Replaced Textual tests with offscreen Qt/PyEdifice interaction tests and updated
  dependencies, executable packaging, and launch documentation.

- UI tests explicitly cover the iCloud, Disk, GitHub, and Logs sections, current
  action labels, and placement of status widgets at narrow and wide terminal sizes.
  Test names follow the current section naming.

- Updated UI tests for the Disk-card fetch button, keyboard fetching across terminal
  sizes, Rich connection routing, and reactive control recovery after fetch failures.
  Removed an empty layout block that prevented application imports.

- Dashboard uses reactive settings, connection, busy, and schedule state. Settings
  updates replace the dataclass; watchers update widgets even while a modal is open.
- Verification codes are visible in Rich prompts; passwords and tokens stay hidden.
- Connect iCloud opens Rich setup, progress reaches the dashboard log, and the
  fetch button is in the Disk card; the `f` shortcut also starts fetching.

- Dashboard distinguishes iCloud source, local disk/Git backup, and optional
  GitHub publishing.
- Unchanged iCloud cursors reuse existing exports without redownloading. Local
  integrity checks still run; changed cursors use a full fetch. The disposable
  cache lives in `.git/notesvault-fetch.json` and is written after successful
  complete backups. Export-format changes invalidate it.
- Setup instructions use uv and Python commands; no setup.bat workflow is planned.

### Earlier unreleased work (date not recorded)

#### Added

- Rich startup wizard for missing credentials or a local backup repository, with
  iCloud sign-in, code-based 2FA, folder preparation, and optional private GitHub
  connection. Completed setup steps are saved.
- Dashboard Settings can reopen the Rich account setup wizard.
- Regression coverage for setup, authentication routing, settings compatibility,
  Markdown metadata, and migration of existing note exports.
- Project TODO and changelog files, with maintenance instructions in AGENTS.md.

#### Changed

- iCloud sign-in uses Apple Account email and password with OS credential storage.
  Authentication prompts run in Rich; Textual remains the dashboard and backup
  settings interface.
- Note metadata is stored as YAML frontmatter in Markdown instead of separate
  JSON sidecars. Managed sidecars are removed when their notes are re-exported;
  earlier versions remain in Git history. The internal backup manifest remains JSON.
- Existing settings accept the obsolete authentication selector without requiring
  users to reconfigure their backup folder.

#### Removed

- Browser authentication, its Playwright dependency, packaging references, and tests.
- Textual email/password, verification-code, and GitHub-token entry forms.
