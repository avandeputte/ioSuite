#!/usr/bin/env python3
"""How much memory a copy of ioSuite holds and how fast it answers, with different lists of apps.

    python3 tools/measure.py --base /opt/iosuite --sets "iostart,iotask;iostart,iocalendar,iotask,iocontact,ionote,iorecipe;all"

For each list: starts `iosuite serve` with that list (APPS in the environment wins over the machine's file), waits
until it has started, lets it settle, then reads the memory of the copy and the processes it started (PSS, so pages
two processes share are counted once) and times requests to every app's status and page, one after another.
The copy of the program folder must not be running meanwhile: the same ports are used.
Not part of the program: nothing imports it.
"""
import argparse
import json
import os
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke  # noqa: E402 - ask(), manifests(): beside this file


def tree(pid: int) -> list:
    """pid and every process below it."""
    kids = {}
    for p in Path("/proc").iterdir():
        if p.name.isdigit():
            try:
                kids.setdefault(int((p / "stat").read_text().rsplit(")", 1)[1].split()[1]), []).append(int(p.name))
            except (OSError, IndexError, ValueError):
                pass
    out, todo = [], [pid]
    while todo:
        x = todo.pop()
        out.append(x)
        todo += kids.get(x, [])
    return out


def memory(pid: int) -> tuple:
    """(PSS, RSS) in MB of pid's tree."""
    pss = rss = 0
    for p in tree(pid):
        try:
            for line in Path(f"/proc/{p}/smaps_rollup").read_text().splitlines():
                if line.startswith("Pss:"):
                    pss += int(line.split()[1])
                elif line.startswith("Rss:"):
                    rss += int(line.split()[1])
        except OSError:
            pass
    return pss / 1024, rss / 1024


def sign_in(web: str, who: str):
    """The session cookie of NAME:PASSWORD at the start page (the same sign-in holds in every app); None when refused."""
    import urllib.request
    name, _, password = who.partition(":")
    req = urllib.request.Request(web + "/api/auth/login", data=json.dumps({"name": name, "password": password}).encode(),
                                 headers={"Content-Type": "application/json", "Origin": web})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return "; ".join(c.split(";", 1)[0] for c in r.headers.get_all("Set-Cookie") or []) or None
    except OSError:
        return None


def timed(url: str, n: int, cookie: str = None) -> tuple:
    """(median, 95th percentile) in ms of n requests, one after another."""
    ms = []
    for _ in range(n):
        t = time.perf_counter()
        code = smoke.ask(url, cookie=cookie)[0]
        ms.append((time.perf_counter() - t) * 1000)
        if code != 200:
            return None, None
    ms.sort()
    return statistics.median(ms), ms[int(len(ms) * 0.95) - 1]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--base", default=str(smoke.ROOT))
    p.add_argument("--sets", default="all", help="lists of apps, ';' between them")
    p.add_argument("--settle", type=int, default=30, help="seconds to let a started copy settle")
    p.add_argument("--requests", type=int, default=200)
    p.add_argument("--login", help="NAME:PASSWORD of an account: its own record is asked of every app too (signed in, read from the database)")
    p.add_argument("--json", help="write the numbers here as well")
    a = p.parse_args()
    base = Path(a.base)
    smoke.ROOT = base
    cfg, known = smoke.machine_file(), smoke.manifests()
    web = f"http://127.0.0.1:{cfg.get('PORT') or 80}"
    results = []
    for apps in [s.strip() for s in a.sets.split(";") if s.strip()]:
        keys = list(known) if apps == "all" else [x.strip() for x in apps.split(",")]
        env = dict(os.environ, APPS=",".join(keys))
        t0 = time.time()
        proc = subprocess.Popen([str(base / ".venv/bin/iosuite"), "serve"], env=env, cwd=base,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            while time.time() - t0 < 300 and smoke.ask(web + "/-/status", 3)[0] != 200:
                if proc.poll() is not None:
                    raise SystemExit(f"the copy with {apps} stopped by itself (exit {proc.returncode})")
                time.sleep(0.5)
            started = time.time() - t0
            time.sleep(a.settle)
            idle = memory(proc.pid)
            rows, cookie = {}, sign_in(web, a.login) if a.login and "iostart" in keys else None
            for key in keys:
                folder = "" if key == "iostart" else "/" + known[key]["folder"]
                rows[key] = {"status": timed(f"{web}{folder}/api/status", a.requests), "page": timed(f"{web}{folder}/", a.requests // 4),
                             "me": timed(f"{web}{folder}/api/auth/me", a.requests, cookie) if cookie else (None, None)}
            after = memory(proc.pid)
            results.append({"apps": keys, "start_s": round(started, 1), "processes": len(tree(proc.pid)),
                            "idle_pss_mb": round(idle[0]), "idle_rss_mb": round(idle[1]), "after_pss_mb": round(after[0]), "requests": rows})
            print(f"\n{len(keys)} apps ({', '.join(keys)})")
            print(f"  started in {started:.1f} s; {len(tree(proc.pid))} process(es); memory {idle[0]:.0f} MB settled, {after[0]:.0f} MB after the requests (RSS {idle[1]:.0f} MB)")
            for key, r in rows.items():
                s, pg = r["status"], r["page"]
                def f(x):
                    return "failed" if x[0] is None else f"{x[0]:.1f} ms (95%: {x[1]:.1f})"
                print(f"  {key:12} status {f(s):28} page {f(pg):28}" + (f" signed in {f(r['me'])}" if cookie else ""))
        finally:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(20)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    pass
            time.sleep(2)
    if a.json:
        Path(a.json).write_text(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
