# UI refinement plan

Scope: refine the desktop UI and implement this plan in the same task. Interpret
“Test viewer” as the existing Tasks viewer. Keep [PLAN.md](PLAN.md) as the record of
the earlier backup work. [todo.md](todo.md) tracks completion.

## 1. Reusable presentation components

Extract card framing, plain-text labels, account summary, backup preferences,
task display, and activity logs from Dashboard. Components receive display props
and callbacks; Dashboard retains its local state and coordinates controllers.
Keep task execution and authentication outside presentation components. Centralize
spacing and colors, use readable wrapping text, and avoid exposing technical
implementation details in ordinary user flows.

## 2. Tall, compact dashboard

Open at approximately 520 × 860 with a single scrolling column. Show account
readiness, backup destination/options, a prominent Fetch action, Tasks, and Logs.
Use consistent cards and spacing; support smaller windows without horizontal
overflow. Show autosave state and actionable prerequisite messages. Keep the last
backup result separate from transient progress; expose a direct retry after failure.

## 3. Tasks and Logs

Tasks should explain running, pausing, paused, cancelling, and saving states;
display latest progress, an honest indeterminate activity indicator, and only
applicable controls. Preserve the single-operation reservation and save cutoff.

Logs should have timestamped, selectable plain-text entries, newest first, a
bounded history, search, and Clear. Clearing the viewer must not clear the persisted
backup result. Keep error messages visible near the relevant action, and avoid
interpreting log/account text as HTML. Test any extracted log logic without Qt.

## 4. Focused sign-in popup

Keep the account card compact. Open a separate sign-in window for credentials and
code verification, with clear step labels, password masking, keyboard submission,
local error/progress feedback, and cancellation. Try saved credentials first;
show the popup if input or verification is needed. Close it on success and resume
a pending fetch after its prerequisites are complete. Closing the popup cancels
pending setup, clears drafts, and preserves completed configuration. While a
non-cancellable authentication request is active, keep close blocked and explain
that the request must finish. Prevent duplicate popups and overlapping operations.
Keep configuration edits and fetch scheduling paused while sign-in is open.

## 5. Verification and records

Run existing logic tests plus focused tests for new non-Qt logic; run runtime and
one-shot demo checks. Use temporary synthetic desktop smoke scripts (not automated
GUI tests) to verify tall/narrow layouts, component rendering, search/Clear,
autosave, retry, pause/resume/cancel/close, popup login/2FA failure and success,
popup cancellation, credential masking, and pending-fetch continuation. Inspect
a synthetic screenshot for spacing and clipping. Keep live iCloud verification
explicitly open. Update README, AGENTS, TODO, changelog, and this plan with results.

## Completed implementation and verification

- Added shared visual primitives in `ui/components.py`, presentation sections in
  `ui/cards.py`, and a focused popup in `ui/sign_in.py`. Dashboard retains local
  workflow state and controller coordination. The window opens at 520 × 860.
- Added timestamped activity history and case-insensitive search in the
  Qt-independent `activity_log.py`. Logs supports selection, search, Copy, and
  Clear; Tasks shows active state, progress, the last result, and Retry fetch.
- Kept saved-credential login, moved credential/code entry into the popup, added
  keyboard submission and guarded popup cancellation, and rechecked live controller
  connection state before fetches. Pending fetches resume after successful setup.
- Passed 111 logic tests, runtime `--check`, and `--demo --once`. Synthetic desktop
  smoke checks passed for preference autosave, log search/Copy/Clear, task progress,
  pause/resume/cancel, retry, repeat backups, and close while paused.
- Synthetic sign-in checks passed for missing-folder setup, password masking,
  keyboard submission, login/2FA errors and retries, close protection during a
  request, popup close/Cancel/Escape, successful unmount without accidental
  cancellation, saved-credential success, reconnection, and pending-fetch continuation.
- Inspected synthetic screenshots of the dashboard and popup. Verified a 380-pixel
  dashboard width without horizontal scrolling. Smoke scripts and screenshots are
  temporary local artifacts; no automated Qt widget tests were added.

Live-account verification remains open in TODO. No dependency, settings, or backup
migration is required.
