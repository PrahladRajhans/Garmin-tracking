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


def test_failed_install_stops_reexecution_and_retries_without_new_commit(tmp_path, monkeypatch):
    import subprocess

    from garmin_mcp import config

    repo = tmp_path / "checkout"
    repo.mkdir()
    monkeypatch.setattr(autoupdate, "repo_dir", lambda: repo)
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.delenv("GARMIN_AUTO_UPDATED", raising=False)
    monkeypatch.delenv("GARMIN_AUTO_UPDATE", raising=False)
    heads = iter(["old", "new", "new", "new"])

    def git(repo, *args):
        if args == ("rev-parse", "HEAD"):
            return next(heads)
        if args == ("rev-parse", "origin/main"):
            return "new"
        return "main" if "--abbrev-ref" in args else ""

    monkeypatch.setattr(autoupdate, "_git", git)
    calls = []

    def install(argv, **kwargs):
        calls.append(argv)
        assert kwargs["check"] is True
        if len(calls) == 1:
            raise subprocess.CalledProcessError(1, argv)
        return subprocess.CompletedProcess(argv, 0)

    executions = []
    monkeypatch.setattr(autoupdate.subprocess, "run", install)
    monkeypatch.setattr(autoupdate.os, "execv", lambda *a: executions.append(a))
    failed = autoupdate.update()
    assert failed["requires_repair"] is True and executions == []
    assert list(tmp_path.glob("pending-install-*.json"))
    def offline(*args):
        raise subprocess.CalledProcessError(1, ["git", "fetch"])

    monkeypatch.setattr(autoupdate, "_git", offline)
    assert autoupdate.update()["requires_repair"] is True
    assert len(calls) == 1 and executions == []
    monkeypatch.setattr(autoupdate, "_git", git)
    retried = autoupdate.update()
    assert retried["updated"] and len(calls) == 2 and len(executions) == 1
    assert not list(tmp_path.glob("pending-install-*.json"))


def test_sync_cli_stops_after_failed_update_install(monkeypatch):
    import sys

    import pytest

    from garmin_mcp import sync

    monkeypatch.setattr(sys, "argv", ["garmin-mcp-sync"])
    monkeypatch.setattr(autoupdate, "update", lambda: {"requires_repair": True})
    monkeypatch.setattr(sync, "gate", lambda: pytest.fail("sync proceeded after failed install"))
    with pytest.raises(SystemExit) as exc:
        sync.main()
    assert exc.value.code == 1
