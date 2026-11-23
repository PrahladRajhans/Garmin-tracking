import json

from garmin_mcp import athlete, autoupdate


def test_seed_from_file_only_fills_missing(conn, tmp_path):
    f = tmp_path / "athlete.json"
    f.write_text(json.dumps({"timezone": "Asia/Kolkata", "goals": "fitness",
                             "not_a_key": 1}))
    athlete.set_value(conn, "goals", "user changed this")
    applied = athlete.seed_from_file(conn, str(f))
    assert applied == ["timezone"]
    assert athlete.get(conn, "goals") == "user changed this"
    assert athlete.get(conn, "timezone") == "Asia/Kolkata"


def test_autoupdate_can_be_disabled(monkeypatch):
    monkeypatch.setenv("GARMIN_AUTO_UPDATE", "0")
    assert "disabled" in autoupdate.update(reexec=False)["skipped"]
