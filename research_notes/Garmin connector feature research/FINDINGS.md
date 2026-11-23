# Garmin connector research: FINDINGS index (Nov 2026)

Goal: a free personal FR955 connector. **Local sync → SQLite → thin MCP server.** This page is the quick read; details live in the linked files.

## Key decisions
1. **Primary data path:** the official **Garmin Personal API key** (free, pull-only, Activity JSON + FIT, Health, Women's Health; key expires ≤1 yr). Exchange the key for a 24 h JWT and re-exchange on 401.
2. **Augment path:** **python-garminconnect** (v0.3.x, mobile SSO + curl_cffi) for metrics the Personal API lacks: Training Readiness/Status, race predictor, endurance/hill score, LT. Isolate it behind an adapter because it can break without warning (it did in Mar 2026).
3. **Backfill:** a one-time Garmin account data export ZIP, plus USB FIT as an offline fallback.
4. **FIT parsing:** the official `garmin-fit-sdk` (Python). Fall back to fitdecode.
5. **Storage:** SQLite with raw tables (activities, FIT streams, daily wellness, sleep, HRV) plus derived tables. Keep dated thresholds so history can be recomputed.
6. **Analytics:** store Garmin's Firstbeat values (opaque) **alongside** open, transparent equivalents (TRIMP/rTSS → CTL/ATL/TSB, ln RMSSD baseline, VDOT/Riegel/CS, decoupling, polarization). Never mix them in one series.
7. **MCP:** a small tool set (~15–25 tools). Copy the useful AthleteData analytics, skip multi-provider sprawl.
8. **Writes (workouts):** encode a FIT workout file and copy it via USB, or use the unofficial workout JSON upload. The official Training API is business-only.
9. **Skip:** skin temp/ECG (no FR955 sensor), ACWR as an "injury risk", composite scores without visible components.

## Files
| File | One-line verdict |
|---|---|
| [integration_options.md](integration_options.md) | The Personal API (Oct 2026) is now the best official path. Unofficial libs work again but are fragile. garth is deprecated. Recommends a local DB + sync daemon + MCP |
| [github_and_garmin_resources.md](github_and_garmin_resources.md) | GitHub and Garmin resource tables (stars, licence, activity). Shortlist: Personal API, python-garminconnect, garmin-fit-sdk, GarminDB ideas (GPL), neurokit2, reference MCPs |
| [fr955_metrics.md](fr955_metrics.md) | The FR955 has the full 2022 Firstbeat suite plus Endurance/Hill (fw 2023). No skin temp or ECG. Readiness weights are unpublished |
| [garmin_insights_reference.md](garmin_insights_reference.md) | Table of 25 Garmin insights: inputs, publication status, ranges/labels, FR955 support and the open equivalent we'd compute |
| [metric_formulas.md](metric_formulas.md) | Implementable formulas: NP/TSS/rTSS/TRIMP, PMC, HRV baseline/SWC, VDOT/Riegel/CS/W′bal, EF/decoupling, polarization, monotony. Covers ACWR caveats |
| [analytics_platforms.md](analytics_platforms.md) | Whoop/Athlytic/Strava/Oura publish concepts, not formulas. intervals.icu/Runalyze/GC are the most open. Users trust sleep, RHR and HRV trends over composites |
| [ai_connectors.md](ai_connectors.md) | Fitness AI Connector (hosted, GCDP-based, 18 tools) and AthleteData (paid, ~250 tools). Open-source Garmin MCPs are free but use unofficial auth |
| [connected_connectors_inventory.md](connected_connectors_inventory.md) | Tool inventories of both connected MCPs, with a copy/skip list for a single-FR955 user |

## Top open questions
- Exact Personal API endpoint list. Does it include readiness, training status or advanced metrics? (Unconfirmed; implementer evidence says no.)
- Personal API rate limits (none published).
- Long-term stability of python-garminconnect against Cloudflare TLS fingerprinting.
- Whether LT auto-detect on the FR955 works without a chest strap (guided test definitely needs one).
- Unverified, still open: HRV SWC multiplier choice, Edwards/Banister constants, fitness-age formula, heat-HR model (garmin.com/support/www8 hosts unreachable from fetch; see VERIFICATION_LOG.md).
- Garmin Connect+ "Active Intelligence" has no API, so it's out of scope. Re-check for an official Garmin MCP periodically.

## Suggested build order
1. Personal-API auth + activity/FIT sync → SQLite.
2. Daily health (sleep, HRV, RHR, stress, BB) sync, plus backfill from the export ZIP.
3. A python-garminconnect adapter for Firstbeat-only metrics.
4. Derived analytics (PMC, HRV baseline, readiness components, pace curve, race prediction).
5. MCP server: raw reads, derived reads, daily brief, data coverage, refresh/refetch-day.
6. Optional: FIT workout encoder, Grafana view, intervals.icu as a 2nd source.
