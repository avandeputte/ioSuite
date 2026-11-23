#!/usr/bin/env python3
"""A running copy of ioSuite, asked from outside: is every app it should run there, at its folder, on the right port?

    python3 tools/smoke.py                              the copy of this program folder (config.env), on this machine
    python3 tools/smoke.py --web 8080 --sync 8443 --apps iostart,iotask

Waits for the copy to say it has started (/-/status), then asks every app for its page and its status, and the sync
port for an answer that is not a page. Says what it found, a line per app; exit code 1 when something is missing.
Not part of the program: nothing imports it. The checks on GitHub run it (.github/workflows/tests.yml).
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def ask(url: str, timeout: float = 15):
    """(status, content type, body, Location) of a GET; status 0 when nothing answers."""
    try:
        with OPENER.open(urllib.request.Request(url, headers={"User-Agent": "iosuite-smoke"}), timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read(), ""
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read(), e.headers.get("Location", "")
    except OSError:
        return 0, "", b"", ""


def machine_file() -> dict:
    out = {}
    f = ROOT / "config.env"
    for line in f.read_text().splitlines() if f.exists() else []:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def manifests() -> dict:
    out = {}
    for f in sorted(ROOT.glob("io*/app.json")):
        m = json.loads(f.read_text())
        out[m["key"]] = m
    return out


def main() -> int:
    cfg = machine_file()
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--at", default="127.0.0.1")
    p.add_argument("--web", type=int, default=int(cfg.get("PORT") or 80))
    p.add_argument("--sync", type=int, default=int(cfg.get("SYNC_PORT") or 8443))
    p.add_argument("--apps", default=cfg.get("APPS") or "all")
    p.add_argument("--wait", type=int, default=180, help="seconds to wait for the copy to start")
    a = p.parse_args()
    known = manifests()
    apps = list(known) if a.apps in ("", "all") else [x.strip() for x in a.apps.split(",") if x.strip()]
    web, sync = f"http://{a.at}:{a.web}", f"http://{a.at}:{a.sync}"

    until, code = time.time() + a.wait, 0
    while time.time() < until:
        code = ask(web + "/-/status", 5)[0]
        if code == 200:
            break
        time.sleep(1)
    if code != 200:
        print(f"the copy at {web} did not start in {a.wait} s (/-/status: {code or 'no answer'})")
        return 1

    bad = 0
    for key in apps:
        m = known[key]
        folder = "" if key == "iostart" else "/" + m["folder"]
        notes = []
        code, kind, body, _ = ask(f"{web}{folder}/")
        if code != 200 or "text/html" not in kind:
            notes.append(f"page {code} {kind}")
        code, kind, body, _ = ask(f"{web}{folder}/api/status")
        try:
            status = json.loads(body) if code == 200 else {}
        except ValueError:
            status = {}
        if code != 200 or not status:
            notes.append(f"status {code}")
        if a.sync:
            code, kind, body, where = ask(f"{sync}{folder}/api/status")
            if code != 200:
                notes.append(f"sync port: status {code}")
            code, kind, body, where = ask(f"{sync}{folder}/")
            if code not in (301, 302, 307, 308) or f":{a.web}" not in where and a.web != 80:
                notes.append(f"sync port: the page was not sent to the web port ({code} {where})")
        bad += bool(notes)
        print(f"{key:12} {status.get('version', '?'):8} {'ok' if not notes else '; '.join(notes)}")
    print(f"{len(apps) - bad} of {len(apps)} apps answer as they should")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
