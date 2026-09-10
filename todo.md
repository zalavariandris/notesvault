# TODO

Track outstanding work here. Check off items only when implementation and relevant
verification are complete. Completed changes belong in [changelog.md](changelog.md).
Backlog entries do not authorize work outside the current user request.

## Export coverage

- [x] by default do not download attachments. add an option to the method to do so, expose that to the UI.
- [ ] Preserve richer note formatting in Markdown.
- [ ] Investigate separate shared zones and locked notes; report unsupported content
  without treating it as deleted.
- [ ] skip staging, and save markdown files directly to the vault's folder.
- [ ] set the notes name formatting: <YYYY-MN-DD>-<NOTE-TITLE>-[<NOTEID>]

## Backup efficiency

- [ ] Avoid downloading unchanged notes. Evaluate PyiCloud sync cursors and note
  summary metadata; retain unchanged exports, handle confirmed deletions, and fall
  back to a full scan when a cursor is invalid. Persist cursors only after a
  successful local backup. Cover failures, skipped notes, and export-format changes.

## Major Refactor

- [x] Decouple task management from Dashboard with a Qt-independent task manager
      and a UI lifecycle hook.
- [x] Show the active task in the dashboard Tasks card.
- [x] Show the active task's latest progress in Tasks, retain its history in Logs,
      and clear progress on completion or failure. Verified with a synthetic
      desktop smoke check and task-manager logic tests.
- [x] Replace iCloudComponent with a reusable AuthenticationComponent that receives
      display props and callbacks without access to application state.
- [x] Create dashboard state in local hooks inside the widget; remove the separate
      DashboardState object.
- [x] Keep ConfigModel limited to saved preferences; separate disk drafts, runtime
      state, and persisted backup results, preserving legacy results automatically.
- [x] Group state and actions by iCloud authentication, disk configuration, and
      fetch/backup responsibilities.
- [x] Separate authentication, disk/Git operations, backup orchestration, and task
      execution; repair imports and retain noninteractive CLI workflows.

Verified with logic tests, runtime checks, and synthetic desktop backup and
authentication smoke checks. See [changelog.md](changelog.md) for details.

## Manual verification

- [ ] Verify sign-in, code-based 2FA, session expiry/reconnection, and fetching with
      a live iCloud account, including pause/resume and cancellation during downloads.
      Current checks use synthetic data and sessions.

## Fetch controls

- [x] Add cooperative Pause/Resume and Cancel in Tasks, with checkpoints during
      retrieval and attachment streaming. Preserve existing backups, cache, and
      status on cancellation; finish any already-started local save safely.
- [x] Closing during a fetch requests cancellation and closes automatically after
      cleanup; also handle closing or unmounting while paused. Verified with logic
      tests and synthetic desktop checks for resume, cancellation/retry, and closing
      during running, paused, and saving stages.
