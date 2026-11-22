# GitHub and Garmin-provided resources (as of 22 Nov 2026)

Method: GitHub stars, last push date and licence come from `gh api search/repositories` run on 22 Nov 2026. `[snippet]` means the claim comes from a search snippet only. `[bg]` means it is background knowledge that was not re-verified this session. Auth and Personal API details are in integration_options.md and are not repeated here.

## 1. GitHub: data access (Garmin Connect)
| Repo | Stars | Last push | Lang | Licence | What it gives us |
|---|---|---|---|---|---|
| cyberjunky/python-garminconnect | 3283 | 2026-10-31 | Py | MIT | Richest unofficial API (~348 methods): readiness, status, HRV, BB, race preds, LT, endurance/hill. Works again since v0.3.x (mobile SSO + curl_cffi) |
| matin/garth | 819 | 2026-06-09 | Py | MIT | Deprecated (broken by the Mar 2026 auth change). Do not build on it |
| garth-ng (PyPI fork) | n/a | n/a | Py | MIT [bg] | Maintained garth fork. Fallback auth layer only |
| tcgoetz/GarminDB | 3368 | 2026-11-19 | Py | GPL-2.0 | Download + FIT parse into **SQLite** (monitoring, sleep, RHR, activities). Closest to our design; the GPL licence means we copy ideas, not code |
| pe-st/garmin-connect-export | 498 | 2026-04-06 | Py | MIT | Bulk activity export (FIT/GPX/TCX + CSV). Good for backfill |
| nrvim/garmin-givemydata | 173 | 2026-10-20 | Py | ? | Personal bulk-dump tool (newer; not evaluated) |
| Samiu1/garmin-connect-mcp | 0 | 2026-11-14 | TS | MIT | Reference implementation of the **official Personal API key** flow, with endpoint history caps |
| Mason-Levyy/garmin-personal-mcp | 76 | 2026-11-15 | Py | ? | A second Personal-API MCP, in Python. Worth reading |

## 2. GitHub: FIT parsing
| Repo | Stars | Last push | Licence | Notes |
|---|---|---|---|---|
| garmin/fit-python-sdk (`garmin-fit-sdk`) | 170 | 2026-11-17 | Garmin FIT licence (permissive) | Official SDK and always current with the profile. **Pick this** |
| garmin/fit-javascript-sdk | 81 | 2026-11-17 | same | Use if the MCP server is TypeScript |
| polyvertex/fitdecode | 221 | 2025-08-06 | MIT | Fast, streaming, handles chained FIT. Good alternative |
| dtcooper/python-fitparse | 826 | 2025-01-28 | MIT | Effectively stale. Avoid for new code |

## 3. GitHub: MCP servers (Garmin and adjacent)
| Repo | Stars | Last push | Lang | Notes |
|---|---|---|---|---|
| Taxuspt/garmin_mcp | 1540 | 2026-10-24 | Py | Most popular Garmin MCP. Live calls via python-garminconnect, no local DB |
| Nicolasvegam/garmin-connect-mcp | 193 | 2026-11-05 | TS | TS alternative |
| eddmann/garmin-connect-mcp | 68 | 2026-05-20 | Py | Small and clean. Inactive since May (possibly broken by the auth change) |
| thetahealth/mirobody | 1664 | 2026-11-22 | Py | Multi-source personal-health MCP platform. Heavier than we need |
| ghighi3f/garmin-grafana-mcp-server | 12 | 2026-06-29 | Py | MCP over the garmin-grafana InfluxDB. Same pattern as ours (local store + MCP) |
| mvilanova/intervals-mcp-server | 398 | 2026-08-02 | Py | intervals.icu MCP: CTL/ATL, wellness, events |
| hhopke/intervals-icu-mcp | 127 | 2026-11-22 | Py | Active intervals.icu MCP |
| soma-intelligence/open-health-sync | 72 | 2026-11-22 | Go | Multi-source sync. Worth comparing as a sync engine |

## 4. GitHub: dashboards, analytics, HRV
| Repo | Stars | Last push | Licence | Use for us |
|---|---|---|---|---|
| arpanghosh8453/garmin-grafana | 3563 | 2026-11-08 | BSD-3 | Docker: garminconnect to InfluxDB to Grafana. Its fetcher shows which daily endpoints matter. An optional visual layer |
| jimmykane/quantified-self | 237 | 2026-11-22 | ? (TS) | Web FIT analysis. Ideas for the UI only |
| GoldenCheetah/GoldenCheetah | 2266 | 2026-11-22 | GPL-3 | Reference implementations (TRIMP, PMC, CP/W′). Read, don't link |
| GoldenCheetah/sweatpy | 79 | 2022-12-08 | MIT | CP/W′bal/mean-max in Python. Stale but small and copyable |
| corriporai/runpandas | 26 | 2023-03-15 | MIT | Pandas for runs. Stale; skip |
| paulvangentcom/heartrate_analysis_python (heartpy) | 1155 | 2025-12-30 | MIT | RR/PPG HRV. Only needed if we get RR intervals (FIT `hrv` msgs from strap) |
| neuropsychology/NeuroKit (neurokit2) | 2433 | 2026-11-22 | MIT | Full HRV suite (time, frequency, nonlinear) and artefact correction. **Pick for any HRV maths** |

