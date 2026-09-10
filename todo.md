# TODO

Track outstanding work here. Check off items only when implementation and relevant
verification are complete. Completed changes belong in [changelog.md](changelog.md).
Backlog entries do not authorize work outside the current user request.

- [x] Review whether `EXPORT_VERSION` is necessary: retain it to invalidate cached
      exports after format/support changes even when the iCloud cursor is unchanged.
      Fixed the outdated monkeypatch target; all five cache service tests pass.
- [x] Remove GitHub publishing code, settings, forms, and tests; retain local Git
      history. Existing settings migrate without losing the backup folder.
- [x] Keep iCloud login and verification inside `ICloudComponent`, including
      saved-credential reconnection, cancellation, and disconnect controls.
- [x] Review and refactor the codebase, remove redundant code and obsolete tests,
      then review again. Removed the unused account form, stale imports, and
      credential debug output; fixed demo exports and unsafe empty/dot paths.
- [x] Fix the demo provider's missing `write_export` import; local commit and
      staging cleanup are covered by the replacement demo service test.
- [x] Remove UI interaction tests and their pytest-asyncio dependency. Keep logic
      tests for the controller, authentication, configuration, exports, and Git.

## Desktop and task management
- [x] Reflect the current two locations: iCloud source and local disk/Git backups.
- [x] Replace Textual with a PyEdifice/Qt GUI using reactive state snapshots,
  background operations, and synthetic desktop smoke checks.
- [x] Move account setup into PyEdifice forms. Login reuses saved credentials;
  Fetch prompts for a missing folder and resumes after setup.
- [x] Automatically save folder and interval edits after a typing pause; retain
  saved values on validation failure and save pending edits before fetching.
- [x] Refactor controller task management into a Qt-independent workflow layer
  and a small Qt adapter. Use one named active task, per-task completion context,
  queued notifications, and explicit continuation after successful setup.
- [x] Add `TasksViewerComponent` to show the active operation.

## Backup efficiency

- [x] Reuse local exports when the entire iCloud sync cursor is unchanged, with
  local integrity checks and cache invalidation after export-format changes.
- [ ] Avoid downloading unchanged notes. Evaluate PyiCloud sync cursors and note
  summary metadata; retain unchanged exports, handle confirmed deletions, and fall
  back to a full scan when a cursor is invalid. Persist cursors only after a
  successful local backup. Cover failures, skipped notes, and export-format changes.

## Export coverage

- [ ] Preserve richer note formatting in Markdown.
- [ ] Investigate separate shared zones and locked notes; report unsupported content
  without treating it as deleted.

## Verification and distribution

- [x] Resolve the documented `setup.bat` workflow. We dont want that anymore.
  Update the setup instructions to the supported commands.
- [x] Verify the cleanup with 47 passing logic tests, `--demo --once`, `--check`,
  dependency sync/lock checks, and synthetic desktop fetch/autosave smoke checks.
  Restore Rich as a runtime dependency required by PyiCloud's Notes imports.

## Investigation notes

- Per-note incremental fetching remains open: verify attachment-only and folder
  changes before trusting the note-filtered changes feed. Changed cursors currently
  trigger a full fetch. The cache is saved only after a complete local backup.
- PyiCloud 2.7.0 `get()` returns decoded text and sets HTML to None. Rich exports
  need a separate rendering path and conversion tests.
- Notes enumeration targets the default Notes zone and Note records; shared zones
  and PasswordProtectedNote discovery need additional work. Existing locked-note
  failures defer deletions. Live-account verification has not been performed.
