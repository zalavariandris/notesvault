# Changelog

Record completed, meaningful changes here. Keep upcoming changes under
`Unreleased`; add release versions and dates only when a release actually occurs.
Outstanding work is tracked in [todo.md](todo.md).

## Unreleased

- Replaced the Rich terminal dashboard with a prompt-based command line in
  `terminal.py`. Startup prepares the backup folder first, then tries saved
  credentials and prompts only as needed. It prints the folder, managed notes on disk,
  last result, and interval. Yes fetches now; no waits without resetting the timer.
  The prompt shows a countdown and starts scheduled fetches automatically.
- Terminal progress and results stay in scrollback. Settings use ordinary prompts;
  Ctrl+C cancels and exits after worker cleanup or a protected local save. Removed
  terminal panels, log widgets, and pause/resume hotkeys. Existing `--tui` and
  launcher/executable names open this CLI; settings and backups need no migration.
- Verified 176 logic tests and 32 affected tests after moving folder setup before
  login, plus a Windows synthetic terminal check for fetch/repeat/settings/timer,
  automatic fetching, and quit. The wheel includes the new terminal adapter.

- Distinguish Apple's terms-acceptance requirement from retryable sign-in errors.
  The command line now pauses with browser instructions and a retry prompt,
  instead of repeatedly requesting credentials. Preserve the specific terms error
  during verification and clear pending credentials. Saved settings/passwords remain
  intact; no migration is required. Browser acceptance and live sign-in still need
  user verification. Verified 38 authentication and interface tests, including
  terms failures during saved login, password submission, and verification.

- Simplified startup to mode selection only; GUI, TUI, and one-shot backups use
  the default per-user settings directory. `cli()` parses arguments and calls the
  typed `main(mode)` dispatcher. Removed `--data-dir`; users of custom
  settings directories must copy settings/status/sessions into the default location
  as described in README. Backup repositories and OS credentials stay in place.
- Removed demo flags and synthetic imports from production workflows and GUI
  controls. `python -m devtools.demo [--tui | --once]` now supplies synthetic
  authentication and notes to the normal application from a source checkout,
  with temporary settings and backups cleaned up on exit. It replaces `--demo`
  and is excluded from installed builds. `main()` retains match-based mode routing.
- Repaired the GUI spec's reference to `launcher_gui.py` and the terminal launcher's
  mode dispatch, retaining `--once` and `--check` for both launchers. The installed
  console entry point now calls `cli()`; rerun `uv sync --extra dev` in source checkouts.
- Verified the 164-test logic suite and 31 CLI/development tests after the typed
  entry-point split, synthetic desktop authentication/fetch/repeat/logout, runtime
  diagnostics, the installed entry point, and a wheel build excluding development
  code. Packaged executable and live-account checks remain in `todo.md`.

- Removed `.env` loading, environment-based account/folder defaults, and the
  `python-dotenv` dependency. Configure the account and backup folder through the
  GUI or TUI if previously supplied only by `ICLOUD_APPLE_ID` or `LOCAL_EXPORT_DIR`.
  Existing saved settings and OS credentials need no migration.

- Refactored `__main__.py` into argument parsing, runtime checks, and one-shot
  execution, with a smaller launch dispatcher and context-managed demo cleanup.
  Production command helpers stay in `__main__.py`; automated tests live under `tests/`.
  One-shot backups reuse the shared application service and always clear their
  in-memory session. Explicit modes retain priority over launcher defaults.
  Runtime failures identify the dependency check, Git checks have a timeout,
  and local file-access failures report a safe error. No migration is required.
  Verified 152 logic tests (including 20 CLI tests), runtime checks, and the
  synthetic desktop smoke check.

- Fixed TUI sign-in retries with safe, actionable errors for rejected credentials,
  network failures, unavailable services, and account setup requirements.
  Failed verification sessions can restart sign-in. Authentication failures during
  fetch clear the in-memory connection and reopen sign-in after worker cleanup;
  cancellation pauses scheduling, and successful reconnection offers fetch retry.
  Existing backups and saved credentials are preserved.
- Export frontmatter now keeps Unicode characters readable instead of ASCII
  escape sequences. Incremented the export version so the next fetch refreshes
  cached notes automatically. No manual settings or backup migration is required.
