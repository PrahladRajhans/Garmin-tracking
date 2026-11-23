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
