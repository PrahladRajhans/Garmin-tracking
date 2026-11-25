# Garmin ecosystem review

Reviewed and followed up on 25 November 2026. The forty supplied entries contain 38 distinct repositories.
Each public default branch resolved, and this ledger links to the exact revision and README
reviewed. The license column records the root file observed, not a legal determination for
every file. The initial ledger records README claims. The follow-up links the source,
test, configuration or public manifest inspected for each entry. The implementations in this repository are original adaptations of the cited ideas and interfaces. The upstream code, visual assets and packages served as references. No live Garmin session was used in this review.

## Ranked decisions

1. **Make archive completeness inspectable.** Build a shareable local audit distinguishing
   valid timeline days from stored payload rows and highlighting absent referenced FIT files.
   Accept only a read-only command with aggregate output, tested against empty data and missing
   files. Keep database integrity distinct from coverage and device availability.
2. **Make saved wellness samples useful.** Reuse the stored Garmin Connect stress response
   to show Stress and Body Battery on separate, aligned day charts. Show source, units,
   recording gaps and coverage. Tests must cover sentinels, local date boundaries, daylight
   saving and absent series. Reuse the renderer and avoid new requests or stores.
3. **Make archived summaries portable.** The follow-up adds selected-field local CSV and
   descriptor-aware Body Battery decoding. Next candidates are richer checks in the existing
   workout preview and a dated coaching evaluation on reproducible cases. Keep coaching claims and usefulness checks separate from transport.
   Multi-provider ingestion, hosted chat and live write tools carry higher complexity.

## Community evidence

