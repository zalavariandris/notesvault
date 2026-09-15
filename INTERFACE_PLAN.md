# Login repair and Rich terminal interface

Historical implementation record. The terminal dashboard described here has been
replaced by the prompt-based [command-line flow](README.md#interactive-command-line).

1. Repair the desktop popup's placement within Edifice's single root. Smoke-check
   opening, verification, cancellation, and successful closure with synthetic sessions.
2. Introduce a UI-independent application service for configuration, authentication,
   prerequisites, and provider selection. Reuse existing safe backup and task controllers.
3. Implement `--tui` with Rich, following [the UX drawing](docs/ux_flow.excalidraw):
   folder setup, saved login, password/verification fallback, then backup dashboard.
   Include settings, logout, progress, logs, retry, scheduling, pause/resume/cancel,
   and safe exit. Preserve noninteractive `--once`, `--demo --once`, and `--check`.
4. Verify shared workflows and terminal behavior with synthetic logic tests; run
   the full suite, runtime checks, and desktop smoke checks.
5. Review project boundaries, backup safety, credentials, packaging, and docs;
   fix concrete related defects and record remaining limitations in todo.md.

## Results and project review

- Completed steps 1–3. The popup was a second component root instead of a child
  of the main Window. A synthetic desktop check now exercises real mouse events,
  modal visibility, cancellation, password entry, verification and successful closure.
- Shared application operations and existing controllers import no UI frameworks.
  Desktop hooks and the Rich adapter retain only presentation/event-loop concerns.
  A subprocess test verifies that importing the TUI does not import Qt or Edifice.
- Reviewed authentication, settings/status persistence, task lifetime, providers,
  export/cache handling, disk/Git recovery, CLI entry points, packaging and records.
  Preserved deletion safeguards, repository locks, OS credentials and the protected
  save boundary. Removed desktop-specific wording from shared controller/provider
  messages. Restored the scroll container and kept terminal controls above content
  so small terminals still expose cancellation/exit actions.
- Full logic suite: 121 passed. Runtime import/Git/credential-backend check passed.
  Windows interactive terminal smoke: demo startup, first fetch (3 added), repeat
  fetch (no changes/no empty commit), and clean exit passed. Desktop offscreen
  smoke passed. Initial pytest runs reported a cache-directory warning; the full
  suite passed with the optional pytest cache provider disabled.
- Review also caught a cancelled terminal reconnection leaving an expired schedule
  active. Reset scheduling after that action; a regression test covers it. Local
  documentation links and the working diff's whitespace checks pass.
- No new dependency or storage migration is needed; the existing Windows build
  enables a console and accepts `--tui`. Packaged executable, Linux/macOS terminal,
  and live iCloud account verification remain explicit follow-ups in [todo.md](todo.md).
