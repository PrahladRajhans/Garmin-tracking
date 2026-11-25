# What 30 Garmin and MCP projects teach us (and what to do about it)

**Status: proposals only. Nothing in this document has been built.** Section 12 was added the same day and covers a second opinion from Grok ([stored verbatim here](external/GROK_UI_UX_RECOMMENDATIONS_2026-11-25.md)). Written 25 November 2026 against
`main` at v0.33.0 by Claude, at the owner's request. The owner will pick items up later, so every item
says what it depends on, where it goes and why.

This complements, and does not replace, [GARMIN_ECOSYSTEM_REVIEW.md](GARMIN_ECOSYSTEM_REVIEW.md)
(ChatGPT's ledger of 40 links, mostly about archive coverage and CSV export). This one asks
different questions: **architecture, login risk, MCP design, a standalone (no-Mac) direction, ways
of working, and the Trends page.** Where the two overlap, this document links to the ledger rather
than repeating it.

## 1. Summary

1. **The 30 links are mostly three kinds of thing:** Garmin MCP servers that mirror Garmin's API
   (1, 10, 20 and others), a few that compute analytics (3, 15, 27), and platforms or apps built around
   a database and a UI (12, 21, 30). Only about eight carry design ideas we do not already have.
2. **We are ahead on analytics and honesty, behind on packaging and portability.** Our computed
   metrics, evidence rules and local AI checks are deeper than anything in the list. Our delivery
   is tied to one Mac.
3. **The biggest systemic risk is login, not code.** Several projects report that Garmin's
   unofficial login keeps breaking (11, 16). Ours works today, but 14 Garmin-computed datasets
   (training readiness, training status, race predictions, endurance and hill score and others)
   exist **only** through that login. See [section 5](#5-the-login-risk-in-numbers).
4. **A standalone, no-Mac setup is feasible** (15 and 27 prove it on Cloudflare's free tier with the
   official Personal API), **but it costs those Garmin-computed scores and the local AI.** The
   decision should follow a cheap test (item M1 below), not precede it.
5. **`dashboard.py` is a hotspot.** It grew from 254 lines (v0.10) to 3,340 (v0.33). Two agents and
   one owner edit it in parallel. Splitting it is the enabling step for almost every other change.
6. **Trends is a menu, not a view.** It is four link cards. The tested trend code that would fill
   it already exists and is not used on that page. See [section 8](#8-the-trends-page-options).
7. **Process: documentation and version numbers are growing faster than the product.** 8,359 lines
   of Markdown against 17,578 lines of Python source, and 23 version numbers (0.17.0 to 0.33.0) in about two days.
8. **A Grok UI/UX brief agrees on the main product gap** (data and honesty are strong; the daily "what do I do?" layer is weak) **but ignores that the dashboard is a static file with no write path.** See [section 12](#12-second-opinion-groks-uiux-brief).
9. **Small safety gaps:** workout deletion is protected only by a sentence in a tool description;
   the Personal API key has no expiry reminder; the repository holds personal details (private
   today, which matters if it is ever shared).

## 2. How to read the evidence

| Label | Meaning |
|---|---|
| **Read** | I fetched the project's README on 25 Nov 2026 and read the passage cited. |
| **Intro only** | I read only the opening of the README. Claims about the rest are not made. |
| **Repo fact** | Measured or read in this repository at v0.33.0. |
| **Not verified** | A claim from a project's own README or a forum post that I did not test. |
| **Not reached** | The link did not load or I did not read it. No claim is made. |

I did not run any of the 30 projects, and I did not read their source code. Everything about them
comes from their READMEs, plus the Garmin forum thread. Vendor pages (6, 7, 25) are commercial and
are read as marketing, not neutral evidence.

## 3. What the 30 links teach (themes)

### 3.1 Designed tools beat mirrored APIs
- Project 3 (`endurancetools/garmin-mcp`) exposes **21 tools built around questions** ("review my
  week", "can I train hard today?"), reports that its tool list costs about 9,700 tokens of model
  context, and that the right first tool was chosen in 96 of 96 scenarios of its own evaluation.
  (**Read**, [README](https://github.com/endurancetools/garmin-mcp#why-garmin-mcp); the figures are
  the project's own and **Not verified**.)
- Project 1 (`taxuspt/garmin_mcp`) mirrors the library: **110+ tools** documented, **155 registered by
  default**, and adds *tool profiles* and allow/deny lists because that much context is heavy.
  (**Read**, [README](https://github.com/taxuspt/garmin_mcp#tool-filtering).)
- Project 20 (`ghighi3f/garmin-grafana-mcp-server`) is explicitly a "pure data access layer"; all
  interpretation is left to the model. (**Read**.)
- **Ours (Repo fact):** 57 tools. Measured size of names, descriptions and input schemas: about
  26,000 characters, roughly **6,500 tokens** (characters ÷ 4, an estimate). That is smaller per
  tool than project 3's reported figure, though the counting methods differ. **Tool-list size is not our problem.**
  What we lack is **evidence the right tool gets picked** (no selection test).

### 3.2 Answers that show their working
- Project 3 returns every answer with the values and rules used, in a `{ data, meta }` envelope
  where `meta.sync_hint` tells the model which date range is missing. (**Read**.)
- Project 15 (`KareemmSayed/Threshold`) states the same stance: "computed in code, rules shown".
  (**Read**.)
- **Ours (Repo fact):** `provenance` is added to every tool result (`server.py` `_provenance`):
  data-through date, last successful sync and the source order. That is good, but it does not tell the
  model *which requested days are missing*, which is the `sync_hint` idea.

### 3.3 Write actions need guards
- Project 3 gates deletes behind `GARMIN_ENABLE_DESTRUCTIVE=false` and shows workout steps before
  saving anything. (**Read**.) Project 27 is read-only. (**Read**.)
- **Ours (Repo fact):** `garmin_workouts(action="delete")` calls Garmin directly. The only guard is
  the sentence "Only delete when the user asks" in the tool description
  (`server.py`, `workouts.delete_on_garmin`). Preview-before-upload exists for `create_workout`.

### 3.4 Login is the fragile part
- Project 11 (`nrvim/garmin-givemydata`) says that in March 2026 Garmin added bot detection,
  that the `garth` library was deprecated on 28 March 2026, and that `python-garminconnect`
  authentication broke (its README cites an upstream issue, #332). (**Read**; **Not verified**.)
- Project 16 (`dsebastien/ai-skill-garmin`) says community libraries "break every few months when
  Garmin rotates endpoints, consumer secrets, or auth flows". (**Read**; **Not verified**.)
- Projects 15, 27 and 4 avoid the problem by using only the **official Personal API** with a key.
  Project 6's guide (athletedata, a commercial vendor) adds that the Personal tier is **pull only**,
  and has no Training or Courses API, so "a personal key cannot put a workout on your watch".
  (**Read**, [guide](https://www.athletedata.health/guides/garmin-personal-api-claude-chatgpt).)
- Project 7 (`missingmcp.com`) asks you to type your Garmin email and password into **its**
  sign-in page. (**Read**.) That is the opposite of our approach and of project 3's browser sign-in.
  **Do not use it.**
- **Tension with our own experience:** our unofficial login works today (the 365-day backfill
  finished with 0 errors). The risk is real but not currently biting us.

### 3.4a Demand signal (forum thread, project 2)
The Garmin Developer Forum request for an official MCP integration has **50 replies and about
80,900 views** (page header on 25 Nov 2026). Replies I read include users saying free third-party
MCP servers already work and speculation that Garmin may hold features back for Connect+.
**I saw no reply from Garmin staff in the part I read** and I did not read all 50. It tells us
people want this; it tells us nothing about Garmin's plans. (**Read**, partial;
[thread](https://forums.garmin.com/developer/connect-iq/f/discussion/437274/).)

### 3.5 Hosted and standalone patterns
| Pattern | Project | What it shows | Source |
|---|---|---|---|
| Free-tier cloud MCP, official API only | 15 Threshold | Runs on Cloudflare Workers; D1 archive with a read-only SQL tool; OAuth so Claude and ChatGPT **mobile** can connect; "your laptop does not need to stay on" | **Read** |
| Same tools local or cloud | 27 colincooperio/garmin-mcp | 29 read-only tools and 6 prompts, local or Cloudflare; Personal API key; ranges limited to 92 days (366 for summaries) | **Read** |
| One schema, many providers, own server | 12 the-momentum/open-wearables | Provider OAuth, background sync, webhooks, one unified schema in PostgreSQL, optional raw payloads to S3, one REST API, outgoing webhooks | **Read** |
| Server plus phone companion | 21 MBombeck/HealthLog | Postgres server, docker compose, **iOS companion app**, one timeline with life events above vitals; licence is PolyForm Noncommercial (do not copy code) | **Intro only** |
| Desktop app | 24 Wewoc/Garmin_Local_Archive | Windows standalone zip with GUI, built-in update check, local Ollama chat and an MCP tab; GPLv3 (do not copy code) | **Intro only** |
| Engine separate from API and UI | 30 askb/ha-garmin-fitness-coach-app | `packages/engine` is "pure TypeScript computation" behind an API; pages for Trends, Correlations, Sleep, HRV | **Read** (structure) |
| Device-agnostic "slots" | 23 BorisBW/claude-fitness-cn | The coach reads six slots (sleep, HRV, resting HR, energy, load, activities); **a new device is a row in a mapping table**; the readiness algorithm "degrades explicitly when a slot is missing" | **Read** |

### 3.6 Safety language and AI
- Project 17 (`dandwhelan/garmin-stats-ai`): "detects deviations from your own personal baselines — it
  does not diagnose"; the agent "will never say you are ill". Also warns the server has no built-in
  authentication. (**Read**.) We already follow the same rule (banned-word list in `narrator.py`).
- Project 9 (`leonzzz435/garmin-ai-coach`) uses a multi-agent LangGraph workflow with human-in-the-loop
  questions and cloud model providers (OpenAI, Anthropic, OpenRouter). (**Read**.) Our local-only
  approach is the stricter privacy position; their *human-in-the-loop questions* are the transferable part.
- Project 29 (n8n morning email) and project 28 (Telegram bot with a markdown/CSV library for
  ChatGPT) show **push delivery**: advice reaches you instead of waiting for you to open a page.
  (**Intro only**.)

### 3.7 Links with little or nothing for us
- 13 `AirspaceConverter` (aviation airspace file formats), 19 `pyG5` (an X-Plane cockpit display) and
  26 `s-ais` (inReach tracking to a ship-tracking site): **not relevant**. (**Read**, intros.)
- 14 `garmin-run-gsheets-sync` (last 20 runs to Google Sheets): nothing we lack; we have CSV export.
- 22 `python-garminconnect-aio`: an async wrapper. Our sync speed is limited by Garmin's rate limits,
  not our code, so async would not help. (**Intro only**.)
- 18 `GarminWorkoutAItoJSON`: a one-line text shorthand for workouts. See backlog item M7.
- 8 `adiesner/GarminPlugin`: **Not reached** (README not found on the default branches I tried).
- 5 (`mcpcursor.com` listing of another Garmin MCP) and 3's directory page: listing pages only
  (the second blocked automated access); the GitHub README was read instead.

## 4. Where we stand (Repo fact, v0.33.0)

| Area | State |
|---|---|
| Code | 17,578 lines of Python in `src/garmin_mcp/`; 437 tests pass; ruff clean; CI on Python 3.12 and 3.13 |
| Biggest files | `dashboard.py` 3,340 lines · `narrator.py` 1,097 · `deep_insight.py` 794 · `server.py` 806 |
| Documentation | 8,359 lines of Markdown across the root, `docs/` and `research_notes/` |
| Data (cloud copy, 23 Nov) | SQLite 45 MB, FIT files 11 MB: small enough to copy anywhere |
| Packaging | `pyproject.toml` only. **No Dockerfile**, no container or service definition |
| Mac-only parts | launchd job, `open`, the iCloud copy, the unofficial login, local Ollama |
| Dashboard file | about 4.9 MB uncompressed (about 0.57 MB compressed) against a 600 KB target; the owner's decision is open ([ROADMAP](../ROADMAP.md)) |
| Sources | Personal API first, unofficial library second, one-time export third; merged field by field (`normalize.py`) |

## 5. The login risk in numbers

`sources/personal_api.py` states what the official Personal API does **not** include:
*"NOT included: training readiness/status, race predictions, endurance/hill score, lactate
threshold, acclimation -> use the garminconnect source for those."* The unofficial source's
`EXTRAS` set (`sources/garminconnect_source.py`) lists 14 datasets that only it provides
(stress timeline, training readiness, training status, max metrics, respiration, intensity
minutes, Body Battery events, acclimation, floors, race predictions, endurance score, hill score,
lactate threshold, body composition).

On the 23 Nov cloud copy of the database, only **6 datasets** (daily summary, fitness age, heart
rate, HRV, sleep, SpO2) came from the Personal API, for the last 30 days. **13 datasets** came from
the one-time Garmin export, which is frozen at the export date. After that date, the
Garmin-computed scores can only be refreshed by the unofficial login.

**If that login stopped working:** Garmin's readiness chip, training status, race predictions,
endurance and hill scores and workout upload would stop updating. Everything we compute ourselves
(load, fitness, recovery, sleep, effective VO2max and race estimates, running form) would continue
to work from Personal API data and FIT files. That is a graceful degradation, but it is untested.

## 6. Improvement backlog, in priority order

Effort: **Quick** = hours, **Medium** = days, **Major** = weeks. "Depends on" lists what must exist first.
Items marked ⚠ touch `dashboard.py`, where ChatGPT is also working; coordinate order to avoid conflicts.

### Quick fixes (no dependencies; can ship independently)

| ID | Item | Where | Why |
|---|---|---|---|
| Q1 | **Rotate the Personal API key and add an expiry reminder.** Store the key's expiry date as a setting; warn on the dashboard footer and in `refresh_data` 14 days before. | `config/athlete.json`, `sync.py`, MAC_SETUP | The key was pasted into a chat early in the project and rotation was deferred ([ROADMAP](../ROADMAP.md), owner table). Keys expire (30 days to 1 year, per README), and expiry silently stops the official source. |
| Q2 | **Gate workout deletion** behind an environment flag (default off), like project 3's `GARMIN_ENABLE_DESTRUCTIVE`. | `server.py` `garmin_workouts`, `workouts.delete_on_garmin` | Today only a sentence in a docstring prevents a model from deleting a saved workout. |
| Q3 | **Confirm the repository is private and keep personal details out of shareable docs.** | GitHub Settings; `AGENTS.md`, `HANDOVER.md`, `docs/CHATGPT_HANDOVER_PROMPT.md`, `config/athlete.json`, real-data screenshots | Age, weight, injury and location are committed in several files. A request to `github.com` without login returned 404 on 25 Nov, consistent with private, but confirm in Settings. Any future sharing or open-sourcing needs a scrub first. |
| Q4 | **Report which requested days are missing** in every tool result (`meta.missing_ranges` / a `sync_hint`), not only the data-through date. | `server.py` `_provenance` | Lets the model say "I have no data for 14–17 Nov" instead of silently averaging around a gap. (Project 3.) |
| Q5 | **Trends hub: show content, not links.** See [section 8](#8-the-trends-page-options), Option A. ⚠ | `dashboard.py` `page_trends`, `engine.trends` | It is the most visible gap and uses code that already exists. |
| Q6 | **Version discipline.** Bump the version only for owner-visible releases; collect interim work under `[Unreleased]`. Add a plain-language "what changed for you" paragraph at the top of each release. | `CHANGELOG.md`, `AGENTS.md` | 23 version numbers in about two days make versions meaningless to the owner. |

### Medium (days; read the dependencies)

| ID | Item | Depends on | Where | Why |
|---|---|---|---|---|
| M1 | **Personal-API-only capability test.** Run the whole pipeline from Personal API data plus FIT files only, and list which dashboard cards and MCP tool fields go blank. Output: a capability matrix in `docs/`. | none | new read-only command, `normalize.py`, `verify.py` | This is the **decision gate for any standalone direction** and also tests graceful degradation. |
| M2 | **MCP tool-selection test.** A fixed list of about 30 owner questions with the expected first tool; run it on each release with Claude and record the hit rate. | none | `tests/` fixture, `docs/` | Project 3 reports 96/96; we have no figure. Catches overlapping or unclear tool descriptions (57 tools). |
| M3 | ⚠ **Split `dashboard.py` into a package** (`dashboard/today.py`, `sleep.py`, `training.py`, `running.py`, `trends.py`, `shared.py`) with no behaviour change. | 437 existing tests; **a pause in ChatGPT's dashboard edits** | `src/garmin_mcp/dashboard.py` | Needed before M4, M8 and any UI work to be safe and reviewable. Do it between ChatGPT's PRs, in one PR, with golden-HTML comparison before and after. |
| M4 | **Pure analytics core.** New analytics take plain data (lists, dicts) instead of a SQLite connection; a thin adapter loads data. Apply to new code first. | M3 (for the dashboard part) | `loads.py`, `recovery.py`, `scores.py`, `trials.py`, `engine.py` | Same pattern as project 30's `packages/engine`. Lets the same analytics run on a server, in a container, in tests or in a future app. |
| M5 | **Source-level availability contract.** Extend `reading_availability.py` so each reading says which source it needs and whether that source is working. | M1 | `reading_availability.py`, dashboard | Project 23's explicit degradation. Makes "Garmin training status unavailable (login)" a normal state instead of a blank. |
| M6 | **Installable web app (PWA) for the protected hosted dashboard.** Web manifest, icons and an offline cache so it opens from the home screen. | private hosting activated ([MAC_SETUP](../MAC_SETUP.md)); the file-size decision | `publish.py`, `dashboard.py` shell | Gets most of what a "standalone app" feels like for little work. **Not verified:** how Cloudflare Access sign-in behaves in an iOS home-screen app. Test on the phone first. |
| M7 | **Workout shorthand.** Accept a one-line text form ("6x400m @5k pace, 90s rest") that expands to our existing validated workout spec. | none | `workouts.py` | Project 18's idea. Easier to say to Claude; reuse existing validation. |
| M8 | **Push delivery.** One short daily message at the owner's wake time (verdict, the one action, the experiment's next step), by email or a notification service. | M5 (so it never sends stale advice) | new small module; opt-in | Projects 28 and 29. Advice that arrives beats a page that must be opened. Privacy: choose a channel whose provider sees only the short text, and say so. |

### Major (weeks; decision-dependent)

| ID | Item | Depends on | Why |
|---|---|---|---|
| J1 | **Hosted runner in a container** (see [section 7](#7-the-standalone-direction-no-mac)). | M1, M3, M4, M5 | Removes the Mac from the pipeline. |
| J2 | **Native phone app or server-plus-companion.** | J1 and a stable API | Only if a web app is not enough. Project 21 shows the shape. |
| J3 | **More providers** (Apple Health, Whoop and others) behind one schema. | J1 | Project 12's idea. Not needed for one Garmin user; park until a second device exists. |

### Parked (not worth doing now)

- **Tool profiles / allow-lists** (project 1): our 57 tools cost about 6,500 tokens. Revisit above about 100 tools.
- **MCPB bundle and MCP registry listing** (project 3): matters only for sharing with others.
- **Async library** (project 22) and **Google Sheets sync** (project 14): no benefit.

## 7. The standalone direction (no Mac)

### What the Mac does today
A scheduler (launchd), storage (SQLite and FIT files), analytics (Python), the unofficial login,
local AI (Ollama), delivery (the HTML file, the iCloud copy, the MCP server for Claude Desktop).

### What the references prove
- **Feasible without a Mac:** projects 15 and 27 run a Personal-API-only MCP server on
  Cloudflare Workers with OAuth, so Claude and ChatGPT on a phone can use it. (**Read**.) Both are
  TypeScript.
- **Not a free lunch:** the Personal API is pull-only with history limits, and has no readiness,
  training status or workout push (section 5; project 6).

### Options

| Option | How | Keeps our Python analytics? | Keeps local AI? | Effort | Main risk |
|---|---|---|---|---|---|
| **A. Container on a small always-on host** (VPS, Raspberry Pi or a free tier that does not sleep) | Add a Dockerfile; cron inside; volume for SQLite and FIT; private HTTPS (Cloudflare Access or Tailscale); remote MCP endpoint | **Yes, unchanged** | **No** on a small host (a 4B model needs several GB of memory and is slow on a cheap CPU) | Medium to major (J1) | Remote MCP for phone Claude needs OAuth, which is real work (Threshold built it). Costs and free-tier limits **not verified**. |
| **B. Rewrite on Cloudflare Workers + D1** (Threshold's model) | Port analytics to TypeScript | **No** (17,578 lines to port) | No | Major | Throws away our main asset. Cloudflare's Python Workers support and D1 size limits are **Not verified**. |
| **C. Keep the Mac as the engine, host only the results** | Already built: HTML to Cloudflare Pages behind Access | Yes | Yes | Already done; needs activation and phone checks | Mac must be on at sync times |
| **D. Hybrid** | A for sync, storage and rule-based advice; the Mac, when on, adds the optional AI summaries | Yes | Partly | Major | Two places to keep consistent |

### The two real conflicts
1. **Login.** A server cannot do an interactive password or MFA login. It must use the **Personal
   API only** (section 5), so item M1 comes first. Seeding is straightforward: copy the database and
   FIT files once from the Mac, then let the server take over.
2. **Private local AI versus "no Mac".** The narrator's privacy depends on the model running on
   your own hardware. A hosted version must either skip the AI (rule-based text remains), run a
   model on a more expensive host, or send facts to a hosted model (a privacy trade-off the owner
   must choose; it should stay opt-in).

### Recommendation
Take the path with least regret, in this order: **M1** (measure the cost of going Personal-API-only),
then **M3 and M4** (make the code portable), then **A** (container) if M1's result is acceptable.
Do **not** do B. In parallel, **M6** gives the "app on my phone" feel with little work. Treat the AI
as an optional extra that runs where a model is available.

### How the 30 links help with this
They give **patterns**, not code to reuse (several are copyleft or non-commercial licences; ours
is private): the Personal-API-only cloud shape (15, 27), the engine/API/UI split (30), the
unified-schema-and-webhooks shape (12), the phone-companion shape (21) and the slot-based
degradation (23). The 110-tool mirrors (1, 10) do not help; more tools is not the gap.

## 8. The Trends page: options

**Finding (Repo fact).** `page_trends()` in `dashboard.py` returns four link cards (Recovery, Body,
Patterns, History) and no data. `engine.trends()` already computes a Theil-Sen slope per 30 days
with a bootstrap confidence interval for six metrics (resting HR, HRV, sleep, VO2max, fitness,
steps) over 90 days and marks a trend "flat" when the interval includes zero. **The dashboard does not call it.**
Also unused on the dashboard: `engine.calendar`, `engine.records`, `engine.streaks`,
`engine.weekday_patterns`, `health.shifts` (lasting step changes). The Patterns page shows
relationships but not trajectories, which is probably why Trends feels "limited and random".

**Constraint.** The file is already about 4.9 MB. Trends should use **weekly** values (about 26 to 52
points per metric), not daily series.

**What references do.** Project 30 offers 30/90/180/365-day rolling averages with regression and a
"6+ year multi-metric" overlay page. (**Read**.) Project 21 puts life events on lanes above vitals.
(**Intro only**.) Project 3 states methods with citations.

| Option | What you would see | Built from | Effort | Notes |
|---|---|---|---|---|
| **A. Trend board (recommended first step)** | About ten tiles: resting HR, HRV, sleep, sleep timing, steps, training load, VO2max, weight, stress, Body Battery. Each shows this week's value, the change versus 4 weeks ago, a verdict ("improving", "steady", "worse") with the confidence rule, and a 26-week sparkline. Tiles are ordered by **what changed most**. | `engine.trends` (extend its metric list), weekly means | Quick to medium | "Improving or worse" must account for direction per metric (lower resting HR is better; higher HRV is better; weight is neutral). |
| **B. Then versus now** | This month, last month and the same month last year side by side for the headline numbers. | `health.monthly_report` extended | Quick | Needs at least 13 months of data; say so when it is missing. |
| **C. Questions, not metrics** | Four questions with an answer and one chart each: *Am I getting fitter?* (VO2max, speed per heartbeat on comparable runs, resting HR) · *Am I recovering better?* (HRV, resting HR, sleep) · *Am I consistent?* (sessions per week, streaks) · *Is my sleep improving?* (duration, wake-time spread) | Existing tested functions | Medium | Reads like a coach. Needs plain-language answers with their evidence and limits. |
| **D. Period and metric picker** | Choose 30 days, 90 days or 1 year; choose metrics to overlay. | the existing chart script | Medium | Pre-render three windows to keep the page offline and small. Free-form overlays risk implying causes; keep to one axis per chart. |
| **E. "What changed it?" annotations** | The same charts with markers where you tagged sick/travel/alcohol, started an experiment, or where `health.shifts` found a lasting change. | `athlete` tags, `trials.py`, `health.shifts` | Medium | Turns a trend into an explanation. This is something Garmin Connect does not offer. |
| **F. Calendar heat map** | A year grid colouring days by sleep, training or recovery. | `engine.calendar` | Quick | Good for consistency; not for magnitude. |
| **G. Monthly report card** | One page per month with a few grades against your own baseline (not a population). | `health.monthly_report` | Medium | Only meaningful with caveats; avoid letter grades that imply precision. |

**Suggested order:** A, then E, then C. Keep F as a small add-on. Tests: each tile's verdict logic
(direction, flat when the interval includes zero), and "not enough data" states.

## 9. What could be implemented now

All three are independent of the standalone decision and of each other.

1. **Trends board (Q5, Option A)** with the "what changed most" ordering. Directly addresses
   the owner's complaint. Uses existing, tested code. Small file-size impact with weekly data.
2. **Capability matrix (M1).** A read-only command, no behaviour change. It turns the standalone
   question from opinion into a measurement.
3. **Safety and visibility fixes (Q1, Q2, Q4).** Small, test-covered, and each reduces a real
   risk found in this review.

Recommended first release: **1 + 3**, then **2**, then decide on J1.

If the owner wants the UX direction from section 12 first, the cheapest start is the **Today hero rewrite plus a single trust indicator** (items G1 and G2), which need no new data, no hosting and no new dependencies.

## 10. Ledger of the 30 links

Numbers follow the owner's list. "Depth" uses the labels in section 2.

| # | Link | What it is | Takeaway for us | Depth |
|---:|---|---|---|---|
| 1 | [taxuspt/garmin_mcp](https://github.com/taxuspt/garmin_mcp) | Large MCP server mirroring the unofficial library (110+ documented, 155 registered tools), write tools for activity feel/RPE and workouts | Tool profiles exist because mirrors are heavy; write tools exist. Neither is our gap. | Read |
| 2 | [Garmin forum request](https://forums.garmin.com/developer/connect-iq/f/discussion/437274/) | Request for an official MCP integration; 50 replies, about 80,900 views | Demand signal only; no Garmin reply seen | Read (partial) |
| 3 | [mcpservers.org listing](https://mcpservers.org/servers/endurancetools/garmin-mcp) → [endurancetools/garmin-mcp](https://github.com/endurancetools/garmin-mcp) | 21 question-shaped tools, local SQLite cache, citations, destructive-action flag, envelope with `sync_hint`, evaluation of tool choice | Best design reference: Q2, Q4, M2 | Read (README; listing page blocked) |
| 4 | [LobeHub: mijndert/garmin-mcp](https://lobehub.com/nl/mcp/mijndert-garmin-mcp) → [repo](https://github.com/mijndert/garmin-mcp) | Small read-only server on the Personal API key; key shown once, chosen lifetime | Confirms key expiry matters (Q1) | Read |
| 5 | [mcpcursor listing](https://mcpcursor.com/server/garmin-connect-mcp) | Directory entry pointing to another Garmin MCP server | Nothing beyond what 1 and 10 show | Listing only |
| 6 | [athletedata guide](https://www.athletedata.health/guides/garmin-personal-api-claude-chatgpt) | Vendor explainer of the Personal API | Pull-only; no Training API so no workout push; Garmin returns raw records. Commercial source. | Read |
| 7 | [missingmcp.com/garmin](https://missingmcp.com/garmin) | Hosted MCP server asking for your Garmin email and password on its own page | **Avoid** (password leaves your control). Commercial. | Read |
| 8 | [adiesner/GarminPlugin](https://github.com/adiesner/GarminPlugin) | Not reached | No claim made | Not reached |
| 9 | [leonzzz435/garmin-ai-coach](https://github.com/leonzzz435/garmin-ai-coach) | CLI that produces an HTML analysis and a season plan with a multi-agent workflow, cloud model providers | Human-in-the-loop questions are transferable; cloud providers conflict with our privacy rule | Read (intro) |
| 10 | [Nicolasvegam/garmin-connect-mcp](https://github.com/Nicolasvegam/garmin-connect-mcp) | 61-tool mirror in seven categories | Same lesson as 1 | Read (headings) |
| 11 | [nrvim/garmin-givemydata](https://github.com/nrvim/garmin-givemydata) | Local SQLite export of all Garmin data, 45 MCP tools; reports March 2026 login breakage | Login risk (section 5); claims not verified | Read (intro) |
| 12 | [the-momentum/open-wearables](https://github.com/the-momentum/open-wearables) | Self-hosted multi-provider data layer, one schema, REST API, webhooks | Pattern for J3; too heavy for one user | Read |
| 13 | [alus-it/AirspaceConverter](https://github.com/alus-it/AirspaceConverter) | Airspace and waypoint file converter (aviation) | Not relevant | Read (intro) |
| 14 | [daviderubio/garmin-run-gsheets-sync](https://github.com/daviderubio/garmin-run-gsheets-sync) | Last 20 runs to Google Sheets with de-duplication | Nothing we lack | Read (intro) |
| 15 | [KareemmSayed/Threshold](https://github.com/KareemmSayed/Threshold) | Personal-API-only MCP on Cloudflare Workers, D1 archive, OAuth, rep-by-rep interval analysis | Proves the no-Mac shape; shows what it costs (section 7) | Read |
| 16 | [dsebastien/ai-skill-garmin](https://github.com/dsebastien/ai-skill-garmin) | Agent skill with its own login port (Bun) | Library breakage claim; token caching with restrictive file mode (we already do this) | Read (intro) |
| 17 | [dandwhelan/garmin-stats-ai](https://github.com/dandwhelan/garmin-stats-ai) | Local SQLite, web chat and optional MCP; multi-user files | "Deviations, not diagnoses" wording; no-authentication warning | Read (intro) |
| 18 | [ThomasRondof/GarminWorkoutAItoJSON](https://github.com/ThomasRondof/GarminWorkoutAItoJSON) | One-line text to Garmin workout JSON | M7 | Read (intro) |
| 19 | [blauret/pyG5](https://github.com/blauret/pyG5) | Flight-simulator cockpit display | Not relevant | Read (intro) |
| 20 | [ghighi3f/garmin-grafana-mcp-server](https://github.com/ghighi3f/garmin-grafana-mcp-server) | Raw-data MCP over InfluxDB, interpretation left to the model | The opposite of our approach; confirms computing in code is a differentiator | Read (intro) |
| 21 | [MBombeck/HealthLog](https://github.com/MBombeck/HealthLog) | Self-hosted health record with iOS app, timeline with life-event lanes; non-commercial licence | Phone-companion shape (J2); lanes idea for Trends Option E | Read (intro) |
| 22 | [cyberjunky/python-garminconnect-aio](https://github.com/cyberjunky/python-garminconnect-aio) | Async variant of the library we depend on | No benefit (rate-limited, not speed-limited) | Read (intro) |
| 23 | [BorisBW/claude-fitness-cn](https://github.com/BorisBW/claude-fitness-cn) | Claude-Code coach reading six device-agnostic slots | M5 (explicit degradation) | Read (intro) |
| 24 | [Wewoc/Garmin_Local_Archive](https://github.com/Wewoc/Garmin_Local_Archive) | Windows desktop app: local archive, built-in update, local-model chat; GPLv3 | Desktop packaging shape; already mined for archive checks in the ChatGPT ledger | Read (intro) |
| 25 | [fmp-projects/fitness-ai-connector](https://github.com/fmp-projects/fitness-ai-connector) | Hosted connector on Garmin's official Health API, OAuth sign-in | Commercial route needing Garmin's business API; not available to us | Read (intro) |
| 26 | [infinitedescent/s-ais](https://github.com/infinitedescent/s-ais) | inReach tracking to a ship-tracking site | Not relevant | Read (intro) |
| 27 | [colincooperio/garmin-mcp](https://github.com/colincooperio/garmin-mcp) | 29 read-only tools and 6 prompts; same tools local or on Cloudflare; Personal API key | No-Mac shape with a smaller tool set; prompts are a feature we do not use | Read (headings) |
| 28 | [TolmachevKirill/garmin_ai](https://github.com/TolmachevKirill/garmin_ai) | Garmin cache plus Telegram bot and a markdown/CSV library for ChatGPT; local models supported | Push delivery (M8) | Read (intro) |
| 29 | [Benno-deskap/Garmin](https://github.com/Benno-deskap/Garmin) | n8n workflow sending a daily emailed training report | Push delivery (M8) | Read (intro) |
| 30 | [askb/ha-garmin-fitness-coach-app](https://github.com/askb/ha-garmin-fitness-coach-app) | Next.js app with a separate computation package, Postgres, Trends and Correlations pages | Engine/API/UI split (M4); Trends ideas (section 8) | Read (structure) |

## 12. Second opinion: Grok's UI/UX brief

### 12.1 What it is
The owner supplied a long brief generated by Grok (36 sections, about 1,750 lines) reviewing the
v0.33.0 dashboard snapshot. It is stored **unchanged** at
[`docs/external/GROK_UI_UX_RECOMMENDATIONS_2026-11-25.md`](external/GROK_UI_UX_RECOMMENDATIONS_2026-11-25.md) under a provenance banner.
Read it as a thoughtful product critique written by someone who saw the output but not the code.
**It is third-party AI output. I checked its claims about this product against the repository and
spot-checked two of its citations; I did not verify its research claims or competitor comparisons.**

### 12.2 Verdict
- **Right about the central gap.** Strong data, honesty and baselines; weak decisive synthesis. This
  matches [PRODUCT_REVIEW_2026-11.md](PRODUCT_REVIEW_2026-11.md) and this document's section 1.
- **Right about several specifics** (table below): no Coach/Scientist mode, soft guidance text, no
  forward projections, repetitive AI labels.
- **Partly wrong about subjective input**, and **silent on the constraint that matters most**: the
  dashboard is a static offline HTML file, so it cannot save anything a user taps (section 12.4).
- **Its research and competitor claims are unverified.** Use its principles, not its citations.

### 12.3 Claim audit

| # | Grok's claim | What I checked | Verdict |
|---:|---|---|---|
| 1 | No Coach/Scientist dual mode; Today is dense | No such mode in `dashboard*.py`. Navigation was already cut to five tabs in v0.19. (Repo fact) | **Agree** |
| 2 | Daily guidance is "safe and almost content-free" ("Follow your planned effort if you feel well.") | The string is `daily_focus.py` line 86. (Repo fact) | **Agree** |
| 3 | Subjective input is "almost none" / "absent" | **Partly wrong.** The MCP tool `coach_checkin` saves rested 1–5 and energy, soreness and knee 0–10; knee 4 or more suppresses next-day running; experiment notes also exist. What is missing is a way to enter it **on the dashboard**. (Repo fact) | **Partly** |
| 4 | No counterfactual or forward-looking guidance | No counterfactual or projection code found. (Repo fact) | **Agree** |
| 5 | Snapshot is about 5 MB with every day and run pre-rendered; should load lazily | 4.9 MB (ROADMAP open item). But lazy loading needs a server or hosted files: a `file://` page cannot fetch other files. (Repo fact) | **Agree, with a dependency** |
| 6 | AI text restates numbers instead of interpreting | By design: since v0.24 the model chooses among pre-written, checked sentences ([OLLAMA.md](OLLAMA.md)), because a number-only check cannot stop invented causes. Fix is to give the model **typed REASON and ACTION facts** computed in Python, not to loosen validation. | **Agree on the symptom; different fix** |
| 7 | "AI summary · facts checked" repeats too often | Plausible; not measured. A single system-level indicator is cheap. | **Agree** |
| 8 | On the Forerunner 955, overnight resting HR is strong; optical HRV is trend-only | Consistent with the general literature. Two real related papers exist (Støve et al. 2018 on the Forerunner 235; Miller et al. 2022, six wearables); both found in Crossref, **not read**. The 955-specific study Grok cites (Casanova-Lizón et al., *Sensors* 2026) and "Dial et al. 2025" were **not found in Crossref**, which may only reflect indexing lag. **Do not quote its percentages.** | **Direction plausible; numbers unverified** |
| 9 | HRV should never drive a strong recommendation alone | Already largely true: HRV enters readiness as the **7-day** average (log scale) versus a 60-day band, as one of four equal-weight signals; the illness flag needs 2 of 3 signals ([METRICS.md](../METRICS.md), v0.4.0 rules). A "without HRV" variant has **not** been tested in `recovery_weight_study`. | **Mostly already done; test before changing** |
| 10 | "Better than every competitor in the world"; competitor table | Not tested; marketing language. | **Ignore** |
| 11 | Nudging, counterfactual and gamification research (§18–19, §28) | Citations not checked. The ethical guardrails (autonomy-preserving, no streak guilt, associations not causes) are sound and match our rules. | **Take principles, not citations** |
| 12 | Local AI playbook for Qwen 3.5 4B (§33) | "Make the system smart, let the model narrate" is already our design. Its "copy linter" (rewrite existing text to a voice guide, show a diff for review) is new and safe if validated. Claims such as MLX being the best Mac path are unverified. | **Partly useful** |
| 13 | Browser-side data store (IndexedDB or SQLite in WebAssembly) | Possible only for a hosted installable web app, not the current offline file. Also moves data onto the phone. | **Dependency: hosting (M6/J1)** |

### 12.4 Where the brief collides with this repository's constraints

1. **There is no write path from the dashboard.** "I feel…" chips (Grok Phase 0) cannot save to the
   database from a static file. Options, cheapest first:
   - **Interim, no new infrastructure:** show on Today a one-line prompt ("Tell Claude: rested 3,
     knee 1") and display the latest saved check-in; add a tiny command-line check-in. Uses the
     existing `coach_checkin`.
   - **On-device only:** store the tap in the browser's local storage. It would not reach the
     database, so it cannot re-weight guidance; label it as a private note.
   - **Real fix:** a small authenticated write endpoint, which exists only with a hosted runner (J1).
2. **Lazy history and a client-side data store need hosting.** Pages already served from Cloudflare
   could fetch per-page JSON files on demand, but only with the private hosting activated and tested
   on the phone (M6). Until then, shrinking the single file is the only lever.
3. **Counterfactual sliders can work offline.** Compute in Python a small lookup table (for example
   bedtime bucket to expected sleep hours and next-day readiness range, from the owner's own history,
   only for buckets with enough nights) and let a slider index it in the page. No server needed.
   It is an **association from this person's data, not a causal claim**, and must show its range and
   sample size. Example already in the data: about +5.7 readiness points per extra hour of sleep
   over 232 paired days (Patterns).
4. **A richer coach voice must respect the validator.** The tone changes Grok wants
   ("observation, personal baseline, implication, action") are achievable if Python supplies the
   baseline comparison and the personal rule of thumb as typed facts and the validator checks each
   sentence against them. This is the same design as the narrator brief given to ChatGPT.
5. **Push versus pull.** My item M8 proposes a daily message; Grok's section on notification ethics
   says mostly pull. Resolution: **opt-in, at most one a day, off by default.**

### 12.5 Merged priority list

"G" items come from Grok's phased roadmap (its §22). Dependencies refer to items in section 6 and
to the constraints in 12.4.

| ID | Item | From | Effort | Depends on |
|---|---|---|---|---|
| G1 | **Today hero rewrite:** one status sentence, one decisive default, an alternative if the user feels off, and the 2 to 3 signals used shown by default, not buried | Grok P0 | Quick | none (`daily_focus.py`, Today page) |
| G2 | **One system-level trust indicator** instead of a label on every AI sentence | Grok §3 | Quick | none |
| G3 | **Voice pass on rule-based text** (observation, personal baseline, implication, action; supportive, not clinical) | Grok P0 | Quick | none for rule text; typed facts for AI text |
| G4 | **Surface personal rules of thumb** from existing relationships ("+5.7 readiness per extra hour of sleep") in guidance | Grok P1 | Quick to medium | none (`engine.relationships`) |
| G5 | **Coach / Scientist toggle**, Coach by default | Grok P0 | Medium | none strictly; easier after M3 |
| G6 | **Sleep debt as a 2 to 3 night recovery plan** | Grok P0 | Medium | existing sleep plan and debt code |
| G7 | **Subjective check-in on Today, interim path** (prompt + latest check-in shown) | Grok P0 | Quick | existing `coach_checkin` |
| G8 | **Subjective check-in with real write path** | Grok P0 | Major | J1 (hosted runner) |
| G9 | **Test a "without HRV" variant** in `recovery_weight_study` before any weight change | Grok §32 | Quick | none |
| G10 | **Offline counterfactual slider** using a precomputed lookup table | Grok P3 | Medium | G4; enough nights per bucket |
| G11 | **Typed REASON and ACTION facts for the narrator**, then free-wording with per-sentence validation | Grok §33 plus the ChatGPT brief | Medium | narrator v2 |
| G12 | **Dismiss / snooze / complete recommendations**, stored locally and used for ranking | Grok P3 | Medium | G8 for a persistent store, or CLI/MCP interim |
| G13 | **Lazy history, per-page data files, browser store** | Grok P2 | Major | M3, M6, hosting |
| G14 | **Responsible gamification layer** | Grok §28 | n/a | **Not recommended now** (Grok's own §28 says mostly avoid) |

**Combined order** (Claude's items first where they fix a measured problem; Grok's where they change the
daily experience):
1. **Quick, parallel, no dependencies:** G1, G2, G3, G9, plus Q1, Q2, Q4 and the Trends board (Q5).
2. **Next:** G4, G5, G6, G7, and M1 (the official-key-only test), which decides the hosting path.
3. **Then:** G10, G11 (needs narrator v2), M3 and M4.
4. **Only after the standalone decision:** G8, G12, G13, J1.

### 12.6 What I would not take from the brief
- The whole-product framing "best in the world": there is no evidence base for it.
- Any specific sensor accuracy percentages or competitor claims until verified.
- A gamification layer.
- Moving the data store into the browser before hosting exists.

### 12.7 How to know it worked
Reuse the five-second Today test from [PRODUCT_REVIEW_2026-11.md](PRODUCT_REVIEW_2026-11.md)
section 5 on the real phone, and add Grok's checks: **time to decision**, **whether the primary action
was accepted**, **whether "Show the facts" was opened**, and **zero strong claims resting on HRV alone**.

## 13. Open questions and limits of this review

- I read READMEs, not source code, and ran none of the projects. Claims about breakage (11, 16) and
  performance (3) are the projects' own.
- Cloudflare free-tier limits, Python Workers support, costs of small hosts and Apple developer
  fees were **not verified**; check current pricing before choosing.
- I did not read all 50 forum replies and cannot say whether Garmin has responded elsewhere.
- Token-cost figures are estimates (characters ÷ 4).
- The database sizes come from a 23 Nov cloud copy, not from the owner's Mac.
- Nothing here was tested on the owner's devices.
- Section 12: I did not read every one of Grok's 36 sections in depth (I read sections 0 to 5, 13, 22 to 24, 32 to 33 and 35); the audit covers its claims about this product and the two citations I could check.
