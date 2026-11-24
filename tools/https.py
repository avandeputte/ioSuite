#!/usr/bin/env python3
"""A running copy of ioSuite asks for its own certificate and answers HTTPS with it: does that work from outside?

    python3 tools/https.py --web 8080 --sync 8443 --https 4443 --login alex:PASSWORD

The copy has to run under something that starts it again when it ends (systemd, Docker, or a shell loop), with
HTTPS_PORT in its machine's file set to `--https`. The certificate comes from a certificate authority of this
script's own (the tests' stand-in: iosuite_shared/tests/authority.py), which looks for its proof at the copy's port
for the pages, as Let's Encrypt would at port 80 of the name. Checks, through the panel's own routes: the
certificate is asked for and given; the copy starts again and answers HTTPS for the name, with a certificate that
verifies; the pages without HTTPS are still served to this machine; the port for devices answers both ways; the
suite's address says https://; a second asking is loaded without the copy starting again; switching it off puts the
address back. Exit code 1 when something is not so.
Not part of the program: nothing imports it. The checks on GitHub run it (.github/workflows/tests.yml).
"""
import argparse
import hashlib
import http.client
import json
import socket
import ssl
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "tools"))
import measure  # noqa: E402 - sign_in(): beside this file
from iosuite_shared.tests.authority import Authority  # noqa: E402


