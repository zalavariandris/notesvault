# TODO

Track outstanding work here. Check off items only when implementation and relevant
verification are complete. Completed changes belong in [changelog.md](changelog.md).
Backlog entries do not authorize work outside the current user request.

- [ ] does the EXPORT_VERSION really necessary?
- [ ] get rid of GitHub related code. we are not going to push the notes ot github.
      Ofcourse, we keep the local git, for history.
- [ ] FIX icloud login. right inside the ICloudComponent
- [ ] review codebase, and remove redundant code as well as redundant, or outdated tests.
- [ ] remvoe all UI related test code. keep the logic only.
- [ ]

## UPDATE UI code
- [x] basically we keep the notes in 3 places: iCloud, Disc(Local git), GitHub.
  update the UI itself as well as the related code to reflect that.
- [x] Replace Textual with a PyEdifice/Qt GUI using reactive state snapshots,
  background operations, and GUI tests.
- [x] Move account setup into PyEdifice forms. Login reuses saved credentials;
  Fetch prompts for a missing folder and resumes after setup.
- [ ] Save setting automatically when changed!

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

## Investigation notes

- Per-note incremental fetching remains open: verify attachment-only and folder
  changes before trusting the note-filtered changes feed. Changed cursors currently
  trigger a full fetch. The cache is saved only after a complete local backup.
- PyiCloud 2.7.0 `get()` returns decoded text and sets HTML to None. Rich exports
  need a separate rendering path and conversion tests.
- Notes enumeration targets the default Notes zone and Note records; shared zones
  and PasswordProtectedNote discovery need additional work. Existing locked-note
  failures defer deletions. Live-account verification has not been performed.
