import math
from datetime import UTC, date, datetime, timedelta

import pytest

from garmin_mcp import dashboard, db, engine, insights, loads, scores
from garmin_mcp.normalize import TABLES, rebuild


def test_banister_constants():
    # x = 0.5: male 0.64*e^(0.96), female 0.86*e^(0.835), per minute at x=0.5
    assert loads.banister_trimp(119.5, 1, 46, 193, "male") == pytest.approx(
        0.5 * 0.64 * math.exp(1.92 * 0.5), rel=1e-6)
    assert loads.banister_trimp(119.5, 1, 46, 193, "female") == pytest.approx(
        0.5 * 0.86 * math.exp(1.67 * 0.5), rel=1e-6)
    assert loads.banister_trimp(40, 1, 46, 193, "male") == 0.0  # below rest clipped


def test_vdot_matches_daniels_table():
    # Daniels' tables: 5K in 19:57 ~ VDOT 50; 10K 41:21 ~ VDOT 50 (Daniels' Running Formula).
    assert loads.vdot(5000, 19 * 60 + 57) == pytest.approx(50, abs=0.5)
    assert loads.vdot(10000, 41 * 60 + 21) == pytest.approx(50, abs=0.5)
    assert loads.time_for_vdot(5000, 50) == pytest.approx(19 * 60 + 57, abs=8)


def test_riegel_ewma_minetti_swain_pi():
    assert loads.riegel(1200, 5000, 10000) == pytest.approx(1200 * 2 ** 1.06)
    assert loads.ewma(0, 100, 42) == pytest.approx(100 * (1 - math.exp(-1 / 42)))
    assert loads.minetti_cost(0) == pytest.approx(3.6)
    assert loads.minetti_cost(0.1) > loads.minetti_cost(0) > loads.minetti_cost(-0.1) > 0
    # Swain 1994: 70% HRmax -> (70-37.182)/0.6463 = 50.8% VO2max
    assert loads.swain_pct_vo2max(0.70) == pytest.approx(0.5078, abs=1e-3)
    assert loads.polarization_index(80, 5, 15) == pytest.approx(math.log10(0.8 / 0.05 * 0.15 * 100))
    assert loads.polarization_index(50, 30, 20) is None  # not Z1 > Z3 > Z2


def test_critical_speed_fit():
    curve = [{"window_s": t, "distance_m": 3.5 * t + 200} for t in (180, 300, 600, 720, 1200)]
    cs = loads.critical_speed(curve)
    assert cs["cs_m_s"] == pytest.approx(3.5) and cs["d_prime_m"] == pytest.approx(200)
    assert cs["maximal"] is True
    flat = [{"window_s": t, "distance_m": 2.8 * t + 10} for t in (180, 300, 600, 1200)]
    assert loads.critical_speed(flat)["maximal"] is False


def _seed(conn):
    for t, cols in TABLES.items():
        conn.execute(f"DROP TABLE IF EXISTS {t}")
        conn.execute(f"CREATE TABLE {t} (day TEXT PRIMARY KEY, {', '.join(cols)}, sources TEXT)")
    d0 = date(2026, 10, 1)
    for i in range(50):
        conn.execute("INSERT INTO daily(day, resting_hr) VALUES (?, 46)",
                     ((d0 + timedelta(days=i)).isoformat(),))
    for i in range(0, 50, 2):
        day = (d0 + timedelta(days=i)).isoformat()
        aid = 1000 + i
        conn.execute("INSERT INTO activities(activity_id, type, start_time_local, duration_s, "
                     "distance_m, avg_hr, max_hr, garmin_training_load, updated_at) VALUES "
                     "(?, 'running', ?, 1800, 5000, 150, 180, 60, 'x')", (aid, f"{day} 07:00:00"))
        for s in range(0, 1800, 1):
            hr = 150 if s < 1500 else 170
            conn.execute("INSERT INTO fit_records(activity_id, ts, heart_rate, speed, distance, "
                         "altitude) VALUES (?, ?, ?, 2.78, ?, 10)",
                         (aid, f"{day}T07:{s // 60:02d}:{s % 60:02d}" if s < 3600 else day,
                          hr, 2.78 * s))
    conn.commit()


def test_rebuild_fitness_series(conn):
    _seed(conn)
    out = loads.rebuild(conn, "2026-11-19")
    assert out["thresholds"]["hr_max"] == 180 and out["thresholds"]["hr_rest"] == 46
    rows = conn.execute("SELECT day, load, ctl, atl, tsb FROM fitness ORDER BY day").fetchall()
    assert rows[0][1] > 0 and rows[1][1] == 0  # every other day
    last = rows[-1]
    assert last[3] > last[2] > 0  # ATL reacts faster than CTL during steady build
    # TSB is yesterday's CTL - ATL
    assert rows[-1][4] == pytest.approx(round(rows[-2][2] - rows[-2][3], 1), abs=0.11)
    z = conn.execute("SELECT z1_s, z2_s, z3_s FROM activity_load LIMIT 1").fetchone()
    assert sum(z) == pytest.approx(1799, abs=2)


