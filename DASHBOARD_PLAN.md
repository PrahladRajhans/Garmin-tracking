# Dashboard plan (v2, to be rebuilt from the ground up)

Status: **built in v0.12 (Phase 11 + 12).** Sections 6-8 are the as-built UI map and design system. The v0.10 dashboard was a working prototype: it proved the data pipeline, but it is too dense, uses jargon ("L1/L2", CTL/ATL), puts two scales on one chart (CTL with "Garmin load ÷ 10"), and has no visual hierarchy. v2 starts from what a person wants to know, in this order: *How am I today? → Why? → What should I do? → Am I improving?*

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

## 6. UI map (as built: multi-page, one file)

Sleep leads with a dated night, a prominent duration, timing and Garmin's score. Stage intervals
are drawn in chronological lanes only when present. Recent night links open the full day view;
history disclosures show nights recorded, duration and Garmin score coverage. Chart readings
appear during inspection and the shared default state has no interaction prompt.
[Garmin sleep glance reference](https://support.garmin.com/en-MY/?faq=HkovCl61Zm7sbUKB8wG2d9)


One self-contained `index.html`. Each "page" is a section addressed by a link (`#sleep`, `#run-123`); the browser shows one at a time with plain CSS (`:target`), so page navigation also works with scripts disabled. The bundled offline script adds chart inspection and an appearance switch. The browser Back button works between pages.

```
Today (home) ─┬─ Sleep ───────── last night breakdown, HR dip, 30 nights, bedtimes
              ├─ Recovery ────── HRV vs your normal band, resting HR, detected shifts
              ├─ Training ────── fitness trend, weekly load, intensity mix
              ├─ Running ─────── run list ─── Run detail (per run): form gauges vs Garmin
              │                  pace curve,                  and vs your usual at that pace,
              │                  race predictions,            km splits, what to work on
              │                  Marathon shape, form trends
              ├─ Body ────────── fitness age + levers, pace of ageing, VO2max, month report
              └─ Patterns ────── up to 6 findings with a "how sure" meter, full text on tap
```

Each page answers one question, top to bottom: **headline number → one sentence → one chart per idea → detail table**. Every hero row links to the page that explains it (tap Recovery dial → Recovery page).

Today uses a large daily guidance card and puts recorded activity alongside it on desktop.
On narrow screens these cards stack, and persistent labeled tabs sit at the bottom. The health
and activity tiles link to the relevant detail pages. The hierarchy draws on Garmin Connect's
Home design, including its activity section, large focus cards and compact glance cards.
[Garmin Connect Home](https://support.garmin.com/en-GB/?faq=35qboQSvKC2WpKkTaDaRP7)

## 7. Design system (as built)

| Element | Rule |
|---|---|
| Type | System sans (SF Pro on Apple). Scale 12 / 13 / 15 / 17 / 22 / 34 / 48 px. Body 15 px, line-height 1.5. Headings 1.25. Big numbers 1.05, letter-spacing −0.02 em, proportional figures. Small caps labels 12 px, +0.06 em, uppercase, muted ink. Tables use tabular figures. |
| Spacing | 4 px base grid: 4 / 8 / 12 / 16 / 24 / 32 / 48. Card padding 20 (16 on phone). Gap between cards 16. Section gap 32. Side gutter 14 on phone, max width 1160. |
| Shapes | Cards radius 16, hairline border, no shadows. Pills radius 999. Bars 4 px rounded data end, 2 px gap between bars. Dials 10 px stroke with round caps on a 270° track. |
| Icons | Inline 16 px line icons, 1.75 px stroke, 8 px gap to the label, always paired with a word. |
| Lines | Data lines 2 px; reference lines 1 px dashed; grid hairline 1 px at 3 ticks max; markers 8 px only on the latest point. |
| Colour | Status (green/amber/red) only for recovery state and form ratings, always with a word. One series blue; a second series uses orange. Garmin values in grey with a "Garmin" label. Validated with the dataviz palette validator, light + dark. |
| Representation | Dial = today's score; bullet/gauge bar = value against bands; line + band = trend against your normal; bars = amounts per day/week; dot strip = timing (bedtimes); table = exact values. Never two y-axes. |
| Interaction | Native hover/long-press tooltips on every mark (SVG `<title>`). Links for drill-down. |

## 8. Hosting and viewing live
Body-page addition (v0.14.0): VO₂max uses an exact FRIEND 2015 population reference with
separate Garmin/effective markers, a table/source disclosure, and the HRmax caveat. Neutral
reference bands avoid turning population ranks into health diagnoses. Missing age/sex remains explicit.

- **Mac:** `$GARMIN_DATA_DIR/dashboard/index.html`, default `~/.garmin-mcp/dashboard/index.html`,
  rebuilt after each sync. Reload an open Safari tab to see the new file.
- **iCloud:** `dashboard.build` copies the HTML to `iCloud Drive/Garmin/dashboard.html` only when
  the iCloud directory exists. Actual Mac copying and phone navigation remain unverified.
- **Anywhere:** optional Cloudflare Pages + Access, implemented in v0.13.1 and disabled by default.
  After local build, sync/the CLI/the MCP build tool call `publish.publish_if_enabled`. It checks
  the production hostname, wildcard previews, exact-email Access policies, conflicting Access
  apps, and anonymous login redirects before uploading the HTML with Wrangler. Only a dedicated
  Direct Upload project without custom domains is supported. Unknown/unsafe configuration or
  an upload error leaves the local build intact and reports an error separately.
- **Alternatives:** Tailscale requires an awake, connected Mac; iCloud viewing needs device checks;
  private Artifacts are manual snapshots. Public GitHub Pages and public dashboard URLs remain
  excluded. Cloudflare is the preferred candidate because the uploaded copy works while the Mac
  is off. Confirm Access free-plan eligibility and perform the live phone checks before calling
  this deployed. No user health data was uploaded during development.

Setup: [MAC_SETUP.md](MAC_SETUP.md#private-phone-access-optional). Source review and verified limits:
[hosting research](research_notes/Garmin%20connector%20feature%20research/private_dashboard_hosting.md).
Sections 1 and 5 retain the original design history; this section records the updated hosting decision.

## Accessibility and reliability follow-up (v0.14.1)

See [UI_REVIEW](docs/UI_REVIEW.md) for before/after evidence. Native disclosures expose exact
chart data with scoped headers and captions. Date-based line charts preserve elapsed gaps;
missing bars keep their original status colour. Text remains legible in both colour themes,
focus has a visible outline, and navigation/disclosure targets are at least 44 px high.
The empty dashboard explains how to obtain data. Today reports signal coverage and partial
syncs; no stale health-status row is presented as today. The footer says "Data through".
HTML is still script-free and responsive, with atomic local/iCloud replacement. Real Safari,
iCloud and Cloudflare Access tests remain rollout work; Chromium checks do not close those.

## Run pacing drill-down (v0.14.2)

Running → activity → Pacing and effort. The split line uses elapsed seconds with clock-formatted
values and a table. The timing card puts FIT sample-derived times next to watch session times.
A separate card presents heart-rate change in bpm and grade-adjusted speed per heartbeat
in percent, with both based on equal recorded moving-time halves. Back links follow the
same static fragment navigation as the rest of the dashboard.

## Monthly history and pattern evidence (v0.14.3)

Body → Month report shows six complete calendar months. Short proportional bars share a scale
within a metric, with values and coverage in the same row. Empty months retain their positions
and use a dash. Patterns lists eligible and qualifying pair counts and shows fit lines only for
pairs passing the existing rule. Expanded evidence gives units and both dates. Phone layout
fits all seven top links on two rows.

## Direct chart interaction and insight hierarchy (v0.15.0)

Today opens with the training plan, scores, and a short list of evidence-backed findings
linked to the detail pages. Training puts recorded workouts and sleep coverage together.
Sleep puts the latest duration and duration chart before supplementary Garmin details.

The chart itself is the control. Hover and drag with a mouse, tap or slide horizontally
with a finger, or focus the plot and use the arrow keys. Vertical touch gestures can
scroll the page. The highlight shows the selected observation and leaves axis labels
uncovered. Chart-value tables were removed. Month comparisons and measurement rows
display their data directly. Each scatter axis names the variable and unit, and zero
represents the recent personal baseline. Fits are shown for qualifying pairs only.

The default is Light and a visible Light/Dark switch is offered when scripting runs.
Both themes preserve axis contrast and focus. The self-contained HTML draws the charts
and links without script support. Some file previews may render only that static view.
See the latest [UI review](docs/UI_REVIEW.md#direct-interaction-review-v0150).

In v0.15.1 the smaller chart marker and thinner guides keep the data visible. The cursor
renders at most once per frame while moving and horizontal touch intent is detected before
updating it. Vertical swipes use native scrolling. A tap still selects the release point.

## Chart sizing (v0.23.0)

Choose the plot drawing using the available width inside its card. Narrow cards keep the
mobile drawing and limit its width. Wide cards use the desktop drawing, with a maximum
plot width of 720 CSS pixels. Maintain the SVG aspect ratio so axis labels and chart
inspection stay aligned. The VO₂max reference band uses the same layout with a shorter
drawing and a compact reading area. The latest three full run timelines offer one overlay at
a time, selected from the readings present in that workout. The second series shares the
same elapsed-time axis and uses a labelled right axis in its original units. Garmin form
bands, recorded heart-rate bands, personal recovery ranges and the sleep goal have color
and text status. The section links at the top jump within the run. Timeline, splits,
conditions and earlier efforts are on the run page. Previous deep links open the same sections.

## Personal ranges, History and the run overlay trial (v0.16.0)

Today remains a short entry point. Recovery cards show a reading line, dashed recent
average and shaded personal range where supported. Each card names the observation
count and comparison period, and gives a brief next check. Sleep and Training show
the weekly average and a reference suited to that metric.

History covers 12 complete calendar months plus the month to date and allows opening
a recorded day from its month. Week shows the recent seven days. Day views include
available readings, workouts and recent hourly pulse. Missing periods remain explicit.

The recent run timeline has two separate optional overlays. Speed and heart rate,
and cadence and step length, use relative change from each signal's median on their
common elapsed-time axis. The readout shows actual sensor values with units. No route
coordinates are included. The owner can try these pairs before a broader rollout.

## Matched effort and timed conditions (v0.17.0)

A run starts with one sentence about heart rate versus comparable sessions and a brief
check when the reading falls outside their observed span. Selecting the card opens the
measured points, a dashed median, a shaded min–max and dated rows in actual units.
The points are unconnected because these are separate efforts. Each available run
page can be opened from its row. Training puts the pre-run readiness benchmark behind
a short summary and expandable paired runs. No fit is shown on that scatter plot.

In Run timeline, outdoor temperature and AQI are secondary information in the point
readout, with units, source and standard. They add no axis and are present only for
covered sample times. Outdoor conditions lists the Garmin snapshot and expandable
source windows. The dashboard remains an offline file with the current bundled controls.

## Coaching-first overview (v0.18.0)

Today offers the next seven days, using recent run frequency and duration, recovery state
and status tags. A stale snapshot or incomplete sync hides the plan. Recovery stays
muted during calibration. Running starts with “What to try next” and offers the optional
knee-aware trial when measured cadence and context qualify. Stats that need more history
stay queryable in MCP. Patterns renders qualifying plots and summarizes other comparisons.
The dashboard keeps 30 detailed day pages with prior days summarized in their month.
The footer shows the time of the last completed sync and the build’s code version.

A representative year-long synthetic dashboard dropped from 424 sections to 83 and
from 3.07 MB to 2.02 MB. Chromium and WebKit checks exercised 190 page, width, theme
and coverage combinations. A script-disabled browser could still open an older month
and read its day summaries. Test the scheduled Mac output on a physical iPhone before
drawing conclusions about Files preview speed or script support.

## Today-first flow (v0.19.0)

Today answers three questions in order: what to do today, what the watch recorded, and
what to plan for the next seven days. Up to three follow-ups give a reason, an action and
a link to evidence. Trends links to the older overview pages. Recovery uses a collapsed
14-day history. Workout comparison has two time-aligned tracks with separate scales and
actual units. Conditions stay near the workout. See the [product review](docs/PRODUCT_REVIEW_2026-11.md)
and [visual checks](docs/UI_REVIEW.md#today-first-flow-v0190).

## Conditions in context (v0.20.0)

The run overview uses a short line for available conditions. A timed reading belongs
to its point on the workout timeline. Conditions across comparable workouts sit behind
Heart rate on similar runs. Sleep shows its own measured room comparisons, including
paired dates in a disclosure, when enough observations exist. Keep these details out of
the first screen and preserve coverage gaps.

## Coaching follow-up (v0.25)

Today shows a wake-time follow-up, Sunday recap and movement progress as evidence permits.
Training shows the saved week and how recorded sessions matched it. Sleep shows journal
comparisons alongside its existing history intervals. The latest run can show a route replay if
the earlier activity's recorded GPS corroborates the match. The graph compares elapsed time per
kilometre, with both input times listed beneath it. The HTML remains offline and read-only.
Use the local MCP tools to enter or revise a check-in or planned session.

### Interpretation layout

Today places the optional model interpretation between the core readings and the longer weekly
plan. The lens labels its focus. Current cited readings link to their detail pages. Earlier
reviewed evidence is labeled separately. The question below the observation suggests what to
compare next. The evidence disclosure shows if the worker fell back to a direct draft.

### Running performance

Running opens with one action, its linked basis and the last four completed weeks. Volume
and effort plots follow. Readers can expand exact recorded values and follow available run
links. Race estimates and extra form trends stay in disclosures. Individual runs give both
moving-time halves and prior form evidence. The timeline's native Kilometre splits control
reveals the same elapsed-time guides on pace, cadence and elevation without changing
metric overlays. The existence of a guide depends on usable full-resolution distance.
For the three recent timelines, target about 200 display points and use a minimum five-second
interval. The complete received FIT data stays in the local archive and drives metrics and split
times. In the trace-heavy synthetic fixture, the uncompressed HTML went from about 1.24 MB to
1.93 MB with the denser charts.

Individual steady outdoor runs can also show early and late mechanics at comparable pace
and grade. The panel lists actual matched time and hides metrics with too little evidence.
Split guides use a thin dashed line and a keyboard-focusable native control. See the
[theme and viewport checks](docs/UI_REVIEW.md#current-light-and-dark-acceptance-work).

### Sleep follow-up

Sleep shows the most recent complete night, the saved bedtime target and its linked dates,
then the weekly, monthly and annual views. A saved target remains visible during a gap in
sleep recordings. Outcome rows appear when there are at least three measured nights in
both timing groups. The display reports observed differences for the recorded week.
