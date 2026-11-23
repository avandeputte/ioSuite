"""The shared updater, without a database: GitHub is a stub, update.sh a tiny script that writes
its result file. (The suite's daily-check switch and the rows the apps write are in test_suiteupdates.py.)"""
import json
import time
import urllib.error

import pytest
from fastapi import FastAPI

from iosuite_shared import updates
from iosuite_shared.fastapi import Auth


@pytest.fixture
def fresh_db():
    """Overrides conftest's autouse database fixture: nothing here needs MariaDB."""
    yield


@pytest.fixture(autouse=True)
def one_copy():
    """What the apps of a copy share (one update.sh run, one answer from GitHub), as a process starts with it."""
    def reset():
        updates._Copy.members.clear()
        updates._Copy.checked.clear()
        updates._Copy.progress.update(running=False, error=None, log="", started=None, finished=None)
    reset()
    yield
    reset()


def asked_again(u):
    """The next check asks GitHub itself, not what an app of this copy found a moment ago."""
    updates._Copy.checked.clear()
    return u


def make_updater(tmp_path, monkeypatch, version="1.2.0", **kw):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    kw.setdefault("result_file", tmp_path / ".update-result")
    u = updates.Updater("iotest", version, tmp_path, repo="someone/iotest", branch="main", **kw)
    u.in_docker = lambda: False
    return u


def github(sha="abcdef0123456789", remote_version="1.3.0", msg="v1.3.0: better", fail=False, refs=True, limited=False):
    """GitHub as the Updater asks it: the branch's commit (from git's info/refs, or with refs=False only from the API,
    which limited=True has used up) and the suite's version file at that commit (shared/iosuite_shared/__init__.py)."""
    full = sha.ljust(40, "0")
    def _get(url, accept=""):
        if fail:
            raise OSError("no network")
        if url.endswith(".git/info/refs?service=git-upload-pack"):
            if not refs:
                raise OSError("github.com away")
            return (f"001e# service=git-upload-pack\n0000015b{full} HEAD\x00multi_ack symref=HEAD:refs/heads/main\n"
                    f"003f{'1' * 40} refs/heads/feature\n003f{full} refs/heads/main\n0000").encode()
        if "api.github.com" in url:
            if limited:
                raise urllib.error.HTTPError(url, 403, "rate limit exceeded", {}, None)
            return json.dumps({"sha": full, "commit": {"committer": {"date": "2026-11-05T01:02:03Z"}, "message": msg + "\n\nmore"}}).encode()
        assert url.endswith(f"/{'fedcba9876543210'.ljust(40, '0')}/" + updates.VERSION_FILE), url
        if remote_version is None:
            return b"nothing here"
        return f'__version__ = "{remote_version}"\n'.encode()
    return _get


def test_commit_from_file_and_check_outcomes(tmp_path, monkeypatch):
    u = make_updater(tmp_path, monkeypatch)
    assert u.local_commit() == "unknown" and u.status()["installed"] == "unknown"
    (tmp_path / "COMMIT").write_text("abcdef0123456789\n")
    assert u.local_commit() == "unknown"  # cached, "unknown" too: no git subprocess per status call
    u._commit = None  # as after the restart update.sh does
    assert u.local_commit() == "abcdef0123456789"

    asked_again(u)._get_url = github()
    assert u.check()["status"] == "current"  # the same commit

    asked_again(u)._get_url = github(sha="fedcba9876543210")
    c = u.check()
    assert c["status"] == "update" and c["remoteVersion"] == "1.3.0" and c["remote"] == "fedcba9" and "remoteDate" not in c
    # github.com's git address away: the API (with the date and the message), and its hourly limit said plainly
    asked_again(u)._get_url = github(sha="fedcba9876543210", refs=False)
    c = u.check()
    assert c["status"] == "update" and c["remote"] == "fedcba9" and c["remoteDate"] == "2026-11-05" and c["remoteMessage"] == "v1.3.0: better"
    asked_again(u)._get_url = github(sha="fedcba9876543210", refs=False, limited=True)
    c = u.check()
    assert c["status"] == "error" and "hourly limit" in c["error"]
    assert updates.head_from_refs(github()("https://github.com/a/b.git/info/refs?service=git-upload-pack"), "feature") == "1" * 40
    assert updates.head_from_refs(b"0000", "main") is None

    asked_again(u)._get_url = github(sha="fedcba9876543210", remote_version="1.2.0")  # another commit, the same version: nothing to install
    assert u.check()["status"] == "current"
    asked_again(u)._get_url = github(sha="fedcba9876543210", remote_version="1.1.9")  # this install is ahead of the branch
    assert u.check()["status"] == "current"
    asked_again(u)._get_url = github(sha="fedcba9876543210", remote_version=None)  # no version line found: say so, to be safe
    c = u.check()
    assert c["status"] == "update" and c["remoteVersion"] is None
    asked_again(u)._get_url = github(fail=True)
    c = u.check()
    assert c["status"] == "error" and "no network" in c["error"]


