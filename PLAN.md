# Implementation plan

Implementation was authorized after this plan was prepared. Completion is recorded
only after verification. [todo.md](todo.md) remains the source of truth for outstanding
work. Follow [AGENTS.md](AGENTS.md) for safety and verification requirements;
[README.md](README.md) describes the documented current behavior.

The user has emptied the old vault. Start with an empty vault; migration of old
exports is out of scope. Backup preservation and recovery guarantees still apply
to subsequent fetches.

## Completion and verification

Phases 1–7 are complete: architecture reviewed/refactored, existing rich Markdown
and incremental retrieval verified, filenames updated, zone limitations investigated,
and direct Markdown writes implemented. Phase 8 passed 109 logic tests, runtime
`--check`, `--demo --once`, and a synthetic desktop smoke check for attachment
autosave, progress, pause/resume, cancellation, failure/retry, repeat backups, and
closing while paused. No GUI interaction tests were added to the automated suite.

Live-account sign-in, 2FA, session expiry/reconnection, and actual iCloud downloads
remain unverified; the manual-verification TODO stays open. Separate shared zones
and locked content remain unsupported, with warnings and retention verified using
synthetic records. Interrupted local saves require manual recovery as documented
in README; recovery copies and a durable marker prevent a new fetch from obscuring
the unfinished save. No old-vault migration was implemented or required.

The phases below retain their original objectives and acceptance criteria; the
decisions and completion record here describe the implemented outcome.

## Architecture review and implementation decisions

Baseline: 91 logic tests passed. GUI sign-in delegates to the authentication
controller; settings drafts delegate to disk configuration; both GUI and CLI call
`fetch_backup`. TaskManager reserves one operation and FetchControl protects the
save boundary. Dashboard's local state groups already match these responsibilities
and will remain local; extracting another state/controller layer is unnecessary.

Findings: providers currently combine rendering with temporary Markdown writes;
BackupController combines orchestration with JSON cache persistence; disk apply
combines validation, planning, and mutation in one long method. These obscure when
filesystem mutation is allowed and make export logic depend on temporary folders.

Chosen changes, before implementation:

- `provider_utils.py`: pure export construction, safe names, and a bounded buffer
  of rendered Markdown bytes (64 MiB per fetch, fail safely when exceeded).
- Providers: retrieval and format conversion; optional attachments stream to a
  temporary download directory without making a second staged attachment copy.
- `fetch_cache.py`: disposable cursor persistence and validation. BackupController
  owns sequencing, resource lifetime, cancellation boundary, and result recording.
- DiskVaultController: distinct existing-backup validation, snapshot planning, and
  local-save methods. Only this layer installs exports and updates Git.
- Preserve GUI/authentication/task boundaries; verify integrated desktop behavior.

Filename decision: `YYYY-MM-DD-<safe-title>-[<stable-id-hash>].md`, using modification
time converted to UTC (naive timestamps treated as UTC); missing or invalid dates
use `0000-00-00`. Keep the existing `notes/<folder>/` layout within the vault root.
No old-vault migration is needed. New Markdown is written directly to these final
paths after validation and the cancellation cutoff, with no Markdown staging files.
The memory limit bounds retained export bytes, not PyiCloud's transient responses.
Attachments remain streamed to temporary files only when requested. Existing Git
history and rollback protect subsequent saves; process-interruption recovery must
retain recovery data and refuse ambiguous overwrites.

PyiCloud 2.7.0 inspection: NotesService uses a fixed Notes zone for get, cursor,
and change operations. Its public change API omits protected/folder records; the
existing raw adapter includes them. Separate shared-zone export remains unsupported
and is reported explicitly; only confirmed tombstones permit deletion. Do not add
speculative shared-zone identity/cursor support without a reliable retrieval API.

## 1. Establish the baseline

- Review existing code and focused tests before implementing each backlog item.
  `markdown_export.py` already contains a Markdown converter, and
  `icloud_note_changes.py` and `icloud_notes_provider.py` contain incremental
  retrieval logic. Their presence alone does not establish completeness.
- Compare those implementations with the unchecked formatting and efficiency
  entries. Identify missing behavior and verification rather than rebuilding them.
- Verify the checked attachment option remains disabled by default and is passed
  consistently through settings, GUI, CLI, provider requests, and cache validation.
  Include its documented behavior when reconciling project records.
