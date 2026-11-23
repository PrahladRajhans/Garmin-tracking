# Architecture

One person's Garmin data → local database → transparent analytics → Claude (MCP tools) and a dashboard.
Collection and analytics run on the user's Mac. The local dashboard needs no server.
An optional Cloudflare Pages copy can be enabled explicitly after Access setup; it is off by default.

```
                ┌──────────────────────── sources/ ────────────────────────┐
 Garmin watch → │ personal_api.py (official Personal API, key)             │
  (phone app    │ garminconnect_source.py (unofficial library, login)      │
   syncs it)    │ importer.py (one-time Garmin account export ZIP)         │
                └───────────────┬──────────────────────────────────────────┘
                                │ sync.py (gate → fetch → store raw verbatim)
                                ▼
                   SQLite  raw_daily / raw_range / activities / fit_* tables
                                │ normalize.py (field-by-field merge, units fixed)
                                ▼
                   tidy tables  daily, sleep, hrv, health_status, readiness,
                                training, race_predictions, fitness_age, fitness …
                                │
      ┌──────────────┬──────────┴───────┬──────────────┬──────────────┐
  recovery.py    loads.py          coaching.py    engine.py      health.py
  readiness,     TRIMP, fitness,   run metrics,   relationships, sleep parts,
  HRV status     VO2max, races     glossary       trends, feed   ageing, shape
      │          scores.py (Recovery %, Sleep %, Strain)   running.py (form)
      └──────────────┬──────────────────────────────────────┘
          server.py (45 MCP tools)        dashboard.py (one HTML file, 7+ pages)
                 │                                │
          Claude Desktop / Code           Safari on Mac, iCloud Drive on phone
```

## Data flow and timing
1. **launchd** runs `garmin-mcp-sync --days 3` every 3 hours on the Mac.
2. **Gate** (`sync.gate`): full sync only if ≥ 11 h since the last good sync, or today's activity list (1 cheap call) has a new activity. The user syncs the phone about twice a day, so this catches both.
3. **Self-update** (`autoupdate.py`) fast-forwards the repo to `origin/main` before syncing, and reinstalls if `pyproject.toml` changed. **Settings** are seeded from `config/athlete.json`.
4. **Store raw first**: every API response is saved verbatim (`raw_daily`, `raw_range`); FIT files are parsed into `fit_*` tables. Raw data is never overwritten by a lower-priority source.
5. **Normalize**: tidy tables are rebuilt from raw. Source priority is Personal API, then unofficial, then export, merged field by field.
6. **Rebuild derived**: `loads.rebuild` (thresholds, per-activity load, fitness), then `dashboard.build`.
   Sync, the dashboard CLI, and the MCP `build_dashboard` tool then call
   `publish.publish_if_enabled`: optional upload to an Access-protected Pages project. Upload
   errors are separate from the local build; no database or FIT files are staged.
7. **Verify** (`garmin-mcp-verify`): cross-source agreement, unit ranges, fill rates and sense checks against Garmin's own values.

