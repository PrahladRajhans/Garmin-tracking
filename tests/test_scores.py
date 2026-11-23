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
