# Handover prompt for ChatGPT

Paste everything below the line into ChatGPT, with access to the GitHub repo `PrahladRajhans/Garmin-tracking` (branch `main`).

---

You are taking over an existing, working software project from another AI assistant (Claude). Your job is to understand it fully before changing anything, then continue building on it. Do not guess. If something isn't in the repo or in this prompt, say so and ask me, or look it up and cite the source. Never invent formulas, norm values, API fields, file names or function names. Check every file and function you mention against the repo.

## 1. Who I am and what I want
- **Me:**
  - Male, 29, 76.5 kg, Mohali, India (time zone Asia/Kolkata).
  - Garmin Forerunner 955, wrist heart rate only (no chest strap).
  - Right knee a little weak.
  - No goal race. General fitness now, maybe a marathon some day.
  - Max HR not tested yet; I'll do the test later.
  - I sync my phone with Garmin Connect about twice a day (after waking and at night).
  - I use a Mac (Python 3.15 installed). I'm not a developer: don't ask me to paste code or run long terminal sequences. If something must run on my Mac, give me one short command and say exactly what it does.
- **Vision:** a free, private, transparent alternative to paid Garmin AI connectors (Fitness AI Connector, AthleteData) and to the insights in Whoop, Oura, Fitbit, Bevel, Strava Athlete Intelligence, Garmin Active Intelligence and Runalyze.
  - **Collect:** pull *all* my Garmin data with full history into a local database.
  - **Compute:** transparent, sense-checked analytics. Every number traceable to a written formula and its inputs; Garmin's own values shown beside ours, never mixed in.
  - **Use:** ask an AI through MCP tools, and look at a simple, glanceable dashboard.
- **How I want you to work:**
  - Truth over confidence: mark uncertainty and cite primary sources.
  - Plain language on anything I see. Say "fitness", not "CTL"; "how sure", not "r/CI"; no "L1/L2" jargon.
  - Fix root causes, not symptoms.
  - Keep ONE plan (`ROADMAP.md`).
  - Update the docs with every change.
  - Don't bother me with small things. Fix your own mistakes.

## 2. Read these first, in this order
1. `HANDOVER.md`: goal, story, why, a reference table for every calculation (code location → formula → source → METRICS section), dashboard references, exact differences from Garmin and other apps, known issues, and what's left. **This is the most important file.**
2. `AGENTS.md`: rules for AI contributors (the same rules are in `CLAUDE.md`).
3. `ARCHITECTURE.md`: data flow diagram and module map.
4. `ROADMAP.md`: the single plan. It covers phases 1–13 (all done), Phase 14 (waiting on inputs), the needs-from-user table, the backlog, dropped items with reasons, and problems caused by incomplete data.
5. `METRICS.md`: every formula, grouped by version, plus the sense-check table, the HRmax policy and the open max-HR question.
6. `DASHBOARD_PLAN.md`: platform decision, what we copied from which app, design rules, UI map (§6), design system (§7), hosting (§8).
7. `CHANGELOG.md`: every change per version, including real-data findings.
8. `README.md`: install, the table of all 43 MCP tools, sync, configuration.
9. `research_notes/Garmin connector feature research/`: the research behind decisions.
   - Start with `FINDINGS.md`.
   - Then `running_form_benchmarks.md` (Garmin form bands, Runalyze Marathon-shape source, running effectiveness, cadence and knee studies).
   - Then `metric_formulas.md`, `fitbit_whoop_bevel.md`, `insights_and_dashboards.md`, `garmin_insights_reference.md`, `VERIFICATION_LOG.md`.
10. `docs/screenshots/`: what the dashboard looks like now.

## 3. The system in brief (verify in the repo)
- **Stack:**
  - Python ≥ 3.12, SQLite.
  - MCP SDK **2.x**: `from mcp.server.mcpserver import MCPServer`, **not** FastMCP.
  - `garmin-fit-sdk` for FIT files.
  - Garmin's official Personal API (key; rate limit about 100 requests per window, HTTP 429 with `retryInSeconds`).
  - The unofficial `garminconnect` library.
  - The one-time Garmin account export ZIP.
- **Package:** `src/garmin_mcp/`. Commands:
  - `garmin-mcp`: MCP server.
  - `garmin-mcp-sync [--days N] [--force]`: sync.
  - `garmin-mcp-import <zip>`: import the account export.
  - `garmin-mcp-verify`: checks.
  - `garmin-mcp-dashboard`: build the dashboard.