def ask(at: str, port: int, path: str = "/", name: str = None, tls: ssl.SSLContext = None, method: str = "GET", body=None, cookie: str = None,
        timeout: float = 20) -> tuple:
    """(status, headers, body, the certificate's fingerprint) of one request to at:port, asked by `name` (the Host,
    and the name the certificate is checked against); status 0 when nothing answers or the certificate is refused."""
    host = name or at
    try:
        sock = socket.create_connection((at, port), timeout=timeout)
        shown = ""
        if tls:
            sock = tls.wrap_socket(sock, server_hostname=host)
            shown = hashlib.sha256(sock.getpeercert(binary_form=True)).hexdigest()
        conn = http.client.HTTPConnection(at, port, timeout=timeout)
        conn.sock = sock
        scheme = "https" if tls else "http"
        headers = {"Host": host, "User-Agent": "iosuite-https-check", "Origin": f"{scheme}://{host}", "Connection": "close"}
        if cookie:
            headers["Cookie"] = cookie
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=data, headers=headers)
        r = conn.getresponse()
        got = r.read()
        conn.close()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, got, shown
    except (OSError, ssl.SSLError, http.client.HTTPException) as e:
        return 0, {"error": str(e)}, b"", ""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--at", default="127.0.0.1")
    p.add_argument("--web", type=int, default=80)
    p.add_argument("--sync", type=int, default=8443)
    p.add_argument("--https", type=int, default=443, help="HTTPS_PORT of the copy's machine's file")
    p.add_argument("--name", default="home.example.com", help="the name the certificate is for (never looked up: every request goes to --at)")
    p.add_argument("--login", required=True, help="NAME:PASSWORD of a suite admin")
    p.add_argument("--wait", type=int, default=180)
    a = p.parse_args()
    bad = []

    def check(what: str, ok: bool, more: str = "") -> bool:
        print(f"{'ok  ' if ok else 'NOT '} {what}{'' if ok or not more else ': ' + str(more)[:300]}", flush=True)
        if not ok:
            bad.append(what)
        return ok

    def up(port: int, tls=None, seconds: float = None) -> bool:
        end = time.time() + (a.wait if seconds is None else seconds)
        while time.time() < end:
            if ask(a.at, port, "/-/status", a.name if tls else None, tls, timeout=5)[0] == 200:
                return True
            time.sleep(0.5)
        return False

    with Authority(http_port=a.web) as ca:
        trust = ssl.create_default_context(cadata=ca.root_pem())
        if not check("the copy has started", up(a.web)):
            return 1
        cookie = measure.sign_in(f"http://{a.at}:{a.web}", a.login)
        if not check("a suite admin signs in", bool(cookie)):
            return 1

        def api(method: str, path: str, body=None):
            code, _h, got, _f = ask(a.at, a.web, "/api/suite-admin/" + path, method=method, body=body, cookie=cookie, timeout=240)
            try:
                return code, json.loads(got)
            except ValueError:
                return code, {"detail": got[:200].decode("utf-8", "replace")}

        def address() -> str:
            return next((s["value"] for s in api("GET", "settings")[1].get("suite") or [] if s["name"] == "PUBLIC_URL"), "?")

        check("no HTTPS before", ask(a.at, a.https, "/", a.name, trust, timeout=5)[0] == 0 and ask(a.at, a.sync, "/-/status", a.name, trust, timeout=5)[0] == 0)
        code, got = api("PUT", "settings/_suite/PUBLIC_URL", {"value": f"http://{a.name}:{a.web}"})
        check("the suite is given an address with a name", code == 200, f"{code} {got}")
        code, d = api("PUT", "certificate", {"on": True, "ca": ca.directory, "email": "admin@example.com"})
        check("the certificate is switched on", code == 200 and d.get("on") and d.get("wanted") == [a.name] and d.get("due") == "there is none yet", f"{code} {d}")
        code, d = api("POST", "certificate")
        have = d.get("certificate") or {}
        check("it is asked for and given", code == 200 and have.get("names") == [a.name], f"{code} {d.get('detail') or d}")
        check("the authority found its proof at the copy", ("http-01", a.name) in ca.looked and len(ca.accounts) == 1, str(ca.looked))

        if check("the copy starts again and answers HTTPS", up(a.https, trust)):
            code, h, got, shown = ask(a.at, a.https, "/", a.name, trust)
            check("the pages over HTTPS, with the certificate that was given", code == 200 and "text/html" in h.get("content-type", "") and shown == have.get("fingerprint"),
                  f"{code} {h.get('content-type')} {shown[:16]} {str(have.get('fingerprint'))[:16]}")
            port = "" if a.https == 443 else f":{a.https}"
            # a browser elsewhere that asks the pages without HTTPS by that name is sent on to HTTPS (the tests hold
            # that); this machine is one the suite trusts (a reverse proxy, another copy), and is served as before
            check("the pages without HTTPS are served to this machine as before", ask(a.at, a.web, "/", a.name)[0] == 200 and ask(a.at, a.web, "/")[0] == 200)
            # nothing there without a password: the refusal is the answer, without HTTPS and with it
            check("the port for devices answers without HTTPS as before", ask(a.at, a.sync, "/dav/ext")[0] == 401, ask(a.at, a.sync, "/dav/ext")[0])
            code, _h, _b, shown = ask(a.at, a.sync, "/dav/ext", a.name, trust)
            check("and over HTTPS", code == 401 and shown == have.get("fingerprint"), code)
            check("a name the certificate is not for is refused by whoever checks it", ask(a.at, a.https, "/", "other.example.com", trust)[0] == 0)
            check("the suite's address says https://", address() == f"https://{a.name}{port}", address())
            code, d = api("GET", "certificate")
            check("the panel says this server answers HTTPS", code == 200 and d.get("serving") and d.get("pagesPort") == a.https and not d.get("note"), f"{code} {d}")

            code, d = api("POST", "certificate")  # as a renewal will: another certificate for the same names
            again = (d.get("certificate") or {}).get("fingerprint")
            check("a second certificate is given", code == 200 and again and again != have.get("fingerprint"), f"{code} {d.get('detail')}")
            code, _h, _b, shown = ask(a.at, a.https, "/", a.name, trust)
            check("and loaded without the copy starting again", code == 200 and shown == again, f"{code} {shown[:16]}")

            code, d = api("PUT", "certificate", {"on": False})
            check("switched off, the address says what it said", code == 200 and not d.get("on") and address() == f"http://{a.name}:{a.web}", f"{code} {address()}")
    print("the suite answers HTTPS with a certificate of its own" if not bad else f"{len(bad)} thing(s) not as they should be")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
