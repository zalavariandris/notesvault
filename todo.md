# TODO

Track outstanding work here. Check off items only when implementation and relevant
verification are complete. Completed changes belong in [changelog.md](changelog.md).
Backlog entries do not authorize work outside the current user request.

# Command-line user flow
- [x] Replace the terminal dashboard with ordinary prompts: folder setup before
      saved-login/password/verification, disk note count and results, fetch-now
      question, automatic-fetch countdown, scrolling progress, and safe Ctrl+C exit.
      Verified 176 logic tests plus 32 affected tests after the final startup-order
      change; Windows synthetic terminal fetch/repeat/settings/countdown/automatic
      fetch/quit and wheel contents/build also passed.

- [x] Report helpful iCloud sign-in errors and allow retries, including restarting
      failed verification sessions. Verified with synthetic controller/TUI tests.
      Terms-required errors now stop credential retries, preserve saved steps, and
      guide browser acceptance before answering yes to retry. Verified 38 authentication and
      interface tests, including saved-login, password, and verification failures.
- [x] Handle credential/session failures during fetch by returning to sign-in after
      worker cleanup. Cancel pauses scheduling; reconnect offers fetch retry.
      Verified reconnection/cancellation and backup/cache/status preservation.

## Export coverage
- [x] Preserve readable Unicode in frontmatter, e.g. `title: "Éttermek"`, while
      escaping quotes and newlines. Verified UTF-8 disk output and repeat backup;
      incremented the export version to refresh previously cached notes.
- [x] by default do not download attachments. add an option to the method to do so, expose that to the UI.
- [x] Preserve richer note formatting in Markdown. Verified converter behavior,
      provider integration, readable fallback, and export-version invalidation.
- [x] Investigate separate shared zones and locked notes; report unsupported content
  without treating it as deleted.
      PyiCloud 2.7.0 retrieval is limited to the private Notes zone. Unsupported
      content is reported; only confirmed tombstones permit deletion, and skipped
      notes defer deletions. Raw-record and retention tests pass.
- [x] Skip Markdown staging and write directly to final vault paths after retrieval
      and validation. Buffer rendered bytes up to 64 MiB; keep optional attachment
      downloads temporary. Verify cancellation, Git rollback, and interrupted saves.
- [x] Set note names to YYYY-MM-DD-<NOTE-TITLE>-[<NOTEID>]. Use UTC modification
      dates, 0000-00-00 when unavailable, safe titles, and stable ID hashes.
      The old vault has been emptied; no legacy export migration is required.
      See [PLAN.md](PLAN.md) for the implementation plan.

## Backup efficiency

- [x] Avoid downloading unchanged notes. Evaluate PyiCloud sync cursors and note
  summary metadata; retain unchanged exports, handle confirmed deletions, and fall
  back to a full scan when a cursor is invalid. Persist cursors only after a
  successful local backup. Cover failures, skipped notes, and export-format changes.

## Major Refactor

- [x] Remove `.env` loading and environment-based account/folder defaults; use
      saved settings and GUI/TUI setup. Removed the dependency and verified
      153 logic tests and lockfile consistency.

- [x] Refactor and polish `__main__.py`: separate parsing, runtime checks, and
      one-shot backups; reuse application operations and guarantee demo/session
      cleanup. Verified 152 logic tests, runtime check, and desktop smoke check.
      Production backup/diagnostic commands remain as dedicated functions in
      `__main__.py`; automated tests remain under `tests/`.
      Follow-up: `cli()` feeds a typed `main(mode)` dispatcher. Both interfaces
      use default per-user settings; synthetic dependencies and temporary storage
      live in `devtools`, with no production demo flags or settings-path arguments.
      Verified the 164-test logic suite, 31 CLI/development tests after the final
      entry-point split, desktop authentication/fetch/repeat/logout smoke, runtime
      diagnostics, installed console entry point, and wheel contents/build.

- [x] Review the current architecture and refactor for clearer responsibilities,
      simpler control flow, and less duplication while preserving backup safety
      and GUI/CLI behavior. Document findings and verify the resulting changes;
      see [PLAN.md](PLAN.md#2-review-architecture-and-refactor-for-clarity).
      Extracted pure export rendering and FetchCache; separated disk validation,
      snapshot planning, and saving. Verified 109 logic tests, runtime and one-shot
      demo checks, and a synthetic desktop smoke check.

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

## UI refinement

- [x] Fix the missing Login popup, separate shared application operations from UI
      adapters, and implement a Rich TUI following the UX drawing. Plan and project
      review: [INTERFACE_PLAN.md](INTERFACE_PLAN.md). Verified 121 logic tests,
      runtime checks, a synthetic desktop popup smoke, and Windows terminal demo
      fetch/repeat/exit. Live-account and packaged/cross-platform checks remain below.

- [x] Implement [UI_PLAN.md](UI_PLAN.md): reusable presentation components, a tall
      dashboard, improved Tasks and searchable logs, and a focused sign-in popup.
      Verified 111 logic tests, runtime/demo checks, and synthetic desktop flows
      for narrow layout, logs, fetch controls/retry, and popup login/verification,
      cancellation, reconnection, and setup continuation.

## Manual verification

- [ ] Restore argument parsing in the dedicated launchers before verifying their
      packaged `--once` and `--check` modes. They currently call `main(mode=...)`
      directly; `python -m notesvault` and the installed `notesvault` entry point
      still parse those flags.

- [ ] Verify the prompt-based command line on Linux/macOS terminals and the packaged Windows
      executable. Source-level Windows terminal and synthetic checks are covered
      by the interface implementation; packaged and other-platform checks remain.

- [ ] Verify sign-in, code-based 2FA, session expiry/reconnection, and fetching with
      a live iCloud account, including pause/resume and cancellation during downloads.
      Current checks use synthetic data and sessions.
      Current blocker: PyiCloud reports Apple's terms-acceptance requirement.
      Verify browser sign-in/terms acceptance, then retry login; successful live
      authentication has not been confirmed. Do not record account details here.

## Fetch controls

- [x] Add cooperative Pause/Resume and Cancel in Tasks, with checkpoints during
      retrieval and attachment streaming. Pause retains buffered exports and optional
      downloads. Preserve existing backups, cache, and
      status on cancellation; finish any already-started local save safely.
- [x] Closing during a fetch requests cancellation and closes automatically after
      cleanup; also handle closing or unmounting while paused. Verified with logic
      tests and synthetic desktop checks for resume, cancellation/retry, and closing
      during running, paused, and saving stages.