People report that they can export activity summaries more readily than detailed wellness
history, and want to know whether the limitation is the report, the source or missing data.
These discussions establish user needs. They cannot confirm coverage or Garmin service
limits for this account. [Reddit detailed health export](https://www.reddit.com/r/Garmin/comments/1d8v68r/how_to_export_all_health_stats_from_garmin/)
· [Reddit history and local archive](https://www.reddit.com/r/GarminWatches/comments/1hrqwcz/limited_data_export_from_garmin_connect/)
· [Garmin forum Body Battery export](https://forums.garmin.com/apps-software/mobile-apps-web/f/garmin-connect-web/345029/body-battery-why-no-longer-able-to-export-data-as-a-csv/1735654)

## Implementation evidence

- Explicit missing context check. Our report counts Garmin timeline coverage and FIT reachability without exporting private records. [Wewoc/Garmin_Local_Archive source](https://github.com/Wewoc/Garmin_Local_Archive/blob/5f65d71e28ff89299f8febef2169cf94808b3303/src/app/outputs/context_check.py)
- Dedicated checkup entry point. Our report addresses source/file coverage while its checkup addresses goals and battery status. [tcgoetz/GarminDB source](https://github.com/tcgoetz/GarminDB/blob/392beb49cfba7599b5a9ed4d195267cf79ec51b0/garmindb/checkup.py)
- Stress and Battery arrays contain epoch-millisecond entries with values at different positions. [arpanghosh8453/garmin-grafana source](https://github.com/arpanghosh8453/garmin-grafana/blob/e0cdba292d9ad77d1881e92ddcabd61525ad9d5a/src/garmin_grafana/garmin_fetch.py)
- get_all_day_stress and get_stress_data use the same daily stress URL, matching our archived dataset. [cyberjunky/python-garminconnect source](https://github.com/cyberjunky/python-garminconnect/blob/82bc11073b597d20f8b080b7aeaac8d4cef4fc3e/garminconnect/api/health.py)

## Where the comparison changes our priorities

GarminDB has a documented monitoring FIT pipeline. Our source archive and activity FIT
pipeline are already persistent, but importing wellness FIT needs confirmed message layouts
and independently validated fixtures. The archive audit gives the owner evidence about
which gaps actually need that importer. The [monitoring FIT preview](WELLNESS_PREVIEW.md) now compares a file with the saved archive without writing either. Wewoc’s checker covers stored context such as
weather rather than Garmin sample usability. Our implementation applies the idea to
different data. [Wewoc archive checker](https://github.com/Wewoc/Garmin_Local_Archive/blob/5f65d71e28ff89299f8febef2169cf94808b3303/src/context/context_silo_check.py)

Threshold explicitly distinguishes a missing night from a weekly recovery measurement and
uses additional recovery inputs when available. PulseCoach centralizes recommendation
mutation records in one writer. We already preserve prior recommendations and checked AI
state, but have no real-archive benchmark for whether an owner would act on the next
recommendation. Compare outcomes and evidence before adding overnight stress to readiness,
since it can share physiology with HRV, or introducing another score.
[Threshold readiness](https://github.com/KareemmSayed/Threshold/blob/ec7e45129c10f3033a9b2470d9f4a703083d4033/src/analysis/readiness.ts)
· [PulseCoach recommendation audit](https://github.com/askb/ha-garmin-fitness-coach-app/blob/5692bdc4e45bf5dcfb7af7b71a61fd8e94357a46/packages/api/src/lib/recommendation-audit.ts)

The nested coaching workflow in garmin-ai-coach separates season planning and weekly
planning. We can test those distinct tasks without moving health records into another model
provider. A broader tool catalog or a prettier report is insufficient evidence of coaching
quality. [Planning workflow](https://github.com/leonzzz435/garmin-ai-coach/blob/54a64942d52a04d624df4bb7cbc7fdc28c39113e/services/ai/langgraph/workflows/planning_workflow.py)

## Repository ledger

| # | Source at reviewed revision | Root license | Useful observation | Decision |
|---:|---|---|---|---|
| 1 | [tcgoetz/GarminDB](https://github.com/tcgoetz/GarminDB/tree/392beb49cfba7599b5a9ed4d195267cf79ec51b0) | GPL v2 | Daily monitoring FIT import and SQLite analysis separate ingest from derived views. | Shipped a read-only monitoring FIT preview. Confirm owner-file coverage and conflicts before considering writes. |
| 2 | [cyberjunky/python-garminconnect](https://github.com/cyberjunky/python-garminconnect/tree/82bc11073b597d20f8b080b7aeaac8d4cef4fc3e) | MIT | Extensive endpoint inventory plus first-party wrapper tests. | Adopt the verified daily stress endpoint contract. Keep our pinned client and probe live fields separately. |
| 3 | [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp/tree/a2ca5fcac34524b83814fe2fcf3d479f8a75983f) | MIT | Activity and workout write tools sit alongside health retrieval. | Keep the current workout preview and explicit upload. Defer broadening write access until reconciliation is designed. Existing local analysis is the baseline. |
| 4 | [arpanghosh8453/garmin-grafana](https://github.com/arpanghosh8453/garmin-grafana/tree/e0cdba292d9ad77d1881e92ddcabd61525ad9d5a) | BSD-3-Clause | Separate intraday stress and Body Battery measurements, plus historical import. | Adopt bounded day charts using archived Connect samples. No metrics stack or new polling needed. |
| 5 | [drkostas/hevy2garmin](https://github.com/drkostas/hevy2garmin/tree/b44bdc7c3a34a40fac77c5ec5dd18209f02f6d21) | MIT | Structured strength migration and exercise mappings. | Useful later with real Hevy input and a confirmed exercise-mapping review. Skip automatic activity writes for now. |
| 6 | [petergardfjall/garminexport](https://github.com/petergardfjall/garminexport/tree/983afda16299e4d2e610c1055604c550c4a16ba5) | Apache-2.0 | Incremental activity backup with multiple export formats. README flags maintenance limits. | Borrow resumable archive thinking. Existing raw FIT retention already meets the core need. |
| 7 | [warmsound/crystal-face](https://github.com/warmsound/crystal-face/tree/bcc340484bd2a3a09f13b22a2d0d6dae3b4de9c7) | GPL v3 | A compact watch face with segmented goal displays. | Favor a legible primary number and secondary context. Skip Connect IQ and branded visual assets. |
| 8 | [house-of-abbey/GarminHomeAssistant](https://github.com/house-of-abbey/GarminHomeAssistant/tree/da40a4b1b8668bbfef9134e0a92de06df5dc3214) | MIT | Watch UI for Home Assistant actions and sensor readings. | Defer actuator controls. A mobile glance remains a useful pattern, and private dashboard delivery already exists. |
| 9 | [chloevoyer/garmin-to-notion](https://github.com/chloevoyer/garmin-to-notion/tree/63287f98b4eede4eec2c21072b7553aea25db60b) | MIT | Activities and personal records pushed to Notion. README marks it archived. | Defer external copies and third-party workspace credentials. |
| 10 | [kjkjava/garmin-connect-export](https://github.com/kjkjava/garmin-connect-export/tree/ab949368b065aa05530566ffa255290e01b0605f) | MIT | Date-stamped activity CSV and optional tracks. | Shipped: date-bounded summary CSV without routes or activity names. Keep the private source archive separate. |
| 11 | [magsol/garmin](https://github.com/magsol/garmin/tree/6b19fc24881fdb9d5a76ad73d3e6f26ab005e3c2) | MIT | Monthly and running trend scripts behind a website scraping workflow. | Our matched-running and dated trends cover more of this need. Avoid form scraping. |
| 12 | [pe-st/garmin-connect-export](https://github.com/pe-st/garmin-connect-export/tree/7bb17ab2d99a6c0942f00071983ab4742d17cc2c) | MIT | Filterable activity export. README reports its current authentication path fails. | Adopt concepts only. Stable source identifiers already matter more than dates alone. |
| 13 | [dtcooper/python-fitparse](https://github.com/dtcooper/python-fitparse/tree/d88bb6997138c38d0c578aeaaf4108df0711d1f6) | MIT | Decodes FIT messages in Python and documents maintenance constraints. | Consider as a secondary offline cross-check if official SDK mismatches are reproducible. |
| 14 | [Pythe1337N/garmin-connect](https://github.com/Pythe1337N/garmin-connect/tree/b2718bfe7c8454348d42a3cd72ff9dc1e2dfba0d) | MIT | TypeScript Garmin client with local token persistence and endpoint breadth. | Keep the Python transport. Token management and country endpoints need adapter-specific evidence. |
| 15 | [Nicolasvegam/garmin-connect-mcp](https://github.com/Nicolasvegam/garmin-connect-mcp/tree/57bc47f03f768e6be7622897beab5b3bfd0f67d7) | No root license file located | Grouped MCP tools by domain. | Borrow finding aids and clearer tool descriptions. Do not duplicate all date-based reads. |
| 16 | [aspain/git-sweaty](https://github.com/aspain/git-sweaty/tree/91e83a001beaa13541ec7c1713045ba4ee6af339) | MIT | Commits workout-derived dashboard output and deploys via GitHub tooling. | Useful build/deploy automation reference. Our private Pages output is opt-in, separate from Git history. |
| 17 | [nrvim/garmin-givemydata](https://github.com/nrvim/garmin-givemydata/tree/a19331da85609e18b8136d6608e6c8aca6b2480c) | AGPL v3 | Local SQLite and FIT files with multiple export choices and MCP. | Adopt data inventory idea. Defer alternate login and export formats. Verify each format independently. |
| 18 | [adiesner/GarminPlugin](https://github.com/adiesner/GarminPlugin/tree/0cdc86ef4a68cce83b4ce880008131365cc344b2) | GPL v3 | Linux plugin compatible with historical Garmin Communicator interfaces. | Outside modern deployment scope. |
| 19 | [leonzzz435/garmin-ai-coach](https://github.com/leonzzz435/garmin-ai-coach/tree/54a64942d52a04d624df4bb7cbc7fdc28c39113e) | MIT | Training report followed by a four-week plan, with optional user clarification. | Useful plan/review separation. Existing weekly plan remains, and provider migration waits for a coaching benchmark. |
| 20 | [Nicolasvegam/garmin-connect-mcp](https://github.com/Nicolasvegam/garmin-connect-mcp/tree/57bc47f03f768e6be7622897beab5b3bfd0f67d7) | No root license file located | Duplicate of entry 15. | Same revision and decision. |
| 21 | [nrvim/garmin-givemydata](https://github.com/nrvim/garmin-givemydata/tree/a19331da85609e18b8136d6608e6c8aca6b2480c) | AGPL v3 | Duplicate of entry 17. | Same revision and decision. |
| 22 | [the-momentum/open-wearables](https://github.com/the-momentum/open-wearables/tree/6811b286c95389d2be20d293d32f393ae4d8a101) | MIT | Normalizes multiple providers behind a shared data layer. | Design input for later provider additions. Keep provenance and metric definitions before schema expansion. |
| 23 | [alus-it/AirspaceConverter](https://github.com/alus-it/AirspaceConverter/tree/b4271502c5eee08829fc8f396ba895e22e13ecf3) | GPL v3 | Aviation airspace and waypoint conversion. | Outside fitness scope. |
| 24 | [daviderubio/garmin-run-gsheets-sync](https://github.com/daviderubio/garmin-run-gsheets-sync/tree/4021c899fb1b0d00382173eb81437311841f99d4) | No root license file located | A scheduled rolling activity-to-Sheets workflow, documented date deduplication. | Shipped: CSV preserves stable activity IDs, including separate runs on the same day. |
| 25 | [KareemmSayed/Threshold](https://github.com/KareemmSayed/Threshold/tree/ec7e45129c10f3033a9b2470d9f4a703083d4033) | MIT | Personal API tools with deterministic analytics and evidence-oriented output. | Keep calculation in code and improve model benchmarks. Do not trade measured definitions for connector count. |
| 26 | [dsebastien/ai-skill-garmin](https://github.com/dsebastien/ai-skill-garmin/tree/22bfebaf567c60cf134229c77682c334aa35df10) | MIT | An agent skill with example questions and Garmin scripts. | Borrow prompt examples and handoff structure. Keep one underlying source of calculations. |
| 27 | [dandwhelan/garmin-stats-ai](https://github.com/dandwhelan/garmin-stats-ai/tree/067d5c6ffc26eac9193bec9c072601c38ceee905) | MIT | Local SQL plus dashboard chat and a copy-to-assistant workflow. | Useful deliberate sharing pattern. Prefer a summary-only archive report ahead of raw uploads or hosted chat. |
| 28 | [ThomasRondof/GarminWorkoutAItoJSON](https://github.com/ThomasRondof/GarminWorkoutAItoJSON/tree/557d3c914a038635e79560cf3d0fb7b3f92447bc) | No root license file located | Sport-specific textual workout syntax for Garmin JSON generation. | Later: extend the existing workout preview to catch repeat-step and target compatibility issues. |
| 29 | [blauret/pyG5](https://github.com/blauret/pyG5/tree/1274d5207ee539304c8737f2ff1bf9e09df5c6ac) | MIT | Garmin G5 instrument emulation for X-Plane. | Outside fitness scope. |
| 30 | [ghighi3f/garmin-grafana-mcp-server](https://github.com/ghighi3f/garmin-grafana-mcp-server/tree/404580b94ac699f200ae8de35154e40402727e11) | MIT | Read access to an existing Garmin Grafana InfluxDB deployment. | Confirms separation of data access from interpretation. Keep existing SQLite MCP path. |
| 31 | [MBombeck/HealthLog](https://github.com/MBombeck/HealthLog/tree/1daefecf19e2a504ba355a0d63ce604bbde02686) | PolyForm Noncommercial | Self-hosted health tracking with device adapters. | Data portability inspiration only. Noncommercial terms make it unsuitable as a code dependency. |
| 32 | [cyberjunky/python-garminconnect-aio](https://github.com/cyberjunky/python-garminconnect-aio/tree/fb913a15107edee5c5530f3bded7c553ec57923b) | MIT | Asynchronous Garmin Connect Python client. | Avoid adding request concurrency without proving rate-limit and completion behavior improves. |
| 33 | [BorisBW/claude-fitness-cn](https://github.com/BorisBW/claude-fitness-cn/tree/b0d6e3a7771b0a815f70186dfdb3dc7693995b7a) | MIT | Local coaching files and recurring readiness, recap and plan workflows. | Borrow the review cadence, already partially covered by our weekly and bedtime follow-ups. External deployment is a separate decision. |
| 34 | [Wewoc/Garmin_Local_Archive](https://github.com/Wewoc/Garmin_Local_Archive/tree/5f65d71e28ff89299f8febef2169cf94808b3303) | GPL v3 | Local archive plus an explicit context check for missing material. | Adopt read-only archive report and paths-free handoff. Do not treat empty payloads as useful history. |
| 35 | [fmp-projects/fitness-ai-connector](https://github.com/fmp-projects/fitness-ai-connector/tree/4559bde3dc1630e62ef9325fb155ad9e4901e625) | MIT | Public description of hosted official API connector with OAuth and health, FIT and trends tools. | Compare this interface, not unseen server internals. Keep Mac-local operation until remote auth is a deliberate product decision. |
| 36 | [infinitedescent/s-ais](https://github.com/infinitedescent/s-ais/tree/358983d93c5a2a6b3124cc209dff136fec5cd920) | GPL v3 | Vessel location relay for Garmin inReach AIS. | Outside fitness scope. |
| 37 | [colincooperio/garmin-mcp](https://github.com/colincooperio/garmin-mcp/tree/a686972aca0091716aa556477531964355bf1650) | MIT | Official Personal API read-only tools with local and remote options. | Borrow deployment boundary and focused tools. Keep raw local archive for replay and history. |
| 38 | [TolmachevKirill/garmin_ai](https://github.com/TolmachevKirill/garmin_ai/tree/f73d9300851ac8fdcb3e92767f30e2eed651ae92) | No root license file located | Garmin cache, markdown/CSV library and several assistant surfaces. | Defer messaging and external sharing. Borrow deliberate portable context as a later design. |
| 39 | [Benno-deskap/Garmin](https://github.com/Benno-deskap/Garmin/tree/fe4fd3e28c7d08d308e11f58ee6e42f50bc38f15) | Custom terms | Scheduled email advice; repository terms restrict reuse. | Idea-level comparison only. Dashboard stays the primary place for evidence and advice. |
| 40 | [askb/ha-garmin-fitness-coach-app](https://github.com/askb/ha-garmin-fitness-coach-app/tree/5692bdc4e45bf5dcfb7af7b71a61fd8e94357a46) | Apache-2.0 | Broad coaching dashboards with separate Home, fitness, training and recovery views. | Borrow hierarchy and future coaching evaluation ideas. Existing offline navigation stays; no web stack migration. |

## Follow-up implementation decisions

Each row points to the concrete artifact reviewed at the pinned revision. Source and test inspection
can establish a behavior or a test contract. It cannot establish live service availability. A candidate
includes the next acceptance check. Two duplicated links retain their original numbers.

The CSV command opens the archive read-only and exports only the selected, inclusive local date range.
Activities preserve IDs and omit names, routes and timestamps finer than the day. Wellness columns
use fixed units and the same nightly HRV fallback as the dashboard. A blank value represents missing
data. The output still contains personal data. When specified, the output file is created with owner-only
access, and an existing file is preserved.

```sh
.venv/bin/garmin-mcp-verify --export-csv wellness --from-date 2026-11-01 --to-date 2026-11-25 --output "$HOME/garmin-wellness.csv"
```

| # | Pinned artifact | Specific design or behavior | Adopting it here and the next check |
|---:|---|---|---|
| 1 | [`test_monitoring_fit_file.py`](https://github.com/tcgoetz/GarminDB/blob/392beb49cfba7599b5a9ed4d195267cf79ec51b0/test/test_monitoring_fit_file.py) | Monitoring FIT tests check message types, elapsed gaps and non-decreasing steps per activity type. | Shipped a read-only gap/overlap preview using the official SDK, a pinned monitoring file probe and synthetic fixtures. A write path still needs source-precedence and replay tests. |
| 2 | [`health.py`](https://github.com/cyberjunky/python-garminconnect/blob/82bc11073b597d20f8b080b7aeaac8d4cef4fc3e/garminconnect/api/health.py) | Two wrapper methods resolve the same daily stress endpoint. | Shared: this is the archived feed already used for the stress timeline. Test against a representative archived response before widening collection. |
| 3 | [`tool_profiles.py`](https://github.com/Taxuspt/garmin_mcp/blob/a2ca5fcac34524b83814fe2fcf3d479f8a75983f/src/garmin_mcp/tool_profiles.py) | The profile module defines separate minimal, health, activity and workout tool sets. | Candidate: group read-only tools for reviewers. Verify exposed tools and ensure a reduced profile cannot reach any write tool before introducing this option. |
| 4 | [`garmin_fetch.py`](https://github.com/arpanghosh8453/garmin-grafana/blob/e0cdba292d9ad77d1881e92ddcabd61525ad9d5a/src/garmin_grafana/garmin_fetch.py) | The intraday fetch reads stress and Body Battery arrays at different indices. | Shipped in v0.28.0: same-day aligned charts from saved values. Any further fields need a real sample and a no-new-request test. |
| 5 | [`test_real_workout_fixtures.py`](https://github.com/drkostas/hevy2garmin/blob/b44bdc7c3a34a40fac77c5ec5dd18209f02f6d21/tests/test_real_workout_fixtures.py) | Anonymized workout fixtures test mapping coverage and valid FIT exercise pairs. | Candidate: add original mixed strength fixtures, then verify sets, rests and units on preview before considering live upload. |
| 6 | [`incremental_backup.py`](https://github.com/petergardfjall/garminexport/blob/983afda16299e4d2e610c1055604c550c4a16ba5/garminexport/incremental_backup.py) | Incremental backup accepts selected file formats and skips activities already stored in the backup directory. | The archive already retains original FIT revisions. Add a resumability test for missing versus corrupt individual files before extending recovery or combining additional formats. |
| 7 | [`AlwaysOnDisplay.mc`](https://github.com/warmsound/crystal-face/blob/bcc340484bd2a3a09f13b22a2d0d6dae3b4de9c7/always-on-source/AlwaysOnDisplay.mc) | The always-on drawable shows a stripped-down time display without the full watch face. | Candidate: expose only the next actionable observation in any future compact display. Test offline legibility at phone size before considering a watch target. |
| 8 | [`config.schema.json`](https://github.com/house-of-abbey/GarminHomeAssistant/blob/da40a4b1b8668bbfef9134e0a92de06df5dc3214/config.schema.json) | The configuration schema separates actions, required fields and optional confirmations. | Maintain explicit upload approval in our workout workflow. Apply the validation pattern only if a new write action has a dry-run/confirmation test. |
| 9 | [`garmin-activities.py`](https://github.com/chloevoyer/garmin-to-notion/blob/63287f98b4eede4eec2c21072b7553aea25db60b/src/workflows/garmin-activities.py) | The activity workflow checks for an existing activity before writing another Notion page. | Keep external Notion writes out of the archive path. Require idempotency by source activity ID and a duplicate-safe dry run before any future bridge. |
| 10 | [`gcexport.py`](https://github.com/kjkjava/garmin-connect-export/blob/ab949368b065aa05530566ffa255290e01b0605f/gcexport.py) | The exporter writes activity summary rows and treats track export independently, skipping empty GPX tracks. | Shipped: only summary CSV here, no route extraction or activity names. Tests assert the fixed column list and preserve zero values. |
| 11 | [`monthly.py`](https://github.com/magsol/garmin/blob/6b19fc24881fdb9d5a76ad73d3e6f26ab005e3c2/monthly.py) | The monthly report calculates the previous complete month from the calendar boundary. | Candidate: compare complete periods in Training when added. Include a January rollover and a short February fixture before changing the active-window analytics. |
| 12 | [`gcexport_test.py`](https://github.com/pe-st/garmin-connect-export/blob/7bb17ab2d99a6c0942f00071983ab4742d17cc2c/gcexport_test.py) | CSV tests pin missing fields, pace versus cycling speed, offsets and exact serialized records. | Shipped: exact CSV schema, inclusive local-day bounds and blank missing values have tests. Keep the raw duration and distance units explicit. |
| 13 | [`base.py`](https://github.com/dtcooper/python-fitparse/blob/d88bb6997138c38d0c578aeaaf4108df0711d1f6/fitparse/base.py) | Developer-data decoding is a separate concern from core FIT records. | Keep the official Garmin SDK as the primary decoder. Compare both against a malformed or novel developer-field fixture only if a reproducible precedence defect appears. |
| 14 | [`GarminConnect.ts`](https://github.com/Pythe1337N/garmin-connect/blob/b2718bfe7c8454348d42a3cd72ff9dc1e2dfba0d/src/garmin/GarminConnect.ts) | Authentication token save/load functions are isolated from metric methods. | Keep authentication unchanged. If token migrations are needed, test corrupted and missing credentials in isolated fixtures without reading a real user secret. |
| 15 | [`snapshot.tools.ts`](https://github.com/Nicolasvegam/garmin-connect-mcp/blob/57bc47f03f768e6be7622897beab5b3bfd0f67d7/src/tools/snapshot.tools.ts) | One snapshot tool packages a date-selected combination of metrics through the Garmin client. | Candidate: expose a single bounded archive-only review snapshot. Accept when a missing stream stays explicitly missing and the call makes no live Garmin request. |
| 16 | [`test_tooltip_touch_link_activation.py`](https://github.com/aspain/git-sweaty/blob/91e83a001beaa13541ec7c1713045ba4ee6af339/tests/test_tooltip_touch_link_activation.py) | Touch link tests distinguish tap behavior from desktop new-tab behavior. | Candidate: keep a phone touch fixture alongside keyboard checks when adding plot interactions. Confirm tapping, scrolling and opening the detail route independently. |
| 17 | [`export.py`](https://github.com/nrvim/garmin-givemydata/blob/a19331da85609e18b8136d6608e6c8aca6b2480c/garmin_mcp/export.py) | The SQLite exporter declares field mappings for broad CSV tables and treats activity-file downloads separately. | Shipped: fixed-schema, date-bounded local CSV. Sensitive fields, free text and activity-file downloads remain outside this command. |
| 18 | [`Fit2TcxConverter.cpp`](https://github.com/adiesner/GarminPlugin/blob/0cdc86ef4a68cce83b4ce880008131365cc344b2/src/Fit2TcxConverter.cpp) | The converter builds TCX records and laps from FIT messages. | Outside the current dashboard scope. Revisit only for a format portability request with a test proving route data requires explicit selection. |
| 19 | [`planning_workflow.py`](https://github.com/leonzzz435/garmin-ai-coach/blob/54a64942d52a04d624df4bb7cbc7fdc28c39113e/services/ai/langgraph/workflows/planning_workflow.py) | The planning workflow separates weekly planning from integrated historical analysis. | Candidate: precompute the measured session evidence, then evaluate planning text independently. Compare factual grounding and actionability on named fixtures before changing the planner. |
| 20 | [`snapshot.tools.ts`](https://github.com/Nicolasvegam/garmin-connect-mcp/blob/57bc47f03f768e6be7622897beab5b3bfd0f67d7/src/tools/snapshot.tools.ts) | Duplicate of entry 15 and the same snapshot registration. | Same bounded local-snapshot candidate and acceptance checks. |
| 21 | [`export.py`](https://github.com/nrvim/garmin-givemydata/blob/a19331da85609e18b8136d6608e6c8aca6b2480c/garmin_mcp/export.py) | Duplicate of entry 17 and the same SQLite exporter. | Same shipped fixed-schema local CSV and privacy tests. |
| 22 | [`series_sample.py`](https://github.com/the-momentum/open-wearables/blob/6811b286c95389d2be20d293d32f393ae4d8a101/backend/app/models/series_sample.py) | The series-sample model keys readings by data source, series type and timestamp, and stores the daily-total flag separately. | Candidate for a new provider. Require provenance and simultaneous-source fixtures before aggregating series or blending totals with intraday samples. |
| 23 | [`CSV.cpp`](https://github.com/alus-it/AirspaceConverter/blob/b4271502c5eee08829fc8f396ba895e22e13ecf3/src/CSV.cpp) | Separate CSV parsers validate latitude, longitude and other aviation fields. | Domain mismatch. Keep runtime sports analytics independent. Validate new archive fields from wearable fixtures rather than importing an aviation parser. |
| 24 | [`sync_garmin.py`](https://github.com/daviderubio/garmin-run-gsheets-sync/blob/4021c899fb1b0d00382173eb81437311841f99d4/sync_garmin.py) | The Sheets sync checks whether a local date already exists, which can collapse two activities on one day. | Shipped: export keeps each activity ID, including two same-day sessions. No external spreadsheet sync is added. |
| 25 | [`readiness.ts`](https://github.com/KareemmSayed/Threshold/blob/ec7e45129c10f3033a9b2470d9f4a703083d4033/src/analysis/readiness.ts) | The briefing marks a signal stale when its data has not arrived instead of counting it in the daily call. | Candidate: test missing, stale and present evidence paths independently before an overnight readiness change. Keep estimates distinct from Garmin Training Readiness. |
| 26 | [`SKILL.md`](https://github.com/dsebastien/ai-skill-garmin/blob/22bfebaf567c60cf134229c77682c334aa35df10/skills/garmin-connect/SKILL.md) | The agent skill documents date arguments, stdout JSON, stderr errors and example questions. | Adopt in our handover: a mechanism-oriented CLI example and explicit date/units contract for other assistants. |
| 27 | [`test_agent_tool_loop.py`](https://github.com/dandwhelan/garmin-stats-ai/blob/067d5c6ffc26eac9193bec9c072601c38ceee905/garmin-insights/tests/test_agent_tool_loop.py) | Tests simulate capped tool loops, failed calls and bounded portable snapshots. | Candidate: model-output tests should score completion and evidence validity separately with harmless fixtures before adding any remote model or open-ended tool loop. |
| 28 | [`GarminGenJSON.html`](https://github.com/ThomasRondof/GarminWorkoutAItoJSON/blob/557d3c914a038635e79560cf3d0fb7b3f92447bc/GarminGenJSON.html) | The generator parses sport-specific executable steps and splits compound step text. | Candidate: cover repeat boundaries and invalid units in the existing preview. Upgrade preview first and require separate live upload approval. |
| 29 | [`pyG5Network.py`](https://github.com/blauret/pyG5/blob/1274d5207ee539304c8737f2ff1bf9e09df5c6ac/pyG5/pyG5Network.py) | The network module keeps the flight-simulator data stream apart from instrument rendering. | Domain mismatch. Its separation is already reflected in our archive/renderer boundary. No aviation dependency or feed is applicable. |
| 30 | [`schema.py`](https://github.com/ghighi3f/garmin-grafana-mcp-server/blob/404580b94ac699f200ae8de35154e40402727e11/tools/schema.py) | The MCP schema endpoint lists measurement fields and data types for an existing database. | Adopt a documented column list and header row for CSV. Defer dynamic schema browsing unless callers need it and the allowlist can be verified. |
| 31 | [`coach-eval.yml`](https://github.com/MBombeck/HealthLog/blob/1daefecf19e2a504ba355a0d63ce604bbde02686/.github/workflows/coach-eval.yml) | The coach workflow separates deterministic grounding and scenario checks from an opt-in live judge. | Use distinct local output regression and Ollama smoke evidence for acceptance. Do not equate a live model producing text with correct facts. |
| 32 | [`__init__.py`](https://github.com/cyberjunky/python-garminconnect-aio/blob/fb913a15107edee5c5530f3bded7c553ec57923b/garminconnect_aio/__init__.py) | The async client maps connection, rate-limit and authentication failures to distinct exceptions. | Keep callable failures diagnosable. Require rate-limit and bounded-concurrency replay before parallel fetches, because throughput alone cannot prove data completion. |
| 33 | [`coach-memory.md`](https://github.com/BorisBW/claude-fitness-cn/blob/b0d6e3a7771b0a815f70186dfdb3dc7693995b7a/examples/coach-memory.md) | The coach-memory example separates goals, baseline trends and active versus resolved issues. | Candidate: use already curated coaching state for dated follow-ups. A regression must prove dated state takes priority over superseded advice and the shared payload contains only authorized fields. |
| 34 | [`context_check.py`](https://github.com/Wewoc/Garmin_Local_Archive/blob/5f65d71e28ff89299f8febef2169cf94808b3303/src/app/outputs/context_check.py) | The context checker reports missing dates and source-specific reasons. | Shipped in v0.28.0: local read-only archive audit with usable-day counts and gaps. Check missing, malformed and present fixtures before adding more streams. |
| 35 | [`server.json`](https://github.com/fmp-projects/fitness-ai-connector/blob/4559bde3dc1630e62ef9325fb155ad9e4901e625/server.json) | The registry manifest exposes the official-provider description and a remote Streamable HTTP endpoint. | Benchmark the published interface only. Require a published schema or an owner-authorized live comparison before claiming parity; no server internals were visible. |
| 36 | [`s-ais.js`](https://github.com/infinitedescent/s-ais/blob/358983d93c5a2a6b3124cc209dff136fec5cd920/lib/s-ais.js) | The service relays inReach-derived positions to a marine tracking service. | Domain mismatch and a data-sharing boundary. No remote location relay is applicable to the archive. |
| 37 | [`compact.ts`](https://github.com/colincooperio/garmin-mcp/blob/a686972aca0091716aa556477531964355bf1650/src/compact.ts) | The compactor reads named timestamp and level descriptors and understands two- and three-column Body Battery arrays. | Shipped: support those local archive shapes. Ambiguous or unknown supplied descriptors leave the Battery stream unavailable while independent stress remains readable. |
| 38 | [`export.py`](https://github.com/TolmachevKirill/garmin_ai/blob/f73d9300851ac8fdcb3e92767f30e2eed651ae92/garmin_pipeline/collectors/export.py) | The period exporter allowlists daily and activity fields, with optional network hydration when a client is supplied. | Shipped: an independently implemented range export reads SQLite only. Explicit dates and a fixed local field list are tested; dates and activity IDs still identify user data. |
| 39 | [`Garmin_clean.json`](https://github.com/Benno-deskap/Garmin/blob/fe4fd3e28c7d08d308e11f58ee6e42f50bc38f15/Garmin_clean.json) | The workflow loads advice memory and includes an SMTP step in the report flow. | Candidate: evaluate dated recommendation carryover without an email pipeline. Verify supersession and rejection handling with local fixtures. |
| 40 | [`recommendation-audit.ts`](https://github.com/askb/ha-garmin-fitness-coach-app/blob/5692bdc4e45bf5dcfb7af7b71a61fd8e94357a46/packages/api/src/lib/recommendation-audit.ts) | Recommendation mutations pass through a schema-validated writer. | Candidate: attach a stable reason and state-change ID to coaching transitions. Confirm retry idempotency and append-only provenance before broadening mutation endpoints. |

## v0.28.0 verification

The build keeps data ingestion, chart formatting and archive reporting separate. The review
found that metadata lookups would otherwise try to create tables, so reading the configured
timezone now avoids schema writes. It also found that two SVGs per metric would duplicate
every chart point, so each wellness panel uses one drawing. The tradeoff is additional
HTML for seven days of chart detail. [UI review](UI_REVIEW.md#intraday-wellness-layout-v0280)

The local suite passed 277 tests. The 36-month fixture replay had no broken links or
duplicate IDs and left the source byte-for-byte unchanged. The owner's audit, wearable
coverage and iPhone behavior still need acceptance. A passed audit is not proof that
every historical file is present or that any metric is sufficiently sampled.
