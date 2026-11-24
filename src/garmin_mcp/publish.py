"""Opt-in Cloudflare Pages upload, after checking Access on every project hostname.

No account configuration is changed here. See MAC_SETUP.md and the hosting research note.
Only index.html and fixed privacy headers are staged; database files are never uploaded.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
import tempfile
from hashlib import file_digest, sha256
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

HEADERS = """/*
  Cache-Control: private, no-store
  X-Robots-Tag: noindex, nofollow, noarchive
  Referrer-Policy: no-referrer
  X-Content-Type-Options: nosniff
"""


class PublishError(Exception):
    """A message safe to show in sync logs, without provider responses or credentials."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Cloudflare:
    def __init__(self, account: str, token: str):
        self.base = f"https://api.cloudflare.com/client/v4/accounts/{account}"
        self.token = token

    def get(self, path: str, page: int | None = None) -> dict:
        url = self.base + path + (f"?page={page}&per_page=100" if page else "")
        req = Request(url, headers={"Authorization": f"Bearer {self.token}",
                                    "User-Agent": "garmin-mcp-dashboard-publisher"})
        try:
            # Refuse redirects, including those that could forward the authorization header.
            with build_opener(_NoRedirect()).open(req, timeout=20) as response:
                payload = json.load(response)
        except Exception:  # noqa: BLE001 - never log authenticated provider response details
            raise PublishError("Cloudflare configuration could not be read; nothing uploaded.") \
                from None
        if payload.get("success") is not True or "result" not in payload:
            raise PublishError("Cloudflare rejected the configuration check; nothing uploaded.")
        return payload

    def items(self, path: str) -> list[dict]:
        items = []
        for page in range(1, 101):
            payload = self.get(path, page)
            rows = payload["result"]
            if not isinstance(rows, list):
                raise PublishError("Unexpected Cloudflare list response; nothing uploaded.")
            items.extend(rows)
            total = payload.get("result_info", {}).get("total_pages")
            if (isinstance(total, int) and page >= total) or (total is None and len(rows) < 100):
                return items
        raise PublishError("Cloudflare pagination did not finish; nothing uploaded.")


def _domains(app: dict) -> list[str]:
    if app.get("destinations"):
        return [d.get("uri", "") for d in app["destinations"]]
    return app.get("self_hosted_domains") or [app.get("domain", "")]


def _relevant(domain: str, host: str) -> bool:
    hostname = domain.split("/", 1)[0].lower()
    return (hostname == host or hostname.endswith("." + host)
            or fnmatch.fnmatchcase(host, hostname)
            or fnmatch.fnmatchcase("privacy-check." + host, hostname))


def check_access(api: Cloudflare, project: str, email: str) -> tuple[str, str]:
    info = api.get(f"/pages/projects/{project}")["result"]
    host, branch = info.get("subdomain", ""), info.get("production_branch", "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.pages\.dev", host) or not branch:
        raise PublishError("Pages project hostname or production branch is missing.")
    if set(info.get("domains") or []) - {host}:
        raise PublishError("Custom domains are not supported by this privacy check.")
    if info.get("source"):
        raise PublishError("Use a dedicated Direct Upload project without Git integration.")
    expected = {host, "*." + host}
    found = set()
    for summary in api.items("/access/apps"):
        if not any(_relevant(d, host) for d in _domains(summary)):
            continue
        app_id = summary.get("id", "")
        if not re.fullmatch(r"[a-fA-F0-9-]{36}", app_id):
            raise PublishError("Unexpected Access application identifier.")
        app = api.get(f"/access/apps/{app_id}")["result"]
        domains = _domains(app)
        if (app.get("type") != "self_hosted" or len(domains) != 1
                or domains[0] not in expected or domains[0] in found
                or app.get("options_preflight_bypass")
                or any(d.get("overrides") for d in app.get("destinations") or [])):
            raise PublishError("Access must use two whole-host applications without bypasses "
                               "or overlapping paths. Nothing uploaded.")
        policies = api.items(f"/access/apps/{app_id}/policies")
        # Deliberately support the simplest personal setup only: one Allow, one exact email.
        if (len(policies) != 1 or policies[0].get("decision") != "allow"
                or policies[0].get("include") != [{"email": {"email": email}}]):
            raise PublishError("Each Access app must have one Allow policy for your exact "
                               "email only. Nothing uploaded.")
        found.add(domains[0])
    if found != expected:
        raise PublishError("Both production and wildcard preview Access apps are required. "
                           "Nothing uploaded.")
    return host, branch


def _check_login(host: str) -> None:
    req = Request(f"https://{host}/", headers={"User-Agent": "garmin-mcp-privacy-check"})
    try:
        with build_opener(_NoRedirect()).open(req, timeout=20):
            pass
    except HTTPError as exc:
        target = urlsplit(exc.headers.get("Location", ""))
        if (exc.code in (302, 303, 307) and target.scheme == "https"
                and (target.hostname or "").endswith(".cloudflareaccess.com")
                and target.path.startswith("/cdn-cgi/access/login")):
            return
    except OSError:
        pass
    raise PublishError("Anonymous access did not redirect to Cloudflare Access. Nothing uploaded.")


def publish_if_enabled(path: Path | None, *, check_only: bool = False) -> dict[str, Any]:
    """Publishing errors are reported separately; they never invalidate the local build."""
    from dotenv import dotenv_values

    try:
        config = {**dotenv_values(Path(__file__).resolve().parents[2] / ".env"), **os.environ}
    except OSError:
        return {"status": "error", "reason": "Could not read local publishing configuration."}
    if not config.get("GARMIN_DASHBOARD_PUBLISH"):
        return {"status": "disabled"}
    if config.get("GARMIN_DASHBOARD_PUBLISH") != "cloudflare":
        return {"status": "error", "reason": "Unknown dashboard publishing option."}
    try:
        account = config.get("CLOUDFLARE_ACCOUNT_ID") or ""
        token = config.get("CLOUDFLARE_API_TOKEN") or ""
        project = config.get("GARMIN_CLOUDFLARE_PROJECT") or ""
        email = config.get("GARMIN_DASHBOARD_EMAIL") or ""
        wrangler = Path(config.get("GARMIN_WRANGLER") or "/nonexistent")
        if (not re.fullmatch(r"[a-fA-F0-9]{32}", account) or not token
                or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,57}", project)
                or not re.fullmatch(r"[^\s@*]+@[^\s@*]+\.[^\s@*]+", email)
                or not wrangler.is_absolute() or not wrangler.is_file()):
            raise PublishError("Publishing configuration is incomplete; see MAC_SETUP.md.")
        def authorize() -> tuple[str, str]:
            host, branch = check_access(Cloudflare(account, token), project, email)
            _check_login(host)
            _check_login("privacy-check." + host)
            return host, branch

        if check_only:
            host, _ = authorize()
            return {"status": "checked", "url": f"https://{host}"}
        if path is None:
            raise PublishError("No dashboard file supplied; nothing uploaded.")
        import fcntl

        path = path.resolve()
        stamp = path.with_name(".published-dashboard")
        with path.with_name(".publish.lock").open("a") as lock:
            # Sync, manual builds, and Ollama all publish through this lock. Read
            # the live file after acquiring it, even when the caller built an
            # earlier generation. The local renderer replaces the file atomically.
            fcntl.flock(lock, fcntl.LOCK_EX)
            with tempfile.TemporaryDirectory(prefix="garmin-dashboard-") as staging:
                root = Path(staging)
                assets = root / "assets"
                assets.mkdir()
                snapshot = assets / "index.html"
                with path.open("rb") as current:
                    if os.fstat(current.fileno()).st_size > 25 * 1024 * 1024:
                        raise PublishError("Dashboard exceeds the Pages 25 MiB file limit.")
                    with snapshot.open("wb") as staged:
                        shutil.copyfileobj(current, staged)
                with snapshot.open("rb") as payload:
                    identity = sha256(f"{account}:{project}:{email}:{HEADERS}".encode())
                    digest = file_digest(payload, lambda: identity).hexdigest()
                if stamp.exists() and stamp.read_bytes() == digest.encode("ascii"):
                    return {"status": "unchanged"}
                host, branch = authorize()
                (assets / "_headers").write_text(HEADERS, encoding="utf-8")
                # An interrupted provider request can leave deployment state uncertain.
                stamp.unlink(missing_ok=True)
                # Run outside the checkout so Wrangler cannot discover other config.
                # Credentials travel in the environment, never argv.
                result = subprocess.run(
                    [str(wrangler), "pages", "deploy", str(assets), "--project-name", project,
                     "--branch", branch], cwd=root, env={**os.environ, "CLOUDFLARE_API_TOKEN": token,
                                                         "CLOUDFLARE_ACCOUNT_ID": account, "CI": "true",
                                                         "WRANGLER_SEND_METRICS": "false"},
                    capture_output=True, timeout=180, check=False)
                if result.returncode:
                    raise PublishError("Wrangler upload failed; the local dashboard is available.")
                stamp.write_text(digest, encoding="ascii")
                return {"status": "published", "url": f"https://{host}"}
    except PublishError as exc:
        return {"status": "error", "reason": str(exc)}
    except Exception:  # noqa: BLE001 - optional publishing must not break a local build
        # Provider output and exception text can include secrets. Never copy them to logs.
        return {"status": "error", "reason": "Publishing failed; local dashboard is available."}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Check private dashboard hosting without uploading.")
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    result = publish_if_enabled(None, check_only=True)
    print(json.dumps(result))
    raise SystemExit(0 if result["status"] == "checked" else 1)


if __name__ == "__main__":
    main()