- Preserve unrelated working-tree changes. Keep all test notes synthetic.

Acceptance: each remaining item has a confirmed implementation gap or an explicit
verification gap; no item is checked off solely from code inspection.

## 2. Review architecture and refactor for clarity

- Map the current dependencies and trace sign-in, settings saves, and a fetch from
  GUI/CLI entry points through retrieval, rendering, local writes, Git, and result
  persistence. Include task ownership, cancellation, and shutdown boundaries.
- Review Dashboard complexity, controller responsibilities, provider coupling to
  export/storage details, shared models, and error/progress handling. Identify
  concrete duplication, mixed responsibilities, and implicit dependencies.
- Record findings and a proposed module/responsibility map in this plan before
  refactoring. Explain how each proposed change makes a workflow easier to follow,
  test, or change. Prefer straightforward functions and cohesive modules; introduce
  abstractions only where actual callers or duplicated logic justify them.
- Preserve local dashboard hooks, the reusable authentication component, the
  Qt-independent task manager, and shared GUI/CLI workflows. Keep credentials,
  configuration, runtime state, and persisted backup results distinct.
- Refactor in small, verifiable steps: clarify interfaces and ownership, extract
  pure rendering/planning logic where useful, consolidate duplicated behavior,
  simplify control flow, and remove obsolete indirection. Repair imports and
  callers together; avoid a wholesale rewrite or speculative framework.
- Consider the direct-write design in section 7 before settling export/storage
  interfaces. Establish the boundaries here, then implement each feature within
  its own phase so structural changes and behavior changes remain reviewable.
- Preserve single-operation reservation, UI-thread updates, cancellation/save
  boundaries, repository safety, noninteractive CLI behavior, and credential
  cleanup throughout the refactor.

Acceptance: the review records concrete findings, chosen changes, and their
rationale; responsibilities and dependencies are documented in AGENTS and README.
Existing logic tests pass after the refactor, with focused regression coverage
for meaningful gaps and synthetic desktop smoke checks for affected UI flows.
The resulting workflows have less duplication and clearer ownership without
unnecessary layers. Review and refactor completed; see the verification record above.

## 3. Complete richer Markdown exports

Primary files: [markdown_export.py](src/notesvault/markdown_export.py),
[icloud_notes_provider.py](src/notesvault/icloud_notes_provider.py), and
[provider_utils.py](src/notesvault/provider_utils.py).

- Review conversion and provider integration for headings, emphasis, links,
  lists/checklists, code, tables, line breaks, and attachment references.
- Preserve readable text for unsupported markup and report meaningful fidelity
  limitations. Do not silently treat inaccessible content as an empty note.
- Keep YAML metadata and Markdown escaping safe for arbitrary synthetic titles
  and bodies; keep output deterministic between identical fetches.
- Increment `EXPORT_VERSION` when the resulting export behavior changes.

Acceptance: focused cases in `tests/test_markdown_export.py` and
`tests/test_provider.py` establish supported formatting, fallback behavior, and
repeatable output; unchanged notes re-export after a format-version change.

## 4. Define dated filenames

Primary files: `provider_utils.py`, provider metadata mapping, and
[disk_vault_controller.py](src/notesvault/disk_vault_controller.py).

- Interpret the backlog's `<YYYY-MN-DD>` as a proposed `YYYY-MM-DD` date prefix.
  Before implementation, settle whether the date uses creation or modification
  time, the timezone, and the deterministic fallback for missing timestamps.
- Proposed basename: `YYYY-MM-DD-<safe-title>-[<stable-id>].md`. Confirm whether
  `<NOTEID>` means the existing stable ID hash or a safely encoded source ID.
  Preserve identity across title/date changes and prevent path collisions.
- Retain Windows filename safety and path-length limits. Keep the current folder
  layout unless the direct-write design explicitly requires a layout change.
- Generate the new filenames on the first backup into the empty vault. No legacy
  filename migration is needed. On subsequent fetches, protect local edits,
  unrelated files, attachments, and Git history when titles or dates change.
- Invalidate cached exports for the naming change.

Acceptance: `tests/test_backup.py` covers the first backup into an empty vault,
rename, collisions, missing dates, unsafe titles, and repeated backups without
duplicates or empty commits.

## 5. Investigate shared zones and locked notes