- **Data flow:** sources (`sources/personal_api.py`, `sources/garminconnect_source.py`, `importer.py`) → raw tables (`raw_daily`, `raw_range`, `activities`, `fit_*`; stored verbatim) → `normalize.py` (tidy tables: `daily`, `sleep`, `hrv`, `health_status`, `readiness`, `training`, `race_predictions`, `fitness_age`, `fitness`; Personal API > unofficial > export, merged field by field) → analytics modules → `server.py` (43 tools) and `dashboard.py`.
- **Analytics modules:**

  | Module | What it covers |
  |---|---|
  | `recovery.py` | Readiness, HRV status, sleep debt, illness flag, suggestion, activity status |
  | `loads.py` | HRmax policy, TRIMP, fitness/fatigue, pace curve, critical speed, effective VO2max, race predictions, sense checks |
  | `coaching.py` | Per-run metrics, glossary, fitness-age levers |
  | `running.py` | Garmin form bands, form compared at the same pace, what to work on, test-run tracking |
  | `health.py` | Sleep breakdown, heart-rate dip, pace of ageing, shift detection, monthly report, Marathon shape |
  | `scores.py` | Recovery %, Sleep %, Strain 0–21, bedtime, recovery weighting study |
  | `engine.py` | Relationships with block-bootstrap CIs and Benjamini-Hochberg control, explorer, trends, personal ranges, insight feed |
  | `goals.py` | Goal-race check |
  | `workouts.py` | Structured workouts sent to the watch |
  | `athlete.py` | Settings, notes, tags |
- **On my Mac:**
  - The repo is at `~/Garmin-tracking`. Data lives in the hidden folder `~/.garmin-mcp/` (database `garmin.db`, dashboard `dashboard/index.html`), unless `GARMIN_DATA_DIR` is set.
  - launchd runs `garmin-mcp-sync --days 3` every 3 hours.
  - Before syncing, a gate (`sync.gate`) checks: full sync only if ≥ 11 h have passed since the last one, or today's activity list shows a new activity.
  - Each sync fast-forwards the repo to `origin/main` (`autoupdate.py`), so merged changes reach my Mac automatically.
  - Settings come from `config/athlete.json`.
  - After syncing, the dashboard is rebuilt and copied to `iCloud Drive/Garmin/dashboard.html` (only if iCloud Drive exists; not yet confirmed on my Mac).
- **Quality gates:**
  - `pytest` and `ruff check .` must pass. CI runs both on Python 3.12 and 3.13 (`.github/workflows/ci.yml`).
  - Real-data checks live in `verify.py`, `loads.sense_checks` and `scores.sense_checks`.
  - Current real-data agreement with Garmin:
    - Acute load r = 0.81.
    - Per-run load r = 0.92.
    - Sleep % vs Garmin sleep score r = 0.85.
    - Recovery % vs Garmin readiness r = 0.36 (explained in `HANDOVER.md` §9).
    - Running form within 0–1.2 % of Garmin's session values.
- **Dashboard (`dashboard.py`):**
  - One self-contained HTML file with no JavaScript and no CDN.
  - Pages are sections switched with CSS `:target`: Today, Sleep, Recovery, Training, Running (→ one page per run), Body, Patterns (correlations explorer).
  - Inline SVG charts with `<title>` tooltips; separate phone and desktop drawings (`both()`).
  - Design rules in `DASHBOARD_PLAN.md` §7: system font, 4 px spacing grid, 16 px card radius, 2 px lines, one y-axis per chart, status colours only with a word, palette validated for colour-blind safety in light and dark.

## 4. Known facts and pitfalls (don't re-break these)
- **FIT and Garmin conventions:**
  - FIT cadence is per foot: ×2 for steps per minute.
  - HR-zone upper bounds are exclusive.
  - FIT scale factors are already applied by the SDK.
- **Data quirks:**
  - Sleep records under 3 h are incomplete and are excluded.
  - Garmin uses −1 to mean "no data" for stress and Body Battery; it is filtered out.
  - `sleep.sleep_start` is UTC; convert to Asia/Kolkata (see `engine._tz`).
