# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
