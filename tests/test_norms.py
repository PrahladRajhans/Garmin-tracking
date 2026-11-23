import csv
from pathlib import Path

from garmin_mcp import dashboard, norms
from garmin_mcp.normalize import rebuild


def test_every_reference_value_matches_primary_table_transcription():
    path = Path(__file__).resolve().parents[1] / "research_notes/Garmin connector feature research/friend_2015_table3.csv"
    count = 0
    with path.open() as f:
        for row in csv.DictReader(f):
            if row["cohort"] != "FRIEND":
                continue
            ref = norms.reference(int(row["age_group"][:2]), row["sex"])
            assert tuple(ref["values"].values()) == tuple(float(row[f"p{p}"]) for p in norms.PERCENTILES)
            count += 7
    assert count == 84
    assert norms.reference(29, "male")["values"][50] == 48.0
    assert norms.reference(29, "female")["values"][50] == 37.6


def test_age_boundaries_and_missing_profiles_are_not_extrapolated():
    assert norms.reference(29.99, "male")["age_group"] == "20–29"
    assert norms.reference(30, "male")["age_group"] == "30–39"
    assert norms.reference(79, "female")["available"]
    for age, sex in ((19, "male"), (80, "female"), (None, "male"), (29, None)):
        assert norms.reference(age, sex)["available"] is False


def test_comparison_on_missing_data_remains_explicit(conn):
    rebuild(conn)
    r = norms.comparison(conn, "2026-11-23")
    assert r["available"] is False and r["garmin"] is None and r["effective"] is None
    assert "no age or sex is assumed" in r["reason"]


def test_reference_bar_keeps_estimates_separate_and_caveated():
    r = {**norms.reference(29, "male"), "garmin": 51.4, "effective": 40.0,
         "garmin_as_of": "2026-11-23", "effective_runs": 5, "hr_max_user_override": False,
         "caveat": "Not a laboratory measurement."}
    text = dashboard.vo2_reference(r)
    assert 'viewBox="0 0 340 84"' in text and 'viewBox="0 0 720 84"' in text
    assert text.count('class="chart-interaction chart-compact"') == 2
    assert 'class="vo2-garmin"' in text and 'class="vo2-effective"' in text
    assert "untested max HR" in text and norms.SOURCE in text
    assert "51.4" in text and "40.0" in text and "<script" not in text