- **Max HR:**
  - The policy (`loads.thresholds`) gives 188: the repeatable observed peak (177) vs Tanaka 208 − 0.7·age, whichever is higher.
  - Garmin's model implies about 209.
  - This changes zones, load and effective VO2max (about 40 at 188 vs Garmin's 51.4).
  - It stays flagged until my test; then use the tool `update_athlete_setting("hr_max_override", value)`.
- **Wrist running power:** reads higher than Stryd. Use running effectiveness only to compare me with myself.
- **Thin running data:** about 1 km a week lately; Marathon shape is 1 %. That is correct, not a bug.
- **Statistics rules for patterns:** baseline-adjust, bootstrap CI, Benjamini-Hochberg q < 0.10 and |r| ≥ 0.15. Measured false-positive rate 1.7 %. Don't loosen this.
- **Recovery weights:** stay equal unless `recovery_weight_study` shows a variant better on both outcomes by > 0.05 r.

## 5. Original continuation brief

As of v0.14.3, Task A's publisher exists and awaits account/device activation. The primary-source
VO₂max bar and dashboard design follow-ups are implemented. Read ROADMAP and HANDOVER for the
current status and next work. The original brief below records the requirements.

### Task A: host the dashboard so I can open it on my phone, privately
- **The problem:** the file is built on my Mac at `~/.garmin-mcp/dashboard/index.html`. That's a hidden folder (press Cmd+Shift+. in Finder to see it). I want to open the dashboard from my phone, anywhere.
- **Constraints:** it is health data, so it must NOT be public. It must be free, update itself after each sync, and need no server I have to keep running if possible.
- **Evaluate these options:**
  1. **Cloudflare Pages + Cloudflare Access** (email one-time-code login). The sync step uploads the file with Wrangler. Recommended by Claude; verify the current free-tier limits.
  2. **Tailscale** (`tailscale serve`) from the Mac. Private, but only works while the Mac is on.
  3. The **iCloud Drive copy** that already exists in code (`dashboard.build`). Check whether it runs on my Mac and whether links work when opened in Safari from the Files app.
  4. A private Claude Artifact (manual, so not automatic).
- **Rule out:** public GitHub Pages, and any public URL.
- **Implement the chosen option:**
  - Add an optional step after `dashboard.build`, configured via environment variables or `config/athlete.json`. Never commit secrets.
  - Document it in `README.md`, `MAC_SETUP.md` and `DASHBOARD_PLAN.md` §8.
  - Give me the minimum one-time setup steps.

### Task B: VO2max range bar by age and sex (roadmap Phase 14)
- **Find the table:** a published, citable VO2max norm table by age and sex (e.g. ACSM's Guidelines for Exercise Testing and Prescription, Cooper Institute norms, or a peer-reviewed reference such as the FRIEND registry, Kaminsky et al.).
- **Record the source:** put the exact table and full citation in `research_notes/` and `METRICS.md`. If you cannot access the primary table, say so and stop. Do not reconstruct numbers from memory.
- **Show it:** a range bar on the Body page with my Garmin VO2max and our effective VO2max marked separately, with a caveat that ours depends on the untested max HR.
- **Plus:** add a test, a CHANGELOG entry and a version bump.

### Task C: review the dashboard design and improve it
- **Review against:** `DASHBOARD_PLAN.md` §4/§7 and `docs/screenshots/`.
- **The bar:** neat, clean, simple, readable. Inspired by Whoop / Apple Health / Fitbit / Garmin, not a copy. Think about line spacing, letter spacing, shape and icon spacing, line weights, and the right chart for each kind of data.
- **Constraint:** keep it script-free (a static HTML file generated by Python). Check at 390 / 768 / 1200 px in light and dark mode.

### Task D: keep the handover current
After each change, update `HANDOVER.md` (sections 6, 9, 10), `ROADMAP.md`, `CHANGELOG.md`, and `README.md` if tools changed.

### Not now
- Race readiness and taper: no goal race.
- Re-running the max-HR-dependent checks: after my test.
- Optional sources (intervals.icu, Apple Health): only if I ask.
- See `ROADMAP.md` "Explicitly not building" and "Planned earlier, now not relevant" before proposing anything; those were decided with reasons.

## 6. Working rules (from AGENTS.md / CLAUDE.md)
1. Every change gets a `CHANGELOG.md` entry. Update `README.md` when tools, setup or config change, and `METRICS.md` for any formula.
2. Run `pytest` and `ruff check .` before committing; CI must be green.
3. MCP SDK 2.x import as above.
4. Never commit credentials, API keys or token files (the Garmin Personal API key lives only on my Mac).
5. Sense-check new numbers against real data and Garmin's values. Check units and ranges.
6. When data is too thin, return `available: false` with a reason.
7. One plan: `ROADMAP.md`. Mark dropped items with the reason; never delete them silently.
8. Work on a branch, open a PR, merge to `main` when green. My Mac updates itself from `main`.

## 7. How to start
1. Read the files in section 2, then reply with a short summary: the system as you understand it, the plan, and any contradictions or gaps you found. Cite file and function names.
2. Ask me at most one clarifying question if something blocks you.
3. Then continue the first actionable item in ROADMAP.
