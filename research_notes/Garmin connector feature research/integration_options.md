# Garmin Forerunner 955 Data Integration Options (as of Nov 2026)

Research note: several primary hosts (developer.garmin.com, tryterra.co, techrepublic.com, forum.intervals.icu) could not be fetched from this session, so those sources are cited from search-engine snippets only. Verify claims marked [snippet] before relying on them.

## Official Garmin Connect Developer Program (Health, Activity, Training, Courses, Women's Health APIs)

### Takeaway
The biggest change is the **Garmin Personal API key**, which appeared around 21 Oct 2026. It gives an individual free, official, pull-only access to their own Activity (JSON + .FIT), Health and Women's Health data. The business tiers (Starter, Enterprise) are still the only route to the Training and Courses APIs and to push delivery.

### Cited Findings
- The business program is free to approved business developers. Garmin's FAQ says it is "only for business use", and some metrics may carry license fees or minimum device orders for commercial use. — [Garmin program FAQ](https://developer.garmin.com/gc-developer-program/program-faq) [snippet]
- Starter tier: push-only delivery, no historical data, limited user capacity. Enterprise tier: negotiated terms, broader history, Women's Health API. — [Garmin Health API enterprise page](https://developer.garmin.com/gc-developer-program/enterprise/health-api/) [snippet]
- New applications to the business program were paused (Garmin said the form was "currently unavailable while we complete updates"). Some requests were reportedly rejected without notice. — [Terra blog](https://tryterra.co/blog/garmin-connect-developer-program-pause) [snippet]; [Garmin forum](https://forums.garmin.com/developer/connect-iq/f/discussion/434542/garmin-connect-developer-program---access-request-rejected-without-notification/2025653)
- The program reportedly reopened after about 7 months closed and now includes a personal option. — [reendure](https://www.reendure.com/post/garmin-personal-api-access-training-data); [the5krunner, 22 Oct 2026](https://the5krunner.com/2026/10/22/garmin-personal-api/)
- **Personal API key details:**
  - Created on Garmin Connect web.
  - Expiry options are 30, 90 or 180 days, or 1 year.
  - The key is shown only once.
  - The key can't call data endpoints directly. It is exchanged for OAuth2 access tokens, which last 24h or until the key expires, whichever is first.
  - Covers Activity JSON & .FIT, Health JSON and Women's Health JSON.
  - Delivery is **pull-only**.
  - Personal, non-commercial use only; the key may not be shared with third parties.
  - Courses and Training (push workouts to watch) are only in the business tiers.
  - Reported free.
  — [Garmin personal FAQ](https://developer.garmin.com/gc-developer-program/personal/personal-faq/) [snippet]; [Garmin personal API page](https://developer.garmin.com/gc-developer-program/personal/personal-api) [snippet]; [appsforstrava](https://appsforstrava.com/blog/garmin-connect-developer-program-personal-api-key)
- Personal API flow, as documented by an implementer:
  1. POST the key with an `ApiKey` Authorization header to `/personal-api-key/token`.
  2. Receive a raw JWT, valid 24h with no refresh token.
  3. On a 401, re-exchange the key.
  — [Samiu1/garmin-connect-mcp](https://github.com/Samiu1/garmin-connect-mcp)
- That implementer counts 26 endpoints. Its 10 tools cover:
  - activities (search, detail, original file ZIP)
  - daily summary, sleep, HR, HRV, SpO2, fitness age, nutrition
  - trends (steps, stress, hydration, sleep, HRV, body battery, weight)
  - HR zones, profile, menstrual cycle
  - VO2max via an unpublished `/metrics-service/metrics/maxmet/daily` path
  — [Samiu1/garmin-connect-mcp](https://github.com/Samiu1/garmin-connect-mcp)
- Undocumented history caps found by testing: steps and stress 28 days; hydration 31 days; HRV, weight and wellness activities 365 days. Longer ranges return a bare HTTP 400. — [Samiu1/garmin-connect-mcp](https://github.com/Samiu1/garmin-connect-mcp)

### Inferences
- The Personal API is now the most reliable *official* path for a solo developer. It is free, sanctioned and pull-based, and a FR955's activity FIT files carry most of the depth.
- Its scope looks narrower than the unofficial API. Training readiness, training status, endurance and hill score, race predictions and lactate threshold were not listed by the implementer.
- Plan for re-issuing the key at least yearly, since the key itself expires.

### Gaps
- Official rate limits for the Personal API: none found.
- The official endpoint list was not fetchable. Whether training readiness, training status and the other advanced metrics are exposed is unconfirmed.
- The business-tier ping/pull vs push semantics could not be confirmed against the current docs.

## Unofficial libraries (python-garminconnect, garth, garmin-connect npm, GarminDB)

### Takeaway
- Garmin broke third-party logins in March 2026, using an auth flow change plus Cloudflare TLS fingerprinting.
- garth is deprecated.
- python-garminconnect (v0.3.x) recovered by mimicking the iOS app's mobile SSO and uses curl_cffi. It still has by far the richest endpoint surface (348 methods).

### Cited Findings
- garth: "deprecated and no longer maintained. Garmin changed their auth flow, breaking the mobile auth approach that Garth depends on." A maintained fork, garth-ng, exists. — [garth docs](https://garth.readthedocs.io/); [garth-ng on PyPI](https://pypi.org/project/garth-ng/)
- Login failures (401/403 on the OAuth exchange) started around 17 Mar 2026. — [python-garminconnect #332](https://github.com/cyberjunky/python-garminconnect/issues/332); [HA garmin_connect #420](https://github.com/cyberjunky/home-assistant-garmin_connect/issues/420)
- A Garmin forum thread reports that "Cloudflare TLS fingerprinting... breaks most/all non-browser clients". — [Garmin forum](https://forums.garmin.com/apps-software/mobile-apps-web/f/garmin-connect-web/433892/tls-fingerprinting-blocks-third-party-clients/2049649)
- python-garminconnect since 0.3.0:
  - Drops garth and uses the iOS mobile SSO flow, yielding DI OAuth bearer and refresh tokens stored at `~/.garminconnect/garmin_tokens.json`.
  - Tokens auto-refresh while the refresh token is valid.
  - MFA works through a `prompt_mfa` callback, or `return_on_mfa=True` plus `resume_login()`.
  - 348 public methods.
  — [python-garminconnect README](https://github.com/cyberjunky/python-garminconnect)
- Endpoints relevant to FR955 in python-garminconnect:
  - `get_hrv_data(_range)`
  - `get_training_readiness(_range)`, `get_morning_training_readiness`
  - `get_training_status`, plus daily and weekly variants
  - `get_body_battery`, `get_body_battery_events`
  - `get_race_predictions`
  - `get_endurance_score`
  - `get_hill_score`
  - `get_lactate_threshold`
  - `download_activity` (ZIP containing the original FIT, plus TCX, GPX, KML, CSV)
  — [python-garminconnect README](https://github.com/cyberjunky/python-garminconnect)
- Another self-healing auth wrapper with MFA, refresh and rate-limit recovery exists. — [garmin-auth on PyPI](https://pypi.org/project/garmin-auth/)
- GarminDB: latest release reportedly v3.8.0 (14 May 2026); a login bug fix was referenced as #109. — [dev.co listing](https://dev.co/databases/open-source/garmindb); [GarminDB discussion #110](https://www.github.com/tcgoetz/GarminDB/discussions/110)

### Inferences
- The unofficial route is high-value but fragile. Expect breakage whenever Garmin changes SSO or fingerprinting, and you depend on the maintainer reacting fast (March 2026 is the precedent).
- Ban risk comes mostly from login frequency. Caching tokens and avoiding repeated logins is essential.

### Gaps
- No published rate-limit numbers. Community lore on 429s after frequent logins was not verified.
- The current status of the garmin-connect npm package (Pulkit Singhal / Garmin-connect JS) was not researched.
- Ban reports: no reliable source found.

## FIT files

### Takeaway
Original FIT files are the richest per-activity data. They can be obtained through the Personal API (.FIT is officially included) or the unofficial `download_activity` ZIP. Parse them with Garmin's official `garmin-fit-sdk` (Python) or fitdecode.

### Cited Findings
- Garmin's official Python SDK is on PyPI as `garmin-fit-sdk` and uses a `Decoder`/`Stream` API. — [fit-python-sdk README](https://raw.githubusercontent.com/garmin/fit-python-sdk/main/README.md)
- FR955 product IDs were added in the FIT SDK release notes. — [FIT SDK release notes](https://forums.garmin.com/developer/fit-sdk/w/fit-sdk-wiki/92/fit-sdk-release-notes/revision/11)
- FIT `hrv` messages carry beat-to-beat RR intervals; for example, the fit-analysis tool parses them. — [tsteven4/fit-analysis](https://github.com/tsteven4/fit-analysis)
- Running dynamics fields (vertical oscillation, stance time, step length) appear in record messages. — [fit_decoder docs (illustrative)](https://readme.hex.pm/fit_decoder/0.1.0)
- A device-specific decode error was reported in a third-party library (fit_tool) with an FR965 file. — [Garmin forum](https://forums.garmin.com/developer/fit-sdk/f/discussion/363932/python-fit_tool-error-decoding-only-with-garming-forerunner-965-and-935-fit-file)

### Inferences
- FR955 FIT files should include records (HR, GPS, cadence, native running power, running dynamics with an HRM-Pro/RD pod or wrist-based), laps and sessions. With the "log HRV" setting on, they include `hrv` RR messages.
- Prefer the official SDK for new-field compatibility.

### Gaps
- No fetched source enumerates exactly which messages and fields an FR955 writes. Wrist-only vs pod running dynamics is unconfirmed.
- fitparse maintenance status and fitdecode behavior on FR955 were not verified.

## Garmin bulk export (GDPR) and Connect IQ

### Takeaway
Not researched in depth in this session. Neither offers a continuous automated feed.

### Cited Findings
- No sources retrieved.

### Inferences
- The GDPR export is a one-off ZIP (JSON plus FIT). Useful for backfilling history beyond the Personal API's 365-day caps.
- Connect IQ apps can only push data from the watch to your own server over the phone link while the app is running. That is impractical for an all-day health feed.

### Gaps
- Export contents and turnaround time; Connect IQ background web-request limits.

## Intermediaries (Strava, Apple Health, intervals.icu, Terra, Health Connect)

### Takeaway
- **Strava** is a poor fit: it receives activities only, and its Nov 2024 API agreement bars AI/ML use of API data.
- **intervals.icu** is an easy, free, official-API intermediary. It receives Garmin activities and wellness (including HRV) and exposes them with a personal API key.

### Cited Findings
- Strava API agreement update (effective 11 Nov 2024):
  - Third parties may display data only to the user themselves.
  - Using API data for AI/ML is prohibited.
  - Coverage reported further tightening in June 2026, with advice to seek written guidance before using the data in AI.
  — [DC Rainmaker](https://dcrainmaker.com/2024/11/stravas-changes-to-kill-off-apps.html); [TechRepublic](https://techrepublic.com/article/news-strava-api-scraping-crackdown) [snippet]; [Strava community thread](https://communityhub.strava.com/developers-api-7/ai-inference-with-strava-data-is-it-prohibited-under-the-new-api-agreement-13256)
- intervals.icu:
  - Every user has a personal API key, used via basic auth (user `API_KEY`).
  - Wellness, including HRV, is available via the API (for example a `wellness.csv` endpoint) when Garmin wellness sync is enabled.
  — [intervals.icu open API](https://www.intervals.icu/features/open-api/); [intervals.icu forum](https://forum.intervals.icu/t/api-access-to-intervals-icu/609/837) [snippet]
- A community "Garmin-intervals bridge" can now use Garmin's Personal API (thread active Oct 2026). — [intervals.icu forum](https://forum.intervals.icu/t/garmin-intervals-bridge-your-complete-garmin-fit-files-and-wellness-data-in-intervals-icu-with-or-without-the-official-garmin-integration-now-also-with-garmin-s-personal-api/132863.md?page=3) [snippet]
- Garmin HRV is mapped from "lastNightAvg" in intervals.icu (vendor blog, secondary). — [sensai.fit](https://www.sensai.fit/blog/apps-that-work-with-garmin)

### Inferences
- Terra is a paid aggregator and depends on Garmin business access, so it is not suited to a free personal connector.
- The Apple Health and Health Connect bridges carry only a subset (steps, HR, sleep, workouts). They lose Garmin-specific metrics such as body battery and training readiness.

### Gaps
- Terra pricing; what the Garmin→Apple Health and Garmin→Health Connect syncs include in 2026. None were verified this session.

## MCP vs alternatives (existing Garmin MCP servers, local DB + sync daemon)

### Takeaway
Many Garmin MCP servers exist. Most wrap python-garminconnect and inherit its fragility; one new server wraps the official Personal API. The most robust design is a sync daemon writing to a local database (SQLite or DuckDB) with a thin MCP server reading that database.

### Cited Findings
- **Taxuspt/garmin_mcp**:
  - Python, about 1.5k stars.
  - 110+ tools; 155 registered by default per its README.
  - Wraps python-garminconnect v0.3.2 at about 90% coverage.
  - One-time `garmin-mcp-auth` with MFA support; tokens reportedly last about 6 months.
  - Workarounds for 403s on activity details.
  — [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp)
- **Samiu1/garmin-connect-mcp**: wraps the official Personal API (bring your own key), with 10 tools over 26 endpoints. — [repo](https://github.com/Samiu1/garmin-connect-mcp)
- Others:
  - eddmann/garmin-connect-mcp (activities, health, sleep, training)
  - stitrace/garmin-mcp-server (MFA, token caching)
  - colincooperio/garmin-mcp (Cloudflare-hosted)
  - arnaud-marcel/garmin-mcp
  - PyPI packages: garmin-mcp-server, mcp-garmin, garmin-connect-mcp
  — [ecosyste.ms eddmann](https://awesome.ecosyste.ms/projects/github.com%2Feddmann%2Fgarmin-connect-mcp); [arnaud-marcel](https://github.com/arnaud-marcel/garmin-mcp); [PyPI garmin-mcp-server](https://pypi.org/project/garmin-mcp-server/); [PyPI mcp-garmin](https://pypi.org/project/mcp-garmin/)

### Inferences (recommended architecture)
1. **Primary source:** the Garmin Personal API. It is official and covers activities and FIT, daily health, sleep, HRV, body battery and VO2max. Exchange the key for the 24h token, cache it, and run the sync daemon daily (or every few hours).
2. **Optional enrichment:** python-garminconnect, for metrics the Personal API lacks (training readiness and status, endurance and hill score, race predictions, lactate threshold). Isolate it as a best-effort module so its breakage doesn't take down the core.
3. **Store** raw JSON plus parsed FIT (via garmin-fit-sdk) in SQLite or DuckDB. Backfill older history from a one-time GDPR export.
4. **Expose** a small number of MCP tools that query the local database (no live API calls). This removes rate-limit and ban exposure and makes AI responses fast.
5. **Avoid Strava** as a data source for AI because of its terms.

### Gaps
- Exact tool counts and maintenance status for the smaller MCP servers were not verified.