- Verified the 132-test logic suite and an additional verification-restart test,
  including synthetic TUI retries/reconnection, failure preservation, UTF-8 exports,
  and repeat backups. Live iCloud verification remains outstanding in `todo.md`.

- Added `notesvault-tui.spec` and a dedicated launcher for `dist/notesvault-tui.exe`.
  It opens the Rich interface by default and retains `--once` and `--check`.
  Documented both Windows build commands; no settings migration is required.

- Fixed Login failing to show its popup: SignInWindow now belongs to the
  dashboard's single Edifice root. Restored the scrolling dashboard container.
- Added `--tui`, a Rich terminal interface following the UX drawing, with folder
  setup, saved-login fallback, masked password/2FA entry, settings, scheduling,
  progress, searchable logs, retry, pause/resume/cancel, and safe exit. One-shot
  and runtime checks remain noninteractive; incompatible mode flags are rejected.
- Shared setup validation and provider selection through a UI-independent
  application service. GUI and TUI retain the same credential and safe local-Git
  controllers. Added interface logic coverage and an opt-in desktop popup smoke
  script. No dependency, settings, or backup migration is required.
- Verified 121 logic tests, runtime checks, desktop popup/verification smoke, and
  Windows terminal demo fetch/repeat/exit. Cancelled terminal reconnection resets
  scheduling, and fetch exit waits for protected local saves to finish.

- Refined the desktop UI around reusable account, backup, Tasks, and Logs cards,
  shared styling, and plain-text labels. The dashboard opens at 520 × 860 in a
  scrolling column and fits narrow windows. Backup preferences show autosave state;
  Tasks separates active progress from the last result and offers fetch retries.
- Added searchable, selectable timestamped logs with Copy and Clear, retaining
  the latest 200 messages. Clearing the viewer preserves the persisted result.
- Moved sign-in and verification into a focused popup with inline errors, keyboard
  submission, masked passwords, and safe cancellation. Saved credentials are tried
  first; successful setup closes the popup and resumes pending fetches. Active
  authentication requests block closing, and expired connections are rechecked
  before fetching. No settings or backup migration is required.
- Verified 111 logic tests, runtime/demo checks, and synthetic desktop flows for
  narrow layouts, preference autosave, logs, fetch controls/retry, and popup
  login/verification, keyboard controls, cancellation, saved-credential login,
  reconnection, and pending-fetch continuation. Live iCloud verification remains open.

- Reviewed the architecture and separated pure export rendering, disposable cursor
  persistence (`FetchCache`), and disk validation/planning/saving. GUI and CLI still
  share the backup workflow; authentication and task lifecycle boundaries remain.
- Removed temporary Markdown exports. Rendered bytes stay in a 64 MiB fetch buffer
  until the protected save phase, then write directly to final vault paths. Optional
  attachments stream once to temporary downloads; pause/cancel and Git rollback
  retain their safety guarantees. Interrupted saves keep a recovery journal and
  copies, block further fetches, and have documented manual recovery instructions.
- Note filenames now use `YYYY-MM-DD-<TITLE>-[<ID>].md`, with UTC modification dates,
  safe titles, and stable ID hashes. Missing/invalid dates use `0000-00-00`.
  Incremented the export version to invalidate cached filenames. This scope starts
  with an empty vault; no old-vault migration is required.
- Verified existing rich Markdown conversion and incremental downloads, including
  provider rendering/fallback, folder refreshes, cursor expiry, skipped content,
  explicit deletions, and failed saves. Reject unexpected zones in raw change
  responses. PyiCloud 2.7.0 still cannot export separate shared zones or locked
  content; warnings and retention behavior are documented.
- Documented the existing attachment preference (off by default) and its cache
  invalidation behavior. Verified 109 logic tests, runtime checks, a one-shot demo,
  and synthetic desktop attachment autosave, progress, pause/resume, cancellation,
  failure/retry, repeat backup, and close while paused. Live iCloud verification
  remains outstanding.

- Added an experimental dependency graph helper using Python symbol tables to
  connect scopes to referenced bindings, including globals, closures, and local
  shadowing. Graphs use dictionaries and sets without new dependencies; dynamic
  attribute resolution and assignment data flow remain outside its scope.

- Added an experimental function-level Python AST comparison with tests for
  changed, unchanged, added, and removed functions, including methods and nested
  functions. Formatting and comments are ignored; external dependencies are not
  analyzed. No migration is required.

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
