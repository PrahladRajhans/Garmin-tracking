import json

from garmin_mcp import conditions, db, weather_fetch


def _run(conn, aid=7, start="2026-11-20 01:30:00", lat=30.6789, lon=76.7321):
    conn.execute("INSERT INTO activities(activity_id, type, start_time_local, start_time_gmt, "
                 "fit_parsed, updated_at) VALUES (?,?,?,?,1,'x')",
                 (aid, "running", start, start))
    from datetime import datetime, timedelta

    t0 = datetime.fromisoformat("2026-11-20T01:30:00+00:00")
    for i in range(0, 3600, 60):  # a one-hour run, 01:30-02:29 UTC
        ts = (t0 + timedelta(seconds=i)).isoformat()
        conn.execute("INSERT INTO fit_records(activity_id, ts, lat, lon) VALUES (?,?,?,?)",
                     (aid, ts, lat, lon))
    conn.commit()


def fake_get(calls):
    def get(url, params):
        calls.append((url, params))
        if "air-quality" in url:
            return {"hourly": {"time": ["2026-11-20T01:00", "2026-11-20T02:00"],
                               "us_aqi": [151.4, None]}}
        return {"hourly": {"time": ["2026-11-20T00:00", "2026-11-20T01:00", "2026-11-20T02:00"],
                           "temperature_2m": [14.0, 15.5, 16.0],
                           "relative_humidity_2m": [80, 70, 999],
                           "wind_speed_10m": [1.0, 2.0, 3.0],
                           "precipitation": [0, 0, 0]}}
    return get


def test_off_by_default_and_sends_nothing(conn):
    _run(conn)
    calls = []
    out = weather_fetch.fill_recent(conn, today=__import__("datetime").date(2026, 11, 21),
                                    get=fake_get(calls))
    assert "off" in out["skipped"] and calls == []


def test_fetch_rounds_location_and_stores_overlapping_hours(conn):
    from datetime import date

    _run(conn)
    weather_fetch.set_enabled(conn, True)
    calls = []
    out = weather_fetch.fill_recent(conn, today=date(2026, 11, 21), get=fake_get(calls))
    assert out["runs_filled"] == 1
    for _, params in calls:
        assert params["latitude"] == 30.68 and params["longitude"] == 76.73  # ~1 km only
        assert set(params) <= {"latitude", "longitude", "start_date", "end_date", "timezone",
                               "hourly", "wind_speed_unit"}
    windows = conditions.for_activity(conn, 7)["windows"]
    assert [w["start_utc"][:13] for w in windows] == ["2026-11-20T01", "2026-11-20T02"]
    first, second = windows
    assert first["aqi"] == 151 and first["aqi_standard"] == "US-EPA"
    assert first["kind"] == "model" and first["temperature_c"] == 15.5
    assert "humidity_pct" not in second  # out-of-range value dropped, not stored
    # a second sync doesn't refetch a run that already has windows
    calls.clear()
    assert weather_fetch.fill_recent(conn, today=date(2026, 11, 21),
                                     get=fake_get(calls))["runs_checked"] == 0


def test_rate_limit_never_breaks_sync(conn):
    from datetime import date

    _run(conn)
    weather_fetch.set_enabled(conn, True)

    def limited(url, params):
        raise OSError("HTTP Error 429")

    out = weather_fetch.fill_recent(conn, today=date(2026, 11, 21), get=limited)
    assert out["runs_filled"] == 0 and out["errors"]


def test_clear_removes_only_fetched_windows(conn):
    db.put_activity_detail(conn, 1, conditions.DETAIL_KIND,
                           [{"source": weather_fetch.SOURCE, "kind": "model"}])
    db.put_activity_detail(conn, 2, conditions.DETAIL_KIND,
                           [{"source": "my station", "kind": "observation"}])
    assert weather_fetch.clear(conn) == 1
    kept = conn.execute("SELECT activity_id, payload FROM activity_details").fetchall()
    assert [k[0] for k in kept] == [2] and json.loads(kept[0][1])[0]["source"] == "my station"
