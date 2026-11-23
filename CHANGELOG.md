# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.1] - 2026-11-23

Data-quality pass (serves every phase: correct inputs).

### Added
- `garmin-mcp-verify`: cross-source agreement (every overlapping field), plausible physical ranges per column and unit, FIT running-form averages, fill rates. Exit code 1 on any problem. On the real data: all checks pass.
- Regression tests for units and timestamp formats (24 total).

### Fixed
- **Floors:** the Personal API's `floorsAscended.value` is a floor count; we stored it as metres. Now uses `distanceInMeters`. Daily distance now also comes from the same block.
- **Sleep start/end:** export timestamps (`2026-10-25T00:08:45.0`) and API timestamps now share one format (`2026-10-25 00:08:45`, UTC).
- **Lap cadence:** laps now report steps/min (×2 of FIT one-foot cadence) like the activity average.

### Notes on earlier gaps (for the record)
- **SpO2 and Body Battery (fixed in 0.3.0):** values were never wrong, they were *missing*. The export stores them under different names (`averageSpo2Value`; a `bodyBatteryStatList` of HIGHEST/LOWEST), so before 0.3.0 only the 30 API days had them. Coverage went from 30 to 445 (SpO2) and 705 (Body Battery) days.
- **Resting HR (fixed in 0.3.0):** the export's `restingHeartRate` is a 7-day value; the day's own is `currentDayRestingHeartRate`.
- **Known upstream differences:** daily min/max HR and sleep average HR differ by 1–3 bpm between Garmin's own sources on some days (Garmin recomputes). The official API value is used.

### Changed
- `ROADMAP.md` rewritten as the single main plan: every item from the research backlog (R1–R34), METRICS.md and earlier plans mapped to a phase and version; side-quest rule added.

## [0.3.0] - 2026-11-23

Phase 2: tidy tables and health snapshot.

### Added
- `normalize.py`: tidy per-day tables (`daily`, `sleep`, `hrv`, `health_status`, `readiness`, `training`, `race_predictions`, `scores`, `fitness_age`) built from all three sources, merged field by field (official API > unofficial > export). Rebuilt automatically after every sync and import.
- `insights.py` + MCP tools `health_snapshot`, `daily_summary`, `activities`, `activity_detail`, `trend`. Flags: short sleep, HRV below baseline band, resting HR ≥5 bpm over the 60-day mean, Garmin readiness LOW/POOR, adverse training status, intensity minutes under 150/week, missing last-night sleep.
- `data_coverage` now reports the tidy tables.
- `MAC_SETUP.md`: one instruction for a local Claude Code session to set everything up on the Mac.
- Tests for normalisation and insights (22 total).

### Changed
- All tools now read the local database (the four original live-calling tools were replaced).

### Fixed
- Export daily summaries: resting HR now uses the day's own value (`currentDayRestingHeartRate`); `restingHeartRate` there is a 7-day figure. Found by cross-checking against the Personal API: now 29/29 days agree, as do steps, calories, intensity minutes, stress, Body Battery and all sleep fields.
- Garmin's `-1` "no data" values for stress and Body Battery no longer leak into the tables.


### Added
- `garmin-mcp-import`: imports the Garmin account data export (ZIP or folder). Verified on a real export: 116 activities with FIT files (May 2024 → Nov 2026), ~900 days of daily summaries, readiness, training status, race predictions, endurance/hill score and acute load, 382 nights of sleep, 286 days of health status. Export units (ms, cm, speed ×10) converted to API units and cross-checked against API data (exact match).
- Tests for the importer (18 total).

### Added
- Research verification pass: Garmin score bands, wrist running dynamics, LT chest-strap requirement (see VERIFICATION_LOG.md).
- Official Garmin Personal API source, built on Garmin's own `garmin-connect-personal-api-python` client: 6 daily datasets, 8 windowed datasets (fetched in 28-day chunks for the API's history caps), activities with pagination, original FIT download, automatic token renewal on 401.
- `--source both` (now the default): official API first, then only the extras the official API lacks from the unofficial library. Either source failing is reported without blocking the other.
- Tests for the Personal API source (14 total).

### Fixed
- Sync now waits and retries on HTTP 429. Garmin's Personal API allows ~100 requests per window and returns `retryInSeconds`; previously the run aborted. Waits are counted in `rate_limit_waits`.
- `--coverage` now lists windowed datasets (Body Battery, stress, steps, VO2max, etc.).

### Verified on real data (2026-11-23)
- Official Personal API: 30 days synced, 0 errors. Unofficial extras: 7 days, 0 errors.
- A watch-only FR955 records vertical oscillation, ground contact time and stride length in FIT records (previously assumed to need a chest strap). Beat-to-beat HRV is not recorded (HRV logging is off on the watch).

### Changed
- Python 3.12+ required (official Garmin client requirement).
- README: key setup via a private key file, source modes, what each source covers.

## [0.2.0] - 2026-11-23

Phase 1: data foundation.

### Added
- Local SQLite store (`~/.garmin-mcp/garmin.db`): raw responses kept verbatim, typed tables for activities, FIT records, laps, sessions, beat-to-beat HRV, sync log.
- Incremental sync engine and `garmin-mcp-sync` CLI: skips stored days (refreshes last 2), isolates failing endpoints, aborts after repeated failures, polite delay between calls.
- Source adapters: `garminconnect` (16 daily datasets, 6 windowed, 5 per-activity details + original FIT), `personal_api` placeholder until the endpoints are verified.
- FIT parsing with Garmin's official `garmin-fit-sdk`.
- MCP tools `refresh_data` and `data_coverage`.
- `METRICS.md`: per-metric decisions comparing Garmin's method, the scientific method, and ours.
- Tests for sync rules and FIT parsing (11 total).


### Added
- `ROADMAP.md`: decisions (local laptop, official API first + unofficial add-on, watch-only sensors) and 8-phase build plan.
- `research_notes/Garmin connector feature research/`: findings log for connector design (FR955 metrics, AI connectors, analytics platforms, metric formulas).
- `reports/Garmin connector feature research.md`: synthesized findings, FR955 data inventory, architecture recommendation, phased feature backlog.
- `connected_connectors_inventory.md`: full tool inventory of Fitness AI Connector and AthleteData.
- `github_and_garmin_resources.md` (GitHub libraries + Garmin official options), `garmin_insights_reference.md` (Garmin insight calculations vs open equivalents), `FINDINGS.md` (quick-read index).

## [0.1.0] - 2026-11-22

### Added
- Python package `garmin_mcp` with an MCP server (MCP Python SDK 2.x, stdio transport).
- Tools: `get_daily_summary`, `get_sleep`, `get_heart_rate`, `get_recent_activities`.
- Token-based auth via `garminconnect` 0.3.x; one-time `python -m garmin_mcp.login` with MFA support.
- `garmin-mcp` console script, `.env.example`, `.gitignore`.
- Unit tests (pytest) and lint config (ruff).
- README with setup, Claude Desktop / Claude Code config, and tool reference.
- This changelog.
