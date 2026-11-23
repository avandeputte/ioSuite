"""Updating the program itself: which commit is installed, whether GitHub has a newer version, running update.sh,
and restarting.

    from iosuite_shared.updates import Updater
    updater = Updater("iocalendar", version=__version__)                    # the program folder, repository and branch: the machine's (config)
    updater.start_daily()                                                   # the daily check, while the setting is on
    app.include_router(auth.server_router(updater))                         # GET/POST /api/server

The suite is one program in one repository and has one version, which every app carries: iosuite_shared.__version__.
An update is a higher version on the branch; a commit that leaves the version as it is (the docs, a workflow) is
nothing to install.

`update.sh` sits in the program folder; this module only runs it. The script is told where to write its outcome and
which repository and branch to follow through IOSUITE_RESULT, IOSUITE_REPO, IOSUITE_BRANCH and IOSUITE_REF in its
environment. Docker installs are updated by pulling the image, so there the check only reports.

One copy of the program runs several apps, and an update is the copy's: every app keeps its Updater and its row in
the Shared ioSuite database (iosuite_shared.suiteupdates), so Settings › Global settings › Updates and the start
page's MCP endpoint go on listing the apps, but the apps of one copy ask GitHub once between them and run update.sh
once (`_Copy`), each writing the same outcome to its own row.

The "check for updates daily" switch is one setting for the whole suite in the Shared ioSuite database (update_check).
"""
import json
import logging
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from iosuite_shared import config, db, suiteupdates

DAILY = 24 * 3600
VERSION_FILE = "iosuite_shared/__init__.py"  # where the suite's version is, in the repository
CHECK_KEPT_S = 60  # the apps of one copy ask GitHub once between them
VERSION_RE = re.compile(r'^__version__\s*=\s*"([^"]+)"', re.M)
_version_tuple = suiteupdates.version_tuple


def head_from_refs(data: bytes, ref: str) -> str | None:
    """The commit a branch (or a tag) is at, in GitHub's answer to git's first question (info/refs)."""
    m = re.search(r"([0-9a-f]{40}) refs/(?:heads|tags)/" + re.escape(ref) + r"(?=[\x00\n])", data.decode("utf-8", "replace"))
    return m.group(1) if m else None


AUTO = True  # False: never ask GitHub unasked (the test suites)


def auto_check_enabled() -> bool:
    """The suite's switch: every app asks GitHub once a day whether there is a newer version."""
    return AUTO and (db.get_setting("update_check", "1") or "1") == "1"


def set_auto_check(on: bool) -> None:
    db.set_setting("update_check", "" if on else "0")  # on is the default: no row


class _Copy:
    """What the apps of one copy of the program share: one update.sh run, one answer from GitHub."""
    lock = threading.Lock()
    progress: dict = {"running": False, "error": None, "log": "", "started": None, "finished": None}
    members: list = []   # every Updater of this process
    checked: dict = {}   # (repo, branch) -> (at, what check() found)