def test_thresholds_skips_fit_zone_records_without_maximum_pulse(conn):
    configured = [188, None, 255, math.inf]
    for aid, configured_max in enumerate(configured, 1):
        day = f"2026-11-{aid + 19}"
        conn.execute("INSERT INTO activities(activity_id, type, start_time_local, max_hr, "
                     "updated_at) VALUES (?, 'running', ?, 179, 'x')", (aid, f"{day} 07:00:00"))
        conn.execute("INSERT INTO fit_zones(activity_id,max_hr) VALUES (?,?)", (aid, configured_max))

    thresholds = loads.thresholds(conn, "2026-11-23")
    assert thresholds["garmin"]["hr_max_setting"] == 188
    assert thresholds["hr_max"] == 179
    conn.execute("DELETE FROM fit_zones WHERE activity_id=1")
    assert loads.thresholds(conn, "2026-11-23")["garmin"]["hr_max_setting"] is None


def test_best_rolling_hr_requires_measured_time_and_weights_boundary():
    origin = datetime(2026, 11, 21, tzinfo=UTC)

    def points(samples):
        return [((origin + timedelta(seconds=seconds)).isoformat(), hr) for seconds, hr in samples]

    assert loads.best_rolling_hr(points([(0, 132), (1200, 192)]), 1200) is None
    assert loads.best_rolling_hr(points((s, 154) for s in range(0, 1201, 5)), 1200) == 154
    gaps = [(s, 154 if s < 500 or s > 700 else None) for s in range(0, 1201, 5)]
    assert loads.best_rolling_hr(points(gaps), 1200) is None
    short_gap = [(s, 154 if s < 500 or s > 550 else None) for s in range(0, 1201, 5)]
    assert loads.best_rolling_hr(points(short_gap), 1200) == 154
    edge = points([(0, 120), (7, 120), (14, 160)])
    assert loads.best_rolling_hr(edge, 10) == 148


def test_sparse_run_uses_garmin_threshold_and_missing_load_stays_missing(conn):
    day = "2026-11-21"
    db.put_daily(conn, "ex_daily_summary", day, "export",
                 {"calendarDate": day, "currentDayRestingHeartRate": 50})
    for aid, start, average in [(1, day, None), (2, day, 160), (3, "2026-11-13", 150)]:
        db.upsert_activity(conn, {"activityId": aid, "activityType": {"typeKey": "running"},
                                  "startTimeLocal": f"{start}T07:00:00", "duration": 1800,
                                  "averageHR": average, "maxHR": 188})
    conn.execute("INSERT INTO fit_zones(activity_id,threshold_hr) VALUES (1,159)")
    conn.executemany("INSERT INTO fit_records(activity_id,ts,heart_rate) VALUES (1,?,?)",
                     [(f"{day}T07:00:00", 132), (f"{day}T07:20:00", 192)])
    rebuild(conn)
    assert loads.thresholds(conn, day)["lthr"] == 159
    first, second = conn.execute("SELECT trimp,trimp_from FROM activity_load WHERE activity_id <= 2 "
                                 "ORDER BY activity_id").fetchall()
    assert tuple(first) == (None, None)
    assert second[0] > 0 and second[1] == "average hr"
    day_load, trend = conn.execute("SELECT load,ctl FROM fitness WHERE day=?", (day,)).fetchone()
    assert day_load is None and trend > 0
    assert dashboard._weekly_load(conn, day)[-1][1] is None
    assert scores.daily_scores(conn, day)["strain"]["value"] is None
    report = insights.weekly_review(conn, day)
    assert report["week"]["sessions_with_load"] == 1 and report["week"]["sessions"] == 2
    assert report["week"]["trimp"] is None and report["week"]["intensity_pct"] is None
    assert report["load_change_pct"] is None
    assert all(flag["flag"] != "load jump" for flag in engine.load_flags(conn, day))
    easy = loads.activity_load(conn, {"activity_id": 99, "type": "walking", "avg_hr": 44,
                                     "duration_s": 300}, loads.thresholds(conn, day), None)
    assert easy["trimp"] == 0 and easy["trimp_from"] == "average hr"


def test_graded_training_stress_uses_same_hill_at_one_and_five_seconds(conn):
    origin = datetime(2026, 11, 21, tzinfo=UTC)
    values = []
    for aid, interval in enumerate((1, 5), 1):
        db.upsert_activity(conn, {"activityId": aid, "activityType": {"typeKey": "running"}})
        conn.executemany("INSERT INTO fit_records(activity_id,ts,speed,distance,altitude) VALUES (?,?,1.8,?,?)",
                         [(aid, (origin + timedelta(seconds=s)).isoformat(), 1.8 * s, 100 + 0.09 * s)
                          for s in range(0, 601, interval)])
        values.append(loads.activity_load(conn, {"activity_id": aid, "type": "running", "duration_s": 600},
                                          {"hr_rest": None, "hr_max": None, "lthr": None, "sex": "male"}, 3))
    assert values[0] == values[1]
    flat = 600 / 3600 * (1.8 / 3) ** 2 * 100
    assert values[0]["rtss"] > flat
    assert values[0]["trimp"] is None
