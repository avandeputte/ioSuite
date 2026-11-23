#!/usr/bin/env python3
"""Two running copies of ioSuite on one Shared ioSuite database, asked from outside: are they one suite?

    python3 tools/twocopies.py --web 80 --other-web 8081 --other-app iopix --login alex:PASSWORD

`--web` is the copy with the start page, `--other-web` the second copy (another port on this machine, or with --other-at
another machine), `--other-app` an app only the second copy runs, `--app` one only the first copy runs (unless said:
the first of the suite's apps that is neither the start page nor --other-app). Checks that each copy answers for the other's apps
(a request for an app that runs elsewhere is passed across), that one sign-in holds in both, that the list of apps says
where each runs, and that the log screen shows both copies on one timeline. Exit code 1 when something is not so.
Not part of the program: nothing imports it. The checks on GitHub run it (.github/workflows/tests.yml).
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure  # noqa: E402 - sign_in(): beside this file
import smoke  # noqa: E402 - ask(), manifests()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--at", default="127.0.0.1")
    p.add_argument("--web", type=int, default=80)
    p.add_argument("--other-at", default=None)
    p.add_argument("--other-web", type=int, default=8081)
    p.add_argument("--other-app", default="iopix")
    p.add_argument("--app", default=None, help="an app only the first copy runs")
    p.add_argument("--login", required=True, help="NAME:PASSWORD of a suite admin")
    p.add_argument("--wait", type=int, default=180)
    a = p.parse_args()
    known = smoke.manifests()
    one, two = f"http://{a.at}:{a.web}", f"http://{a.other_at or a.at}:{a.other_web}"
    folder = "/" + known[a.other_app]["folder"]
    mine = a.app or next(k for k in known if k not in (a.other_app, "iostart") and known[k].get("folder"))  # an app of the first copy
    until = time.time() + a.wait
    while time.time() < until and (smoke.ask(one + "/-/status", 5)[0] != 200 or smoke.ask(two + "/-/status", 5)[0] != 200):
        time.sleep(1)
    bad = []

    def check(what: str, ok: bool, more: str = "") -> None:
        print(f"{'ok  ' if ok else 'NOT '} {what}{'' if ok or not more else ': ' + more}")
        if not ok:
            bad.append(what)

    def js(url: str, cookie: str = None):
        code, kind, body, _ = smoke.ask(url, cookie=cookie)
        try:
            return code, json.loads(body)
        except ValueError:
            return code, {}

    check("both copies have started", smoke.ask(one + "/-/status", 5)[0] == 200 and smoke.ask(two + "/-/status", 5)[0] == 200)
    code, st = js(f"{two}{folder}/api/status")
    check(f"the second copy answers for {a.other_app}", code == 200 and bool(st.get("version")), str(code))
    code, st = js(f"{one}{folder}/api/status")
    check(f"the first copy passes a request for {a.other_app} across", code == 200 and bool(st.get("version")), str(code))
    code, kind, body, _ = smoke.ask(f"{one}{folder}/")
    check(f"and {a.other_app}'s page comes back through the first copy", code == 200 and "text/html" in kind, f"{code} {kind}")
    code, st = js(f"{two}/{known[mine]['folder']}/api/status")
    check(f"the second copy passes a request for {mine} across", code == 200 and bool(st.get("version")), str(code))
    code, kind, body, _ = smoke.ask(f"{two}/")
    check("the second copy passes the start page across", code == 200 and "text/html" in kind, f"{code} {kind}")

    cookie = measure.sign_in(one, a.login)
    check("a suite admin signs in at the first copy", bool(cookie))
    if cookie:
        name = a.login.partition(":")[0]
        code, me = js(f"{one}{folder}/api/auth/me", cookie)
        check(f"the sign-in holds in {a.other_app}, through the first copy", code == 200 and (me.get("user") or me).get("name") == name, f"{code} {str(me)[:120]}")
        code, me = js(f"{two}{folder}/api/auth/me", cookie)
        check("and at the second copy itself", code == 200 and (me.get("user") or me).get("name") == name, f"{code} {str(me)[:120]}")
        code, got = js(f"{one}/api/suite-admin/addresses", cookie)
        rows = {r.get("app"): r for r in got.get("apps") or []}
        copies = {str((rows.get(k) or {}).get("copy")) for k in (a.other_app, mine)}
        check("the list of apps says which copy runs each", code == 200 and len(copies) == 2 and "None" not in copies, f"{code} {sorted(copies)}")
        code, logs = js(f"{one}/api/suite-admin/logs?requests=1&limit=300", cookie)
        seen = {c.get("copy"): c for c in logs.get("copies") or []}
        check("the log screen reaches both copies", code == 200 and len(seen) == 2 and all(c.get("reachable") for c in seen.values()),
              f"{code} {[(c.get('copy'), c.get('reachable'), c.get('note')) for c in seen.values()]}")
        from_copies = {ln.get("copy") for ln in logs.get("lines") or []}
        check("and shows lines of both on one timeline", len(from_copies) == 2, str(sorted(str(x) for x in from_copies)))
        code, tiles = js(f"{one}/api/apps", cookie)
        check(f"the start page lists {a.other_app}", code == 200 and a.other_app in json.dumps(tiles), str(code))
        finds = [k for k in (a.other_app, mine) if (known[k].get("start") or {}).get("find")]
        if finds:  # one search: the app in this copy asked inside it, the one in the other copy over the network
            code, got = js(f"{one}/api/search?q=zq&wait=1&apps={','.join(finds)}", cookie)
            answered = {k: v for k, v in (got.get("apps") or {}).items() if "more" in v}
            check(f"one search asks {' and '.join(finds)} in both copies", code == 200 and sorted(answered) == sorted(finds),
                  f"{code} {got.get('apps')} late {got.get('late')}")
    print(f"{'two copies, one suite' if not bad else str(len(bad)) + ' thing(s) not as they should be'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
