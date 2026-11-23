import copy
import subprocess
from pathlib import Path
from urllib.error import HTTPError

import pytest

from garmin_mcp import publish

HOST = "garmin-private.pages.dev"
EMAIL = "owner@example.com"
IDS = ["00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"]


class FakeAPI:
    def __init__(self):
        self.project = {"subdomain": HOST, "production_branch": "main", "domains": []}
        self.apps = [{"id": aid, "type": "self_hosted", "domain": domain}
                     for aid, domain in zip(IDS, (HOST, "*." + HOST))]
        self.policies = [{"decision": "allow", "include": [{"email": {"email": EMAIL}}]}]

    def get(self, path):
        if path.startswith("/pages/projects/"):
            return {"result": self.project}
        return {"result": next(a for a in self.apps if a["id"] == path.split("/")[-1])}

    def items(self, path):
        return self.policies if path.endswith("/policies") else self.apps


def test_requires_both_production_and_preview_access():
    api = FakeAPI()
    assert publish.check_access(api, "garmin-private", EMAIL) == (HOST, "main")
    api.apps.pop()
    with pytest.raises(publish.PublishError, match="Both production"):
        publish.check_access(api, "garmin-private", EMAIL)


@pytest.mark.parametrize("change", [
    {"decision": "bypass"}, {"decision": "non_identity"},
    {"include": [{"everyone": {}}]}, {"include": [{"email_domain": {"domain": "example.com"}}]},
    {"include": [{"email": {"email": "other@example.com"}}]},
    {"include": [{"email": {"email": EMAIL}}, {"everyone": {}}]},
])
def test_refuses_policies_that_allow_other_people(change):
    api = FakeAPI()
    api.policies[0].update(change)
    with pytest.raises(publish.PublishError, match="exact email"):
        publish.check_access(api, "garmin-private", EMAIL)


@pytest.mark.parametrize("change", [
    {"domain": HOST + "/public"}, {"options_preflight_bypass": True},
    {"type": "biso"},
    {"destinations": [{"type": "public", "uri": HOST,
                       "overrides": [{"path": "/index.html"}]}]},
])
def test_refuses_paths_and_bypasses(change):
    api = FakeAPI()
    api.apps[0].update(change)
    with pytest.raises(publish.PublishError):
        publish.check_access(api, "garmin-private", EMAIL)


def test_checks_destinations_and_refuses_overlapping_app():
    api = FakeAPI()
    api.apps[0]["destinations"] = [{"type": "public", "uri": HOST}]
    assert publish.check_access(api, "garmin-private", EMAIL)[0] == HOST
    app = copy.deepcopy(api.apps[1])
    app["domain"] = "main." + HOST
    api.apps.append(app)
    with pytest.raises(publish.PublishError):
        publish.check_access(api, "garmin-private", EMAIL)


def test_refuses_custom_domain_and_extra_policy():
    api = FakeAPI()
    api.project["domains"] = ["health.example.com"]
    with pytest.raises(publish.PublishError, match="Custom domains"):
        publish.check_access(api, "garmin-private", EMAIL)
    api.project["domains"] = []
    api.policies.append({"decision": "bypass", "include": [{"everyone": {}}]})
    with pytest.raises(publish.PublishError):
        publish.check_access(api, "garmin-private", EMAIL)


def test_disabled_publish_performs_no_network_or_subprocess(monkeypatch, tmp_path):
    monkeypatch.delenv("GARMIN_DASHBOARD_PUBLISH", raising=False)
    monkeypatch.setattr("dotenv.dotenv_values", lambda path: {})
    monkeypatch.setattr(publish, "Cloudflare", lambda *a: pytest.fail("network attempted"))
    monkeypatch.setattr(publish.subprocess, "run", lambda *a, **kw: pytest.fail("upload attempted"))
    assert publish.publish_if_enabled(tmp_path / "missing.html") == {"status": "disabled"}


@pytest.fixture
def configured(monkeypatch, tmp_path):
    wrangler = tmp_path / "wrangler"
    wrangler.touch()
    for name, value in {"GARMIN_DASHBOARD_PUBLISH": "cloudflare",
                        "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                        "CLOUDFLARE_API_TOKEN": "private-test-token",
                        "GARMIN_CLOUDFLARE_PROJECT": "garmin-private",
                        "GARMIN_DASHBOARD_EMAIL": EMAIL, "GARMIN_WRANGLER": str(wrangler)}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr("dotenv.dotenv_values", lambda path: {})
    api = FakeAPI()
    monkeypatch.setattr(publish, "Cloudflare", lambda *args: api)
    logins = []
    monkeypatch.setattr(publish, "_check_login", logins.append)
    path = tmp_path / "index.html"
    path.write_text("synthetic dashboard")
    (tmp_path / "garmin.db").write_text("must stay local")
    return api, path, logins


