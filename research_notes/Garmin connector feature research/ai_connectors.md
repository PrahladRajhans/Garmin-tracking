# AI Fitness Data Connectors (MCP and similar), as of Nov 2026

Method note: web fetches of the vendor sites (athletedata.health, fmp.it.com, mcp.so) were blocked by this session's network allowlist. That leaves search snippets and one primary source. Both the Fitness AI Connector and the athletedata connector are attached to this Claude session, so their full tool names and server instructions were visible here. Where a finding is cited as "[session tool listing]", it comes from those live tool names and the servers' MCP instructions. Tool *names* are verified. What each tool returns is inferred from its name unless noted otherwise.

## Fitness AI Connector (Garmin MCP for Claude)

### Takeaway
This is a hosted, Garmin-only remote MCP with about 18 tools. It covers reads (activities, FIT files, health summary, body comp, cycle, trends), write-back of structured workouts to Garmin, and account/subscription tools. Login uses Garmin's OAuth, which suggests the official Garmin Connect Developer Program (GCDP) APIs. That reading is supported by the strict Garmin attribution rules it enforces.

### Cited Findings
- Full tool list: get_user_profile, get_help, get_activities, get_activity_details, get_activity_fit_file, refetch_activity_detail, set_activity_visibility, get_health_summary, get_body_composition, get_cycle_data, get_trends, refresh_data, create_workout, list_workouts, delete_workout, acknowledge_garmin_source, manage_subscription, delete_account — [session tool listing]
- Server instructions require an attribution_header ("Data from Garmin" + device name) and the footer "Insights derived in part from Garmin device-sourced data." on every turn that presents fetched data. They require per-activity device names (e.g. "Forerunner 955") from a `device` field, and say "Do not imply that Garmin endorses" any analysis. They also note that "Health API does not include device model information." The rules cite GCDP "Combined or Derived Data" compliance — [session MCP instructions]
- Onboarding: get_user_profile returns garmin_connected, a connect_url and example_questions. Errors return `garmin_not_connected` together with connect_url. The timezone offset from the profile is used to resolve "today" — [session MCP instructions]
- manage_subscription / delete_account return a portal_url / confirm_url, so this is a paid subscription managed in a web portal — [session MCP instructions]
- Sign-in goes through Garmin's own OAuth page, so the password is not shared. It is added to Claude as a custom connector via an MCP endpoint. A "Developer Option" costs +$10/mo for use from your own code or Claude Code, personal use only, with applications reviewed — [search snippet of fmp.it.com/en/fitness-ai](https://fmp.it.com/en/fitness-ai/); listing at [mcp.so](https://mcp.so/server/fitness-ai-connector/fmp-projects)
- Garmin's own Connect+ AI tier is $6.99/mo or $69.99/yr. It is separate from this connector — [Tom's Guide](https://www.tomsguide.com/wellness/smartwatches/garmin-launches-a-paywall-here-are-all-the-premium-connect-features-that-will-cost-you-usd6-99-a-month)

### Inferences
- The tool names refresh_data and refetch_activity_detail imply a server-side cache fed by Garmin push or ping notifications, with a manual re-pull available. That is typical of the official Health/Activity APIs. Data is therefore likely minutes-fresh after a watch sync, not real-time.
- acknowledge_garmin_source and the attribution rules point to an official-API partner. A free personal clone using unofficial garminconnect/garth logins would not need them, but it would carry ToS risk.
- There are no derived analytics tools (no CTL/ATL, curves or predictions). Analysis is left to the LLM, apart from get_trends.

### Gaps
- Base consumer price: not found (site blocked).
- Exact data fields per tool, the trend windows, and the workout formats create_workout supports (run, bike, strength?) are unverified.
- Sync latency is not stated anywhere I could reach.

## AthleteData (athletedata MCP)

### Takeaway
This is the broadest product found. It is a multi-provider aggregator with about 250 tools: raw per-provider tools for 20+ sources, cross-source deduped tools, a derived-analytics layer, athlete memory, and write-back to watches, TrainingPeaks, intervals.icu, Hevy, calendars and class booking. It runs on a paid plan with a 7-day trial. The price could not be verified.

### Cited Findings
- **Derived analytics tools:** get_pmc_status (CTL/ATL/TSB per the server instructions), get_readiness_today, get_load_flag, get_load_balance, get_intensity_distribution, get_efficiency_trend, get_pace_curve, get_power_curve, get_race_prediction, get_performance_estimates, analyze_dose_response, analyze_pattern, get_anomalies, reality_check_goal, get_training_trends, get_sleep_trend, get_analytics_summary — [session tool listing]
- **Cross-source and dedupe tools:** get_daily_metrics, get_sleep, get_activity_detail, get_activity_stream, get_dedupe_clusters, get_data_coverage, get_connection_status. The instructions say these tools "merge connected apps and count duplicate sessions once", while `<provider>_*` tools read one app each — [session MCP instructions]
- **Memory and context tools:** get_athlete_context (described as "shared memory, baselines and decisions", to be read before personalized advice), athlete_preference_update, coaching_note_create/get/delete, set_ftp, set_thresholds, set_units, list_athlete_files/read_athlete_file — [session tool listing and MCP instructions]
- **Write-back tools:** push_workout_to_watch, update_workout_on_watch, delete_workout_from_watch, list_workouts_on_watch (for when the watch is full, delete past workouts first), mywhoosh_push_workout, intervals_upsert_workout/move/delete, trainingpeaks_create/edit/move/delete_workout and save_note, hevy_create_routine/workout, google_calendar_create_event, plus classpass and urban_sports_club booking — [session tool listing]
- **Context data tools:** get_weather_forecast, get_historical_weather, geocode_location, race_search, race_get, race_results_lookup, food_log_* and nutrition_targets_*, get_glucose, get_blood_pressure, get_planned_workouts — [session tool listing]
- **Sources supported:** Garmin (activities, FIT files, daily summaries, HRV, sleep, stress, pulse ox, respiration, skin temperature, Move IQ, user metrics, refetch_day), Apple Health (workouts, run streams, HRV, RHR, sleep, VO2max, vitals, body comp), Google Health, Oura, Whoop, Withings, Polar is absent, Wahoo, Peloton, Concept2, Hevy, intervals.icu, TrainingPeaks, Terra, Eight Sleep, Renpho, Xiaomi, BodySpec DEXA, plus calendars and Sheets — [session tool listing]
- **Plan gating:** with no active plan, every data tool returns how to start the plan instead of data — [session MCP instructions]. Accounts get a 7-day free trial, and the API key is on the dashboard MCP page — [search snippets, athletedata.health/mcp](https://www.athletedata.health/mcp); [Hermes plugin docs](https://hermes-agent.nousresearch.com/docs/plugins/athletedata)
- **One athlete per connection:** each connection is scoped to a single athlete, and connections are "never merged" — [session MCP instructions]

### Inferences
- Its competitive moat is the derived layer (PMC, curves, readiness, anomalies, goal reality checks), the memory, and the dedupe, more than raw access. These are the features most worth replicating.
- The tool count (~250) is very large for an LLM context. A personal alternative should expose far fewer tools, ideally consolidated by intent.

### Gaps
- Prices and tiers: the pricing page was blocked and the snippets showed only testimonials.
- The algorithms are undisclosed: how readiness is computed, which TSS model is used, and how dedupe matching works. How Garmin is accessed (official API or otherwise) is also unknown.

## Other connectors and AI coaches

### Takeaway
Open-source MCPs exist for every major source and are free. Garmin ones mostly use unofficial login tokens (garminconnect/garth). They expose raw data, sometimes with intervals.icu-computed load. Commercial AI coaches (Runna, TrainAsONE, Athletica, AI Endurance, Humango) generate adaptive plans but are not LLM connectors.

### Cited Findings
- **Garmin, open source:** Taxuspt/garmin_mcp is the most popular (MIT; star counts conflict between listings). Others include eddmann/garmin-connect-mcp (activities, health, sleep, training analysis; MIT), garth-mcp-server, and stitrace/garmin-mcp-server. Most log in once and store tokens locally — [GitHub](https://github.com/Taxuspt/garmin_mcp); [ecosyste.ms](https://awesome.ecosyste.ms/projects/github.com%2Feddmann%2Fgarmin-connect-mcp); [PyPI garth-mcp-server](https://pypi.org/project/garth-mcp-server/)
- **intervals.icu:** hhopke/intervals-icu-mcp is read/write with 55+ tools (activities, streams, wellness, calendar, gear, zones, structured workout creation for bike, run and swim). It forks eddmann's version. mvilanova/intervals-mcp-server is GPL-3.0. A hosted option is discussed on the intervals forum — [PyPI](https://pypi.org/project/intervals-icu-mcp); [GitHub mvilanova](https://github.com/mvilanova/intervals-mcp-server); [intervals forum](https://forum.intervals.icu/t/hosted-mcp-server-for-connecting-claude-with-intervals-icu/126554)
- **Strava:** r-huijts/strava-mcp covers activities, segments, leaderboards and nearby segments. eddmann/strava-mcp has 11 tools across activities, stats, segments and routes. Users need their own Strava API app — [GitHub](https://github.com/r-huijts/strava-mcp); [eddmann README](https://raw.githubusercontent.com/eddmann/strava-mcp/HEAD/README.md)
- **Whoop and Oura:** community servers use the WHOOP v2 API (v1 was removed after 1 Oct 2025). One is local-only with a SQLite cache and CSV/Parquet export. The Oura API returns 403 without an Oura subscription — [PyPI whoop-mcp](https://pypi.org/project/whoop-mcp); [ouramcp README](https://raw.githubusercontent.com/davidmosiah/ouramcp/HEAD/README.md)
- **Terra:** a webhook-based aggregation API with a free tier. No Terra MCP was found, although athletedata wraps Terra — [Terra](https://www.tryterra.co/integrations/whoop)
- **AI coaches:** Strava acquired Runna in 2025, and its price conflicts between sources ($10 vs $15/mo). TrainAsONE has the deepest personalization but a less polished UI. Athletica starts around $20/mo. AI Endurance combines personal modelling with an AI chat coach. No good 2026 review of Humango was found — [RunnersPicks](https://www.runnerspicks.com/blog/best-ai-running-coaches-2026/); [Outside](https://run.outsideonline.com/training/which-is-better-human-run-coach-or-ai-run-coach/?scope=anon); [eliteai.tools](https://eliteai.tools/comparison/trainasone/vs/athletica); [SensAI](https://www.sensai.fit/blog/best-ai-marathon-training-apps-2026)

### Inferences: common design patterns
- **Memory and athlete context:** athletedata keeps a persistent profile (preferences, thresholds, coaching decisions), read before giving advice. Cheap to replicate with a local JSON/SQLite store.
- **Dedupe:** merged views count a session recorded by several devices once and expose the clusters for transparency. Replicate with time overlap plus sport plus duration matching.
- **Write-back:** both commercial products push structured workouts to Garmin. athletedata also handles watch capacity (list, then delete). With unofficial APIs, Garmin workout upload is possible via garminconnect.
- **Attribution:** official-API products must show the Garmin source, the per-activity device and a no-endorsement disclaimer. Not required for personal use, but a good provenance habit.
- **Local cache plus refresh tool:** a common pattern (refresh_data, refetch_day, SQLite caches).
- **Priority to replicate for free:** PMC (CTL/ATL/TSB), readiness from HRV/RHR/sleep against baseline, ACWR load flag, intensity distribution, pace/power curves, race prediction (Riegel/VDOT), anomaly detection, athlete memory, workout push.

### Gaps
- Humango feature details, and how these AI coaches present their insights, could not be checked first-hand.
- Whether any Apple Health MCP exists outside athletedata was not researched, because the search budget was used up.