## 5. GitHub: intervals.icu and workout builders
| Repo | Stars | Last push | Notes |
|---|---|---|---|
| CrankAddict/section-11 | 170 | 2026-11-12 | intervals.icu AI-coach tooling |
| freekode/tp2intervals | 102 | 2026-04-12 | TrainingPeaks to intervals.icu plan copy |
| LeonardHd/python-intervals-icu-client | 0 | 2026-03-09 | Thin client. The intervals.icu REST API (API key, basic auth) is simple enough to call directly |
| mkuthan/garmin-workouts | 128 | 2026-11-10 | YAML to Garmin Connect workout JSON and upload (unofficial). Reference for the workout JSON schema |
| mgifos/quick-plan | 157 | 2026-03-27 | Plan from CSV to Garmin workouts |
| philosowaffle/peloton-to-garmin | 360 | 2026-04-10 | Shows how to write FIT activity files that Garmin accepts |
| drkostas/hevy2garmin | 190 | 2026-11-20 | Strength-to-Garmin sync. FIT encoding reference |
| FIT SDK `Encoder` (workout file) | n/a | n/a | Official route: build a `workout` FIT file and copy it to `/GARMIN/NEWFILES` over USB. No API needed [bg] |

## 6. GitHub: Connect IQ
| Repo | Stars | Last push | Notes |
|---|---|---|---|
| garmin/connectiq-apps | 596 | 2025-01-08 | Official sample apps (Apache-2.0) |
| Likenttt/garmin-connectiq-samples-brief-explanations | 144 | 2026-08-08 | Annotated SDK samples |
| douglasr/connectiq-samples | 80 | 2024-03-12 | Community samples |

## 7. Garmin-provided options
| Option | Cost / access | Gives | Verdict for us |
|---|---|---|---|
| **Personal API key** (GCDP personal) | Free, self-serve, keys valid up to 1 yr | Activity JSON + FIT, Health, Women's Health; pull only | **Primary official path** (see integration_options.md) |
| GCDP business: Health, Activity, Training (push workouts), Courses, Women's Health | Free but approval-gated, business only; was paused ~7 months | Push/ping delivery, Training/Courses write | Not available to an individual; skip |
| FIT SDK (Py/JS/C/Java/C#…) | Free | Decode/encode FIT, including workout files | Use (decode activities, encode workouts) |
| Connect IQ SDK (Monkey C) | Free | On-watch apps, data fields, widgets; can log custom FIT dev fields; Health/ActivityMonitor read APIs [bg] | Optional later: e.g. a custom field that records RR or RPE |
| Garmin data export (Account → Export Your Data) | Free, takes days | Full ZIP: all FIT files, JSON wellness, sleep, etc. [bg] | One-time historical backfill |
| USB mass storage on the FR955 | Free | `/GARMIN/Activity/*.fit`, monitoring FIT [bg] | Offline fallback, no cloud needed |
| Official partner sync: Strava, TrainingPeaks, intervals.icu, Apple Health, Google Health Connect, Runna, Zwift etc. | Free | Activities (and some wellness) leave Garmin automatically | intervals.icu sync = free computed PMC/eFTP plus a simple API; a useful 2nd source |
| **Garmin Connect+** (Mar 2025, ~$6.99/mo) "Active Intelligence" | Paid | AI-written insights in the Connect app, performance dashboards, LiveTrack+ [bg/snippet] | Closed: no API or MCP. Shows what users value; nothing for us to integrate |
| Official Garmin MCP / LLM API | None found (Nov 2026) | n/a | Doesn't exist; this gap is why we're building |

## Shortlist for us
1. **Garmin Personal API key**: official, free, stable. Use it for activities, FIT files and daily health. Re-issue the key yearly.
2. **python-garminconnect**: a fallback/augment for metrics the Personal API lacks (Training Readiness, Training Status, race preds, endurance/hill, LT). Accept the breakage risk.
3. **garmin-fit-sdk (Python)**: canonical FIT decode, plus encoding of structured workouts for USB/Connect upload.
4. **GarminDB (ideas only)**: SQLite schema and FIT-monitoring parsing patterns. Write our own code because of the GPL.
5. **neurokit2 + sweatpy-style code**: HRV maths, CP/W′, mean-max. Everything else (TRIMP, PMC, VDOT) is implemented directly from metric_formulas.md.
6. **Taxuspt/garmin_mcp + Samiu1/garmin-connect-mcp**: reference tool surfaces and Personal-API auth, for our thin MCP server.
