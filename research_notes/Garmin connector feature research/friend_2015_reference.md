# FRIEND 2015 treadmill VO₂max reference

Kaminsky LA, Arena R, Myers J. Reference Standards for Cardiorespiratory Fitness Measured With
Cardiopulmonary Exercise Testing: Data From the Fitness Registry and the Importance of Exercise
National Database. *Mayo Clinic Proceedings*. 2015;90(11):1515–1523.
DOI: [10.1016/j.mayocp.2015.07.026](https://doi.org/10.1016/j.mayocp.2015.07.026).
PMID: 26455884. PMCID: PMC4919021.

Primary [Table 3](https://pmc.ncbi.nlm.nih.gov/articles/PMC4919021/#T3), retrieved 23 November 2026.
It contains measured FRIEND and predicted Cooper Clinic rows. Only the **FRIEND measured rows**
are implemented. The full 24 numeric rows, including unused Cooper comparison rows, were
extracted directly to `friend_2015_table3.csv`. No values were reconstructed from memory.

## Exact FRIEND rows used (mL O₂/kg/min)

| Sex | Age | 5th | 10th | 25th | 50th | 75th | 90th | 95th |
|---|---|---|---|---|---|---|---|---|
| male | 20–29 | 29.0 | 32.1 | 40.1 | 48.0 | 55.2 | 61.8 | 66.3 |
| male | 30–39 | 27.2 | 30.2 | 35.9 | 42.4 | 49.2 | 56.5 | 59.8 |
| male | 40–49 | 24.2 | 26.8 | 31.9 | 37.8 | 45.0 | 52.1 | 55.6 |
| male | 50–59 | 20.9 | 22.8 | 27.1 | 32.6 | 39.7 | 45.6 | 50.7 |
| male | 60–69 | 17.4 | 19.8 | 23.7 | 28.2 | 34.5 | 40.3 | 43.0 |
| male | 70–79 | 16.3 | 17.1 | 20.4 | 24.4 | 30.4 | 36.6 | 39.7 |
| female | 20–29 | 21.7 | 23.9 | 30.5 | 37.6 | 44.7 | 51.3 | 56.0 |
| female | 30–39 | 19.0 | 20.9 | 25.3 | 30.2 | 36.1 | 41.4 | 45.8 |
| female | 40–49 | 17.0 | 18.8 | 22.1 | 26.7 | 32.4 | 38.4 | 41.7 |
| female | 50–59 | 16.0 | 17.3 | 19.9 | 23.4 | 27.6 | 32.0 | 35.9 |
| female | 60–69 | 13.4 | 14.6 | 17.2 | 20.0 | 23.8 | 27.0 | 29.4 |
| female | 70–79 | 13.1 | 13.6 | 15.6 | 18.3 | 20.8 | 23.1 | 24.1 |

## Interpretation and implementation

The study describes 7,783 maximal treadmill CPX tests from US men/women aged 20–79 without
cardiovascular disease. These are reference percentiles for that cohort, not health cutoffs,
prescribed targets, an Indian population norm, or a lab validation of a wrist estimate.
The source's binary sex groups are retained; no age/sex is assumed when profile data are absent.

`norms.reference` chooses the published decade (20≤age<30, etc.) without interpolation.
Ages outside 20–79 are unavailable. It returns the exact seven reference points and source.
`norms.comparison` reads recorded age/sex, last Garmin running VO₂max with its date, and the
existing 180-day effective estimate/HRmax policy. The Body page draws separate Garmin and
effective markers, with a table/source and an explicit untested-HRmax caveat when no override
exists. The effective pace/HR construct is not physiologically equivalent to measured VO₂max.

No exact personal percentile is interpolated or claimed. Values outside the 5th–95th display
range expand the axis rather than disappearing. Missing profile or estimates stay explicit.
`tests/test_norms.py` compares all 84 implemented values with the source transcription and
checks age boundaries, unknown profiles and missing estimates.

This is a verified 2015 reference, not a claim that no newer FRIEND reference exists. Revising
the cohort requires a new retrieved primary table and a documented comparison.

Retrieved HTML SHA-256 (transient verification copy, not distributed article text):
`12f1236bf90fbb2fc16e50634c2a24dcb764419f8255ce1018cb6fa3cae93eae`.
