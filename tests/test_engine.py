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
