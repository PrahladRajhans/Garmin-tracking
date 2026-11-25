import random
from datetime import date, timedelta

from garmin_mcp import engine


def _feat(n=120, effect=0.5, seed=1):
    rng = random.Random(seed)
    d0 = date(2026, 1, 1)
    feat = {}
    for i in range(n):
        s = 7 + rng.gauss(0, 0.8)
        feat[(d0 + timedelta(days=i)).isoformat()] = {"sleep_h": s,
                                                      "hrv": 50 + effect * 4 * (s - 7)
                                                      + rng.gauss(0, 2)}
    return feat


def test_relationship_detects_real_effect_and_ignores_noise():
    strong = engine.relationship(_feat(effect=1.0), "sleep_h", "hrv", 0)
    assert strong["status"] == "ok" and strong["r"] > 0.5 and strong["r_ci95"][0] > 0
    # Calibration: with no true effect, the 95% CI should exclude 0 rarely (~5%).
    old_boot = engine.BOOT
    engine.BOOT = 200
    try:
        fp = sum(not (r["r_ci95"][0] < 0 < r["r_ci95"][1]) for r in (
            engine.relationship(_feat(effect=0.0, seed=s), "sleep_h", "hrv", 0)
            for s in range(100, 120)))
    finally:
        engine.BOOT = old_boot
    assert fp <= 2


def test_minimum_pairs_enforced():
    r = engine.relationship(_feat(n=35), "sleep_h", "hrv", 0)  # 10 days lost to baseline
    assert r["status"].startswith("insufficient")


def test_bh_and_theil_sen():
    res = [{"status": "ok", "p_boot": p} for p in (0.001, 0.02, 0.04, 0.5)]
    engine.bh_adjust(res)
    assert [r["q_bh"] for r in res] == [0.004, 0.04, 0.0533, 0.5]
    pts = [(x, 2 * x + 1) for x in range(10)] + [(10, 500)]  # outlier
    assert engine.theil_sen(pts) == 2


def test_constant_signal_is_unavailable_instead_of_crashing():
    feat = {(date(2026, 1, 1) + timedelta(days=i)).isoformat():
            {"a": 4.0, "b": float(i % 7)} for i in range(75)}
    result = engine.relationship(feat, "a", "b")
    assert result["n"] >= engine.MIN_PAIRS
    assert result["available"] is False and result["status"] == "insufficient variation"
    assert "constant" in result["reason"] and "r" not in result


def test_personal_ranges_do_not_present_stale_values_as_today(conn):
    from garmin_mcp.normalize import rebuild

    rebuild(conn)
    conn.execute("INSERT INTO health_status(day,hrv,hrv_low,hrv_high) "
                 "VALUES ('2026-01-01',50,40,60)")
    assert "hrv_ms" not in engine.personal_ranges(conn, "2026-11-23")["metrics"]
    conn.execute("INSERT INTO hrv(day,last_night_avg) VALUES ('2026-11-23',70)")
    metric = engine.personal_ranges(conn, "2026-11-23")["metrics"]["hrv_ms"]
    assert metric["value"] == 70 and metric["as_of"] == "2026-11-23"
    assert metric["range"] is None and metric["state"] == "calibrating"
    conn.execute("INSERT INTO health_status(day,hrv,hrv_low,hrv_high) "
                 "VALUES ('2026-11-23',70,40,NULL)")
    assert engine.personal_ranges(conn, "2026-11-23")["outside_range"] == 0
    detail = engine.insight_feed(conn, "2026-11-23")["insights"][0]["detail"]
    assert isinstance(detail, str) and "not enough recovery data" in detail


def test_training_end_uses_local_finish_date_without_leaking_past_query_end(conn, monkeypatch):
    from garmin_mcp import db
    from garmin_mcp.normalize import rebuild

    monkeypatch.setenv("GARMIN_TZ", "America/New_York")
    rebuild(conn)
    for aid, stamp, local, duration in [
        (1, "2026-03-07T23:30:00-05:00", "2026-03-07 23:30:00", 1800),
        (2, "2026-03-08T01:50:00-05:00", "2026-03-08 01:50:00", 1200),
        (3, "2026-03-08T23:50:00-04:00", "2026-03-08 23:50:00", 1200),
        (4, "2026-03-08T18:00:00-04:00", "2026-03-08 18:00:00", None),
    ]:
        db.upsert_activity(conn, {"activityId": aid, "startTimeGMT": stamp,
                                  "startTimeLocal": local, "duration": duration})
    day = engine.features(conn, "2026-03-08", "2026-03-08")
    assert list(day) == ["2026-03-08"]
    assert day["2026-03-08"]["last_training_end_h"] == 3 + 10 / 60
    midnight = engine.features(conn, "2026-03-09", "2026-03-09")
    assert midnight["2026-03-09"]["last_training_end_h"] == 10 / 60