## Module map (`src/garmin_mcp/`)
| File | Role |
|---|---|
| `config.py`, `db.py` | Paths, schema, coverage |
| `client.py`, `login.py` | Unofficial login, `today()` in the user's timezone |
| `sources/` | One adapter per Garmin source behind `base.py` |
| `sync.py` | Gate, fetch loop, 429 back-off, `garmin-mcp-sync` |
| `importer.py` | Account-export importer, `garmin-mcp-import` |
| `fit.py` | FIT parsing (records, laps, sessions, HRV, swim lengths, strength sets) |
| `normalize.py` | Raw → tidy tables |
| `recovery.py` | Readiness z-scores, HRV status, sleep debt, illness flag, suggestion |
| `loads.py` | HRmax policy, TRIMP, CTL/ATL/TSB, pace curve, critical speed, effective VO2max, race predictions, sense checks |
| `coaching.py` | Per-run metrics, run analysis, form trends, glossary, fitness age levers |
| `running.py` | Running breakdown: Garmin form bands, pace-matched form, what to work on |
| `health.py` | Sleep breakdown, HR dip, activity status, pace of ageing, shifts, monthly report, Marathon shape |
| `training_plan.py` | Seven-day starting plan shared by the daily MCP brief and Today |
| `scores.py` | Recovery %, Sleep %, Strain 0–21, bedtime suggestion |
| `engine.py` | Insight engine: relationships with bootstrap CIs and FDR control, trends, patterns, feed |
| `goals.py`, `workouts.py`, `athlete.py` | Goals, structured workouts to the watch, athlete settings and notes |
| `signal_context.py`, `dashboard_history.py` | Personal weekly comparisons with source coverage and year-bounded Garmin history for UI drill-downs |
| `dashboard.py`, `dashboard_interaction.py` | Single offline HTML dashboard with SVG charts and a hash-allowed inline script for chart controls, active navigation and theme |
| `norms.py` | Exact FRIEND 2015 age/sex reference lookup and comparison; no inferred profile or percentile interpolation |
| `publish.py` | Opt-in Pages upload, Access checks, check-only CLI; no account configuration writes |
| `server.py` | MCP server: every tool reads the local DB; only `refresh_data` calls Garmin |
| `verify.py`, `autoupdate.py` | Checks; self-update |

## Design principles
- **Transparent:** every number can be traced to a formula in `METRICS.md` and its inputs. Garmin's values are shown beside ours, never blended.
- **Honest about thin data:** results carry `calibrating`, `signals_used` or `available: false` with a reason, never a guess.
- **Raw first:** analytics can be recomputed from stored raw data at any time.
- **Private:** collection and analysis stay on the Mac. A dashboard copy leaves only when publishing
  is explicitly enabled (or a manual Artifact is requested). Access must protect all Pages addresses.

## Tests and CI
`pytest` (unit + small end-to-end on synthetic FIT data) and `ruff`, run on Python 3.12 and 3.13 by `.github/workflows/ci.yml`. Real-data checks run with `garmin-mcp-verify` on the Mac.

## Delivery boundaries and file lifecycle (v0.14.1)

SQLite/raw credentials stay on the Mac in production. MCP stdio returns requested tool results
to the desktop client, which may transmit them to its model provider. Optional Pages publication
sends a derived HTML health-data snapshot to Cloudflare; Access authenticates readers but does
not encrypt the content against the hosting provider. Cloud tests use synthetic data only.

New POSIX database and HTML files are owner-readable/writable (0600); newly created data/FIT/
dashboard directories use 0700. Existing paths retain owner-managed permissions. Each HTML
write uses a sibling temporary file followed by atomic replacement. iCloud write failure warns
without discarding the local build. This is file-replacement integrity, not a transaction across
all destinations. MCP provenance reads full-sync completion, not the latest successful endpoint.

## Run evidence and source windows (v0.17.0)

`run_evidence.matched_effort` uses the same FIT-derived `coaching.run_metrics` for MCP
and the dashboard. The dashboard reuses a bounded in-memory read cache across its
analyses. `readiness_benchmark` joins raw timestamped scores and prior-only match results.
`conditions` stores user-supplied UTC windows under a separate `activity_details` kind,
alongside existing Garmin weather. No SQLite migration or external client is needed.
Only rendered readings and their source labels enter the dashboard. CSV inputs and raw
FIT locations stay on the Mac. Any enabled snapshot publisher also includes that context.

## Dashboard refresh and daily coaching (v0.19.0)

`daily_focus.py` turns the same recovery and recent sleep measurements into the linked
focus returned by `daily_brief` and rendered on Today. The dashboard stays independent
of a model or network query. Sync persists a local render-pending flag before building
HTML. The Garmin fetch gate and HTML refresh are separate decisions. It compares the
version/build stamp of local and available iCloud snapshots, and retries rendering
without advancing the completed Garmin sync time.
