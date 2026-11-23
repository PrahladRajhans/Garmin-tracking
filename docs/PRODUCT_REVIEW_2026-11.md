# Product review: what is wrong and what to build next (for ChatGPT)

**Status: the owner is very unhappy with v0.17.0.** Treat this document as the brief for the next stage of work. It overrides earlier "describe, don't prescribe" choices wherever the two conflict.

Reviewed: `main` at v0.17.0. Dashboard rebuilt from the owner's real data (to 23 Nov), checked at phone width (390 px). Tests: 130 pass.

---

## 1. The verdict in one paragraph

The engineering got better and the product got worse. The dashboard is now an **archive of charts**, not a **coach**:
- **432 pages and 3.8 MB** in one file.
- Every page states numbers and draws plots, then leaves the conclusion to the reader.
- There is no weekly plan and no clear next step.
- The one finding that matters most for this person is never stated as a headline: **sleep is short and late, and training volume is too low to build fitness.**

The owner asked for Whoop / Garmin / Strava-level intelligence with transparent maths. What shipped is a careful statistics notebook. Caution is not the same thing as honesty. Honest coaching gives a sensible default and says how sure it is.

## 2. What the owner sees, screen by screen (evidence)

| Screen | What it shows | What's wrong |
|---|---|---|
| **Today** | Plan "Easy aerobic only", three dials, "What stands out", one measurement row, a 14-day bar chart | Recovery is shown as **"23 %, Low" in red while the small print says "uses 2 of 4 signals"**; Garmin says 54. "What stands out" says *"Training load trend is trending up, +0.48 load units per 30 days"*, which means nothing to a person. No weekly plan. No "why" behind the plan. |
| **Recovery** | Four cards (HRV, resting HR, Pulse Ox, breathing), each "Within your usual range" plus a chart | Four cards say the same thing and none says what it adds up to. Generic filler: *"Use sleep, resting pulse and how you feel alongside HRV"*, *"Compare nights with similar sleep conditions"*. Clinical links (FDA sensor guidance, the adult 60–100 bpm reference) are clutter for a fit 29-year-old. **Missing:** one sentence like "Your body is handling your load fine; sleep is what's holding recovery back." |
| **Training** | Week summary, a readiness-benchmark card, a load-trend line, weekly load bars | **"Do readiness scores line up with your runs? 0 of 20 paired days"** is an empty card on real data. "Smoothed training load", 2–10 with no unit, is unreadable. Garmin says **Detraining / Recovery**, but nothing says "you're losing fitness; here's the minimum to stop that". |
| **Running → run page** | Similar-runs card, "What to work on", form gauges, numbers, links to 3 sub-pages | "Heart rate on similar runs: 1 matched, 3 needed" is an empty card. "What to work on" says only *"Compare another steady run and check heat, hills, fuelling and sensor fit"*: homework, not coaching. **The knee-aware cadence guidance the owner asked for was deleted.** Three sub-pages per run fragment one story. |
| **Patterns** | 8 scatter plots, **4,400 px tall**; 4 say "No clear pattern" | Half the page is nothing. Raw axes ("Bedtime (h)" from −20 to +10, "TRIMP") need a statistics background to read. There are no takeaways: for example, "Sleep 1 h more → Garmin readiness +5.7: this is your biggest lever." |
| **Body** | Fitness age with levers, fitness-age trend, month report, VO₂max bar | Broken rows: **"Resting heart rate 46.0 → – bpm, fitness age – if reached"**, "Bmi". The most actionable fact in the product is buried: **vigorous minutes 1.1 → 75 a week moves fitness age**. That should drive the weekly plan. The VO₂max bar is a thin unlabelled line. |
| **Whole app** | 8 tabs in two rows, 432 pages, JavaScript-driven charts | Feels like a reporting tool, not a product. Too deep, too long, too many words. The charts need JavaScript, which iPhone's Files preview may not run (not tested on a device). |

## 3. Root causes (fix these, not just the symptoms)

1. **No insight layer.** Every page goes straight from data to chart. A real product has a layer in between that turns measurements into **conclusions → reasons → actions**. Nothing in the code does this; `engine.insight_feed` is a list of facts, not judgements.
2. **Over-applied caution.** "Don't prescribe" became "don't help". The rule should be: *recommend sensible defaults from established guidelines, say how sure you are, then personalise as data arrives.*
3. **No information hierarchy.** Everything has equal weight: every metric gets a card, every card gets a chart. A finished product shows 3 things big, 10 things small and the rest on request.
4. **Showing empty states.** Cards appear before they have enough data, which trains the user to skim past every card.
5. **Building for AI reviewers, not for the person.** Process documents (`CONTINUATION_REVIEW.md`, `PROGRESS_AUDIT.md`, `UI_REVIEW.md`), five version bumps in a day, and 324 "browser states" tested. None of that is what the owner experiences.

## 4. What to build (specification)

### 4.1 An insight and recommendation engine (new module `coach.py`)
Each day it produces a small, ranked set of **insights**. Each insight has a fixed shape:

```
headline     one plain sentence a person understands in 3 seconds
why          1–2 sentences with the actual numbers ("5.7 h a night vs 8 h target; bedtime 02:30")
action       one concrete next step ("Lights out by 01:00 this week, 30 min earlier than now")
confidence   High / Medium / Low, with the reason ("232 nights of your data" / "general guideline")
source       the rule or study it rests on (linked to METRICS.md)
category     sleep | recovery | training | running | body
```

Rules for v1, all transparent, all documented in `METRICS.md`:

