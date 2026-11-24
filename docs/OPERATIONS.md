# Operations and recovery

## Where each part runs

- **Mac:** Garmin credentials, raw data, SQLite, scheduled sync and dashboard generation. MCP
  runs over stdio when the desktop client starts `garmin-mcp`; this is not a public HTTP API or
  a permanent background web service. Keep database and credential directories private to the owner.
- **Cloud development environment:** checkout, tests and synthetic fixtures. It is not the
  production Garmin service. Do not copy the owner's credentials/database here to make tests pass.
- **Optional Cloudflare Pages:** only the generated HTML snapshot, protected by Access. It keeps
  serving the last uploaded snapshot when the Mac is off; it cannot pull new Garmin data itself.
  Production and preview addresses both need protection. See MAC_SETUP for activation checks.
- **Remote MCP, if needed later:** remains a design item. A future HTTP transport needs TLS,
  authenticated single-user access, authorization per tool, explicit handling of workout writes,
  secret storage, backups and monitoring. A Pages login is not automatically MCP authorization.
  Do not expose the existing stdio server through an unauthenticated public tunnel.

## Completion and retries

Sync marks `sync_retry_required` before source work. Only after all requested sources finish
without endpoint errors, skipped authentication or aborts, and normalization finishes, does it
record `last_full_sync` and clear the retry flag. Dashboard/publishing failures remain separate
from data-fetch completion. A retry does not bypass the existing rate-limit backoff.

Old endpoint logs are retained for diagnosis but are not completion evidence. The first run
after this migration fetches normally once; there is no destructive migration of raw data.
An unavailable requested source means the next scheduled run retries, so fix expired login
rather than interpreting a skipped source as fresh data.

Activity pagination rejects an identical repeated page and stops with an explicit error after
1,000 pages of 100 activities. The cap prevents endless requests; it does not silently return
the first 100,000 items as complete history. Range chunks must have a positive size. Other
date/record loops advance a date or bounded index; rate-limit retries already have a budget.

## Code-update failure

The updater saves a per-checkout pending-install marker in the data directory before changing
code. It never re-executes the sync after a failed pip install. The next scheduled execution
retries installation even when Git has no new commit; a failed Git fetch does not permit an
unresolved install to be treated as ready. Success clears the marker and restarts on the installed
code. Git remains fast-forward-only and local tracked edits are preserved.

If repeated installs fail, the local assistant should inspect the actual pip failure on the
Mac, repair the prerequisite, and run the normal install/tests. Do not delete the marker merely
to suppress the error, disable TLS verification, or reset the checkout over local edits.

## Backups and rollback

Back up the data directory before substantial data/normalization changes. Because SQLite uses
WAL, copying only `garmin.db` while writers are active can omit committed changes. Prefer
SQLite's online backup API (`sqlite3.Connection.backup`) or stop writers and perform a consistent
backup. Keep backups private; the generated dashboard is health data too.

For a code regression already merged, revert the specific change through a tested PR. Avoid
rewriting main: the Mac follows main automatically. Repository rollback does not require
discarding raw Garmin payloads, which permit analytics to be rebuilt. Live restore and Mac
restart behavior still need device testing; synthetic tests do not prove backup restoration.

## PR governance

Use `chatgpt/<topic>` branches, never direct pushes to main. PR checks run on Python 3.12 and
3.13; merge only the tested head. GitHub API and Git transport are separate access paths. If API
access is denied, add `api.github.com` in the cloud environment's Internet/network allowed
domains and apply the setting. A repository edit cannot remove an external egress restriction.

## Output, provenance and privacy follow-up (v0.14.1)

A returned `loads_error` from normalization counts as an incomplete sync and retains the retry
flag. Athlete-setting responses expose recalculation failure. `data_coverage.last_full_sync`
and MCP `last_successful_sync` mean complete source/normalization success; legacy `last_sync`
is still the last request-run log and must not be used as a freshness guarantee.

New POSIX SQLite/HTML files use 0600 and new data/FIT/dashboard directories 0700; no chmod is
applied to existing paths. Check permissions of pre-existing data/backups separately. Atomic
HTML replacement preserves the old file on failure; an iCloud error warns and leaves local
output available. Empty databases now render a waiting dashboard rather than crashing.

Requested MCP results may leave the Mac through the selected AI client/model provider.
Cloudflare Access protects reader access; the HTML is still stored by Cloudflare. Keep the
optional upload disabled until the owner has configured both protected hostnames and checked
anonymous denial, owner login and phone navigation.

## Archive verification (v0.14.3)

Use `garmin-mcp-verify --run-timing` on the Mac for a read-only annual summary of paired
FIT sample span vs Garmin elapsed time, recorded moving time vs Garmin timer time, and
moving HR vs Garmin activity HR. The named differences can reflect timing definitions and
sampling. They are useful diagnostics for older exports, recent syncs and gaps, without an
automatic claim of agreement or sensor accuracy. The ordinary data-quality verifier still
covers unit ranges/source mappings and rebuilds tidy tables.

## Offline monthly replay

Use `garmin-mcp-verify --replay-dashboard` on the machine holding the Garmin archive.
Replay samples the latest recorded day in up to 36 months from a temporary SQLite copy.
It checks structural dashboard links and duplicate IDs. The result includes how many months
had evidence for a coaching comparison. It does not render a live report, publish anything
or run the model. The original archive stays read-only. See the
[repository review](REPOSITORY_REVIEW.md) for fixture results and remaining checks.
This is a structural replay. Some long-term panels read settings or records from the
current archive, so use a separate as-of dataset for time-isolated model or forecast evaluation.
