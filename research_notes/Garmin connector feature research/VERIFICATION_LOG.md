# Verification log (2026-11-23)
Note: WebFetch could not resolve www8.garmin.com or support.garmin.com; verification used search-indexed Garmin manual pages + the5krunner. Formula items (METRICS.md ⚠: HRV SWC, TRIMP, fitness age, heat) not re-verified this pass.

| Claim | Old | Verified/corrected | Source |
|---|---|---|---|
| Training Readiness bands | labels only [bg] | Prime 95–100, High 75–94, Moderate 50–74 (Low/Poor bounds bg) | FR955 OM (manualowl) |
| HRV Status labels | labels only | Balanced/Unbalanced/Low/Poor defined; Poor = vs age norm; 3 wk data | Garmin manual HRV Status page |
| Stress bands | [bg] | Verified 0–25/26–50/51–75/76–100 | Garmin manual stress page |
| Sleep Score bands | Poor <60 [bg] | Verified; Garmin writes poor 0–60 | garmin.com blog p=34517 |
| Recovery Time max | 96 h [bg] | Verified (4 days) | FR955 OM p.45 |
| Wrist running dynamics | ⚠ VO/GCT probably absent | CORRECTED: present via wrist RD (fw 15.09+); only GCT balance absent | the5krunner 2023-04-04; Garmin RD manual page |
| LT requires chest strap | unverified | Guided test: yes. Auto-detect: open | FR955 OM p.40; Garmin forum |

## v0.5.0 additions (verified on real data or by test)
| Claim | Result | How |
|---|---|---|
| FIT running fields are scaled by the SDK to m/s, mm, ms, one-foot rpm | verified | cadence×2×step_length = speed within 0.3 % on all runs |
| Garmin HR-zone upper bounds are exclusive (HR < bound) | verified | recomputed zone times match Garmin's FIT time_in_zone 0.0–1.0 % on runs |
| Banister, VDOT, Riegel, Swain, Minetti constants | pinned | unit tests (tests/test_loads.py); VDOT matches Daniels' table (5K 19:57 ≈ 50) |
| running_and_sport_metrics.md was written from memory (no page fetches) | caution | constants used in code are pinned by tests above; others stay unverified |

## v0.17.0 run evidence and conditions

- Tested the prior-only matched-run median and sample span against deterministic moving HR
  values. Tested rejection of future runs, materially different efforts and missing ascent/HR.
- Tested that the readiness benchmark excludes post-run snapshots and reports sample
  coverage. The synthetic coefficient validates the calculation, with live coverage and
  prospective usefulness pending.
- Checked the unofficial weather shape and unit conventions against two independent
  source implementations and verified conversion from 77 °F to 25 °C. Real Garmin
  payload coverage remains to be checked on the Mac. [Source details](owner_reference_review_2026-11.md#implemented-in-v0170)