class Updater:
    """One per app. `app` is its key (iocalendar), `version` the running version (the suite's: app.__version__).
    `root` is the program folder (update.sh, .venv, the checkout), `repo` and `branch` what it follows: the
    machine's unless given."""

    def __init__(self, app: str, version: str, root=None, repo: str = None, branch: str = None, result_file=None,
                 user_agent: str = None):
        self.app, self.version, self.root = app, version, Path(root or config.BASE)
        self.repo = repo or config.REPO
        self.branch = branch or config.BRANCH
        self.result_file = Path(result_file) if result_file else config.DATA_DIR / ".update-result"
        self.user_agent = user_agent or app
        self._commit = None
        self.local_commit()  # read now, as the process starts: an update moves HEAD while this copy still runs the code it started with
        self.progress = _Copy.progress
        _Copy.members.append(self)

    # ---- what is installed
    def in_docker(self) -> bool:
        return os.path.exists("/.dockerenv")

    def local_commit(self) -> str:
        """The installed commit (cached: it only changes through update.sh, which restarts the process)."""
        if self._commit is None:
            self._commit = self._read_commit()  # "unknown" is kept too: no git subprocess per status call
        return self._commit

    def _git_root(self) -> Path | None:
        """The program folder when it is a checkout of the repository."""
        return self.root if (self.root / ".git").exists() else None

    def _read_commit(self) -> str:
        if self._git_root():
            try:
                return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.root), capture_output=True, text=True,
                                      timeout=10).stdout.strip() or "unknown"
            except (OSError, subprocess.SubprocessError):
                return "unknown"
        try:
            return (self.root / "COMMIT").read_text().strip() or "unknown"
        except OSError:
            return "unknown"

    # ---- the daily check
    def auto_check_enabled(self) -> bool:
        try:
            return auto_check_enabled()
        except Exception:  # noqa: BLE001  the database is away: no check
            return False

    def _get_url(self, url: str, accept: str = "application/vnd.github+json") -> bytes:
        req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": self.user_agent})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read()

    def _remote_version(self, sha: str) -> str | None:
        """The suite's version at that commit, so a commit that leaves it as it is (the docs, a workflow) is not announced as new."""
        text = self._get_url(f"https://raw.githubusercontent.com/{self.repo}/{sha}/{VERSION_FILE}", "text/plain").decode("utf-8", "replace")
        m = VERSION_RE.search(text)
        return m.group(1) if m else None

    def _branch_head(self) -> dict:
        """The branch's commit: {sha} from GitHub's git address (as git asks it), which has no hourly limit, or, when
        that cannot be read, {sha, date, message} from api.github.com, which allows a server 60 unsigned calls an hour
        (a suite of apps checking together soon uses them up)."""
        try:
            sha = head_from_refs(self._get_url(f"https://github.com/{self.repo}.git/info/refs?service=git-upload-pack", "*/*"), self.branch)
            if sha:
                return {"sha": sha}
        except Exception:  # noqa: BLE001 - the API below says why, if it fails too
            pass
        try:
            c = json.loads(self._get_url(f"https://api.github.com/repos/{self.repo}/commits/{self.branch}"))
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise RuntimeError("GitHub's hourly limit for this server is used up; it resets within the hour") from e
            raise
        return {"sha": c["sha"], "date": c["commit"]["committer"]["date"][:10], "message": c["commit"]["message"].splitlines()[0][:120]}

    def check(self) -> dict:
        """Ask GitHub: {installed, version, remote, remoteDate, remoteMessage, remoteVersion,
        status: current | update | error, checked}; the app's row (iosuite_shared.suiteupdates) gets the answer."""
        mine = self.local_commit()
        kept = _Copy.checked.get((self.repo, self.branch))
        if kept and time.time() - kept[0] < CHECK_KEPT_S:  # another app of this copy just asked
            out = dict(kept[1])
            suiteupdates.publish(self.app, installed=self.version, git_commit=mine[:7], status=out["status"], checked_at=out["checked"],
                                 latest=out.get("remoteVersion") or (self.version if out["status"] == "current" else None))
            return out
        out = {"installed": mine[:7], "version": self.version, "checked": int(time.time())}
        try:
            c = self._branch_head()
            out.update(remote=c["sha"][:7])
            if c.get("date"):
                out.update(remoteDate=c["date"], remoteMessage=c["message"])
            if mine != "unknown" and c["sha"].startswith(mine):
                out["status"] = "current"
            else:
                try:
                    rv = self._remote_version(c["sha"])
                except Exception:  # noqa: BLE001
                    rv = None
                out["remoteVersion"] = rv
                # a newer build is one with a higher version; the same version under another commit (the docs, a
                # workflow) is nothing to install, and an older one means this install is ahead of the branch
                out["status"] = "update" if rv is None or _version_tuple(rv) > _version_tuple(self.version) else "current"
        except Exception as e:  # noqa: BLE001
            out.update(status="error", error=str(e)[:160])
        latest = out.get("remoteVersion") or (self.version if out["status"] == "current" else None)
        suiteupdates.publish(self.app, installed=self.version, git_commit=mine[:7], latest=latest, status=out["status"],
                             checked_at=out["checked"])
        if out["status"] != "error":
            _Copy.checked[(self.repo, self.branch)] = (time.time(), dict(out))
        if out["status"] == "update" and out.get("remoteVersion"):
            self._announce(out["remoteVersion"])
        return out

    def _announce(self, version: str) -> None:
        """Tell the suite admins who want it that a newer version is out: once per version, whichever app saw it first."""
        try:
            from iosuite_shared import push
            push.notify_admins("updates", f"ioSuite {version} is out", f"This server has {self.version}. Update every app in one go "
                               "under Settings › Global settings › Updates.", url=push.link("iostart", "#/settings/global/updates"),
                               once=f"update:{version}")
        except Exception:  # noqa: BLE001 - a notification that cannot go out never stops the check
            pass

    def start_daily(self, first_after: float = 60, watch: bool = True) -> threading.Thread:
        """Ask GitHub once a day (the first time a minute after start) whether the branch has moved on, while the
        setting is on. Only the public commit is fetched; nothing about this install is sent. With `watch`, also
        watch for a check or an update a suite admin asks for (watch())."""
        if watch:
            self.watch()
        def loop():
            time.sleep(first_after)
            while True:
                try:
                    if self.auto_check_enabled():
                        self.check()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    from iosuite_shared import push
                    push.purge()  # the notifications' sent-once keys of long ago
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(DAILY)
        t = threading.Thread(target=loop, name="update-check", daemon=True)
        t.start()
        return t

    # ---- asked from the start page (iosuite_shared.suiteupdates)
    def watch(self, every: float = None) -> threading.Thread:
        """Say what is installed, then look every few seconds for a check or an update a suite admin asked for and run
        it: a check asks GitHub even while the daily check is off (an admin asked), an update runs update.sh."""
        def loop():
            self._said_hello()
            beat = time.time()
            while True:
                time.sleep(every or suiteupdates.WATCH_S)
                try:
                    self.serve(suiteupdates.claim(self.app))
                except Exception:  # noqa: BLE001
                    pass
                if time.time() - beat >= suiteupdates.BEAT_S:
                    beat = time.time()
                    suiteupdates.beat(self.app)
        t = threading.Thread(target=loop, name="update-watch", daemon=True)
        t.start()
        return t

    def _said_hello(self) -> None:
        """What a fresh start knows: the version, the commit, whether it can update itself; and when the update before
        the restart was running, how it went (update.sh wrote that down before the restart)."""
        r = suiteupdates.row(self.app) or {}
        fields = {"installed": self.version, "git_commit": self.local_commit()[:7], "can_run": int(self.can_run()), "docker": int(self.in_docker())}
        last = self.last_result()
        if r.get("state") == "running" and not self.progress["running"]:
            fields.update(state="ok" if last and last["ok"] else "failed",
                          message=(last or {}).get("text") or "update.sh did not say how it went (see the server log)")
        elif r.get("state") == "failed" and last and last["ok"] and last["at"] >= (r.get("updated_at") or 0) - 120:
            # the run before this start was marked failed as the restart ended it, but update.sh had written "ok"
            # (the result file is removed when a run starts, so it is that run's)
            fields.update(state="ok", message=last["text"])
        elif r.get("state") in ("ok", "failed") and (r.get("git_commit") or "") != fields["git_commit"] and not last:
            # the row says how an update of another program went (the one this install replaced: its own update.sh,
            # its own folders). Nothing of that is about what runs here now, so the line is cleared rather than shown.
            fields.update(state="", message="")
        if r.get("latest") and r.get("status") != "error":
            # the newest version GitHub had when last asked: what this start installed may be it
            fields["status"] = "update" if _version_tuple(r["latest"]) > _version_tuple(self.version) else "current"
        suiteupdates.publish(self.app, **fields)

    def serve(self, action: str | None) -> None:
        """Run what a suite admin asked for ('check', 'update' or 'restart'); an update that cannot run says why on the row."""
        if action == "check":
            self.check()
        elif action == "restart":
            for u in _Copy.members:  # the copy starts again once, whichever of its apps were asked
                if u is not self:
                    suiteupdates.claim(u.app)
            logging.getLogger("iosuite_shared.updates").info("restart asked from Settings: the copy starts again")
            self.restart()
        elif action == "update":
            try:
                self.run()
            except RuntimeError as e:
                suiteupdates.publish(self.app, state="failed", message=str(e)[:300])

    # ---- running update.sh
    def last_result(self) -> dict | None:
        """The outcome of the last update.sh run, from the file it writes before the restart: {ok, text, at}."""
        try:
            text = self.result_file.read_text().strip()
        except OSError:
            return None
        if not text:
            return None
        return {"ok": text.startswith("ok:"), "text": text.split(":", 1)[-1].strip()[:300], "at": int(self.result_file.stat().st_mtime)}

    def _writable(self) -> bool:
        g = self._git_root()
        paths = [self.root] + [p for p in (self.root / ".venv", g / ".git" if g else None) if p and p.exists()]
        return all(os.access(str(p), os.W_OK) for p in paths)

    def can_run(self) -> bool:
        return (self.root / "update.sh").exists() and (self.root / ".venv").exists() and not self.in_docker() and self._writable()

    def status(self) -> dict:
        return {"version": self.version, "installed": self.local_commit()[:7], "docker": self.in_docker(), "canRun": self.can_run(),
                "repo": self.repo, "branch": self.branch, "progress": dict(self.progress), "lastUpdate": self.last_result()}

    def run(self) -> None:
        """update.sh in a child process, which installs the tip of the branch; the service manager starts the program
        again when it finishes. Raises RuntimeError when it cannot run. With several apps in this copy, the first
        one asked runs it and the others follow along. Another commit is installed from a shell on the server only
        (IOSUITE_REF=<commit> ./update.sh): GitHub serves a fork's commits under the repository's own address, so a
        commit id taken from a request could install anybody's code."""
        if self.in_docker():
            raise RuntimeError("In Docker, update by pulling the image: docker compose pull && docker compose up -d")
        if not self.can_run():
            raise RuntimeError("This install cannot update itself (no update.sh or .venv in the program folder, or the folder is not "
                               "writable by the service). Run ./update.sh in the program folder.")
        with _Copy.lock:
            if self.progress["running"]:  # another app of this copy started it: the same run
                suiteupdates.publish(self.app, state="running", message=f"update.sh started at version {self.version}")
                return
            self.progress.update(running=True, error=None, log="", started=int(time.time()), finished=None)
        mine = [u.app for u in _Copy.members]

        def publish(**fields):
            for k in mine:
                suiteupdates.publish(k, **fields)

        suiteupdates.publish(self.app, state="running", message=f"update.sh started at version {self.version}")
        env = dict(os.environ, IOSUITE_RESULT=str(self.result_file), IOSUITE_REPO=self.repo, IOSUITE_BRANCH=self.branch,
                   IOSUITE_RUNNING=self.version)
        env.pop("IOSUITE_REF", None)  # never inherited: the service installs the tip of its branch
        try:
            self.result_file.unlink()
        except OSError:
            pass

        def work():
            restarting = False
            try:
                res = subprocess.run(["sh", str(self.root / "update.sh")], cwd=str(self.root), capture_output=True, text=True, timeout=1800, env=env)
                self.progress["log"] = (res.stdout + res.stderr)[-3000:]
                done = self.last_result()
                if res.returncode < 0 and done and done["ok"]:
                    # update.sh wrote "ok" and then restarted the service, which ends every process of it, the script
                    # included (killed by a signal): the update went through, the restart is under way
                    restarting = True
                elif res.returncode != 0:
                    tail = re.sub(r"\x1b\[[0-9;]*m", "", (res.stderr or res.stdout)).strip()
                    self.progress["error"] = tail.splitlines()[-1] if tail else f"exit {res.returncode}"
                elif os.environ.get("INVOCATION_ID") and "updated to" in (self.last_result() or {}).get("text", ""):
                    # still running after a successful update: the service could not be restarted from here (it runs
                    # as an account without sudo), so this process ends and systemd (Restart=always) starts the new version
                    restarting = True
                    self.restart(1.5)
            except Exception as e:  # noqa: BLE001
                self.progress["error"] = str(e)[:300]
            finally:
                self.progress.update(running=False, finished=int(time.time()))
                last = self.last_result()
                if self.progress["error"]:
                    publish(state="failed", message=self.progress["error"][:300])
                elif restarting:
                    # updated, and the restart is under way: the rows stay "running" until the new version starts and
                    # says how it went (_said_hello). Marked "ok" here, the suite's Updates page would see these apps
                    # still on the old version and stop following along while a slow starter (ioPix) is coming back
                    publish(state="running", message=f"{last['text']}; restarting")
                elif last:  # nothing to install, or updated without a restart (update.sh says what to do)
                    publish(state="ok" if last["ok"] else "failed", message=last["text"])

        threading.Thread(target=work, name="self-update", daemon=True).start()

    @staticmethod
    def restart(delay: float = 0.5) -> None:
        """End the process shortly; systemd (Restart=always), launchd (KeepAlive) or Docker (restart: unless-stopped)
        starts the program again, with every app of this copy."""
        threading.Timer(delay, lambda: os._exit(0)).start()


# ---- the log: the copy's one (iosuite_shared.logs); these are the names the apps call
def setup_log(*_old, **_ignored) -> bool:
    """Logging the same way in every app: iosuite_shared.logs.setup (the copy's one log, each line marked with its app)."""
    from iosuite_shared import logs
    return logs.setup()


def tail(app: str, lines: int = 300, contains: str = "", level: str = "any") -> dict:
    """The last lines of one app in the copy's log (the apps' MCP tools): iosuite_shared.logs.tail."""
    from iosuite_shared import logs
    return logs.tail(app, lines, contains, level)
