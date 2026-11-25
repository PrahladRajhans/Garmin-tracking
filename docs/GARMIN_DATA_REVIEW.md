# Garmin sources, coverage and product decisions

Reviewed 25 November 2026. This register covers the Forerunner 955 manual, Garmin Connect
support definitions and documented API/FIT surfaces relevant to this dashboard. Account-specific
fields still need a replay of the owner's archive. Garmin may show fields in Connect that a
particular device, firmware, export or API response does not expose.

## Where the best opportunities are

| Area | Available to the dashboard | Product choice and remaining evidence |
|---|---|---|
| Resting and daily pulse | Normalized daily estimate, daily summary source records, recent Personal API or Connect samples | Explain the estimated number and show separately the intraday median and range. Check dated sources rather than using the export's rolling value as the day's pulse. The daily curve cannot reproduce Garmin's watch calculation. First verify the reported 44 bpm against the archived daily payload and an awake measurement. |
| Sleep duration, score and Coach | Dated sleep duration, score, stage totals, some timestamps and dated Garmin sleep need | Compare like-for-like windows with explicit gaps. Show how much recorded sleep fell below its target, along with a separate trend and the score. Garmin documents Sleep Coach, naps and Sleep Alignment by device. Map any supported nap records to their local dates and check the data before counting them toward a sleep target. |
| Stress, Body Battery and movement | Daily summaries and some raw stress data. Official enterprise documentation advertises detailed health snapshots | Audit timestamped stress, steps and charge/drain on archive and live samples. Once coverage is established, align time-of-day context with heart rate without treating Body Battery and stress as independent signals. Both can depend on HRV. |
| Overnight HRV, breathing and Pulse Ox | HRV summary or export fallback, overnight respiration and Pulse Ox when recorded | Separate support and recording gaps from changes in the athlete. Test field agreement, then consider recurring multi-signal patterns and sensor quality before expanding model interpretation. |
| Training and running | FIT samples, activity summaries, load, readiness and recent environments, with coverage varying by field | FIT records, laps, workouts and device/developer fields are distinct. Existing reviews use matched pace and grade. Next opportunities are workout-step alignment, repeat-route comparisons and sensor-specific data availability, each verified against FIT messages before surfacing. |

Sources: [Forerunner 955 manual](https://www8.garmin.com/manuals/webhelp/GUID-9D99A9D4-467A-4F1A-A0EA-023184FEA3DD/EN-US/Forerunner_955_OM_shared_EN-US.pdf),
[Garmin Health API](https://developer.garmin.com/gc-developer-program/enterprise/health-api/),
[Garmin Activity API](https://developer.garmin.com/gc-developer-program/enterprise/activity-api/),
[FIT activity file specification](https://developer.garmin.com/fit/file-types/activity),
[Garmin Connect daily pulse chart](https://support.garmin.com/en-US/?faq=dLag82HPPk0l4T2tRELSgA),
[Garmin sleep tracking](https://support.garmin.com/en-IN/?faq=mBRMf4ks7XAQ03qtsbI8J6),
[Garmin nap tracking](https://support.garmin.com/en-US/?faq=2icqqZFq3YAX5K9VGU2CQ9),
[Garmin Body Battery](https://support.garmin.com/en-GB/?faq=VOFJAsiXut9K19k1qEn5W5).

## Why the resting-pulse check works this way

Garmin says the daily resting estimate is the lowest 30-minute average in a 24-hour period.
An overnight low and a manually checked awake pulse answer different questions. The AHA
describes awake measurement and when an unusual pulse warrants attention. A systematic review
assessed optical wrist-device agreement across settings, so the dashboard treats these recordings as
wearable estimates. The under-50 prompt and robust range in this project are review heuristics.
A single watch result cannot determine why a pulse is low. [Garmin resting heart rate](https://support.garmin.com/en-US/?faq=F8YKCB4CJd5PG0DR9ICV3A),
[AHA pulse guidance](https://www.heart.org/en/health-topics/high-blood-pressure/the-facts-about-high-blood-pressure/all-about-heart-rate-pulse/),
[Wrist optical HR systematic review](https://pubmed.ncbi.nlm.nih.gov/32552580/).

## Why we show sleep shortfall

Bevel makes the accumulated gap visible. This project reports the observed shortfall against
dated Garmin targets or a clearly marked 8-hour fallback. It avoids converting a shortfall into
a physiological repayment schedule. Sleep duration and regularity have separate evidence bases.
Controlled catch-up studies have different outcomes depending on the protocol and outcome.
[Bevel sleep needs](https://www.bevel.health/it/blog/the-basics-sleep-needed),
[AASM/SRS adult duration recommendation](https://pmc.ncbi.nlm.nih.gov/articles/PMC4434546/),
[NSF sleep regularity consensus](https://pubmed.ncbi.nlm.nih.gov/37684151/),
[Controlled weekend recovery study](https://pubmed.ncbi.nlm.nih.gov/30827911/),
[Chronic restriction recovery study](https://pubmed.ncbi.nlm.nih.gov/30892916/).

[Formulas and safeguards](../METRICS.md#day-readings-sleep-shortfall-and-archive-baselines) ·
[Data lineage and reviewer checks](REVIEW_START_HERE.md) · [Prior Garmin source research](../research_notes/Garmin%20connector%20feature%20research/FINDINGS.md).
