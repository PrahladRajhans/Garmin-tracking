from datetime import UTC, datetime, timedelta

import pytest
from garmin_fit_sdk import Encoder, Profile

from garmin_mcp import db


@pytest.fixture(autouse=True)
def isolated_home(tmp_path_factory, monkeypatch):
    """Keep every test away from the owner's files. Dashboard builds mirror into the home
    folder's iCloud Drive even when the data folder is temporary."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    for name in ("GARMIN_DATA_DIR", "GARMIN_DB_PATH", "GARMIN_TZ", "GARMIN_TOKEN_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GARMIN_DATA_DIR", str(home / "data"))
    monkeypatch.setenv("GARMIN_TOKEN_DIR", str(home / ".garminconnect"))
    monkeypatch.delenv("GARMIN_DASHBOARD_PUBLISH", raising=False)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("GARMIN_DATA_DIR", str(tmp_path))
    c = db.connect(tmp_path / "test.db")
    yield c
    c.close()


def make_fit(n: int = 5, with_hrv: bool = True) -> bytes:
    mn = Profile["mesg_num"]
    t0 = datetime(2026, 11, 1, 7, 0, tzinfo=UTC)
    e = Encoder()
    e.write_mesg({"mesg_num": mn["FILE_ID"], "type": "activity", "manufacturer": "garmin",
                  "time_created": t0})
    for i in range(n):
        e.write_mesg({"mesg_num": mn["RECORD"], "timestamp": t0 + timedelta(seconds=i),
                      "heart_rate": 140 + i, "enhanced_speed": 3.2, "cadence": 86,
                      "power": 260, "distance": 3.2 * i, "enhanced_altitude": 50.0,
                      "position_lat": 612553216, "position_long": -1550000})
    if with_hrv:
        e.write_mesg({"mesg_num": mn["HRV"], "time": [0.42, 0.43, 0.44]})
    e.write_mesg({"mesg_num": mn["LAP"], "timestamp": t0 + timedelta(seconds=n),
                  "start_time": t0, "total_timer_time": float(n), "total_distance": 3.2 * n,
                  "avg_heart_rate": 142})
    e.write_mesg({"mesg_num": mn["SESSION"], "timestamp": t0 + timedelta(seconds=n),
                  "start_time": t0, "sport": "running", "sub_sport": "generic",
                  "total_timer_time": float(n)})
    return e.close()