Primary files: [icloud_note_changes.py](src/notesvault/icloud_note_changes.py),
`icloud_notes_provider.py`, and [models.py](src/notesvault/models.py).

- Inspect the installed PyiCloud 2.7.0 interfaces and synthetic record shapes to
  establish which zones and protected-note records can be enumerated reliably.
- Distinguish confirmed deletion from locked, unsupported, inaccessible, and
  incompletely enumerated content. Retain existing exports for these cases.
- If separate shared zones are feasible, design zone-aware identities, cursor
  state, and completeness tracking before adding support. Otherwise document
  the limitation and surface safe warnings without promising full coverage.
- Do not attempt to bypass note protection or add two-way synchronization.

Acceptance: provider tests cover locked records, inaccessible zones, incomplete
pagination, identity collisions across zones, and retention of earlier exports
where applicable. Remaining unsupported behavior is explicit in README and TODO.

## 6. Finish incremental backup verification and gaps

Primary files: `icloud_note_changes.py`, `icloud_notes_provider.py`, and
[backup_controller.py](src/notesvault/backup_controller.py).

- Verify that unchanged exports are reused when other notes change, and that
  only changed/new notes require content downloads where the adapter supports it.
- Cover confirmed deletions, folder changes, locked/skipped notes, and a remote
  change occurring during retrieval. Never infer deletion from a partial listing.
- Fall back to a complete scan for invalid/expired cursors, missing or corrupt
  cache state, incompatible export versions, or changed export options.
- Preserve account and manifest validation, repository integrity checks, and
  cursor persistence only after a successful complete local backup.

Acceptance: `tests/test_incremental.py`, `tests/test_service.py`, and provider tests
assert download counts as well as resulting files, deletion safety, failed-commit
recovery, cancellation, and cache advancement. Update the README's current
changed-cursor/full-fetch description only after the final behavior is verified.

## 7. Design direct writes before removing staging

The request to skip staging conflicts with the current guarantee that cancellation
discards unfinished downloads while preserving exports. Resolve this in the design
before changing the retrieval/save boundary.

- Clarify whether “vault's folder” means writing within the selected backup root
  using the current `notes/` layout or placing Markdown at the root itself.
- Separate Markdown rendering from file installation so downloads and rendering
  cannot overwrite committed exports before a complete snapshot is validated.
- Evaluate buffering Markdown until the protected save phase, then writing it
  directly to final managed paths. Specify a practical memory bound and safe
  behavior when that bound is exceeded; do not silently introduce unbounded use.
- Define attachment handling independently. Optional large downloads still need
  a safe temporary destination or another explicit recovery strategy.
- Preserve repository locking, local-edit checks, history before replacement,
  rollback on failed saves, and the atomic cancellation cutoff before local writes.
  Account for process interruption as well as ordinary exceptions.
- If safe direct writes require relaxing existing guarantees, record the concrete
  tradeoff for user decision before implementing that behavior.

Acceptance: failure and fetch-control tests prove unchanged exports, manifest,
cache, and last result after cancellation; safe cleanup on close; and recoverable
Git failures. No writes occur outside managed paths. Update the architecture
documentation only after the final storage strategy is implemented and verified.

## 8. Verify and reconcile records

- Run focused logic tests for each implementation change, then the full suite:
  `.venv/Scripts/python.exe -m pytest`.
- Run `.venv/Scripts/python.exe -m notesvault --check` and a synthetic
  `--demo --once` backup for integrated runtime and backup changes.
- For desktop changes, use a synthetic `--demo` smoke check covering attachment
  settings, progress, retry, pause/resume, cancellation, and safe close. Do not
  introduce Qt widget or GUI interaction tests.
- Keep live-account verification separate: sign-in, code-based 2FA, session
  expiry/reconnection, fetching, and controls during downloads remain unverified
  until exercised with an available account. Never put credentials or real notes
  into tests, logs, screenshots, or project records.
- Check off TODO entries only after their acceptance checks pass. Record completed
  behavior under Unreleased in [changelog.md](changelog.md), noting that no old-vault
  migration is required for this scope, and reconcile README and AGENTS with the
  final implementation.

The initial plan was documentation only. Implementation and synthetic verification
have now been completed; live-account verification remains open.
Publishing, two-way sync, and unrelated experiments are outside this plan's scope.
The architecture review builds on the completed refactors listed in TODO.
