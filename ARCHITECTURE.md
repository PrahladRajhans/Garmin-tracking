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
          server.py (43 MCP tools)        dashboard.py (one HTML file, 7+ pages)
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
| `scores.py` | Recovery %, Sleep %, Strain 0–21, bedtime suggestion |
| `engine.py` | Insight engine: relationships with bootstrap CIs and FDR control, trends, patterns, feed |
| `goals.py`, `workouts.py`, `athlete.py` | Goals, structured workouts to the watch, athlete settings and notes |
| `dashboard.py` | Static multi-page dashboard (inline SVG, no JS) |
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
