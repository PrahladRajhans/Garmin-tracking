from datetime import UTC, datetime, timedelta

import pytest
from test_run_evidence import seed

from garmin_mcp import coaching, conditions, dashboard, db, environment_review


def test_workout_conditions_match_source_and_coverage(conn):
    anchor = datetime(2026, 11, 23, 6, tzinfo=UTC)
    for i in range(5):
        start = anchor - timedelta(days=2 * (4 - i))
        seed(conn, i + 1, start, hr=140 + 2 * i)
        end = start + timedelta(minutes=25 if i != 1 else 16)
        db.put_activity_detail(conn, i + 1, conditions.DETAIL_KIND, [{
            "start_utc": start.isoformat(), "end_utc": end.isoformat(),
            "source": "Public station", "kind": "observation",
            "temperature_c": 20 + i, "aqi": 105,
            "aqi_standard": "US-EPA" if i == 2 else "IN-CPCB"}])
    result = coaching.run_analysis(conn, 5)["conditions_comparison"]
    assert len(result) == 1
    item = result[0]
    assert item["metric"] == "temperature_c"
    assert item["recorded"]["value"] == 24 and item["earlier_value"] == 22
    assert item["recorded"]["hr_bpm"] == 148 and item["earlier_hr_bpm"] == 144
    assert {r["activity_id"] for r in item["earlier_runs"]} == {1, 3, 4}
    assert "Conditions on similar runs" in dashboard._run_conditions_comparison(result)


def test_bedroom_review_uses_local_intervals_and_optional_morning_checkins(conn, tmp_path):
    from garmin_mcp.normalize import rebuild

    rebuild(conn)
    anchor = datetime(2026, 11, 1, 6, tzinfo=UTC)
    path = tmp_path / "room.csv"
    for i in range(12):
        end = anchor + timedelta(days=2 * i)
        day = end.date().isoformat()
        start = end - timedelta(hours=8)
        conn.execute("INSERT INTO sleep(day,sleep_s,sleep_start,sleep_end) VALUES (?,?,?,?)",
                     (day, (8 if i < 6 else 7)*3600, start.isoformat(), end.isoformat()))
        temperature = 19 if i < 6 else 24
        path.write_text("start_utc,end_utc,source,kind,temperature_c\n"
                        f"{start.isoformat()},{end.isoformat()},Bedroom logger,observation,"
                        f"{temperature}\n")
        assert conditions.import_bedroom(conn, day, path, energy=(4 if i < 6 else 3)) == 1
        if i == 0:
            assert not environment_review.bedroom(conn, day)["available"]
    review = environment_review.bedroom(conn, day)
    assert review["available"] and review["imported_nights"] == 12
    assert review["groups"][0]["lower"]["sleep_h"] == 8
    assert review["groups"][0]["higher"]["morning_energy"] == 3
    html = dashboard._bedroom_card(review)
    assert "Room conditions and sleep" in html and "Morning energy 3/5" in html
    assert "Bedroom logger" in html and "2026-11-01" in html
    with pytest.raises(ValueError, match="between 1 and 5"):
        conditions.import_bedroom(conn, day, path, energy=6)


def _paired_runs(conn):
    from garmin_mcp.normalize import rebuild

    rebuild(conn)
    first = datetime(2026, 10, 10, 4, tzinfo=UTC)
    for n in range(12):
        start = first + timedelta(days=2 * n)
        high = n % 2 == 1
        seed(conn, n + 1, start, hr=148 if high else 140)
        conn.execute("UPDATE fit_records SET lat=19.08, lon=72.88 WHERE activity_id=?", (n + 1,))
        db.put_activity_detail(conn, n + 1, conditions.DETAIL_KIND, [{
            "start_utc": start.isoformat(), "end_utc": (start + timedelta(hours=1)).isoformat(),
            "kind": "model", "source": "Open-Meteo test", "aqi_standard": "US-EPA",
            "temperature_c": 26, "aqi": 96 if high else 52}])
        bedtime = start + timedelta(hours=15)
        hours, hrv, rhr = (7, 49, 53) if high else (8, 54, 50)
        # The wake date is the following local day, though bedtime is on the activity date in UTC.
        wake = (start.date() + timedelta(days=1)).isoformat()
        conn.execute("INSERT INTO sleep(day,sleep_s,sleep_start,sleep_end) VALUES (?,?,?,?)",
                     (wake, 3600 * hours, bedtime.isoformat(),
                      (bedtime + timedelta(hours=hours)).isoformat()))
        conn.execute("INSERT INTO hrv(day,last_night_avg) VALUES (?,?)", (wake, hrv))
        conn.execute("INSERT INTO daily(day,resting_hr) VALUES (?,?)", (wake, rhr))
    conn.commit()
    return "2026-11-02"


def test_modelled_aqi_can_use_same_kind_and_standard_in_run_comparison(conn):
    _paired_runs(conn)
    evidence = coaching.run_analysis(conn, 12)["conditions_comparison"]
    aqi = next(row for row in evidence if row["metric"] == "aqi")
    assert aqi["recorded"]["kind"] == "model" and aqi["recorded"]["standard"] == "US-EPA"
    assert aqi["recorded"]["value"] == 96
    assert "Model estimate" in dashboard._run_conditions_comparison(evidence)


def test_outdoor_pairs_use_utc_order_and_separate_outcome_counts(conn):
    end = _paired_runs(conn)
    review = environment_review.outdoor_patterns(conn, end)
    assert review["sampled_runs"] == 12
    assert len(review["patterns"]) == 1  # temperature did not differ
    aqi = review["patterns"][0]
    assert aqi["metric"] == "aqi" and aqi["kind"] == "model" and aqi["standard"] == "US-EPA"
    assert {item["key"]: (item["median_delta"], item["pairs"]) for item in aqi["outcomes"]} == {
        "moving_hr": (8, 6), "sleep_h": (-1, 6), "hrv": (-5, 6), "rhr": (3, 6)}
    assert len({part["day"] for pair in aqi["pairs"] for part in pair.values()}) == 12
    assert all(part["wake_day"] > part["day"] for pair in aqi["pairs"] for part in pair.values())
    assert "72.88" not in str(review)
    card = dashboard._outdoor_patterns_card(review)
    assert "See the pairs" in card and "AQI (US EPA)" in card and "Following nightly HRV" in card

    # A mismatched record that starts before the run ends contributes no later-health value.
    conn.execute("UPDATE sleep SET sleep_start='2026-11-01T03:00:00+00:00' WHERE day=?", (end,))
    review = environment_review.outdoor_patterns(conn, end)
    assert [o["key"] for o in review["patterns"][0]["outcomes"]] == ["moving_hr"]


@pytest.mark.parametrize("change", ["second workout", "different location", "different AQI scale"])
def test_outdoor_pairs_do_not_fill_evidence_gaps(conn, change):
    end = _paired_runs(conn)
    if change == "second workout":
        seed(conn, 13, datetime(2026, 11, 1, 11, tzinfo=UTC), kind="walking", fit=False)
    elif change == "different location":
        conn.execute("UPDATE fit_records SET lat=29.05 WHERE activity_id=12")
    else:
        windows = conditions.for_activity(conn, 12)["windows"]
        windows[0]["aqi_standard"] = "IN-CPCB"
        db.put_activity_detail(conn, 12, conditions.DETAIL_KIND, windows)
    assert environment_review.outdoor_patterns(conn, end)["patterns"] == []