def test_version_line_shapes():
    assert updates.VERSION_RE.search('APP_VERSION = "2.0.1"\n') is None  # one spelling in every app
    assert updates.VERSION_RE.search('"""doc"""\n__version__ = "0.4.2"\n').group(1) == "0.4.2"
    assert updates._version_tuple("1.10.2") > updates._version_tuple("1.9.9")


def test_the_daily_check_follows_the_suites_switch(tmp_path, monkeypatch):
    u = make_updater(tmp_path, monkeypatch)
    monkeypatch.setattr(updates, "auto_check_enabled", lambda: True)  # the suite's switch (in the database)
    assert u.auto_check_enabled()
    monkeypatch.setattr(updates, "auto_check_enabled", lambda: False)
    assert not u.auto_check_enabled()


def test_what_it_follows_is_the_machines(tmp_path, monkeypatch):
    monkeypatch.setattr("iosuite_shared.config.REPO", "me/suite")
    monkeypatch.setattr("iosuite_shared.config.BRANCH", "dev")
    u = updates.Updater("iocalendar", "1", tmp_path)
    assert u.repo == "me/suite" and u.branch == "dev"
    assert updates.Updater("iotask", "1", tmp_path, repo="x/y", branch="z").repo == "x/y"


def test_the_apps_of_a_copy_ask_github_once_and_update_once(tmp_path, monkeypatch):
    a, b = make_updater(tmp_path, monkeypatch), updates.Updater("iotask", "1.2.0", tmp_path, repo="someone/iotest", branch="main")
    b.in_docker = lambda: False
    (tmp_path / "COMMIT").write_text("abcdef0123456789\n")
    a._commit = b._commit = None
    asked = []
    stub = github(sha="fedcba9876543210")
    a._get_url = lambda url, accept="": asked.append(url) or stub(url, accept)
    b._get_url = lambda url, accept="": pytest.fail("the second app of the copy asked GitHub again")
    assert a.check()["status"] == "update" and b.check()["status"] == "update" and len(asked) == 2  # the branch, and its version file
    assert a.progress is b.progress  # one update.sh run between them


def test_run_update_script_and_result(tmp_path, monkeypatch):
    u = make_updater(tmp_path, monkeypatch)
    assert not u.can_run()
    with pytest.raises(RuntimeError, match="cannot update itself"):
        u.run()
    (tmp_path / ".venv").mkdir()
    (tmp_path / "update.sh").write_text('#!/bin/sh\necho "repo=$IOSUITE_REPO ref=$IOSUITE_REF"\nprintf "ok: updated to v9 now\\n" > "$IOSUITE_RESULT"\n')
    assert u.can_run() and u.status()["canRun"]
    monkeypatch.setenv("IOSUITE_REF", "0123abc")  # a ref in the service's environment is never passed on: the tip of the branch
    with pytest.raises(TypeError):
        u.run("0123abc")  # and a request cannot name one (a fork's commit is served under the repository's address)
    u.run()
    for _ in range(100):
        if not u.progress["running"]:
            break
        time.sleep(0.05)
    assert not u.progress["running"] and u.progress["error"] is None
    assert "repo=someone/iotest ref=\n" in u.progress["log"]
    assert u.last_result()["ok"] and u.last_result()["text"] == "updated to v9 now"

    (tmp_path / "update.sh").write_text('#!/bin/sh\necho "\\033[1;31merror:\\033[0m packages failed" >&2\nexit 3\n')
    u.run()
    for _ in range(100):
        if not u.progress["running"]:
            break
        time.sleep(0.05)
    assert u.progress["error"] == "error: packages failed"
    assert u.last_result() is None  # the old result file was removed before the run

    u.in_docker = lambda: True
    with pytest.raises(RuntimeError, match="pulling the image"):
        u.run()
    assert u.status()["docker"] and not u.can_run()


def admin_app(auth: Auth, monkeypatch):
    """The router under an admin, without the database: the middleware is replaced by one that signs an admin in."""
    app = FastAPI()
    admin = {"id": 1, "name": "alex", "role": "admin", "suiteAdmin": True, "passwordless": False}

    @app.middleware("http")
    async def as_admin(request, call_next):
        request.state.user = admin
        return await call_next(request)
    monkeypatch.setattr("iosuite_shared.users.is_admin", lambda u: bool(u and u.get("role") == "admin"))
    monkeypatch.setattr("iosuite_shared.users.any_users", lambda: True)
    return app


