import pytest

from garmin_mcp import scores


def test_strain_calibration_points():
    assert scores.strain_from_trimp(0) == 0
    assert 8.5 <= scores.strain_from_trimp(68) <= 10.5     # easy ~30-min run
    assert 15.5 <= scores.strain_from_trimp(250) <= 17.5   # hard ~2 h
    assert scores.strain_from_trimp(5000) == 21            # capped
    vals = [scores.strain_from_trimp(t) for t in range(0, 900, 25)]
    assert vals == sorted(vals)                            # monotonic


def test_recovery_mapping_and_bands():
    assert scores.phi(0) == pytest.approx(0.5)
    assert round(100 * scores.phi(1)) == 84 and round(100 * scores.phi(-1)) == 16
    assert scores.band(70) == ("green", "recovered")
    assert scores.band(50) == ("yellow", "moderate")
    assert scores.band(20) == ("red", "low")
    assert scores.band(None) == (None, None)


def test_zero_correlation_is_not_treated_as_missing():
    base = {"hrv": {"r": 0.0}, "garmin": {"r": 0.0}}
    assert not scores._beats_on_both({"hrv": {"r": -0.1}, "garmin": {"r": -0.1}}, base)
    assert scores._beats_on_both({"hrv": {"r": 0.1}, "garmin": {"r": 0.1}}, base)
    assert not scores._beats_on_both({"hrv": {"r": None}, "garmin": {"r": 0.2}}, base)


def test_weight_study_keeps_hrv_only_days_and_matches_comparison_days(conn, monkeypatch):
    from datetime import date, timedelta

    from garmin_mcp import recovery
    from garmin_mcp.normalize import rebuild

    rebuild(conn)
    start = date(2026, 1, 1)
    names = ["HRV (7-day vs normal)", "Resting HR (today vs 60-day)",
             "Sleep (last night vs 28-day)", "Respiration (last night vs 60-day)"]
    for i in range(90):
        day = (start + timedelta(days=i)).isoformat()
        conn.execute("INSERT INTO hrv(day,last_night_avg) VALUES (?,?)", (day, 50 + i % 7))
        conn.execute("INSERT INTO readiness(day,score) VALUES (?,?)", (day, 60 + i % 11))

    def readiness(c, day):
        i = (date.fromisoformat(day) - start).days
        return {"ours": {"components": [{"name": n, "contribution": None if i % 5 == 0
                                           and j < 2 else float((i + j) % 7)}
                                          for j, n in enumerate(names)]}}

    monkeypatch.setattr(recovery, "readiness", readiness)
    report = scores.weight_study(conn, (start + timedelta(days=89)).isoformat(), 60)
    comp = report["composites"]
    assert comp["equal weights (current)"]["next_night_hrv"]["n"] >= 30
    for outcome in ("next_night_hrv", "garmin_readiness"):
        assert len({v[outcome]["n"] for v in comp.values()}) == 1
