#!/usr/bin/env python3
"""A running copy of ioSuite under many requests at once: does every one get an answer, within the copy's allowance
of database connections?

    python3 tools/load.py --login alex:PASSWORD                    the copy of this program folder, on this machine
    python3 tools/load.py --web 8080 --each 30 --login alex:PASSWORD

Signs in, then asks every app for the signed-in account (read from the database) `--each` times, all of them at the
same moment, and once more after that. Every answer must be 200: a copy that opens a connection for every request
runs into the database server's limit and answers 500, and one that is merely busy says 503. Then reads what the
copy says about its connections (/-/status, from this machine only): never more open than DB_CONNECTIONS.
Not part of the program: nothing imports it. The checks on GitHub run it (.github/workflows/tests.yml).
"""
import argparse
import collections
import concurrent.futures
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure  # noqa: E402 - sign_in(): beside this file
import smoke  # noqa: E402 - ask(), manifests(), machine_file()


def main() -> int:
    cfg = smoke.machine_file()
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--at", default="127.0.0.1")
    p.add_argument("--web", type=int, default=int(cfg.get("PORT") or 80))
    p.add_argument("--apps", default=cfg.get("APPS") or "all")
    p.add_argument("--each", type=int, default=30, help="requests to every app, all at the same moment")
    p.add_argument("--rounds", type=int, default=2)
    p.add_argument("--login", required=True, help="NAME:PASSWORD of an account")
    a = p.parse_args()
    known = smoke.manifests()
    apps = list(known) if a.apps in ("", "all") else [x.strip() for x in a.apps.split(",") if x.strip()]
    web = f"http://{a.at}:{a.web}"
    cookie = measure.sign_in(web, a.login)
    if not cookie:
        print(f"could not sign in at {web} as {a.login.partition(':')[0]}")
        return 1
    urls = [f"{web}{'' if key == 'iostart' else '/' + known[key]['folder']}/api/auth/me" for key in apps for _ in range(a.each)]
    bad = 0
    for n in range(a.rounds):
        go, codes = threading.Barrier(len(urls)), collections.Counter()

        def one(url):
            go.wait()
            return smoke.ask(url, timeout=60, cookie=cookie)[0]
        t = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(len(urls)) as ex:
            for code in ex.map(one, urls):
                codes[code or "no answer"] += 1
        took = time.perf_counter() - t
        bad += sum(v for k, v in codes.items() if k != 200)
        print(f"round {n + 1}: {len(urls)} requests at once to {len(apps)} apps in {took:.1f} s: "
              + ", ".join(f"{v} answered {k}" for k, v in sorted(codes.items(), key=str)))
    code, _, body, _ = smoke.ask(web + "/-/status")
    try:
        d = (json.loads(body) if code == 200 else {}).get("database") or {}
    except ValueError:
        d = {}
    if not d:
        print(f"the copy did not say how many database connections it holds (/-/status: {code})")
        return 1
    print(f"database connections: {d['open']} open of {d['limit']} allowed; {d['waited']} requests waited for one, "
          f"{d['refused']} were told the server is busy, {d['shed']} idle ones were closed to make room, {d['over']} went over")
    if d["open"] > d["limit"]:
        print("more connections are open than the copy is allowed")
        bad += 1
    if bad:
        print("not every request was answered as it should")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