- **Sleep limiter.** Average sleep < 7 h, or bedtime later than 01:00 → top insight, with a bedtime target 30 min earlier each week. Use `scores.bedtime_suggestion` and the user's own sleep → readiness relationship (r = 0.50, 232 days) as evidence.
- **Detraining.** Garmin status Detraining, or fewer than 2 sessions a week for 3 weeks → "You're losing fitness. Minimum to stop it: 3 × 30 min easy a week." The dose should come from established guidance (e.g. WHO 150 min moderate a week) and be stated as such.
- **Vigorous minutes lever** (from `coaching.fitness_age` levers) → "Add 2 × 20 min of hard effort a week to lower your fitness age from 24.9 toward 24.3."
- **Recovery state.** Recovery % (only with ≥ 3 signals) plus Garmin readiness → today's intensity call, with the reason.
- **Running form, knee-aware.**
  - If cadence < 170 spm: "Try about +3–5 % cadence on one easy run (e.g. 172 spm); shorter, quicker steps reduce knee load (Heiderscheit 2011; Willy 2016)." Frame it as an experiment, then compare the next run.
  - If HR drift > 5 %: "Aerobic base is the limiter: more easy minutes, not faster runs."
- **Patterns as takeaways.** For each notable relationship, one sentence plus the lever: "Your biggest lever: 1 h more sleep ≈ +6 Garmin readiness."
- **Closed loop.** When the owner follows an experiment (e.g. a cadence target), the next matching run says what changed.

### 4.2 A weekly plan
A card on Today showing **this week's sessions**, built from a conservative rule table (load, recovery state, Garmin status, knee note, no goal race):

- **Example:** "Mon easy 30 min · Wed easy 30 min + 4 × 20 s strides · Fri strength 25 min (hips, calves, single-leg) · Sun easy 40 min".
- **Show the rule:** e.g. "Base-building: detraining + low volume. +10 % volume a week maximum."
- **Optional:** push it to the watch with the existing `workouts.create(upload=True)`.

### 4.3 A redesign that looks like a finished product
- **Five tabs at most**, in one row: **Today · Sleep · Training · Running · Trends**. Fold Recovery into Today and Sleep. Fold Body and Patterns into Trends. Move History to Trends behind "See all".
- **The same anatomy on every page:**
  1. A one-sentence verdict at the top.
  2. 2–3 big numbers.
  3. Insight cards (headline / why / action).
  4. **One** supporting chart.
  5. "Details" collapsed.
- **Cut charts by about 70 %.** No chart without a takeaway written above it. No scatter plots on the main path (they move to a "See the evidence" drill-down).
- **Hide any card that doesn't have enough data.** Instead, one line at the bottom: "Collecting data: similar-run comparison (1/3 runs)".
- **Cut the file size.** Day pages only for the last 30 days; older history goes to monthly summaries, and Claude answers deep questions. The target is under 60 pages and under 600 KB.
- **Visual polish:**
  - Fix the broken rows ("– bpm", "Bmi").
  - Give the VO₂max bar labels and a proper height.
  - Use real units everywhere ("load points", never "load units"; no "TRIMP" on the surface).
  - Bigger scatter dots on phone.
  - Recovery dial grey with "Calibrating" when fewer than 3 signals.
- **Words:** each card at most 25 words before "Details". Remove generic filler sentences and clinical reference links from the main path.
- **Inspiration (not a copy):**
  - Whoop: three dials, one verdict and a coach line.
  - Oura: contributor rows in plain words.
  - Garmin: the morning report.
  - Apple Fitness: rings, big numbers, white space.

### 4.4 Make it reliable where the owner lives
1. The owner's Mac stopped auto-updating at PR #10. Add a visible footer line, "Last sync 6 h ago ✓ · Version 0.17.0 ✓", and a warning banner when either is stale.
2. Finish the private hosting (`publish.py`, steps in `MAC_SETUP.md`) and verify it on the owner's iPhone. The phone is the main screen.

### 4.5 What to subtract
- Hide the readiness benchmark card, the similar-runs card and "No clear pattern" charts from the main path.
- Park weather and air quality (`conditions.py`) until 4.1–4.3 ship.
- Merge `docs/CONTINUATION_REVIEW.md`, `PROGRESS_AUDIT.md` and `UI_REVIEW.md` into `HANDOVER.md` and `ROADMAP.md`, then delete them.
- One version bump per shipped feature, not per pull request.
- Split `dashboard.py` (1,714 lines) into a `dashboard/` package with one file per page.

## 5. Acceptance criteria (the owner's test)

The work is done when, on the owner's iPhone, with real data:

1. **In 5 seconds** on Today, the owner can say how recovered they are, what to do today and what the plan is this week.
2. **Every page** starts with a plain-English verdict and has at least one concrete next step.
3. **No card** is empty, and no visible text has jargon (CTL, TRIMP, "load units", r/CI) outside "Details".
4. **The top 3 insights** for this owner today are, in some form: *short, late sleep is your main limiter*; *you're detraining, here's the minimum weekly dose*; and *knee-aware cadence experiment on your next easy run*.
5. **The file** is under 600 KB and opens instantly on the phone, through the private link.
6. **Every recommendation** shows its confidence and source with one tap, so transparency is kept and the coaching comes back.

## 6. Order of work
1. 4.4 (reliability on the Mac and phone): nothing else matters until the owner sees updates.
2. 4.1 the insight engine, with tests that pin the owner's top 3 insights on a fixture copy of their data.
3. 4.2 the weekly plan.
4. 4.3 the redesign, built page by page around the insight cards.
5. 4.5 the cleanup.

Show the owner screenshots after steps 2 and 4 before going further.
