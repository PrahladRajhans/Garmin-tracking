"""Self-update: keep the installed connector on the latest tested `main` without manual steps.

Runs at the start of every scheduled sync (disable with GARMIN_AUTO_UPDATE=0). Safe by design:
- only when the code directory is a git checkout with no local changes;
- only fast-forward to origin/main (never rewrites or merges);
- reinstalls the package only when the code changed, then re-runs the command on the new code;
- Git failures leave the old sync available; failed dependency installs stop the sync and
  leave a marker so the next scheduled run retries before using updated code.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

BRANCH = "main"


def repo_dir() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists() and (parent / "pyproject.toml").exists():
            return parent
    return None


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, timeout=120).stdout.strip()


def update(reexec: bool = True) -> dict[str, Any]:
    if os.getenv("GARMIN_AUTO_UPDATE", "1") == "0":
        return {"skipped": "disabled by GARMIN_AUTO_UPDATE=0"}
    if os.getenv("GARMIN_AUTO_UPDATED") == "1":
        return {"skipped": "already updated in this run"}
    repo = repo_dir()
    if repo is None:
        return {"skipped": "not a git checkout"}
    marker = None
    try:
        from garmin_mcp.config import data_dir

        suffix = hashlib.sha256(str(repo).encode()).hexdigest()[:12]
        marker = data_dir() / f"pending-install-{suffix}.json"
        if _git(repo, "status", "--porcelain", "--untracked-files=no"):
            return {"skipped": "local changes present; not touching them",
                    "requires_repair": marker.exists()}
        before = _git(repo, "rev-parse", "HEAD")
        _git(repo, "fetch", "--quiet", "origin", BRANCH)
        upstream = f"origin/{BRANCH}"
        target = _git(repo, "rev-parse", upstream)
        current = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
        has_main = current != BRANCH and _has_branch(repo)
        candidates = ("HEAD", BRANCH) if has_main else ("HEAD",)
        for ref in candidates:
            if not _is_ancestor(repo, ref, upstream):
                return {"skipped": f"{ref} has commits outside {upstream}; left it in place",
                        "requires_repair": marker.exists()}
        # Persist before changing files: even an interrupted update must retry installation.
        if before != target:
            marker.write_text(json.dumps({"repo": str(repo), "commit": target}), encoding="utf-8")
        if current != BRANCH:
            if has_main:
                _git(repo, "checkout", "--quiet", BRANCH)
            else:
                _git(repo, "checkout", "--quiet", "-b", BRANCH, upstream)
        _git(repo, "merge", "--ff-only", "--quiet", upstream)
        after = _git(repo, "rev-parse", "HEAD")
    except (subprocess.SubprocessError, OSError) as exc:
        return {"error": f"{type(exc).__name__}: {str(exc)[:200]}",
                "requires_repair": bool(marker is not None and marker.exists())}
    if before == after and not marker.exists():
        return {"updated": False, "commit": after[:9]}
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-e", str(repo)],
                       check=True, capture_output=True, timeout=600)
        marker.unlink()
    except (subprocess.SubprocessError, OSError):
        return {"updated": before != after, "commit": after[:9], "requires_repair": True,
                "error": "Dependency installation failed. Sync stopped; next run retries "
                         "installation before using the updated code."}
    result = {"updated": True, "from": before[:9], "to": after[:9]}
    if reexec:
        os.environ["GARMIN_AUTO_UPDATED"] = "1"
        os.execv(sys.executable, [sys.executable, "-m", "garmin_mcp.sync", *sys.argv[1:]])
    return result


def _is_ancestor(repo: Path, ref: str, upstream: str) -> bool:
    try:
        _git(repo, "merge-base", "--is-ancestor", ref, upstream)
    except subprocess.CalledProcessError as exc:
        if exc.returncode == 1:
            return False
        raise
    return True


def _has_branch(repo: Path) -> bool:
    try:
        _git(repo, "rev-parse", "--verify", "--quiet", BRANCH)
        return True
    except subprocess.CalledProcessError:
        return False