def test_upload_stages_only_dashboard_and_privacy_headers(configured, monkeypatch):
    _api, path, logins = configured
    calls = []

    def run(argv, **kwargs):
        assert "private-test-token" not in argv
        assert kwargs["env"]["CLOUDFLARE_API_TOKEN"] == "private-test-token"
        assert kwargs["env"]["CI"] == "true" and kwargs["timeout"] == 180
        assets = Path(argv[3])
        assert sorted(p.name for p in assets.iterdir()) == ["_headers", "index.html"]
        assert (assets / "index.html").read_text() == path.read_text()
        assert "private, no-store" in (assets / "_headers").read_text()
        assert Path(kwargs["cwd"]) == assets.parent
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(publish.subprocess, "run", run)
    result = publish.publish_if_enabled(path)
    assert result == {"status": "published", "url": "https://" + HOST}
    assert len(calls) == 1 and logins == [HOST, "privacy-check." + HOST]
    assert path.read_text() == "synthetic dashboard"


def test_unsafe_setup_never_uploads(configured, monkeypatch):
    api, path, _ = configured
    api.apps.pop()
    monkeypatch.setattr(publish.subprocess, "run", lambda *a, **kw: pytest.fail("upload attempted"))
    assert publish.publish_if_enabled(path)["status"] == "error"
    assert path.exists()


def test_check_only_never_uploads(configured, monkeypatch):
    monkeypatch.setattr(publish.subprocess, "run", lambda *a, **kw: pytest.fail("upload attempted"))
    assert publish.publish_if_enabled(None, check_only=True)["status"] == "checked"


def test_upload_failure_does_not_leak_output_or_remove_local_file(configured, monkeypatch):
    _, path, _ = configured
    monkeypatch.setattr(publish.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(
        a, 1, stdout=b"private-test-token", stderr=b"private-test-token"))
    result = publish.publish_if_enabled(path)
    assert result["status"] == "error" and "private-test-token" not in str(result)
    assert path.exists()


@pytest.mark.parametrize("location,code,allowed", [
    ("https://team.cloudflareaccess.com/cdn-cgi/access/login/site", 302, True),
    ("https://team.cloudflareaccess.com.evil.test/cdn-cgi/access/login", 302, False),
    ("http://team.cloudflareaccess.com/cdn-cgi/access/login", 302, False),
    ("https://team.cloudflareaccess.com/cdn-cgi/access/login", 403, False),
])
def test_login_probe_requires_an_https_access_redirect(monkeypatch, location, code, allowed):
    class Opener:
        def open(self, req, timeout):
            assert "Authorization" not in req.headers
            raise HTTPError(req.full_url, code, "blocked", {"Location": location}, None)

    monkeypatch.setattr(publish, "build_opener", lambda *a: Opener())
    if allowed:
        publish._check_login(HOST)
    else:
        with pytest.raises(publish.PublishError):
            publish._check_login(HOST)


def test_all_application_pages_are_checked(monkeypatch):
    api = publish.Cloudflare("a" * 32, "not-real")
    pages = []

    def get(path, page):
        pages.append(page)
        return {"result": [{"id": page}], "result_info": {"total_pages": 2}}

    monkeypatch.setattr(api, "get", get)
    assert api.items("/access/apps") == [{"id": 1}, {"id": 2}]
    assert pages == [1, 2]


def test_sync_keeps_local_dashboard_when_upload_is_refused(conn, tmp_path, monkeypatch):
    from test_sync import FakeSource

    from garmin_mcp import dashboard, sync

    path = tmp_path / "index.html"
    path.write_text("local dashboard")
    monkeypatch.setattr(sync, "db_path", lambda: tmp_path / "test.db")
    monkeypatch.setattr(sync, "_personal_api", FakeSource)
    monkeypatch.setattr(dashboard, "build", lambda c, **options: path)
    monkeypatch.setattr(publish, "publish_if_enabled", lambda p: {
        "status": "error", "reason": "Access is not configured"})
    result = sync.run_sync(days=1, source="personal_api", delay=0)
    assert result["sources"]["personal_api"]["errors"] == 0
    assert result["dashboard"] == str(path)
    assert result["dashboard_publish"]["status"] == "error"
    assert "dashboard_error" not in result and path.read_text() == "local dashboard"
