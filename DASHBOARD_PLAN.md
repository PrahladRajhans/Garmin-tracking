# Dashboard plan (v2, to be rebuilt from the ground up)

Status: **plan approved for build in Phase 11.** The v0.10 dashboard was a working prototype: it proved the data pipeline, but it is too dense, uses jargon ("L1/L2", CTL/ATL), puts two scales on one chart (CTL with "Garmin load ÷ 10"), and has no visual hierarchy. v2 starts from what a person wants to know, in this order: *How am I today? → Why? → What should I do? → Am I improving?*

## 1. Platform decision

| Option | Looks / glanceable | Private | Phone | Live from our data | Effort | Verdict |
|---|---|---|---|---|---|---|
| **Local web app (static HTML from Python, built after each sync)** | Full control: dials, cards, charts | Yes, never leaves the Mac | On the Mac; phone via the option below | Yes | Medium | **Chosen (core)** |
| Claude private Artifact page (snapshot published on request) | Same HTML | Private by default, but data leaves the Mac | Yes, anywhere | Snapshot per publish | Low (reuses core) | **Optional add-on**, only if you opt in, because health data is sensitive |
| Streamlit / local server | Good, more interactive | Yes | Only on home Wi-Fi | Yes | Medium; needs a running server | Not needed yet |
| Grafana | Ops-style panels, not friendly | Yes | Yes | Yes | High | Wrong tool for a personal health view |
| Notion | Tables and text; weak charts | Cloud | Yes | Needs a sync job, API limits | Medium | Good for a journal, not for charts |
| Google Sheets | Charts are basic; slow | Cloud | Yes | Needs a sync job | Medium | Good for exporting, not for daily glance |

**Decision:** one self-contained HTML page per day, generated locally, with no server, accounts or cloud. It's the only option that is private, free, pretty and always in sync with the same numbers Claude uses. Phone access later: a private Artifact snapshot (opt-in) or opening the file from iCloud Drive.

## 2. What others do well (and what we copy)
| App | What works | We copy |
|---|---|---|
| Whoop | Three big dials (Recovery %, Strain, Sleep %) with one colour each; everything else one tap deeper | **Three-dial hero**; colour only for recovery state |
| Oura | Contributor list under each score with plain words ("Optimal", "Pay attention") | **Contributors as plain-word rows** |
| Fitbit / Google Health | Personal-range bands ("in your range") on vitals | **Vitals in/out of range row** |
| Garmin | Morning report: one sentence of guidance | **One-sentence "Today" message** |
| Strava / intervals.icu | Fitness chart; run recap | **Simplified fitness trend**, **run card** |

## 3. Information architecture (one page, top to bottom; tabs only below the fold)

1. **Hero, three dials** (the whole answer in 2 seconds):
   - Recovery % (green/yellow/red with icon + word).
   - Sleep % (hours vs need).
   - Strain (0–21) with today's target range drawn on the dial.
2. **Today:** one sentence ("Easy day: resting heart rate is up 4 bpm; HRV is normal.") plus a suggested bedtime.
3. **Why:** contributor rows (HRV, resting HR, sleep, breathing): value, your normal, a ✓/↓/↑ icon and a word. Garmin readiness shown as a small grey "Garmin 54 · Moderate" chip.
4. **This week:** 7 small bars of strain with recovery colour dots; sleep hours vs need line; sessions list.
5. **Tabs (one chart per idea, one y-axis each):**
   - **Recovery:** 60-day HRV with your normal band; resting HR.
   - **Sleep:** duration vs need, bedtime consistency.
   - **Training:** fitness trend (one line), weekly load bars, intensity mix.
   - **Running:** last run card (pace, efficiency vs norm, form at the same pace), pace curve, race predictions (ours beside Garmin's).
   - **Body:** fitness age with levers, VO2max, weight.
6. **Patterns:** at most 3 plain-English findings ("Later bedtimes → shorter sleep for you"), with a "how sure" meter instead of r/CI. Details stay in a table view.

## 4. Design rules (from the dataviz skill + Whoop/Oura review)
- **No jargon on the surface:** say "fitness" not CTL, "fatigue" not ATL, "how sure" not r/CI/q; no "L1/L2". Technical values stay in tooltips and the table view.
- **One y-axis per chart;** two measures means two charts.
- **Colour with a job:**
  - Status colours (good/warning/critical) only for recovery state, always with icon + word.
  - Series colours from the validated categorical order.
  - Sequential blue for heatmaps.
  - Palette checked with the skill's validator in light and dark.
- **Hierarchy:** one hero row, big numbers, max ~7 elements above the fold, generous whitespace, 16 px side gutter on phone, no horizontal scroll.
- **Marks:** thin lines (2 px), rounded bar ends, direct labels on ≤ 4 series, faint grid, hover tooltips.
- **Garmin values** in neutral grey with a small "Garmin" label, never mixed into our series.
- **Honesty:** a "calibrating" or "based on 2 of 4 signals" note whenever data is thin; never show a score without its inputs one tap away.
- **Accessibility:** colour never alone; table view for every chart; dark mode chosen deliberately; works at 390 px.

## 5. Build steps (Phase 11)
| Step | Item |
|---|---|
| 11.1 | Score engine (Phase 10) finished and sense-checked ✅ |
| 11.2 | Static wireframe of the hero + Today + Why on phone and desktop; screenshot review |
| 11.3 | Palette run through the dataviz validator (light + dark) |
| 11.4 | Tabs: Recovery, Sleep, Training, Running, Body, each with a table view |
| 11.5 | Patterns section with a "how sure" meter |
| 11.6 | Headless-browser checks: no errors, no overflow at 390 / 768 / 1200 px, dark mode, print |
| 11.7 | Optional: private Artifact snapshot for phone, opt-in only |
